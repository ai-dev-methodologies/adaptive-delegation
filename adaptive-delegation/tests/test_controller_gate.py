from __future__ import annotations

import io
import json
import os
import shlex
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock
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
        self.main_turn_id = "22222222-2222-4222-8222-222222222222"
        self.child_turn_id = "33333333-3333-4333-8333-333333333333"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prompt_payload(self, prompt: str) -> dict[str, object]:
        return {
            "hook_event_name": "UserPromptSubmit",
            "session_id": self.session_id,
            "turn_id": self.main_turn_id,
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
            "turn_id": self.main_turn_id,
            "cwd": str(self.cwd),
            "tool_name": tool_name,
            "tool_input": tool_input or {},
        }
        payload.update(overrides)
        return payload

    def child_transcript(
        self,
        decision: dict[str, object],
        *,
        turn_id: str | None = None,
        task_name: str | None = None,
    ) -> Path:
        planned = decision["planned_launch"]
        self.assertIsInstance(planned, dict)
        selected_task_name = task_name or planned["task_name"]
        selected_turn_id = turn_id or self.child_turn_id
        today = gate._datetime.datetime.now(gate._datetime.timezone.utc)
        transcript = self.runtime_home / "sessions" / f"{today:%Y}" / f"{today:%m}" / f"{today:%d}" / "child-rollout.jsonl"
        transcript.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "type": "session_meta",
                "payload": {
                    "session_id": self.session_id,
                    "parent_thread_id": self.session_id,
                    "thread_source": "subagent",
                    "agent_role": planned["agent_type"],
                    "source": {
                        "subagent": {
                            "thread_spawn": {
                                "parent_thread_id": self.session_id,
                                "agent_path": f"/root/{selected_task_name}",
                                "agent_role": planned["agent_type"],
                            }
                        }
                    },
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "task_started",
                    "turn_id": selected_turn_id,
                },
            },
        ]
        transcript.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        return transcript

    def activate(self) -> Path:
        output = gate.handle_hook(
            self.prompt_payload("$adaptive-delegation implement the bounded change"),
            runtime_home=self.runtime_home,
        )
        self.assertEqual(
            output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
        )
        self.assertIn("preflight", output["hookSpecificOutput"]["additionalContext"])
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
        self.assertEqual(state["main_turn_id"], self.main_turn_id)
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

    def test_actionable_mid_prompt_defers_activation_to_main_judgment(self) -> None:
        output = gate.handle_hook(
            self.prompt_payload(
                "Continue the current work and use adaptive-delegation for the bounded slices."
            ),
            runtime_home=self.runtime_home,
        )

        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Decide from the user's actionable intent", context)
        self.assertIn(" activate ", context)
        self.assertFalse((self.runtime_home / "state").exists())

    def test_main_can_activate_after_semantic_judgment_without_prefix(self) -> None:
        state = gate.activate_controller(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            main_turn_id=self.main_turn_id,
            model="gpt-5.6-sol",
            reasoning_effort="high",
        )

        self.assertEqual(state["phase"], "explicit_active")
        self.assertEqual(state["main_model"], "gpt-5.6-sol")
        self.assertEqual(state["main_turn_id"], self.main_turn_id)

    def test_natural_mention_preserves_an_open_controller_without_reactivation(self) -> None:
        state_path = self.activate()
        before = json.loads(state_path.read_text(encoding="utf-8"))
        payload = self.prompt_payload(
            "Continue using adaptive-delegation for the already active task."
        )
        payload["turn_id"] = "77777777-7777-4777-8777-777777777777"

        output = gate.handle_hook(payload, runtime_home=self.runtime_home)

        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIn("already active", output["systemMessage"])
        self.assertNotIn(" activate ", output["systemMessage"])
        self.assertEqual(after["activation_id"], before["activation_id"])
        self.assertEqual(after["main_turn_id"], payload["turn_id"])

    def test_repeated_explicit_invocation_preserves_open_controller(self) -> None:
        state_path = self.activate()
        gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="6" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        before = json.loads(state_path.read_text(encoding="utf-8"))

        output = gate.handle_hook(
            self.prompt_payload("$adaptive-delegation continue the same task"),
            runtime_home=self.runtime_home,
        )

        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIn("preflight", output["systemMessage"])
        self.assertEqual(after["activation_id"], before["activation_id"])
        self.assertEqual(after["phase"], "leaf_required")
        ledger = state_path.parent / "controller-events.jsonl"
        events = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual(
            sum(event["event_type"] == "explicit_activation" for event in events),
            1,
        )

    def test_closed_controller_starts_a_distinct_later_activation(self) -> None:
        state_path = self.activate()
        before = json.loads(state_path.read_text(encoding="utf-8"))
        gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="main_only_exception",
            exception_reason="non_delegable_authority",
            objective_lock_digest="5" * 64,
            evidence_references=["local/authority-check.json"],
        )
        gate.close_controller(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            terminal_status="complete",
            evidence_references=["local/authority-check.json"],
        )

        output = gate.handle_hook(
            self.prompt_payload("$adaptive-delegation start a later task"),
            runtime_home=self.runtime_home,
        )

        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIn("preflight", output["systemMessage"])
        self.assertNotEqual(after["activation_id"], before["activation_id"])
        self.assertEqual(after["phase"], "explicit_active")

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
        self.assertIn("preflight", output["systemMessage"])
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

    def test_active_main_allows_goal_control_plane_continuation_but_denies_product_work(self) -> None:
        self.activate()

        for tool_name in (
            "functions.get_goal",
            "functions.update_goal",
            "functions.hud",
        ):
            with self.subTest(tool_name=tool_name):
                self.assertEqual(
                    gate.handle_hook(
                        self.tool_payload(tool_name, {}),
                        runtime_home=self.runtime_home,
                    ),
                    {},
                )

        denied = gate.handle_hook(
            self.tool_payload("functions.apply_patch", {"patch": "product"}),
            runtime_home=self.runtime_home,
        )
        self.assertEqual(
            denied["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )

    def test_codex_sanitized_control_plane_tool_name_is_allowed(self) -> None:
        self.activate()

        output = gate.handle_hook(
            self.tool_payload("collaborationlist_agents", {}),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(output, {})

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

    def test_controller_preflight_is_the_only_allowed_main_read_lane(self) -> None:
        self.activate()
        controller = shlex.quote(str(Path(gate.__file__).resolve()))
        command = (
            f"{shlex.quote(sys.executable)} {controller} preflight "
            f"--session-id {self.session_id} --workspace {shlex.quote(str(self.cwd))} "
            "--surface skill"
        )

        allowed = gate.handle_hook(
            self.tool_payload("exec_command", {"cmd": command}),
            runtime_home=self.runtime_home,
        )
        extra_flag = gate.handle_hook(
            self.tool_payload(
                "exec_command", {"cmd": command + " --model gpt-5.6-sol"}
            ),
            runtime_home=self.runtime_home,
        )
        route_without_role = gate.handle_hook(
            self.tool_payload(
                "exec_command",
                {"cmd": command.removesuffix("skill") + "route"},
            ),
            runtime_home=self.runtime_home,
        )
        exact_route = gate.handle_hook(
            self.tool_payload(
                "exec_command",
                {
                    "cmd": command.removesuffix("skill")
                    + "route --agent-type adaptive-luna-maker-high"
                },
            ),
            runtime_home=self.runtime_home,
        )
        direct_read = gate.handle_hook(
            self.tool_payload(
                "exec_command",
                {"cmd": f"sed -n '1,9999p' {gate.SKILL_ROOT / 'SKILL.md'}"},
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(allowed, {})
        self.assertEqual(exact_route, {})
        self.assertEqual(
            extra_flag["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertEqual(
            route_without_role["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertEqual(
            direct_read["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_preflight_returns_only_skill_or_selected_route_surfaces(self) -> None:
        self.activate()
        agents = self.runtime_home / "agents"
        agents.mkdir(parents=True)
        role_name = "adaptive-luna-maker-high"
        role_source = gate.SKILL_ROOT / "roles" / f"{role_name}.toml"
        (agents / f"{role_name}.toml").write_text(
            role_source.read_text(encoding="utf-8"), encoding="utf-8"
        )

        skill = gate.read_controller_preflight(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            surface="skill",
            agent_type=None,
        )
        route = gate.read_controller_preflight(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            surface="route",
            agent_type=role_name,
        )

        self.assertIn("# Adaptive Delegation", skill["content"])
        self.assertEqual(
            route["task_defaults"]["clear_implementation_or_transformation"],
            "luna_high",
        )
        self.assertEqual(route["role_binding"]["model"], "gpt-5.6-luna")
        self.assertIn('model = "gpt-5.6-luna"', route["role_toml"])
        commands = route["lifecycle_command_templates"]
        decision_tokens = shlex.split(commands["decision_leaf_required"])
        accepted_tokens = shlex.split(commands["result_accepted"])
        admission_failure_tokens = shlex.split(commands["admission_failure"])
        close_tokens = shlex.split(commands["close_complete"])
        self.assertEqual(
            decision_tokens[:3],
            [sys.executable, str(Path(gate.__file__).resolve()), "decision"],
        )
        self.assertEqual(
            decision_tokens[decision_tokens.index("--agent-type") + 1], role_name
        )
        self.assertEqual(
            decision_tokens[decision_tokens.index("--model") + 1],
            "gpt-5.6-luna",
        )
        self.assertEqual(
            decision_tokens[decision_tokens.index("--reasoning-effort") + 1],
            "high",
        )
        self.assertIn("--integration-accepted", accepted_tokens)
        self.assertIn("--token-observation", accepted_tokens)
        self.assertEqual(admission_failure_tokens[2], "admission-failure")
        self.assertIn("--evidence-ref", admission_failure_tokens)
        self.assertEqual(
            close_tokens[close_tokens.index("--terminal-status") + 1], "complete"
        )
        self.assertEqual(
            route["lifecycle_allowed_values"]["quality_verdict"],
            ["fail", "inconclusive", "pass"],
        )
        with self.assertRaisesRegex(gate.ControllerGateError, "package-declared"):
            gate.read_controller_preflight(
                runtime_home=self.runtime_home,
                session_id=self.session_id,
                workspace=self.cwd,
                surface="route",
                agent_type="adaptive-not-installed",
            )
        role_text = (agents / f"{role_name}.toml").read_text(encoding="utf-8")
        (agents / f"{role_name}.toml").unlink()
        agents.rmdir()
        outside = self.runtime_home.parent / "outside-agents"
        outside.mkdir()
        (outside / f"{role_name}.toml").write_text(role_text, encoding="utf-8")
        agents.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(gate.ControllerGateError, "unavailable"):
            gate.read_controller_preflight(
                runtime_home=self.runtime_home,
                session_id=self.session_id,
                workspace=self.cwd,
                surface="route",
                agent_type=role_name,
            )

    def test_route_preflight_rejects_symlinked_or_oversized_policy(self) -> None:
        self.activate()
        agents = self.runtime_home / "agents"
        agents.mkdir(parents=True)
        role_name = "adaptive-luna-maker-high"
        role_source = gate.SKILL_ROOT / "roles" / f"{role_name}.toml"
        (agents / f"{role_name}.toml").write_text(
            role_source.read_text(encoding="utf-8"), encoding="utf-8"
        )
        outside = self.runtime_home.parent / "outside-policy.json"
        outside.write_text(gate.POLICY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        linked = self.runtime_home.parent / "linked-policy.json"
        linked.symlink_to(outside)

        with mock.patch.object(gate, "POLICY_PATH", linked):
            with self.assertRaisesRegex(gate.ControllerGateError, "unavailable"):
                gate.read_controller_preflight(
                    runtime_home=self.runtime_home,
                    session_id=self.session_id,
                    workspace=self.cwd,
                    surface="route",
                    agent_type=role_name,
                )

        oversized = self.runtime_home.parent / "oversized-policy.json"
        oversized.write_text(
            " " * (gate.MAX_PREFLIGHT_FILE_BYTES + 1), encoding="utf-8"
        )
        with mock.patch.object(gate, "POLICY_PATH", oversized):
            with self.assertRaisesRegex(gate.ControllerGateError, "exceeds"):
                gate.read_controller_preflight(
                    runtime_home=self.runtime_home,
                    session_id=self.session_id,
                    workspace=self.cwd,
                    surface="route",
                    agent_type=role_name,
                )

    def test_matching_adaptive_child_is_not_blocked_by_main_controller_state(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="3" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        gate.handle_hook(
            self.tool_payload(
                "collaborationspawn_agent",
                {
                    "task_name": decision["planned_launch"]["task_name"],
                    "message": "gAAAAABopaque-native-hook-message",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
                agent_type="adaptive-luna-maker-high",
                parent_session_id=self.session_id,
            ),
            runtime_home=self.runtime_home,
        )
        wrong_transcript = self.child_transcript(
            decision,
            task_name="adaptive_" + "f" * 64,
        )
        wrong_child = gate.handle_hook(
            self.tool_payload(
                "Bash",
                {"command": "sed -n '1p' bounded.txt"},
                turn_id=self.child_turn_id,
                transcript_path=str(wrong_transcript),
            ),
            runtime_home=self.runtime_home,
        )
        child_transcript = self.child_transcript(decision)

        output = gate.handle_hook(
            self.tool_payload(
                "Bash",
                {"command": "sed -n '1p' bounded.txt"},
                turn_id=self.child_turn_id,
                transcript_path=str(child_transcript),
            ),
            runtime_home=self.runtime_home,
        )
        foreign_output = gate.handle_hook(
            self.tool_payload(
                "Bash",
                {"command": "sed -n '1p' foreign.txt"},
                turn_id="55555555-5555-4555-8555-555555555555",
                transcript_path=str(child_transcript),
            ),
            runtime_home=self.runtime_home,
        )
        main_output = gate.handle_hook(
            self.tool_payload(
                "Bash",
                {"command": "sed -n '1p' main-must-not-read.txt"},
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(
            wrong_child["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertEqual(output, {})
        self.assertEqual(
            foreign_output["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertEqual(
            main_output["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_child_without_payload_transcript_binds_unique_exact_rollout(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            decision="leaf_required", objective_lock_digest="a" * 64,
            agent_type="adaptive-luna-maker-high", model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertEqual(gate.handle_hook(self.tool_payload("spawn_agent", {
            "task_name": decision["planned_launch"]["task_name"], "message": "locked",
            "agent_type": "adaptive-luna-maker-high", "reasoning_effort": "high",
            "fork_turns": "none",
        }), runtime_home=self.runtime_home), {})
        self.child_transcript(decision)
        self.assertEqual(gate.handle_hook(self.tool_payload(
            "Bash", {"command": "true"}, turn_id=self.child_turn_id,
        ), runtime_home=self.runtime_home), {})

    def test_child_fallback_ignores_many_old_unrelated_rollouts(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            decision="leaf_required", objective_lock_digest="0" * 64,
            agent_type="adaptive-luna-maker-high", model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertEqual(gate.handle_hook(self.tool_payload("spawn_agent", {
            "task_name": decision["planned_launch"]["task_name"], "message": "locked",
            "agent_type": "adaptive-luna-maker-high", "reasoning_effort": "high",
            "fork_turns": "none",
        }), runtime_home=self.runtime_home), {})
        old_root = self.runtime_home / "sessions" / "old"
        old_root.mkdir(parents=True)
        for index in range(gate.MAX_TRANSCRIPT_BINDING_FILES + 1):
            old = old_root / f"{index}.jsonl"
            old.write_text("{}\n", encoding="utf-8")
            os.utime(old, (1, 1))
        self.child_transcript(decision)
        self.assertEqual(gate.handle_hook(self.tool_payload(
            "Bash", {"command": "true"}, turn_id=self.child_turn_id,
        ), runtime_home=self.runtime_home), {})

    def test_child_fallback_rejects_ambiguous_or_unsafe_rollouts(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            decision="leaf_required", objective_lock_digest="b" * 64,
            agent_type="adaptive-luna-maker-high", model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertEqual(gate.handle_hook(self.tool_payload("spawn_agent", {
            "task_name": decision["planned_launch"]["task_name"], "message": "locked",
            "agent_type": "adaptive-luna-maker-high", "reasoning_effort": "high",
            "fork_turns": "none",
        }), runtime_home=self.runtime_home), {})
        first = self.child_transcript(decision)
        second = first.with_name("second-rollout.jsonl")
        second.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
        denied = gate.handle_hook(self.tool_payload(
            "Bash", {"command": "true"}, turn_id=self.child_turn_id,
        ), runtime_home=self.runtime_home)
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        second.unlink()
        first.unlink()
        first.symlink_to(self.cwd / "missing-rollout.jsonl")
        denied = gate.handle_hook(self.tool_payload(
            "Bash", {"command": "true"}, turn_id=self.child_turn_id,
        ), runtime_home=self.runtime_home)
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_admission_failure_releases_pending_leaf_for_next_decision(self) -> None:
        self.activate()
        digest = "c" * 64
        gate.record_decision(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            decision="leaf_required", objective_lock_digest=digest,
            agent_type="adaptive-luna-maker-high", model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        state = gate.record_launch_admission_failure(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            evidence_references=["local/native-rejection.json"],
        )
        self.assertEqual(state["phase"], "leaf_result_recorded")
        self.assertEqual(state["last_outcome"], "path_blocked")
        retry = gate.record_decision(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            decision="leaf_required", objective_lock_digest=digest,
            agent_type="adaptive-luna-maker-high", model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertEqual(retry["phase"], "leaf_required")

    def test_admission_failure_releases_authorized_leaf_without_created_child(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            decision="leaf_required", objective_lock_digest="f" * 64,
            agent_type="adaptive-luna-maker-high", model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertEqual(gate.handle_hook(self.tool_payload("spawn_agent", {
            "task_name": decision["planned_launch"]["task_name"], "message": "locked",
            "agent_type": "adaptive-luna-maker-high", "reasoning_effort": "high",
            "fork_turns": "none",
        }), runtime_home=self.runtime_home), {})
        state = gate.record_launch_admission_failure(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            evidence_references=["local/native-rejection.json"],
        )
        self.assertEqual(state["phase"], "leaf_result_recorded")

    def test_admission_failure_rejects_authorized_or_completed_child_phases(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            decision="leaf_required", objective_lock_digest="d" * 64,
            agent_type="adaptive-luna-maker-high", model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertEqual(gate.handle_hook(self.tool_payload("spawn_agent", {
            "task_name": decision["planned_launch"]["task_name"], "message": "locked",
            "agent_type": "adaptive-luna-maker-high", "reasoning_effort": "high",
            "fork_turns": "none",
        }), runtime_home=self.runtime_home), {})
        self.child_transcript(decision)
        with self.assertRaisesRegex(gate.ControllerGateError, "no created child"):
            gate.record_launch_admission_failure(
                runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
                evidence_references=["local/native-rejection.json"],
            )

    def test_child_restart_rebinds_only_same_bound_transcript(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            decision="leaf_required", objective_lock_digest="e" * 64,
            agent_type="adaptive-luna-maker-high", model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertEqual(gate.handle_hook(self.tool_payload("spawn_agent", {
            "task_name": decision["planned_launch"]["task_name"], "message": "locked",
            "agent_type": "adaptive-luna-maker-high", "reasoning_effort": "high",
            "fork_turns": "none",
        }), runtime_home=self.runtime_home), {})
        transcript = self.child_transcript(decision)
        self.assertEqual(gate.handle_hook(self.tool_payload(
            "Bash", {"command": "true"}, turn_id=self.child_turn_id,
            transcript_path=str(transcript),
        ), runtime_home=self.runtime_home), {})
        restart_turn = "77777777-7777-4777-8777-777777777777"
        with transcript.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "event_msg", "payload": {
                "type": "task_started", "turn_id": restart_turn,
            }}) + "\n")
        self.assertEqual(gate.handle_hook(self.tool_payload(
            "Bash", {"command": "true"}, turn_id=restart_turn,
        ), runtime_home=self.runtime_home), {})

    def test_child_restart_finds_late_task_started_in_bound_transcript(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home, session_id=self.session_id, workspace=self.cwd,
            decision="leaf_required", objective_lock_digest="1" * 64,
            agent_type="adaptive-luna-maker-high", model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        gate.handle_hook(self.tool_payload("spawn_agent", {
            "task_name": decision["planned_launch"]["task_name"], "message": "locked",
            "agent_type": "adaptive-luna-maker-high", "reasoning_effort": "high", "fork_turns": "none",
        }), runtime_home=self.runtime_home)
        transcript = self.child_transcript(decision)
        gate.handle_hook(self.tool_payload("Bash", {"command": "true"}, turn_id=self.child_turn_id,
            transcript_path=str(transcript)), runtime_home=self.runtime_home)
        restart_turn = "88888888-8888-4888-8888-888888888888"
        with transcript.open("a", encoding="utf-8") as handle:
            for _ in range(gate.MAX_TRANSCRIPT_BINDING_LINES + 1):
                handle.write(json.dumps({"type": "event_msg", "payload": {"type": "noise"}}) + "\n")
            handle.write(json.dumps({"type": "event_msg", "payload": {
                "type": "task_started", "turn_id": restart_turn,
            }}) + "\n")
        self.assertEqual(gate.handle_hook(self.tool_payload("Bash", {"command": "true"}, turn_id=restart_turn),
            runtime_home=self.runtime_home), {})

    def test_foreign_turn_cannot_run_exact_controller_command(self) -> None:
        self.activate()
        command = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(gate.__file__).resolve()))} "
            f"admission-failure --session-id {self.session_id} --workspace {shlex.quote(str(self.cwd))} "
            "--evidence-ref local/native-rejection.json"
        )
        output = gate.handle_hook(self.tool_payload("Bash", {"command": command},
            turn_id=self.child_turn_id), runtime_home=self.runtime_home)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_adaptive_child_permission_escalation_is_denied_without_user_prompt(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="4" * 64,
            agent_type="adaptive-luna-maker-max",
            model="gpt-5.6-luna",
            reasoning_effort="max",
        )
        gate.handle_hook(
            self.tool_payload(
                "collaborationspawn_agent",
                {
                    "task_name": decision["planned_launch"]["task_name"],
                    "message": "locked",
                    "agent_type": "adaptive-luna-maker-max",
                    "reasoning_effort": "max",
                    "fork_turns": "none",
                },
                agent_type="adaptive-luna-maker-max",
                parent_session_id=self.session_id,
            ),
            runtime_home=self.runtime_home,
        )
        transcript = self.child_transcript(decision)

        output = gate.handle_hook(
            self.tool_payload(
                "functions.exec",
                {
                    "code": 'tools.exec_command({cmd:"mv old new", sandbox_permissions:"require_escalated"})'
                },
                turn_id=self.child_turn_id,
                transcript_path=str(transcript),
            ),
            runtime_home=self.runtime_home,
        )

        decision_output = output["hookSpecificOutput"]
        self.assertEqual(decision_output["permissionDecision"], "deny")
        self.assertIn("without permission escalation", decision_output["permissionDecisionReason"])
        self.assertNotIn("ask the user", decision_output["permissionDecisionReason"].lower())
        ledger = (
            self.runtime_home
            / "state"
            / "adaptive-delegation"
            / "controller"
            / "controller-events.jsonl"
        )
        events = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual(events[-1]["event_type"], "child_permission_escalation_denied")

    def test_nonexplicit_user_prompt_refreshes_the_main_turn_identity(self) -> None:
        state_path = self.activate()
        next_turn_id = "44444444-4444-4444-8444-444444444444"
        payload = self.prompt_payload("Continue with a normal main request")
        payload["turn_id"] = next_turn_id

        output = gate.handle_hook(payload, runtime_home=self.runtime_home)

        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(output, {})
        self.assertEqual(state["main_turn_id"], next_turn_id)

    def test_main_spawn_metadata_cannot_bypass_a_missing_leaf_decision(self) -> None:
        self.activate()

        output = gate.handle_hook(
            self.tool_payload(
                "collaborationspawn_agent",
                {
                    "task_name": "adaptive_" + "0" * 64,
                    "message": "gAAAAABopaque-native-hook-message",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
                agent_type="adaptive-luna-maker-high",
                parent_session_id=self.session_id,
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        state_path = next(
            (self.runtime_home / "state" / "adaptive-delegation" / "controller").glob(
                "state-*.json"
            )
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "explicit_active")

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

    def test_main_may_keep_a_context_bound_microtask_with_recorded_judgment(self) -> None:
        self.activate()

        state = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="main_only_exception",
            exception_reason="context_bound_microtask",
            objective_lock_digest="c" * 64,
            evidence_references=["local/main-routing-judgment.json"],
        )

        self.assertEqual(state["phase"], "main_only_exception")

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
        decision = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="c" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        task_name = decision["planned_launch"]["task_name"]

        allowed = gate.handle_hook(
            self.tool_payload(
                "collaboration.spawn_agent",
                {
                    "task_name": task_name,
                    "message": "gAAAAABopaque-native-hook-message",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
                agent_type="adaptive-luna-maker-high",
                parent_session_id=self.session_id,
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

    def test_leaf_decision_cli_returns_exact_launch_task_name(self) -> None:
        self.activate()
        output = io.StringIO()
        arguments = [
            "decision",
            "--session-id",
            self.session_id,
            "--workspace",
            str(self.cwd),
            "--decision",
            "leaf_required",
            "--objective-lock-digest",
            "e" * 64,
            "--agent-type",
            "adaptive-luna-maker-high",
            "--model",
            "gpt-5.6-luna",
            "--reasoning-effort",
            "high",
        ]

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(self.runtime_home)}):
            with redirect_stdout(output):
                exit_code = gate.main(arguments)

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertRegex(result["launch_task_name"], r"^adaptive_[0-9a-f]{64}$")

    def test_leaf_decision_denies_wrong_launch_task_name_with_opaque_message(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="a" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )

        output = gate.handle_hook(
            self.tool_payload(
                "collaborationspawn_agent",
                {
                    "task_name": "adaptive_" + "0" * 64,
                    "message": "gAAAAABopaque-native-hook-message",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )

        self.assertNotEqual(
            decision["planned_launch"].get("task_name"),
            "adaptive_" + "0" * 64,
        )
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        state_path = next(
            (self.runtime_home / "state" / "adaptive-delegation" / "controller").glob(
                "state-*.json"
            )
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "leaf_required")

    def test_native_spawn_tool_name_uses_the_same_exact_launch_gate(self) -> None:
        self.activate()
        decision = gate.record_decision(
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
                    "task_name": decision["planned_launch"]["task_name"],
                    "message": f"OBJECTIVE LOCK: {'f' * 64}",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(allowed, {})

    def test_arbitrary_punctuation_variant_is_not_a_spawn_alias(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="4" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )

        output = gate.handle_hook(
            self.tool_payload(
                "collaboration/spawn_agent",
                {
                    "task_name": decision["planned_launch"]["task_name"],
                    "message": f"OBJECTIVE LOCK: {'4' * 64}",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        state_path = next(
            (self.runtime_home / "state" / "adaptive-delegation" / "controller").glob(
                "state-*.json"
            )
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "leaf_required")

    def test_leaf_result_closes_launch_and_writes_cumulative_private_review(self) -> None:
        self.activate()
        decision = gate.record_decision(
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
                "collaborationspawn_agent",
                {
                    "task_name": decision["planned_launch"]["task_name"],
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

    def test_accepted_maker_can_continue_to_checker_with_immutable_lock(self) -> None:
        self.activate()
        digest = "a" * 64
        maker = gate.record_decision(
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
                    "task_name": maker["planned_launch"]["task_name"],
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
            outcome="accepted",
            route_assessment="correct",
            quality_verdict="pass",
            integration_accepted=True,
            token_observation="unavailable",
            evidence_references=["local/maker-receipt.json"],
        )

        checker = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest=digest,
            agent_type="adaptive-luna-checker-xhigh",
            model="gpt-5.6-luna",
            reasoning_effort="xhigh",
        )

        self.assertEqual(checker["phase"], "leaf_required")
        self.assertEqual(checker["objective_lock_digest"], digest)
        self.assertEqual(
            checker["planned_launch"]["agent_type"], "adaptive-luna-checker-xhigh"
        )

    def test_next_main_only_decision_clears_prior_leaf_bindings(self) -> None:
        self.activate()
        digest = "b" * 64
        maker = gate.record_decision(
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
                    "task_name": maker["planned_launch"]["task_name"],
                    "message": f"OBJECTIVE LOCK: {digest}",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )
        transcript = self.child_transcript(maker)
        gate.handle_hook(
            self.tool_payload(
                "Bash",
                {"command": "true"},
                turn_id=self.child_turn_id,
                transcript_path=str(transcript),
            ),
            runtime_home=self.runtime_home,
        )
        gate.record_leaf_result(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            outcome="accepted",
            route_assessment="correct",
            quality_verdict="pass",
            integration_accepted=True,
            token_observation="unavailable",
            evidence_references=["local/maker-receipt.json"],
        )

        main_only = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="main_only_exception",
            exception_reason="context_bound_microtask",
            objective_lock_digest=digest,
            evidence_references=["local/main-routing.json"],
        )

        self.assertEqual(main_only["phase"], "main_only_exception")
        self.assertEqual(main_only["objective_lock_digest"], digest)
        self.assertEqual(main_only["last_outcome"], "accepted")
        for key in ("planned_launch", "child_turn_id", "child_transcript_path"):
            self.assertNotIn(key, main_only)

    def test_adaptive_child_cannot_run_exact_controller_command_after_launch(self) -> None:
        self.activate()
        digest = "c" * 64
        decision = gate.record_decision(
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
                    "task_name": decision["planned_launch"]["task_name"],
                    "message": f"OBJECTIVE LOCK: {digest}",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )
        transcript = self.child_transcript(decision)
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload(
                    "Bash",
                    {"command": "true"},
                    turn_id=self.child_turn_id,
                    transcript_path=str(transcript),
                ),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        command = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(gate.__file__).resolve()))} "
            f"result --session-id {self.session_id} --workspace {shlex.quote(str(self.cwd))} "
            "--outcome path_blocked --route-assessment inconclusive "
            "--quality-verdict inconclusive --integration-accepted false "
            "--token-observation unavailable --evidence-ref local/blocked.json"
        )

        output = gate.handle_hook(
            self.tool_payload(
                "Bash",
                {"command": command},
                turn_id=self.child_turn_id,
                transcript_path=str(transcript),
            ),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("turn binding", output["hookSpecificOutput"]["permissionDecisionReason"].lower())

    def test_stale_main_turn_controller_command_reports_turn_binding_failure(self) -> None:
        self.activate()
        command = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(gate.__file__).resolve()))} "
            f"result --session-id {self.session_id} --workspace {shlex.quote(str(self.cwd))} "
            "--outcome accepted --route-assessment correct --quality-verdict pass "
            "--integration-accepted true --token-observation unavailable "
            "--evidence-ref local/checker.json"
        )

        output = gate.handle_hook(
            self.tool_payload("Bash", {"command": command}, turn_id=self.child_turn_id),
            runtime_home=self.runtime_home,
        )

        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("turn binding", reason.lower())
        self.assertNotIn("invalid controller result command", reason.lower())

    def test_predecision_controller_can_cancel_without_terminal_status(self) -> None:
        state_path = self.activate()
        cancel_command = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(gate.__file__).resolve()))} "
            f"cancel --session-id {self.session_id} --workspace {shlex.quote(str(self.cwd))}"
        )
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload("Bash", {"command": cancel_command}),
                runtime_home=self.runtime_home,
            ),
            {},
        )

        output = io.StringIO()
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(self.runtime_home)}):
            with redirect_stdout(output):
                exit_code = gate.main(
                    [
                        "cancel",
                        "--session-id",
                        self.session_id,
                        "--workspace",
                        str(self.cwd),
                    ]
                )

        cancelled = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(cancelled, {"phase": "closed", "recorded": True})
        state = json.loads(state_path.read_text())
        self.assertNotIn("terminal_status", state)
        events = [
            json.loads(line)
            for line in (state_path.parent / "controller-events.jsonl").read_text().splitlines()
        ]
        self.assertEqual(events[-1]["event_type"], "controller_cancelled")
        self.assertNotIn("terminal_status", events[-1])
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload("functions.apply_patch", {"patch": "released"}),
                runtime_home=self.runtime_home,
            ),
            {},
        )

    def test_awaiting_main_declaration_can_cancel(self) -> None:
        payload = self.prompt_payload("$adaptive-delegation wait for declaration")
        payload.pop("model")
        payload.pop("reasoning_effort")
        output = gate.handle_hook(payload, runtime_home=self.runtime_home)
        self.assertIn("declare-main", output["systemMessage"])

        cancel_command = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(gate.__file__).resolve()))} "
            f"cancel --session-id {self.session_id} --workspace {shlex.quote(str(self.cwd))}"
        )
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload("Bash", {"command": cancel_command}),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        state_path = next(
            (self.runtime_home / "state" / "adaptive-delegation" / "controller").glob(
                "state-*.json"
            )
        )
        self.assertEqual(json.loads(state_path.read_text())["phase"], "awaiting_main_declaration")

        gate.cancel_controller(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
        )
        self.assertEqual(json.loads(state_path.read_text())["phase"], "closed")

    def test_cancel_after_decision_is_denied(self) -> None:
        self.activate()
        gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="main_only_exception",
            exception_reason="context_bound_microtask",
            objective_lock_digest="d" * 64,
            evidence_references=["local/main-routing.json"],
        )
        cancel_command = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(gate.__file__).resolve()))} "
            f"cancel --session-id {self.session_id} --workspace {shlex.quote(str(self.cwd))}"
        )

        output = gate.handle_hook(
            self.tool_payload("Bash", {"command": cancel_command}),
            runtime_home=self.runtime_home,
        )

        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("before a decision", output["hookSpecificOutput"]["permissionDecisionReason"])
        with self.assertRaisesRegex(gate.ControllerGateError, "before a decision"):
            gate.cancel_controller(
                runtime_home=self.runtime_home,
                session_id=self.session_id,
                workspace=self.cwd,
            )

    def test_bound_leaf_transcript_promotes_unavailable_cost_to_exact(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="1" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        gate.handle_hook(
            self.tool_payload(
                "collaborationspawn_agent",
                {
                    "task_name": decision["planned_launch"]["task_name"],
                    "message": "gAAAAABopaque-native-hook-message",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )
        transcript = self.child_transcript(decision)
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload(
                    "Bash",
                    {"command": "python3 -m unittest -v test_target.py"},
                    turn_id=self.child_turn_id,
                    transcript_path=str(transcript),
                ),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        with transcript.open("a", encoding="utf-8") as handle:
            for index in range(6):
                handle.write(
                    json.dumps(
                        {
                            "type": "response_item",
                            "payload": {"type": "message", "index": index},
                        }
                    )
                    + "\n"
                )
            handle.write(
                json.dumps(
                    {
                        "type": "world_state",
                        "payload": {"opaque": "x" * (2 * 1024 * 1024)},
                    }
                )
                + "\n"
            )
            handle.write(
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 100,
                                    "output_tokens": 7,
                                    "total_tokens": 107,
                                }
                            },
                        },
                    }
                )
                + "\n"
            )

        gate.record_leaf_result(
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

        ledger = (
            self.runtime_home
            / "state"
            / "adaptive-delegation"
            / "controller"
            / "controller-events.jsonl"
        )
        result_event = next(
            event
            for event in reversed(
                [json.loads(line) for line in ledger.read_text().splitlines()]
            )
            if event["event_type"] == "leaf_result_recorded"
        )
        self.assertEqual(result_event["token_observation"], "exact")
        self.assertEqual(
            result_event["token_observation_source"], "bound_child_transcript"
        )
        self.assertEqual(result_event["weighted_tokens"], 32)
        self.assertEqual(result_event["cost_proxy"], 1.28)
        review_path = next(
            (
                self.runtime_home
                / "state"
                / "adaptive-delegation"
                / "controller"
                / "reviews"
            ).glob("controller-review-*.json")
        )
        review = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertEqual(review["cost"]["status"], "observed")
        self.assertEqual(review["cost"]["weighted_tokens_observed"], 32)
        self.assertEqual(
            review["cost"]["observation_sources"],
            {"bound_child_transcript": 1},
        )

    def test_unavailable_cost_records_its_source_when_usage_cannot_be_bound(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="2" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        gate.handle_hook(
            self.tool_payload(
                "collaborationspawn_agent",
                {
                    "task_name": decision["planned_launch"]["task_name"],
                    "message": "gAAAAABopaque-native-hook-message",
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
            outcome="path_blocked",
            route_assessment="inconclusive",
            quality_verdict="inconclusive",
            integration_accepted=False,
            token_observation="unavailable",
            evidence_references=["local/path-blocked.json"],
        )

        ledger = (
            self.runtime_home
            / "state"
            / "adaptive-delegation"
            / "controller"
            / "controller-events.jsonl"
        )
        event = json.loads(ledger.read_text().splitlines()[-1])
        self.assertEqual(event["token_observation"], "unavailable")
        self.assertEqual(event["token_observation_source"], "unavailable")
        self.assertNotIn("weighted_tokens", event)

    def test_controller_review_rejects_contradictory_token_source(self) -> None:
        with self.assertRaisesRegex(
            gate.ControllerGateError, "token observation source does not match"
        ):
            gate._controller_review(
                [
                    {
                        "event_type": "leaf_result_recorded",
                        "outcome": "accepted",
                        "route_assessment": "correct",
                        "quality_verdict": "pass",
                        "integration_accepted": True,
                        "token_observation": "exact",
                        "token_observation_source": "unavailable",
                        "weighted_tokens": 32,
                        "cost_proxy": 1.28,
                        "planned_launch": {
                            "model": "gpt-5.6-luna",
                            "reasoning_effort": "high",
                        },
                    }
                ]
            )

    def test_invalid_controller_command_reports_the_current_exact_flag_form(self) -> None:
        self.activate()
        decision = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest="3" * 64,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        gate.handle_hook(
            self.tool_payload(
                "collaborationspawn_agent",
                {
                    "task_name": decision["planned_launch"]["task_name"],
                    "message": "gAAAAABopaque-native-hook-message",
                    "agent_type": "adaptive-luna-maker-high",
                    "reasoning_effort": "high",
                    "fork_turns": "none",
                },
            ),
            runtime_home=self.runtime_home,
        )
        invalid = (
            f"{shlex.quote(sys.executable)} "
            f"{shlex.quote(str(Path(gate.__file__).resolve()))} result "
            f"--session-id {self.session_id} "
            f"--workspace {shlex.quote(str(self.cwd))} "
            "--outcome accepted --route-assessment correct --quality-verdict pass "
            "--integration-acceptance true --token-observation unavailable "
            "--evidence-ref local/checker.json"
        )

        output = gate.handle_hook(
            self.tool_payload("Bash", {"command": invalid}),
            runtime_home=self.runtime_home,
        )

        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("--integration-accepted", reason)
        self.assertIn("--evidence-ref", reason)
        self.assertIn("accepted|failed|path_blocked", reason)

    def test_objective_lock_digest_is_immutable_across_leaf_retries(self) -> None:
        self.activate()
        digest = "7" * 64
        decision = gate.record_decision(
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
                    "task_name": decision["planned_launch"]["task_name"],
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
        self.assertNotEqual(
            retry["planned_launch"]["task_name"],
            decision["planned_launch"]["task_name"],
        )

    def test_failed_leaf_retry_rebinds_child_turn_and_transcript(self) -> None:
        self.activate()
        digest = "6" * 64
        decision = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest=digest,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload(
                    "spawn_agent",
                    {
                        "task_name": decision["planned_launch"]["task_name"],
                        "message": f"OBJECTIVE LOCK: {digest}",
                        "agent_type": "adaptive-luna-maker-high",
                        "reasoning_effort": "high",
                        "fork_turns": "none",
                    },
                ),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        transcript_a = self.child_transcript(decision)
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload(
                    "Bash",
                    {"command": "python3 -m unittest -v test_a.py"},
                    turn_id=self.child_turn_id,
                    transcript_path=str(transcript_a),
                ),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        gate.record_leaf_result(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            outcome="failed",
            route_assessment="correct",
            quality_verdict="fail",
            integration_accepted=False,
            token_observation="unavailable",
            evidence_references=["local/failed-check.json"],
        )

        retry = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest=digest,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertNotEqual(
            retry["planned_launch"]["task_name"],
            decision["planned_launch"]["task_name"],
        )
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload(
                    "spawn_agent",
                    {
                        "task_name": retry["planned_launch"]["task_name"],
                        "message": f"OBJECTIVE LOCK: {digest}",
                        "agent_type": "adaptive-luna-maker-high",
                        "reasoning_effort": "high",
                        "fork_turns": "none",
                    },
                ),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        child_b_turn_id = "55555555-5555-4555-8555-555555555555"
        self.child_transcript(retry, turn_id=child_b_turn_id)
        stale = gate.handle_hook(
            self.tool_payload(
                "Bash",
                {"command": "python3 -m unittest -v test_stale.py"},
                turn_id=self.child_turn_id,
                transcript_path=str(transcript_a),
            ),
            runtime_home=self.runtime_home,
        )
        self.assertEqual(stale["hookSpecificOutput"]["permissionDecision"], "deny")
        transcript_b = self.runtime_home / "sessions" / "child-b.jsonl"
        transcript_a.rename(transcript_b)

        self.assertEqual(
            gate.handle_hook(
                self.tool_payload(
                    "Bash",
                    {"command": "python3 -m unittest -v test_b.py"},
                    turn_id=child_b_turn_id,
                    transcript_path=str(transcript_b),
                ),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        state_path = next(
            (self.runtime_home / "state" / "adaptive-delegation" / "controller").glob(
                "state-*.json"
            )
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["child_turn_id"], child_b_turn_id)
        self.assertEqual(state["child_transcript_path"], str(transcript_b.resolve()))

    def test_path_blocked_leaf_retry_rebinds_child_turn_and_transcript(self) -> None:
        self.activate()
        digest = "8" * 64
        decision = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest=digest,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload(
                    "spawn_agent",
                    {
                        "task_name": decision["planned_launch"]["task_name"],
                        "message": f"OBJECTIVE LOCK: {digest}",
                        "agent_type": "adaptive-luna-maker-high",
                        "reasoning_effort": "high",
                        "fork_turns": "none",
                    },
                ),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        transcript_a = self.child_transcript(decision)
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload(
                    "Bash",
                    {"command": "python3 -m unittest -v test_a.py"},
                    turn_id=self.child_turn_id,
                    transcript_path=str(transcript_a),
                ),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        gate.record_leaf_result(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            outcome="path_blocked",
            route_assessment="inconclusive",
            quality_verdict="inconclusive",
            integration_accepted=False,
            token_observation="unavailable",
            evidence_references=["local/path-blocked.json"],
        )

        retry = gate.record_decision(
            runtime_home=self.runtime_home,
            session_id=self.session_id,
            workspace=self.cwd,
            decision="leaf_required",
            objective_lock_digest=digest,
            agent_type="adaptive-luna-maker-high",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        self.assertNotIn("child_turn_id", retry)
        self.assertNotIn("child_transcript_path", retry)
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload(
                    "spawn_agent",
                    {
                        "task_name": retry["planned_launch"]["task_name"],
                        "message": f"OBJECTIVE LOCK: {digest}",
                        "agent_type": "adaptive-luna-maker-high",
                        "reasoning_effort": "high",
                        "fork_turns": "none",
                    },
                ),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        child_b_turn_id = "66666666-6666-4666-8666-666666666666"
        self.child_transcript(retry, turn_id=child_b_turn_id)
        transcript_b = self.runtime_home / "sessions" / "child-b.jsonl"
        transcript_a.rename(transcript_b)
        self.assertEqual(
            gate.handle_hook(
                self.tool_payload(
                    "Bash",
                    {"command": "python3 -m unittest -v test_b.py"},
                    turn_id=child_b_turn_id,
                    transcript_path=str(transcript_b),
                ),
                runtime_home=self.runtime_home,
            ),
            {},
        )
        state_path = next(
            (self.runtime_home / "state" / "adaptive-delegation" / "controller").glob(
                "state-*.json"
            )
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["child_turn_id"], child_b_turn_id)
        self.assertEqual(state["child_transcript_path"], str(transcript_b.resolve()))

    def test_leaf_decision_denies_spawn_effort_mismatch(self) -> None:
        self.activate()
        decision = gate.record_decision(
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
                    "task_name": decision["planned_launch"]["task_name"],
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
