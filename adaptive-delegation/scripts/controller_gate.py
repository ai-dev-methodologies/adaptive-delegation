#!/usr/bin/env python3
"""Enforce controller-only tool use for explicit adaptive-delegation sessions."""

from __future__ import annotations

import argparse
import datetime as _datetime
import fcntl
import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any


STATE_SCHEMA_VERSION = "1"
EVENT_SCHEMA_VERSION = "1"
MAX_INPUT_BYTES = 1024 * 1024
MAX_TRANSCRIPT_BINDING_BYTES = 256 * 1024
MAX_TRANSCRIPT_BINDING_LINES = 8
MAX_TRANSCRIPT_USAGE_BYTES = 64 * 1024 * 1024
MAX_TRANSCRIPT_USAGE_LINE_BYTES = 4 * 1024 * 1024
MAX_TOKEN_COUNT = 1_000_000_000_000
MAX_EVIDENCE_REFERENCES = 8
MAX_EVIDENCE_REFERENCE_LENGTH = 256
EXPLICIT_INVOCATION = re.compile(r"^\s*\$adaptive-delegation(?:\s|:|$)", re.I)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_AGENT_TYPE = re.compile(r"^adaptive-[a-z0-9-]+$")
SAFE_EVIDENCE_REFERENCE = re.compile(
    r"^(?!.*[?#@:])(?!.*://)(?!.*(?:/|\\){2})"
    r"(?:[A-Za-z0-9][A-Za-z0-9._/\\+ ~-]*|/[A-Za-z0-9][A-Za-z0-9._/\\+ ~-]*)$"
)
MAIN_ONLY_REASONS = {
    "non_delegable_authority",
    "weak_oracle",
    "high_risk_or_ambiguous",
}
DECISIONS = {"leaf_required", "main_only_exception", "takeover"}
LEAF_OUTCOMES = {"accepted", "failed", "path_blocked"}
ROUTE_ASSESSMENTS = {"correct", "too-cheap", "too-premium", "inconclusive"}
QUALITY_VERDICTS = {"pass", "fail", "inconclusive"}
TOKEN_OBSERVATIONS = {"exact", "estimated", "unavailable"}
TERMINAL_STATUSES = {"complete", "blocked"}
CONTROL_PLANE_TOOLS = {
    "functions.request_user_input",
    "request_user_input",
    "functions.update_plan",
    "update_plan",
    "collaboration.list_agents",
    "collaboration.wait_agent",
    "collaboration.send_message",
    "collaboration.followup_task",
    "collaboration.interrupt_agent",
}
MAIN_EFFORTS = {"high", "xhigh", "max", "ultra"}
CONTROLLER_EXEC_TOOLS = {"Bash", "exec_command", "functions.exec_command"}
SPAWN_TOOLS = {
    "Task",
    "task",
    "spawn_agent",
    "collaboration.spawn_agent",
    "multi_agent_v1.spawn_agent",
}
SKILL_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = SKILL_ROOT / "config" / "model-routing.defaults.json"
MAX_PREFLIGHT_FILE_BYTES = 512 * 1024


class ControllerGateError(RuntimeError):
    """A fail-closed controller state or transition error."""


def _runtime_home(value: Path | None = None) -> Path:
    if value is not None:
        return value.expanduser().resolve()
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser().resolve() if configured else (Path.home() / ".codex").resolve()


def _controller_dir(runtime_home: Path) -> Path:
    return runtime_home / "state" / "adaptive-delegation" / "controller"


def _canonical_workspace(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ControllerGateError("controller workspace must be an existing directory")
    return path


def _state_key(session_id: str, workspace: Path) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ControllerGateError("controller session_id is required")
    material = f"{session_id.strip()}\0{workspace}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _state_path(runtime_home: Path, session_id: str, workspace: Path) -> Path:
    return _controller_dir(runtime_home) / f"state-{_state_key(session_id, workspace)}.json"


def _ensure_private_directory(path: Path) -> None:
    if os.path.lexists(path) and path.is_symlink():
        raise ControllerGateError("controller state directory must not be a symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise ControllerGateError("controller state path is not a directory")
    path.chmod(0o700)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _timestamp() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _launch_task_name(
    *,
    activation_id: str,
    objective_lock_digest: str,
    timestamp: str,
    agent_type: str,
    model: str,
    reasoning_effort: str,
) -> str:
    material = _canonical_json(
        {
            "activation_id": activation_id,
            "agent_type": agent_type,
            "model": model,
            "objective_lock_digest": objective_lock_digest,
            "reasoning_effort": reasoning_effort,
            "timestamp": timestamp,
        }
    ).encode("utf-8")
    return f"adaptive_{hashlib.sha256(material).hexdigest()}"


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    _ensure_private_directory(path.parent)
    if os.path.lexists(path) and path.is_symlink():
        raise ControllerGateError("controller state file must not be a symlink")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        payload = (_canonical_json(value) + "\n").encode("utf-8")
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def _append_event(runtime_home: Path, event: dict[str, Any]) -> None:
    directory = _controller_dir(runtime_home)
    _ensure_private_directory(directory)
    ledger = directory / "controller-events.jsonl"
    if os.path.lexists(ledger) and ledger.is_symlink():
        raise ControllerGateError("controller event ledger must not be a symlink")
    descriptor = os.open(
        ledger,
        os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        os.write(descriptor, (_canonical_json(event) + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _payload_string(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _hook_event(payload: dict[str, Any]) -> str:
    return _payload_string(
        payload,
        "hook_event_name",
        "hookEventName",
        "event",
        "name",
    )


def _workspace_from_payload(payload: dict[str, Any]) -> Path:
    value = _payload_string(payload, "cwd", "working_directory", "workingDirectory")
    if not value:
        raise ControllerGateError("hook payload is missing cwd")
    return _canonical_workspace(value)


def _session_from_payload(payload: dict[str, Any]) -> str:
    value = _payload_string(payload, "session_id", "sessionId")
    if not value:
        raise ControllerGateError("hook payload is missing session_id")
    return value


def _prompt_from_payload(payload: dict[str, Any]) -> str:
    return _payload_string(payload, "prompt", "user_prompt", "userPrompt")


def _activation_event(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_type": "explicit_activation",
        "timestamp": state["activated_at"],
        "activation_id": state["activation_id"],
        "session_id": state["session_id"],
        "workspace": state["workspace"],
        "phase": state["phase"],
        "main_model": state["main_model"],
        "main_reasoning_effort": state["main_reasoning_effort"],
    }


def _activate(payload: dict[str, Any], runtime_home: Path) -> bool:
    session_id = _session_from_payload(payload)
    workspace = _workspace_from_payload(payload)
    main_turn_id = _payload_string(payload, "turn_id", "turnId")
    main_model = _payload_string(payload, "model", "main_model", "mainModel")
    main_effort = _payload_string(
        payload,
        "reasoning_effort",
        "model_reasoning_effort",
        "main_reasoning_effort",
        "reasoningEffort",
    )
    if main_effort and not main_model:
        raise ControllerGateError("main authority declaration is incomplete")
    if main_model and main_model != "gpt-5.6-sol":
        raise ControllerGateError(
            "main authority must be gpt-5.6-sol with reasoning_effort >= high"
        )
    if main_effort and main_effort not in MAIN_EFFORTS:
        raise ControllerGateError(
            "main authority must be gpt-5.6-sol with reasoning_effort >= high"
        )
    existing = _load_state(runtime_home, session_id, workspace)
    if existing is not None and existing.get("phase") != "closed":
        if main_turn_id and existing.get("main_turn_id") != main_turn_id:
            existing = dict(existing)
            existing["main_turn_id"] = main_turn_id
            existing["updated_at"] = _timestamp()
            _atomic_write_json(
                _state_path(runtime_home, session_id, workspace), existing
            )
        if existing.get("phase") == "awaiting_main_declaration":
            return False
        if (
            existing.get("main_model") == "gpt-5.6-sol"
            and existing.get("main_reasoning_effort") in MAIN_EFFORTS
        ):
            return True
        raise ControllerGateError("open controller state lacks valid main authority")
    declared = bool(main_model and main_effort)
    activated_at = _timestamp()
    activation_id = hashlib.sha256(
        f"{session_id}\0{workspace}\0{activated_at}".encode("utf-8")
    ).hexdigest()
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "activation_id": activation_id,
        "session_id": session_id,
        "workspace": str(workspace),
        "phase": "explicit_active" if declared else "awaiting_main_declaration",
        "activated_at": activated_at,
        "updated_at": activated_at,
    }
    if declared:
        state["main_model"] = main_model
        state["main_reasoning_effort"] = main_effort
    if main_turn_id:
        state["main_turn_id"] = main_turn_id
    _atomic_write_json(_state_path(runtime_home, session_id, workspace), state)
    if declared:
        _append_event(runtime_home, _activation_event(state))
    else:
        _append_event(
            runtime_home,
            {
                "schema_version": EVENT_SCHEMA_VERSION,
                "event_type": "explicit_activation_requested",
                "timestamp": activated_at,
                "activation_id": activation_id,
                "session_id": session_id,
                "workspace": str(workspace),
                "phase": state["phase"],
            },
        )
    return declared


def _load_state(runtime_home: Path, session_id: str, workspace: Path) -> dict[str, Any] | None:
    path = _state_path(runtime_home, session_id, workspace)
    if not os.path.lexists(path):
        return None
    if path.is_symlink() or not path.is_file():
        raise ControllerGateError("controller state file is unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControllerGateError("controller state file is invalid") from exc
    if not isinstance(value, dict) or value.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ControllerGateError("controller state schema is unsupported")
    if value.get("session_id") != session_id or value.get("workspace") != str(workspace):
        raise ControllerGateError("controller state binding does not match hook scope")
    return value


def _refresh_main_turn(payload: dict[str, Any], runtime_home: Path) -> None:
    main_turn_id = _payload_string(payload, "turn_id", "turnId")
    if not main_turn_id:
        return
    session_id = _session_from_payload(payload)
    workspace = _workspace_from_payload(payload)
    state = _load_state(runtime_home, session_id, workspace)
    if (
        state is None
        or state.get("phase") == "closed"
        or state.get("main_turn_id") == main_turn_id
    ):
        return
    updated = dict(state)
    updated["main_turn_id"] = main_turn_id
    updated["updated_at"] = _timestamp()
    _atomic_write_json(_state_path(runtime_home, session_id, workspace), updated)


def _evidence_references(values: list[str] | None) -> list[str]:
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_EVIDENCE_REFERENCES:
        raise ControllerGateError("main-only exception requires bounded evidence references")
    if len(values) != len(set(values)):
        raise ControllerGateError("evidence references must be unique")
    for value in values:
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= MAX_EVIDENCE_REFERENCE_LENGTH
            or SAFE_EVIDENCE_REFERENCE.fullmatch(value) is None
        ):
            raise ControllerGateError("main-only exception evidence reference is invalid")
    return values


def _role_binding(
    agent_type: str, *, policy: dict[str, Any] | None = None
) -> dict[str, Any]:
    if SAFE_AGENT_TYPE.fullmatch(agent_type) is None:
        raise ControllerGateError("leaf decision requires a safe adaptive agent_type")
    if policy is None:
        policy = _routing_policy()
    bindings = policy.get("role_bindings") if isinstance(policy, dict) else None
    binding = bindings.get(agent_type) if isinstance(bindings, dict) else None
    if not isinstance(binding, dict):
        raise ControllerGateError("leaf decision agent_type is not package-declared")
    return binding


def _bounded_regular_file(path: Path, *, label: str) -> str:
    try:
        if path.is_symlink() or not path.is_file():
            raise ControllerGateError(f"{label} is unavailable")
        if path.stat().st_size > MAX_PREFLIGHT_FILE_BYTES:
            raise ControllerGateError(f"{label} exceeds the preflight bound")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ControllerGateError(f"{label} is unavailable") from exc


def _routing_policy() -> dict[str, Any]:
    content = _bounded_regular_file(POLICY_PATH, label="installed routing policy")
    try:
        policy = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ControllerGateError("installed routing policy is invalid") from exc
    if not isinstance(policy, dict):
        raise ControllerGateError("installed routing policy is invalid")
    return policy


def _lifecycle_command_templates(
    *,
    session_id: str,
    workspace: Path,
    agent_type: str,
    binding: dict[str, Any],
) -> dict[str, str]:
    prefix = [sys.executable, str(Path(__file__).resolve())]
    scope = ["--session-id", session_id, "--workspace", str(workspace)]
    evidence = "LOCAL_EVIDENCE_REF"

    def command(name: str, *arguments: str) -> str:
        return shlex.join([*prefix, name, *scope, *arguments])

    return {
        "decision_leaf_required": command(
            "decision",
            "--decision",
            "leaf_required",
            "--objective-lock-digest",
            "OBJECTIVE_LOCK_SHA256",
            "--agent-type",
            agent_type,
            "--model",
            str(binding["model"]),
            "--reasoning-effort",
            str(binding["reasoning_effort"]),
        ),
        "result_accepted": command(
            "result",
            "--outcome",
            "accepted",
            "--route-assessment",
            "correct",
            "--quality-verdict",
            "pass",
            "--integration-accepted",
            "true",
            "--token-observation",
            "unavailable",
            "--evidence-ref",
            evidence,
        ),
        "result_failed": command(
            "result",
            "--outcome",
            "failed",
            "--route-assessment",
            "ROUTE_ASSESSMENT",
            "--quality-verdict",
            "fail",
            "--integration-accepted",
            "false",
            "--token-observation",
            "unavailable",
            "--evidence-ref",
            evidence,
        ),
        "result_path_blocked": command(
            "result",
            "--outcome",
            "path_blocked",
            "--route-assessment",
            "inconclusive",
            "--quality-verdict",
            "inconclusive",
            "--integration-accepted",
            "false",
            "--token-observation",
            "unavailable",
            "--evidence-ref",
            evidence,
        ),
        "close_complete": command(
            "close",
            "--terminal-status",
            "complete",
            "--evidence-ref",
            evidence,
        ),
        "close_blocked": command(
            "close",
            "--terminal-status",
            "blocked",
            "--evidence-ref",
            evidence,
        ),
    }


def read_controller_preflight(
    *,
    runtime_home: Path | None,
    session_id: str,
    workspace: str | Path,
    surface: str,
    agent_type: str | None,
) -> dict[str, Any]:
    resolved_home = _runtime_home(runtime_home)
    resolved_workspace = _canonical_workspace(workspace)
    state = _load_state(resolved_home, session_id, resolved_workspace)
    if state is None or state.get("phase") == "closed":
        raise ControllerGateError("controller preflight requires an open activation")
    if surface == "skill":
        if agent_type is not None:
            raise ControllerGateError("skill preflight does not accept an agent_type")
        return {
            "surface": "skill",
            "content": _bounded_regular_file(
                SKILL_ROOT / "SKILL.md", label="installed adaptive skill"
            ),
        }
    if surface != "route":
        raise ControllerGateError("controller preflight surface is invalid")
    if state.get("phase") not in {"explicit_active", "leaf_result_recorded"}:
        raise ControllerGateError("route preflight requires declared main authority")
    if not isinstance(agent_type, str):
        raise ControllerGateError("route preflight requires an agent_type")
    policy = _routing_policy()
    binding = _role_binding(agent_type, policy=policy)
    task_defaults = policy.get("task_defaults")
    if not isinstance(task_defaults, dict):
        raise ControllerGateError("installed routing defaults are unavailable")
    agents_root = resolved_home / "agents"
    role_path = agents_root / f"{agent_type}.toml"
    try:
        if agents_root.is_symlink():
            raise ControllerGateError("installed role binding is unavailable")
        resolved_role = role_path.resolve(strict=True)
        resolved_role.relative_to(agents_root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ControllerGateError("installed role binding is unavailable") from exc
    if role_path.is_symlink():
        raise ControllerGateError("installed role binding is unavailable")
    role_toml = _bounded_regular_file(resolved_role, label="installed role binding")
    try:
        role = tomllib.loads(role_toml)
    except tomllib.TOMLDecodeError as exc:
        raise ControllerGateError("installed role binding is invalid") from exc
    if (
        role.get("name") != agent_type
        or role.get("model") != binding.get("model")
        or role.get("model_reasoning_effort") != binding.get("reasoning_effort")
    ):
        raise ControllerGateError("installed role binding does not match policy")
    return {
        "surface": "route",
        "task_defaults": task_defaults,
        "agent_type": agent_type,
        "role_binding": binding,
        "role_toml": role_toml,
        "lifecycle_command_templates": _lifecycle_command_templates(
            session_id=session_id,
            workspace=resolved_workspace,
            agent_type=agent_type,
            binding=binding,
        ),
        "lifecycle_allowed_values": {
            "outcome": sorted(LEAF_OUTCOMES),
            "route_assessment": sorted(ROUTE_ASSESSMENTS),
            "quality_verdict": sorted(QUALITY_VERDICTS),
            "integration_accepted": ["false", "true"],
            "terminal_status": sorted(TERMINAL_STATUSES),
        },
        "evidence_reference_rule": (
            "Use one to eight bounded local paths or stable IDs; exclude ? # @ : "
            "and URI schemes. Replace every uppercase placeholder before execution."
        ),
    }


def record_main_declaration(
    *,
    runtime_home: Path | None,
    session_id: str,
    workspace: str | Path,
    model: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    resolved_home = _runtime_home(runtime_home)
    resolved_workspace = _canonical_workspace(workspace)
    state = _load_state(resolved_home, session_id, resolved_workspace)
    if state is None or state.get("phase") != "awaiting_main_declaration":
        raise ControllerGateError("main authority declaration is not pending")
    if model != "gpt-5.6-sol" or reasoning_effort not in MAIN_EFFORTS:
        raise ControllerGateError(
            "main authority must be gpt-5.6-sol with reasoning_effort >= high"
        )
    timestamp = _timestamp()
    updated = dict(state)
    updated.update(
        {
            "phase": "explicit_active",
            "main_model": model,
            "main_reasoning_effort": reasoning_effort,
            "updated_at": timestamp,
        }
    )
    _atomic_write_json(
        _state_path(resolved_home, session_id, resolved_workspace), updated
    )
    event = _activation_event(updated)
    event["timestamp"] = timestamp
    _append_event(resolved_home, event)
    return updated


def _controller_events(runtime_home: Path) -> list[dict[str, Any]]:
    ledger = _controller_dir(runtime_home) / "controller-events.jsonl"
    if ledger.is_symlink() or not ledger.is_file():
        raise ControllerGateError("controller event ledger is unavailable")
    if ledger.stat().st_size > 64 * 1024 * 1024:
        raise ControllerGateError("controller event ledger exceeds review bound")
    events: list[dict[str, Any]] = []
    try:
        for line in ledger.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ControllerGateError("controller event ledger row is invalid")
            events.append(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControllerGateError("controller event ledger is invalid") from exc
    return events


def _controller_observation_source(event: dict[str, Any]) -> str:
    observation = event.get("token_observation")
    source = event.get("token_observation_source")
    if source is None:
        if observation == "unavailable":
            return "unavailable"
        if observation in {"exact", "estimated"}:
            return "legacy_unspecified"
    valid_sources = {
        "unavailable": {"unavailable"},
        "estimated": {"main_reported"},
        "exact": {"main_reported", "bound_child_transcript"},
    }
    if (
        not isinstance(source, str)
        or source not in valid_sources.get(observation, set())
    ):
        raise ControllerGateError("token observation source does not match observation")
    return source


def _controller_review(events: list[dict[str, Any]]) -> dict[str, Any]:
    results = [event for event in events if event.get("event_type") == "leaf_result_recorded"]
    assessment_counts = {
        "appropriate": 0,
        "underpowered": 0,
        "overpowered": 0,
        "inconclusive": 0,
    }
    assessment_names = {
        "correct": "appropriate",
        "too-cheap": "underpowered",
        "too-premium": "overpowered",
        "inconclusive": "inconclusive",
    }
    outcomes = {value: 0 for value in sorted(LEAF_OUTCOMES)}
    verdicts = {value: 0 for value in sorted(QUALITY_VERDICTS)}
    routes: dict[str, int] = {}
    observed = 0
    weighted_tokens = 0
    cost_by_route: dict[str, float] = {}
    observation_sources: dict[str, int] = {}
    integration_accepted = 0
    for event in results:
        assessment = assessment_names.get(event.get("route_assessment"), "inconclusive")
        assessment_counts[assessment] += 1
        outcome = event.get("outcome")
        if outcome in outcomes:
            outcomes[outcome] += 1
        verdict = event.get("quality_verdict")
        if verdict in verdicts:
            verdicts[verdict] += 1
        integration_accepted += int(event.get("integration_accepted") is True)
        planned = event.get("planned_launch")
        if isinstance(planned, dict):
            route = f"{planned.get('model', 'unknown')}/{planned.get('reasoning_effort', 'unknown')}"
            routes[route] = routes.get(route, 0) + 1
        else:
            route = "unknown/unknown"
        if event.get("token_observation") != "unavailable":
            observed += 1
            weighted_tokens += int(event.get("weighted_tokens", 0))
            cost_by_route[route] = round(
                cost_by_route.get(route, 0.0) + float(event.get("cost_proxy", 0.0)),
                6,
            )
        source = _controller_observation_source(event)
        observation_sources[source] = observation_sources.get(source, 0) + 1
    total = len(results)
    conclusive = (
        assessment_counts["appropriate"]
        + assessment_counts["underpowered"]
        + assessment_counts["overpowered"]
    )
    try:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        sample_threshold = policy["audit"]["review_every_accepted_attempts"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ControllerGateError("controller review policy is unavailable") from exc
    if (
        not isinstance(sample_threshold, int)
        or isinstance(sample_threshold, bool)
        or not 1 <= sample_threshold <= 10000
    ):
        raise ControllerGateError("controller review sample threshold is invalid")
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "generated_at": _timestamp(),
        "snapshot_kind": "cumulative",
        "trigger_reasons": ["leaf-result"],
        "covered_leaf_results": total,
        "model_selection": {
            "status": (
                "evaluated"
                if conclusive >= sample_threshold
                else "insufficient_sample"
            ),
            "minimum_conclusive_results": sample_threshold,
            "conclusive_results": conclusive,
            **assessment_counts,
        },
        "routes": dict(sorted(routes.items())),
        "cost": {
            "status": (
                "unavailable"
                if observed == 0
                else "observed"
                if observed == total
                else "partial"
            ),
            "observed_results": observed,
            "unobserved_results": total - observed,
            "weighted_tokens_observed": weighted_tokens if observed else None,
            "cost_proxy_observed_by_model_effort": dict(sorted(cost_by_route.items())),
            "observation_sources": dict(sorted(observation_sources.items())),
            "cross_model_cost_comparison": "not_comparable_without_price_table",
        },
        "quality": {
            "status": (
                "sufficient_sample"
                if outcomes["accepted"] >= sample_threshold
                else "insufficient_sample"
            ),
            "minimum_accepted_results": sample_threshold,
            **outcomes,
            "integration_accepted": integration_accepted,
            "verdicts": verdicts,
        },
    }


def _write_controller_review(runtime_home: Path) -> Path:
    review = _controller_review(_controller_events(runtime_home))
    directory = _controller_dir(runtime_home) / "reviews"
    _ensure_private_directory(directory)
    name = _datetime.datetime.now(_datetime.timezone.utc).strftime(
        "controller-review-%Y%m%dT%H%M%S.%fZ.json"
    )
    path = directory / name
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, (_canonical_json(review) + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def record_leaf_result(
    *,
    runtime_home: Path | None,
    session_id: str,
    workspace: str | Path,
    outcome: str,
    route_assessment: str,
    quality_verdict: str,
    integration_accepted: bool,
    token_observation: str,
    evidence_references: list[str] | None,
    weighted_tokens: int | None = None,
    cost_proxy: float | None = None,
) -> dict[str, Any]:
    resolved_home = _runtime_home(runtime_home)
    resolved_workspace = _canonical_workspace(workspace)
    state = _load_state(resolved_home, session_id, resolved_workspace)
    if state is None or state.get("phase") != "leaf_launch_authorized":
        raise ControllerGateError("leaf result requires one authorized leaf launch")
    if outcome not in LEAF_OUTCOMES or route_assessment not in ROUTE_ASSESSMENTS:
        raise ControllerGateError("leaf result outcome or route assessment is invalid")
    if quality_verdict not in QUALITY_VERDICTS or token_observation not in TOKEN_OBSERVATIONS:
        raise ControllerGateError("leaf result quality or token observation is invalid")
    if outcome == "accepted" and (
        quality_verdict != "pass" or integration_accepted is not True
    ):
        raise ControllerGateError("accepted leaf result requires passed integration")
    if outcome != "accepted" and integration_accepted:
        raise ControllerGateError("nonaccepted leaf result cannot be integration accepted")
    references = _evidence_references(evidence_references)
    token_observation_source = "unavailable"
    if token_observation == "unavailable":
        if weighted_tokens is not None or cost_proxy is not None:
            raise ControllerGateError("unavailable token observation cannot carry cost values")
        recovered = _bound_child_token_cost(state, resolved_home)
        if recovered is not None:
            token_observation = "exact"
            token_observation_source = "bound_child_transcript"
            weighted_tokens = recovered["weighted_tokens"]
            cost_proxy = recovered["cost_proxy"]
    elif (
        not isinstance(weighted_tokens, int)
        or isinstance(weighted_tokens, bool)
        or weighted_tokens < 0
        or not isinstance(cost_proxy, (int, float))
        or isinstance(cost_proxy, bool)
        or cost_proxy < 0
    ):
        raise ControllerGateError("observed token result requires nonnegative cost values")
    else:
        token_observation_source = "main_reported"
    timestamp = _timestamp()
    updated = dict(state)
    updated["phase"] = "leaf_result_recorded"
    updated["last_outcome"] = outcome
    updated["last_integration_accepted"] = integration_accepted
    updated["updated_at"] = timestamp
    event = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_type": "leaf_result_recorded",
        "timestamp": timestamp,
        "activation_id": state["activation_id"],
        "session_id": session_id,
        "workspace": str(resolved_workspace),
        "objective_lock_digest": state["objective_lock_digest"],
        "planned_launch": state["planned_launch"],
        "outcome": outcome,
        "route_assessment": route_assessment,
        "quality_verdict": quality_verdict,
        "integration_accepted": integration_accepted,
        "token_observation": token_observation,
        "token_observation_source": token_observation_source,
        "evidence_references": references,
    }
    if token_observation != "unavailable":
        event["weighted_tokens"] = weighted_tokens
        event["cost_proxy"] = round(float(cost_proxy), 6)
    _append_event(resolved_home, event)
    _atomic_write_json(
        _state_path(resolved_home, session_id, resolved_workspace), updated
    )
    _write_controller_review(resolved_home)
    return updated


def close_controller(
    *,
    runtime_home: Path | None,
    session_id: str,
    workspace: str | Path,
    terminal_status: str,
    evidence_references: list[str] | None,
) -> dict[str, Any]:
    resolved_home = _runtime_home(runtime_home)
    resolved_workspace = _canonical_workspace(workspace)
    state = _load_state(resolved_home, session_id, resolved_workspace)
    if state is None or state.get("phase") not in {
        "leaf_result_recorded",
        "main_only_exception",
        "takeover",
    }:
        raise ControllerGateError("controller can close only after terminal evidence")
    if terminal_status not in TERMINAL_STATUSES:
        raise ControllerGateError("controller terminal status is invalid")
    if (
        terminal_status == "complete"
        and state.get("phase") == "leaf_result_recorded"
        and (
            state.get("last_outcome") != "accepted"
            or state.get("last_integration_accepted") is not True
        )
    ):
        raise ControllerGateError("complete requires an accepted integrated leaf result")
    references = _evidence_references(evidence_references)
    timestamp = _timestamp()
    updated = dict(state)
    updated.update(
        {
            "phase": "closed",
            "terminal_status": terminal_status,
            "updated_at": timestamp,
        }
    )
    _append_event(
        resolved_home,
        {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_type": "controller_closed",
            "timestamp": timestamp,
            "activation_id": state["activation_id"],
            "session_id": session_id,
            "workspace": str(resolved_workspace),
            "objective_lock_digest": state.get("objective_lock_digest"),
            "terminal_status": terminal_status,
            "evidence_references": references,
        },
    )
    _atomic_write_json(
        _state_path(resolved_home, session_id, resolved_workspace), updated
    )
    return updated


def record_decision(
    *,
    runtime_home: Path | None,
    session_id: str,
    workspace: str | Path,
    decision: str,
    exception_reason: str | None = None,
    objective_lock_digest: str,
    evidence_references: list[str] | None = None,
    agent_type: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    resolved_home = _runtime_home(runtime_home)
    resolved_workspace = _canonical_workspace(workspace)
    state = _load_state(resolved_home, session_id, resolved_workspace)
    if state is None:
        raise ControllerGateError("explicit controller state is not active")
    current_phase = state.get("phase")
    if current_phase == "awaiting_main_declaration":
        raise ControllerGateError("main authority declaration is still pending")
    if current_phase == "leaf_launch_authorized":
        raise ControllerGateError("leaf result must be recorded before another decision")
    if current_phase not in {"explicit_active", "leaf_result_recorded"}:
        raise ControllerGateError("controller phase does not admit another decision")
    if current_phase == "leaf_result_recorded" and state.get("last_outcome") == "accepted":
        raise ControllerGateError("accepted leaf result must close the controller")
    if decision not in DECISIONS:
        raise ControllerGateError("delegation decision is unsupported")
    if SHA256.fullmatch(objective_lock_digest) is None:
        raise ControllerGateError("delegation decision requires an Objective Lock digest")
    prior_digest = state.get("objective_lock_digest")
    if prior_digest is not None and prior_digest != objective_lock_digest:
        raise ControllerGateError("Objective Lock digest must remain immutable")
    if (
        decision == "takeover"
        or exception_reason in {"weak_oracle", "high_risk_or_ambiguous"}
    ) and state.get("main_reasoning_effort") != "ultra":
        raise ControllerGateError(
            "weak/high-risk main execution or takeover requires declared main ultra"
        )
    references: list[str] = []
    if decision == "main_only_exception":
        if exception_reason not in MAIN_ONLY_REASONS:
            raise ControllerGateError("main-only exception reason is not authorized")
        references = _evidence_references(evidence_references)
        phase = "main_only_exception"
    elif decision == "takeover":
        if exception_reason != "ladder_exhausted":
            raise ControllerGateError("main takeover requires exhausted-ladder evidence")
        references = _evidence_references(evidence_references)
        phase = "takeover"
    else:
        if exception_reason is not None or evidence_references not in (None, []):
            raise ControllerGateError("leaf-required decision must not carry a main-only exception")
        if not all(isinstance(item, str) and item for item in (agent_type, model, reasoning_effort)):
            raise ControllerGateError("leaf-required decision requires exact role/model/effort")
        binding = _role_binding(str(agent_type))
        if binding.get("model") != model or binding.get("reasoning_effort") != reasoning_effort:
            raise ControllerGateError("leaf-required role/model/effort does not match policy")
        phase = "leaf_required"
    timestamp = _timestamp()
    updated = dict(state)
    updated.update(
        {
            "phase": phase,
            "objective_lock_digest": objective_lock_digest,
            "updated_at": timestamp,
        }
    )
    if exception_reason is not None:
        updated["exception_reason"] = exception_reason
        updated["evidence_references"] = references
    if decision == "leaf_required":
        updated["planned_launch"] = {
            "agent_type": agent_type,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "fork_turns": "none",
            "task_name": _launch_task_name(
                activation_id=str(state["activation_id"]),
                objective_lock_digest=objective_lock_digest,
                timestamp=timestamp,
                agent_type=str(agent_type),
                model=str(model),
                reasoning_effort=str(reasoning_effort),
            ),
        }
    _atomic_write_json(_state_path(resolved_home, session_id, resolved_workspace), updated)
    event = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_type": "delegation_decision",
        "timestamp": timestamp,
        "activation_id": updated["activation_id"],
        "session_id": session_id,
        "workspace": str(resolved_workspace),
        "decision": decision,
        "phase": phase,
        "objective_lock_digest": objective_lock_digest,
    }
    if exception_reason is not None:
        event["exception_reason"] = exception_reason
        event["evidence_references"] = references
    if decision == "leaf_required":
        event["planned_launch"] = updated["planned_launch"]
    _append_event(resolved_home, event)
    return updated


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _denied(
    *,
    reason: str,
    tool_name: str,
    state: dict[str, Any],
    runtime_home: Path,
) -> dict[str, Any]:
    _append_event(
        runtime_home,
        {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_type": "main_tool_denied",
            "timestamp": _timestamp(),
            "activation_id": state["activation_id"],
            "session_id": state["session_id"],
            "workspace": state["workspace"],
            "phase": state.get("phase"),
            "tool_name": tool_name or "unknown",
            "reason": reason,
        },
    )
    return _deny(reason)


def _authorized_controller_command(
    payload: dict[str, Any], state: dict[str, Any], workspace: Path
) -> bool:
    tool_input = _spawn_input(payload)
    command = tool_input.get("cmd") or tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return False
    if any(token in command for token in ("$", "`", "\n", "\r", ";", "&", "|", "<", ">")):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if len(tokens) < 5:
        return False
    try:
        interpreter = Path(tokens[0]).expanduser().resolve()
        controller = Path(tokens[1]).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    if interpreter != Path(sys.executable).resolve():
        return False
    if controller != Path(__file__).resolve() or tokens[2] not in {
        "decision",
        "declare-main",
        "preflight",
        "result",
        "close",
    }:
        return False
    allowed_flags = {
        "--session-id",
        "--workspace",
        "--decision",
        "--exception-reason",
        "--objective-lock-digest",
        "--evidence-ref",
        "--agent-type",
        "--model",
        "--reasoning-effort",
        "--surface",
        "--outcome",
        "--route-assessment",
        "--quality-verdict",
        "--integration-accepted",
        "--token-observation",
        "--weighted-tokens",
        "--cost-proxy",
        "--terminal-status",
    }
    values: dict[str, list[str]] = {}
    index = 3
    while index < len(tokens):
        flag = tokens[index]
        if flag not in allowed_flags or index + 1 >= len(tokens):
            return False
        value = tokens[index + 1]
        if value.startswith("--") or flag in values and flag != "--evidence-ref":
            return False
        values.setdefault(flag, []).append(value)
        index += 2
    required = {"--session-id", "--workspace"}
    if tokens[2] == "decision":
        required.update({"--decision", "--objective-lock-digest"})
    elif tokens[2] == "declare-main":
        required.update({"--model", "--reasoning-effort"})
    elif tokens[2] == "preflight":
        required.add("--surface")
    elif tokens[2] == "result":
        required.update(
            {
                "--outcome",
                "--route-assessment",
                "--quality-verdict",
                "--integration-accepted",
                "--token-observation",
                "--evidence-ref",
            }
        )
    else:
        required.update({"--terminal-status", "--evidence-ref"})
    if not required.issubset(values):
        return False
    if values["--session-id"] != [state["session_id"]]:
        return False
    try:
        command_workspace = _canonical_workspace(values["--workspace"][0])
    except ControllerGateError:
        return False
    if command_workspace != workspace:
        return False
    if tokens[2] == "preflight":
        surface = values.get("--surface")
        if surface == ["skill"]:
            return set(values) == {"--session-id", "--workspace", "--surface"}
        if surface == ["route"]:
            return (
                set(values)
                == {"--session-id", "--workspace", "--surface", "--agent-type"}
                and SAFE_AGENT_TYPE.fullmatch(values["--agent-type"][0]) is not None
            )
        return False
    return True


def _resolved_transcript_path(
    payload: dict[str, Any], runtime_home: Path
) -> Path | None:
    value = _payload_string(payload, "transcript_path", "transcriptPath")
    if not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        return None
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to((runtime_home / "sessions").resolve())
    except (OSError, ValueError):
        return None
    if candidate.is_symlink() or not resolved.is_file():
        return None
    return resolved


def _transcript_binds_planned_child(
    *,
    transcript: Path,
    session_id: str,
    turn_id: str,
    planned: dict[str, Any],
) -> bool:
    rows: list[dict[str, Any]] = []
    consumed = 0
    try:
        with transcript.open("r", encoding="utf-8") as handle:
            for _ in range(MAX_TRANSCRIPT_BINDING_LINES):
                line = handle.readline(MAX_TRANSCRIPT_BINDING_BYTES - consumed + 1)
                if not line:
                    break
                consumed += len(line.encode("utf-8"))
                if consumed > MAX_TRANSCRIPT_BINDING_BYTES:
                    return False
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not rows or rows[0].get("type") != "session_meta":
        return False
    metadata = rows[0].get("payload")
    if not isinstance(metadata, dict):
        return False
    source = metadata.get("source")
    subagent = source.get("subagent") if isinstance(source, dict) else None
    spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
    task_name = planned.get("task_name")
    agent_type = planned.get("agent_type")
    if not isinstance(spawn, dict) or not all(
        isinstance(value, str) and value
        for value in (task_name, agent_type)
    ):
        return False
    expected_agent_path = f"/root/{task_name}"
    metadata_matches = (
        metadata.get("session_id") == session_id
        and metadata.get("parent_thread_id") == session_id
        and metadata.get("thread_source") == "subagent"
        and metadata.get("agent_role") == agent_type
        and spawn.get("parent_thread_id") == session_id
        and spawn.get("agent_path") == expected_agent_path
        and spawn.get("agent_role") == agent_type
    )
    task_started = any(
        row.get("type") == "event_msg"
        and isinstance(row.get("payload"), dict)
        and row["payload"].get("type") == "task_started"
        and row["payload"].get("turn_id") == turn_id
        for row in rows[1:]
    )
    return metadata_matches and task_started


def _bound_child_token_cost(
    state: dict[str, Any], runtime_home: Path
) -> dict[str, int | float] | None:
    transcript_value = state.get("child_transcript_path")
    child_turn_id = state.get("child_turn_id")
    planned = state.get("planned_launch")
    if (
        not isinstance(transcript_value, str)
        or not transcript_value
        or not isinstance(child_turn_id, str)
        or not child_turn_id
        or not isinstance(planned, dict)
    ):
        return None
    transcript = Path(transcript_value)
    try:
        if not transcript.is_absolute() or transcript.is_symlink():
            return None
        resolved = transcript.resolve(strict=True)
        resolved.relative_to((runtime_home / "sessions").resolve(strict=True))
        if resolved != transcript or not resolved.is_file():
            return None
        size = resolved.stat().st_size
        if size > MAX_TRANSCRIPT_USAGE_BYTES:
            return None
    except (OSError, ValueError):
        return None
    if not _transcript_binds_planned_child(
        transcript=resolved,
        session_id=str(state.get("session_id", "")),
        turn_id=child_turn_id,
        planned=planned,
    ):
        return None

    latest_usage: tuple[int, int] | None = None
    consumed = 0
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            while True:
                line = handle.readline(MAX_TRANSCRIPT_USAGE_LINE_BYTES + 1)
                if not line:
                    break
                encoded_size = len(line.encode("utf-8"))
                consumed += encoded_size
                if (
                    encoded_size > MAX_TRANSCRIPT_USAGE_LINE_BYTES
                    or consumed > MAX_TRANSCRIPT_USAGE_BYTES
                    or not line.endswith("\n")
                ):
                    return None
                row = json.loads(line)
                if not isinstance(row, dict):
                    return None
                payload = row.get("payload")
                if (
                    row.get("type") != "event_msg"
                    or not isinstance(payload, dict)
                    or payload.get("type") != "token_count"
                ):
                    continue
                info = payload.get("info")
                usage = info.get("total_token_usage") if isinstance(info, dict) else None
                if not isinstance(usage, dict):
                    continue
                input_tokens = usage.get("input_tokens")
                output_tokens = usage.get("output_tokens")
                if not all(
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and 0 <= value <= MAX_TOKEN_COUNT
                    for value in (input_tokens, output_tokens)
                ):
                    return None
                latest_usage = (input_tokens, output_tokens)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if latest_usage is None:
        return None

    model = planned.get("model")
    try:
        policy = _routing_policy()
        price = policy.get("price_evidence")
        fractions = (
            price.get("sol_equivalent_price_fraction")
            if isinstance(price, dict)
            else None
        )
        fraction = fractions.get(model) if isinstance(fractions, dict) else None
        if (
            not isinstance(fraction, (int, float))
            or isinstance(fraction, bool)
            or not 0 <= float(fraction) <= 1
        ):
            return None
    except ControllerGateError:
        return None
    input_tokens, output_tokens = latest_usage
    weighted_tokens = (input_tokens + 3) // 4 + output_tokens
    return {
        "weighted_tokens": weighted_tokens,
        "cost_proxy": round(weighted_tokens * float(fraction), 6),
    }


def _controller_command_attempt(payload: dict[str, Any]) -> str | None:
    tool_input = _spawn_input(payload)
    command = tool_input.get("cmd") or tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    try:
        tokens = shlex.split(command)
        controller = Path(tokens[1]).expanduser().resolve()
    except (IndexError, OSError, RuntimeError, ValueError):
        return None
    if controller != Path(__file__).resolve() or len(tokens) < 3:
        return None
    controller_commands = {"decision", "declare-main", "preflight", "result", "close"}
    return tokens[2] if tokens[2] in controller_commands else None


def _controller_command_correction(
    command_name: str, state: dict[str, Any], workspace: Path
) -> str:
    prefix = shlex.join(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            command_name,
            "--session-id",
            state["session_id"],
            "--workspace",
            str(workspace),
        ]
    )
    forms = {
        "decision": (
            "--decision <leaf_required|main_only_exception|takeover> "
            "--objective-lock-digest <64-lowercase-hex> followed by the exact "
            "role flags or evidence-backed exception flags"
        ),
        "declare-main": "--model gpt-5.6-sol --reasoning-effort <high|xhigh|max|ultra>",
        "preflight": "--surface <skill|route> and --agent-type <role> only for route",
        "result": (
            "--outcome <accepted|failed|path_blocked> "
            "--route-assessment <correct|too-cheap|too-premium|inconclusive> "
            "--quality-verdict <pass|fail|inconclusive> "
            "--integration-accepted <true|false> --token-observation unavailable "
            "--evidence-ref <local-safe-ref>"
        ),
        "close": (
            "--terminal-status <complete|blocked> "
            "--evidence-ref <local-safe-ref>"
        ),
    }
    return (
        f"Adaptive Delegation rejected an invalid controller {command_name} command. "
        f"Use this exact flag form: {prefix} {forms[command_name]}. "
        "Evidence references must exclude ? # @ : and URI schemes."
    )


def _adaptive_child(
    payload: dict[str, Any],
    main_session_id: str,
    state: dict[str, Any],
    runtime_home: Path,
    state_path: Path,
) -> bool:
    if state.get("phase") != "leaf_launch_authorized":
        return False
    turn_id = _payload_string(payload, "turn_id", "turnId")
    main_turn_id = state.get("main_turn_id")
    if turn_id and isinstance(main_turn_id, str):
        if turn_id == main_turn_id:
            return False
        transcript = _resolved_transcript_path(payload, runtime_home)
        if transcript is None:
            return False
        child_turn_id = state.get("child_turn_id")
        child_transcript_path = state.get("child_transcript_path")
        if isinstance(child_turn_id, str) or isinstance(child_transcript_path, str):
            return (
                turn_id == child_turn_id
                and str(transcript) == child_transcript_path
            )
        planned = state.get("planned_launch")
        if not isinstance(planned, dict) or not _transcript_binds_planned_child(
            transcript=transcript,
            session_id=main_session_id,
            turn_id=turn_id,
            planned=planned,
        ):
            return False
        updated = dict(state)
        updated["child_turn_id"] = turn_id
        updated["child_transcript_path"] = str(transcript)
        updated["updated_at"] = _timestamp()
        _atomic_write_json(state_path, updated)
        return True
    role = _payload_string(payload, "agent_type", "agent_role", "agentType", "agentRole")
    parent = _payload_string(payload, "parent_session_id", "parentSessionId")
    return role.startswith("adaptive-") and parent == main_session_id


def _spawn_input(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("tool_input")
    if not isinstance(value, dict):
        value = payload.get("toolInput")
    return value if isinstance(value, dict) else {}


def _tool_matches(tool_name: str, allowed: set[str]) -> bool:
    return tool_name in allowed or tool_name in {
        candidate.replace(".", "") for candidate in allowed
    }


def _authorize_spawn(
    payload: dict[str, Any],
    state: dict[str, Any],
    runtime_home: Path,
    state_path: Path,
) -> dict[str, Any]:
    planned = state.get("planned_launch")
    launch = _spawn_input(payload)
    if not isinstance(planned, dict):
        return _deny("Adaptive Delegation launch envelope is missing from controller state.")
    exact = (
        launch.get("agent_type") == planned.get("agent_type")
        and launch.get("reasoning_effort") == planned.get("reasoning_effort")
        and launch.get("fork_turns") == "none"
        and launch.get("task_name") == planned.get("task_name")
        and (
            launch.get("model") is None
            or launch.get("model") == planned.get("model")
        )
    )
    if not exact:
        return _deny(
            "Adaptive Delegation launch envelope does not match the locked "
            "task/role/model/effort."
        )
    message = launch.get("message")
    digest = state.get("objective_lock_digest")
    if not isinstance(message, str) or not message or not isinstance(digest, str):
        return _deny("Adaptive Delegation launch envelope is missing its required child message.")
    timestamp = _timestamp()
    updated = dict(state)
    updated["phase"] = "leaf_launch_authorized"
    updated["updated_at"] = timestamp
    _atomic_write_json(state_path, updated)
    _append_event(
        runtime_home,
        {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_type": "leaf_launch_authorized",
            "timestamp": timestamp,
            "activation_id": state["activation_id"],
            "session_id": state["session_id"],
            "workspace": state["workspace"],
            "objective_lock_digest": digest,
            "planned_launch": planned,
        },
    )
    return {}


def _handle_pre_tool_use(payload: dict[str, Any], runtime_home: Path) -> dict[str, Any]:
    session_id = _session_from_payload(payload)
    workspace = _workspace_from_payload(payload)
    state_path = _state_path(runtime_home, session_id, workspace)
    state = _load_state(runtime_home, session_id, workspace)
    if state is None:
        return {}
    phase = state.get("phase")
    if phase == "closed":
        return {}
    tool_name = _payload_string(payload, "tool_name", "toolName")
    if phase in {"main_only_exception", "takeover"}:
        if _tool_matches(tool_name, SPAWN_TOOLS):
            return _denied(
                reason=(
                    "Adaptive Delegation main-only execution does not authorize an "
                    "unlocked child launch."
                ),
                tool_name=tool_name,
                state=state,
                runtime_home=runtime_home,
            )
        return {}
    if _tool_matches(tool_name, SPAWN_TOOLS):
        if phase == "leaf_required":
            result = _authorize_spawn(payload, state, runtime_home, state_path)
            if not result:
                return result
            reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        else:
            reason = (
                "Adaptive Delegation child launch requires a pending locked "
                "leaf decision."
            )
        return _denied(
            reason=reason,
            tool_name=tool_name,
            state=state,
            runtime_home=runtime_home,
        )
    if _adaptive_child(payload, session_id, state, runtime_home, state_path):
        return {}
    if _tool_matches(tool_name, CONTROL_PLANE_TOOLS):
        return {}
    if (
        _tool_matches(tool_name, CONTROLLER_EXEC_TOOLS)
        and _authorized_controller_command(payload, state, workspace)
    ):
        return {}
    if _tool_matches(tool_name, CONTROLLER_EXEC_TOOLS):
        command_name = _controller_command_attempt(payload)
        if command_name is not None:
            return _denied(
                reason=_controller_command_correction(command_name, state, workspace),
                tool_name=tool_name,
                state=state,
                runtime_home=runtime_home,
            )
    return _denied(
        reason=(
            "Adaptive Delegation controller-only enforcement denied main task execution. "
            "Record an Objective-Locked leaf decision and use an admitted adaptive leaf, "
            "or record an evidence-backed authorized main-only exception."
        ),
        tool_name=tool_name,
        state=state,
        runtime_home=runtime_home,
    )


def handle_hook(
    payload: dict[str, Any], *, runtime_home: Path | None = None
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ControllerGateError("hook payload must be an object")
    resolved_home = _runtime_home(runtime_home)
    event = _hook_event(payload)
    if event == "UserPromptSubmit":
        prompt = _prompt_from_payload(payload)
        if EXPLICIT_INVOCATION.search(prompt):
            try:
                activated = _activate(payload, resolved_home)
                skill_command = shlex.join(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "preflight",
                        "--session-id",
                        _session_from_payload(payload),
                        "--workspace",
                        str(_workspace_from_payload(payload)),
                        "--surface",
                        "skill",
                    ]
                )
                if not activated:
                    command = shlex.join(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "declare-main",
                            "--session-id",
                            _session_from_payload(payload),
                            "--workspace",
                            str(_workspace_from_payload(payload)),
                            "--model",
                            "gpt-5.6-sol",
                            "--reasoning-effort",
                            "<high|xhigh|max|ultra>",
                        ]
                    )
                    message = (
                        "Adaptive Delegation is controller-only and is waiting for a "
                        "declared current-session main authority. First load the complete "
                        "installed skill through the bounded controller preflight by running "
                        f"exactly: {skill_command}. Then replace the final "
                        "effort placeholder with the actual current effort and run: "
                        f"{command}. Task tools remain denied until that bounded "
                        "gpt-5.6-sol/high-or-above declaration succeeds."
                    )
                    return {
                        "systemMessage": message,
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": message,
                        },
                    }
                message = (
                    "Adaptive Delegation controller authority is active. Before route "
                    "work, if it is not already loaded for this open activation, load "
                    "the complete installed skill through the bounded "
                    f"controller preflight by running exactly: {skill_command}. "
                    "Do not replace this with a direct shell read."
                )
                return {
                    "systemMessage": message,
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": message,
                    },
                }
            except ControllerGateError:
                model = _payload_string(payload, "model", "main_model", "mainModel") or "unknown"
                effort = _payload_string(
                    payload,
                    "reasoning_effort",
                    "model_reasoning_effort",
                    "main_reasoning_effort",
                    "reasoningEffort",
                ) or "unknown"
                return {
                    "systemMessage": (
                        "Adaptive Delegation blocked: main authority must be gpt-5.6-sol "
                        "with reasoning_effort >= high. "
                        f"Current: {model}/{effort}. No child was launched. Switch the main "
                        "session to gpt-5.6-sol/high or above, then invoke "
                        "$adaptive-delegation again."
                    )
                }
        else:
            try:
                _refresh_main_turn(payload, resolved_home)
            except ControllerGateError as exc:
                return {
                    "continue": False,
                    "stopReason": (
                        "Adaptive Delegation controller turn binding failed closed: "
                        f"{exc}"
                    ),
                }
        return {}
    if event == "PreToolUse":
        try:
            return _handle_pre_tool_use(payload, resolved_home)
        except ControllerGateError as exc:
            return _deny(f"Adaptive Delegation controller state is invalid: {exc}")
    return {}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    decision = subparsers.add_parser("decision")
    decision.add_argument("--session-id", required=True)
    decision.add_argument("--workspace", required=True, type=Path)
    decision.add_argument("--decision", required=True, choices=sorted(DECISIONS))
    decision.add_argument("--exception-reason")
    decision.add_argument("--objective-lock-digest", required=True)
    decision.add_argument("--evidence-ref", action="append", default=[])
    decision.add_argument("--agent-type")
    decision.add_argument("--model")
    decision.add_argument("--reasoning-effort")
    declare = subparsers.add_parser("declare-main")
    declare.add_argument("--session-id", required=True)
    declare.add_argument("--workspace", required=True, type=Path)
    declare.add_argument("--model", required=True)
    declare.add_argument("--reasoning-effort", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--session-id", required=True)
    preflight.add_argument("--workspace", required=True, type=Path)
    preflight.add_argument("--surface", required=True, choices=("skill", "route"))
    preflight.add_argument("--agent-type")
    result = subparsers.add_parser("result")
    result.add_argument("--session-id", required=True)
    result.add_argument("--workspace", required=True, type=Path)
    result.add_argument("--outcome", required=True, choices=sorted(LEAF_OUTCOMES))
    result.add_argument(
        "--route-assessment", required=True, choices=sorted(ROUTE_ASSESSMENTS)
    )
    result.add_argument(
        "--quality-verdict", required=True, choices=sorted(QUALITY_VERDICTS)
    )
    result.add_argument(
        "--integration-accepted", required=True, choices=("true", "false")
    )
    result.add_argument(
        "--token-observation", required=True, choices=sorted(TOKEN_OBSERVATIONS)
    )
    result.add_argument("--weighted-tokens", type=int)
    result.add_argument("--cost-proxy", type=float)
    result.add_argument("--evidence-ref", action="append", default=[])
    close = subparsers.add_parser("close")
    close.add_argument("--session-id", required=True)
    close.add_argument("--workspace", required=True, type=Path)
    close.add_argument(
        "--terminal-status", required=True, choices=sorted(TERMINAL_STATUSES)
    )
    close.add_argument("--evidence-ref", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "decision":
            result = record_decision(
                runtime_home=None,
                session_id=args.session_id,
                workspace=args.workspace,
                decision=args.decision,
                exception_reason=args.exception_reason,
                objective_lock_digest=args.objective_lock_digest,
                evidence_references=args.evidence_ref,
                agent_type=args.agent_type,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
            output: dict[str, Any] = {"phase": result["phase"], "recorded": True}
            if result["phase"] == "leaf_required":
                output["launch_task_name"] = result["planned_launch"]["task_name"]
            print(_canonical_json(output))
            return 0
        if args.command == "declare-main":
            result = record_main_declaration(
                runtime_home=None,
                session_id=args.session_id,
                workspace=args.workspace,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
            print(_canonical_json({"phase": result["phase"], "recorded": True}))
            return 0
        if args.command == "preflight":
            result = read_controller_preflight(
                runtime_home=None,
                session_id=args.session_id,
                workspace=args.workspace,
                surface=args.surface,
                agent_type=args.agent_type,
            )
            if args.surface == "skill":
                ending = "" if result["content"].endswith("\n") else "\n"
                print(result["content"], end=ending)
            else:
                print(_canonical_json(result))
            return 0
        if args.command == "result":
            result = record_leaf_result(
                runtime_home=None,
                session_id=args.session_id,
                workspace=args.workspace,
                outcome=args.outcome,
                route_assessment=args.route_assessment,
                quality_verdict=args.quality_verdict,
                integration_accepted=args.integration_accepted == "true",
                token_observation=args.token_observation,
                evidence_references=args.evidence_ref,
                weighted_tokens=args.weighted_tokens,
                cost_proxy=args.cost_proxy,
            )
            print(_canonical_json({"phase": result["phase"], "recorded": True}))
            return 0
        if args.command == "close":
            result = close_controller(
                runtime_home=None,
                session_id=args.session_id,
                workspace=args.workspace,
                terminal_status=args.terminal_status,
                evidence_references=args.evidence_ref,
            )
            print(_canonical_json({"phase": result["phase"], "recorded": True}))
            return 0
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ControllerGateError("hook payload exceeds size bound")
        payload = json.loads(raw.decode("utf-8")) if raw.strip() else {}
        print(_canonical_json(handle_hook(payload)))
        return 0
    except (ControllerGateError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(_canonical_json(_deny(f"Adaptive Delegation controller gate failed: {exc}")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
