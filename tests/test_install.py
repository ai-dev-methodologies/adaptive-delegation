from __future__ import annotations

import json
import re
import stat
import subprocess
import sys
import tempfile
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
            native = policy["native_routing"]
            self.assertEqual(
                native["primary_selection_mode"], "verified-fixed-agent-type"
            )
            self.assertFalse(native["fixed_role_model_override_required"])
            self.assertFalse(
                native["model_override_enum_absence_is_native_rejection"]
            )
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue(dispatcher.is_file())
            self.assertEqual(stat.S_IMODE(dispatcher.stat().st_mode), 0o700)
            for role_name in policy["role_bindings"]:
                self.assertTrue(role_name.startswith("adaptive-"), role_name)
                role = codex_home / "agents" / f"{role_name}.toml"
                self.assertTrue(role.is_file(), role)
                self.assertEqual(stat.S_IMODE(role.stat().st_mode), 0o600)
            self.assertEqual(shared_role.read_text(), "shared role\n")
            self.assertFalse((codex_home / "state").exists())
            self.assertFalse((codex_home / "auth.json").exists())
            self.assertFalse(any(installed.rglob("__pycache__")))
            self.assertFalse(any(installed.rglob("*.pyc")))

            second = self.run_installer(codex_home)
            self.assertEqual(second.returncode, 0, second.stderr)

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
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            obsolete = agents / "adaptive-obsolete-maker.toml"
            unrelated = agents / "custom-role.toml"
            obsolete.write_text("obsolete\n", encoding="utf-8")
            unrelated.write_text("preserve\n", encoding="utf-8")

            result = self.run_installer(codex_home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(obsolete.exists())
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
        self.assertIn("not absolute prices", reference)
        self.assertIn("token-effective", skill)
        self.assertIn("\ud1a0\ud070\ud6a8\uc728\ud654", skill)
        self.assertIn("\ud1a0\ud070 \ud6a8\uc728\ud654", skill)
        self.assertIn(
            "absence of Luna from the optional `model` override enum does not reject",
            normalized_skill,
        )
        self.assertIn("prefer Native V2 through a verified fixed `agent_type`", normalized_skill)
        self.assertIn("Select the installed Luna role", normalized_skill)
        self.assertIn("Use typed direct only when", reference)

    def test_public_docs_are_codex_only_and_links_resolve(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        reporting = (ROOT / "REPORTING.md").read_text(encoding="utf-8")
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        cross_pc = (
            ROOT / "adaptive-delegation" / "CROSS_PC_TRANSFER.md"
        ).read_text(encoding="utf-8")
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
        self.assertIn("do not silently turn a takeover into a redesign", skill)
        self.assertIn("issue-report", reporting)
        self.assertIn("dispatch_attestation.jsonl", install)
        self.assertIn("Older installers cannot know", cross_pc)

        owned_paths = {
            "AGENTS.md",
            "README.md",
            "INSTALL.md",
            "REPORTING.md",
            ".gitignore",
            "prompts/maintain-adaptive-delegation.md",
            "adaptive-delegation/SKILL.md",
            "adaptive-delegation/CROSS_PC_TRANSFER.md",
            "adaptive-delegation/TOKEN_EFFICIENCY_CONTINUITY.md",
            "adaptive-delegation/references/MODEL_ROUTING_POLICY.md",
            "adaptive-delegation/references/TRIGGERS.md",
            "adaptive-delegation/scripts/model_routing_audit.py",
            "adaptive-delegation/tests/test_model_routing_audit.py",
            ".github/ISSUE_TEMPLATE/routing-report.md",
            "tests/test_install.py",
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
