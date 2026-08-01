import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "model_routing_audit.py"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import model_routing_audit as audit  # noqa: E402


class ModelRoutingAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.ledger = self.root / "state" / "attempts.jsonl"
        self.review_dir = self.root / "reviews"

    def tearDown(self):
        self.temp_dir.cleanup()

    def addCleanup(self, function, *args, **kwargs):
        return super().addCleanup(function, *args, **kwargs)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            check=False,
            capture_output=True,
            text=True,
        )

    def write_event(self, name, event, mode=0o600):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(event), encoding="utf-8")
        os.chmod(path, mode)
        return path

    @staticmethod
    def pre(attempt_id, task_id, index=1, model="gpt-5.6-luna", task_class="clear_implementation_or_transformation"):
        return {
            "schema_version": "0.1.0",
            "event_type": "pre_decision",
            "attempt_id": attempt_id,
            "task_id": task_id,
            "attempt_index": index,
            "timestamp": "2026-07-31T00:00:00Z",
            "model": model,
            "model_tier": {
                "gpt-5.6-luna": "spark-tier",
                "gpt-5.6-terra": "standard-tier",
                "gpt-5.6-sol": "frontier-tier",
            }[model],
            "reasoning_effort": "xhigh" if model != "gpt-5.6-sol" else "ultra",
            "rationale": {
                "task_class": task_class,
                "oracle_strength": "strong",
                "risk_class": "medium",
                "prior_failure_class": None,
                "prior_attempts": index - 1,
                "selection_basis": "policy_default",
            },
        }

    @staticmethod
    def post(attempt_id, task_id, index=1, **overrides):
        event = {
            "schema_version": "0.1.0",
            "event_type": "post_result",
            "attempt_id": attempt_id,
            "task_id": task_id,
            "attempt_index": index,
            "timestamp": "2026-07-31T00:01:00Z",
            "accepted": True,
            "failure_class": "none",
            "effort_escalations": 0,
            "model_escalations": 0,
            "final_model": "gpt-5.6-luna",
            "final_model_tier": "spark-tier",
            "final_reasoning_effort": "xhigh",
            "elapsed_ms": 100,
            "input_tokens": 10,
            "output_tokens": 5,
            "weighted_tokens": 20,
            "cost_proxy": 0.2,
        }
        event.update(overrides)
        return event

    @classmethod
    def linked_pre(cls, dispatch_id, task_id, index=1, **overrides):
        event = cls.pre(dispatch_id, task_id, index=index)
        event.update(
            {
                "schema_version": "0.2.0",
                "dispatch_id": dispatch_id,
                "policy_id": "adaptive-delegation-luna-first-v0.2",
                "policy_fingerprint": "a" * 64,
                "workspace": "/workspace/project",
                "main_session_id": "session-123",
                "main_model": "gpt-5.6-sol",
                "main_reasoning_effort": "ultra",
                "surface_identity": "typed-external-worker",
                "surface_schema_fingerprint": "b" * 64,
            }
        )
        event.update(overrides)
        return event

    @classmethod
    def linked_post(cls, dispatch_id, task_id, index=1, **overrides):
        event = cls.post(dispatch_id, task_id, index=index)
        event.update(
            {
                "schema_version": "0.2.0",
                "dispatch_id": dispatch_id,
                "policy_id": "adaptive-delegation-luna-first-v0.2",
                "policy_fingerprint": "a" * 64,
                "workspace": "/workspace/project",
                "main_session_id": "session-123",
                "main_model": "gpt-5.6-sol",
                "main_reasoning_effort": "ultra",
                "surface_identity": "typed-external-worker",
                "surface_schema_fingerprint": "b" * 64,
                "execution_completed": True,
                "oracle_verdict": "pass",
                "integration_accepted": True,
            }
        )
        event.update(overrides)
        return event

    def record(self, name, event):
        event_file = self.write_event(name, event)
        result = self.run_cli(
            "record",
            "--event-file",
            event_file,
            "--ledger",
            self.ledger,
            "--review-dir",
            self.review_dir,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    @staticmethod
    def pre_detail():
        return {
            "boundedness": "bounded",
            "context_pressure": "medium",
            "constraint_count": 6,
            "task_shape_signals": [
                "implementation",
                "multi_file",
                "verification",
            ],
            "expected_oracle_types": [
                "unit_test",
                "schema_validation",
                "compile_check",
            ],
            "cheaper_route_not_chosen_because": [
                "constraint_density",
                "task_complexity",
            ],
        }

    @staticmethod
    def post_detail():
        return {
            "observable_result_signals": [
                "accepted_by_oracle",
                "tests_passed",
                "constraints_met",
            ],
            "evidence_references": [
                "/tmp/model-routing/reviews/review.json",
                "receipt-adaptive-route-1",
            ],
            "route_assessment": "correct",
            "next_action": "retain_route",
            "token_observation": "exact",
            "elapsed_observation": "exact",
        }

    def test_records_pairs_and_reviews_metrics(self):
        self.record("one-pre.json", self.pre("a1", "task-one"))
        self.record(
            "one-post.json",
            self.post("a1", "task-one", effort_escalations=1),
        )
        self.record(
            "two-pre.json",
            self.pre(
                "a2", "task-two", model="gpt-5.6-sol",
                task_class="clear_implementation_or_transformation",
            ),
        )
        self.record(
            "two-post.json",
            self.post("a2", "task-two", final_model="gpt-5.6-sol", final_model_tier="frontier-tier", final_reasoning_effort="ultra", cost_proxy=3.0),
        )
        self.record(
            "three-pre.json",
            self.pre("a3", "task-three"),
        )
        self.record(
            "three-post.json",
            self.post(
                "a3", "task-three", model_escalations=1,
                final_model="gpt-5.6-sol", final_model_tier="frontier-tier",
                final_reasoning_effort="ultra", cost_proxy=2.0,
            ),
        )
        result = self.run_cli(
            "review", "--ledger", self.ledger, "--review-dir", self.review_dir
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        review_path = Path(result.stdout.strip())
        self.assertTrue(review_path.is_file())
        self.assertEqual(stat.S_IMODE(review_path.stat().st_mode), 0o600)
        self.assertRegex(review_path.name, r"^review-\d{8}T\d{6}\.\d{6}Z\.json$")
        review = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertEqual(review["attempts"]["paired"], 3)
        self.assertEqual(review["tasks"]["accepted"], 3)
        self.assertEqual(review["metrics"]["first_pass_acceptance_rate"], 1.0)
        self.assertAlmostEqual(
            review["metrics"]["effort_escalation_rate"], 1 / 3, places=6
        )
        self.assertAlmostEqual(
            review["metrics"]["model_escalation_rate"], 1 / 3, places=6
        )
        self.assertAlmostEqual(
            review["metrics"]["sol_rescue_rate"], 1 / 3, places=6
        )
        self.assertEqual(review["metric_counts"]["avoidable_premium_calls"], 1)
        self.assertEqual(review["metric_counts"]["false_cheap_routes"], 1)
        self.assertEqual(stat.S_IMODE(self.ledger.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.review_dir.stat().st_mode), 0o700)

    def test_duplicate_and_post_first_are_rejected(self):
        post = self.write_event("post.json", self.post("x", "task"))
        result = self.run_cli("record", "--event-file", post, "--ledger", self.ledger)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot precede", result.stderr)

        pre = self.write_event("pre.json", self.pre("x", "task"))
        self.record("pre-again.json", self.pre("x", "task"))
        result = self.run_cli("record", "--event-file", pre, "--ledger", self.ledger)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate", result.stderr)

    def test_sensitive_unknown_and_symlink_event_inputs_are_rejected(self):
        event = self.pre("safe", "task")
        event["prompt"] = "must not be stored"
        prompt = self.write_event("prompt.json", event)
        result = self.run_cli("record", "--event-file", prompt, "--ledger", self.ledger)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sensitive field", result.stderr)

        source = self.write_event("source.json", self.pre("link", "task"))
        link = self.root / "link.json"
        os.symlink(source, link)
        result = self.run_cli("record", "--event-file", link, "--ledger", self.ledger)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)

    def test_unpaired_pre_decision_is_reported_without_counting(self):
        self.record("open-pre.json", self.pre("open", "open-task"))
        result = self.run_cli(
            "review", "--ledger", self.ledger, "--review-dir", self.review_dir
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        review = json.loads(Path(result.stdout.strip()).read_text(encoding="utf-8"))
        self.assertEqual(review["attempts"]["paired"], 0)
        self.assertEqual(review["attempts"]["incomplete_pre_decisions"], 1)
        self.assertEqual(review["tasks"]["total"], 0)

    def test_audit_script_uses_package_relative_policy_path(self):
        content = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            'SKILL_ROOT / "config" / "model-routing.defaults.json"', content
        )
        self.assertNotIn(str(SKILL_ROOT), content)

    def test_automatic_review_is_created_for_failure(self):
        self.record("failure-pre.json", self.pre("failure", "failed-task"))
        result = self.record(
            "failure-post.json",
            self.post(
                "failure",
                "failed-task",
                accepted=False,
                failure_class="tool_or_environment",
            ),
        )
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["automatic_review"]["reasons"],
            ["failure"],
        )
        review_path = Path(payload["automatic_review"]["path"])
        self.assertTrue(review_path.is_file())
        self.assertEqual(stat.S_IMODE(review_path.stat().st_mode), 0o600)

    def test_detailed_pair_is_valid_and_review_counts_are_aggregated(self):
        pre = self.pre("detail", "detailed-task")
        pre["pre_decision_detail"] = self.pre_detail()
        post = self.post("detail", "detailed-task")
        post["post_result_detail"] = self.post_detail()

        self.record("detail-pre.json", pre)
        self.record("detail-post.json", post)
        result = self.run_cli(
            "review", "--ledger", self.ledger, "--review-dir", self.review_dir
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        review = json.loads(Path(result.stdout.strip()).read_text(encoding="utf-8"))
        self.assertEqual(review["metric_counts"]["route_assessments"]["correct"], 1)
        self.assertEqual(review["metric_counts"]["route_assessments"]["too-cheap"], 0)
        self.assertEqual(review["metric_counts"]["next_actions"]["retain_route"], 1)
        self.assertEqual(review["metric_counts"]["next_actions"]["raise_model"], 0)
        self.assertEqual(review["tasks"]["elapsed_metric_covered"], 1)
        self.assertEqual(review["tasks"]["token_cost_metric_covered"], 1)

    def test_detail_validation_rejects_bad_enum_and_unsafe_or_oversized_evidence(self):
        bad_enum = self.pre("bad-enum", "task")
        bad_enum["pre_decision_detail"] = self.pre_detail()
        bad_enum["pre_decision_detail"]["boundedness"] = "fluid"
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("bad-enum.json", bad_enum),
            "--ledger",
            self.ledger,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported value", result.stderr)

        for index, reference in enumerate(
            (
                "https://user@example.com/result?token=secret",
                "x" * 257,
                "receipt\ninjected",
            ),
            start=1,
        ):
            post = self.post(f"bad-ref-{index}", f"task-{index}")
            post["post_result_detail"] = self.post_detail()
            post["post_result_detail"]["evidence_references"] = [reference]
            pre = self.pre(f"bad-ref-{index}", f"task-{index}")
            self.record(f"bad-ref-{index}-pre.json", pre)
            result = self.run_cli(
                "record",
                "--event-file",
                self.write_event(f"bad-ref-{index}-post.json", post),
                "--ledger",
                self.ledger,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe or oversized reference", result.stderr)

    def test_legacy_0_1_0_pair_without_detail_remains_valid(self):
        self.record("legacy-pre.json", self.pre("legacy", "legacy-task"))
        result = self.record(
            "legacy-post.json", self.post("legacy", "legacy-task")
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["recorded"]["accepted"])
        self.assertNotIn("pre_decision_detail", payload["recorded"])
        self.assertNotIn("post_result_detail", payload["recorded"])

    def test_unavailable_measurements_are_excluded_from_metric_coverage(self):
        pre = self.pre("unmeasured", "unmeasured-task")
        post = self.post(
            "unmeasured",
            "unmeasured-task",
            weighted_tokens=0,
            cost_proxy=0,
            elapsed_ms=0,
        )
        post["post_result_detail"] = self.post_detail()
        post["post_result_detail"]["token_observation"] = "unavailable"
        post["post_result_detail"]["elapsed_observation"] = "unavailable"
        self.record("unmeasured-pre.json", pre)
        self.record("unmeasured-post.json", post)

        result = self.run_cli(
            "review", "--ledger", self.ledger, "--review-dir", self.review_dir
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        review = json.loads(Path(result.stdout.strip()).read_text(encoding="utf-8"))
        self.assertEqual(review["tasks"]["accepted"], 1)
        self.assertEqual(review["tasks"]["elapsed_metric_covered"], 0)
        self.assertEqual(review["tasks"]["token_cost_metric_covered"], 0)
        self.assertEqual(review["metrics"]["weighted_tokens_per_accepted_task"], 0.0)

    def test_review_counts_actual_route_transitions(self):
        self.record("route-1-pre.json", self.pre("route-1", "route-task", index=1))
        self.record(
            "route-1-post.json",
            self.post(
                "route-1",
                "route-task",
                index=1,
                accepted=False,
                failure_class="tool_or_environment",
            ),
        )

        self.record("route-2-pre.json", self.pre("route-2", "route-task", index=2))
        self.record(
            "route-2-post.json",
            self.post(
                "route-2",
                "route-task",
                index=2,
                accepted=False,
                failure_class="reasoning_insufficiency",
            ),
        )

        effort_up = self.pre("route-3", "route-task", index=3)
        effort_up["reasoning_effort"] = "max"
        self.record("route-3-pre.json", effort_up)
        self.record(
            "route-3-post.json",
            self.post(
                "route-3",
                "route-task",
                index=3,
                accepted=False,
                failure_class="context_ceiling",
                final_reasoning_effort="max",
            ),
        )

        self.record(
            "route-4-pre.json",
            self.pre("route-4", "route-task", index=4, model="gpt-5.6-terra"),
        )
        self.record(
            "route-4-post.json",
            self.post(
                "route-4",
                "route-task",
                index=4,
                final_model="gpt-5.6-terra",
                final_model_tier="standard-tier",
            ),
        )

        result = self.run_cli(
            "review", "--ledger", self.ledger, "--review-dir", self.review_dir
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        review = json.loads(Path(result.stdout.strip()).read_text(encoding="utf-8"))
        counts = review["metric_counts"]
        self.assertEqual(counts["same_route_retry_count"], 1)
        self.assertEqual(counts["effort_transition_count"], 1)
        self.assertEqual(counts["model_transition_count"], 1)
        self.assertEqual(counts["main_takeover_count"], 0)

    def test_linked_execution_can_complete_without_integration_acceptance(self):
        dispatch_id = "linked-not-integrated"
        self.record(
            "linked-pre.json",
            self.linked_pre(dispatch_id, "linked-task"),
        )
        result = self.record(
            "linked-post.json",
            self.linked_post(
                dispatch_id,
                "linked-task",
                accepted=False,
                failure_class="none",
                execution_completed=True,
                oracle_verdict="pass",
                integration_accepted=False,
            ),
        )
        payload = json.loads(result.stdout)
        self.assertFalse(payload["recorded"]["accepted"])
        self.assertTrue(payload["recorded"]["execution_completed"])

    def test_linked_acceptance_and_pair_context_are_fail_closed(self):
        mismatch = self.linked_post(
            "acceptance-mismatch",
            "linked-task",
            accepted=True,
            integration_accepted=False,
        )
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("acceptance-mismatch.json", mismatch),
            "--ledger",
            self.ledger,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("accepted must equal integration_accepted", result.stderr)

        dispatch_id = "context-mismatch"
        self.record(
            "context-pre.json", self.linked_pre(dispatch_id, "linked-task")
        )
        post = self.linked_post(dispatch_id, "linked-task")
        post["policy_fingerprint"] = "c" * 64
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("context-post.json", post),
            "--ledger",
            self.ledger,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("policy_fingerprint", result.stderr)

    def test_public_record_event_is_idempotent_only_when_requested(self):
        event = self.linked_pre("idempotent", "linked-task")
        first = audit.record_event(
            event,
            self.ledger,
            self.review_dir,
            auto_review=False,
            idempotent=True,
        )
        second = audit.record_event(
            event,
            self.ledger,
            self.review_dir,
            auto_review=False,
            idempotent=True,
        )
        self.assertFalse(first["idempotent_duplicate"])
        self.assertTrue(second["idempotent_duplicate"])
        self.assertEqual(len(self.ledger.read_text().splitlines()), 1)

        conflict = dict(event)
        conflict["workspace"] = "/workspace/other"
        with self.assertRaises(audit.AuditError):
            audit.record_event(
                conflict,
                self.ledger,
                self.review_dir,
                auto_review=False,
                idempotent=True,
            )

    def test_review_reports_linked_coverage_and_grouping(self):
        self.record("linked-one-pre.json", self.linked_pre("linked-one", "task-one"))
        self.record("linked-one-post.json", self.linked_post("linked-one", "task-one"))
        self.record(
            "linked-open-pre.json", self.linked_pre("linked-open", "task-open")
        )
        result = self.run_cli(
            "review", "--ledger", self.ledger, "--review-dir", self.review_dir
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        review = json.loads(Path(result.stdout.strip()).read_text(encoding="utf-8"))
        linked = review["linked_audit"]
        self.assertEqual(linked["paired"], 1)
        self.assertEqual(linked["paired_coverage_rate"], 1.0)
        self.assertEqual(linked["incomplete_pre_decisions_excluded"], 1)
        self.assertEqual(len(linked["groups"]), 1)
        group = linked["groups"][0]
        self.assertEqual(group["main_model"], "gpt-5.6-sol")
        self.assertEqual(group["main_reasoning_effort"], "ultra")
        self.assertEqual(group["policy_id"], "adaptive-delegation-luna-first-v0.2")
        self.assertEqual(group["surface_identity"], "typed-external-worker")
        self.assertEqual(group["paired_attempts"], 1)

    def test_policy_gate_is_a_valid_linked_failure_class(self):
        dispatch_id = "policy-gate"
        self.record("gate-pre.json", self.linked_pre(dispatch_id, "gate-task"))
        result = self.record(
            "gate-post.json",
            self.linked_post(
                dispatch_id,
                "gate-task",
                accepted=False,
                failure_class="policy_gate",
                execution_completed=False,
                oracle_verdict="not_run",
                integration_accepted=False,
            ),
        )
        payload = json.loads(result.stdout)
        self.assertIn("failure", payload["automatic_review"]["reasons"])


if __name__ == "__main__":
    unittest.main()
