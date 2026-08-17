from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_isolated_dogfood.py"


def load_module():
    spec = importlib.util.spec_from_file_location("isolated_dogfood", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class IsolatedDogfoodTests(unittest.TestCase):
    def test_derives_one_parent_session_from_thread_started_output(self) -> None:
        module = load_module()
        session_id = "019ff0df-6dd7-7682-90b7-e17e07630999"
        output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": session_id}),
                json.dumps({"type": "turn.started"}),
            ]
        )
        self.assertEqual(module.derive_parent_session_id(output), session_id)
        with self.assertRaises(ValueError):
            module.derive_parent_session_id("{}\n")
        with self.assertRaises(ValueError):
            module.derive_parent_session_id(
                output + "\n" + json.dumps({"type": "thread.started", "thread_id": "foreign"})
            )
        with self.assertRaises(ValueError):
            module.derive_parent_session_id("[]\n")

    def test_rejects_symlinked_or_oversized_state_evidence(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            regular = root / "state.json"
            regular.write_text("{}\n", encoding="utf-8")
            symlink = root / "linked.json"
            symlink.symlink_to(regular)
            with self.assertRaises(ValueError):
                module.read_json_object(symlink)
            regular.write_text("x" * 32, encoding="utf-8")
            with self.assertRaises(ValueError):
                module.read_json_object(regular, maximum_bytes=16)

    def test_installation_docs_require_promotion_before_user_level_install(self) -> None:
        for name in ("README.md", "INSTALL.md"):
            content = (ROOT / name).read_text(encoding="utf-8")
            promotion = content.index("verify_isolated_dogfood.py")
            approval = content.index("# With explicit user approval only:", promotion)
            install = content.index("python3 scripts/install.py", approval)
            self.assertLess(promotion, approval, name)
            self.assertLess(approval, install, name)
        prompt = (ROOT / "prompts" / "maintain-adaptive-delegation.md").read_text(encoding="utf-8")
        self.assertIn("Do not proceed from unit tests directly", prompt)
        gate = (ROOT / "scripts" / "verify_isolated_dogfood.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Non-goals:", gate)
        self.assertIn("do not perform additional reviews", gate)
        self.assertNotIn('"--ignore-user-config"', gate)

    def make_fake_codex(
        self,
        directory: Path,
        behavior: str,
        *,
        child_verifications: int = 1,
        foreign_child_binding: bool = False,
    ) -> Path:
        executable = directory / "codex"
        executable.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, subprocess, sys\n"
            "fixture = pathlib.Path.cwd()\n"
            "target = fixture / 'target.py'\n"
            + behavior
            + "\n"
            "candidate = pathlib.Path(os.environ['CODEX_HOME'])\n"
            "session = 'parent-session'\n"
            "turn = 'child-turn'\n"
            "task = 'adaptive_hook_free_dogfood'\n"
            + (
                "role = 'adaptive-sol-maker-medium'\n"
                if foreign_child_binding
                else "role = 'adaptive-luna-maker-high'\n"
            )
            +
            "workspace = str(fixture.resolve())\n"
            "rollout = candidate / 'sessions' / '2026' / '01' / '01' / 'rollout.jsonl'\n"
            "rollout.parent.mkdir(parents=True, exist_ok=True)\n"
            "spawn = {'parent_thread_id': session, 'depth': 1, 'agent_path': '/root/' + task, 'agent_role': role}\n"
            "rows = [\n"
            " {'type': 'session_meta', 'payload': {'session_id': session, 'id': 'child-session', 'parent_thread_id': session, 'cwd': workspace, 'thread_source': 'subagent', 'agent_role': role, 'agent_path': '/root/' + task, 'source': {'subagent': {'thread_spawn': spawn}}}},\n"
            " {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': turn}},\n"
            " {'type': 'turn_context', 'payload': {'turn_id': turn, 'model': 'gpt-5.6-luna', 'effort': 'high'}},\n"
            "]\n"
            "command = 'python3 -m unittest -v test_target.TargetTests.test_normalizes_whitespace_and_case'\n"
            f"for index in range({child_verifications}):\n"
            " call = 'call-' + str(index)\n"
            " tool_input = 'const r = await tools.exec_command({cmd:' + json.dumps(command) + '}); text(r.output);'\n"
            " rows.append({'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'exec', 'call_id': call, 'input': tool_input}})\n"
            " rows.append({'type': 'response_item', 'payload': {'type': 'custom_tool_call_output', 'call_id': call, 'output': [{'type': 'input_text', 'text': 'Ran 1 test in 0.001s\\n\\nOK\\n'}]}})\n"
            "rollout.write_text(''.join(json.dumps(row) + '\\n' for row in rows), encoding='utf-8')\n"
            "print(json.dumps({'type': 'thread.started', 'thread_id': session}))\n"
            "print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'The exact requested unittest passed (Ran 1 test). git diff -- target.py showed only the requested change.'}}))"
            + "\nprint(json.dumps({'event': 'completed', 'codex_home': os.environ.get('CODEX_HOME', '')}))\n",
            encoding="utf-8",
        )
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable

    def run_gate(
        self,
        module,
        *,
        behavior: str,
        extra: list[str] | None = None,
        child_verifications: int = 1,
        foreign_child_binding: bool = False,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            self.make_fake_codex(
                fake_bin,
                behavior,
                child_verifications=child_verifications,
                foreign_child_binding=foreign_child_binding,
            )
            auth = root / "auth.json"
            auth.write_text("{}", encoding="utf-8")
            user_home = root / "user-codex"
            managed = user_home / "skills" / "adaptive-delegation"
            managed.mkdir(parents=True)
            (managed / "marker").write_text("before", encoding="utf-8")
            environment = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}
            return module.run_gate(
                repo_root=ROOT,
                auth_source=auth,
                user_codex_home=user_home,
                keep_artifacts=False,
                environment=environment,
                extra_codex_args=["--test-expose-user-home", *(extra or [])],
            )

    def test_returns_success_when_fresh_session_updates_only_target(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior="target.write_text(\"def normalize(value):\\n    return value.strip().lower()\\n\", encoding='utf-8')",
        )
        self.assertEqual(result.exit_code, 0, result.diagnostic)

    def test_rejects_reported_targeted_evidence_without_bound_child_unittest(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior="target.write_text(\"def normalize(value):\\n    return value.strip().lower()\\n\", encoding='utf-8')",
            child_verifications=0,
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("observed []", result.diagnostic)

    def test_rejects_main_product_edit_and_targeted_test_activity(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior=(
                "target.write_text(\"def normalize(value):\\n"
                "    return value.strip().lower()\\n\", encoding='utf-8'); "
                "print(json.dumps({'type': 'item.completed', 'item': {"
                "'type': 'command_execution', 'command': "
                f"{('python3 -m unittest -v ' + module.TARGET_TEST + ' && git diff -- target.py')!r}"
                "}}))"
            ),
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("product", result.diagnostic)

    def test_rejects_removed_controller_commands(self) -> None:
        module = load_module()
        commands = [
            "/bin/zsh -lc '/usr/local/bin/python3 "
            "adaptive-delegation/scripts/controller_gate.py result "
            "--session-id s --workspace . --evidence-ref target.py "
            "--evidence-ref test_target.TargetTests.test_normalizes_whitespace_and_case'",
            "/bin/zsh -lc '/usr/local/bin/python3 "
            "adaptive-delegation/scripts/controller_gate.py close "
            "--session-id s --workspace . --evidence-ref target.py "
            "--evidence-ref test_target.TargetTests.test_normalizes_whitespace_and_case'",
        ]
        self.assertEqual(module.product_work_violations(commands), commands)

    def test_rejects_scope_drift_outside_target(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior="target.write_text(\"def normalize(value):\\n    return value.strip().lower()\\n\", encoding='utf-8'); (fixture / 'extra.py').write_text('drift', encoding='utf-8')",
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("scope drift", result.diagnostic)

    def test_rejects_fresh_command_output_that_references_user_codex_home(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior="target.write_text(\"def normalize(value):\\n    return value.strip().lower()\\n\", encoding='utf-8'); print(os.environ['USER_CODEX_HOME'])",
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("user Codex home", result.diagnostic)

    def test_portable_home_literal_is_not_treated_as_user_home_access(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior=(
                "target.write_text(\"def normalize(value):\\n"
                "    return value.strip().lower()\\n\", encoding='utf-8'); "
                "print('portable fallback: ~/.codex')"
            ),
        )
        self.assertEqual(result.exit_code, 0, result.diagnostic)

    def test_rejects_mutation_of_user_managed_files(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior="target.write_text(\"def normalize(value):\\n    return value.strip().lower()\\n\", encoding='utf-8'); pathlib.Path(os.environ['USER_CODEX_HOME'], 'skills', 'adaptive-delegation', 'marker').write_text('changed', encoding='utf-8')",
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("fingerprint", result.diagnostic)

    def test_rejects_mutation_of_user_hook_installation_surface(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior=(
                "target.write_text(\"def normalize(value):\\n"
                "    return value.strip().lower()\\n\", encoding='utf-8'); "
                "pathlib.Path(os.environ['USER_CODEX_HOME'], 'hooks.json').write_text("
                "'changed', encoding='utf-8')"
            ),
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("fingerprint", result.diagnostic)

    def test_allows_append_only_runtime_audit_evidence(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior=(
                "target.write_text(\"def normalize(value):\\n"
                "    return value.strip().lower()\\n\", encoding='utf-8'); "
                "audit = pathlib.Path(os.environ['USER_CODEX_HOME'], 'state', "
                "'model-routing', 'attempts.jsonl'); "
                "audit.parent.mkdir(parents=True, exist_ok=True); "
                "audit.open('a', encoding='utf-8').write('{}\\n')"
            ),
        )
        self.assertEqual(result.exit_code, 0, result.diagnostic)

    def test_rejects_verification_ceiling_drift(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior="target.write_text(\"def normalize(value):\\n    return value.strip().lower()\\n\", encoding='utf-8'); print('test_adjacent')",
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("verification ceiling", result.diagnostic)

    def test_rejects_duplicate_target_verification(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior="target.write_text(\"def normalize(value):\\n    return value.strip().lower()\\n\", encoding='utf-8')",
            child_verifications=2,
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("exactly the declared targeted Python verification once", result.diagnostic)

    def test_rejects_foreign_native_child_role(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior="target.write_text(\"def normalize(value):\\n    return value.strip().lower()\\n\", encoding='utf-8')",
            foreign_child_binding=True,
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("rollout metadata", result.diagnostic)

    def test_rejects_optional_package_archaeology_in_main_preflight(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior=(
                "target.write_text(\"def normalize(value):\\n"
                "    return value.strip().lower()\\n\", encoding='utf-8'); "
                "print(json.dumps({'type': 'item.completed', 'item': {"
                "'type': 'command_execution', 'command': "
                "'sed -n 1,200p TOKEN_EFFICIENCY_CONTINUITY.md'}}))"
            ),
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("routing preflight", result.diagnostic)

    def test_rejects_broad_model_routing_config_dump(self) -> None:
        module = load_module()
        result = self.run_gate(
            module,
            behavior=(
                "target.write_text(\"def normalize(value):\\n"
                "    return value.strip().lower()\\n\", encoding='utf-8'); "
                "print(json.dumps({'type': 'item.completed', 'item': {"
                "'type': 'command_execution', 'command': "
                "\"jq '.routes // .routing // .' model-routing.defaults.json\"}}))"
            ),
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("routing preflight", result.diagnostic)

    def test_accepts_bounded_config_and_role_reads_in_one_command(self) -> None:
        module = load_module()
        command = (
            "jq '{task_defaults, role_binding: "
            ".role_bindings[\"adaptive-luna-maker-high\"]}' "
            '"$RUNTIME_HOME/skills/adaptive-delegation/config/'
            'model-routing.defaults.json"; '
            'ROLE_FILE="$(rg --files "$RUNTIME_HOME/agents" | '
            'rg "/adaptive-luna-maker-high\\.toml$" | head -1)"; '
            "sed -n '1,200p' \"$ROLE_FILE\""
        )
        result = self.run_gate(
            module,
            behavior=(
                "target.write_text(\"def normalize(value):\\n"
                "    return value.strip().lower()\\n\", encoding='utf-8'); "
                "print(json.dumps({'type': 'item.completed', 'item': {"
                "'type': 'command_execution', 'command': "
                f"{command!r}" "}}))"
            ),
        )
        self.assertEqual(result.exit_code, 0, result.diagnostic)
