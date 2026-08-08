from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.py"
VERSION_STATUS = ROOT / "scripts" / "version_status.py"


def load_module():
    spec = importlib.util.spec_from_file_location("adaptive_version_status", VERSION_STATUS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class VersionStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.codex_home = Path(self.temporary.name) / ".codex"
        self.source_version = (
            ROOT / "adaptive-delegation" / "VERSION"
        ).read_text(encoding="utf-8").strip()

    def run_status(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VERSION_STATUS),
                "--codex-home",
                str(self.codex_home),
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def install(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--codex-home",
                str(self.codex_home),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def payload(self) -> dict:
        result = self.run_status()
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_not_installed_reports_source_version_without_writing(self) -> None:
        payload = self.payload()

        self.assertEqual(payload["status"], "not_installed")
        self.assertEqual(payload["source"]["version"], self.source_version)
        self.assertFalse(payload["installed"]["exists"])
        self.assertIn("VERSION", payload["changes"]["source_only"])
        self.assertFalse(self.codex_home.exists())

    def test_installed_package_is_current_and_digest_matched(self) -> None:
        self.install()
        payload = self.payload()

        self.assertEqual(payload["status"], "current")
        self.assertEqual(payload["installed"]["version"], self.source_version)
        self.assertEqual(
            payload["source"]["package_digest"],
            payload["installed"]["package_digest"],
        )
        self.assertEqual(
            payload["changes"],
            {"installed_only": [], "modified": [], "source_only": []},
        )

    def test_same_version_content_change_is_reported_as_drift(self) -> None:
        self.install()
        installed_skill = self.codex_home / "skills" / "adaptive-delegation"
        with (installed_skill / "SKILL.md").open("a", encoding="utf-8") as handle:
            handle.write("\nlocal drift\n")

        payload = self.payload()

        self.assertEqual(payload["status"], "same_version_drift")
        self.assertEqual(payload["changes"]["modified"], ["SKILL.md"])

    def test_unexpected_installed_file_is_reported_as_drift(self) -> None:
        self.install()
        installed_skill = self.codex_home / "skills" / "adaptive-delegation"
        unexpected = installed_skill / "tests" / "test_unexpected.py"
        unexpected.parent.mkdir()
        unexpected.write_text("not runtime\n", encoding="utf-8")

        payload = self.payload()

        self.assertEqual(payload["status"], "same_version_drift")
        self.assertEqual(
            payload["changes"]["installed_only"],
            ["tests/test_unexpected.py"],
        )

    def test_older_and_unversioned_installations_are_distinguished(self) -> None:
        self.install()
        version_path = (
            self.codex_home / "skills" / "adaptive-delegation" / "VERSION"
        )
        version_path.write_text("0.3.0\n", encoding="utf-8")
        older = self.payload()
        self.assertEqual(older["status"], "update_available")
        self.assertEqual(older["installed"]["version"], "0.3.0")
        self.assertEqual(older["changes"]["modified"], ["VERSION"])

        version_path.unlink()
        unversioned = self.payload()
        self.assertEqual(unversioned["status"], "installed_unversioned")
        self.assertIsNone(unversioned["installed"]["version"])
        self.assertEqual(unversioned["changes"]["source_only"], ["VERSION"])

    def test_semver_ordering_and_metadata_contract(self) -> None:
        module = load_module()
        self.assertGreater(
            module.SemVer.parse("1.0.0").compare(module.SemVer.parse("1.0.0-rc.1")),
            0,
        )
        self.assertLess(
            module.SemVer.parse("1.0.0-rc.2").compare(
                module.SemVer.parse("1.0.0-rc.10")
            ),
            0,
        )
        with self.assertRaises(module.VersionStatusError):
            module.SemVer.parse("1.0.0-01")

        version = (ROOT / "adaptive-delegation" / "VERSION").read_text().strip()
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        prompt = (ROOT / "CODEX-INSTALL-PROMPT.md").read_text(encoding="utf-8")
        normalized_prompt = " ".join(prompt.split())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(version, re.compile(r"^\d+\.\d+\.\d+(?:[-+].+)?$"))
        self.assertIn(f"## [{version}]", changelog)
        self.assertIn("scripts/version_status.py", prompt)
        self.assertIn("git fetch --force origin main", prompt)
        self.assertIn("equals `git rev-parse origin/main`", normalized_prompt)
        self.assertIn("Never install a feature-branch commit.", prompt)
        self.assertIn("git checkout --detach FETCH_HEAD", prompt)
        self.assertIn("scripts/release_preflight.py --mode deploy", prompt)
        self.assertIn('AUTH_SOURCE=""', prompt)
        self.assertIn("local Codex authentication is required", normalized_prompt)
        self.assertIn("CODEX-INSTALL-PROMPT.md", readme)
        self.assertIn("CHANGELOG.md", readme)
        self.assertIn(f"Current installable package version: `{version}`.", readme)


if __name__ == "__main__":
    unittest.main()
