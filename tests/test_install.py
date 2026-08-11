from __future__ import annotations

import json
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.py"


class InstallerTests(unittest.TestCase):
    def run_installer(
        self, codex_home: Path, *extra: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(INSTALLER), "--codex-home", str(codex_home), *extra],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_installs_portable_package_dispatcher_and_policy_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / ".codex"
            agents = codex_home / "agents"
            agents.mkdir(parents=True)
            shared_role = agents / "custom-shared-role.toml"
            shared_role.write_text("shared role\n", encoding="utf-8")
            result = self.run_installer(codex_home)
            self.assertEqual(result.returncode, 0, result.stderr)

            installed = codex_home / "skills" / "adaptive-delegation"
            dispatcher = codex_home / "scripts" / "adaptive_dispatch_attestation.py"
            policy = json.loads(
                (installed / "config" / "model-routing.defaults.json").read_text()
            )
            self.assertEqual(policy["audit"]["path_base"], "runtime_home")
            self.assertFalse(policy["audit"]["ledger"].startswith(("~", "$", "/")))
            self.assertFalse(policy["audit"]["review_dir"].startswith(("~", "$", "/")))
            native = policy["native_routing"]
            self.assertEqual(
                native["primary_selection_mode"], "verified-fixed-agent-type"
            )
            self.assertFalse(native["fixed_role_model_override_required"])
            self.assertFalse(
                native["model_override_enum_absence_is_native_rejection"]
            )
            self.assertEqual(
                policy["escalation_ladders"][
                    "clear_implementation_or_transformation"
                ],
                [
                    "luna_high",
                    "luna_xhigh",
                    "luna_max",
                    "terra_medium",
                    "sol_medium",
                    "sol_high",
                    "main_takeover_sol_ultra",
                ],
            )
            self.assertFalse(policy["routing_observations"]["terra"]["paired_ab"])
            self.assertEqual(
                policy["escalation_ladders"][
                    "latency_insensitive_long_horizon_with_strong_oracle"
                ],
                [
                    "luna_max",
                    "terra_xhigh",
                    "terra_max",
                    "sol_high",
                    "main_takeover_sol_ultra",
                ],
            )
            self.assertTrue((installed / "SKILL.md").is_file())
            source_version = (
                ROOT / "adaptive-delegation" / "VERSION"
            ).read_text(encoding="utf-8").strip()
            self.assertEqual(
                (installed / "VERSION").read_text(encoding="utf-8").strip(),
                source_version,
            )
            self.assertTrue((installed / "scripts" / "read_continuity.py").is_file())
            self.assertTrue((installed / "scripts" / "controller_gate.py").is_file())
            self.assertTrue(
                (installed / "references" / "CODEX-ISSUE-REPORT-PROMPT.md").is_file()
            )
            self.assertTrue(dispatcher.is_file())
            self.assertEqual(stat.S_IMODE(dispatcher.stat().st_mode), 0o700)
            for role_name in policy["role_bindings"]:
                self.assertTrue(role_name.startswith("adaptive-"), role_name)
                role = codex_home / "agents" / f"{role_name}.toml"
                self.assertTrue(role.is_file(), role)
                self.assertEqual(stat.S_IMODE(role.stat().st_mode), 0o600)
            self.assertEqual(shared_role.read_text(), "shared role\n")
            self.assertIn(f"package version: {source_version}", result.stdout)
            self.assertFalse((codex_home / "state").exists())
            self.assertFalse((codex_home / "auth.json").exists())
            self.assertFalse(any(installed.rglob("__pycache__")))
            self.assertFalse(any(installed.rglob("*.pyc")))
            self.assertFalse((installed / "tests").exists())
            self.assertFalse((installed / "CROSS_PC_TRANSFER.md").exists())
            self.assertFalse(
                (installed / "references" / "MODEL_ROUTING_POLICY.md").exists()
            )
            self.assertFalse((installed / "references" / "TRIGGERS.md").exists())

            second = self.run_installer(codex_home)
            self.assertEqual(second.returncode, 0, second.stderr)

            hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))[
                "hooks"
            ]
            for event in ("UserPromptSubmit", "PreToolUse"):
                commands = [
                    hook["command"]
                    for group in hooks[event]
                    for hook in group.get("hooks", [])
                    if "command" in hook
                ]
                controller_commands = [
                    command for command in commands if "controller_gate.py" in command
                ]
                self.assertEqual(len(controller_commands), 1, (event, commands))
            self.assertNotIn("Stop", hooks)
            config = tomllib.loads(
                (codex_home / "config.toml").read_text(encoding="utf-8")
            )
            trust = config["hooks"]["state"]
            self.assertEqual(len(trust), 2)
            self.assertTrue(any(":pre_tool_use:" in key for key in trust))
            self.assertTrue(any(":user_prompt_submit:" in key for key in trust))
            for item in trust.values():
                self.assertRegex(item["trusted_hash"], r"^sha256:[0-9a-f]{64}$")

    def test_update_removes_only_roles_managed_by_the_previous_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / ".codex"
            installed = codex_home / "skills" / "adaptive-delegation"
            config = installed / "config"
            agents = codex_home / "agents"
            config.mkdir(parents=True)
            agents.mkdir(parents=True)
            (config / "model-routing.defaults.json").write_text(
                json.dumps(
                    {
                        "role_bindings": {
                            "adaptive-obsolete-maker": {
                                "model": "obsolete",
                                "reasoning_effort": "low",
                            },
                            "adaptive-terra-maker-max": {
                                "model": "gpt-5.6-terra",
                                "reasoning_effort": "max",
                            },
                            "adaptive-terra-checker-max": {
                                "model": "gpt-5.6-terra",
                                "reasoning_effort": "max",
                            },
                            "adaptive-terra-checker-xhigh": {
                                "model": "gpt-5.6-terra",
                                "reasoning_effort": "xhigh",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            obsolete = agents / "adaptive-obsolete-maker.toml"
            unrelated = agents / "custom-role.toml"
            obsolete.write_text("obsolete\n", encoding="utf-8")
            restored_terra = [
                agents / "adaptive-terra-maker-max.toml",
                agents / "adaptive-terra-checker-max.toml",
                agents / "adaptive-terra-checker-xhigh.toml",
            ]
            for role in restored_terra:
                role.write_text("obsolete Terra route\n", encoding="utf-8")
            unrelated.write_text("preserve\n", encoding="utf-8")

            result = self.run_installer(codex_home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(obsolete.exists())
            self.assertTrue(all(role.is_file() for role in restored_terra))
            self.assertTrue(
                all(
                    role.read_text(encoding="utf-8") != "obsolete Terra route\n"
                    for role in restored_terra
                )
            )
            self.assertTrue((agents / "adaptive-terra-maker-medium.toml").is_file())
            self.assertTrue((agents / "adaptive-terra-maker-high.toml").is_file())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve\n")

    def test_existing_codex_home_permissions_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / ".codex"
            codex_home.mkdir()
            codex_home.chmod(0o755)

            result = self.run_installer(codex_home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(stat.S_IMODE(codex_home.stat().st_mode), 0o755)

    def test_dry_run_validates_without_writing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / ".codex"
            result = self.run_installer(codex_home, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("no files changed", result.stdout)
            self.assertFalse(codex_home.exists())

    def test_install_preserves_unrelated_hooks_and_does_not_add_stop_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / ".codex"
            codex_home.mkdir(parents=True)
            (codex_home / "config.toml").write_text(
                'model = "gpt-5.6-sol"\n', encoding="utf-8"
            )
            hooks_path = codex_home / "hooks.json"
            foreign_wrapper = (
                "foreign-wrapper --delegate "
                f"{codex_home}/skills/adaptive-delegation/scripts/controller_gate.py "
                "--audit"
            )
            hooks_path.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "PreToolUse": [
                                {
                                    "matcher": "Read",
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "preserve-pre-tool",
                                        }
                                    ],
                                }
                            ],
                            "UserPromptSubmit": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "preserve-prompt",
                                        },
                                        {
                                            "type": "command",
                                            "command": foreign_wrapper,
                                        }
                                    ]
                                }
                            ],
                            "Stop": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "single-stop-owner",
                                        }
                                    ]
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_installer(codex_home)

            self.assertEqual(result.returncode, 0, result.stderr)
            hooks = json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"]
            serialized = json.dumps(hooks, sort_keys=True)
            self.assertIn("preserve-pre-tool", serialized)
            self.assertIn("preserve-prompt", serialized)
            self.assertIn(foreign_wrapper, serialized)
            self.assertEqual(serialized.count("controller_gate.py"), 3)
            stop_commands = [
                hook["command"]
                for group in hooks["Stop"]
                for hook in group.get("hooks", [])
            ]
            self.assertEqual(stop_commands, ["single-stop-owner"])
            installed_config = (codex_home / "config.toml").read_text(encoding="utf-8")
            self.assertIn('model = "gpt-5.6-sol"', installed_config)
            self.assertIn("adaptive-delegation-controller-trust:start", installed_config)

    def test_reinstall_replaces_unmarked_controller_trust_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / ".codex"
            first = self.run_installer(codex_home)
            self.assertEqual(first.returncode, 0, first.stderr)
            config_path = codex_home / "config.toml"
            config_text = config_path.read_text(encoding="utf-8")
            config_text = config_text.replace(
                "# adaptive-delegation-controller-trust:start\n", ""
            ).replace("# adaptive-delegation-controller-trust:end\n", "")
            config_path.write_text(config_text, encoding="utf-8")

            second = self.run_installer(codex_home)

            self.assertEqual(second.returncode, 0, second.stderr)
            parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
            trust = parsed["hooks"]["state"]
            controller_keys = [
                key for key in trust if str(codex_home / "hooks.json") in key
            ]
            self.assertEqual(len(controller_keys), 2)

    def test_docs_define_weighted_budget_and_portable_trigger_contract(self) -> None:
        skill = (ROOT / "adaptive-delegation" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        reference = (
            ROOT
            / "adaptive-delegation"
            / "references"
            / "MODEL_ROUTING_POLICY.md"
        ).read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())

        self.assertIn("ceil(input_tokens / 4) + output_tokens", skill)
        self.assertIn("routing proxy, not a provider", skill)
        self.assertIn("Model-relative price factors are never aggregated", reference)
        self.assertIn("API token prices", reference)
        self.assertIn("token-effective", skill)
        self.assertIn("\ud1a0\ud070\ud6a8\uc728\ud654", skill)
        self.assertIn("\ud1a0\ud070 \ud6a8\uc728\ud654", skill)
        self.assertIn(
            "absence of a selected model from the optional `model` override enum does not reject",
            normalized_skill,
        )
        self.assertIn("prefer Native V2 through a verified fixed `agent_type`", normalized_skill)
        self.assertIn("Select the installed package role", normalized_skill)
        self.assertIn("Use typed direct only when", reference)

    def test_public_docs_are_codex_only_and_links_resolve(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        reporting = (ROOT / "REPORTING.md").read_text(encoding="utf-8")
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        cross_pc = (
            ROOT / "adaptive-delegation" / "CROSS_PC_TRANSFER.md"
        ).read_text(encoding="utf-8")
        normalized_install = " ".join(install.split())
        self.assertTrue(
            readme.startswith("# Adaptive Delegation\n\n**Codex-only skill:**")
        )
        self.assertIn("Codex native subagents", readme)
        self.assertIn(
            "Model or reasoning escalation changes capability, not authority or scope.",
            readme,
        )
        skill = (ROOT / "adaptive-delegation" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("**OBJECTIVE LOCK**", skill)
        self.assertIn("## Primary invariant — Objective Lock", skill)
        self.assertIn("No valid Objective Lock, no child launch.", skill)
        self.assertLess(
            skill.index("## Primary invariant — Objective Lock"),
            skill.index("## Policy source and routing defaults"),
        )
        self.assertIn("non-goals", skill)
        self.assertIn("additional reviews", skill)
        self.assertIn("The lock binds the main session too.", skill)
        self.assertIn("Continuity is an optimization, not a mandatory preflight.", skill)
        self.assertIn("do not reopen it, enumerate the package", skill)
        self.assertIn("do not silently turn a takeover into a redesign", skill)
        self.assertIn("issue-report", reporting)
        self.assertIn("record-submission", reporting)
        self.assertIn("issue-report-state.jsonl", reporting)
        self.assertIn("CODEX-ISSUE-REPORT-PROMPT.md", readme)
        self.assertIn("docs/DELEGATION-FLOW.md", readme)
        self.assertIn("## Invocation and `ultra` reasoning behavior", readme)
        self.assertIn(
            "Skill activation and reasoning effort are separate decisions.",
            readme,
        )
        self.assertIn("Does not activate this skill by itself.", readme)
        self.assertIn("explicit and opt-in", readme.lower())
        self.assertNotIn("eligible for implicit activation", readme.lower())
        self.assertIn("controller-only", readme)
        self.assertIn("Prompt text cannot upgrade the session.", readme)
        self.assertIn("Leaf `ultra` remains forbidden.", readme)
        self.assertIn("dispatch_attestation.jsonl", install)
        self.assertIn("Before updating, finalize every pending attempt", install)
        self.assertIn("## Maintainer promotion and local deployment order", readme)
        self.assertIn("`main` is the only deployable branch.", readme)
        self.assertIn("scripts/release_preflight.py --mode pre-merge", readme)
        self.assertIn("scripts/release_preflight.py --mode deploy", readme)
        self.assertIn("## Published-main deployment rule", install)
        self.assertIn("matches `origin/main`", install)
        install_prompt = (ROOT / "CODEX-INSTALL-PROMPT.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("git fetch --force origin main", install_prompt)
        self.assertIn("Never install a feature-branch commit.", install_prompt)
        self.assertIn(
            "new task ID, attempt index 1, dispatch ID, packet",
            normalized_install,
        )
        self.assertIn("Older installers cannot know", cross_pc)

        for role in (ROOT / "adaptive-delegation" / "roles").glob("adaptive-*.toml"):
            role_text = role.read_text(encoding="utf-8")
            normalized_role = " ".join(role_text.split())
            self.assertNotIn("under the user's current AGENTS.md", role_text)
            self.assertIn("portable adaptive-delegation", normalized_role)
            self.assertIn("If no valid lock is supplied, do not act.", normalized_role)
            self.assertIn(
                "Never request sandbox permission escalation or user approval.",
                normalized_role,
            )
            self.assertIn(
                "return the blocked action to the main",
                normalized_role,
            )

        owned_paths = {
            "AGENTS.md",
            "CHANGELOG.md",
            "CODEX-INSTALL-PROMPT.md",
            "README.md",
            "INSTALL.md",
            "REPORTING.md",
            ".gitignore",
            "prompts/maintain-adaptive-delegation.md",
            "adaptive-delegation/SKILL.md",
            "adaptive-delegation/VERSION",
            "adaptive-delegation/CROSS_PC_TRANSFER.md",
            "adaptive-delegation/TOKEN_EFFICIENCY_CONTINUITY.md",
            "adaptive-delegation/references/MODEL_ROUTING_POLICY.md",
            "adaptive-delegation/references/CODEX-ISSUE-REPORT-PROMPT.md",
            "adaptive-delegation/references/TRIGGERS.md",
            "adaptive-delegation/scripts/model_routing_audit.py",
            "scripts/version_status.py",
            "scripts/release_preflight.py",
            "adaptive-delegation/tests/test_model_routing_audit.py",
            ".github/ISSUE_TEMPLATE/routing-report.md",
            "docs/DELEGATION-FLOW.md",
            "tests/test_install.py",
            "tests/test_release_preflight.py",
            "tests/test_version_status.py",
        }
        text_files = {ROOT / name for name in owned_paths if (ROOT / name).is_file()}
        for path in text_files:
            if path.suffix.lower() != ".md":
                continue
            content = path.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", content):
                target = target.split("#", 1)[0]
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                self.assertTrue((path.parent / target).exists(), f"missing link: {path} -> {target}")

    def test_localized_triggers_are_only_in_skill_frontmatter(self) -> None:
        skill_path = ROOT / "adaptive-delegation" / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        _, frontmatter, body = skill.split("---", 2)
        self.assertIn(
            "description: Codex-only skill for Codex native subagents.",
            frontmatter,
        )
        allowed = {
            "\ud1a0\ud070\ud6a8\uc728\ud654",
            "\ud1a0\ud070 \ud6a8\uc728\ud654",
        }
        for literal in allowed:
            self.assertIn(literal, frontmatter)
            self.assertNotIn(literal, body)

        removed = {
            "\ud1a0\ud070 \ud6a8\uc728\uc801\uc778 \uc704\uc784",
            "\ub8e8\ub098 \uc6b0\uc120 \uc704\uc784",
            "\ube44\uc6a9 \ud6a8\uc728\uc801\uc778 \uc11c\ube0c\uc5d0\uc774\uc804\ud2b8",
            "\ubaa8\ub378 \uc120\ud0dd \uac80\uc99d",
        }
        text_files = {
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and not any(part.startswith(".") or part == "__pycache__" for part in path.parts)
            and path.suffix.lower() in {".md", ".py", ".json", ".toml", ".yaml", ".yml"}
        }
        all_text = "\n".join(path.read_text(encoding="utf-8") for path in text_files)
        for literal in removed:
            self.assertNotIn(literal, all_text)
        self.assertNotRegex(body, r"[\uac00-\ud7a3]")
        for path in text_files - {skill_path}:
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"[\uac00-\ud7a3]")


if __name__ == "__main__":
    unittest.main()
