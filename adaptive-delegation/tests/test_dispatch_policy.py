from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "scripts"))

import dispatch_policy as contract  # noqa: E402


ROLE = "adaptive-luna-maker-xhigh"
WARNING = (
    "Adaptive Delegation blocked: main authority must be gpt-5.6-sol with "
    "reasoning_effort >= high. Current: {current}. No child was launched. Switch "
    "the main session to gpt-5.6-sol/high or above, then invoke "
    "$adaptive-delegation again."
)


def load_policy():
    path = PACKAGE_ROOT / "config" / "model-routing.defaults.json"
    return json.loads(path.read_text(encoding="utf-8"))


def authority(model="gpt-5.6-sol", effort="high"):
    return {"model": model, "reasoning_effort": effort}


def routing_audit():
    return {
        "task_id": "task-123",
        "attempt_index": 1,
        "decision_timestamp": "2026-07-31T12:00:00Z",
        "effort_escalations": 0,
        "model_escalations": 0,
        "task_class": "bounded_complex_implementation_or_verification",
        "oracle_strength": "strong",
        "risk_class": "medium",
        "selection_basis": "policy_default",
        "workspace": "/workspace/project",
        "main_session_id": "session-123",
        "surface_identity": "typed-external-worker",
        "surface_schema_fingerprint": "a" * 64,
    }


class DispatchPolicyTests(unittest.TestCase):
    def assert_blocked(self, declared, code, current):
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.enforce_main_authority(load_policy(), ROLE, declared)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.warning, WARNING.format(current=current))

    def test_missing_wrong_and_below_minimum_authority_are_blocked(self):
        self.assert_blocked(None, "MAIN_AUTHORITY_MISSING", "unknown/unknown")
        self.assert_blocked(
            authority("gpt-5.6-luna"), "MAIN_AUTHORITY_UNKNOWN", "gpt-5.6-luna/high"
        )
        self.assert_blocked(
            authority(effort="medium"),
            "MAIN_AUTHORITY_BELOW_MINIMUM",
            "gpt-5.6-sol/medium",
        )

    def test_high_xhigh_max_and_ultra_pass(self):
        for effort in ("high", "xhigh", "max", "ultra"):
            with self.subTest(effort=effort):
                decision = contract.enforce_main_authority(
                    load_policy(), ROLE, authority(effort=effort)
                )
                self.assertTrue(decision.enforced)
                self.assertEqual(decision.reasoning_effort, effort)

    def test_non_package_role_bypasses_authority_settings(self):
        policy = {"role_bindings": {ROLE: {}}}
        decision = contract.enforce_main_authority(policy, "external-role", None)
        self.assertFalse(decision.package_owned)
        self.assertFalse(decision.enforced)

    def test_operational_values_are_policy_driven(self):
        policy = copy.deepcopy(load_policy())
        policy["required_model"] = "test-main"
        policy["minimum_reasoning_effort"] = "xhigh"
        policy["allowed_main_efforts"] = ["xhigh", "max"]
        decision = contract.enforce_main_authority(
            policy, ROLE, authority("test-main", "max")
        )
        self.assertTrue(decision.enforced)
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.enforce_main_authority(policy, ROLE, authority("test-main", "high"))
        self.assertIn("test-main/xhigh", caught.exception.warning)

    def test_policy_consistency_is_fail_closed(self):
        for field, value in (
            ("enforcement_mode", "warn-only"),
            ("parent_model_mutation", True),
            ("allowed_main_efforts", ["medium", "high"]),
        ):
            with self.subTest(field=field):
                policy = copy.deepcopy(load_policy())
                policy[field] = value
                with self.assertRaises(contract.PolicyContractError):
                    contract.enforce_main_authority(policy, ROLE, authority())

    def test_routing_audit_accepts_only_bounded_finite_fields(self):
        valid = routing_audit()
        self.assertEqual(contract.validate_routing_audit(valid), valid)
        cases = []
        zero = copy.deepcopy(valid)
        zero["attempt_index"] = 0
        cases.append(zero)
        unknown = copy.deepcopy(valid)
        unknown["extra"] = "value"
        cases.append(unknown)
        sensitive = copy.deepcopy(valid)
        sensitive["prompt"] = "not retained"
        cases.append(sensitive)
        bad_enum = copy.deepcopy(valid)
        bad_enum["oracle_strength"] = "medium"
        cases.append(bad_enum)
        bad_id = copy.deepcopy(valid)
        bad_id["task_id"] = "unsafe id"
        cases.append(bad_id)
        bad_fingerprint = copy.deepcopy(valid)
        bad_fingerprint["surface_schema_fingerprint"] = "not-sha256"
        cases.append(bad_fingerprint)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(contract.PolicyContractError):
                    contract.validate_routing_audit(value)

    def test_fingerprint_is_stable(self):
        left = {"b": 2, "a": {"z": 1, "y": ["x"]}}
        right = {"a": {"y": ["x"], "z": 1}, "b": 2}
        self.assertEqual(
            contract.canonical_policy_fingerprint(left),
            contract.canonical_policy_fingerprint(right),
        )
        self.assertEqual(len(contract.canonical_policy_fingerprint(left)), 64)

    def test_module_has_no_content_or_event_builder_surface(self):
        source = (PACKAGE_ROOT / "scripts" / "dispatch_policy.py").read_text()
        self.assertLessEqual(len(source.splitlines()), 300)
        for name in (
            "build_pre_decision_event",
            "build_post_result_event",
            "objective",
            "prompt_body",
        ):
            self.assertFalse(hasattr(contract, name))
            self.assertNotIn(f"def {name}", source)


if __name__ == "__main__":
    unittest.main()
