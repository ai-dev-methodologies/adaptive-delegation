from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("adaptive_release_preflight", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReleasePreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.version = (
            ROOT / "adaptive-delegation" / "VERSION"
        ).read_text(encoding="utf-8").strip()
        cls.changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        cls.policy = json.loads(
            (
                ROOT
                / "adaptive-delegation"
                / "config"
                / "model-routing.defaults.json"
            ).read_text(encoding="utf-8")
        )

    def test_repository_readme_matches_package_contract(self) -> None:
        result = self.module.validate_readme_contract(
            self.readme, self.version, self.changelog, self.policy
        )
        self.assertEqual(result["version"], self.version)
        self.assertEqual(result["main_efforts"], ["high", "xhigh", "max"])
        self.assertGreaterEqual(result["unique_policy_ladders"], 5)

    def test_stale_version_or_ladder_fails_closed(self) -> None:
        with self.assertRaises(self.module.PreflightError):
            self.module.validate_readme_contract(
                self.readme.replace(
                    f"Current installable package version: `{self.version}`.",
                    "Current installable package version: `0.0.0`.",
                ),
                self.version,
                self.changelog,
                self.policy,
            )
        bindings = self.policy["route_bindings"]
        ladder = self.policy["escalation_ladders"]["simple_lookup_or_extraction"]
        display = " -> ".join(
            self.module._route_label(route_id, bindings) for route_id in ladder
        )
        with self.assertRaises(self.module.PreflightError):
            self.module.validate_readme_contract(
                self.readme.replace(f"`{display}`", "`stale route`"),
                self.version,
                self.changelog,
                self.policy,
            )

    def test_stale_main_model_or_effort_fails_closed(self) -> None:
        for stale in (
            self.readme.replace("`gpt-6-astra`", "`gpt-5.6-sol`"),
            self.readme.replace("`high`, `xhigh`, or `max` effort", "`ultra` effort"),
        ):
            with self.subTest(readme=stale[:80]):
                with self.assertRaises(self.module.PreflightError):
                    self.module.validate_readme_contract(
                        stale, self.version, self.changelog, self.policy
                    )
        policy = dict(self.policy, required_model="gpt-5.6-sol")
        with self.assertRaises(self.module.PreflightError):
            self.module.validate_readme_contract(
                self.readme, self.version, self.changelog, policy
            )


if __name__ == "__main__":
    unittest.main()
