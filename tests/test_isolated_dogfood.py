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
    def test_accepts_native_targeted_evidence_wording(self) -> None:
        module = load_module()
        output = (
            "The exact targeted test passed (Ran 1 test — OK), and the scoped "
            "diff contains only the requested change."
        )
        self.assertTrue(module.reported_targeted_evidence(output))
        native_output = (
            "The exact requested unittest passed: 1 test, `OK`. "
            "`git diff -- target.py` showed only the requested change."
        )
        self.assertTrue(module.reported_targeted_evidence(native_output))

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

    def make_fake_codex(self, directory: Path, behavior: str) -> Path:
        executable = directory / "codex"
        executable.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, subprocess, sys\n"
            "fixture = pathlib.Path.cwd()\n"
            "target = fixture / 'target.py'\n"
            + behavior
            + "\nresult = subprocess.run(['python3', '-m', 'unittest', '-v', "
            + repr("test_target.TargetTests.test_normalizes_whitespace_and_case")
            + "], check=False, capture_output=True, text=True)"
            + "\nprint(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'The exact requested unittest passed (Ran 1 test). git diff -- target.py showed only the requested change.'}}))"
            + "\nprint(json.dumps({'event': 'completed', 'codex_home': os.environ.get('CODEX_HOME', '')}))\n",
            encoding="utf-8",
        )
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable

    def run_gate(self, module, *, behavior: str, extra: list[str] | None = None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            self.make_fake_codex(fake_bin, behavior)
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
            behavior=(
                "target.write_text(\"def normalize(value):\\n"
                "    return value.strip().lower()\\n\", encoding='utf-8'); "
                "subprocess.run(['python3', '-m', 'unittest', '-v', "
                f"{module.TARGET_TEST!r}], check=False, capture_output=True, text=True)"
            ),
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("exactly the declared targeted Python verification once", result.diagnostic)

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
            "sed -n '1,200p' "
            '"$RUNTIME_HOME/agents/adaptive-luna-maker-high.toml"'
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
