from __future__ import annotations

import json
import os
import shlex
import stat
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"

import sys

sys.path.insert(0, str(SCRIPTS))

import controller_gate as gate  # noqa: E402


class ControllerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.runtime_home = Path(self.temporary.name) / ".codex"
        self.cwd = Path(self.temporary.name) / "workspace"
        self.cwd.mkdir()
        self.session_id = "11111111-1111-4111-8111-111111111111"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prompt_payload(self, prompt: str) -> dict[str, object]:
        return {
            "hook_event_name": "UserPromptSubmit",
            "session_id": self.session_id,
            "cwd": str(self.cwd),
            "prompt": prompt,
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
        }

    def tool_payload(
        self,
        tool_name: str,
        tool_input: dict[str, object] | None = None,
        **overrides: object,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "hook_event_name": "PreToolUse",
            "session_id": self.session_id,
            "cwd": str(self.cwd),
            "tool_name": tool_name,
            "tool_input": tool_input or {},
        }
        payload.update(overrides)
        return payload

    def activate(self) -> Path:
        output = gate.handle_hook(
            self.prompt_payload("$adaptive-delegation implement the bounded change"),
            runtime_home=self.runtime_home,
        )
        self.assertEqual(output, {})
        states = list(
            (self.runtime_home / "state" / "adaptive-delegation" / "controller").glob(
                "state-*.json"
            )
        )
        self.assertEqual(len(states), 1)
        return states[0]

    def test_explicit_invocation_creates_private_controller_state_without_prompt(self) -> None:
        state_path = self.activate()

        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "explicit_active")
        self.assertEqual(state["session_id"], self.session_id)
        self.assertEqual(state["workspace"], str(self.cwd.resolve()))
        self.assertNotIn("prompt", state)
        self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(state_path.parent.stat().st_mode), 0o700)

    def test_nonexplicit_prompt_does_not_create_state(self) -> None:
        output = gate.handle_hook(
            self.prompt_payload("Please explain adaptive delegation."),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(output, {})
        self.assertFalse((self.runtime_home / "state").exists())

    def test_explicit_invocation_rejects_main_below_sol_high(self) -> None:
        payload = self.prompt_payload("$adaptive-delegation implement it")
        payload["model"] = "gpt-5.6-luna"
        payload["reasoning_effort"] = "max"

        output = gate.handle_hook(payload, runtime_home=self.runtime_home)

        self.assertIn("Adaptive Delegation blocked", output["systemMessage"])
        self.assertFalse((self.runtime_home / "state").exists())

    def test_documented_prompt_shape_waits_for_bounded_main_declaration(self) -> None:
        payload = self.prompt_payload("$adaptive-delegation implement it")
        payload.pop("model")
        payload.pop("reasoning_effort")

        output = gate.handle_hook(payload, runtime_home=self.runtime_home)

        self.assertIn("declare-main", output["systemMessage"])
        self.assertIn(self.session_id, output["systemMessage"])
        self.assertIn(str(self.cwd), output["systemMessage"])
        state_path = next(
            (self.runtime_home / "state" / "adaptive-delegation" / "controller").glob(
                "state-*.json"
            )
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "awaiting_main_declaration")
        self.assertNotIn("main_model", state)

        controller = shlex.quote(str(Path(gate.__file__).resolve()))
        command = (
            f"{shlex.quote(sys.executable)} {controller} declare-main "
            f"--session-id {self.session_id} --workspace {shlex.quote(str(self.cwd))} "
            "--model gpt-5.6-sol --reasoning-effort high"
        )
        allowed = gate.handle_hook(
            self.tool_payload("Bash", {"command": command}),
            runtime_home=self.runtime_home,
        )
        self.assertEqual(allowed, {})

        declared = gate.record_main_declaration(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            model="gpt-5.6-sol",
            reasoning_effort="high",
        )
        self.assertEqual(declared["phase"], "explicit_active")

    def test_codex_prompt_shape_without_effort_waits_and_injects_declaration(self) -> None:
        payload = self.prompt_payload("$adaptive-delegation implement it")
        payload.pop("reasoning_effort")

        output = gate.handle_hook(payload, runtime_home=self.runtime_home)

        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(
            output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
        )
        expected_command = shlex.join(
            [
                sys.executable,
                str(Path(gate.__file__).resolve()),
                "declare-main",
                "--session-id",
                self.session_id,
                "--workspace",
                str(self.cwd.resolve()),
                "--model",
                "gpt-5.6-sol",
                "--reasoning-effort",
                "<high|xhigh|max|ultra>",
            ]
        )
        self.assertIn(expected_command, context)
        state_path = next(
            (self.runtime_home / "state" / "adaptive-delegation" / "controller").glob(
                "state-*.json"
            )
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "awaiting_main_declaration")
        self.assertNotIn("main_model", state)
        self.assertNotIn("main_reasoning_effort", state)

        denied = gate.handle_hook(
            self.tool_payload("exec_command", {"cmd": "pwd"}),
            runtime_home=self.runtime_home,
        )
        self.assertEqual(
            denied["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_codex_prompt_shape_rejects_non_sol_model_without_effort(self) -> None:
        payload = self.prompt_payload("$adaptive-delegation implement it")
        payload["model"] = "gpt-5.6-terra"
        payload.pop("reasoning_effort")

        output = gate.handle_hook(payload, runtime_home=self.runtime_home)

        self.assertIn("Adaptive Delegation blocked", output["systemMessage"])
        self.assertFalse((self.runtime_home / "state").exists())

    def test_active_main_is_denied_task_tool_but_control_plane_is_allowed(self) -> None:
        self.activate()

        denied = gate.handle_hook(
            self.tool_payload(
                "functions.apply_patch",
                {"patch": "*** Begin Patch\n*** Update File: product.py\n"},
            ),
            runtime_home=self.runtime_home,
        )
        allowed = gate.handle_hook(
            self.tool_payload("functions.update_plan", {"plan": []}),
            runtime_home=self.runtime_home,
        )

        decision = denied["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("controller-only", decision["permissionDecisionReason"])
        self.assertEqual(allowed, {})

        ledger = state_path = (
            self.runtime_home
            / "state"
            / "adaptive-delegation"
            / "controller"
            / "controller-events.jsonl"
        )
        events = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual(events[-1]["event_type"], "main_tool_denied")
        self.assertEqual(events[-1]["tool_name"], "functions.apply_patch")
        self.assertNotIn("tool_input", events[-1])

    def test_controller_decision_cli_is_the_only_allowed_main_exec_lane(self) -> None:
        self.activate()
        controller = shlex.quote(str(Path(gate.__file__).resolve()))
        command = (
            f"{shlex.quote(sys.executable)} {controller} decision "
            f"--session-id {self.session_id} --workspace {shlex.quote(str(self.cwd))} "
            f"--decision leaf_required --objective-lock-digest {'e' * 64} "
            "--agent-type adaptive-luna-maker-high --model gpt-5.6-luna "
            "--reasoning-effort high"
        )

        allowed = gate.handle_hook(
            self.tool_payload("exec_command", {"cmd": command}),
            runtime_home=self.runtime_home,
        )
        compound = gate.handle_hook(
            self.tool_payload("exec_command", {"cmd": command + " && touch escaped"}),
            runtime_home=self.runtime_home,
        )
        substitution = gate.handle_hook(
            self.tool_payload(
                "Bash",
                {"command": command + " --evidence-ref '$(touch${IFS}/tmp/escaped)'"},
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(allowed, {})
        self.assertEqual(
            compound["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )
        self.assertEqual(
            substitution["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )

    def test_matching_adaptive_child_is_not_blocked_by_main_controller_state(self) -> None:
        self.activate()

        output = gate.handle_hook(
            self.tool_payload(
                "functions.exec",
                {"source": "await tools.exec_command({cmd: 'python3 -m unittest'});"},
                agent_type="adaptive-luna-maker-high",
                parent_session_id=self.session_id,
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(output, {})

    def test_cost_or_task_size_cannot_authorize_main_only_execution(self) -> None:
        self.activate()

        for reason in ("estimated_cheaper", "small_task", "existing_context", "latency"):
            with self.subTest(reason=reason):
                with self.assertRaises(gate.ControllerGateError):
                    gate.record_decision(
                        runtime_home=self.runtime_home,
                        session_id=self.session_id,
                        workspace=self.cwd,
                        decision="main_only_exception",
                        exception_reason=reason,
                        objective_lock_digest="a" * 64,
                        evidence_references=["local/evidence.json"],
                    )

        for decision, reason in (
            ("main_only_exception", "weak_oracle"),
            ("main_only_exception", "high_risk_or_ambiguous"),
            ("takeover", "ladder_exhausted"),
        ):
            with self.subTest(decision=decision, reason=reason):
                with self.assertRaisesRegex(
                    gate.ControllerGateError, "requires declared main ultra"
                ):
                    gate.record_decision(
                        runtime_home=self.runtime_home,
                        session_id=self.session_id,
                        workspace=self.cwd,
                        decision=decision,
                        exception_reason=reason,
                        objective_lock_digest="8" * 64,
                        evidence_references=["local/evidence.json"],
                    )

    def test_evidence_backed_non_delegable_exception_allows_main_tool(self) -> None:
        self.activate()
        gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="main_only_exception",
            exception_reason="non_delegable_authority",
            objective_lock_digest="b" * 64,
            evidence_references=["local/authority-check.json"],
        )

        output = gate.handle_hook(
            self.tool_payload("functions.apply_patch", {"patch": "bounded"}),
            runtime_home=self.runtime_home,
        )
        spawn = gate.handle_hook(
            self.tool_payload(
                "collaboration.spawn_agent",
                {
                    "task_name": "bypass",
                    "message": "unlocked",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "all",
                },
                agent_type="adaptive-luna-maker-high",
                parent_session_id=self.session_id,
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(output, {})
        self.assertEqual(
            spawn["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )
        self.assertIn(
            "does not authorize an unlocked child launch",
            spawn["hookSpecificOutput"]["permissionDecisionReason"],
        )
        ledger = (
            self.runtime_home
            / "state"
            / "adaptive-delegation"
            / "controller"
            / "controller-events.jsonl"
        )
        events = [json.loads(line) for line in ledger.read_text().splitlines()]
        decision_event = next(
            event for event in events if event["event_type"] == "delegation_decision"
        )
        self.assertEqual(decision_event["exception_reason"], "non_delegable_authority")
        self.assertNotIn("prompt", decision_event)
        self.assertEqual(events[-1]["event_type"], "main_tool_denied")

    def test_leaf_decision_allows_only_exact_fixed_role_spawn(self) -> None:
        self.activate()
        gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="c" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )

        allowed = gate.handle_hook(
            self.tool_payload(
                "collaboration.spawn_agent",
                {
                    "task_name": "bounded_change",
                    "message": f"OBJECTIVE LOCK: {'c' * 64}",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(allowed, {})
        state_path = next(
            (self.runtime_home / "state" / "adaptive-delegation" / "controller").glob(
                "state-*.json"
            )
        )
        state = json.loads(state_path.read_text())
        self.assertEqual(state["phase"], "leaf_launch_authorized")

    def test_native_spawn_tool_name_uses_the_same_exact_launch_gate(self) -> None:
        self.activate()
        gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="f" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )

        allowed = gate.handle_hook(
            self.tool_payload(
                "spawn_agent",
                {
                    "task_name": "bounded_change",
                    "message": f"OBJECTIVE LOCK: {'f' * 64}",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(allowed, {})

    def test_leaf_result_closes_launch_and_writes_cumulative_private_review(self) -> None:
        self.activate()
        gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="9" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        gate.handle_hook(
            self.tool_payload(
                "spawn_agent",
                {
                    "task_name": "bounded_change",
                    "message": f"OBJECTIVE LOCK: {'9' * 64}",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )

        with self.assertRaisesRegex(
            gate.ControllerGateError, "leaf result must be recorded"
        ):
            gate.record_decision(
                runtime_home=self.runtime_home,
                session_id=self.session_id,
                workspace=self.cwd,
                decision="leaf_required",
                objective_lock_digest="9" * 64,
                agent_type="adaptive-luna-maker-high",
                model="gpt-5.6-luna",
                reasoning_effort="high",
            )

        result_command = (
            f"{shlex.quote(sys.executable)} "
            f"{shlex.quote(str(Path(gate.__file__).resolve()))} result "
            f"--session-id {self.session_id} --workspace {shlex.quote(str(self.cwd))} "
            "--outcome accepted --route-assessment correct --quality-verdict pass "
            "--integration-accepted true --token-observation unavailable "
            "--evidence-ref local/checker-receipt.json"
        )
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload("Bash", {"command": result_command}),
                runtime_home=self.runtime_home,
            ),
            {},
        )

        state = gate.record_leaf_result(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            outcome="accepted",
            route_assessment="correct",
            quality_verdict="pass",
            integration_accepted=True,
            token_observation="unavailable",
            evidence_references=["local/checker-receipt.json"],
        )

        self.assertEqual(state["phase"], "leaf_result_recorded")
        review_dir = (
            self.runtime_home
            / "state"
            / "adaptive-delegation"
            / "controller"
            / "reviews"
        )
        reviews = list(review_dir.glob("controller-review-*.json"))
        self.assertEqual(len(reviews), 1)
        self.assertEqual(stat.S_IMODE(review_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(reviews[0].stat().st_mode), 0o600)
        review = json.loads(reviews[0].read_text(encoding="utf-8"))
        self.assertEqual(review["snapshot_kind"], "cumulative")
        self.assertEqual(review["trigger_reasons"], ["leaf-result"])
        self.assertEqual(review["model_selection"]["status"], "insufficient_sample")
        self.assertEqual(review["model_selection"]["appropriate"], 1)
        self.assertEqual(review["cost"]["observed_results"], 0)
        self.assertEqual(review["cost"]["unobserved_results"], 1)
        self.assertEqual(review["quality"]["accepted"], 1)
        self.assertEqual(review["quality"]["status"], "insufficient_sample")
        self.assertNotIn("evidence_references", review)

        closed = gate.close_controller(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            terminal_status="complete",
            evidence_references=["local/checker-receipt.json"],
        )
        self.assertEqual(closed["phase"], "closed")
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload("functions.apply_patch", {"patch": "next task"}),
                runtime_home=self.runtime_home,
            ),
            {},
        )

    def test_objective_lock_digest_is_immutable_across_leaf_retries(self) -> None:
        self.activate()
        digest = "7" * 64
        gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest=digest,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        gate.handle_hook(
            self.tool_payload(
                "spawn_agent",
                {
                    "task_name": "bounded_change",
                    "message": f"OBJECTIVE LOCK: {digest}",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )
        gate.record_leaf_result(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            outcome="failed",
            route_assessment="too-cheap",
            quality_verdict="fail",
            integration_accepted=False,
            token_observation="unavailable",
            evidence_references=["local/failed-check.json"],
        )

        with self.assertRaisesRegex(gate.ControllerGateError, "must remain immutable"):
            gate.record_decision(
                runtime_home=self.runtime_home,
                session_id=self.session_id,
                workspace=self.cwd,
                decision="leaf_required",
                objective_lock_digest="8" * 64,
                agent_type="adaptive-luna-maker-xhigh",
                model="gpt-5.6-luna",
                reasoning_effort="xhigh",
            )

        retry = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest=digest,
            agent_type="adaptive-luna-maker-xhigh",
            model="gpt-5.6-luna",
            reasoning_effort="xhigh",
        )
        self.assertEqual(retry["objective_lock_digest"], digest)

    def test_leaf_decision_denies_spawn_effort_mismatch(self) -> None:
        self.activate()
        gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="d" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )

        output = gate.handle_hook(
            self.tool_payload(
                "collaboration.spawn_agent",
                {
                    "task_name": "bounded_change",
                    "message": f"OBJECTIVE LOCK: {'d' * 64}",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "xhigh",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )
        self.assertIn("launch envelope", output["hookSpecificOutput"]["permissionDecisionReason"])


if __name__ == "__main__":
    unittest.main()
