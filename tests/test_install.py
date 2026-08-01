from __future__ import annotations

import json
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
            shared_verifier = agents / "verifier.toml"
            shared_verifier.write_text("shared verifier\n", encoding="utf-8")
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
                if not role_name.startswith("adaptive-"):
                    continue
                role = codex_home / "agents" / f"{role_name}.toml"
                self.assertTrue(role.is_file(), role)
                self.assertEqual(stat.S_IMODE(role.stat().st_mode), 0o600)
            self.assertEqual(shared_verifier.read_text(), "shared verifier\n")
            self.assertFalse((codex_home / "state").exists())
            self.assertFalse((codex_home / "auth.json").exists())
            self.assertFalse(any(installed.rglob("__pycache__")))
            self.assertFalse(any(installed.rglob("*.pyc")))

            second = self.run_installer(codex_home)
            self.assertEqual(second.returncode, 0, second.stderr)

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
        self.assertIn("not a provider bill or official absolute price", reference)
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

    def test_localized_triggers_are_only_in_skill_frontmatter(self) -> None:
        skill_path = ROOT / "adaptive-delegation" / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        _, frontmatter, body = skill.split("---", 2)
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
            and not any(part in {".git", ".omx", ".serena", "__pycache__"} for part in path.parts)
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
