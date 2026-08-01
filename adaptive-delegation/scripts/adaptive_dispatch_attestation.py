#!/usr/bin/env python3
"""Fail-closed, evidence-backed guard for adaptive worker dispatches."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import queue
import re
import secrets
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import tomllib
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
DEFAULT_LEDGER = CODEX_HOME / "state" / "adaptive-delegation" / "dispatch_attestation.jsonl"
AGENT_CONFIG_ROOT = CODEX_HOME / "agents"
ADAPTIVE_SKILL_ROOT = CODEX_HOME / "skills" / "adaptive-delegation"
PACKAGE_ROLE_ROOT = ADAPTIVE_SKILL_ROOT / "roles"
ROUTING_POLICY_CONFIG = (
    ADAPTIVE_SKILL_ROOT / "config" / "model-routing.defaults.json"
)
MODEL_ROUTING_LEDGER = CODEX_HOME / "state" / "model-routing" / "attempts.jsonl"
MODEL_ROUTING_REVIEW_DIR = CODEX_HOME / "state" / "model-routing" / "reviews"
SESSIONS_ROOT = CODEX_HOME / "sessions"
LEAF_RUNTIME_HOME = CODEX_HOME / "leaf-runtime"
MIN_TOKEN_BUDGET = 1_000
PROJECT_DOC_MAX_BYTES = 4_096
TOKEN_MONITOR_POLL_SECONDS = 0.05
CHILD_GROUP_TERM_GRACE_SECONDS = 0.5
ROLLOUT_LINE_MAX_BYTES = 8_000_000
MAX_TOOL_CALLS = 128
MAX_OUTPUT_TOKENS_PER_CALL = 50_000
DEFAULT_EXEC_COMMAND_MAX_OUTPUT_TOKENS = 10_000
MAX_CUMULATIVE_TOOL_OUTPUT_BYTES = 64_000_000
MAX_CHILD_STDOUT_BYTES = 16_000_000
V2_PACKET_VERSION = 2
V2_DELTA_SUMMARY_MAX_CHARS = 1_024
V2_COMMAND_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_VERSION = 1
RECEIPT_MARKER_TYPE = "adaptive_dispatch_receipt"
TERMINAL_EVENT_VERSION = 1
INTEGRATION_CHECKER_AGENT_TYPE = "adaptive-terra-checker-high"
CHILD_ENV_ALLOWLIST = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "COLORTERM",
    "TMPDIR",
    "TMP",
    "TEMP",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
)
V2_ESTIMATE_FIELDS = (
    "tool_calls",
    "max_output_tokens_per_call",
    "cumulative_tool_output_bytes",
    "child_stdout_bytes",
    "weighted_tokens",
)

EXIT_SUCCESS = 0
EXIT_INVALID_PACKET = 20
EXIT_ROUTING_MISMATCH_RECOVERY_FAILURE = 21
EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE = 22
EXIT_UNSAFE_LAUNCH_PATH = 23
EXIT_PROTECTED_COMMAND_FAILURE = 24
EXIT_POLICY_GATE = 25
EXIT_MODEL_ROUTING_AUDIT_FAILURE = 26

REQUIRED_PACKET_FIELDS = (
    "dispatch_id",
    "objective",
    "agent_type",
    "model_tier",
    "reasoning_effort",
    "write_scope",
    "resource_cap",
    "evidence_path",
    "stop_condition",
    "token_budget",
)
TRIPLE_FIELDS = ("agent_type", "model_tier", "reasoning_effort")
DISPATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHELL_EXECUTABLES = {
    "bash",
    "cmd",
    "cmd.exe",
    "dash",
    "fish",
    "ksh",
    "powershell",
    "pwsh",
    "sh",
    "tcsh",
    "zsh",
}
UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
ROLLOUT_PATTERN = re.compile(
    rf"^rollout-(?P<date>\d{{4}}-\d{{2}}-\d{{2}})T\d{{2}}-\d{{2}}-\d{{2}}-(?P<session_id>{UUID_PATTERN})\.jsonl$"
)
SESSION_ID_OUTPUT_PATTERN = re.compile(rf"^session id:\s*(?P<session_id>{UUID_PATTERN})\s*$")
TERMINAL_NONCE_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Outcome:
    kind: str
    child_returncode: int | None = None


@dataclass(frozen=True)
class RecoveryLaunch:
    launch_type: str
    packet: dict[str, Any]
    argv: list[str]
    binding: RoleBinding
    observed_source: dict[str, str]
    runtime_home: Path


@dataclass(frozen=True)
class RoleBinding:
    agent_type: str
    model_tier: str
    model: str
    effort: str
    instructions: str
    role_config: Path


@dataclass(frozen=True)
class RuntimeEvidence:
    session_id: str
    model: str
    effort: str


@dataclass(frozen=True)
class ReceiptEnvelope:
    """A permission-checked local receipt whose contents remain untrusted."""

    value: dict[str, Any]
    path: Path


@dataclass(frozen=True)
class TerminalEvent:
    """Dispatcher-captured completion facts used to finalize integration."""

    value: dict[str, Any]
    digest: str


@dataclass
class AdaptiveAuditContext:
    policy: dict[str, Any]
    routing: dict[str, Any]
    binding: dict[str, str]
    main_model: str
    main_effort: str
    policy_fingerprint: str
    ledger: Path
    review_dir: Path
    attestation_ledger: Path
    started: float
    contract_module: Any
    audit_module: Any


NATIVE_REQUIRED_SCHEMA_FIELDS = (
    "agent_type",
    "reasoning_effort",
    "fork_turns",
)
NATIVE_SELECTION_MODES = (
    "explicit_model_override",
    "verified-fixed-agent-type",
)
NATIVE_GATE_ORDER = (
    "pending_receipt",
    "native_spawn_gate",
    "child_creation_eligibility",
)


def _binding_triple(binding: RoleBinding) -> dict[str, str]:
    return {
        "agent_type": binding.agent_type,
        "model": binding.model,
        "reasoning_effort": binding.effort,
    }


def _schema_fingerprint(schema: Any) -> str | None:
    if not isinstance(schema, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in schema.items()
    ):
        return None
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _role_config_digest(binding: RoleBinding) -> str | None:
    if not _secure_owned_file(binding.role_config, exact_mode=0o600):
        return None
    try:
        with binding.role_config.open("rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None


def _receipt_value(value: Any) -> tuple[dict[str, Any] | None, Path | None]:
    if not isinstance(value, ReceiptEnvelope):
        return None, None
    return value.value, value.path


def _native_structural_admission(
    value: Any,
    binding: RoleBinding,
    *,
    dispatch_id: str,
) -> dict[str, Any]:
    """Reject structurally impossible Native V2 calls before child creation.

    Receipt contents remain untrusted at this stage.  This check deliberately
    establishes only whether the surface *could* support the requested Native
    call; rollout-bound provenance is checked after the runtime verdict and
    immediately before a protected argv can run.
    """
    fallback = "typed_external_worker"
    receipt: dict[str, Any] = {
        "surface_identity": "unknown",
        "schema_fingerprint": None,
        "desired_route": None,
        "explicit_route": None,
        "selection_mode": None,
        "installed_binding": _binding_triple(binding),
        "allowlist": [],
        "gate_order": [],
        "rejection_reason": "invalid_admission_receipt",
        "child_count": 0,
        "child_tokens": 0,
        "selected_fallback": fallback,
        "fallback_scope_fingerprint": None,
        "status": "rejected",
    }
    value, receipt_path = _receipt_value(value)
    if value is None or receipt_path is None:
        return receipt
    surface = value.get("surface_identity")
    schema = value.get("original_callable_schema")
    fingerprint = _schema_fingerprint(schema)
    if isinstance(surface, str) and surface and len(surface) <= 128:
        receipt["surface_identity"] = surface
    receipt["schema_fingerprint"] = fingerprint
    receipt["fallback_scope_fingerprint"] = fingerprint
    for field in ("desired_route", "explicit_route"):
        candidate = value.get(field)
        if isinstance(candidate, str) and candidate in {"native_v2", fallback}:
            receipt[field] = candidate
    if fingerprint is None:
        return receipt
    selection_mode = value.get("selection_mode", "explicit_model_override")
    if selection_mode not in NATIVE_SELECTION_MODES:
        receipt["rejection_reason"] = "native_selection_mode_invalid"
        return receipt
    receipt["selection_mode"] = selection_mode
    required_schema_fields = list(NATIVE_REQUIRED_SCHEMA_FIELDS)
    if selection_mode == "explicit_model_override":
        required_schema_fields.append("model")
    if any(field not in schema for field in required_schema_fields):
        receipt["rejection_reason"] = "original_schema_missing_required_fields"
        return receipt
    if schema["fork_turns"] != "none":
        receipt["rejection_reason"] = "original_schema_fork_turns_not_none"
        return receipt
    if receipt["desired_route"] != "native_v2" or receipt["explicit_route"] != "native_v2":
        receipt["rejection_reason"] = "desired_or_explicit_route_not_native_v2"
        return receipt
    expected_binding = {**_binding_triple(binding), "fork_turns": "none"}
    if value.get("installed_binding") != expected_binding:
        receipt["rejection_reason"] = "installed_role_binding_mismatch"
        return receipt
    if selection_mode == "verified-fixed-agent-type":
        expected_arguments = {
            "agent_type": binding.agent_type,
            "reasoning_effort": binding.effort,
            "fork_turns": "none",
        }
        if value.get("explicit_arguments") != expected_arguments:
            receipt["rejection_reason"] = "fixed_role_arguments_mismatch"
            return receipt
    allowlist = value.get("allowlist")
    if not isinstance(allowlist, list) or _binding_triple(binding) not in allowlist:
        receipt["rejection_reason"] = "exact_role_model_effort_not_allowlisted"
        return receipt
    receipt["allowlist"] = [_binding_triple(binding)]
    events = value.get("gate_events")
    if not isinstance(events, list) or len(events) != len(NATIVE_GATE_ORDER):
        receipt["rejection_reason"] = "gate_order_missing"
        return receipt
    names = [event.get("name") if isinstance(event, dict) else None for event in events]
    ticks = [event.get("monotonic_ns") if isinstance(event, dict) else None for event in events]
    if names != list(NATIVE_GATE_ORDER) or any(
        not isinstance(tick, int) or isinstance(tick, bool) for tick in ticks
    ) or any(left >= right for left, right in zip(ticks, ticks[1:])):
        receipt["rejection_reason"] = "gate_order_or_monotonic_proof_invalid"
        return receipt
    receipt["gate_order"] = list(NATIVE_GATE_ORDER)
    receipt["rejection_reason"] = None
    receipt["child_count"] = None
    receipt["child_tokens"] = None
    receipt["selected_fallback"] = None
    receipt["status"] = "structurally_eligible"
    return receipt


def _native_admission_provenance(
    value: Any,
    receipt: dict[str, Any],
    binding: RoleBinding,
    *,
    dispatch_id: str,
    rollout: Path | None,
    session_id: str | None,
) -> dict[str, Any]:
    """Require a secure, rollout-bound envelope before protected execution."""
    def reject(reason: str) -> dict[str, Any]:
        receipt.update(
            rejection_reason=reason,
            status="rejected",
            child_count=0,
            child_tokens=0,
            selected_fallback="typed_external_worker",
        )
        return receipt

    value, receipt_path = _receipt_value(value)
    if value is None or receipt_path is None:
        return reject("invalid_admission_receipt")
    if value.get("receipt_kind") != "native_admission" or value.get("receipt_version") != RECEIPT_VERSION:
        return reject("receipt_kind_or_version_invalid")
    if value.get("dispatch_id") != dispatch_id:
        return reject("admission_dispatch_id_mismatch")
    issuer = value.get("issuer")
    if not isinstance(issuer, dict) or issuer.get("rollout_session_id") != session_id:
        return reject("trusted_precreation_issuer_missing")
    if issuer.get("role") != _binding_triple(binding) or issuer.get("role_config") != str(binding.role_config):
        return reject("admission_issuer_binding_mismatch")
    role_digest = _role_config_digest(binding)
    if role_digest is None or issuer.get("role_config_digest") != role_digest:
        return reject("admission_role_config_digest_invalid")
    if not _rollout_has_receipt_marker(rollout, session_id, value):
        return reject("trusted_precreation_marker_missing")
    receipt["gate_order"] = list(NATIVE_GATE_ORDER)
    receipt["rejection_reason"] = None
    receipt["child_count"] = None
    receipt["child_tokens"] = None
    receipt["selected_fallback"] = None
    receipt["status"] = "eligible"
    return receipt


def _native_admission(
    value: Any,
    binding: RoleBinding,
    *,
    dispatch_id: str,
    rollout: Path | None,
    session_id: str | None,
    require_provenance: bool = True,
) -> dict[str, Any]:
    """Compatibility wrapper for callers that need the complete gate."""
    receipt = _native_structural_admission(value, binding, dispatch_id=dispatch_id)
    if receipt["status"] != "structurally_eligible" or not require_provenance:
        return receipt
    return _native_admission_provenance(
        value,
        receipt,
        binding,
        dispatch_id=dispatch_id,
        rollout=rollout,
        session_id=session_id,
    )


def _integration_gate(
    value: Any,
    *,
    packet: dict[str, Any],
    binding: RoleBinding,
    runtime: RuntimeEvidence | None,
    expected_session_id: str | None,
    selected_launch_path: str,
    parent_enforced: bool,
    terminal_event: TerminalEvent | None,
    dispatch_id: str | None = None,
) -> dict[str, Any]:
    """Finalize only a receipt bound to a dispatcher-captured terminal event."""
    gate: dict[str, Any] = {
        "status": "blocked",
        "reason": "integration_receipt_missing",
        "selected_launch_path": selected_launch_path,
        "evidence_digest": None,
        "token_observation": {
            "semantics": "unavailable",
            "parent_enforced": False,
            "quantitative_caps_enforced": False,
        },
    }
    if terminal_event is None:
        gate["reason"] = "terminal_event_missing"
        return gate
    terminal_runtime = _trusted_terminal_runtime(terminal_event)
    if terminal_runtime is None:
        gate["reason"] = "trusted_terminal_event_invalid"
        return gate
    terminal = terminal_event.value
    packet_digest = _canonical_digest(packet)
    triple = _binding_triple(binding)
    child = terminal.get("child")
    terminal_result = terminal.get("terminal_result")
    terminal_nonce = terminal.get("terminal_nonce")
    terminal_parent_enforced = terminal.get("parent_enforced")
    main_session_id = terminal.get("main_session_id")
    typed_launch_paths = {"typed_external_worker", "corrected_typed_worker"}
    if (
        terminal.get("version") != TERMINAL_EVENT_VERSION
        or terminal.get("packet_digest") != packet_digest
        or terminal.get("dispatch_id") != dispatch_id
        or terminal.get("selected_launch_path") != selected_launch_path
        or selected_launch_path not in {"protected", *typed_launch_paths}
        or terminal.get("actual") != triple
        or not isinstance(child, dict)
        or child.get("session_id") != terminal_runtime.session_id
        or child.get("role") != triple
        or terminal_runtime.model != binding.model
        or terminal_runtime.effort != binding.effort
        or not isinstance(terminal_result, dict)
        or isinstance(terminal_result.get("returncode"), bool)
        or terminal_result.get("returncode") != EXIT_SUCCESS
        or terminal_result.get("succeeded") is not True
        or not isinstance(terminal_nonce, str)
        or TERMINAL_NONCE_PATTERN.fullmatch(terminal_nonce) is None
        or not isinstance(main_session_id, str)
        or not main_session_id
        or terminal_parent_enforced is not parent_enforced
        or (
            selected_launch_path in typed_launch_paths
            and terminal_parent_enforced is not True
        )
        or (
            selected_launch_path == "protected"
            and terminal_parent_enforced is not False
        )
    ):
        gate["reason"] = "terminal_event_binding_invalid"
        return gate
    if (
        runtime is None
        or expected_session_id is None
        or runtime != terminal_runtime
        or expected_session_id != terminal_runtime.session_id
    ):
        gate["reason"] = "trusted_unique_rollout_identity_missing"
        return gate
    if _worktree_digest(packet) != terminal.get("worktree_digest"):
        gate["reason"] = "terminal_worktree_stale_or_mutable"
        return gate
    value, receipt_path = _receipt_value(value)
    if value is None or receipt_path is None:
        return gate
    if value.get("receipt_kind") != "integration" or value.get("receipt_version") != RECEIPT_VERSION:
        gate["reason"] = "receipt_kind_or_version_invalid"
        return gate
    if dispatch_id is None or value.get("dispatch_id") != dispatch_id:
        gate["reason"] = "integration_dispatch_id_mismatch"
        return gate
    if value.get("packet_digest") != packet_digest:
        gate["reason"] = "integration_packet_digest_mismatch"
        return gate
    if (
        value.get("rollout_session_id") != expected_session_id
        or value.get("child_session_id") != terminal_runtime.session_id
        or value.get("child_role") != triple
    ):
        gate["reason"] = "trusted_unique_rollout_identity_missing"
        return gate
    if value.get("terminal_digest") != terminal_event.digest or value.get("terminal") != terminal:
        gate["reason"] = "terminal_receipt_binding_mismatch"
        return gate
    if (
        value.get("terminal_nonce") != terminal.get("terminal_nonce")
        or value.get("terminal_result") != terminal.get("terminal_result")
        or value.get("rollout_digest") != terminal.get("rollout", {}).get("sha256")
        or value.get("output_digest") != terminal.get("output_digest")
        or value.get("worktree_digest") != terminal.get("worktree_digest")
    ):
        gate["reason"] = "terminal_output_or_worktree_mismatch"
        return gate
    if any(value.get(field) != triple for field in ("desired", "explicit", "effective")):
        gate["reason"] = "desired_explicit_effective_mismatch"
        return gate
    if value.get("launch_bound_role") != {
        "agent_type": binding.agent_type,
        "role_config": str(binding.role_config),
    }:
        gate["reason"] = "launch_bound_role_proof_missing"
        return gate
    if value.get("selected_launch_path") != selected_launch_path:
        gate["reason"] = "selected_launch_path_mismatch"
        return gate
    target_role_digest = _role_config_digest(binding)
    if target_role_digest is None or value.get("launch_bound_role_config_digest") != target_role_digest:
        gate["reason"] = "launch_bound_role_digest_invalid"
        return gate
    issuer = value.get("issuer")
    checker = _installed_integration_checker_binding()
    if not isinstance(issuer, dict) or checker is None:
        gate["reason"] = "integration_checker_issuer_missing"
        return gate
    checker_digest = _role_config_digest(checker)
    issuer_session = _canonical_uuid(issuer.get("rollout_session_id"))
    issuer_rollout = issuer.get("rollout_path")
    if (
        checker_digest is None
        or issuer.get("role") != _binding_triple(checker)
        or issuer.get("role_config") != str(checker.role_config)
        or issuer.get("role_config_digest") != checker_digest
        or not isinstance(issuer_rollout, str)
        or issuer_session is None
    ):
        gate["reason"] = "integration_checker_issuer_binding_invalid"
        return gate
    if issuer_session in {terminal_runtime.session_id, main_session_id}:
        gate["reason"] = "integration_checker_session_not_independent"
        return gate
    checker_runtime = _trusted_rollout(Path(issuer_rollout), issuer_session)
    if (
        checker_runtime is None
        or checker_runtime.model != checker.model
        or checker_runtime.effort != checker.effort
        or not _rollout_has_receipt_marker(Path(issuer_rollout), issuer_session, value)
    ):
        gate["reason"] = "trusted_integration_checker_marker_missing"
        return gate
    digest = value.get("evidence_digest")
    if (
        value.get("finished_success") is not True
        or value.get("checker_pass") is not True
        or not isinstance(digest, str)
        or V2_COMMAND_DIGEST_PATTERN.fullmatch(digest) is None
    ):
        gate["reason"] = "completion_checker_or_evidence_digest_invalid"
        return gate
    checks = value.get("verification_checks")
    if (
        not isinstance(checks, list)
        or not checks
        or value.get("verification_checks_digest") != _canonical_digest(checks)
        or any(
            not isinstance(check, dict)
            or not isinstance(check.get("name"), str)
            or not check["name"].strip()
            or check.get("passed") is not True
            or check.get("evidence_digest") != digest
            for check in checks
        )
    ):
        gate["reason"] = "verification_checks_invalid"
        return gate
    artifact = value.get("evidence_artifact")
    if (
        not isinstance(artifact, dict)
        or not isinstance(artifact.get("path"), str)
        or artifact.get("sha256") != digest
        or artifact.get("terminal_digest") != terminal_event.digest
        or artifact.get("verification_checks_digest") != _canonical_digest(checks)
        or artifact.get("output_digest") != terminal.get("output_digest")
        or artifact.get("worktree_digest") != terminal.get("worktree_digest")
        or not _secure_owned_file(Path(artifact["path"]), exact_mode=0o600)
    ):
        gate["reason"] = "evidence_artifact_invalid"
        return gate
    if _secure_file_digest(Path(artifact["path"])) != digest:
        gate["reason"] = "evidence_artifact_invalid"
        return gate
    observation = value.get("token_observation")
    if not isinstance(observation, dict):
        gate["reason"] = "token_observation_missing"
        return gate
    semantics = observation.get("semantics")
    observed_parent = observation.get("parent_enforced")
    observed_caps = observation.get("quantitative_caps_enforced")
    typed = selected_launch_path in {
        "typed_external_worker",
        "corrected_typed_worker",
    }
    if typed:
        valid_observation = (
            semantics == "trusted_parent_monitoring"
            and observed_parent is True
            and observed_caps is True
            and parent_enforced
        )
    else:
        valid_observation = (
            semantics == "unavailable"
            and observed_parent is False
            and observed_caps is False
            and not parent_enforced
        )
    if not valid_observation:
        gate["reason"] = "token_observation_semantics_invalid"
        return gate
    gate.update(
        {
            "status": "passed",
            "reason": None,
            "evidence_digest": digest,
            "token_observation": {
                "semantics": semantics,
                "parent_enforced": observed_parent,
                "quantitative_caps_enforced": observed_caps,
            },
        }
    )
    return gate


def _secure_file_digest(path: Path) -> str | None:
    """Hash one owner-only regular file without following a replacement symlink."""
    if not _secure_owned_file(path, exact_mode=0o600):
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            digest = hashlib.sha256()
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
        after = path.lstat()
    except OSError:
        return None
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        return None
    return digest.hexdigest()


def _trusted_terminal_runtime(terminal_event: TerminalEvent) -> RuntimeEvidence | None:
    """Recheck the terminal rollout so a stale or mutable terminal cannot finalize."""
    value = terminal_event.value
    if _canonical_digest(value) != terminal_event.digest:
        return None
    child = value.get("child")
    rollout = value.get("rollout")
    if (
        not isinstance(child, dict)
        or not isinstance(rollout, dict)
        or not isinstance(rollout.get("path"), str)
        or V2_COMMAND_DIGEST_PATTERN.fullmatch(rollout.get("sha256", "")) is None
        or rollout.get("runtime_home") not in {"main", "leaf"}
    ):
        return None
    session_id = _canonical_uuid(child.get("session_id"))
    if session_id is None:
        return None
    runtime_home = LEAF_RUNTIME_HOME if rollout["runtime_home"] == "leaf" else CODEX_HOME
    runtime = _trusted_rollout(
        Path(rollout["path"]),
        session_id,
        codex_home=runtime_home,
        sessions_root=runtime_home / "sessions",
    )
    if (
        runtime is None
        or _secure_file_digest(Path(rollout["path"])) != rollout["sha256"]
    ):
        return None
    return runtime


def _capture_terminal_event(
    *,
    packet: dict[str, Any],
    binding: RoleBinding,
    runtime: RuntimeEvidence | None,
    rollout: Path | None,
    rollout_runtime_home: str,
    selected_launch_path: str,
    child_returncode: int | None,
    output_digest: str | None,
    parent_enforced: bool,
    weighted_tokens: int | None = None,
    execution_elapsed_ms: int | None = None,
) -> TerminalEvent | None:
    """Capture actual completion data before any receipt can be considered."""
    main_authority = packet.get("main_authority")
    main_session_id = (
        main_authority.get("session_id") if isinstance(main_authority, dict) else None
    )
    if (
        runtime is None
        or rollout is None
        or runtime.model != binding.model
        or runtime.effort != binding.effort
        or rollout_runtime_home not in {"main", "leaf"}
        or isinstance(child_returncode, bool)
        or not isinstance(child_returncode, int)
        or not isinstance(main_session_id, str)
        or not main_session_id
        or not isinstance(output_digest, str)
        or V2_COMMAND_DIGEST_PATTERN.fullmatch(output_digest) is None
        or (
            weighted_tokens is not None
            and (
                isinstance(weighted_tokens, bool)
                or not isinstance(weighted_tokens, int)
                or weighted_tokens < 0
            )
        )
        or (
            execution_elapsed_ms is not None
            and (
                isinstance(execution_elapsed_ms, bool)
                or not isinstance(execution_elapsed_ms, int)
                or execution_elapsed_ms < 0
            )
        )
    ):
        return None
    rollout_digest = _secure_file_digest(rollout)
    worktree_digest = _worktree_digest(packet)
    if (
        rollout_digest is None
        or (packet.get("write_scope") != ["read-only"] and worktree_digest is None)
    ):
        return None
    value = {
        "version": TERMINAL_EVENT_VERSION,
        "dispatch_id": packet["dispatch_id"].strip(),
        "packet_digest": _canonical_digest(packet),
        "selected_launch_path": selected_launch_path,
        "actual": _binding_triple(binding),
        "child": {
            "session_id": runtime.session_id,
            "role": _binding_triple(binding),
        },
        "terminal_result": {
            "returncode": child_returncode,
            "succeeded": child_returncode == EXIT_SUCCESS,
        },
        "rollout": {
            "path": str(rollout),
            "sha256": rollout_digest,
            "runtime_home": rollout_runtime_home,
        },
        "output_digest": output_digest,
        "worktree_digest": worktree_digest,
        "parent_enforced": parent_enforced,
        "weighted_tokens": weighted_tokens,
        "execution_elapsed_ms": execution_elapsed_ms,
        "main_session_id": main_session_id,
        "terminal_nonce": secrets.token_hex(32),
    }
    return TerminalEvent(value, _canonical_digest(value))


def _load_terminal_event(ledger: Path, packet: dict[str, Any]) -> TerminalEvent | None:
    """Load the newest exact terminal event for this packet from a secure ledger."""
    if not _secure_owned_file(ledger, exact_mode=0o600):
        return None
    expected_dispatch_id = packet["dispatch_id"].strip()
    expected_packet_digest = _canonical_digest(packet)
    latest: TerminalEvent | None = None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(ledger, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                if len(raw_line) > ROLLOUT_LINE_MAX_BYTES or not raw_line.strip():
                    return None
                record = json.loads(raw_line)
                if not isinstance(record, dict) or record.get("dispatch_id") != expected_dispatch_id:
                    continue
                raw_terminal = record.get("terminal_event")
                if not isinstance(raw_terminal, dict):
                    continue
                value = raw_terminal.get("value")
                digest = raw_terminal.get("digest")
                if (
                    not isinstance(value, dict)
                    or not isinstance(digest, str)
                    or V2_COMMAND_DIGEST_PATTERN.fullmatch(digest) is None
                    or _canonical_digest(value) != digest
                    or value.get("packet_digest") != expected_packet_digest
                ):
                    return None
                latest = TerminalEvent(value, digest)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return latest


@dataclass(frozen=True)
class ExecutionPolicy:
    max_tool_calls: int
    max_output_tokens_per_call: int
    max_cumulative_tool_output_bytes: int
    max_child_stdout_bytes: int
    allow_repo_wide_search: bool
    v2_source_dump_allowed: bool = True
    v2_full_diff_allowed: bool = True

    def public_limits(self) -> dict[str, int | bool]:
        return {
            "max_tool_calls": self.max_tool_calls,
            "max_output_tokens_per_call": self.max_output_tokens_per_call,
            "max_cumulative_tool_output_bytes": self.max_cumulative_tool_output_bytes,
            "max_child_stdout_bytes": self.max_child_stdout_bytes,
            "allow_repo_wide_search": self.allow_repo_wide_search,
        }


@dataclass
class RolloutTokenMonitor:
    descriptor: int
    execution_policy: ExecutionPolicy
    pending: bytes = b""
    observed_weighted_tokens: int | None = None
    forbidden_leaf_tool_call: str | None = None
    observed_tool_calls: int = 0
    observed_tool_output_bytes: int = 0
    execution_policy_violation: str | None = None

    def poll(self, *, final: bool = False) -> int | None:
        while True:
            try:
                chunk = os.read(self.descriptor, 65_536)
            except OSError:
                break
            if not chunk:
                break
            self.pending += chunk
            lines = self.pending.split(b"\n")
            self.pending = lines.pop()
            for raw_line in lines:
                self._observe(raw_line)
            pending_limit = ROLLOUT_LINE_MAX_BYTES
            if len(self.pending) > pending_limit:
                self._violate("rollout_line_bytes_exceeded")
                self.pending = b""

        if final and self.pending.strip():
            self._observe(self.pending)
            self.pending = b""
        return self.observed_weighted_tokens

    def _observe(self, raw_line: bytes) -> None:
        if not raw_line.strip():
            return
        if len(raw_line) > ROLLOUT_LINE_MAX_BYTES:
            self._violate("rollout_line_bytes_exceeded")
            return
        try:
            record = json.loads(raw_line)
        except (UnicodeError, json.JSONDecodeError):
            return
        if isinstance(record, dict) and record.get("type") == "response_item":
            payload = record.get("payload")
            if (
                isinstance(payload, dict)
                and payload.get("type") == "function_call"
                and payload.get("namespace") == "collaboration"
            ):
                tool_name = payload.get("name")
                self.forbidden_leaf_tool_call = (
                    str(tool_name) if isinstance(tool_name, str) else "unknown"
                )
            if isinstance(payload, dict) and payload.get("type") == "custom_tool_call":
                self._observe_custom_tool_call(payload)
            if (
                isinstance(payload, dict)
                and payload.get("type") == "custom_tool_call_output"
            ):
                self.observed_tool_output_bytes += _content_bytes(payload.get("output"))
                if (
                    self.observed_tool_output_bytes
                    > self.execution_policy.max_cumulative_tool_output_bytes
                ):
                    self._violate("cumulative_tool_output_bytes_exceeded")
        weighted_usage = _weighted_token_usage(record)
        if weighted_usage is not None:
            self.observed_weighted_tokens = max(
                self.observed_weighted_tokens or 0, weighted_usage
            )

    def _observe_custom_tool_call(self, payload: dict[str, Any]) -> None:
        tool_name = payload.get("name")
        tool_input = payload.get("input")
        nested_calls = (
            _extract_js_nested_tool_calls(tool_input)
            if isinstance(tool_input, str)
            else []
        )
        call_count = max(1, len(nested_calls))
        self.observed_tool_calls += call_count
        if self.observed_tool_calls > self.execution_policy.max_tool_calls:
            self._violate("tool_calls_exceeded")
        if tool_name != "exec" or not isinstance(tool_input, str):
            return

        output_limited_calls = [
            call
            for call in nested_calls
            if call.name in {"exec_command", "write_stdin"}
        ]
        requested_output_tokens: list[int] = []
        for call in output_limited_calls:
            present, value = _js_object_int_field(
                call.argument_object, "max_output_tokens"
            )
            if not present:
                requested_output_tokens.append(DEFAULT_EXEC_COMMAND_MAX_OUTPUT_TOKENS)
            elif value is None:
                self._violate("max_output_tokens_literal_required")
                return
            else:
                requested_output_tokens.append(value)
        if any(
            value > self.execution_policy.max_output_tokens_per_call
            for value in requested_output_tokens
        ):
            self._violate("max_output_tokens_per_call_exceeded")
            return
        exec_calls = [call for call in nested_calls if call.name == "exec_command"]
        if not exec_calls:
            return
        commands: list[str] = []
        for call in exec_calls:
            present, command = _js_object_string_field(call.argument_object, "cmd")
            if not present or command is None:
                self._violate("exec_command_literal_required")
                return
            commands.append(command)
        if not self.execution_policy.allow_repo_wide_search and any(
            _is_repo_wide_search(command) for command in commands
        ):
            self._violate("repo_wide_search_forbidden")
            return
        if any(
            _is_unapproved_v2_dump(command, self.execution_policy)
            for command in commands
        ):
            self._violate("source_or_full_diff_dump_forbidden")

    def _violate(self, reason: str) -> None:
        if self.execution_policy_violation is None:
            self.execution_policy_violation = reason

    def close(self) -> None:
        try:
            os.close(self.descriptor)
        except OSError:
            pass


@dataclass(frozen=True)
class _JsNestedToolCall:
    name: str
    argument_object: str | None


def _js_code_mask(source: str) -> str:
    """Replace JavaScript strings and comments without changing offsets."""
    masked = list(source)
    index = 0
    while index < len(source):
        character = source[index]
        next_character = source[index + 1] if index + 1 < len(source) else ""
        if character == "/" and next_character == "/":
            end = source.find("\n", index + 2)
            end = len(source) if end == -1 else end
            for position in range(index, end):
                masked[position] = " "
            index = end
            continue
        if character == "/" and next_character == "*":
            end = source.find("*/", index + 2)
            end = len(source) if end == -1 else end + 2
            for position in range(index, end):
                masked[position] = " "
            index = end
            continue
        if character in {"'", '"', "`"}:
            quote = character
            end = index + 1
            while end < len(source):
                if source[end] == "\\":
                    end += 2
                    continue
                if source[end] == quote:
                    end += 1
                    break
                end += 1
            for position in range(index, min(end, len(source))):
                masked[position] = " "
            index = end
            continue
        index += 1
    return "".join(masked)


def _find_js_balanced(masked: str, start: int, opening: str, closing: str) -> int | None:
    if start >= len(masked) or masked[start] != opening:
        return None
    depth = 0
    for index in range(start, len(masked)):
        if masked[index] == opening:
            depth += 1
        elif masked[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def _extract_js_nested_tool_calls(source: str) -> list[_JsNestedToolCall]:
    masked = _js_code_mask(source)
    calls: list[_JsNestedToolCall] = []
    pattern = re.compile(r"\btools\.([A-Za-z0-9_]+)\s*\(")
    for match in pattern.finditer(masked):
        opening = masked.find("(", match.start(), match.end())
        closing = _find_js_balanced(masked, opening, "(", ")")
        object_start = opening + 1
        while object_start < len(masked) and masked[object_start].isspace():
            object_start += 1
        object_end = _find_js_balanced(masked, object_start, "{", "}")
        argument_object = (
            source[object_start : object_end + 1]
            if closing is not None and object_end is not None and object_end < closing
            else None
        )
        calls.append(_JsNestedToolCall(match.group(1), argument_object))
    return calls


def _js_string_end(source: str, start: int) -> int | None:
    quote = source[start]
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
            continue
        if source[index] == quote:
            return index + 1
        index += 1
    return None


def _js_object_field_start(
    argument_object: str | None, field: str
) -> tuple[bool, int | None]:
    if argument_object is None:
        return True, None
    masked = _js_code_mask(argument_object)
    depth = 0
    index = 1
    value_start: int | None = None
    while index < len(argument_object) - 1:
        character = masked[index]
        if character in "{[(":
            depth += 1
            index += 1
            continue
        if character in "})]":
            depth = max(0, depth - 1)
            index += 1
            continue
        if depth != 0:
            index += 1
            continue
        key_end = index
        key_matches = False
        if argument_object[index] in {"'", '"'}:
            string_end = _js_string_end(argument_object, index)
            if string_end is None:
                return True, None
            key_matches = argument_object[index + 1 : string_end - 1] == field
            key_end = string_end
        elif character.isalpha() or character in "_$":
            key_end += 1
            while key_end < len(masked) and (
                masked[key_end].isalnum() or masked[key_end] in "_$"
            ):
                key_end += 1
            key_matches = masked[index:key_end] == field
        else:
            index += 1
            continue
        colon = key_end
        while colon < len(masked) and masked[colon].isspace():
            colon += 1
        if key_matches and colon < len(masked) and masked[colon] == ":":
            value_start = colon + 1
        index = max(key_end, index + 1)
    return value_start is not None, value_start


def _js_object_int_field(
    argument_object: str | None, field: str
) -> tuple[bool, int | None]:
    present, value_start = _js_object_field_start(argument_object, field)
    if not present or value_start is None or argument_object is None:
        return present, None
    while value_start < len(argument_object) and argument_object[value_start].isspace():
        value_start += 1
    match = re.match(r"\d+\b", argument_object[value_start:])
    return present, int(match.group(0)) if match else None


def _js_object_string_field(
    argument_object: str | None, field: str
) -> tuple[bool, str | None]:
    present, value_start = _js_object_field_start(argument_object, field)
    if not present or value_start is None or argument_object is None:
        return present, None
    while value_start < len(argument_object) and argument_object[value_start].isspace():
        value_start += 1
    if value_start >= len(argument_object) or argument_object[value_start] not in {
        "'",
        '"',
        "`",
    }:
        return present, None
    string_end = _js_string_end(argument_object, value_start)
    if string_end is None:
        return present, None
    if argument_object[value_start] == "`":
        value = argument_object[value_start + 1 : string_end - 1]
        return present, value if "${" not in value else None
    if argument_object[value_start] == '"':
        try:
            value, _end = json.JSONDecoder().raw_decode(argument_object[value_start:])
        except json.JSONDecodeError:
            return present, None
        return present, value if isinstance(value, str) else None
    return present, argument_object[value_start + 1 : string_end - 1]


def _content_bytes(value: Any) -> int:
    if isinstance(value, str):
        return len(value.encode("utf-8", errors="replace"))
    if isinstance(value, list):
        return sum(_content_bytes(item) for item in value)
    if isinstance(value, dict):
        return sum(_content_bytes(item) for item in value.values())
    return 0


def _shell_segments(command: str) -> list[tuple[list[str], bool]] | None:
    try:
        lexer = shlex.shlex(
            command.replace("\n", " ; "), posix=True, punctuation_chars="|&;"
        )
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return None
    segments: list[tuple[list[str], bool]] = []
    current: list[str] = []
    stdin_piped = False
    current_stdin_piped = False
    for token in tokens:
        if token in {"|", "||", "&&", ";"}:
            if current:
                segments.append((current, current_stdin_piped))
            current = []
            stdin_piped = token == "|"
            current_stdin_piped = stdin_piped
            continue
        current.append(token)
    if current:
        segments.append((current, current_stdin_piped))
    return segments


def _non_option_operands(arguments: list[str]) -> list[str]:
    value_options = {
        "-A",
        "-B",
        "-C",
        "-e",
        "-f",
        "-g",
        "-j",
        "-m",
        "-t",
        "--after-context",
        "--before-context",
        "--context",
        "--encoding",
        "--file",
        "--glob",
        "--iglob",
        "--max-count",
        "--max-depth",
        "--regexp",
        "--threads",
        "--type",
    }
    operands: list[str] = []
    skip_next = False
    for index, argument in enumerate(arguments):
        if skip_next:
            skip_next = False
            continue
        if argument == "--":
            operands.extend(arguments[index + 1 :])
            break
        option_name = argument.split("=", 1)[0]
        if option_name in value_options and "=" not in argument:
            skip_next = True
            continue
        if argument.startswith("-"):
            continue
        operands.append(argument)
    return operands


def _is_repo_wide_search(command: str) -> bool:
    segments = _shell_segments(command)
    if segments is None:
        return True
    for tokens, stdin_piped in segments:
        if not tokens:
            continue
        command_index = 0
        while command_index < len(tokens) and re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[command_index]
        ):
            command_index += 1
        if command_index >= len(tokens):
            continue
        executable = Path(tokens[command_index]).name
        arguments = tokens[command_index + 1 :]
        pytest_arguments: list[str] | None = None
        if executable == "pytest":
            pytest_arguments = arguments
        elif (
            re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable)
            and len(arguments) >= 2
            and arguments[:2] == ["-m", "pytest"]
        ):
            pytest_arguments = arguments[2:]
        if pytest_arguments is not None:
            pytest_targets: list[str] = []
            selector_value_follows = False
            for argument in pytest_arguments:
                if selector_value_follows:
                    selector_value_follows = False
                    continue
                if argument in {"-k", "-m", "--keyword", "--mark"}:
                    selector_value_follows = True
                    continue
                if argument.startswith(("-k=", "-m=", "--keyword=", "--mark=")):
                    continue
                if not argument.startswith("-"):
                    pytest_targets.append(argument)
            if not pytest_targets:
                return True
        broad_operand = any(
            value in {".", "./", "..", "../", "/"} or value.startswith("../")
            for value in arguments
        )
        if executable == "git":
            git_index = 0
            git_value_options = {
                "-C",
                "-c",
                "--config-env",
                "--git-dir",
                "--namespace",
                "--super-prefix",
                "--work-tree",
            }
            while git_index < len(arguments):
                argument = arguments[git_index]
                option_name = argument.split("=", 1)[0]
                if option_name in git_value_options:
                    git_index += 1 if "=" in argument else 2
                elif argument.startswith("-"):
                    git_index += 1
                else:
                    break
            if git_index < len(arguments):
                git_subcommand = arguments[git_index]
                git_subcommand_arguments = arguments[git_index + 1 :]
                if git_subcommand in {"diff", "status"}:
                    if "--" not in git_subcommand_arguments:
                        return True
                    separator = git_subcommand_arguments.index("--")
                    pathspecs = git_subcommand_arguments[separator + 1 :]
                    if not pathspecs or any(
                        value in {".", "./", "..", "../", "/"}
                        or value.startswith("../")
                        for value in pathspecs
                    ):
                        return True
        elif executable in {"rg", "ripgrep"}:
            if broad_operand:
                return True
            operands = _non_option_operands(arguments)
            if "--files" in arguments:
                if not operands:
                    return True
            elif not stdin_piped:
                pattern_is_option = any(
                    value in {"-e", "--regexp"}
                    or value.startswith("--regexp=")
                    for value in arguments
                )
                minimum_operands = 1 if pattern_is_option else 2
                if len(operands) < minimum_operands:
                    return True
        elif executable in {"find", "fd", "fdfind"}:
            if broad_operand or not arguments or arguments[0].startswith("-"):
                return True
        elif executable in {"grep", "egrep", "fgrep"} and any(
            flag in arguments for flag in ("-r", "-R", "--recursive")
        ):
            operands = _non_option_operands(arguments)
            if broad_operand or (not stdin_piped and len(operands) < 2):
                return True
    return False


def _is_unapproved_v2_dump(command: str, execution_policy: ExecutionPolicy) -> bool:
    if execution_policy.v2_source_dump_allowed and execution_policy.v2_full_diff_allowed:
        return False
    segments = _shell_segments(command)
    if segments is None:
        return True
    for tokens, _stdin_piped in segments:
        if not tokens:
            continue
        executable = Path(tokens[0]).name
        arguments = tokens[1:]
        if not execution_policy.v2_source_dump_allowed and executable in {
            "cat", "less", "more",
        }:
            return True
        if executable == "git" and "diff" in arguments:
            diff_arguments = arguments[arguments.index("diff") + 1 :]
            bounded_summary = any(
                item in {"--stat", "--name-only", "--check", "--summary"}
                for item in diff_arguments
            )
            if not execution_policy.v2_full_diff_allowed and not bounded_summary:
                return True
    return False


def _weighted_token_usage(record: Any) -> int | None:
    if not isinstance(record, dict) or record.get("type") != "event_msg":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None
    info = payload.get("info")
    total_usage = info.get("total_token_usage") if isinstance(info, dict) else None
    if not isinstance(total_usage, dict):
        return None
    input_tokens = total_usage.get("input_tokens")
    output_tokens = total_usage.get("output_tokens")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (input_tokens, output_tokens)
    ):
        return None
    # Codex input_tokens already includes cached input, so do not subtract it.
    return (input_tokens + 3) // 4 + output_tokens


def _open_rollout_token_monitor(
    path: Path, execution_policy: ExecutionPolicy
) -> RolloutTokenMonitor | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        path_metadata = path.lstat()
    except OSError:
        return None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or (metadata.st_dev, metadata.st_ino)
        != (path_metadata.st_dev, path_metadata.st_ino)
    ):
        os.close(descriptor)
        return None
    return RolloutTokenMonitor(descriptor, execution_policy)


def _terminate_child_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=CHILD_GROUP_TERM_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=CHILD_GROUP_TERM_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        return


def _nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return value is not None and value is not False


def _bounded_int(value: Any, minimum: int, maximum: int) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and minimum <= value <= maximum
    )


def _v2_read_scopes(value: Any) -> list[Path] | None:
    if not isinstance(value, list) or not value:
        return None
    scopes: list[Path] = []
    for item in value:
        if not isinstance(item, str) or not item or "\x00" in item:
            return None
        candidate = Path(item)
        if not candidate.is_absolute():
            return None
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            return None
        if not resolved.is_dir() or resolved not in scopes:
            scopes.append(resolved)
    return scopes or None


def _v2_explicit_file_rg(packet: dict[str, Any]) -> list[str] | None:
    scopes = _v2_read_scopes(packet.get("read_scope"))
    argv = packet.get("explicit_file_rg_argv")
    if scopes is None or not isinstance(argv, list) or len(argv) < 4:
        return None
    if any(not isinstance(item, str) or not item or "\x00" in item for item in argv):
        return None
    if argv[0] != "rg" or argv.count("--") != 1:
        return None
    separator = argv.index("--")
    if separator < 2 or separator == len(argv) - 1:
        return None
    # A deliberately small argv grammar keeps this classification canonical:
    # one pattern, followed by -- and one or more literal regular files.
    flag_without_value = {
        "-F", "--fixed-strings", "-i", "--ignore-case", "-s",
        "--case-sensitive", "-w", "--word-regexp", "-x", "--line-regexp",
        "-n", "--line-number", "--no-heading", "--color=never",
    }
    flag_with_value = {"-e", "--regexp", "-g", "--glob", "-t", "--type"}
    before = argv[1:separator]
    pattern_count = 0
    index = 0
    while index < len(before):
        argument = before[index]
        if argument in {"-r", "-R", "--recursive", "--files", "--files-from"}:
            return None
        if argument in flag_without_value:
            index += 1
            continue
        if argument in flag_with_value:
            if index + 1 >= len(before) or before[index + 1].startswith("-"):
                return None
            if argument in {"-e", "--regexp"}:
                pattern_count += 1
            index += 2
            continue
        if argument.startswith("--regexp=") or argument.startswith("-e="):
            if not argument.split("=", 1)[1]:
                return None
            pattern_count += 1
            index += 1
            continue
        if argument.startswith(("--glob=", "--type=")):
            if not argument.split("=", 1)[1]:
                return None
            index += 1
            continue
        if argument.startswith("-"):
            return None
        pattern_count += 1
        index += 1
    if pattern_count != 1:
        return None

    resolved_files: list[str] = []
    for item in argv[separator + 1 :]:
        if any(character in item for character in "*?[]"):
            return None
        candidate = Path(item)
        if not candidate.is_absolute() or candidate.is_symlink():
            return None
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            return None
        if (
            not resolved.is_file()
            or not any(resolved.is_relative_to(scope) for scope in scopes)
            or str(resolved) in resolved_files
        ):
            return None
        resolved_files.append(str(resolved))
    return resolved_files or None


def _v2_delta_receipt(packet: dict[str, Any]) -> dict[str, Any] | None:
    parent = packet.get("parent")
    checkpoint = packet.get("checkpoint")
    delta = packet.get("delta")
    if not isinstance(parent, dict) or not isinstance(checkpoint, dict) or not isinstance(delta, dict):
        return None
    parent_dispatch_id = parent.get("dispatch_id")
    parent_checkpoint_id = parent.get("checkpoint_id")
    initial = parent_dispatch_id is None and parent_checkpoint_id is None
    continuation = (
        isinstance(parent_dispatch_id, str)
        and bool(DISPATCH_ID_PATTERN.fullmatch(parent_dispatch_id))
        and isinstance(parent_checkpoint_id, str)
        and bool(DISPATCH_ID_PATTERN.fullmatch(parent_checkpoint_id))
    )
    checkpoint_id = checkpoint.get("id")
    digests = checkpoint.get("completed_command_digests")
    summary = delta.get("delta_summary")
    source_dump = delta.get("source_dump")
    full_diff = delta.get("full_diff")
    if (
        not (initial or continuation)
        or not isinstance(checkpoint_id, str)
        or not DISPATCH_ID_PATTERN.fullmatch(checkpoint_id)
        or not isinstance(digests, list)
        or len(digests) > 128
        or any(not isinstance(item, str) or not V2_COMMAND_DIGEST_PATTERN.fullmatch(item) for item in digests)
        or len(set(digests)) != len(digests)
        or not isinstance(summary, str)
        or not summary.strip()
        or len(summary) > V2_DELTA_SUMMARY_MAX_CHARS
        or not isinstance(source_dump, bool)
        or not isinstance(full_diff, bool)
    ):
        return None
    if source_dump or full_diff:
        reason = delta.get("dump_reason", delta.get("opt_in_reason"))
        if not isinstance(reason, str) or not reason.strip() or len(reason) > V2_DELTA_SUMMARY_MAX_CHARS:
            return None
    return {
        "parent": {
            "dispatch_id": parent_dispatch_id,
            "checkpoint_id": parent_checkpoint_id,
        },
        "checkpoint": {
            "id": checkpoint_id,
            "completed_command_digests": list(digests),
        },
        "delta": {
            "delta_summary": summary.strip(),
            "source_dump": source_dump,
            "full_diff": full_diff,
        },
    }


def _v2_preflight(packet: dict[str, Any]) -> tuple[list[str], int] | None:
    explicit_files = _v2_explicit_file_rg(packet)
    receipt = _v2_delta_receipt(packet)
    estimate = packet.get("execution_estimate")
    minima = packet.get("prelaunch_minima")
    policy = _execution_policy(packet)
    target = packet.get("token_budget")
    if (
        explicit_files is None
        or receipt is None
        or not isinstance(estimate, dict)
        or not isinstance(minima, dict)
        or policy is None
        or not isinstance(target, int)
    ):
        return None
    values: dict[str, tuple[int, int]] = {}
    for field in V2_ESTIMATE_FIELDS:
        estimated = estimate.get(field)
        minimum = minima.get(field)
        if (
            isinstance(estimated, bool)
            or isinstance(minimum, bool)
            or not isinstance(estimated, int)
            or not isinstance(minimum, int)
            or minimum < 1
            or estimated < minimum
        ):
            return None
        values[field] = (estimated, minimum)
    if (
        values["tool_calls"][0] > policy.max_tool_calls
        or values["max_output_tokens_per_call"][0] > policy.max_output_tokens_per_call
        or values["cumulative_tool_output_bytes"][0] > policy.max_cumulative_tool_output_bytes
        or values["child_stdout_bytes"][0] > policy.max_child_stdout_bytes
        or values["weighted_tokens"][0] > target
    ):
        return None
    return explicit_files, target


def _execution_policy(packet: dict[str, Any]) -> ExecutionPolicy | None:
    resource_cap = packet.get("resource_cap")
    if not isinstance(resource_cap, dict):
        return None
    processes = resource_cap.get("processes")
    network = resource_cap.get("network")
    max_tool_calls = resource_cap.get("max_tool_calls")
    max_output_tokens_per_call = resource_cap.get("max_output_tokens_per_call")
    max_cumulative_tool_output_bytes = resource_cap.get(
        "max_cumulative_tool_output_bytes"
    )
    max_child_stdout_bytes = resource_cap.get("max_child_stdout_bytes")
    allow_repo_wide_search = resource_cap.get("allow_repo_wide_search")
    repo_wide_search_reason = resource_cap.get("repo_wide_search_reason")
    token_budget = packet.get("token_budget")
    if (
        not _bounded_int(processes, 1, 64)
        or not isinstance(network, bool)
        or network is not packet.get("network_access", False)
        or not _bounded_int(max_tool_calls, 1, MAX_TOOL_CALLS)
        or not _bounded_int(
            max_output_tokens_per_call, 128, MAX_OUTPUT_TOKENS_PER_CALL
        )
        or not isinstance(token_budget, int)
        or max_output_tokens_per_call > token_budget
        or not _bounded_int(
            max_cumulative_tool_output_bytes,
            1_024,
            MAX_CUMULATIVE_TOOL_OUTPUT_BYTES,
        )
        or not _bounded_int(max_child_stdout_bytes, 256, MAX_CHILD_STDOUT_BYTES)
        or not isinstance(allow_repo_wide_search, bool)
        or (
            allow_repo_wide_search
            and (not isinstance(repo_wide_search_reason, str) or not repo_wide_search_reason.strip())
        )
    ):
        return None
    v2_receipt = _v2_delta_receipt(packet) if packet.get("packet_version") == V2_PACKET_VERSION else None
    return ExecutionPolicy(
        max_tool_calls=max_tool_calls,
        max_output_tokens_per_call=max_output_tokens_per_call,
        max_cumulative_tool_output_bytes=max_cumulative_tool_output_bytes,
        max_child_stdout_bytes=max_child_stdout_bytes,
        allow_repo_wide_search=allow_repo_wide_search,
        v2_source_dump_allowed=(
            bool(v2_receipt["delta"]["source_dump"])
            if v2_receipt is not None
            else True
        ),
        v2_full_diff_allowed=(
            bool(v2_receipt["delta"]["full_diff"])
            if v2_receipt is not None
            else True
        ),
    )


def _validate_packet(packet: Any, source_path: Path | None) -> str | None:
    if not isinstance(packet, dict):
        return "packet_not_object"
    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet or not _nonempty(packet[field]):
            return f"packet_field_missing_or_empty:{field}"
    if not isinstance(packet["dispatch_id"], str) or not DISPATCH_ID_PATTERN.fullmatch(
        packet["dispatch_id"].strip()
    ):
        return "dispatch_id_invalid"
    if any(not isinstance(packet[field], str) for field in TRIPLE_FIELDS):
        return "routing_triple_invalid"
    token_budget = packet.get("token_budget")
    if (
        isinstance(token_budget, bool)
        or not isinstance(token_budget, int)
        or token_budget < MIN_TOKEN_BUDGET
    ):
        return "token_budget_invalid"
    if _execution_policy(packet) is None:
        return "resource_cap_invalid"
    packet_version = packet.get("packet_version")
    if packet_version is not None:
        if isinstance(packet_version, bool) or packet_version != V2_PACKET_VERSION:
            return "packet_version_invalid"
        if _v2_preflight(packet) is None:
            return "v2_preflight_invalid"
    network_access = packet.get("network_access", False)
    if not isinstance(network_access, bool):
        return "network_access_invalid"
    if network_access and packet.get("write_scope") == ["read-only"]:
        return "network_access_requires_workspace_write"
    if source_path is not None and packet["evidence_path"] != str(source_path):
        return "evidence_path_mismatch"
    return None


def _intended_triple(packet: dict[str, Any]) -> dict[str, str]:
    return {field: packet[field].strip() for field in TRIPLE_FIELDS}


def _load_json(path: Path) -> Any:
    if path.stat().st_size > 1_000_000:
        raise ValueError("json_too_large")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _role_config_path(agent_type: str) -> Path | None:
    candidates = (
        AGENT_CONFIG_ROOT / f"{agent_type}.toml",
        PACKAGE_ROLE_ROOT / f"{agent_type}.toml",
    )
    return next((path for path in candidates if _secure_owned_file(path)), None)


def _load_routing_policy() -> tuple[bool, dict[str, Any] | None]:
    """Load the installed package policy without external overrides."""
    if not os.path.lexists(ROUTING_POLICY_CONFIG):
        return False, None
    if not _secure_owned_file(ROUTING_POLICY_CONFIG):
        return True, None
    try:
        policy = _load_json(ROUTING_POLICY_CONFIG)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return True, None
    if not isinstance(policy, dict):
        return True, None
    return True, policy


def _package_policy_binding(
    *,
    agent_type: str,
    model_tier: str | None,
    model: str,
    effort: str,
) -> tuple[bool, bool]:
    """Return (declared, valid) for a package-owned routing-policy binding."""
    declared, policy = _load_routing_policy()
    if not declared:
        return False, False
    if policy is None:
        return True, False
    bindings = policy.get("role_bindings") if isinstance(policy, dict) else None
    if not isinstance(bindings, dict):
        return True, False
    binding = bindings.get(agent_type)
    if binding is None:
        return False, False
    if not isinstance(binding, dict):
        return True, False
    expected_tier = binding.get("model_tier")
    expected_model = binding.get("model")
    expected_effort = binding.get("reasoning_effort")
    valid = (
        isinstance(expected_tier, str)
        and isinstance(expected_model, str)
        and isinstance(expected_effort, str)
        and expected_model == model
        and expected_effort == effort
        and (model_tier is None or expected_tier == model_tier)
    )
    return True, valid


def _adaptive_modules() -> tuple[Any, Any]:
    package_scripts = ADAPTIVE_SKILL_ROOT / "scripts"
    rendered = str(package_scripts)
    if rendered not in sys.path:
        sys.path.insert(0, rendered)
    try:
        import dispatch_policy
        import model_routing_audit
    except ImportError as exc:
        raise RuntimeError("adaptive policy or audit module is unavailable") from exc
    return dispatch_policy, model_routing_audit


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _adaptive_package_binding(
    packet: Any,
) -> tuple[dict[str, Any], dict[str, str]] | None:
    if not isinstance(packet, dict) or not isinstance(packet.get("agent_type"), str):
        return None
    declared, policy = _load_routing_policy()
    if not declared:
        return None
    if policy is None:
        raise RuntimeError("adaptive package policy is unavailable or unsafe")
    bindings = policy.get("role_bindings")
    if not isinstance(bindings, dict):
        raise RuntimeError("adaptive package role bindings are invalid")
    raw = bindings.get(packet["agent_type"].strip())
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise RuntimeError("adaptive package role binding is invalid")
    fields = {
        "agent_type": packet["agent_type"].strip(),
        "model": raw.get("model"),
        "model_tier": raw.get("model_tier"),
        "reasoning_effort": raw.get("reasoning_effort"),
    }
    if not all(isinstance(value, str) and value for value in fields.values()):
        raise RuntimeError("adaptive package role binding is incomplete")
    return policy, fields


def _linked_fields(context: AdaptiveAuditContext) -> dict[str, Any]:
    return {
        "dispatch_id": context.routing["dispatch_id"],
        "policy_id": context.policy["policy_id"],
        "policy_fingerprint": context.policy_fingerprint,
        "workspace": context.routing["workspace"],
        "main_session_id": context.routing["main_session_id"],
        "main_model": context.main_model,
        "main_reasoning_effort": context.main_effort,
        "surface_identity": context.routing["surface_identity"],
        "surface_schema_fingerprint": context.routing[
            "surface_schema_fingerprint"
        ],
    }


def _start_adaptive_audit(
    packet: Any,
    *,
    ledger: Path,
    review_dir: Path,
    attestation_ledger: Path,
    require_existing_pre: bool = False,
) -> tuple[AdaptiveAuditContext | None, str | None]:
    package = _adaptive_package_binding(packet)
    if package is None:
        return None, None
    policy, binding = package
    contract, audit = _adaptive_modules()
    try:
        routing = contract.validate_routing_audit(packet.get("routing_audit"))
    except contract.PolicyContractError as exc:
        raise RuntimeError(f"invalid routing_audit: {exc.code}") from exc
    try:
        selected_route_fields = set(routing) & contract.ROUTING_AUDIT_ROUTE_FIELDS
        if selected_route_fields:
            route_id = routing["route_id"]
            selected_role = routing["role"]
            selected_model = routing["route_model"]
            selected_model_tier = routing["route_model_tier"]
            selected_effort = routing["route_reasoning_effort"]
        else:
            if (
                routing["attempt_index"] != 1
                or routing["selection_basis"] != "policy_default"
            ):
                raise contract.PolicyContractError(
                    "ROUTE_SELECTION_MISSING",
                    "non-default attempts require an explicit route selection",
                )
            route_id = policy["task_defaults"][routing["task_class"]]
            selected_role = binding["agent_type"]
            selected_model = binding["model"]
            selected_model_tier = binding["model_tier"]
            selected_effort = binding["reasoning_effort"]
        route = contract.validate_route_selection(
            policy,
            route_id=route_id,
            task_class=routing["task_class"],
            oracle_strength=routing["oracle_strength"],
            selection_basis=routing["selection_basis"],
            role=selected_role,
            model=selected_model,
            reasoning_effort=selected_effort,
            attempt_index=routing["attempt_index"],
            override_reason=routing.get("override_reason"),
        )
        if selected_model_tier != route["model_tier"]:
            raise contract.PolicyContractError(
                "ROUTE_TIER_MISMATCH",
                "selected route tier does not match the package route",
            )
        if (
            route["role"],
            route["model"],
            route["model_tier"],
            route["reasoning_effort"],
        ) != (
            binding["agent_type"],
            binding["model"],
            binding["model_tier"],
            binding["reasoning_effort"],
        ):
            raise contract.PolicyContractError(
                "ROUTE_BINDING_MISMATCH",
                "selected route does not match the installed package binding",
            )
    except (KeyError, TypeError, contract.PolicyContractError) as exc:
        raise RuntimeError("routing policy cannot attest the selected route") from exc
    routing = {
        **routing,
        "dispatch_id": packet["dispatch_id"].strip(),
        "route_id": route_id,
        "role": route["role"],
    }
    authority = packet.get("main_authority")
    observed_model = (
        authority.get("model") if isinstance(authority, dict) else "unknown"
    )
    observed_effort = (
        authority.get("reasoning_effort")
        if isinstance(authority, dict)
        else "unknown"
    )
    main_model = (
        observed_model
        if observed_model in (*audit.MODELS, "unknown")
        else "unknown"
    )
    main_effort = (
        observed_effort
        if observed_effort in (*audit.EFFORTS, "unknown")
        else "unknown"
    )
    policy_id = policy.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id:
        raise RuntimeError("adaptive package policy_id is invalid")
    context = AdaptiveAuditContext(
        policy=policy,
        routing=routing,
        binding=binding,
        main_model=main_model,
        main_effort=main_effort,
        policy_fingerprint=contract.canonical_policy_fingerprint(policy),
        ledger=ledger,
        review_dir=review_dir,
        attestation_ledger=attestation_ledger,
        started=time.monotonic(),
        contract_module=contract,
        audit_module=audit,
    )
    gate_warning: str | None = None
    try:
        contract.enforce_main_authority(
            policy, binding["agent_type"], authority
        )
    except contract.PolicyContractError as exc:
        if not exc.warning:
            raise RuntimeError(f"invalid adaptive authority policy: {exc.code}") from exc
        gate_warning = exc.warning
    pre_event = {
        "schema_version": audit.LINKED_SCHEMA_VERSION,
        "event_type": "pre_decision",
        "attempt_id": routing["dispatch_id"],
        "task_id": routing["task_id"],
        "attempt_index": routing["attempt_index"],
        "timestamp": routing["decision_timestamp"],
        "model": binding["model"],
        "model_tier": binding["model_tier"],
        "reasoning_effort": binding["reasoning_effort"],
        "route_id": routing["route_id"],
        "role": routing["role"],
        "rationale": {
            "task_class": routing["task_class"],
            "oracle_strength": routing["oracle_strength"],
            "risk_class": routing["risk_class"],
            "prior_failure_class": None,
            "prior_attempts": routing["attempt_index"] - 1,
            "selection_basis": routing["selection_basis"],
        },
        "planned_effort_escalations": routing["effort_escalations"],
        "planned_model_escalations": routing["model_escalations"],
        **_linked_fields(context),
    }
    if routing.get("override_reason") is not None:
        pre_event["override_reason"] = routing["override_reason"]
    if require_existing_pre and not audit.exact_unpaired_pre_exists(
        pre_event, ledger
    ):
        raise RuntimeError(
            "integration finalization requires an exact unpaired pre_decision"
        )
    try:
        audit.record_event(
            pre_event,
            ledger,
            review_dir,
            auto_review=True,
            idempotent=True,
        )
    except audit.AuditError as exc:
        raise RuntimeError("model-routing pre_decision record failed") from exc
    return context, gate_warning


def _configured_escalation_action(context: AdaptiveAuditContext) -> str:
    contract = context.contract_module
    ladder = contract.applicable_ladder(
        context.policy,
        context.routing["task_class"],
        context.routing["oracle_strength"],
    )
    try:
        current_index = ladder.index(context.routing["route_id"])
    except ValueError as exc:
        raise RuntimeError("current route is outside its configured ladder") from exc
    if current_index + 1 >= len(ladder):
        return "stop"
    current = contract.route_for(context.policy, ladder[current_index])
    following = contract.route_for(context.policy, ladder[current_index + 1])
    if following["authority"] == "main":
        return "main_takeover"
    if following["model"] == current["model"]:
        return "raise_effort"
    return "raise_model"


def _finish_adaptive_audit(
    context: AdaptiveAuditContext,
    status: dict[str, Any],
    result_code: int,
    *,
    failure_override: str | None = None,
) -> None:
    execution_completed = bool(status.get("execution_completed"))
    child_succeeded = bool(status.get("child_succeeded"))
    integration_accepted = (
        bool(status.get("integration_accepted"))
        and child_succeeded
        and result_code == 0
    )
    if integration_accepted:
        failure_class = "none"
    elif failure_override is not None:
        failure_class = failure_override
    elif isinstance(status.get("failure_class"), str):
        failure_class = status["failure_class"]
    elif child_succeeded:
        # A clean child exit without a separate receipt is deliberately not an
        # accepted outcome and therefore is not a no-failure acceptance claim.
        failure_class = "other"
    elif status.get("validate_only"):
        failure_class = "other"
    else:
        failure_class = "tool_or_environment"
    if integration_accepted:
        oracle_verdict = "pass"
        signals = ["accepted_by_oracle", "constraints_met", "output_complete"]
        route_assessment = "correct"
        next_action = "stop"
    elif failure_override == "policy_gate":
        oracle_verdict = "not_run"
        signals = ["constraints_missed", "evidence_inconclusive"]
        route_assessment = "inconclusive"
        next_action = "stop"
    elif failure_class in {
        "reasoning_insufficiency",
        "context_ceiling",
        "capability_ceiling",
    }:
        oracle_verdict = "fail"
        signals = {
            "reasoning_insufficiency": ["tests_failed", "evidence_inconclusive"],
            "context_ceiling": ["budget_exhausted", "output_incomplete"],
            "capability_ceiling": ["constraints_missed", "output_incomplete"],
        }[failure_class]
        route_assessment = "inconclusive"
        next_action = _configured_escalation_action(context)
    elif failure_class == "scope_or_retrieval_overbreadth":
        oracle_verdict = "fail"
        signals = ["constraints_missed", "output_incomplete"]
        route_assessment = "inconclusive"
        next_action = "narrow_scope"
    elif failure_class == "tool_or_environment":
        oracle_verdict = "fail"
        signals = ["tool_failure", "output_incomplete"]
        route_assessment = "inconclusive"
        next_action = "environment_retry"
    elif failure_class == "weak_oracle":
        oracle_verdict = "inconclusive"
        signals = ["evidence_inconclusive", "human_review_required"]
        route_assessment = "inconclusive"
        next_action = "main_takeover"
    elif child_succeeded:
        oracle_verdict = "inconclusive"
        signals = ["output_complete", "evidence_inconclusive", "human_review_required"]
        route_assessment = "inconclusive"
        next_action = "human_review"
    else:
        oracle_verdict = "not_run"
        signals = ["evidence_inconclusive"]
        route_assessment = "inconclusive"
        next_action = "stop" if status.get("validate_only") else "human_review"
    weighted_tokens = status.get("weighted_tokens")
    if not isinstance(weighted_tokens, int) or isinstance(weighted_tokens, bool):
        weighted_tokens = 0
    price = context.policy.get("price_evidence", {})
    fraction = 1.0
    if context.binding["model"] == "gpt-5.6-luna":
        fraction = float(price.get("luna_previous_price_fraction", 1.0))
    elif context.binding["model"] == "gpt-5.6-terra":
        fraction = float(price.get("terra_previous_price_fraction", 1.0))
    elapsed_ms = status.get("execution_elapsed_ms")
    if (
        isinstance(elapsed_ms, bool)
        or not isinstance(elapsed_ms, int)
        or elapsed_ms < 0
    ):
        elapsed_ms = max(0, int((time.monotonic() - context.started) * 1000))
    event = {
        "schema_version": context.audit_module.LINKED_SCHEMA_VERSION,
        "event_type": "post_result",
        "attempt_id": context.routing["dispatch_id"],
        "task_id": context.routing["task_id"],
        "attempt_index": context.routing["attempt_index"],
        "timestamp": _utc_timestamp(),
        "accepted": integration_accepted,
        "failure_class": failure_class,
        "effort_escalations": context.routing["effort_escalations"],
        "model_escalations": context.routing["model_escalations"],
        "final_model": context.binding["model"],
        "final_model_tier": context.binding["model_tier"],
        "final_reasoning_effort": context.binding["reasoning_effort"],
        "final_route_id": context.routing["route_id"],
        "final_role": context.routing["role"],
        "elapsed_ms": elapsed_ms,
        "weighted_tokens": weighted_tokens,
        "cost_proxy": round(weighted_tokens * fraction, 6),
        "post_result_detail": {
            "observable_result_signals": signals,
            "evidence_references": [str(context.attestation_ledger)],
            "route_assessment": route_assessment,
            "next_action": next_action,
            "token_observation": "exact" if weighted_tokens else "unavailable",
            "elapsed_observation": "exact",
        },
        "execution_completed": execution_completed,
        "oracle_verdict": oracle_verdict,
        "integration_accepted": integration_accepted,
        **_linked_fields(context),
    }
    try:
        context.audit_module.record_event(
            event,
            context.ledger,
            context.review_dir,
            auto_review=True,
            idempotent=False,
        )
    except context.audit_module.AuditError as exc:
        raise RuntimeError("model-routing post_result record failed") from exc


def _load_receipt(path: Path | None) -> ReceiptEnvelope | None:
    """Load a bounded receipt object; callers treat every other form as absent."""
    if path is None:
        return None
    if not _secure_owned_file(path, exact_mode=0o600):
        return None
    try:
        value = _load_json(path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return ReceiptEnvelope(value, path) if isinstance(value, dict) else None


def _safe_argv(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    if any(not isinstance(part, str) or not part or "\x00" in part for part in value):
        return None
    if Path(value[0]).name.lower() in SHELL_EXECUTABLES:
        return None
    return list(value)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _append_attestation(
    ledger: Path,
    *,
    packet: dict[str, Any],
    binding: RoleBinding,
    expected_session_id: str | None,
    runtime: RuntimeEvidence | None,
    source: dict[str, Any],
    verdict: str,
    reason: str,
    selected_launch_path: str,
    token_budget_observed: int | None = None,
    parent_enforced: bool = False,
    forbidden_leaf_tool_call: str | None = None,
    execution_policy_violation: str | None = None,
    observed_tool_calls: int = 0,
    observed_tool_output_bytes: int = 0,
    observed_child_stdout_bytes: int = 0,
    native_admission: dict[str, Any] | None = None,
    terminal_event: TerminalEvent | None = None,
    integration_gate: dict[str, Any] | None = None,
) -> None:
    # Construct the persisted record from an explicit allowlist. Packet text,
    # argv, credentials, environment values, and arbitrary evidence fields never
    # enter this object.
    record = {
        "dispatch_id": packet["dispatch_id"].strip(),
        "timestamp": _timestamp(),
        "configured_role": {
            "agent_type": binding.agent_type,
            "model_tier": binding.model_tier,
            "role_config": str(binding.role_config),
        },
        "runtime_expected": {
            "session_id": expected_session_id,
            "model": binding.model,
            "effort": binding.effort,
            "token_budget": packet["token_budget"],
        },
        "runtime_observed": (
            {
                "session_id": runtime.session_id,
                "model": runtime.model,
                "effort": runtime.effort,
            }
            if runtime is not None
            else None
        ),
        "observed_source": {
            "kind": source["kind"],
            "path": source["path"],
            "status": source["status"],
        },
        "verdict": verdict,
        "reason": reason,
        "selected_launch_path": selected_launch_path,
    }
    if native_admission is not None:
        record["native_admission"] = native_admission
    if terminal_event is not None:
        record["terminal_event"] = {
            "value": terminal_event.value,
            "digest": terminal_event.digest,
        }
    if integration_gate is not None:
        record["integration_gate"] = integration_gate
    execution_policy = _execution_policy(packet)
    if execution_policy is not None:
        record["execution_policy_expected"] = execution_policy.public_limits()
    v2_preflight = _v2_preflight(packet) if packet.get("packet_version") == V2_PACKET_VERSION else None
    if v2_preflight is not None:
        explicit_files, planning_target = v2_preflight
        record["packet_version"] = V2_PACKET_VERSION
        record["execution_estimate"] = {
            field: packet["execution_estimate"][field] for field in V2_ESTIMATE_FIELDS
        }
        record["prelaunch_minima"] = {
            field: packet["prelaunch_minima"][field] for field in V2_ESTIMATE_FIELDS
        }
        record["explicit_file_rg"] = {
            "classification": "explicit_files",
            "paths": explicit_files,
        }
        record["continuation_receipt"] = _v2_delta_receipt(packet)
        record["token_budget_observation"] = {
            "planning_target": planning_target,
            "observed": token_budget_observed,
            "parent_enforced": parent_enforced,
        }
    elif token_budget_observed is not None:
        record["token_budget_observation"] = {
            "planning_target": packet["token_budget"],
            "observed": token_budget_observed,
            "parent_enforced": parent_enforced,
        }
    if runtime is not None:
        record["resource_observation"] = {
            "planned_tool_calls": (
                execution_policy.max_tool_calls if execution_policy is not None else None
            ),
            "observed_tool_calls": observed_tool_calls,
            "planned_cumulative_tool_output_bytes": (
                execution_policy.max_cumulative_tool_output_bytes
                if execution_policy is not None
                else None
            ),
            "observed_tool_output_bytes": observed_tool_output_bytes,
            "planned_child_stdout_bytes": (
                execution_policy.max_child_stdout_bytes
                if execution_policy is not None
                else None
            ),
            "observed_child_stdout_bytes": observed_child_stdout_bytes,
            "quantitative_caps_enforced": parent_enforced,
        }
    if forbidden_leaf_tool_call is not None:
        record["leaf_isolation"] = {
            "forbidden_tool_call": forbidden_leaf_tool_call,
            "parent_enforced": parent_enforced,
        }
    if execution_policy_violation is not None:
        record["execution_policy_enforcement"] = {
            "violation": execution_policy_violation,
            "observed_tool_calls": observed_tool_calls,
            "observed_tool_output_bytes": observed_tool_output_bytes,
            "observed_child_stdout_bytes": observed_child_stdout_bytes,
            "parent_enforced": parent_enforced,
            "feedback_action": "main_replan_and_relaunch",
        }
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    ledger.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(ledger, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("ledger_write_failed")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _isolated_child_environment(runtime_home: Path) -> dict[str, str]:
    """Build the only environment a bounded child is permitted to inherit."""
    environment = {
        key: value
        for key in CHILD_ENV_ALLOWLIST
        if isinstance((value := os.environ.get(key)), str) and value
    }
    environment["CODEX_HOME"] = str(runtime_home)
    environment["HOME"] = str(runtime_home)
    return environment


def _run_argv_with_output_digest(
    argv: list[str], environment: dict[str, str]
) -> tuple[int | None, str | None]:
    """Run one protected command while preserving its output and terminal digest."""
    digest = hashlib.sha256()
    try:
        process = subprocess.Popen(
            argv,
            shell=False,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError:
        return None, None
    assert process.stdout is not None
    try:
        while chunk := process.stdout.read(64 * 1024):
            digest.update(chunk)
            stream = getattr(sys.stdout, "buffer", None)
            if stream is not None:
                stream.write(chunk)
                stream.flush()
            else:
                sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                sys.stdout.flush()
    finally:
        process.stdout.close()
    return process.wait(), digest.hexdigest()


def _attest_native(
    *,
    packet: Any,
    rollout: Path | None,
    session_id: str | None,
    argv: Any,
    ledger: Path,
    match_path: str,
    mismatch_path: str,
    unavailable_path: str,
    validate_only: bool,
    native_admission: Any = None,
    execution_status: dict[str, Any] | None = None,
) -> Outcome:
    validation_error = _validate_packet(packet, rollout)
    if validation_error is not None:
        return Outcome("invalid_packet")

    binding = _role_binding(packet)
    if binding is None:
        return Outcome("unsafe")

    expected_session_id = _canonical_uuid(session_id)
    source = {
        "kind": "codex_rollout" if rollout is not None else "none",
        "path": str(rollout) if rollout is not None else packet["evidence_path"],
        "status": "unavailable",
    }
    admission = _native_structural_admission(
        native_admission,
        binding,
        dispatch_id=packet["dispatch_id"].strip(),
    )
    if admission["status"] != "structurally_eligible":
        _append_attestation(
            ledger,
            packet=packet,
            binding=binding,
            expected_session_id=_canonical_uuid(session_id),
            runtime=None,
            source=source,
            verdict="native_admission_rejected",
            reason=admission["rejection_reason"],
            selected_launch_path=unavailable_path,
            native_admission=admission,
        )
        return Outcome("unavailable")
    runtime = None
    if rollout is not None and expected_session_id is not None:
        runtime = _trusted_rollout(rollout, expected_session_id)
        source["status"] = "trusted" if runtime is not None else "trust_validation_failed"

    if runtime is None:
        _append_attestation(
            ledger,
            packet=packet,
            binding=binding,
            expected_session_id=expected_session_id,
            runtime=None,
            source=source,
            verdict="unavailable",
            reason="trusted_rollout_unavailable",
            selected_launch_path=unavailable_path,
            native_admission=admission,
        )
        return Outcome("unavailable")

    if runtime.model != binding.model or runtime.effort != binding.effort:
        _append_attestation(
            ledger,
            packet=packet,
            binding=binding,
            expected_session_id=expected_session_id,
            runtime=runtime,
            source=source,
            verdict="mismatch",
            reason="runtime_model_or_effort_mismatch",
            selected_launch_path=mismatch_path,
            native_admission=admission,
        )
        return Outcome("mismatch")

    protected_argv = _canonical_resume_binding(
        argv, binding, expected_session_id, packet["objective"]
    )
    if protected_argv is None:
        _append_attestation(
            ledger,
            packet=packet,
            binding=binding,
            expected_session_id=expected_session_id,
            runtime=runtime,
            source=source,
            verdict="unsafe_launch_path",
            reason="protected_resume_binding_mismatch",
            selected_launch_path="none",
            native_admission=admission,
        )
        return Outcome("unsafe")

    admission = _native_admission_provenance(
        native_admission,
        admission,
        binding,
        dispatch_id=packet["dispatch_id"].strip(),
        rollout=rollout,
        session_id=expected_session_id,
    )
    if admission["status"] != "eligible":
        _append_attestation(
            ledger,
            packet=packet,
            binding=binding,
            expected_session_id=expected_session_id,
            runtime=runtime,
            source=source,
            verdict="native_admission_rejected",
            reason=admission["rejection_reason"],
            selected_launch_path=unavailable_path,
            native_admission=admission,
        )
        return Outcome("unavailable")

    _append_attestation(
        ledger,
        packet=packet,
        binding=binding,
        expected_session_id=expected_session_id,
        runtime=runtime,
        source=source,
        verdict="match",
        reason="trusted_rollout_and_resume_binding_matched",
        selected_launch_path=match_path,
        native_admission=admission,
    )
    if validate_only:
        return Outcome("success", EXIT_SUCCESS)
    if execution_status is not None:
        execution_status["process_started"] = True
    execution_started = time.monotonic()
    child_returncode, output_digest = _run_argv_with_output_digest(
        protected_argv, _isolated_child_environment(CODEX_HOME)
    )
    execution_elapsed_ms = max(
        0, int((time.monotonic() - execution_started) * 1000)
    )
    protected_succeeded = child_returncode == EXIT_SUCCESS
    terminal_event = _capture_terminal_event(
        packet=packet,
        binding=binding,
        runtime=runtime,
        rollout=rollout,
        rollout_runtime_home="main",
        selected_launch_path=match_path,
        child_returncode=child_returncode,
        output_digest=output_digest,
        parent_enforced=False,
        execution_elapsed_ms=execution_elapsed_ms,
    )
    if execution_status is not None:
        execution_status.update(
            execution_completed=child_returncode is not None,
            child_succeeded=protected_succeeded,
            integration_accepted=False,
            execution_elapsed_ms=execution_elapsed_ms,
        )
    _append_attestation(
        ledger,
        packet=packet,
        binding=binding,
        expected_session_id=expected_session_id,
        runtime=runtime,
        source=source,
        verdict="protected_completed" if protected_succeeded else "protected_failed",
        reason=(
            "protected_resume_completed"
            if protected_succeeded
            else "protected_resume_failed"
        ),
        selected_launch_path=match_path,
        native_admission=admission,
        terminal_event=terminal_event,
    )
    if not protected_succeeded:
        return Outcome("command_failed", child_returncode)
    return Outcome("success", child_returncode)


def _secure_owned_file(path: Path, exact_mode: int | None = None) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return bool(
        stat.S_ISREG(metadata.st_mode)
        and not path.is_symlink()
        and metadata.st_uid == os.getuid()
        and not metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        and (exact_mode is None or stat.S_IMODE(metadata.st_mode) == exact_mode)
    )


def _canonical_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
    canonical = str(parsed)
    return canonical if value == canonical else None


def _secure_rollout_path(
    path: Path,
    *,
    codex_home: Path = CODEX_HOME,
    sessions_root: Path = SESSIONS_ROOT,
) -> tuple[re.Match[str], tuple[str, str, str]] | None:
    try:
        resolved_codex_home = codex_home.resolve(strict=True)
        resolved_sessions_root = sessions_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        if (
            resolved_codex_home != codex_home
            or resolved_sessions_root != sessions_root
            or resolved != path
        ):
            return None
        relative = resolved.relative_to(resolved_sessions_root)
    except (OSError, ValueError):
        return None
    if len(relative.parts) != 4:
        return None
    year, month, day, filename = relative.parts
    if not re.fullmatch(r"\d{4}", year) or not re.fullmatch(r"\d{2}", month) or not re.fullmatch(r"\d{2}", day):
        return None
    match = ROLLOUT_PATTERN.fullmatch(filename)
    if match is None or match.group("date") != f"{year}-{month}-{day}":
        return None

    chain = [
        codex_home,
        sessions_root,
        sessions_root / year,
        sessions_root / year / month,
        sessions_root / year / month / day,
        resolved,
    ]
    for index, component in enumerate(chain):
        try:
            metadata = component.lstat()
        except OSError:
            return None
        if component.is_symlink() or metadata.st_uid != os.getuid():
            return None
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            return None
        if index == len(chain) - 1:
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
                return None
        elif not stat.S_ISDIR(metadata.st_mode):
            return None
    return match, (year, month, day)


def _trusted_rollout(
    path: Path,
    expected_session_id: str,
    *,
    codex_home: Path = CODEX_HOME,
    sessions_root: Path = SESSIONS_ROOT,
) -> RuntimeEvidence | None:
    trusted_path = _secure_rollout_path(
        path, codex_home=codex_home, sessions_root=sessions_root
    )
    if trusted_path is None:
        return None
    match, _ = trusted_path
    filename_session_id = match.group("session_id")
    if filename_session_id != expected_session_id:
        return None

    session_ids: tuple[str, str] | None = None
    runtime: tuple[str, str] | None = None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 100_000_000
        ):
            os.close(descriptor)
            return None
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                if len(raw_line) > 8_000_000:
                    return None
                if not raw_line.strip():
                    continue
                record = json.loads(raw_line)
                if not isinstance(record, dict):
                    return None
                record_type = record.get("type")
                if record_type not in {"session_meta", "turn_context"}:
                    continue
                if set(record) - {"timestamp", "type", "payload"}:
                    return None
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    return None
                if record_type == "session_meta":
                    meta_id = _canonical_uuid(payload.get("id"))
                    meta_session_id = _canonical_uuid(payload.get("session_id"))
                    if meta_id is None or meta_session_id is None:
                        return None
                    current_ids = (meta_id, meta_session_id)
                    if session_ids is not None and session_ids != current_ids:
                        return None
                    session_ids = current_ids
                else:
                    model = payload.get("model")
                    effort = payload.get("effort")
                    if not isinstance(model, str) or not model or not isinstance(effort, str) or not effort:
                        return None
                    runtime = (model, effort)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    if session_ids != (expected_session_id, expected_session_id) or runtime is None:
        return None
    return RuntimeEvidence(expected_session_id, runtime[0], runtime[1])


def _rollout_has_receipt_marker(
    rollout: Path | None, session_id: str | None, receipt: dict[str, Any]
) -> bool:
    """A receipt is usable only when its exact payload is recorded by its rollout."""
    if rollout is None or session_id is None or _trusted_rollout(rollout, session_id) is None:
        return False
    expected = {
        "receipt_kind": receipt.get("receipt_kind"),
        "receipt_version": receipt.get("receipt_version"),
        "payload_digest": _canonical_digest(receipt),
    }
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(rollout, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                if len(raw_line) > 8_000_000:
                    return False
                record = json.loads(raw_line)
                if (
                    isinstance(record, dict)
                    and record.get("type") == RECEIPT_MARKER_TYPE
                    and set(record) == {"timestamp", "type", "payload"}
                    and record.get("payload") == expected
                ):
                    return True
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return False


def _leaf_rollout_for_session(runtime_home: Path, session_id: str) -> Path | None:
    sessions_root = runtime_home / "sessions"
    try:
        matches = list(
            sessions_root.glob(f"*/*/*/rollout-*-{session_id}.jsonl")
        )
    except OSError:
        return None
    if len(matches) != 1:
        return None
    path = matches[0]
    return (
        path
        if _secure_rollout_path(
            path, codex_home=runtime_home, sessions_root=sessions_root
        )
        is not None
        else None
    )


def _trusted_leaf_token_monitor(
    runtime_home: Path, session_id: str, execution_policy: ExecutionPolicy
) -> tuple[Path, RuntimeEvidence, RolloutTokenMonitor] | None:
    rollout = _leaf_rollout_for_session(runtime_home, session_id)
    if rollout is None:
        return None
    runtime = _trusted_rollout(
        rollout,
        session_id,
        codex_home=runtime_home,
        sessions_root=runtime_home / "sessions",
    )
    if runtime is None:
        return None
    monitor = _open_rollout_token_monitor(rollout, execution_policy)
    if monitor is None:
        return None
    return rollout, runtime, monitor


def _role_binding(packet: dict[str, Any]) -> RoleBinding | None:
    agent_type = packet["agent_type"].strip()
    role_config = _role_config_path(agent_type)
    if role_config is None:
        return None
    try:
        with role_config.open("rb") as handle:
            role = tomllib.load(handle)
    except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError):
        return None

    role_name = role.get("name")
    model = role.get("model")
    effort = role.get("model_reasoning_effort")
    instructions = role.get("developer_instructions")
    if not all(isinstance(value, str) and value for value in (role_name, model, effort, instructions)):
        return None
    model_tier = packet["model_tier"].strip()
    _declared, package_valid = _package_policy_binding(
        agent_type=agent_type,
        model_tier=model_tier,
        model=model,
        effort=effort,
    )
    if (
        role_name != agent_type
        or packet["reasoning_effort"].strip() != effort
        or not package_valid
    ):
        return None
    return RoleBinding(agent_type, model_tier, model, effort, instructions, role_config)


def _installed_integration_checker_binding() -> RoleBinding | None:
    """Return only the package-declared independent integration checker."""
    agent_type = INTEGRATION_CHECKER_AGENT_TYPE
    role_config = _role_config_path(agent_type)
    if role_config is None or not _secure_owned_file(role_config, exact_mode=0o600):
        return None
    try:
        with role_config.open("rb") as handle:
            role = tomllib.load(handle)
    except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError):
        return None
    model = role.get("model")
    effort = role.get("model_reasoning_effort")
    instructions = role.get("developer_instructions")
    if (
        role.get("name") != agent_type
        or not all(isinstance(value, str) and value for value in (model, effort, instructions))
    ):
        return None
    _declared, package_valid = _package_policy_binding(
        agent_type=agent_type,
        model_tier=None,
        model=model,
        effort=effort,
    )
    if not package_valid:
        return None
    _policy_declared, policy = _load_routing_policy()
    if policy is None:
        return None
    role_bindings = policy.get("role_bindings")
    checker_policy = (
        role_bindings.get(agent_type) if isinstance(role_bindings, dict) else None
    )
    model_tier = (
        checker_policy.get("model_tier")
        if isinstance(checker_policy, dict)
        else None
    )
    if not isinstance(model_tier, str):
        return None
    return RoleBinding(agent_type, model_tier, model, effort, instructions, role_config)


def _secure_leaf_runtime_home(path: Path) -> bool:
    try:
        expected = LEAF_RUNTIME_HOME.resolve(strict=True)
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
    except OSError:
        return False
    if (
        path.is_symlink()
        or resolved != expected
        or metadata.st_uid != os.getuid()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        return False

    auth_source = CODEX_HOME / "auth.json"
    auth_link = path / "auth.json"
    try:
        if (
            not _secure_owned_file(auth_source, exact_mode=0o600)
            or not auth_link.is_symlink()
            or auth_link.resolve(strict=True) != auth_source.resolve(strict=True)
        ):
            return False
    except OSError:
        return False

    return not any(
        (path / name).exists() or (path / name).is_symlink()
        for name in ("AGENTS.md", "AGENTS.override.md", "plugins")
    )


def _sandbox_for_packet(packet: dict[str, Any]) -> str | None:
    write_scope = packet.get("write_scope")
    if not isinstance(write_scope, list) or not write_scope:
        return None
    if write_scope == ["read-only"]:
        return "read-only"
    if any(not isinstance(path, str) or not path.strip() for path in write_scope):
        return None
    return "workspace-write"


def _writable_roots(packet: dict[str, Any]) -> list[str]:
    if packet.get("write_scope") == ["read-only"]:
        return []
    roots: list[str] = []
    for value in packet.get("write_scope", []):
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve(strict=False)
        root = resolved if resolved.is_dir() else resolved.parent
        rendered = str(root)
        if rendered not in roots:
            roots.append(rendered)
    return roots


def _worktree_digest(packet: dict[str, Any]) -> str | None:
    """Digest the declared mutable scope after the child has stopped."""
    if packet.get("write_scope") == ["read-only"]:
        return None
    values = packet.get("write_scope")
    if not isinstance(values, list) or not values:
        return None
    digest = hashlib.sha256()

    def add(kind: str, relative: str, mode: int, content: str | None = None) -> None:
        digest.update(
            json.dumps(
                [kind, relative, mode, content],
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")

    def visit(path: Path, relative: str) -> bool:
        try:
            metadata = path.lstat()
        except OSError:
            return False
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISLNK(metadata.st_mode):
            try:
                add("symlink", relative, mode, os.readlink(path))
            except OSError:
                return False
            return True
        if stat.S_ISDIR(metadata.st_mode):
            add("directory", relative, mode)
            try:
                children = sorted(path.iterdir(), key=lambda child: child.name)
            except OSError:
                return False
            return all(
                visit(child, f"{relative}/{child.name}") for child in children
            )
        if not stat.S_ISREG(metadata.st_mode):
            return False
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as handle:
                opened = os.fstat(handle.fileno())
                if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                    return False
                contents = hashlib.sha256()
                while chunk := handle.read(64 * 1024):
                    contents.update(chunk)
            current = path.lstat()
        except OSError:
            return False
        if (
            (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
            != (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        ):
            return False
        add("file", relative, mode, contents.hexdigest())
        return True

    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not visit(path, f"scope-{index}"):
            return None
    return digest.hexdigest()


def _budget_configs(packet: dict[str, Any]) -> tuple[str, str]:
    target = int(packet["token_budget"])
    reminder = max(250, min(2_000, target // 5))
    rollout_budget = (
        "features.rollout_budget={enabled=true,"
        f"limit_tokens={target},"
        f"reminder_at_remaining_tokens=[{reminder}],"
        "sampling_token_weight=1.0,prefill_token_weight=0.25}"
    )
    token_guidance = (
        "features.token_budget={enabled=true,"
        f"reminder_threshold_tokens={reminder},"
        "guidance_message="
        + json.dumps(
            f"This typed child has a binding {target}-weighted-token budget. "
            "Return concise evidence and stop before the limit."
        )
        + ",reminder_message_template="
        + json.dumps(
            "{n_remaining} weighted tokens remain; return evidence and stop."
        )
        + "}"
    )
    return rollout_budget, token_guidance


def _typed_objective(packet: dict[str, Any]) -> str:
    contract = {
        "agent_type": packet["agent_type"],
        "model_tier": packet["model_tier"],
        "reasoning_effort": packet["reasoning_effort"],
        "network_access": packet.get("network_access", False),
        "write_scope": packet["write_scope"],
        "resource_cap": packet["resource_cap"],
        "stop_condition": packet["stop_condition"],
        "token_budget": packet["token_budget"],
    }
    for field in (
        "packet_version",
        "read_scope",
        "explicit_file_rg_argv",
        "execution_estimate",
        "prelaunch_minima",
        "parent",
        "checkpoint",
        "delta",
    ):
        if field in packet:
            contract[field] = packet[field]
    return (
        packet["objective"].rstrip()
        + "\n\nADAPTIVE_DISPATCH_CONTRACT (binding):\n"
        + json.dumps(contract, sort_keys=True, separators=(",", ":"))
    )


def _typed_exec_tail(
    binding: RoleBinding, packet: dict[str, Any]
) -> list[str] | None:
    sandbox = _sandbox_for_packet(packet)
    if sandbox is None:
        return None
    rollout_budget, token_guidance = _budget_configs(packet)
    tail = [
        "exec",
        "--ignore-user-config",
        "--disable",
        "apps",
        "--disable",
        "plugins",
        "--disable",
        "multi_agent",
        "--sandbox",
        sandbox,
        "--config",
        'approval_policy="never"',
        "--config",
        f"project_doc_max_bytes={PROJECT_DOC_MAX_BYTES}",
    ]
    for writable_root in _writable_roots(packet):
        tail.extend(["--add-dir", writable_root])
    if packet.get("network_access", False):
        tail.extend(
            ["--config", "sandbox_workspace_write.network_access=true"]
        )
    tail.extend(
        [
            "--config",
            rollout_budget,
            "--config",
            token_guidance,
            "--model",
            binding.model,
            "--config",
            "model_reasoning_effort=" + json.dumps(binding.effort),
            "--config",
            "developer_instructions=" + json.dumps(binding.instructions),
            "--",
            _typed_objective(packet),
        ]
    )
    return tail


def _canonical_resume_binding(
    value: Any,
    binding: RoleBinding,
    session_id: str,
    objective: str,
) -> list[str] | None:
    argv = _safe_argv(value)
    codex = shutil.which("codex")
    resolved_codex = _resolved_executable(codex) if codex is not None else None
    if (
        argv is None
        or resolved_codex is None
        or _resolved_executable(argv[0]) != resolved_codex
    ):
        return None
    expected_tail = [
        "exec",
        "--ignore-user-config",
        "--disable",
        "apps",
        "--disable",
        "plugins",
        "--disable",
        "multi_agent",
        "resume",
        "--model",
        binding.model,
        "--config",
        "model_reasoning_effort=" + json.dumps(binding.effort),
        "--config",
        "developer_instructions=" + json.dumps(binding.instructions),
        "--",
        session_id,
        objective,
    ]
    return [str(resolved_codex), *expected_tail] if argv[1:] == expected_tail else None


def _resolved_executable(value: str) -> Path | None:
    candidate = shutil.which(value) if "/" not in value else value
    if not candidate:
        return None
    try:
        return Path(candidate).resolve(strict=True)
    except OSError:
        return None


def _typed_launch_binding(
    payload: dict[str, Any], expected_type: str, dispatched_packet: dict[str, Any]
) -> RecoveryLaunch | None:
    if payload.get("launch_type") != expected_type:
        return None
    packet = payload.get("packet")
    agent_type = payload.get("agent_type")
    role_config_value = payload.get("role_config")
    runtime_home_value = payload.get("runtime_home")
    argv = _safe_argv(payload.get("argv"))
    if (
        not isinstance(packet, dict)
        or not isinstance(agent_type, str)
        or not agent_type.strip()
        or not isinstance(role_config_value, str)
        or not isinstance(runtime_home_value, str)
        or argv is None
    ):
        return None

    role_config = Path(role_config_value)
    expected_role_config = _role_config_path(agent_type)
    if expected_role_config is None:
        return None
    try:
        if role_config.resolve(strict=True) != expected_role_config.resolve(strict=True):
            return None
    except OSError:
        return None
    if not _secure_owned_file(role_config):
        return None
    if _validate_packet(packet, role_config) is not None:
        return None
    if (
        _validate_packet(dispatched_packet, None) is not None
        or _canonical_digest(packet) != _canonical_digest(dispatched_packet)
        or packet["dispatch_id"].strip() != dispatched_packet["dispatch_id"].strip()
        or _intended_triple(packet) != _intended_triple(dispatched_packet)
    ):
        return None
    if packet["agent_type"].strip() != agent_type:
        return None

    binding = _role_binding(packet)
    if binding is None or binding.agent_type != agent_type or binding.role_config != role_config:
        return None

    runtime_home = Path(runtime_home_value)
    if not _secure_leaf_runtime_home(runtime_home):
        return None

    codex = shutil.which("codex")
    if codex is None or _resolved_executable(argv[0]) != _resolved_executable(codex):
        return None
    expected_argv_tail = _typed_exec_tail(binding, packet)
    if expected_argv_tail is None or argv[1:] != expected_argv_tail:
        return None

    source = {
        "kind": "installed_role_config",
        "path": str(role_config),
        "status": "configuration_only",
    }
    return RecoveryLaunch(expected_type, packet, argv, binding, source, runtime_home)


def _load_recovery(
    path: Path, expected_type: str, dispatched_packet: dict[str, Any]
) -> RecoveryLaunch | None:
    try:
        payload = _load_json(path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return _typed_launch_binding(payload, expected_type, dispatched_packet)


def _direct_typed_launch(packet: dict[str, Any]) -> RecoveryLaunch | None:
    agent_type = packet.get("agent_type")
    if not isinstance(agent_type, str) or not agent_type.strip():
        return None
    role_config = _role_config_path(agent_type.strip())
    if role_config is None:
        return None
    if _validate_packet(packet, role_config) is not None:
        return None
    binding = _role_binding(packet)
    if binding is None or not _secure_leaf_runtime_home(LEAF_RUNTIME_HOME):
        return None
    codex = shutil.which("codex")
    tail = _typed_exec_tail(binding, packet)
    if codex is None or tail is None:
        return None
    source = {
        "kind": "installed_role_config",
        "path": str(role_config),
        "status": "configuration_only",
    }
    return RecoveryLaunch(
        "typed_external_worker",
        packet,
        [codex, *tail],
        binding,
        source,
        LEAF_RUNTIME_HOME,
    )


def _run_recovery(
    launch: RecoveryLaunch,
    ledger: Path,
    failure_code: int,
    validate_only: bool,
    execution_status: dict[str, Any] | None = None,
) -> int:
    execution_policy = _execution_policy(launch.packet)
    if execution_policy is None:
        return failure_code
    _append_attestation(
        ledger,
        packet=launch.packet,
        binding=launch.binding,
        expected_session_id=None,
        runtime=None,
        source=launch.observed_source,
        verdict="launch_config_match",
        reason="installed_role_config_and_argv_matched",
        selected_launch_path=launch.launch_type,
    )
    if validate_only:
        return EXIT_SUCCESS
    child_environment = _isolated_child_environment(launch.runtime_home)
    session_id: str | None = None
    session_id_conflict = False
    rollout: Path | None = None
    budget_runtime: RuntimeEvidence | None = None
    budget_monitor: RolloutTokenMonitor | None = None
    observed_weighted_tokens: int | None = None
    forbidden_leaf_tool_call: str | None = None
    execution_policy_violation: str | None = None
    observed_child_stdout_bytes = 0
    child_output_digest = hashlib.sha256()
    execution_started = time.monotonic()
    try:
        process = subprocess.Popen(
            launch.argv,
            shell=False,
            env=child_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except OSError:
        return failure_code
    if execution_status is not None:
        execution_status["process_started"] = True
    assert process.stdout is not None
    child_output: queue.Queue[str | None] = queue.Queue()

    def read_child_output() -> None:
        try:
            for output_line in process.stdout:
                child_output.put(output_line)
        finally:
            child_output.put(None)

    output_thread = threading.Thread(target=read_child_output, daemon=True)
    output_thread.start()
    output_closed = False
    while process.poll() is None or not output_closed:
        received_output = False
        try:
            line = child_output.get(timeout=TOKEN_MONITOR_POLL_SECONDS)
            received_output = True
        except queue.Empty:
            line = None
        if received_output and line is None:
            output_closed = True
        elif line is not None:
            encoded_line = line.encode("utf-8", errors="replace")
            observed_child_stdout_bytes += len(encoded_line)
            child_output_digest.update(encoded_line)
            sys.stdout.write(line)
            sys.stdout.flush()
            match = SESSION_ID_OUTPUT_PATTERN.fullmatch(line.rstrip("\r\n"))
            if match is not None:
                observed_session_id = match.group("session_id")
                if session_id is not None and session_id != observed_session_id:
                    session_id_conflict = True
                elif not session_id_conflict:
                    session_id = observed_session_id
            if (
                observed_child_stdout_bytes
                > execution_policy.max_child_stdout_bytes
                and execution_policy_violation is None
            ):
                execution_policy_violation = "child_stdout_bytes_exceeded"
                _terminate_child_group(process)

        if session_id_conflict and budget_monitor is not None:
            budget_monitor.close()
            budget_monitor = None
            budget_runtime = None
            rollout = None
        if (
            not session_id_conflict
            and session_id is not None
            and budget_monitor is None
        ):
            trusted_monitor = _trusted_leaf_token_monitor(
                launch.runtime_home, session_id, execution_policy
            )
            if trusted_monitor is not None:
                rollout, budget_runtime, budget_monitor = trusted_monitor
        if budget_monitor is not None:
            observed_weighted_tokens = budget_monitor.poll()
            if (
                observed_weighted_tokens is not None
                and observed_weighted_tokens >= int(launch.packet["token_budget"])
                and execution_policy_violation is None
            ):
                execution_policy_violation = "token_budget_exceeded"
                _terminate_child_group(process)
            if (
                budget_monitor.execution_policy_violation is not None
                and execution_policy_violation is None
            ):
                execution_policy_violation = (
                    budget_monitor.execution_policy_violation
                )
                _terminate_child_group(process)
            if (
                budget_monitor.forbidden_leaf_tool_call is not None
                and forbidden_leaf_tool_call is None
            ):
                forbidden_leaf_tool_call = budget_monitor.forbidden_leaf_tool_call
                _terminate_child_group(process)
    child_returncode = process.wait()
    execution_elapsed_ms = max(
        0, int((time.monotonic() - execution_started) * 1000)
    )
    if execution_status is not None:
        execution_status.update(
            execution_completed=True,
            child_succeeded=child_returncode == EXIT_SUCCESS,
            execution_elapsed_ms=execution_elapsed_ms,
        )
    output_thread.join(timeout=CHILD_GROUP_TERM_GRACE_SECONDS)

    if session_id_conflict:
        session_id = None
    elif session_id is not None and budget_monitor is None:
        trusted_monitor = _trusted_leaf_token_monitor(
            launch.runtime_home, session_id, execution_policy
        )
        if trusted_monitor is not None:
            rollout, budget_runtime, budget_monitor = trusted_monitor
    if budget_monitor is not None:
        observed_weighted_tokens = budget_monitor.poll(final=True)
        if (
            observed_weighted_tokens is not None
            and observed_weighted_tokens >= int(launch.packet["token_budget"])
            and execution_policy_violation is None
        ):
            execution_policy_violation = "token_budget_exceeded"
        execution_policy_violation = (
            execution_policy_violation
            or budget_monitor.execution_policy_violation
        )
        forbidden_leaf_tool_call = (
            forbidden_leaf_tool_call or budget_monitor.forbidden_leaf_tool_call
        )
        budget_monitor.close()
    if rollout is None and session_id is not None:
        rollout = _leaf_rollout_for_session(launch.runtime_home, session_id)
    runtime = (
        _trusted_rollout(
            rollout,
            session_id,
            codex_home=launch.runtime_home,
            sessions_root=launch.runtime_home / "sessions",
        )
        if rollout is not None and session_id is not None
        else None
    )
    source = {
        "kind": "codex_rollout" if rollout is not None else "none",
        "path": str(rollout) if rollout is not None else launch.packet["evidence_path"],
        "status": "trusted" if runtime is not None else "unavailable",
    }
    if execution_status is not None:
        execution_status["weighted_tokens"] = observed_weighted_tokens
        execution_status["integration_accepted"] = False
    terminal_event = _capture_terminal_event(
        packet=launch.packet,
        binding=launch.binding,
        runtime=runtime,
        rollout=rollout,
        rollout_runtime_home="leaf",
        selected_launch_path=launch.launch_type,
        child_returncode=child_returncode,
        output_digest=child_output_digest.hexdigest(),
        parent_enforced=True,
        weighted_tokens=observed_weighted_tokens,
        execution_elapsed_ms=execution_elapsed_ms,
    )
    if execution_policy_violation is not None:
        if execution_status is not None:
            execution_status["failure_class"] = (
                "context_ceiling"
                if execution_policy_violation == "token_budget_exceeded"
                else "scope_or_retrieval_overbreadth"
            )
            execution_status["failure_signal"] = (
                "budget_exhausted"
                if execution_policy_violation == "token_budget_exceeded"
                else "scope_violation"
            )
        _append_attestation(
            ledger,
            packet=launch.packet,
            binding=launch.binding,
            expected_session_id=session_id,
            runtime=runtime or budget_runtime,
            source=source,
            verdict="execution_policy_violation",
            reason="parent_enforced_execution_policy_violation",
            selected_launch_path=launch.launch_type,
            token_budget_observed=observed_weighted_tokens,
            parent_enforced=True,
            execution_policy_violation=execution_policy_violation,
            observed_tool_calls=(
                budget_monitor.observed_tool_calls if budget_monitor is not None else 0
            ),
            observed_tool_output_bytes=(
                budget_monitor.observed_tool_output_bytes
                if budget_monitor is not None
                else 0
            ),
            observed_child_stdout_bytes=observed_child_stdout_bytes,
            terminal_event=terminal_event,
        )
        return failure_code
    if (
        forbidden_leaf_tool_call is not None
        and budget_runtime is not None
        and rollout is not None
    ):
        leaf_source = dict(source)
        leaf_source["status"] = "trusted"
        _append_attestation(
            ledger,
            packet=launch.packet,
            binding=launch.binding,
            expected_session_id=session_id,
            runtime=budget_runtime,
            source=leaf_source,
            verdict="forbidden_leaf_tool_call",
            reason="parent_blocked_nested_collaboration",
            selected_launch_path=launch.launch_type,
            parent_enforced=True,
            forbidden_leaf_tool_call=forbidden_leaf_tool_call,
            terminal_event=terminal_event,
        )
        return failure_code
    if runtime is None:
        _append_attestation(
            ledger,
            packet=launch.packet,
            binding=launch.binding,
            expected_session_id=session_id,
            runtime=None,
            source=source,
            verdict="runtime_unavailable",
            reason="typed_runtime_evidence_unavailable",
            selected_launch_path=launch.launch_type,
        )
        return failure_code
    if runtime.model != launch.binding.model or runtime.effort != launch.binding.effort:
        _append_attestation(
            ledger,
            packet=launch.packet,
            binding=launch.binding,
            expected_session_id=session_id,
            runtime=runtime,
            source=source,
            verdict="runtime_mismatch",
            reason="typed_runtime_model_or_effort_mismatch",
            selected_launch_path=launch.launch_type,
        )
        return failure_code

    child_succeeded = child_returncode == EXIT_SUCCESS
    _append_attestation(
        ledger,
        packet=launch.packet,
        binding=launch.binding,
        expected_session_id=session_id,
        runtime=runtime,
        source=source,
        verdict="typed_completed" if child_succeeded else "typed_failed",
        reason=(
            "typed_worker_completed" if child_succeeded else "typed_worker_failed"
        ),
        selected_launch_path=launch.launch_type,
        token_budget_observed=observed_weighted_tokens,
        parent_enforced=True,
        observed_tool_calls=(
            budget_monitor.observed_tool_calls if budget_monitor is not None else 0
        ),
        observed_tool_output_bytes=(
            budget_monitor.observed_tool_output_bytes if budget_monitor is not None else 0
        ),
        observed_child_stdout_bytes=observed_child_stdout_bytes,
        terminal_event=terminal_event,
    )
    return EXIT_SUCCESS if child_succeeded else failure_code


def _finalize_integration(
    *,
    packet: Any,
    ledger: Path,
    receipt_path: Path | None,
    execution_status: dict[str, Any] | None = None,
) -> int:
    """Phase two: evaluate one receipt after a trusted terminal event exists."""
    def precondition_failure(code: int) -> int:
        if execution_status is not None:
            execution_status["finalize_precondition_failed"] = True
        return code

    if _validate_packet(packet, None) is not None or not isinstance(packet, dict):
        return precondition_failure(EXIT_INVALID_PACKET)
    binding = _role_binding(packet)
    if binding is None:
        return precondition_failure(EXIT_UNSAFE_LAUNCH_PATH)
    terminal_event = _load_terminal_event(ledger, packet)
    if terminal_event is None:
        return precondition_failure(EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE)
    runtime = _trusted_terminal_runtime(terminal_event)
    if runtime is None:
        return precondition_failure(EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE)
    terminal = terminal_event.value
    selected_launch_path = terminal.get("selected_launch_path")
    parent_enforced = terminal.get("parent_enforced")
    rollout = terminal.get("rollout")
    if (
        not isinstance(selected_launch_path, str)
        or not isinstance(parent_enforced, bool)
        or not isinstance(rollout, dict)
        or not isinstance(rollout.get("path"), str)
    ):
        return precondition_failure(EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE)

    # This is intentionally the first receipt read in the entire acceptance path.
    receipt = _load_receipt(receipt_path)
    gate = _integration_gate(
        receipt,
        packet=packet,
        binding=binding,
        runtime=runtime,
        expected_session_id=runtime.session_id,
        selected_launch_path=selected_launch_path,
        parent_enforced=parent_enforced,
        terminal_event=terminal_event,
        dispatch_id=packet["dispatch_id"].strip(),
    )
    if execution_status is not None:
        child_returncode = terminal.get("terminal_result", {}).get("returncode")
        execution_status.update(
            execution_completed=isinstance(child_returncode, int)
            and not isinstance(child_returncode, bool),
            child_succeeded=child_returncode == EXIT_SUCCESS,
            integration_accepted=gate["status"] == "passed",
            weighted_tokens=terminal.get("weighted_tokens"),
            execution_elapsed_ms=terminal.get("execution_elapsed_ms"),
        )
    _append_attestation(
        ledger,
        packet=packet,
        binding=binding,
        expected_session_id=runtime.session_id,
        runtime=runtime,
        source={
            "kind": "codex_rollout",
            "path": rollout["path"],
            "status": "trusted",
        },
        verdict="integration_accepted" if gate["status"] == "passed" else "integration_blocked",
        reason="receipt_finalized" if gate["status"] == "passed" else gate["reason"],
        selected_launch_path=selected_launch_path,
        parent_enforced=parent_enforced,
        terminal_event=terminal_event,
        integration_gate=gate,
    )
    return (
        EXIT_SUCCESS
        if gate["status"] == "passed"
        else EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adaptive_dispatch_attestation.py",
        description="Attest a trusted Codex rollout before running a canonical resume.",
        epilog=(
            "exit codes: 0 success; 20 invalid packet; 21 mismatch recovery failure; "
            "22 unavailable fallback failure; 23 unsafe launch path; "
            "24 protected command failure; 25 main-authority policy gate; "
            "26 model-routing audit failure"
        ),
    )
    parser.add_argument("--packet", required=True, type=Path, help="validated packet JSON file")
    parser.add_argument("--rollout", type=Path, help="trusted Codex rollout JSONL evidence")
    parser.add_argument("--session-id", help="expected canonical Codex session UUID")
    parser.add_argument(
        "--native-admission-receipt",
        type=Path,
        help="allowlisted pre-creation Native V2 admission receipt JSON",
    )
    parser.add_argument(
        "--integration-receipt",
        type=Path,
        help="post-execution receipt JSON; used only with --finalize-integration",
    )
    parser.add_argument(
        "--finalize-integration",
        action="store_true",
        help="evaluate a receipt against a previously captured terminal event without launching a child",
    )
    parser.add_argument(
        "--protected-argv-json", help="protected command as a JSON argv list"
    )
    parser.add_argument(
        "--corrected-launch", type=Path, help="corrected_typed_worker recovery envelope"
    )
    parser.add_argument(
        "--fallback-launch", type=Path, help="typed_external_worker fallback envelope"
    )
    parser.add_argument(
        "--direct-typed",
        action="store_true",
        help="build and execute a bounded typed external worker from the validated packet",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="attest a selected path without executing any subprocess",
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER, help="JSONL ledger path")
    parser.add_argument(
        "--model-routing-ledger",
        type=Path,
        default=MODEL_ROUTING_LEDGER,
        help="linked model-routing audit JSONL path",
    )
    parser.add_argument(
        "--model-routing-review-dir",
        type=Path,
        default=MODEL_ROUTING_REVIEW_DIR,
        help="model-routing automatic review directory",
    )
    return parser


def _print_error(message: str) -> None:
    print(f"adaptive-dispatch-attestation: {message}", file=sys.stderr)


@contextmanager
def _finalization_lock(ledger: Path, dispatch_id: str):
    """Serialize pending-check, receipt acceptance, and terminal audit append."""
    parent = ledger.parent
    try:
        parent_metadata = parent.lstat()
    except OSError as exc:
        raise RuntimeError("model-routing ledger directory is unavailable") from exc
    if (
        parent.is_symlink()
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
        or parent_metadata.st_mode & 0o077
    ):
        raise RuntimeError("model-routing ledger directory is not owner-only")
    lock_id = hashlib.sha256(dispatch_id.encode("utf-8")).hexdigest()
    lock_path = parent / f".finalize-{lock_id}.lock"
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("could not open the finalization lock") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
        ):
            raise RuntimeError("finalization lock is not an owner-only file")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _dispatch_main(
    argv: list[str] | None = None,
    execution_status: dict[str, Any] | None = None,
    *,
    parsed_args: argparse.Namespace | None = None,
    packet: Any = None,
    packet_loaded: bool = False,
) -> int:
    args = parsed_args if parsed_args is not None else _parser().parse_args(argv)
    if execution_status is not None:
        execution_status["validate_only"] = args.validate_only
    if not packet_loaded:
        try:
            packet = _load_json(args.packet)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            _print_error("invalid packet")
            return EXIT_INVALID_PACKET
    if args.finalize_integration:
        if any(
            value is not None
            for value in (
                args.rollout,
                args.session_id,
                args.protected_argv_json,
                args.corrected_launch,
                args.fallback_launch,
                args.native_admission_receipt,
            )
        ) or args.direct_typed or args.validate_only:
            if execution_status is not None:
                execution_status["finalize_precondition_failed"] = True
            _print_error("unsafe finalization path")
            return EXIT_UNSAFE_LAUNCH_PATH
        return _finalize_integration(
            packet=packet,
            ledger=args.ledger,
            receipt_path=args.integration_receipt,
            execution_status=execution_status,
        )
    native_admission = _load_receipt(args.native_admission_receipt)

    if args.direct_typed:
        if any(
            value is not None
            for value in (
                args.rollout,
                args.session_id,
                args.protected_argv_json,
                args.corrected_launch,
                args.fallback_launch,
                args.native_admission_receipt,
            )
        ):
            _print_error("unsafe launch path")
            return EXIT_UNSAFE_LAUNCH_PATH
        launch = _direct_typed_launch(packet) if isinstance(packet, dict) else None
        if launch is None:
            validation_error = _validate_packet(packet, None)
            _print_error("invalid packet" if validation_error else "unsafe typed launch")
            return EXIT_INVALID_PACKET if validation_error else EXIT_UNSAFE_LAUNCH_PATH
        try:
            return _run_recovery(
                launch,
                args.ledger,
                EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE,
                args.validate_only,
                execution_status,
            )
        except OSError:
            return EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE

    if args.protected_argv_json is None:
        _print_error("unsafe launch path")
        return EXIT_UNSAFE_LAUNCH_PATH
    try:
        protected_argv = json.loads(args.protected_argv_json)
    except (TypeError, json.JSONDecodeError):
        _print_error("unsafe launch path")
        return EXIT_UNSAFE_LAUNCH_PATH

    try:
        outcome = _attest_native(
            packet=packet,
            rollout=args.rollout,
            session_id=args.session_id,
            argv=protected_argv,
            ledger=args.ledger,
            match_path="protected",
            mismatch_path="corrected_typed_worker" if args.corrected_launch else "none",
            unavailable_path="typed_external_worker" if args.fallback_launch else "none",
            validate_only=args.validate_only,
            native_admission=native_admission,
            execution_status=execution_status,
        )
    except OSError:
        _print_error("unsafe launch path")
        return EXIT_UNSAFE_LAUNCH_PATH

    if outcome.kind == "success":
        return EXIT_SUCCESS
    if outcome.kind == "invalid_packet":
        _print_error("invalid packet")
        return EXIT_INVALID_PACKET
    if outcome.kind == "unsafe":
        _print_error("unsafe launch path")
        return EXIT_UNSAFE_LAUNCH_PATH
    if outcome.kind == "command_failed":
        _print_error("protected command failed")
        return EXIT_PROTECTED_COMMAND_FAILURE

    if outcome.kind == "mismatch":
        if args.corrected_launch is None:
            _print_error("safe corrected launch missing")
            return EXIT_UNSAFE_LAUNCH_PATH
        launch = _load_recovery(
            args.corrected_launch, "corrected_typed_worker", packet
        )
        if launch is None:
            _print_error("unsafe corrected launch")
            return EXIT_UNSAFE_LAUNCH_PATH
        try:
            return _run_recovery(
                launch,
                args.ledger,
                EXIT_ROUTING_MISMATCH_RECOVERY_FAILURE,
                args.validate_only,
                execution_status,
            )
        except OSError:
            return EXIT_ROUTING_MISMATCH_RECOVERY_FAILURE

    if args.fallback_launch is None:
        _print_error("safe fallback launch missing")
        return EXIT_UNSAFE_LAUNCH_PATH
    launch = _load_recovery(args.fallback_launch, "typed_external_worker", packet)
    if launch is None:
        _print_error("unsafe fallback launch")
        return EXIT_UNSAFE_LAUNCH_PATH
    try:
        return _run_recovery(
            launch,
            args.ledger,
            EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE,
            args.validate_only,
            execution_status,
        )
    except OSError:
        return EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE


def _audited_dispatch(args: argparse.Namespace, packet: Any) -> int:
    status: dict[str, Any] = {"validate_only": args.validate_only}
    try:
        context, gate_warning = _start_adaptive_audit(
            packet,
            ledger=args.model_routing_ledger,
            review_dir=args.model_routing_review_dir,
            attestation_ledger=args.ledger,
            require_existing_pre=args.finalize_integration,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            "Adaptive Delegation blocked: model-routing audit failed before child "
            "creation. No child was launched. Fix the package policy/audit path, "
            "then invoke $adaptive-delegation again. "
            f"Reason: {exc}",
            file=sys.stderr,
        )
        return EXIT_MODEL_ROUTING_AUDIT_FAILURE

    if context is not None and gate_warning is not None:
        try:
            _finish_adaptive_audit(
                context, status, EXIT_POLICY_GATE, failure_override="policy_gate"
            )
        except (OSError, RuntimeError, ValueError) as exc:
            _print_error(f"model-routing audit failure: {exc}")
            return EXIT_MODEL_ROUTING_AUDIT_FAILURE
        print(gate_warning, file=sys.stderr)
        return EXIT_POLICY_GATE

    result = _dispatch_main(
        execution_status=status,
        parsed_args=args,
        packet=packet,
        packet_loaded=True,
    )
    if context is not None:
        awaiting_integration = (
            bool(status.get("execution_completed"))
            and bool(status.get("child_succeeded"))
            and not bool(status.get("integration_accepted"))
        ) or bool(status.get("finalize_precondition_failed"))
        if awaiting_integration:
            return result
        try:
            _finish_adaptive_audit(context, status, result)
        except (OSError, RuntimeError, ValueError) as exc:
            _print_error(f"model-routing audit failure: {exc}")
            return EXIT_MODEL_ROUTING_AUDIT_FAILURE
    return result


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        packet = _load_json(args.packet)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        _print_error("invalid packet")
        return EXIT_INVALID_PACKET

    if args.finalize_integration:
        dispatch_id = packet.get("dispatch_id") if isinstance(packet, dict) else None
        if (
            not isinstance(dispatch_id, str)
            or DISPATCH_ID_PATTERN.fullmatch(dispatch_id.strip()) is None
        ):
            _print_error("invalid packet")
            return EXIT_INVALID_PACKET
        try:
            with _finalization_lock(
                args.model_routing_ledger, dispatch_id.strip()
            ):
                return _audited_dispatch(args, packet)
        except (OSError, RuntimeError, ValueError) as exc:
            _print_error(f"model-routing finalization lock failure: {exc}")
            return EXIT_MODEL_ROUTING_AUDIT_FAILURE
    return _audited_dispatch(args, packet)


if __name__ == "__main__":
    raise SystemExit(main())
