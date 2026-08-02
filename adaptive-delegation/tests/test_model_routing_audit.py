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
import dispatch_policy as contract  # noqa: E402


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

    @classmethod
    def current_pre(cls, dispatch_id, task_id, index=1, route_id="luna_high", **overrides):
        policy = json.loads((SKILL_ROOT / "config" / "model-routing.defaults.json").read_text())
        route = policy["route_bindings"][route_id]
        event = cls.linked_pre(dispatch_id, task_id, index=index)
        event.update(
            {
                "schema_version": "0.3.0",
                "objective_lock_version": audit.CURRENT_OBJECTIVE_LOCK_VERSION,
                "objective_lock_digest": "c" * 64,
                "policy_id": policy["policy_id"],
                "policy_fingerprint": contract.canonical_policy_fingerprint(policy),
                "model": route["model"],
                "model_tier": route["model_tier"],
                "reasoning_effort": route["reasoning_effort"],
                "route_id": route_id,
                "role": route["role"],
                "planned_effort_escalations": 0,
                "planned_model_escalations": 0,
                "rationale": {
                    "task_class": "clear_implementation_or_transformation",
                    "oracle_strength": "strong",
                    "risk_class": "medium",
                    "prior_failure_class": None if index == 1 else "reasoning_insufficiency",
                    "prior_attempts": index - 1,
                    "selection_basis": "policy_default" if index == 1 else "failure_action",
                },
            }
        )
        event.update(overrides)
        return event

    @classmethod
    def current_post(cls, dispatch_id, task_id, index=1, **overrides):
        pre = cls.current_pre(dispatch_id, task_id, index=index, **overrides)
        event = cls.linked_post(dispatch_id, task_id, index=index)
        event.update(
            {
                "schema_version": pre["schema_version"],
                "objective_lock_version": pre["objective_lock_version"],
                "objective_lock_digest": pre["objective_lock_digest"],
                "policy_id": pre["policy_id"],
                "policy_fingerprint": pre["policy_fingerprint"],
                "final_model": pre["model"],
                "final_model_tier": pre["model_tier"],
                "final_reasoning_effort": pre["reasoning_effort"],
                "final_route_id": pre["route_id"],
                "final_role": pre["role"],
                "effort_escalations": pre["planned_effort_escalations"],
                "model_escalations": pre["planned_model_escalations"],
                "accepted": False,
                "failure_class": "reasoning_insufficiency",
                "oracle_verdict": "fail",
                "integration_accepted": False,
                "post_result_detail": {
                    "observable_result_signals": ["tests_failed"],
                    "evidence_references": [f"receipt-{dispatch_id}"],
                    "route_assessment": "inconclusive",
                    "next_action": "raise_effort",
                },
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

    def test_objective_lock_digest_must_match_linked_pair_and_transition(self):
        pre = self.current_pre("lock-first", "objective-lock-history")
        post = self.current_post("lock-first", "objective-lock-history")
        post["post_result_detail"]["next_action"] = "raise_effort"
        self.record("lock-first-pre.json", pre)
        self.record("lock-first-post.json", post)

        retry = self.current_pre(
            "lock-second", "objective-lock-history", index=2, route_id="luna_xhigh"
        )
        retry["planned_effort_escalations"] = 1
        retry["objective_lock_digest"] = "d" * 64
        event_file = self.write_event("lock-second-pre.json", retry)
        result = self.run_cli(
            "record", "--event-file", event_file, "--ledger", self.ledger,
            "--review-dir", self.review_dir,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("objective lock digest", result.stderr)

        mismatch_post = self.current_post("lock-pair", "objective-lock-pair")
        mismatch_pre = self.current_pre("lock-pair", "objective-lock-pair")
        mismatch_post["objective_lock_digest"] = "d" * 64
        with self.assertRaisesRegex(audit.AuditError, "objective_lock_digest"):
            audit._check_pair(mismatch_pre, mismatch_post)

        version_mismatch_post = self.current_post(
            "lock-version-pair", "objective-lock-version-pair"
        )
        version_mismatch_pre = self.current_pre(
            "lock-version-pair", "objective-lock-version-pair"
        )
        version_mismatch_post["objective_lock_version"] = "1"
        with self.assertRaisesRegex(audit.AuditError, "objective_lock_version"):
            audit._check_pair(version_mismatch_pre, version_mismatch_post)

    def test_objective_lock_v1_records_remain_readable_but_cannot_continue_as_v3(self):
        legacy_pre = self.current_pre(
            "lock-v1-first", "objective-lock-version-history",
            objective_lock_version="1",
        )
        legacy_post = self.current_post(
            "lock-v1-first", "objective-lock-version-history",
            objective_lock_version="1",
        )
        legacy_post["post_result_detail"]["next_action"] = "raise_effort"
        self.record("lock-v1-first-pre.json", legacy_pre)
        self.record("lock-v1-first-post.json", legacy_post)

        next_attempt = self.current_pre(
            "lock-v3-second",
            "objective-lock-version-history",
            index=2,
            route_id="luna_xhigh",
        )
        next_attempt["planned_effort_escalations"] = 1
        with self.assertRaisesRegex(
            audit.AuditError,
            "objective lock version|objective lock digest",
        ):
            audit.record_event(
                next_attempt, self.ledger, self.review_dir, auto_review=False
            )

        unsupported = self.current_pre(
            "lock-v3", "objective-lock-unsupported",
            objective_lock_version="4",
        )
        with self.assertRaisesRegex(audit.AuditError, "unsupported objective_lock_version"):
            audit.validate_event(unsupported)

    def test_linked_schema_cannot_upgrade_or_downgrade_within_task_history(self):
        for direction in ("upgrade", "downgrade"):
            with self.subTest(direction=direction):
                ledger = self.root / f"{direction}.jsonl"
                task_id = f"schema-{direction}"
                if direction == "upgrade":
                    first = self.linked_pre(f"{direction}-first", task_id)
                    first_post = self.linked_post(f"{direction}-first", task_id)
                    second = self.current_pre(
                        f"{direction}-second", task_id, index=2
                    )
                else:
                    first = self.current_pre(f"{direction}-first", task_id)
                    first_post = self.current_post(f"{direction}-first", task_id)
                    second = self.linked_pre(
                        f"{direction}-second", task_id, index=2
                    )
                first_post["accepted"] = False
                first_post["integration_accepted"] = False
                first_post["oracle_verdict"] = "fail"
                first_post["failure_class"] = "reasoning_insufficiency"
                first_post["post_result_detail"] = {
                    "observable_result_signals": ["tests_failed"],
                    "evidence_references": ["schema-transition-evidence"],
                    "route_assessment": "too-cheap",
                    "next_action": "raise_effort",
                }
                audit.record_event(
                    first, ledger, self.review_dir, auto_review=False
                )
                audit.record_event(
                    first_post, ledger, self.review_dir, auto_review=False
                )
                with self.assertRaisesRegex(
                    audit.AuditError, "cannot change schema version|current-policy transition"
                ):
                    audit.record_event(
                        second, ledger, self.review_dir, auto_review=False
                    )

    def test_main_takeover_preserves_objective_lock_digest(self):
        task_id = "objective-lock-main-takeover"
        first = self.current_pre(
            "objective-lock-leaf", task_id, route_id="luna_xhigh"
        )
        first["rationale"].update(
            task_class="bounded_complex_implementation_or_verification",
            oracle_strength="weak",
        )
        first_post = self.current_post("objective-lock-leaf", task_id)
        first_post.update(
            final_model=first["model"],
            final_model_tier=first["model_tier"],
            final_reasoning_effort=first["reasoning_effort"],
            final_route_id=first["route_id"],
            final_role=first["role"],
            failure_class="weak_oracle",
            post_result_detail={
                "observable_result_signals": ["evidence_inconclusive"],
                "evidence_references": ["objective-lock-takeover-evidence"],
                "route_assessment": "inconclusive",
                "next_action": "main_takeover",
            },
        )
        self.record("objective-lock-leaf-pre.json", first)
        self.record("objective-lock-leaf-post.json", first_post)

        takeover = self.current_pre(
            "objective-lock-main",
            task_id,
            index=2,
            route_id="main_takeover_sol_ultra",
        )
        takeover["planned_model_escalations"] = 1
        takeover["objective_lock_digest"] = "d" * 64
        takeover["rationale"].update(
            task_class="bounded_complex_implementation_or_verification",
            oracle_strength="weak",
            prior_failure_class="weak_oracle",
        )
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("objective-lock-main-pre.json", takeover),
            "--ledger",
            self.ledger,
            "--review-dir",
            self.review_dir,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("objective lock digest", result.stderr)

    def test_event_types_reject_cross_type_fields(self):
        cases = []
        for field, value in (
            ("accepted", "garbage"),
            ("final_model", "gpt-9-fake"),
            ("elapsed_ms", -5),
        ):
            event = self.pre("pre-cross-type", "task-pre-cross-type")
            event[field] = value
            cases.append((f"pre:{field}", event))
        for field, value in (
            ("model", "gpt-9-fake"),
            ("rationale", {"task_class": "bogus"}),
        ):
            event = self.post("post-cross-type", "task-post-cross-type")
            event[field] = value
            cases.append((f"post:{field}", event))

        for label, event in cases:
            with self.subTest(label=label):
                with self.assertRaises(audit.AuditError):
                    audit.validate_event(event)

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
        self.assertIsNone(review["metrics"]["cost_proxy_per_accepted_task"])
        self.assertTrue(review["metrics"]["tokens_and_calls_by_model_effort"])
        self.assertTrue(review["metrics"]["policy_segments"])
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

    def test_default_paths_follow_codex_home_but_policy_stays_package_relative(self):
        configured_home = self.root / "custom-codex"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.path.insert(0, 'scripts'); import model_routing_audit as a; print(a.DEFAULT_LEDGER); print(a.DEFAULT_REVIEW_DIR); print(a.DEFAULT_CONFIG)",
            ],
            env={**os.environ, "CODEX_HOME": str(configured_home)},
            cwd=SKILL_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        paths = result.stdout.splitlines()
        self.assertEqual(paths[0], str(configured_home / "state" / "model-routing" / "attempts.jsonl"))
        self.assertEqual(paths[1], str(configured_home / "state" / "model-routing" / "reviews"))
        self.assertEqual(paths[2], str(SKILL_ROOT / "config" / "model-routing.defaults.json"))

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

    def test_legacy_0_2_0_rejects_objective_lock_wire_fields(self):
        for fields in (
            {"objective_lock_version": "1"},
            {"objective_lock_digest": "c" * 64},
            {
                "objective_lock_version": "1",
                "objective_lock_digest": "c" * 64,
            },
        ):
            with self.subTest(fields=sorted(fields)):
                event = self.linked_pre("legacy-lock-shape", "legacy-lock-task")
                event.update(fields)
                with self.assertRaisesRegex(
                    audit.AuditError, "objective lock fields require schema 0.3.0"
                ):
                    audit.validate_event(event)

    def test_legacy_0_2_0_task_classes_remain_readable(self):
        for task_class in audit.LEGACY_LINKED_TASK_CLASSES:
            with self.subTest(task_class=task_class):
                event = self.linked_pre(
                    f"legacy-task-{task_class}",
                    f"legacy-task-{task_class}",
                )
                event["rationale"]["task_class"] = task_class
                audit.validate_event(event)

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

    def test_current_policy_route_history_is_table_driven_and_fail_closed(self):
        self.record("strict-pre.json", self.current_pre("strict-1", "strict-task"))
        result = self.record(
            "strict-post.json",
            self.current_post("strict-1", "strict-task"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        illegal_first = self.current_pre(
            "strict-bad-first",
            "strict-bad-first-task",
            route_id="terra_medium",
        )
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("strict-bad-first.json", illegal_first),
            "--ledger",
            self.ledger,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FIRST_ROUTE_INVALID", result.stderr)

        bad_failure = self.current_post(
            "strict-bad-failure",
            "strict-bad-failure-task",
            failure_class="tool_or_environment",
        )
        bad_failure["post_result_detail"]["next_action"] = "environment_retry"
        self.record("strict-bad-failure-pre.json", self.current_pre("strict-bad-failure", "strict-bad-failure-task"))
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("strict-bad-failure-post.json", bad_failure),
            "--ledger",
            self.ledger,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("observable matching signal", result.stderr)

        skipped = self.current_pre(
            "strict-skip-2",
            "strict-task",
            index=2,
            route_id="luna_max",
        )
        skipped["planned_effort_escalations"] = 1
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("strict-skip.json", skipped),
            "--ledger",
            self.ledger,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("skipped", result.stderr)

    def test_current_policy_rejects_orphan_nondefault_attempt(self):
        orphan = self.current_pre(
            "orphan-2",
            "orphan-task",
            index=2,
            route_id="luna_xhigh",
        )
        orphan["planned_effort_escalations"] = 1
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("orphan-2.json", orphan),
            "--ledger",
            self.ledger,
            "--review-dir",
            self.review_dir,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must begin at attempt_index 1", result.stderr)
        self.assertEqual(self.ledger.read_text(encoding="utf-8"), "")

    def test_pending_current_attempt_blocks_interleaved_duplicate_index(self):
        task_id = "pending-current-task"
        self.record(
            "pending-current-first.json",
            self.current_pre("pending-current-first", task_id),
        )

        duplicate = self.current_pre("pending-current-duplicate", task_id)
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("pending-current-duplicate.json", duplicate),
            "--ledger",
            self.ledger,
            "--review-dir",
            self.review_dir,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("task has a pending attempt", result.stderr)
        self.assertEqual(len(self.ledger.read_text(encoding="utf-8").splitlines()), 1)

    def test_weak_oracle_can_take_over_directly_but_raise_model_cannot(self):
        task_id = "weak-oracle-direct-main"
        first = self.current_pre(
            "weak-oracle-first",
            task_id,
            route_id="luna_xhigh",
        )
        first["rationale"].update(
            task_class="bounded_complex_implementation_or_verification",
            oracle_strength="weak",
        )
        self.record("weak-oracle-first-pre.json", first)

        failed = self.current_post("weak-oracle-first", task_id)
        failed.update(
            final_model=first["model"],
            final_model_tier=first["model_tier"],
            final_reasoning_effort=first["reasoning_effort"],
            final_route_id=first["route_id"],
            final_role=first["role"],
            failure_class="weak_oracle",
            post_result_detail={
                "observable_result_signals": ["evidence_inconclusive"],
                "evidence_references": ["receipt-weak-oracle-first"],
                "route_assessment": "inconclusive",
                "next_action": "main_takeover",
            },
        )
        self.record("weak-oracle-first-post.json", failed)

        takeover = self.current_pre(
            "weak-oracle-main",
            task_id,
            index=2,
            route_id="main_takeover_sol_ultra",
        )
        takeover["planned_model_escalations"] = 1
        takeover["rationale"].update(
            task_class="bounded_complex_implementation_or_verification",
            oracle_strength="weak",
            prior_failure_class="weak_oracle",
        )
        self.record("weak-oracle-main-pre.json", takeover)

        wrong_task = "raise-model-main-task"
        final_leaf = self.current_pre(
            "raise-model-sol-high",
            wrong_task,
            route_id="sol_high",
        )
        final_leaf["override_reason"] = "Bounded test setup at the final leaf route."
        final_leaf["rationale"].update(
            task_class="bounded_complex_implementation_or_verification",
            oracle_strength="weak",
            selection_basis="human_override",
        )
        self.record("raise-model-sol-high-pre.json", final_leaf)
        final_leaf_post = self.current_post("raise-model-sol-high", wrong_task)
        final_leaf_post.update(
            final_model=final_leaf["model"],
            final_model_tier=final_leaf["model_tier"],
            final_reasoning_effort=final_leaf["reasoning_effort"],
            final_route_id=final_leaf["route_id"],
            final_role=final_leaf["role"],
            failure_class="reasoning_insufficiency",
            post_result_detail={
                "observable_result_signals": ["tests_failed"],
                "evidence_references": ["receipt-raise-model-sol-high"],
                "route_assessment": "inconclusive",
                "next_action": "raise_model",
            },
        )
        self.record("raise-model-sol-high-post.json", final_leaf_post)
        invalid_main = self.current_pre(
            "raise-model-main",
            wrong_task,
            index=2,
            route_id="main_takeover_sol_ultra",
        )
        invalid_main["planned_model_escalations"] = 1
        invalid_main["rationale"].update(
            task_class="bounded_complex_implementation_or_verification",
            oracle_strength="weak",
        )
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("raise-model-main-pre.json", invalid_main),
            "--ledger",
            self.ledger,
            "--review-dir",
            self.review_dir,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("raise_model cannot select", result.stderr)

    def test_main_takeover_rejects_main_repeat_and_non_weak_skip(self):
        main_task = "main-repeat-task"
        main_pre = self.current_pre(
            "main-repeat-first",
            main_task,
            route_id="main_takeover_sol_ultra",
        )
        main_pre["rationale"].update(
            task_class="weak_oracle_ambiguous_high_risk_or_long_contract",
            oracle_strength="weak",
        )
        self.record("main-repeat-first-pre.json", main_pre)
        main_post = self.current_post("main-repeat-first", main_task)
        main_post.update(
            final_model=main_pre["model"],
            final_model_tier=main_pre["model_tier"],
            final_reasoning_effort=main_pre["reasoning_effort"],
            final_route_id=main_pre["route_id"],
            final_role=main_pre["role"],
            failure_class="weak_oracle",
            post_result_detail={
                "observable_result_signals": ["evidence_inconclusive"],
                "evidence_references": ["receipt-main-repeat-first"],
                "route_assessment": "inconclusive",
                "next_action": "main_takeover",
            },
        )
        self.record("main-repeat-first-post.json", main_post)
        repeated_main = self.current_pre(
            "main-repeat-second",
            main_task,
            index=2,
            route_id="main_takeover_sol_ultra",
        )
        repeated_main["rationale"].update(
            task_class="weak_oracle_ambiguous_high_risk_or_long_contract",
            oracle_strength="weak",
            prior_failure_class="weak_oracle",
        )
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("main-repeat-second-pre.json", repeated_main),
            "--ledger",
            self.ledger,
            "--review-dir",
            self.review_dir,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("main authority is already selected", result.stderr)

        skip_task = "non-weak-main-skip"
        leaf = self.current_pre("non-weak-leaf", skip_task)
        self.record("non-weak-leaf-pre.json", leaf)
        leaf_post = self.current_post("non-weak-leaf", skip_task)
        leaf_post.update(
            failure_class="capability_ceiling",
            post_result_detail={
                "observable_result_signals": ["constraints_missed"],
                "evidence_references": ["receipt-non-weak-leaf"],
                "route_assessment": "inconclusive",
                "next_action": "main_takeover",
            },
        )
        self.record("non-weak-leaf-post.json", leaf_post)
        skipped_main = self.current_pre(
            "non-weak-main",
            skip_task,
            index=2,
            route_id="main_takeover_sol_ultra",
        )
        skipped_main["planned_model_escalations"] = 1
        skipped_main["rationale"]["prior_failure_class"] = "capability_ceiling"
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("non-weak-main-pre.json", skipped_main),
            "--ledger",
            self.ledger,
            "--review-dir",
            self.review_dir,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("main_takeover must be adjacent", result.stderr)

    def test_route_less_legacy_history_does_not_crash_retry_accounting(self):
        task_id = "mixed-history-retry"
        legacy_pre = self.pre("mixed-legacy", task_id)
        current_pre = self.current_pre("mixed-current", task_id)
        self.record("mixed-legacy-pre.json", legacy_pre)
        self.record("mixed-current-pre.json", current_pre)
        self.record("mixed-legacy-post.json", self.post("mixed-legacy", task_id))

        current_post = self.current_post("mixed-current", task_id)
        current_post.update(
            accepted=False,
            failure_class="tool_or_environment",
            oracle_verdict="fail",
            integration_accepted=False,
            post_result_detail={
                "observable_result_signals": ["tool_failure"],
                "evidence_references": ["receipt-mixed-current"],
                "route_assessment": "inconclusive",
                "next_action": "environment_retry",
            },
        )
        self.record("mixed-current-post.json", current_post)
        retry = self.current_pre("mixed-current-retry", task_id, index=2)
        retry["rationale"]["prior_failure_class"] = "tool_or_environment"

        result = self.record("mixed-current-retry-pre.json", retry)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_interleaved_legacy_pair_does_not_reset_current_retry_budget(self):
        task_id = "interleaved-retry-budget"

        def retryable_post(dispatch_id, index):
            event = self.current_post(dispatch_id, task_id, index=index)
            event.update(
                accepted=False,
                failure_class="tool_or_environment",
                oracle_verdict="fail",
                integration_accepted=False,
                post_result_detail={
                    "observable_result_signals": ["tool_failure"],
                    "evidence_references": [f"receipt-{dispatch_id}"],
                    "route_assessment": "inconclusive",
                    "next_action": "environment_retry",
                },
            )
            return event

        first = self.current_pre("interleaved-current-1", task_id)
        self.record("interleaved-current-1-pre.json", first)
        self.record(
            "interleaved-current-1-post.json",
            retryable_post("interleaved-current-1", 1),
        )

        legacy_pre = self.pre("interleaved-legacy", task_id)
        self.record("interleaved-legacy-pre.json", legacy_pre)
        second = self.current_pre("interleaved-current-2", task_id, index=2)
        second["rationale"]["prior_failure_class"] = "tool_or_environment"
        self.record("interleaved-current-2-pre.json", second)
        self.record(
            "interleaved-legacy-post.json",
            self.post("interleaved-legacy", task_id),
        )
        self.record(
            "interleaved-current-2-post.json",
            retryable_post("interleaved-current-2", 2),
        )

        third = self.current_pre("interleaved-current-3", task_id, index=3)
        third["rationale"]["prior_failure_class"] = "tool_or_environment"
        result = self.run_cli(
            "record",
            "--event-file",
            self.write_event("interleaved-current-3-pre.json", third),
            "--ledger",
            self.ledger,
            "--review-dir",
            self.review_dir,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("same route retry budget is exhausted", result.stderr)

    def test_same_route_retry_budget_resets_after_route_transition(self):
        task_id = "per-stage-retry-task"

        def post_for(pre, failure_class, next_action, signals):
            event = self.current_post(
                pre["dispatch_id"], task_id, index=pre["attempt_index"]
            )
            event.update(
                {
                    "final_model": pre["model"],
                    "final_model_tier": pre["model_tier"],
                    "final_reasoning_effort": pre["reasoning_effort"],
                    "final_route_id": pre["route_id"],
                    "final_role": pre["role"],
                    "effort_escalations": pre["planned_effort_escalations"],
                    "model_escalations": pre["planned_model_escalations"],
                    "failure_class": failure_class,
                    "post_result_detail": {
                        "observable_result_signals": signals,
                        "evidence_references": [f"receipt-{pre['dispatch_id']}"],
                        "route_assessment": "inconclusive",
                        "next_action": next_action,
                    },
                }
            )
            return event

        first = self.current_pre("stage-1", task_id)
        self.record("stage-1-pre.json", first)
        self.record(
            "stage-1-post.json",
            post_for(
                first,
                "tool_or_environment",
                "environment_retry",
                ["tool_failure"],
            ),
        )

        first_retry = self.current_pre("stage-1-retry", task_id, index=2)
        first_retry["rationale"]["prior_failure_class"] = "tool_or_environment"
        self.record("stage-1-retry-pre.json", first_retry)
        self.record(
            "stage-1-retry-post.json",
            post_for(
                first_retry,
                "reasoning_insufficiency",
                "raise_effort",
                ["tests_failed"],
            ),
        )

        second = self.current_pre(
            "stage-2", task_id, index=3, route_id="luna_xhigh"
        )
        second["planned_effort_escalations"] = 1
        self.record("stage-2-pre.json", second)
        self.record(
            "stage-2-post.json",
            post_for(
                second,
                "tool_or_environment",
                "environment_retry",
                ["tool_failure"],
            ),
        )

        second_retry = self.current_pre(
            "stage-2-retry", task_id, index=4, route_id="luna_xhigh"
        )
        second_retry["planned_effort_escalations"] = 1
        second_retry["rationale"]["prior_failure_class"] = "tool_or_environment"
        result = self.record("stage-2-retry-pre.json", second_retry)
        self.assertEqual(result.returncode, 0, result.stderr)

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
        self.assertEqual(review["attempts"]["analysis_basis"], "historical_only")
        self.assertEqual(review["attempts"]["current_policy_paired"], 0)
        self.assertEqual(review["attempts"]["analysis_basis_paired"], 1)
        self.assertEqual(review["tasks"]["total"], 1)
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

    def test_review_separates_legacy_linked_history_from_current_analysis(self):
        policy = json.loads(
            (SKILL_ROOT / "config" / "model-routing.defaults.json").read_text()
        )
        fingerprint = contract.canonical_policy_fingerprint(policy)
        legacy_pre = self.linked_pre(
            "legacy-linked-review",
            "legacy-linked-review-task",
            policy_fingerprint=fingerprint,
        )
        legacy_post = self.linked_post(
            "legacy-linked-review",
            "legacy-linked-review-task",
            policy_fingerprint=fingerprint,
        )
        current_pre = self.current_pre(
            "current-linked-review", "current-linked-review-task"
        )
        current_post = self.current_post(
            "current-linked-review",
            "current-linked-review-task",
            accepted=True,
            failure_class="none",
            oracle_verdict="pass",
            integration_accepted=True,
        )
        current_post["post_result_detail"] = {
            "observable_result_signals": ["tests_passed"],
            "evidence_references": ["current-review-receipt"],
            "route_assessment": "correct",
            "next_action": "retain_route",
        }
        for name, event in (
            ("legacy-review-pre.json", legacy_pre),
            ("legacy-review-post.json", legacy_post),
            ("current-review-pre.json", current_pre),
            ("current-review-post.json", current_post),
        ):
            self.record(name, event)

        result = self.run_cli(
            "review", "--ledger", self.ledger, "--review-dir", self.review_dir
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        review = json.loads(Path(result.stdout.strip()).read_text(encoding="utf-8"))
        self.assertEqual(review["attempts"]["analysis_basis"], "current_0.3")
        self.assertEqual(review["attempts"]["current_policy_paired"], 1)
        self.assertEqual(review["attempts"]["analysis_basis_paired"], 1)
        self.assertEqual(review["tasks"]["total"], 1)
        self.assertEqual(
            {group["schema_version"] for group in review["linked_audit"]["groups"]},
            {"0.2.0", "0.3.0"},
        )

    def test_review_keeps_prior_policy_0_3_history_readable(self):
        prior_pre = self.current_pre(
            "prior-policy-review",
            "prior-policy-review-task",
            policy_id="adaptive-delegation-prior-policy",
            policy_fingerprint="d" * 64,
        )
        prior_post = self.current_post(
            "prior-policy-review",
            "prior-policy-review-task",
            policy_id="adaptive-delegation-prior-policy",
            policy_fingerprint="d" * 64,
            accepted=True,
            failure_class="none",
            oracle_verdict="pass",
            integration_accepted=True,
        )
        prior_post["post_result_detail"] = {
            "observable_result_signals": ["tests_passed"],
            "evidence_references": ["prior-policy-receipt"],
            "route_assessment": "correct",
            "next_action": "retain_route",
        }
        self.record("prior-policy-pre.json", prior_pre)
        self.record("prior-policy-post.json", prior_post)

        result = self.run_cli(
            "review", "--ledger", self.ledger, "--review-dir", self.review_dir
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        review = json.loads(Path(result.stdout.strip()).read_text(encoding="utf-8"))
        self.assertEqual(review["attempts"]["analysis_basis"], "historical_only")
        self.assertEqual(review["attempts"]["current_policy_paired"], 0)
        self.assertEqual(review["attempts"]["analysis_basis_paired"], 1)
        self.assertEqual(review["tasks"]["total"], 1)
        self.assertEqual(review["linked_audit"]["groups"][0]["schema_version"], "0.3.0")

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

    def test_issue_report_selects_latest_completed_task_and_specific_task(self):
        old_pre = self.pre("old-attempt", "old-task")
        old_pre["timestamp"] = "2026-07-30T00:00:00Z"
        old_post = self.post("old-attempt", "old-task")
        old_post["timestamp"] = "2026-07-30T00:01:00Z"
        self.record("old-pre.json", old_pre)
        self.record("old-post.json", old_post)

        new_pre = self.pre("new-attempt", "new-task", model="gpt-5.6-terra")
        new_pre["timestamp"] = "2026-07-31T00:00:00Z"
        new_post = self.post(
            "new-attempt",
            "new-task",
            final_model="gpt-5.6-terra",
            final_model_tier="standard-tier",
        )
        new_post["timestamp"] = "2026-07-31T00:01:00Z"
        self.record("new-pre.json", new_pre)
        self.record("new-post.json", new_post)

        latest = self.run_cli("issue-report", "--ledger", self.ledger)
        repeat = self.run_cli("issue-report", "--ledger", self.ledger)
        self.assertEqual(latest.returncode, 0, latest.stderr)
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertEqual(latest.stdout, repeat.stdout)
        self.assertIn("latest completed task", latest.stdout)
        self.assertIn("gpt-5.6-terra", latest.stdout)
        self.assertNotIn("old-task", latest.stdout)
        self.assertNotIn("new-task", latest.stdout)

        specific = self.run_cli(
            "issue-report", "--ledger", self.ledger, "--task-id", "old-task"
        )
        self.assertEqual(specific.returncode, 0, specific.stderr)
        self.assertIn("requested task", specific.stdout)
        self.assertIn("gpt-5.6-luna", specific.stdout)
        self.assertNotIn("gpt-5.6-terra", specific.stdout)

    def test_issue_report_omits_private_fields_and_does_not_mutate_ledger(self):
        dispatch_id = "private-dispatch"
        private_workspace = "https://user:secret@example.com/private?token=secret#frag"
        private_session = "session-private-123"
        private_receipt = "/private/example/review.json"
        pre = self.linked_pre(
            dispatch_id,
            "private-task",
            workspace=private_workspace,
            main_session_id=private_session,
        )
        post = self.linked_post(
            dispatch_id,
            "private-task",
            workspace=private_workspace,
            main_session_id=private_session,
        )
        post["post_result_detail"] = self.post_detail()
        post["post_result_detail"]["evidence_references"] = [private_receipt]
        self.record("private-pre.json", pre)
        self.record("private-post.json", post)
        before = self.ledger.read_bytes()

        result = self.run_cli("issue-report", "--ledger", self.ledger)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.ledger.read_bytes())
        for private_value in (private_workspace, private_session, private_receipt):
            self.assertNotIn(private_value, result.stdout)
        self.assertNotIn("prompt", result.stdout.lower())
        self.assertIn("allowlisted routing outcomes", result.stdout)

    def test_issue_report_fails_closed_for_incomplete_or_sensitive_ledger(self):
        self.record("open-pre.json", self.pre("open", "open-task"))
        before = self.ledger.read_bytes()
        incomplete = self.run_cli("issue-report", "--ledger", self.ledger)
        self.assertNotEqual(incomplete.returncode, 0)
        self.assertIn("could not be generated", incomplete.stderr)
        self.assertEqual(before, self.ledger.read_bytes())

        sensitive_ledger = self.root / "sensitive" / "attempts.jsonl"
        sensitive_ledger.parent.mkdir(parents=True)
        sensitive = self.pre("sensitive", "sensitive-task")
        sensitive["prompt"] = "private prompt payload"
        sensitive_ledger.write_text(json.dumps(sensitive) + "\n", encoding="utf-8")
        os.chmod(sensitive_ledger, 0o600)
        sensitive_before = sensitive_ledger.read_bytes()
        rejected = self.run_cli("issue-report", "--ledger", sensitive_ledger)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn("private prompt payload", rejected.stderr)
        self.assertEqual(sensitive_before, sensitive_ledger.read_bytes())

        attacker_key = "BEGIN_FAKE_TRANSCRIPT https://secret.example/?token=private END"
        attacker_ledger = self.root / "attacker-key" / "attempts.jsonl"
        attacker_ledger.parent.mkdir(parents=True)
        attacker_ledger.write_text(
            json.dumps({attacker_key: 1}) + "\n", encoding="utf-8"
        )
        os.chmod(attacker_ledger, 0o600)
        rejected = self.run_cli("issue-report", "--ledger", attacker_ledger)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn(attacker_key, rejected.stderr)
        self.assertNotIn("secret.example", rejected.stderr)

        private_attempt = "MARKLEGATT1.sk-live-4242"
        duplicate_ledger = self.root / "duplicate" / "attempts.jsonl"
        duplicate_ledger.parent.mkdir(parents=True)
        duplicated = json.dumps(
            self.pre(private_attempt, "private-duplicate-task"), sort_keys=True
        )
        duplicate_ledger.write_text(duplicated + "\n" + duplicated + "\n", encoding="utf-8")
        os.chmod(duplicate_ledger, 0o600)
        rejected = self.run_cli("issue-report", "--ledger", duplicate_ledger)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn(private_attempt, rejected.stderr)

        missing_parent = self.root / "PRIVATE_LEDGER_PATH_MARKER" / "nested"
        missing_ledger = missing_parent / "attempts.jsonl"
        self.assertFalse(missing_parent.exists())
        rejected = self.run_cli("issue-report", "--ledger", missing_ledger)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn("PRIVATE_LEDGER_PATH_MARKER", rejected.stderr)
        self.assertFalse(missing_parent.exists())


if __name__ == "__main__":
    unittest.main()
