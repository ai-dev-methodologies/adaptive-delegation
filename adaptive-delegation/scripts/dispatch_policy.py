"""Small, fail-closed policy and semantic-route contract helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max", "ultra")
EFFORT_RANK = {name: index for index, name in enumerate(EFFORT_LEVELS)}
ROUTING_AUDIT_FIELDS = (
    "task_id", "attempt_index", "decision_timestamp", "effort_escalations",
    "model_escalations", "task_class", "oracle_strength", "risk_class",
    "selection_basis", "workspace", "main_session_id", "surface_identity",
    "surface_schema_fingerprint",
)
ROUTING_AUDIT_ROUTE_FIELDS = frozenset({"route_id", "role", "route_model", "route_model_tier", "route_reasoning_effort"})
ROUTING_AUDIT_OPTIONAL_FIELDS = frozenset({"override_reason"})
MAX_ATTEMPT_INDEX = 1_000_000
MAX_TEXT_LENGTH = 256
MAX_ID_LENGTH = 128
SUPPORTED_ENFORCEMENT_MODE = "fail-closed-declared-context"
TASK_CLASSES = frozenset({
    "simple_lookup_or_extraction", "clear_implementation_or_transformation",
    "bounded_complex_implementation_or_verification",
    "weak_oracle_ambiguous_high_risk_or_long_contract",
})
ORACLE_STRENGTHS = frozenset({"strong", "weak", "ambiguous"})
RISK_CLASSES = frozenset({"low", "medium", "high"})
SELECTION_BASES = frozenset({"policy_default", "failure_action", "human_override"})
_ENUMS = {"task_class": TASK_CLASSES, "oracle_strength": ORACLE_STRENGTHS,
          "risk_class": RISK_CLASSES, "selection_basis": SELECTION_BASES}
_ID_FIELDS = frozenset({"task_id", "main_session_id", "surface_identity"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_WORDS = frozenset({
    "authorization", "body", "cookie", "credential", "log", "objective",
    "password", "prompt", "request", "response", "secret", "token", "transcript",
})

class PolicyContractError(ValueError):
    """Machine-readable policy or packet validation failure."""

    def __init__(self, code: str, message: str, *, warning: str | None = None,
                 details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.warning = code, message, warning
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        result = {"error_code": self.code, "message": self.message,
                  "details": dict(self.details)}
        if self.warning is not None:
            result["warning"] = self.warning
        return result

@dataclass(frozen=True)
class AuthorityDecision:
    role: str
    package_owned: bool
    enforced: bool
    model: str
    reasoning_effort: str

def effort_rank(effort: str) -> int:
    try:
        return EFFORT_RANK[effort]
    except (KeyError, TypeError):
        raise PolicyContractError("EFFORT_UNKNOWN", f"unknown reasoning effort: {effort!r}") from None


def effort_at_least(effort: str, minimum: str) -> bool:
    try:
        return effort_rank(effort) >= effort_rank(minimum)
    except PolicyContractError:
        return False

def package_owned_roles(policy: Mapping[str, Any]) -> frozenset[str]:
    if not isinstance(policy, Mapping):
        raise PolicyContractError("POLICY_NOT_OBJECT", "policy must be an object")
    bindings = policy.get("role_bindings")
    if not isinstance(bindings, Mapping) or any(not isinstance(n, str) or not n for n in bindings):
        raise PolicyContractError("ROLE_BINDINGS_INVALID", "policy.role_bindings must be a non-empty object")
    return frozenset(bindings)

def _route_error(code: str, message: str, **details: Any) -> PolicyContractError:
    return PolicyContractError(code, message, details=details)

def validate_policy_routes(policy: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Validate every named route against an exact package role binding."""
    roles = policy.get("role_bindings")
    routes = policy.get("route_bindings")
    if not isinstance(roles, Mapping) or not isinstance(routes, Mapping) or not routes:
        raise _route_error("ROUTE_BINDINGS_INVALID", "route_bindings and role_bindings are required")
    result: dict[str, dict[str, str]] = {}
    for route_id, raw in routes.items():
        if not isinstance(route_id, str) or not _SAFE_ID.fullmatch(route_id) or not isinstance(raw, Mapping):
            raise _route_error("ROUTE_INVALID", "route id and binding must be bounded objects")
        fields = {key: raw.get(key) for key in ("authority", "role", "model", "model_tier", "reasoning_effort")}
        if any(not isinstance(value, str) or not value for value in fields.values()):
            raise _route_error("ROUTE_BINDING_INCOMPLETE", f"route {route_id!r} is incomplete")
        if fields["authority"] == "leaf":
            binding = roles.get(fields["role"])
            if not isinstance(binding, Mapping):
                raise _route_error("ROUTE_ROLE_UNBOUND", f"route {route_id!r} has no package role")
            if fields["model"] == "gpt-5.6-sol" or fields["reasoning_effort"] == "ultra":
                raise _route_error("LEAF_PREMIUM_FORBIDDEN", f"leaf route {route_id!r} cannot use Sol/Ultra")
            if any(binding.get(key) != fields[key] for key in ("model", "model_tier", "reasoning_effort")):
                raise _route_error("ROUTE_ROLE_MISMATCH", f"route {route_id!r} disagrees with package role")
        elif fields["authority"] == "main":
            if (fields["role"], fields["model"], fields["reasoning_effort"]) != ("main-authority", "gpt-5.6-sol", "ultra"):
                raise _route_error("MAIN_ROUTE_INVALID", f"main route {route_id!r} is not Sol/Ultra takeover")
        else:
            raise _route_error("ROUTE_AUTHORITY_INVALID", f"route {route_id!r} has unknown authority")
        result[route_id] = fields
    defaults = policy.get("task_defaults")
    ladders = policy.get("escalation_ladders")
    if not isinstance(defaults, Mapping) or not isinstance(ladders, Mapping):
        raise _route_error("ROUTE_POLICY_INVALID", "task defaults and escalation ladders are required")
    for task, route in defaults.items():
        if task not in TASK_CLASSES or route not in result:
            raise _route_error("TASK_DEFAULT_INVALID", f"task default {task!r} is not a named route")
    for ladder_name, ladder in ladders.items():
        if not isinstance(ladder, Sequence) or isinstance(ladder, (str, bytes)) or not ladder:
            raise _route_error("LADDER_INVALID", f"ladder {ladder_name!r} must be non-empty")
        if any(step not in result for step in ladder) or len(set(ladder)) != len(ladder):
            raise _route_error("LADDER_STEP_INVALID", f"ladder {ladder_name!r} has unknown/repeated steps")
        if any(result[step]["authority"] == "main" for step in ladder[:-1]):
            raise _route_error("LADDER_MAIN_JUMP_INVALID", f"ladder {ladder_name!r} reaches main before its final step")
        if ladder_name in defaults and ladder[0] != defaults[ladder_name]:
            raise _route_error("LADDER_DEFAULT_MISMATCH", f"ladder {ladder_name!r} does not start at its task default")
    contract = policy.get("transition_contract")
    if not isinstance(contract, Mapping) or contract.get("max_same_route_retries_per_stage") != 1 or contract.get("require_contiguous_attempt_indices") is not True or contract.get("require_previous_attempt_evidence") is not True or contract.get("require_current_policy_fingerprint") is not True:
        raise _route_error("TRANSITION_CONTRACT_INVALID", "transition contract must be fail-closed and bounded")
    override = contract.get("human_override")
    if not isinstance(override, Mapping) or override.get("requires_selection_basis") != "human_override" or override.get("requires_reason") is not True or override.get("route_must_be_in_applicable_ladder") is not True:
        raise _route_error("HUMAN_OVERRIDE_POLICY_INVALID", "human override policy is not explicit and bounded")
    return result

def route_for(policy: Mapping[str, Any], route_id: str) -> dict[str, str]:
    routes = validate_policy_routes(policy)
    try:
        return dict(routes[route_id])
    except KeyError:
        raise _route_error("ROUTE_UNKNOWN", f"unknown semantic route: {route_id!r}") from None


def applicable_ladder(policy: Mapping[str, Any], task_class: str, oracle_strength: str) -> tuple[str, ...]:
    validate_policy_routes(policy)
    key = "bounded_complex_with_strong_oracle" if task_class == "bounded_complex_implementation_or_verification" and oracle_strength == "strong" else task_class
    ladder = policy.get("escalation_ladders", {}).get(key)
    if not isinstance(ladder, Sequence) or isinstance(ladder, (str, bytes)):
        raise _route_error("LADDER_UNKNOWN", f"no ladder for task class {task_class!r}")
    return tuple(ladder)


def validate_route_selection(policy: Mapping[str, Any], *, route_id: str, task_class: str,
                             oracle_strength: str, selection_basis: str, role: str,
                             model: str, reasoning_effort: str, attempt_index: int = 1,
                             override_reason: str | None = None) -> dict[str, str]:
    """Validate route identity, exact role/model/effort, and first-route policy."""
    route = route_for(policy, route_id)
    expected = policy.get("task_defaults", {}).get(task_class)
    ladder = applicable_ladder(policy, task_class, oracle_strength)
    if route_id not in ladder:
        raise _route_error("ROUTE_NOT_IN_LADDER", "route is outside the applicable ladder")
    if attempt_index == 1 and selection_basis != "human_override":
        if selection_basis != "policy_default" or route_id != expected:
            raise _route_error("FIRST_ROUTE_INVALID", "first route must equal the task default")
    if selection_basis == "human_override":
        if not isinstance(override_reason, str) or not 1 <= len(override_reason) <= 256:
            raise _route_error("HUMAN_OVERRIDE_UNBOUNDED", "human override requires a bounded reason")
    elif selection_basis not in SELECTION_BASES:
        raise _route_error("SELECTION_BASIS_INVALID", "selection basis is invalid")
    if (route["role"], route["model"], route["reasoning_effort"]) != (role, model, reasoning_effort):
        raise _route_error("ROUTE_ATTESTATION_MISMATCH", "route does not match its package binding")
    return route


def route_transition(policy: Mapping[str, Any], task_class: str, oracle_strength: str,
                     previous_route: str, next_action: str) -> str:
    """Return the only route allowed by one observed failure action."""
    ladder = applicable_ladder(policy, task_class, oracle_strength)
    try:
        index = ladder.index(previous_route)
    except ValueError:
        raise _route_error("ROUTE_HISTORY_INVALID", "previous route is outside the ladder") from None
    if next_action in {"retain_route", "retry_same_route", "narrow_scope", "environment_retry"}:
        return previous_route
    if next_action == "main_takeover":
        candidate = ladder[-1]
        if candidate == previous_route:
            raise _route_error("LADDER_EXHAUSTED", "main authority is already selected")
        if route_for(policy, candidate)["authority"] != "main":
            raise _route_error("TRANSITION_KIND_MISMATCH", "main_takeover must end at main authority")
        return candidate
    if next_action in {"raise_effort", "raise_model"}:
        if index + 1 >= len(ladder):
            raise _route_error("LADDER_EXHAUSTED", "no next route remains")
        candidate = ladder[index + 1]
        previous, following = route_for(policy, previous_route), route_for(policy, candidate)
        if next_action == "raise_effort" and previous["model"] != following["model"]:
            raise _route_error("TRANSITION_KIND_MISMATCH", "raise_effort must retain the model")
        if next_action == "raise_model" and previous["model"] == following["model"]:
            raise _route_error("TRANSITION_KIND_MISMATCH", "raise_model must change the model")
        if next_action == "raise_model" and following["authority"] == "main":
            raise _route_error("TRANSITION_KIND_MISMATCH", "raise_model cannot select main authority")
        return candidate
    raise _route_error("NEXT_ACTION_TERMINAL", "next action does not select another route")


def _policy_settings(policy: Mapping[str, Any]) -> dict[str, Any]:
    package_owned_roles(policy)
    validate_policy_routes(policy)
    required, minimum, allowed = policy.get("required_model"), policy.get("minimum_reasoning_effort"), policy.get("allowed_main_efforts")
    if not isinstance(required, str) or not required:
        raise PolicyContractError("POLICY_REQUIRED_MODEL_INVALID", "policy.required_model is required")
    if minimum not in EFFORT_RANK or not isinstance(allowed, list) or not allowed or len(allowed) != len(set(allowed)) or any(item not in EFFORT_RANK for item in allowed) or minimum not in allowed or any(not effort_at_least(item, minimum) for item in allowed):
        raise PolicyContractError("POLICY_ALLOWED_EFFORTS_INVALID", "policy allowed efforts are inconsistent")
    if policy.get("enforcement_mode") != SUPPORTED_ENFORCEMENT_MODE:
        raise PolicyContractError("POLICY_ENFORCEMENT_MODE_INVALID", "unsupported enforcement mode")
    if policy.get("parent_model_mutation") is not False:
        raise PolicyContractError("POLICY_PARENT_MUTATION_INVALID", "parent model mutation must be false")
    return {"required_model": required, "minimum_reasoning_effort": minimum, "allowed_main_efforts": tuple(allowed)}


def _authority_value(authority: Any, field: str) -> str:
    value = authority.get(field) if isinstance(authority, Mapping) else None
    return value if isinstance(value, str) and value else "unknown"


def _warning(authority: Any, settings: Mapping[str, Any]) -> str:
    return (f"Adaptive Delegation blocked: main authority must be {settings['required_model']} with reasoning_effort >= {settings['minimum_reasoning_effort']}. Current: {_authority_value(authority, 'model')}/{_authority_value(authority, 'reasoning_effort')}. No child was launched. Switch the main session to {settings['required_model']}/{settings['minimum_reasoning_effort']} or above, then invoke $adaptive-delegation again.")


def enforce_main_authority(policy: Mapping[str, Any], role: str, main_authority: Mapping[str, Any] | None) -> AuthorityDecision:
    owned = role in package_owned_roles(policy)
    model, effort = _authority_value(main_authority, "model"), _authority_value(main_authority, "reasoning_effort")
    if not owned:
        return AuthorityDecision(role, False, False, model, effort)
    settings = _policy_settings(policy)
    if main_authority is None:
        code = "MAIN_AUTHORITY_MISSING"
    elif not isinstance(main_authority, Mapping) or model != settings["required_model"] or effort not in EFFORT_RANK:
        code = "MAIN_AUTHORITY_UNKNOWN"
    elif not effort_at_least(effort, settings["minimum_reasoning_effort"]):
        code = "MAIN_AUTHORITY_BELOW_MINIMUM"
    elif effort not in settings["allowed_main_efforts"]:
        code = "MAIN_AUTHORITY_EFFORT_NOT_ALLOWED"
    else:
        return AuthorityDecision(role, True, True, model, effort)
    raise PolicyContractError(code, "declared main authority does not satisfy the package policy", warning=_warning(main_authority, settings), details={"current_model": model, "current_reasoning_effort": effort})


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    words = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_").split("_")
    return any(word in _SENSITIVE_WORDS for word in words)


def validate_routing_audit(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PolicyContractError("ROUTING_AUDIT_NOT_OBJECT", "routing_audit must be an object")
    if any(_is_sensitive_key(key) for key in value):
        raise PolicyContractError("ROUTING_AUDIT_SENSITIVE_KEY", "routing_audit contains a sensitive key")
    unknown = set(value) - (
        set(ROUTING_AUDIT_FIELDS)
        | ROUTING_AUDIT_ROUTE_FIELDS
        | ROUTING_AUDIT_OPTIONAL_FIELDS
    )
    missing = set(ROUTING_AUDIT_FIELDS) - set(value)
    if unknown or missing:
        raise PolicyContractError("ROUTING_AUDIT_FIELDS_INVALID", "routing_audit fields do not match the bounded contract", details={"unknown": sorted(unknown), "missing": sorted(missing)})
    result = dict(value)
    for field, minimum in (("attempt_index", 1), ("effort_escalations", 0), ("model_escalations", 0)):
        item = result[field]
        if isinstance(item, bool) or not isinstance(item, int) or not minimum <= item <= MAX_ATTEMPT_INDEX:
            raise PolicyContractError("ROUTING_AUDIT_COUNT_INVALID", f"routing_audit.{field} is out of bounds")
    for field in ROUTING_AUDIT_FIELDS:
        if field in {"attempt_index", "effort_escalations", "model_escalations"}:
            continue
        item, limit = result[field], MAX_ID_LENGTH if field in _ID_FIELDS else MAX_TEXT_LENGTH
        if not isinstance(item, str) or not item or len(item) > limit or any(ord(char) < 32 for char in item):
            raise PolicyContractError("ROUTING_AUDIT_STRING_INVALID", f"routing_audit.{field} is invalid")
        if field in _ID_FIELDS and not _SAFE_ID.fullmatch(item):
            raise PolicyContractError("ROUTING_AUDIT_ID_INVALID", f"routing_audit.{field} is not a safe identifier")
        if field == "surface_schema_fingerprint" and not _SHA256.fullmatch(item):
            raise PolicyContractError("ROUTING_AUDIT_FINGERPRINT_INVALID", "surface fingerprint must be SHA-256")
        if field in _ENUMS and item not in _ENUMS[field]:
            raise PolicyContractError("ROUTING_AUDIT_ENUM_INVALID", f"routing_audit.{field} is outside its enum")
    optional_route = set(value) & ROUTING_AUDIT_ROUTE_FIELDS
    if optional_route and optional_route != ROUTING_AUDIT_ROUTE_FIELDS:
        raise PolicyContractError("ROUTING_AUDIT_ROUTE_FIELDS_INVALID", "routing_audit route fields must be complete")
    override_reason = value.get("override_reason")
    if result["selection_basis"] == "human_override":
        if (
            not isinstance(override_reason, str)
            or not 1 <= len(override_reason) <= MAX_TEXT_LENGTH
            or any(ord(char) < 32 for char in override_reason)
        ):
            raise PolicyContractError(
                "ROUTING_AUDIT_OVERRIDE_REASON_INVALID",
                "routing_audit human override requires a bounded reason",
            )
    elif override_reason is not None:
        raise PolicyContractError(
            "ROUTING_AUDIT_OVERRIDE_REASON_UNEXPECTED",
            "routing_audit override_reason requires human_override selection",
        )
    for field in ("route_id", "role"):
        if field in value and (not isinstance(value[field], str) or not _SAFE_ID.fullmatch(value[field])):
            raise PolicyContractError("ROUTING_AUDIT_ROUTE_ID_INVALID", f"routing_audit.{field} is invalid")
    for field in ("route_model", "route_model_tier", "route_reasoning_effort"):
        if field in value and (not isinstance(value[field], str) or not value[field] or len(value[field]) > MAX_TEXT_LENGTH):
            raise PolicyContractError("ROUTING_AUDIT_ROUTE_VALUE_INVALID", f"routing_audit.{field} is invalid")
    return result


def canonical_policy_fingerprint(policy: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(policy, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PolicyContractError("POLICY_NOT_CANONICALIZABLE", "policy cannot be fingerprinted") from exc
    return hashlib.sha256(encoded).hexdigest()
