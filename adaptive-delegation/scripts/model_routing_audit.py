#!/usr/bin/env python3
"""Append-only model-routing audit ledger and review CLI.

The event format is deliberately small and structured.  This module uses only
the Python standard library so it can be dropped into an adaptive-delegation
installation without adding runtime dependencies.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import errno
import fcntl
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import dispatch_policy as _route_policy
except ImportError:  # pragma: no cover - package script is normally co-located
    _route_policy = None


SCHEMA_VERSION = "0.1.0"
LINKED_SCHEMA_VERSION = "0.3.0"
LEGACY_LINKED_SCHEMA_VERSION = "0.2.0"
SUPPORTED_SCHEMA_VERSIONS = (SCHEMA_VERSION, LEGACY_LINKED_SCHEMA_VERSION, LINKED_SCHEMA_VERSION)
_configured_codex_home = os.environ.get("CODEX_HOME")
CODEX_HOME = (
    Path(_configured_codex_home).expanduser()
    if isinstance(_configured_codex_home, str) and _configured_codex_home.strip()
    else Path.home() / ".codex"
)
DEFAULT_LEDGER = CODEX_HOME / "state" / "model-routing" / "attempts.jsonl"
DEFAULT_REVIEW_DIR = CODEX_HOME / "state" / "model-routing" / "reviews"
SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SKILL_ROOT / "config" / "model-routing.defaults.json"
AUDITOR_NAME = "model-routing-audit"

# These bounds apply before parsing and while serializing.  They prevent a
# purported audit event from becoming an unbounded input or ledger line.
MAX_EVENT_BYTES = 64 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_LEDGER_BYTES = 64 * 1024 * 1024
MAX_STRING_LENGTH = 512
MAX_ID_LENGTH = 128
MAX_DETAIL_ITEMS = 8
MAX_EVIDENCE_REFERENCE_LENGTH = 256
AUTO_REVIEW_ACCEPTED_CADENCE = 25
ISSUE_REPORT_SCHEMA_VERSION = "1"

MODE_FILE = 0o600
MODE_DIRECTORY = 0o700

MODELS = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
MODEL_TIERS = ("spark-tier", "standard-tier", "frontier-tier")
EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
MAIN_MODELS = MODELS + ("unknown",)
MAIN_EFFORTS = EFFORTS + ("unknown",)
TASK_CLASSES = (
    "simple_lookup_or_extraction",
    "clear_implementation_or_transformation",
    "bounded_complex_implementation_or_verification",
    "weak_oracle_ambiguous_high_risk_or_long_contract",
)
# 0.1 ledgers can still be read after policy vocabulary changes.  These values
# are accepted only for legacy records and are never emitted in current output.
LEGACY_TASK_CLASS_PREFIX = "former" + "_"
FAILURE_CLASSES = (
    "none",
    "reasoning_insufficiency",
    "context_ceiling",
    "scope_or_retrieval_overbreadth",
    "tool_or_environment",
    "capability_ceiling",
    "weak_oracle",
    "policy_gate",
    "other",
)
ORACLE_VERDICTS = ("pass", "fail", "inconclusive", "not_run")
ORACLE_STRENGTHS = ("strong", "weak", "ambiguous")
RISK_CLASSES = ("low", "medium", "high")
SELECTION_BASES = ("policy_default", "failure_action", "human_override")
BOUNDEDNESS_VALUES = ("bounded", "partially_bounded", "unbounded")
CONTEXT_PRESSURES = ("low", "medium", "high", "critical")
TASK_SHAPE_SIGNALS = (
    "single_step",
    "multi_step",
    "lookup",
    "extraction",
    "implementation",
    "transformation",
    "verification",
    "multi_file",
    "api_contract",
    "schema_contract",
    "strict_output",
    "ambiguous_requirements",
    "long_context",
    "security_sensitive",
    "tool_dependent",
)
EXPECTED_ORACLE_TYPES = (
    "unit_test",
    "integration_test",
    "schema_validation",
    "compile_check",
    "lint_check",
    "deterministic_diff",
    "runtime_smoke_test",
    "human_review",
    "benchmark",
    "none",
)
CHEAPER_ROUTE_REASONS = (
    "not_applicable",
    "context_pressure",
    "constraint_density",
    "task_complexity",
    "weak_oracle",
    "failure_history",
    "risk_exposure",
    "quality_bar",
    "tooling_risk",
    "human_override",
)
OBSERVABLE_RESULT_SIGNALS = (
    "accepted_by_oracle",
    "rejected_by_oracle",
    "tests_passed",
    "tests_failed",
    "constraints_met",
    "constraints_missed",
    "output_complete",
    "output_incomplete",
    "budget_within_bound",
    "budget_exhausted",
    "escalation_required",
    "tool_failure",
    "regression_observed",
    "no_regression_observed",
    "evidence_inconclusive",
    "human_review_required",
)
ROUTE_ASSESSMENTS = ("correct", "too-cheap", "too-premium", "inconclusive")
TOKEN_OBSERVATIONS = ("exact", "lower_bound", "estimated", "unavailable")
ELAPSED_OBSERVATIONS = ("exact", "estimated", "unavailable")
NEXT_ACTIONS = (
    "retain_route",
    "lower_effort",
    "lower_model",
    "raise_effort",
    "raise_model",
    "retry_same_route",
    "narrow_scope",
    "split_task",
    "environment_retry",
    "main_takeover",
    "collect_more_evidence",
    "human_review",
    "stop",
)

COMMON_FIELDS = {
    "schema_version",
    "event_type",
    "attempt_id",
    "task_id",
    "attempt_index",
    "timestamp",
}
PRE_FIELDS = {
    "model",
    "model_tier",
    "reasoning_effort",
    "rationale",
    "pre_decision_detail",
    "planned_effort_escalations",
    "planned_model_escalations",
    "premium_call_justified",
    "price_change_observed",
    "route_id",
    "role",
    "override_reason",
}
POST_FIELDS = {
    "accepted",
    "failure_class",
    "effort_escalations",
    "model_escalations",
    "final_model",
    "final_model_tier",
    "final_reasoning_effort",
    "elapsed_ms",
    "input_tokens",
    "output_tokens",
    "weighted_tokens",
    "cost_proxy",
    "sol_rescue",
    "avoidable_premium_call",
    "false_cheap_route",
    "price_change_observed",
    "post_result_detail",
    "final_route_id",
    "final_role",
}
LINKED_COMMON_FIELDS = {
    "dispatch_id",
    "policy_id",
    "policy_fingerprint",
    "workspace",
    "main_session_id",
    "main_model",
    "main_reasoning_effort",
    "surface_identity",
    "surface_schema_fingerprint",
}
OBJECTIVE_LOCK_FIELDS = {"objective_lock_version", "objective_lock_digest"}
SUPPORTED_OBJECTIVE_LOCK_VERSIONS = {"1", "2"}
CURRENT_OBJECTIVE_LOCK_VERSION = "2"
LINKED_POST_FIELDS = {
    "execution_completed",
    "oracle_verdict",
    "integration_accepted",
}
RATIONALE_FIELDS = {
    "task_class",
    "oracle_strength",
    "risk_class",
    "prior_failure_class",
    "prior_attempts",
    "selection_basis",
    "override_reason",
}
PRE_DETAIL_FIELDS = {
    "boundedness",
    "context_pressure",
    "constraint_count",
    "task_shape_signals",
    "expected_oracle_types",
    "cheaper_route_not_chosen_because",
}
POST_DETAIL_FIELDS = {
    "observable_result_signals",
    "evidence_references",
    "route_assessment",
    "next_action",
    "token_observation",
    "elapsed_observation",
}

# Explicitly reject sensitive names even when the error would otherwise be an
# ordinary unknown-field error.  Token counts are allowed; credential tokens
# and token-bearing payloads are not.
FORBIDDEN_FIELD_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "prompt",
    "transcript",
    "rawlog",
    "requestbody",
    "responsebody",
    "secret",
)
FORBIDDEN_EXACT_FIELDS = {
    "access_token",
    "api_key",
    "api_token",
    "bearer_token",
    "id_token",
    "refresh_token",
    "token",
}

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EVIDENCE_REFERENCE_RE = re.compile(
    r"^(?!.*[?#@:])(?!.*://)(?!.*(?:/|\\){2})"
    r"(?:[A-Za-z0-9][A-Za-z0-9._/\\+ ~-]*|/[A-Za-z0-9][A-Za-z0-9._/\\+ ~-]*)$"
)


class AuditError(Exception):
    """An expected, user-correctable audit input or filesystem error."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _normal_field_name(name: Any) -> str:
    return str(name).lower().replace("-", "").replace("_", "")


def _reject_sensitive_names(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise AuditError("event field names must be strings")
            normalized = _normal_field_name(key)
            if normalized in {
                _normal_field_name(item) for item in FORBIDDEN_EXACT_FIELDS
            } or any(part in normalized for part in FORBIDDEN_FIELD_PARTS):
                raise AuditError("sensitive field name is not allowed")
            _reject_sensitive_names(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive_names(child)


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _require_type(event: dict[str, Any], name: str, expected: type) -> Any:
    value = event.get(name)
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise AuditError(f"{name} must be a {expected.__name__}")
    return value


def _check_enum(value: Any, name: str, choices: Iterable[str]) -> None:
    if value not in choices:
        raise AuditError(f"{name} has an unsupported value")


def _check_nonnegative_int(value: Any, name: str, maximum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AuditError(f"{name} must be a non-negative integer")
    if value < 0 or value > maximum:
        raise AuditError(f"{name} is outside its permitted bound")


def _check_enum_list(
    value: Any,
    name: str,
    choices: Iterable[str],
    *,
    minimum: int = 1,
    maximum: int = MAX_DETAIL_ITEMS,
) -> None:
    if not isinstance(value, list):
        raise AuditError(f"{name} must be a bounded list")
    if not minimum <= len(value) <= maximum:
        raise AuditError(f"{name} is outside its item-count bound")
    if not all(isinstance(item, str) for item in value):
        raise AuditError(f"{name} must contain string values")
    if len(value) != len(set(value)):
        raise AuditError(f"{name} must contain unique string values")
    for item in value:
        _check_enum(item, name, choices)


def _check_detail_object(
    value: Any,
    name: str,
    allowed_fields: set[str],
    required_fields: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuditError(f"{name} must be a structured JSON object")
    required = allowed_fields if required_fields is None else required_fields
    unknown = set(value) - allowed_fields
    if unknown:
        raise AuditError(f"{name} contains unknown fields")
    missing = required - set(value)
    if missing:
        raise AuditError(
            f"missing {name} field(s): {', '.join(sorted(missing))}"
        )
    return value


def _check_evidence_references(value: Any) -> None:
    name = "post_result_detail.evidence_references"
    if not isinstance(value, list):
        raise AuditError(f"{name} must be a bounded list")
    if not 1 <= len(value) <= MAX_DETAIL_ITEMS:
        raise AuditError(f"{name} is outside its item-count bound")
    if not all(isinstance(item, str) for item in value):
        raise AuditError(f"{name} must contain string values")
    if len(value) != len(set(value)):
        raise AuditError(f"{name} must contain unique values")
    for reference in value:
        if (
            len(reference) > MAX_EVIDENCE_REFERENCE_LENGTH
            or not _EVIDENCE_REFERENCE_RE.fullmatch(reference)
            or any(ord(character) < 32 or ord(character) == 127 for character in reference)
        ):
            raise AuditError(f"{name} contains an unsafe or oversized reference")


def _check_timestamp(value: Any, name: str = "timestamp") -> None:
    if not isinstance(value, str) or len(value) > 40 or "\n" in value:
        raise AuditError(f"{name} must be a bounded ISO-8601 timestamp")
    try:
        parsed = _datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise AuditError(f"{name} must include a timezone")


def _load_policy() -> dict[str, Any]:
    """Load only the package default policy named by the task contract."""
    try:
        with DEFAULT_CONFIG.open("rb") as stream:
            raw = stream.read(MAX_EVENT_BYTES)
            if stream.read(1):
                raise AuditError("model-routing defaults exceed the input bound")
        policy = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot load model-routing defaults: {exc}") from exc
    if not isinstance(policy, dict):
        raise AuditError("model-routing defaults must be a JSON object")
    return policy


def _policy_identity(policy: dict[str, Any]) -> tuple[str, str]:
    policy_id = policy.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id:
        raise AuditError("model-routing policy_id is missing")
    if _route_policy is None:
        raise AuditError("route policy contract is unavailable")
    try:
        fingerprint = _route_policy.canonical_policy_fingerprint(policy)
    except _route_policy.PolicyContractError as exc:
        raise AuditError(f"cannot fingerprint model-routing policy: {exc}") from exc
    return policy_id, fingerprint


def _is_current_policy_event(event: dict[str, Any], policy: dict[str, Any]) -> bool:
    if event.get("schema_version") != LINKED_SCHEMA_VERSION:
        return False
    if event.get("objective_lock_version") != CURRENT_OBJECTIVE_LOCK_VERSION:
        return False
    try:
        policy_id, fingerprint = _policy_identity(policy)
    except AuditError:
        return False
    return event.get("policy_id") == policy_id and event.get("policy_fingerprint") == fingerprint


def _validate_current_route(event: dict[str, Any], policy: dict[str, Any], *, strict: bool) -> None:
    if not strict or event["event_type"] != "pre_decision":
        return
    rationale = event["rationale"]
    selection_basis = rationale.get("selection_basis")
    required = {"route_id", "role"}
    if required - set(event) or selection_basis is None:
        raise AuditError("current-policy pre_decision requires route_id, role, and selection_basis")
    if not isinstance(event["route_id"], str) or not _ID_RE.fullmatch(event["route_id"]):
        raise AuditError("route_id must be a bounded safe identifier")
    if not isinstance(event["role"], str) or not _ID_RE.fullmatch(event["role"]):
        raise AuditError("role must be a bounded safe identifier")
    reason = event.get("override_reason", rationale.get("override_reason"))
    try:
        _route_policy.validate_route_selection(
            policy,
            route_id=event["route_id"],
            task_class=rationale["task_class"],
            oracle_strength=rationale["oracle_strength"],
            selection_basis=selection_basis,
            role=event["role"],
            model=event["model"],
            reasoning_effort=event["reasoning_effort"],
            attempt_index=event["attempt_index"],
            override_reason=reason,
        )
    except _route_policy.PolicyContractError as exc:
        raise AuditError(f"route contract: {exc.code}: {exc}") from exc
    if selection_basis == "human_override" and event.get("override_reason") not in (None, reason):
        raise AuditError("human override reason fields disagree")


def _validate_failure_observation(failure_class: str, detail: dict[str, Any]) -> None:
    signals = set(detail["observable_result_signals"])
    required = {
        "reasoning_insufficiency": {"tests_failed", "regression_observed", "evidence_inconclusive"},
        "context_ceiling": {"output_incomplete", "budget_exhausted"},
        "scope_or_retrieval_overbreadth": {"constraints_missed"},
        "tool_or_environment": {"tool_failure"},
        "capability_ceiling": {"tests_failed", "constraints_missed", "output_incomplete"},
        "weak_oracle": {"evidence_inconclusive", "human_review_required"},
        "policy_gate": {"constraints_missed", "evidence_inconclusive"},
        "other": {"evidence_inconclusive", "human_review_required"},
    }
    needed = required.get(failure_class)
    if needed is not None and not signals.intersection(needed):
        raise AuditError(f"failure_class {failure_class} lacks an observable matching signal")
    if failure_class == "scope_or_retrieval_overbreadth" and {"tool_failure", "budget_exhausted"}.intersection(signals):
        raise AuditError("resource/tool signals cannot be relabeled as scope overbreadth")


def _validate_failure_action(policy: dict[str, Any], failure_class: str, detail: dict[str, Any]) -> None:
    actions = policy.get("failure_actions", {}).get(failure_class)
    if isinstance(actions, str):
        actions = (actions,)
    if not isinstance(actions, (list, tuple, set)) or detail["next_action"] not in actions:
        raise AuditError(f"next_action {detail['next_action']!r} is not allowed for failure_class {failure_class!r}")
    _validate_failure_observation(failure_class, detail)


def validate_event(event: Any) -> dict[str, Any]:
    """Validate one event without accepting unstructured or sensitive fields."""
    if not isinstance(event, dict):
        raise AuditError("event must be a JSON object")
    _reject_sensitive_names(event)

    required_common = COMMON_FIELDS
    missing = required_common - set(event)
    if missing:
        raise AuditError(f"missing event field(s): {', '.join(sorted(missing))}")
    if event["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
        raise AuditError("unsupported schema_version")
    _check_enum(event["event_type"], "event_type", ("pre_decision", "post_result"))
    type_fields = PRE_FIELDS if event["event_type"] == "pre_decision" else POST_FIELDS | LINKED_POST_FIELDS
    allowed = COMMON_FIELDS | LINKED_COMMON_FIELDS | OBJECTIVE_LOCK_FIELDS | type_fields
    unknown = set(event) - allowed
    if unknown:
        raise AuditError(f"{event['event_type']} contains unknown fields")
    for field in ("attempt_id", "task_id"):
        value = event[field]
        if (
            not isinstance(value, str)
            or len(value) > MAX_ID_LENGTH
            or not _ID_RE.fullmatch(value)
        ):
            raise AuditError(f"{field} must be a bounded safe identifier")
    attempt_index = event["attempt_index"]
    if (
        not isinstance(attempt_index, int)
        or isinstance(attempt_index, bool)
        or not 1 <= attempt_index <= 1000000
    ):
        raise AuditError("attempt_index must be between 1 and 1000000")
    _check_timestamp(event["timestamp"])

    linked = event["schema_version"] in {LEGACY_LINKED_SCHEMA_VERSION, LINKED_SCHEMA_VERSION}
    linked_fields_present = (LINKED_COMMON_FIELDS | LINKED_POST_FIELDS) & set(event)
    lock_fields_present = OBJECTIVE_LOCK_FIELDS & set(event)
    if event["schema_version"] != LINKED_SCHEMA_VERSION and lock_fields_present:
        raise AuditError("objective lock fields require schema 0.3.0")
    if not linked and linked_fields_present:
        raise AuditError("legacy 0.1.0 events must not contain linked fields")
    if linked:
        missing_linked = LINKED_COMMON_FIELDS - set(event)
        if missing_linked:
            raise AuditError(
                f"missing linked field(s): {', '.join(sorted(missing_linked))}"
            )
        for field in ("dispatch_id", "policy_id", "main_session_id", "surface_identity"):
            value = event[field]
            if (
                not isinstance(value, str)
                or len(value) > MAX_ID_LENGTH
                or not _ID_RE.fullmatch(value)
            ):
                raise AuditError(f"{field} must be a bounded safe identifier")
        for field in ("policy_fingerprint", "surface_schema_fingerprint"):
            if not isinstance(event[field], str) or not _SHA256_RE.fullmatch(event[field]):
                raise AuditError(f"{field} must be a lowercase SHA-256 fingerprint")
        workspace = event["workspace"]
        if (
            not isinstance(workspace, str)
            or not workspace
            or len(workspace) > MAX_STRING_LENGTH
            or any(ord(character) < 32 or ord(character) == 127 for character in workspace)
        ):
            raise AuditError("workspace must be a bounded safe string")
        _check_enum(event["main_model"], "main_model", MAIN_MODELS)
        _check_enum(event["main_reasoning_effort"], "main_reasoning_effort", MAIN_EFFORTS)
        if event["schema_version"] == LINKED_SCHEMA_VERSION:
            missing_lock = OBJECTIVE_LOCK_FIELDS - set(event)
            if missing_lock:
                raise AuditError("missing objective lock field(s): " + ", ".join(sorted(missing_lock)))
            if event["objective_lock_version"] not in SUPPORTED_OBJECTIVE_LOCK_VERSIONS:
                raise AuditError("unsupported objective_lock_version")
            if not isinstance(event["objective_lock_digest"], str) or not _SHA256_RE.fullmatch(event["objective_lock_digest"]):
                raise AuditError("objective_lock_digest must be a lowercase SHA-256 fingerprint")

    for key, value in event.items():
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            raise AuditError(f"{key} exceeds the string-size bound")

    policy = _load_policy()
    strict_current = _is_current_policy_event(event, policy)
    capabilities = policy.get("model_capabilities", {})
    if not isinstance(capabilities, dict):
        capabilities = {}

    if event["event_type"] == "pre_decision":
        if "post_result_detail" in event:
            raise AuditError("pre_decision must not contain post_result_detail")
        if LINKED_POST_FIELDS & set(event):
            raise AuditError("pre_decision must not contain linked result fields")
        # The three core decision fields and structured rationale are required;
        # escalation plans and premium justification are optional annotations.
        required_pre = {"model", "model_tier", "reasoning_effort", "rationale"}
        missing = required_pre - set(event)
        if missing:
            raise AuditError(f"missing pre_decision field(s): {', '.join(sorted(missing))}")
        _check_enum(event["model"], "model", MODELS)
        _check_enum(event["model_tier"], "model_tier", MODEL_TIERS)
        _check_enum(event["reasoning_effort"], "reasoning_effort", EFFORTS)
        model_capability = capabilities.get(event["model"], {})
        if isinstance(model_capability, dict):
            allowed_efforts = model_capability.get("allowed_efforts")
            if isinstance(allowed_efforts, list) and event["reasoning_effort"] not in allowed_efforts:
                raise AuditError("reasoning_effort is not allowed for model")
        rationale = event["rationale"]
        if not isinstance(rationale, dict):
            raise AuditError("rationale must be a structured JSON object")
        if set(rationale) - RATIONALE_FIELDS:
            raise AuditError("rationale contains unknown fields")
        required_rationale = {"task_class", "oracle_strength", "risk_class"}
        missing = required_rationale - set(rationale)
        if missing:
            raise AuditError(
                f"missing rationale field(s): {', '.join(sorted(missing))}"
            )
        task_class = rationale["task_class"]
        if task_class not in TASK_CLASSES and not (
            event["schema_version"] == SCHEMA_VERSION
            and isinstance(task_class, str)
            and task_class.startswith(LEGACY_TASK_CLASS_PREFIX)
        ):
            raise AuditError("rationale.task_class is outside the current policy vocabulary")
        _check_enum(
            rationale["oracle_strength"],
            "rationale.oracle_strength",
            ORACLE_STRENGTHS,
        )
        _check_enum(rationale["risk_class"], "rationale.risk_class", RISK_CLASSES)
        if "prior_failure_class" in rationale:
            prior_failure = rationale["prior_failure_class"]
            if prior_failure is not None:
                _check_enum(prior_failure, "rationale.prior_failure_class", FAILURE_CLASSES)
        if "prior_attempts" in rationale:
            _check_nonnegative_int(rationale["prior_attempts"], "rationale.prior_attempts", 1000000)
        if "selection_basis" in rationale:
            _check_enum(rationale["selection_basis"], "rationale.selection_basis", SELECTION_BASES)
        if "override_reason" in rationale:
            if not isinstance(rationale["override_reason"], str) or not 1 <= len(rationale["override_reason"]) <= MAX_STRING_LENGTH:
                raise AuditError("rationale.override_reason must be a bounded string")
        if "pre_decision_detail" in event:
            detail = _check_detail_object(
                event["pre_decision_detail"],
                "pre_decision_detail",
                PRE_DETAIL_FIELDS,
            )
            _check_enum(
                detail["boundedness"],
                "pre_decision_detail.boundedness",
                BOUNDEDNESS_VALUES,
            )
            _check_enum(
                detail["context_pressure"],
                "pre_decision_detail.context_pressure",
                CONTEXT_PRESSURES,
            )
            _check_nonnegative_int(
                detail["constraint_count"],
                "pre_decision_detail.constraint_count",
                64,
            )
            _check_enum_list(
                detail["task_shape_signals"],
                "pre_decision_detail.task_shape_signals",
                TASK_SHAPE_SIGNALS,
            )
            _check_enum_list(
                detail["expected_oracle_types"],
                "pre_decision_detail.expected_oracle_types",
                EXPECTED_ORACLE_TYPES,
            )
            _check_enum_list(
                detail["cheaper_route_not_chosen_because"],
                "pre_decision_detail.cheaper_route_not_chosen_because",
                CHEAPER_ROUTE_REASONS,
            )
        for field in ("planned_effort_escalations", "planned_model_escalations"):
            if field in event:
                _check_nonnegative_int(event[field], field, 1000000)
        if "premium_call_justified" in event and not _is_bool(event["premium_call_justified"]):
            raise AuditError("premium_call_justified must be a boolean")
        if "price_change_observed" in event and not _is_bool(event["price_change_observed"]):
            raise AuditError("price_change_observed must be a boolean")
        if "role" in event and (not isinstance(event["role"], str) or not _ID_RE.fullmatch(event["role"])):
            raise AuditError("role must be a bounded safe identifier")
        if "route_id" in event and (not isinstance(event["route_id"], str) or not _ID_RE.fullmatch(event["route_id"])):
            raise AuditError("route_id must be a bounded safe identifier")
        if "override_reason" in event and (not isinstance(event["override_reason"], str) or not 1 <= len(event["override_reason"]) <= MAX_STRING_LENGTH):
            raise AuditError("override_reason must be a bounded string")
        _validate_current_route(event, policy, strict=strict_current)
        if strict_current:
            for field in ("planned_effort_escalations", "planned_model_escalations"):
                if field not in event:
                    raise AuditError(f"current-policy pre_decision requires {field}")
    else:
        if "pre_decision_detail" in event:
            raise AuditError("post_result must not contain pre_decision_detail")
        required_post = {
            "accepted",
            "failure_class",
            "effort_escalations",
            "model_escalations",
            "final_model",
            "elapsed_ms",
            "weighted_tokens",
            "cost_proxy",
        }
        missing = required_post - set(event)
        if missing:
            raise AuditError(f"missing post_result field(s): {', '.join(sorted(missing))}")
        if not _is_bool(event["accepted"]):
            raise AuditError("accepted must be a boolean")
        _check_enum(event["failure_class"], "failure_class", FAILURE_CLASSES)
        if event["accepted"] and event["failure_class"] != "none":
            raise AuditError("accepted post_result must have failure_class none")
        if not linked and not event["accepted"] and event["failure_class"] == "none":
            raise AuditError("rejected post_result must declare a failure_class")
        if linked:
            missing_linked_post = LINKED_POST_FIELDS - set(event)
            if missing_linked_post:
                raise AuditError(
                    "missing linked post_result field(s): "
                    + ", ".join(sorted(missing_linked_post))
                )
            if not _is_bool(event["execution_completed"]):
                raise AuditError("execution_completed must be a boolean")
            _check_enum(event["oracle_verdict"], "oracle_verdict", ORACLE_VERDICTS)
            if not _is_bool(event["integration_accepted"]):
                raise AuditError("integration_accepted must be a boolean")
            if event["accepted"] != event["integration_accepted"]:
                raise AuditError("accepted must equal integration_accepted")
            if (
                not event["accepted"]
                and event["failure_class"] == "none"
                and not event["execution_completed"]
            ):
                raise AuditError(
                    "failure_class none requires completed execution when integration is rejected"
                )
        _check_nonnegative_int(event["effort_escalations"], "effort_escalations", 1000000)
        _check_nonnegative_int(event["model_escalations"], "model_escalations", 1000000)
        _check_enum(event["final_model"], "final_model", MODELS)
        if "final_model_tier" in event:
            _check_enum(event["final_model_tier"], "final_model_tier", MODEL_TIERS)
        if "final_reasoning_effort" in event:
            _check_enum(event["final_reasoning_effort"], "final_reasoning_effort", EFFORTS)
            final_capability = capabilities.get(event["final_model"], {})
            if isinstance(final_capability, dict):
                allowed_efforts = final_capability.get("allowed_efforts")
                if isinstance(allowed_efforts, list) and event["final_reasoning_effort"] not in allowed_efforts:
                    raise AuditError("final_reasoning_effort is not allowed for model")
        _check_nonnegative_int(event["elapsed_ms"], "elapsed_ms", 604800000)
        for field in ("input_tokens", "output_tokens", "weighted_tokens"):
            if field in event:
                _check_nonnegative_int(event[field], field, 1000000000000)
        if not isinstance(event["cost_proxy"], (int, float)) or isinstance(event["cost_proxy"], bool):
            raise AuditError("cost_proxy must be a non-negative number")
        if not 0 <= event["cost_proxy"] <= 1000000000000:
            raise AuditError("cost_proxy is outside its permitted bound")
        for field in ("sol_rescue", "avoidable_premium_call", "false_cheap_route"):
            if field in event and not _is_bool(event[field]):
                raise AuditError(f"{field} must be a boolean")
        if "price_change_observed" in event and not _is_bool(event["price_change_observed"]):
            raise AuditError("price_change_observed must be a boolean")
        for field in ("final_role", "final_route_id"):
            if field in event and (not isinstance(event[field], str) or not _ID_RE.fullmatch(event[field])):
                raise AuditError(f"{field} must be a bounded safe identifier")
        if strict_current and {"final_route_id", "final_role"} - set(event):
            raise AuditError("current-policy post_result requires final_route_id and final_role")
        if "post_result_detail" in event:
            detail = _check_detail_object(
                event["post_result_detail"],
                "post_result_detail",
                POST_DETAIL_FIELDS,
                {
                    "observable_result_signals",
                    "evidence_references",
                    "route_assessment",
                    "next_action",
                },
            )
            _check_enum_list(
                detail["observable_result_signals"],
                "post_result_detail.observable_result_signals",
                OBSERVABLE_RESULT_SIGNALS,
            )
            _check_evidence_references(detail["evidence_references"])
            _check_enum(
                detail["route_assessment"],
                "post_result_detail.route_assessment",
                ROUTE_ASSESSMENTS,
            )
            _check_enum(
                detail["next_action"],
                "post_result_detail.next_action",
                NEXT_ACTIONS,
            )
            if "token_observation" in detail:
                _check_enum(
                    detail["token_observation"],
                    "post_result_detail.token_observation",
                    TOKEN_OBSERVATIONS,
                )
            if "elapsed_observation" in detail:
                _check_enum(
                    detail["elapsed_observation"],
                    "post_result_detail.elapsed_observation",
                    ELAPSED_OBSERVATIONS,
                )
            if strict_current:
                _validate_failure_action(policy, event["failure_class"], detail)
        elif strict_current:
            raise AuditError("current-policy post_result requires post_result_detail evidence")
        if strict_current and event["failure_class"] == "none" and not event["accepted"]:
            raise AuditError("current-policy rejected result with failure_class none needs explicit evidence")
    try:
        serialized = _canonical_json(event).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AuditError(f"event cannot be serialized deterministically: {exc}") from exc
    if len(serialized) > MAX_LINE_BYTES - 1 or len(serialized) > MAX_EVENT_BYTES:
        raise AuditError("serialized event exceeds the size bound")
    return event


def _lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except FileNotFoundError as exc:
        raise AuditError(f"path does not exist: {path}") from exc


def _check_owner_only(path: Path, st: os.stat_result, kind: str) -> None:
    if os.geteuid() != st.st_uid:
        raise AuditError(f"{kind} is not owned by the current user: {path}")
    if st.st_mode & 0o077:
        raise AuditError(f"{kind} is not owner-only: {path}")


def _check_existing_directory(path: Path, kind: str = "directory") -> None:
    st = _lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise AuditError(f"{kind} must not be a symlink: {path}")
    if not stat.S_ISDIR(st.st_mode):
        raise AuditError(f"{kind} must be a directory: {path}")
    _check_owner_only(path, st, kind)


def _ensure_private_directory(path: Path) -> None:
    """Create missing path components privately without trusting symlinks."""
    path = Path(path)
    missing: list[Path] = []
    probe = path
    while not os.path.lexists(probe):
        missing.append(probe)
        parent = probe.parent
        if parent == probe:
            break
        probe = parent
    if os.path.lexists(probe):
        st = os.lstat(probe)
        if stat.S_ISLNK(st.st_mode):
            raise AuditError(f"directory ancestor must not be a symlink: {probe}")
    for child in reversed(missing):
        try:
            child.mkdir(mode=MODE_DIRECTORY)
        except FileExistsError:
            pass
        child_st = os.lstat(child)
        if stat.S_ISLNK(child_st.st_mode):
            raise AuditError(f"directory must not be a symlink: {child}")
        if not stat.S_ISDIR(child_st.st_mode):
            raise AuditError(f"path must be a directory: {child}")
        _check_owner_only(child, child_st, "directory")
        os.chmod(child, MODE_DIRECTORY)
    if not missing:
        _check_existing_directory(path)


def _open_ledger(path: Path, writable: bool) -> int:
    if writable:
        _ensure_private_directory(path.parent)
    else:
        _check_existing_directory(path.parent, "ledger directory")
    flags = (os.O_RDWR if writable else os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0)
    if writable:
        flags |= os.O_APPEND | os.O_CREAT
    try:
        fd = os.open(path, flags, MODE_FILE)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise AuditError(f"ledger must not be a symlink: {path}") from exc
        raise AuditError(f"cannot open ledger {path}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise AuditError(f"ledger must be a regular file: {path}")
        _check_owner_only(path, st, "ledger")
        if writable:
            os.fchmod(fd, MODE_FILE)
        if st.st_size > MAX_LEDGER_BYTES:
            raise AuditError("ledger exceeds the total-size bound")
        return fd
    except Exception:
        os.close(fd)
        raise


def _read_fd_bytes(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_LEDGER_BYTES:
            raise AuditError("ledger exceeds the total-size bound")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_ledger(fd: int) -> list[dict[str, Any]]:
    raw = _read_fd_bytes(fd)
    if not raw:
        return []
    if not raw.endswith(b"\n"):
        raise AuditError("ledger contains an unterminated line")
    events: list[dict[str, Any]] = []
    for number, line in enumerate(raw.split(b"\n")[:-1], start=1):
        if not line:
            raise AuditError(f"ledger line {number} is empty")
        if len(line) > MAX_LINE_BYTES:
            raise AuditError(f"ledger line {number} exceeds the size bound")
        try:
            event = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AuditError(f"ledger line {number} is not valid JSON: {exc}") from exc
        try:
            events.append(validate_event(event))
        except AuditError as exc:
            raise AuditError(f"ledger line {number}: {exc}") from exc
    return events


def _pair_key(event: dict[str, Any]) -> tuple[str, str]:
    if event["schema_version"] in {LEGACY_LINKED_SCHEMA_VERSION, LINKED_SCHEMA_VERSION}:
        return ("linked", event["dispatch_id"])
    return ("legacy", event["attempt_id"])


def _check_pair(pre: dict[str, Any], post: dict[str, Any]) -> None:
    if pre["task_id"] != post["task_id"] or pre["attempt_index"] != post["attempt_index"]:
        raise AuditError("paired events disagree")
    if pre["schema_version"] != post["schema_version"]:
        raise AuditError("paired events use different schema versions")
    if pre["schema_version"] in {LEGACY_LINKED_SCHEMA_VERSION, LINKED_SCHEMA_VERSION}:
        mismatch = [field for field in LINKED_COMMON_FIELDS if pre[field] != post[field]]
        if mismatch:
            raise AuditError(
                f"linked events disagree: {', '.join(sorted(mismatch))}"
            )
        if pre["schema_version"] == LINKED_SCHEMA_VERSION:
            if pre["objective_lock_version"] != post["objective_lock_version"]:
                raise AuditError("linked events disagree: objective_lock_version")
            if pre["objective_lock_digest"] != post["objective_lock_digest"]:
                raise AuditError("linked events disagree: objective_lock_digest")
    if _parse_timestamp(post["timestamp"]) < _parse_timestamp(pre["timestamp"]):
        raise AuditError("post_result timestamp precedes pre_decision")
    policy = _load_policy()
    strict = _is_current_policy_event(pre, policy) and _is_current_policy_event(post, policy)
    if not strict:
        return
    if post["effort_escalations"] != pre["planned_effort_escalations"] or post["model_escalations"] != pre["planned_model_escalations"]:
        raise AuditError("route counters disagree")
    for field in ("model", "reasoning_effort"):
        final_field = "final_" + field
        if final_field in post and post[final_field] != pre[field]:
            raise AuditError("final route disagrees with pre_decision")
    if "final_route_id" in post and post["final_route_id"] != pre["route_id"]:
        raise AuditError("final route id disagrees with pre_decision")
    if "final_role" in post and post["final_role"] != pre["role"]:
        raise AuditError("final role disagrees with pre_decision")


def _check_current_transition(previous: tuple[dict[str, Any], dict[str, Any]], current: dict[str, Any], policy: dict[str, Any]) -> None:
    prior_pre, prior_post = previous
    if not (_is_current_policy_event(prior_pre, policy) and _is_current_policy_event(prior_post, policy) and _is_current_policy_event(current, policy)):
        return
    if current["attempt_index"] != prior_pre["attempt_index"] + 1:
        raise AuditError("current-policy attempt_index must be contiguous")
    if current["schema_version"] == LINKED_SCHEMA_VERSION:
        if prior_pre["schema_version"] != LINKED_SCHEMA_VERSION:
            raise AuditError("cannot continue a 0.2.0 chain into a 0.3.0 chain")
        if current["objective_lock_digest"] != prior_pre["objective_lock_digest"]:
            raise AuditError("objective lock digest must be preserved across attempt transitions")
    rationale = current["rationale"]
    prior_rationale = prior_pre["rationale"]
    if rationale.get("selection_basis") not in {"failure_action", "human_override"}:
        raise AuditError("attempt_index > 1 requires failure_action or explicit human_override selection")
    if rationale.get("prior_attempts") != current["attempt_index"] - 1:
        raise AuditError("prior_attempts does not match attempt history")
    if rationale.get("prior_failure_class") not in (None, prior_post["failure_class"]):
        raise AuditError("prior_failure_class does not match previous result")
    detail = prior_post.get("post_result_detail")
    if not isinstance(detail, dict) or not detail.get("evidence_references"):
        raise AuditError("attempt_index > 1 requires bounded previous-attempt evidence")
    action = detail["next_action"]
    try:
        ladder = _route_policy.applicable_ladder(policy, prior_rationale["task_class"], prior_rationale["oracle_strength"])
    except _route_policy.PolicyContractError as exc:
        raise AuditError(f"route history ladder is invalid: {exc}") from exc
    previous_index = ladder.index(prior_pre["route_id"])
    current_index = ladder.index(current["route_id"]) if current["route_id"] in ladder else -1
    same_route = current["route_id"] == prior_pre["route_id"]
    same_actions = {"retain_route", "retry_same_route", "narrow_scope", "environment_retry"}
    if action in same_actions:
        if prior_post["accepted"]:
            raise AuditError("an accepted attempt cannot be retried")
        if not same_route:
            raise AuditError("same-route action cannot transition to a different route")
    elif action in {"raise_effort", "raise_model", "main_takeover"}:
        if action == "main_takeover" and previous_index == len(ladder) - 1:
            raise AuditError("main authority is already selected")
        if (
            action == "main_takeover"
            and prior_post["failure_class"] != "weak_oracle"
            and previous_index != len(ladder) - 2
        ):
            raise AuditError("main_takeover must be adjacent unless failure_class is weak_oracle")
        expected_index = len(ladder) - 1 if action == "main_takeover" else previous_index + 1
        if current_index != expected_index:
            raise AuditError("route transition skipped or repeated a ladder step")
        if action == "raise_effort" and current["model"] != prior_pre["model"]:
            raise AuditError("raise_effort must retain the model")
        if action == "raise_model" and current["model"] == prior_pre["model"]:
            raise AuditError("raise_model must change the model")
        if action == "raise_model" and current["role"] == "main-authority":
            raise AuditError("raise_model cannot select the main-authority route")
        if action == "main_takeover" and current["role"] != "main-authority":
            raise AuditError("main_takeover must select the main-authority route")
    else:
        raise AuditError(f"previous next_action {action!r} cannot start another attempt")
    effort_delta = int(current["model"] == prior_pre["model"] and current["reasoning_effort"] != prior_pre["reasoning_effort"])
    model_delta = int(current["model"] != prior_pre["model"])
    if current["planned_effort_escalations"] != prior_post["effort_escalations"] + effort_delta or current["planned_model_escalations"] != prior_post["model_escalations"] + model_delta:
        raise AuditError("route escalation counters do not match the observed transition")


def _check_sequence(events: list[dict[str, Any]]) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], int]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    history: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    pending_current: dict[str, dict[str, Any]] = {}
    highest_current_attempt: dict[str, int] = {}
    policy = _load_policy()
    for event in events:
        key = _pair_key(event)
        event_type = event["event_type"]
        prior = seen.get(key)
        pair_pre = prior if event_type == "post_result" else None
        if prior is not None:
            if prior["event_type"] == event_type:
                raise AuditError(f"duplicate {event_type}")
            if event_type == "pre_decision":
                raise AuditError("post_result already recorded")
            _check_pair(prior, event)
            pairs.append((prior, event))
            seen[key] = event
        else:
            if event_type == "post_result":
                raise AuditError("post_result cannot precede pre_decision")
            prior_history = history.get(event["task_id"], [])
            current_policy_event = _is_current_policy_event(event, policy)
            if current_policy_event:
                if event["task_id"] in pending_current:
                    raise AuditError("task has a pending attempt")
                highest_index = highest_current_attempt.get(event["task_id"])
                if highest_index is not None and event["attempt_index"] != highest_index + 1:
                    raise AuditError("current-policy attempt_index must be contiguous")
            if not prior_history and current_policy_event:
                if event["attempt_index"] != 1:
                    raise AuditError(
                        "current-policy task history must begin at attempt_index 1"
                    )
                if event["rationale"].get("prior_attempts") != 0:
                    raise AuditError(
                        "first current-policy attempt must declare zero prior attempts"
                    )
            if prior_history:
                previous_schema = prior_history[-1][0]["schema_version"]
                current_schema = event["schema_version"]
                linked_versions = {LEGACY_LINKED_SCHEMA_VERSION, LINKED_SCHEMA_VERSION}
                if (
                    previous_schema in linked_versions
                    and current_schema in linked_versions
                    and previous_schema != current_schema
                ):
                    raise AuditError(
                        "linked task history cannot change schema version"
                    )
                if (
                    previous_schema == LINKED_SCHEMA_VERSION
                    and current_schema == LINKED_SCHEMA_VERSION
                    and prior_history[-1][0]["objective_lock_version"]
                    != event["objective_lock_version"]
                ):
                    raise AuditError(
                        "linked task history cannot change objective lock version"
                    )
                previous_current = all(
                    _is_current_policy_event(item, policy)
                    for item in prior_history[-1]
                )
                if current_policy_event and not previous_current:
                    raise AuditError(
                        "current-policy transition requires current-policy history"
                    )
                _check_current_transition(prior_history[-1], event, policy)
                if current_policy_event:
                    trailing_stage_attempts = 0
                    current_history = [
                        pair
                        for pair in prior_history
                        if all(_is_current_policy_event(item, policy) for item in pair)
                    ]
                    for prior_pre, _prior_post in reversed(current_history):
                        if prior_pre["route_id"] != event["route_id"]:
                            break
                        trailing_stage_attempts += 1
                    same_retries = max(0, trailing_stage_attempts - 1)
                    max_retries = policy.get("transition_contract", {}).get("max_same_route_retries_per_stage", 1)
                    if event["route_id"] == prior_history[-1][0]["route_id"] and same_retries >= max_retries:
                        raise AuditError("same route retry budget is exhausted")
            seen[key] = event
            if current_policy_event:
                pending_current[event["task_id"]] = event
                highest_current_attempt[event["task_id"]] = event["attempt_index"]
        if event_type == "post_result":
            if pair_pre is not None:
                history.setdefault(event["task_id"], []).append((pair_pre, event))
                if pending_current.get(event["task_id"]) is pair_pre:
                    pending_current.pop(event["task_id"], None)
    incomplete = sum(1 for event in seen.values() if event["event_type"] == "pre_decision")
    return pairs, incomplete


def _parse_timestamp(value: str) -> _datetime.datetime:
    return _datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _read_event_file(path: Path) -> dict[str, Any]:
    try:
        st = path.lstat()
    except FileNotFoundError as exc:
        raise AuditError(f"event file does not exist: {path}") from exc
    if stat.S_ISLNK(st.st_mode):
        raise AuditError("event file must not be a symlink")
    if not stat.S_ISREG(st.st_mode):
        raise AuditError("event file must be a regular file")
    _check_owner_only(path, st, "event file")
    if st.st_size > MAX_EVENT_BYTES:
        raise AuditError("event file exceeds the size bound")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise AuditError("event file must not be a symlink") from exc
        raise AuditError(f"cannot open event file: {exc}") from exc
    try:
        current = os.fstat(fd)
        _check_owner_only(path, current, "event file")
        if current.st_size > MAX_EVENT_BYTES:
            raise AuditError("event file exceeds the size bound")
        data = os.read(fd, MAX_EVENT_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_EVENT_BYTES:
        raise AuditError("event file exceeds the size bound")
    try:
        event = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"event file is not one valid UTF-8 JSON object: {exc}") from exc
    return validate_event(event)


def _append_event(
    event: dict[str, Any], ledger_path: Path, *, idempotent: bool
) -> bool:
    event = validate_event(event)
    line = (_canonical_json(event) + "\n").encode("utf-8")
    if len(line) > MAX_LINE_BYTES:
        raise AuditError("serialized ledger line exceeds the size bound")
    fd = _open_ledger(ledger_path, writable=True)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            events = _parse_ledger(fd)
            key = _pair_key(event)
            same_type = next(
                (
                    item
                    for item in events
                    if _pair_key(item) == key
                    and item["event_type"] == event["event_type"]
                ),
                None,
            )
            if same_type is not None:
                if idempotent and _canonical_json(same_type) == _canonical_json(event):
                    return False
                kind = "conflicting" if idempotent else "duplicate"
                raise AuditError(f"{kind} {event['event_type']}")
            counterpart = next(
                (item for item in events if _pair_key(item) == key), None
            )
            if counterpart is not None:
                if event["event_type"] == "pre_decision":
                    raise AuditError("post_result already recorded")
                _check_pair(counterpart, event)
            elif event["event_type"] == "post_result":
                raise AuditError("post_result cannot precede pre_decision")
            _check_sequence(events + [event])
            os.lseek(fd, 0, os.SEEK_END)
            os.write(fd, line)
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    return True


def _record(event_path: Path, ledger_path: Path) -> dict[str, Any]:
    event = _read_event_file(event_path)
    _append_event(event, ledger_path, idempotent=False)
    return event


def record_event(
    event: dict[str, Any],
    ledger_path: Path = DEFAULT_LEDGER,
    review_dir: Path = DEFAULT_REVIEW_DIR,
    *,
    auto_review: bool = True,
    idempotent: bool = False,
) -> dict[str, Any]:
    """Append a validated event and optionally create a trigger-based review.

    Idempotent mode treats an exact same-type duplicate as a no-op while still
    rejecting a conflicting duplicate. The CLI intentionally keeps strict
    legacy duplicate behavior by calling this API with ``idempotent=False``.
    """

    validated = validate_event(event)
    appended = _append_event(validated, Path(ledger_path), idempotent=idempotent)
    reasons = (
        _automatic_review_reasons(Path(ledger_path), validated)
        if auto_review and appended
        else []
    )
    review_path = (
        _review(Path(ledger_path), Path(review_dir)) if reasons else None
    )
    return {
        "recorded": validated,
        "idempotent_duplicate": not appended,
        "automatic_review": {
            "reasons": reasons,
            "path": str(review_path) if review_path else None,
        },
    }


def exact_unpaired_pre_exists(
    event: dict[str, Any], ledger_path: Path = DEFAULT_LEDGER
) -> bool:
    """Return whether an exact pre-decision exists without a paired result."""
    validated = validate_event(event)
    if validated["event_type"] != "pre_decision":
        raise AuditError("pending-event lookup requires a pre_decision")
    ledger = Path(ledger_path)
    if not os.path.lexists(ledger):
        return False
    fd = _open_ledger(ledger, writable=False)
    try:
        expected_key = _pair_key(validated)
        expected_json = _canonical_json(validated)
        candidates = _parse_ledger(fd)
        exact_pre = any(
            _pair_key(candidate) == expected_key
            and candidate["event_type"] == "pre_decision"
            and _canonical_json(candidate) == expected_json
            for candidate in candidates
        )
        paired = any(
            _pair_key(candidate) == expected_key
            and candidate["event_type"] == "post_result"
            for candidate in candidates
        )
        return exact_pre and not paired
    finally:
        os.close(fd)


def _round(value: float) -> float:
    return round(value, 6)


def _rate(numerator: int, denominator: int) -> float:
    return _round(numerator / denominator) if denominator else 0.0


def _is_sol(model: str) -> bool:
    return model == "gpt-5.6-sol"


def _is_cheap(model: str) -> bool:
    return model == "gpt-5.6-luna"


def _derive_sol_rescue(pre: dict[str, Any], post: dict[str, Any]) -> bool:
    if "sol_rescue" in post:
        return post["sol_rescue"]
    return bool(
        post["accepted"]
        and _is_sol(post["final_model"])
        and post["model_escalations"] > 0
        and not _is_sol(pre["model"])
    )


def _derive_avoidable_premium(pre: dict[str, Any], post: dict[str, Any]) -> bool:
    if "avoidable_premium_call" in post:
        return post["avoidable_premium_call"]
    if "premium_call_justified" in pre:
        return _is_sol(pre["model"]) and not pre["premium_call_justified"]
    return _is_sol(pre["model"]) and pre["rationale"]["task_class"] != (
        "weak_oracle_ambiguous_high_risk_or_long_contract"
    )


def _derive_false_cheap(pre: dict[str, Any], post: dict[str, Any]) -> bool:
    if "false_cheap_route" in post:
        return post["false_cheap_route"]
    if not _is_cheap(pre["model"]):
        return False
    return bool(
        post["model_escalations"] > 0
        and (
            post["failure_class"] in {"context_ceiling", "capability_ceiling"}
            or post["final_model"] != pre["model"]
        )
    )


def _make_review(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    incomplete: int,
    ledger_path: Path,
) -> dict[str, Any]:
    all_pairs = list(pairs)
    policy = _load_policy()
    try:
        current_policy_id, current_fingerprint = _policy_identity(policy)
    except AuditError:
        current_policy_id, current_fingerprint = "", ""
    linked_pairs = [
        (pre, post)
        for pre, post in pairs
        if pre["schema_version"] in {LEGACY_LINKED_SCHEMA_VERSION, LINKED_SCHEMA_VERSION}
    ]
    linked_groups: dict[tuple[str, ...], dict[str, Any]] = {}
    for pre, post in linked_pairs:
        key = (
            pre["schema_version"],
            pre["main_model"],
            pre["main_reasoning_effort"],
            pre["policy_id"],
            pre["policy_fingerprint"],
            pre["surface_identity"],
            pre["surface_schema_fingerprint"],
        )
        group = linked_groups.setdefault(
            key,
            {
                "schema_version": key[0],
                "main_model": key[1],
                "main_reasoning_effort": key[2],
                "policy_id": key[3],
                "policy_fingerprint": key[4],
                "surface_identity": key[5],
                "surface_schema_fingerprint": key[6],
                "paired_attempts": 0,
                "execution_completed": 0,
                "integration_accepted": 0,
                "oracle_verdicts": {value: 0 for value in ORACLE_VERDICTS},
            },
        )
        group["paired_attempts"] += 1
        group["execution_completed"] += int(post["execution_completed"])
        group["integration_accepted"] += int(post["integration_accepted"])
        group["oracle_verdicts"][post["oracle_verdict"]] += 1

    def is_current_pair(pair: tuple[dict[str, Any], dict[str, Any]]) -> bool:
        pre, _post = pair
        return (
            pre.get("schema_version") == LINKED_SCHEMA_VERSION
            and pre.get("policy_id") == current_policy_id
            and pre.get("policy_fingerprint") == current_fingerprint
        )

    current_pairs = [pair for pair in all_pairs if is_current_pair(pair)]
    historical_pairs = [pair for pair in all_pairs if not is_current_pair(pair)]
    # Historical records remain readable and reviewable. They are never mixed
    # into the analysis basis once current 0.3 records exist.
    pairs = current_pairs or historical_pairs
    analysis_basis = "current_0.3" if current_pairs else "historical_only"

    task_pairs: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for pre, post in pairs:
        task_pairs.setdefault(pre["task_id"], []).append((pre, post))
    for task in task_pairs.values():
        task.sort(key=lambda pair: (pair[0]["attempt_index"], pair[0]["attempt_id"]))

    task_count = len(task_pairs)
    effort_order = {effort: index for index, effort in enumerate(EFFORTS)}
    effort_transition_count = 0
    model_transition_count = 0
    same_route_retry_count = 0
    main_takeover_count = 0
    for attempts in task_pairs.values():
        previous_pre: dict[str, Any] | None = None
        for pre, _ in attempts:
            if previous_pre is not None:
                if pre["model"] != previous_pre["model"]:
                    model_transition_count += 1
                elif pre["reasoning_effort"] == previous_pre["reasoning_effort"]:
                    same_route_retry_count += 1
                elif (
                    effort_order[pre["reasoning_effort"]]
                    > effort_order[previous_pre["reasoning_effort"]]
                ):
                    effort_transition_count += 1
            if _is_sol(pre["model"]) and pre["rationale"].get("prior_attempts", 0) > 0:
                main_takeover_count += 1
            previous_pre = pre

    accepted_task_values: list[
        tuple[int | None, int | None, float | None]
    ] = []
    first_pass_accepted = 0
    accepted_tasks = 0
    for attempts in task_pairs.values():
        first_accepted_index: int | None = None
        elapsed = 0
        weighted_tokens = 0
        elapsed_covered = True
        token_cost_covered = True
        for pre, post in attempts:
            elapsed += post["elapsed_ms"]
            weighted_tokens += post["weighted_tokens"]
            detail = post.get("post_result_detail")
            if isinstance(detail, dict):
                if detail.get("elapsed_observation") == "unavailable":
                    elapsed_covered = False
                if detail.get("token_observation") == "unavailable":
                    token_cost_covered = False
            if post["accepted"] and first_accepted_index is None:
                first_accepted_index = pre["attempt_index"]
                break
        if first_accepted_index is not None:
            accepted_tasks += 1
            if first_accepted_index == 1:
                first_pass_accepted += 1
            accepted_task_values.append(
                (
                    elapsed if elapsed_covered else None,
                    weighted_tokens if token_cost_covered else None,
                    None,
                )
            )

    paired_attempts = len(pairs)
    all_paired_attempts = len(all_pairs)
    effort_escalated = sum(1 for _, post in pairs if post["effort_escalations"] > 0)
    model_escalated = sum(1 for _, post in pairs if post["model_escalations"] > 0)
    sol_rescues = sum(1 for pre, post in pairs if _derive_sol_rescue(pre, post))
    premium_calls = sum(1 for pre, _ in pairs if _is_sol(pre["model"]))
    avoidable_premium = sum(
        1 for pre, post in pairs if _derive_avoidable_premium(pre, post)
    )
    cheap_routes = sum(1 for pre, _ in pairs if _is_cheap(pre["model"]))
    false_cheap = sum(1 for pre, post in pairs if _derive_false_cheap(pre, post))
    route_assessment_counts = {value: 0 for value in ROUTE_ASSESSMENTS}
    next_action_counts = {value: 0 for value in NEXT_ACTIONS}
    for _, post in pairs:
        detail = post.get("post_result_detail")
        if not isinstance(detail, dict):
            continue
        route_assessment_counts[detail["route_assessment"]] += 1
        next_action_counts[detail["next_action"]] += 1
    elapsed_values = [item[0] for item in accepted_task_values if item[0] is not None]
    weighted_values = [item[1] for item in accepted_task_values if item[1] is not None]
    elapsed_total = sum(elapsed_values)
    weighted_total = sum(weighted_values)

    route_metrics: dict[str, dict[str, Any]] = {}
    policy_segments: dict[str, dict[str, Any]] = {}
    for pre, post in pairs:
        fingerprint = pre.get("policy_fingerprint", "legacy")
        segment_key = f"{pre['schema_version']}:{fingerprint}"
        route_key = f"{segment_key}:{pre['model']}/{pre['reasoning_effort']}"
        route = route_metrics.setdefault(route_key, {
            "schema_version": pre["schema_version"],
            "policy_fingerprint": fingerprint,
            "model": pre["model"],
            "reasoning_effort": pre["reasoning_effort"],
            "calls": 0,
            "accepted_calls": 0,
            "weighted_tokens": 0,
            "cost_proxy_total": 0.0,
        })
        route["calls"] += 1
        route["accepted_calls"] += int(post["accepted"])
        route["weighted_tokens"] += post["weighted_tokens"]
        route["cost_proxy_total"] = _round(route["cost_proxy_total"] + float(post["cost_proxy"]))
        segment = policy_segments.setdefault(segment_key, {
            "schema_version": pre["schema_version"],
            "policy_fingerprint": fingerprint,
            "calls": 0,
            "accepted_calls": 0,
            "weighted_tokens": 0,
        })
        segment["calls"] += 1
        segment["accepted_calls"] += int(post["accepted"])
        segment["weighted_tokens"] += post["weighted_tokens"]

    metrics = {
        "first_pass_acceptance_rate": _rate(first_pass_accepted, task_count),
        "effort_escalation_rate": _rate(effort_escalated, paired_attempts),
        "model_escalation_rate": _rate(model_escalated, paired_attempts),
        "sol_rescue_rate": _rate(sol_rescues, paired_attempts),
        "avoidable_premium_call_rate": _rate(avoidable_premium, premium_calls),
        "false_cheap_route_rate": _rate(false_cheap, cheap_routes),
        "elapsed_time_per_accepted_task_ms": _round(elapsed_total / len(elapsed_values))
        if elapsed_values
        else 0.0,
        "weighted_tokens_per_accepted_task": _round(weighted_total / len(weighted_values))
        if weighted_values
        else 0.0,
        # Model-relative price fractions are only comparable inside a route
        # segment; no common cross-model cost is reported here.
        "cost_proxy_per_accepted_task": None,
        "tokens_and_calls_by_model_effort": route_metrics,
        "policy_segments": policy_segments,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": _load_policy().get("policy_id", "unknown"),
        "auditor": AUDITOR_NAME,
        "ledger": str(ledger_path),
        "attempts": {
            "paired": all_paired_attempts,
            "analysis_basis": analysis_basis,
            "analysis_basis_paired": paired_attempts,
            "current_policy_paired": len(current_pairs),
            "incomplete_pre_decisions": incomplete,
        },
        "linked_audit": {
            "paired": len(linked_pairs),
            "legacy_paired": all_paired_attempts - len(linked_pairs),
            "paired_coverage_rate": _rate(len(linked_pairs), all_paired_attempts),
            "incomplete_pre_decisions_excluded": incomplete,
            "groups": [linked_groups[key] for key in sorted(linked_groups)],
        },
        "tasks": {
            "total": task_count,
            "accepted": accepted_tasks,
            "first_pass_accepted": first_pass_accepted,
            "elapsed_metric_covered": len(elapsed_values),
            "token_cost_metric_covered": len(weighted_values),
        },
        "metric_counts": {
            "effort_escalated_attempts": effort_escalated,
            "model_escalated_attempts": model_escalated,
            "sol_rescues": sol_rescues,
            "premium_calls": premium_calls,
            "avoidable_premium_calls": avoidable_premium,
            "cheap_routes": cheap_routes,
            "false_cheap_routes": false_cheap,
            "effort_transition_count": effort_transition_count,
            "model_transition_count": model_transition_count,
            "same_route_retry_count": same_route_retry_count,
            "main_takeover_count": main_takeover_count,
            "route_assessments": route_assessment_counts,
            "next_actions": next_action_counts,
        },
        "metrics": metrics,
    }


def _review(ledger_path: Path, review_dir: Path) -> Path:
    fd = _open_ledger(ledger_path, writable=False)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        try:
            events = _parse_ledger(fd)
            pairs, incomplete = _check_sequence(events)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    _ensure_private_directory(review_dir)
    generated = _datetime.datetime.now(_datetime.timezone.utc)
    timestamp = generated.strftime("%Y%m%dT%H%M%S.%fZ")
    payload = _make_review(pairs, incomplete, ledger_path)
    payload["generated_at"] = generated.isoformat(timespec="microseconds").replace("+00:00", "Z")
    serialized = (_canonical_json(payload) + "\n").encode("utf-8")
    if len(serialized) > MAX_LINE_BYTES * 16:
        raise AuditError("review output exceeds the size bound")
    for suffix in range(1000):
        suffix_text = "" if suffix == 0 else f"-{suffix}"
        output = review_dir / f"review-{timestamp}{suffix_text}.json"
        try:
            fd = os.open(
                output,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                MODE_FILE,
            )
        except FileExistsError:
            continue
        except OSError as exc:
            raise AuditError(f"cannot create review file {output}: {exc}") from exc
        try:
            os.fchmod(fd, MODE_FILE)
            os.write(fd, serialized)
            os.fsync(fd)
        finally:
            os.close(fd)
        # Sync the directory entry as well as the file contents.
        try:
            dir_fd = os.open(review_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # File fsync is mandatory; directory fsync is unavailable on some
            # supported filesystems and is therefore best effort.
            pass
        return output
    raise AuditError("could not allocate a unique timestamped review filename")


def _automatic_review_reasons(
    ledger_path: Path, event: dict[str, Any]
) -> list[str]:
    reasons: list[str] = []
    if event.get("price_change_observed"):
        reasons.append("model-price-change")
    if event["event_type"] == "pre_decision":
        if _is_sol(event["model"]):
            reasons.append("direct-sol")
        return reasons

    if not event["accepted"]:
        reasons.append("failure")
    if event["effort_escalations"] > 0 or event["model_escalations"] > 0:
        reasons.append("escalation")
    detail = event.get("post_result_detail")
    if isinstance(detail, dict) and detail["route_assessment"] != "correct":
        reasons.append("route-assessment")

    fd = _open_ledger(ledger_path, writable=False)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        try:
            pairs, _incomplete = _check_sequence(_parse_ledger(fd))
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)

    matching_pre = next(
        (pre for pre, post in pairs if _pair_key(post) == _pair_key(event)),
        None,
    )
    if (
        _is_sol(event["final_model"])
        and matching_pre is not None
        and not _is_sol(matching_pre["model"])
    ):
        reasons.append("direct-sol")

    accepted_tasks = {
        pre["task_id"] for pre, post in pairs if post["accepted"]
    }
    if (
        accepted_tasks
        and len(accepted_tasks) % AUTO_REVIEW_ACCEPTED_CADENCE == 0
    ):
        reasons.append("accepted-cadence")
    return list(dict.fromkeys(reasons))


def _read_pairs_for_issue_report(
    ledger_path: Path,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Read and validate a ledger without changing its contents.

    Incomplete pre-decision records are intentionally ignored here.  A report
    can be made for a completed task while another attempt is still open; a
    requested task with no completed pair fails closed below.
    """
    fd = _open_ledger(ledger_path, writable=False)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        try:
            pairs, _incomplete = _check_sequence(_parse_ledger(fd))
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    return pairs


def _issue_report_pair_key(
    pair: tuple[dict[str, Any], dict[str, Any]],
) -> tuple[_datetime.datetime, int, str]:
    pre, post = pair
    return (
        _parse_timestamp(post["timestamp"]),
        pre["attempt_index"],
        pre["attempt_id"],
    )


def _select_issue_report_pairs(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    task_id: str | None,
) -> tuple[str, list[tuple[dict[str, Any], dict[str, Any]]]]:
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for pair in pairs:
        grouped.setdefault(pair[0]["task_id"], []).append(pair)
    if task_id is not None:
        if not isinstance(task_id, str) or not _ID_RE.fullmatch(task_id):
            raise AuditError("task_id must be a bounded safe identifier")
        selected = grouped.get(task_id)
        if not selected:
            raise AuditError("no completed task matches task_id")
        selected.sort(key=lambda pair: (pair[0]["attempt_index"], pair[0]["attempt_id"]))
        return task_id, selected
    if not grouped:
        raise AuditError("ledger contains no completed task")
    selected_task = max(
        grouped,
        key=lambda candidate: _issue_report_pair_key(max(grouped[candidate], key=_issue_report_pair_key)),
    )
    selected = grouped[selected_task]
    selected.sort(key=lambda pair: (pair[0]["attempt_index"], pair[0]["attempt_id"]))
    return selected_task, selected


def _issue_report_markdown(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    requested_task: bool,
) -> str:
    """Render the deliberately allowlisted, English issue-report format."""
    first_pre, _first_post = pairs[0]
    _last_pre, last_post = pairs[-1]
    accepted = bool(last_post["accepted"])
    lines = [
        "# Adaptive-delegation routing report",
        "",
        f"- Report format: `issue-report/{ISSUE_REPORT_SCHEMA_VERSION}`",
        "- Selection: " + ("requested task" if requested_task else "latest completed task"),
        f"- Attempts in selected task: `{len(pairs)}`",
        f"- Result: `{'accepted' if accepted else 'not accepted'}`",
        f"- Initial route: `{first_pre['model']}` at `{first_pre['reasoning_effort']}`",
        f"- Final route: `{last_post['final_model']}` at `"
        f"{last_post.get('final_reasoning_effort', 'not recorded')}`",
        f"- Failure class: `{last_post['failure_class']}`",
        f"- Effort escalations: `{last_post['effort_escalations']}`",
        f"- Model escalations: `{last_post['model_escalations']}`",
    ]
    if last_post["schema_version"] in {LEGACY_LINKED_SCHEMA_VERSION, LINKED_SCHEMA_VERSION}:
        lines.extend(
            [
                f"- Execution completed: `{'yes' if last_post['execution_completed'] else 'no'}`",
                f"- Oracle verdict: `{last_post['oracle_verdict']}`",
                f"- Integration accepted: `{'yes' if last_post['integration_accepted'] else 'no'}`",
            ]
        )
    detail = last_post.get("post_result_detail")
    if isinstance(detail, dict):
        lines.extend(
            [
                f"- Route assessment: `{detail['route_assessment']}`",
                f"- Next action: `{detail['next_action']}`",
            ]
        )
    lines.extend(
        [
            "",
            "This report contains only allowlisted routing outcomes; inspect "
            "it locally before sharing.",
        ]
    )
    return "\n".join(lines) + "\n"


def issue_report(
    ledger_path: Path = DEFAULT_LEDGER,
    task_id: str | None = None,
) -> str:
    """Return a deterministic sanitized Markdown report for one task.

    This function only reads the validated local ledger and never publishes,
    uploads, or mutates the ledger.
    """
    pairs = _read_pairs_for_issue_report(Path(ledger_path))
    _selected_task, selected_pairs = _select_issue_report_pairs(pairs, task_id)
    return _issue_report_markdown(selected_pairs, task_id is not None)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="append one validated event")
    record.add_argument("--event-file", required=True, type=Path)
    record.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    record.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    record.add_argument(
        "--no-auto-review",
        action="store_true",
        help="append without creating a trigger-based review",
    )

    review = subparsers.add_parser("review", help="write a deterministic audit review")
    review.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    review.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)

    issue = subparsers.add_parser(
        "issue-report",
        help="print a sanitized report for the latest completed task",
    )
    issue.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    issue.add_argument(
        "--task-id",
        help="select one completed task; omitted selects the latest completed task",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            event = _read_event_file(args.event_file)
            result = record_event(
                event,
                args.ledger,
                args.review_dir,
                auto_review=not args.no_auto_review,
                idempotent=False,
            )
            result.pop("idempotent_duplicate", None)
            print(_canonical_json(result))
        elif args.command == "review":
            output = _review(args.ledger, args.review_dir)
            print(output)
        elif args.command == "issue-report":
            print(issue_report(args.ledger, args.task_id), end="")
        else:
            raise AuditError(f"unsupported command: {args.command}")
    except (AuditError, OSError, ValueError) as exc:
        message = (
            "issue report could not be generated from the local ledger"
            if args.command == "issue-report"
            else str(exc)
        )
        print(f"error: {message}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
