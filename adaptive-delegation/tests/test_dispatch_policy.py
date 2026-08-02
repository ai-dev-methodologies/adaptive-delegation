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

    def test_routing_audit_requires_complete_routes_and_bounded_overrides(self):
        selected = routing_audit()
        selected.update(
            {
                "route_id": "luna_max",
                "role": "adaptive-luna-maker-max",
                "route_model": "gpt-5.6-luna",
                "route_model_tier": "spark-tier",
                "route_reasoning_effort": "max",
            }
        )
        self.assertEqual(contract.validate_routing_audit(selected), selected)

        incomplete = copy.deepcopy(selected)
        incomplete.pop("route_model")
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.validate_routing_audit(incomplete)
        self.assertEqual(caught.exception.code, "ROUTING_AUDIT_ROUTE_FIELDS_INVALID")

        override = copy.deepcopy(selected)
        override["selection_basis"] = "human_override"
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.validate_routing_audit(override)
        self.assertEqual(caught.exception.code, "ROUTING_AUDIT_OVERRIDE_REASON_INVALID")

        override["override_reason"] = "Explicit operator decision within the ladder."
        self.assertEqual(contract.validate_routing_audit(override), override)

        unexpected = copy.deepcopy(selected)
        unexpected["override_reason"] = "Not allowed for policy selection."
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.validate_routing_audit(unexpected)
        self.assertEqual(caught.exception.code, "ROUTING_AUDIT_OVERRIDE_REASON_UNEXPECTED")

    def test_fingerprint_is_stable(self):
        left = {"b": 2, "a": {"z": 1, "y": ["x"]}}
        right = {"a": {"y": ["x"], "z": 1}, "b": 2}
        self.assertEqual(
            contract.canonical_policy_fingerprint(left),
            contract.canonical_policy_fingerprint(right),
        )
        self.assertEqual(len(contract.canonical_policy_fingerprint(left)), 64)

    def test_every_default_and_ladder_step_is_an_exact_package_route(self):
        policy = load_policy()
        routes = contract.validate_policy_routes(policy)
        for task, route_id in policy["task_defaults"].items():
            with self.subTest(task=task):
                self.assertIn(route_id, routes)
                self.assertEqual(policy["escalation_ladders"][task][0], route_id)
        for ladder_name, ladder in policy["escalation_ladders"].items():
            for route_id in ladder:
                with self.subTest(ladder=ladder_name, route=route_id):
                    route = routes[route_id]
                    self.assertEqual(
                        (route["authority"], route["model"], route["reasoning_effort"])
                        if route["authority"] == "main"
                        else (route["role"], route["model"], route["reasoning_effort"]),
                        ("main", "gpt-5.6-sol", "ultra")
                        if route["authority"] == "main"
                        else (
                            route["role"],
                            policy["role_bindings"][route["role"]]["model"],
                            policy["role_bindings"][route["role"]]["reasoning_effort"],
                        ),
                    )
                    if route["authority"] == "leaf":
                        self.assertNotEqual(route["reasoning_effort"], "ultra")
            for previous, following in zip(ladder, ladder[1:]):
                previous_route = routes[previous]
                following_route = routes[following]
                action = (
                    "main_takeover"
                    if following_route["authority"] == "main"
                    else "raise_model"
                    if previous_route["model"] != following_route["model"]
                    else "raise_effort"
                )
                with self.subTest(ladder=ladder_name, transition=(previous, following)):
                    self.assertEqual(
                        contract.route_transition(
                            policy,
                            task_class=ladder_name
                            if ladder_name in policy["task_defaults"]
                            else "bounded_complex_implementation_or_verification",
                            oracle_strength="weak"
                            if ladder_name == "bounded_complex_implementation_or_verification"
                            else "strong",
                            previous_route=previous,
                            next_action=action,
                        ),
                        following,
                    )

    def test_main_sol_classifies_each_slice_and_goal_labels_do_not_select_routes(self):
        policy = load_policy()
        decision = policy["decision_contract"]
        self.assertEqual(decision["owner"], "main_session")
        self.assertEqual(policy["required_model"], "gpt-5.6-sol")
        self.assertEqual(policy["minimum_reasoning_effort"], "high")
        self.assertTrue(decision["classify_before_child_launch"])
        self.assertTrue(decision["classify_each_bounded_slice"])
        self.assertEqual(decision["labels_do_not_select_routes"], ["goal", "ultragoal"])
        self.assertEqual(
            decision["long_horizon_route_requires_all"],
            [
                "active_goal_or_ultragoal",
                "latency_insensitive",
                "long_horizon",
                "strong_oracle",
                "risk_low_or_medium",
            ],
        )

        invalid = copy.deepcopy(policy)
        invalid["decision_contract"]["owner"] = "child_session"
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.validate_policy_routes(invalid)
        self.assertEqual(caught.exception.code, "DECISION_CONTRACT_INVALID")

        label_selected = copy.deepcopy(policy)
        label_selected["decision_contract"]["labels_do_not_select_routes"] = []
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.validate_policy_routes(label_selected)
        self.assertEqual(caught.exception.code, "DECISION_CONTRACT_INVALID")

    def test_route_transition_contract_rejects_jumps_and_illegal_overrides(self):
        policy = load_policy()
        self.assertEqual(
            contract.route_transition(
                policy,
                task_class="clear_implementation_or_transformation",
                oracle_strength="strong",
                previous_route="luna_high",
                next_action="raise_effort",
            ),
            "luna_xhigh",
        )
        self.assertEqual(
            contract.route_transition(
                policy,
                task_class="bounded_complex_implementation_or_verification",
                oracle_strength="weak",
                previous_route="luna_xhigh",
                next_action="main_takeover",
                failure_class="weak_oracle",
            ),
            "main_takeover_sol_ultra",
        )
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.route_transition(
                policy,
                task_class="clear_implementation_or_transformation",
                oracle_strength="strong",
                previous_route="luna_high",
                next_action="main_takeover",
                failure_class="capability_ceiling",
            )
        self.assertEqual(caught.exception.code, "TRANSITION_KIND_MISMATCH")
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.route_transition(
                policy,
                task_class="bounded_complex_implementation_or_verification",
                oracle_strength="weak",
                previous_route="sol_high",
                next_action="raise_model",
            )
        self.assertEqual(caught.exception.code, "TRANSITION_KIND_MISMATCH")
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
        self.assertIn("terra_max", policy["route_bindings"])
        self.assertIn("checker_terra_max", policy["route_bindings"])
        self.assertFalse(policy["routing_observations"]["terra"]["paired_ab"])
        self.assertEqual(
            contract.route_for(policy, "sol_medium")["role"],
            "adaptive-sol-maker-medium",
        )
        invalid_observation = copy.deepcopy(policy)
        invalid_observation["routing_observations"]["terra"]["paired_ab"] = True
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.validate_policy_routes(invalid_observation)
        self.assertEqual(caught.exception.code, "OBSERVATION_POLICY_INVALID")
        leaked_quota_route = copy.deepcopy(policy)
        leaked_quota_route["escalation_ladders"][
            "clear_implementation_or_transformation"
        ].insert(-1, "terra_max")
        with self.assertRaises(contract.PolicyContractError) as caught:
            contract.validate_policy_routes(leaked_quota_route)
        self.assertEqual(caught.exception.code, "QUOTA_LADDER_LEAK")
        with self.assertRaises(contract.PolicyContractError):
            contract.validate_route_selection(
                policy,
                route_id="luna_xhigh",
                task_class="clear_implementation_or_transformation",
                oracle_strength="strong",
                selection_basis="human_override",
                role="adaptive-luna-maker-xhigh",
                model="gpt-5.6-luna",
                reasoning_effort="xhigh",
            )

    def test_terra_routes_require_observed_failure_or_direct_latency_predicate(self):
        policy = load_policy()
        predicate = {field: True for field in contract.DIRECT_LATENCY_PREDICATE_FIELDS}
        predicate["latency_budget_ms"] = 5000
        selected = contract.validate_route_selection(
            policy,
            route_id="terra_medium",
            task_class="clear_implementation_or_transformation",
            oracle_strength="strong",
            selection_basis="direct_latency",
            role="adaptive-terra-maker-medium",
            model="gpt-5.6-terra",
            reasoning_effort="medium",
            direct_latency_predicate=predicate,
            use_mode="direct_latency",
        )
        self.assertEqual(selected["model"], "gpt-5.6-terra")
        quota_route = contract.validate_route_selection(
            policy,
            route_id="terra_xhigh",
            task_class="latency_insensitive_long_horizon_with_strong_oracle",
            oracle_strength="strong",
            selection_basis="failure_action",
            role="adaptive-terra-maker-xhigh",
            model="gpt-5.6-terra",
            reasoning_effort="xhigh",
            attempt_index=2,
            use_mode="post_luna_failure",
        )
        self.assertEqual(quota_route["reasoning_effort"], "xhigh")
        with self.assertRaisesRegex(contract.PolicyContractError, "direct Terra"):
            contract.validate_route_selection(
                policy,
                route_id="terra_medium",
                task_class="clear_implementation_or_transformation",
                oracle_strength="strong",
                selection_basis="direct_latency",
                role="adaptive-terra-maker-medium",
                model="gpt-5.6-terra",
                reasoning_effort="medium",
            )
        with self.assertRaisesRegex(contract.PolicyContractError, "runtime or tool"):
            contract.route_transition(
                policy,
                "clear_implementation_or_transformation",
                "strong",
                "luna_max",
                "raise_model",
                failure_class="tool_or_environment",
            )

    def test_module_has_no_content_or_event_builder_surface(self):
        source = (PACKAGE_ROOT / "scripts" / "dispatch_policy.py").read_text()
        self.assertLessEqual(len(source.splitlines()), 435)
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
