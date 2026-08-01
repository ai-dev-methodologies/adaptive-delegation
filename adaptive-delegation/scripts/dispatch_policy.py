"""Policy-driven authority and privacy-safe routing-audit validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max", "ultra")
EFFORT_RANK = {name: index for index, name in enumerate(EFFORT_LEVELS)}
ROUTING_AUDIT_FIELDS = (
    "task_id",
    "attempt_index",
    "decision_timestamp",
    "effort_escalations",
    "model_escalations",
    "task_class",
    "oracle_strength",
    "risk_class",
    "selection_basis",
    "workspace",
    "main_session_id",
    "surface_identity",
    "surface_schema_fingerprint",
)
MAX_ATTEMPT_INDEX = 1_000_000
MAX_TEXT_LENGTH = 256
MAX_ID_LENGTH = 128
SUPPORTED_ENFORCEMENT_MODE = "fail-closed-declared-context"

TASK_CLASSES = frozenset(
    {
        "simple_lookup_or_extraction",
        "clear_implementation_or_transformation",
        "bounded_complex_implementation_or_verification",
        "former_terra_bounded",
        "former_sol_bounded_with_strong_oracle",
        "weak_oracle_ambiguous_high_risk_or_long_contract",
    }
)
ORACLE_STRENGTHS = frozenset({"strong", "weak", "ambiguous"})
RISK_CLASSES = frozenset({"low", "medium", "high"})
SELECTION_BASES = frozenset({"policy_default", "failure_action", "human_override"})
_ENUMS = {
    "task_class": TASK_CLASSES,
    "oracle_strength": ORACLE_STRENGTHS,
    "risk_class": RISK_CLASSES,
    "selection_basis": SELECTION_BASES,
}
_ID_FIELDS = frozenset({"task_id", "main_session_id", "surface_identity"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_WORDS = frozenset(
    {
        "authorization",
        "body",
        "cookie",
        "credential",
        "log",
        "objective",
        "password",
        "prompt",
        "request",
        "response",
        "secret",
        "token",
        "transcript",
    }
)

class PolicyContractError(ValueError):
    """Machine-readable policy or packet validation failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        warning: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.warning = warning
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        result = {
            "error_code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }
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
        raise PolicyContractError(
            "EFFORT_UNKNOWN", f"unknown reasoning effort: {effort!r}"
        ) from None

def effort_at_least(effort: str, minimum: str) -> bool:
    try:
        return effort_rank(effort) >= effort_rank(minimum)
    except PolicyContractError:
        return False

def package_owned_roles(policy: Mapping[str, Any]) -> frozenset[str]:
    if not isinstance(policy, Mapping):
        raise PolicyContractError("POLICY_NOT_OBJECT", "policy must be an object")
    bindings = policy.get("role_bindings")
    if not isinstance(bindings, Mapping):
        raise PolicyContractError(
            "ROLE_BINDINGS_INVALID", "policy.role_bindings must be an object"
        )
    if any(not isinstance(name, str) or not name for name in bindings):
        raise PolicyContractError(
            "ROLE_BINDING_ROLE_INVALID", "role names must be non-empty strings"
        )
    return frozenset(bindings)


def _policy_settings(policy: Mapping[str, Any]) -> dict[str, Any]:
    package_owned_roles(policy)
    required_model = policy.get("required_model")
    minimum = policy.get("minimum_reasoning_effort")
    allowed = policy.get("allowed_main_efforts")
    enforcement = policy.get("enforcement_mode")
    parent_mutation = policy.get("parent_model_mutation")
    if not isinstance(required_model, str) or not required_model:
        raise PolicyContractError(
            "POLICY_REQUIRED_MODEL_INVALID", "policy.required_model is required"
        )
    if minimum not in EFFORT_RANK:
        raise PolicyContractError(
            "POLICY_MINIMUM_EFFORT_INVALID", "policy minimum effort is invalid"
        )
    if (
        not isinstance(allowed, list)
        or not allowed
        or any(item not in EFFORT_RANK for item in allowed)
        or len(allowed) != len(set(allowed))
        or minimum not in allowed
        or any(not effort_at_least(item, minimum) for item in allowed)
    ):
        raise PolicyContractError(
            "POLICY_ALLOWED_EFFORTS_INVALID", "policy allowed efforts are inconsistent"
        )
    if enforcement != SUPPORTED_ENFORCEMENT_MODE:
        raise PolicyContractError(
            "POLICY_ENFORCEMENT_MODE_INVALID", "unsupported enforcement mode"
        )
    if parent_mutation is not False:
        raise PolicyContractError(
            "POLICY_PARENT_MUTATION_INVALID", "parent model mutation must be false"
        )
    return {
        "required_model": required_model,
        "minimum_reasoning_effort": minimum,
        "allowed_main_efforts": tuple(allowed),
    }


def _authority_value(authority: Any, field: str) -> str:
    if isinstance(authority, Mapping):
        value = authority.get(field)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _warning(authority: Any, settings: Mapping[str, Any]) -> str:
    model = _authority_value(authority, "model")
    effort = _authority_value(authority, "reasoning_effort")
    required = settings["required_model"]
    minimum = settings["minimum_reasoning_effort"]
    return (
        f"Adaptive Delegation blocked: main authority must be {required} with "
        f"reasoning_effort >= {minimum}. Current: {model}/{effort}. No child was "
        f"launched. Switch the main session to {required}/{minimum} or above, then "
        "invoke $adaptive-delegation again."
    )


def enforce_main_authority(
    policy: Mapping[str, Any],
    role: str,
    main_authority: Mapping[str, Any] | None,
) -> AuthorityDecision:
    owned = role in package_owned_roles(policy)
    model = _authority_value(main_authority, "model")
    effort = _authority_value(main_authority, "reasoning_effort")
    if not owned:
        return AuthorityDecision(role, False, False, model, effort)

    settings = _policy_settings(policy)
    details = {"current_model": model, "current_reasoning_effort": effort}
    if main_authority is None:
        code = "MAIN_AUTHORITY_MISSING"
    elif not isinstance(main_authority, Mapping):
        code = "MAIN_AUTHORITY_UNKNOWN"
    elif model != settings["required_model"] or effort not in EFFORT_RANK:
        code = "MAIN_AUTHORITY_UNKNOWN"
    elif not effort_at_least(effort, settings["minimum_reasoning_effort"]):
        code = "MAIN_AUTHORITY_BELOW_MINIMUM"
    elif effort not in settings["allowed_main_efforts"]:
        code = "MAIN_AUTHORITY_EFFORT_NOT_ALLOWED"
    else:
        return AuthorityDecision(role, True, True, model, effort)
    raise PolicyContractError(
        code,
        "declared main authority does not satisfy the package policy",
        warning=_warning(main_authority, settings),
        details=details,
    )


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    words = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_").split("_")
    return any(word in _SENSITIVE_WORDS for word in words)


def validate_routing_audit(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PolicyContractError(
            "ROUTING_AUDIT_NOT_OBJECT", "routing_audit must be an object"
        )
    if any(_is_sensitive_key(key) for key in value):
        raise PolicyContractError(
            "ROUTING_AUDIT_SENSITIVE_KEY", "routing_audit contains a sensitive key"
        )
    unknown = set(value) - set(ROUTING_AUDIT_FIELDS)
    missing = set(ROUTING_AUDIT_FIELDS) - set(value)
    if unknown or missing:
        raise PolicyContractError(
            "ROUTING_AUDIT_FIELDS_INVALID",
            "routing_audit fields do not match the bounded contract",
            details={"unknown": sorted(unknown), "missing": sorted(missing)},
        )
    result = dict(value)
    for field, minimum in (
        ("attempt_index", 1),
        ("effort_escalations", 0),
        ("model_escalations", 0),
    ):
        item = result[field]
        if isinstance(item, bool) or not isinstance(item, int) or not minimum <= item <= MAX_ATTEMPT_INDEX:
            raise PolicyContractError(
                "ROUTING_AUDIT_COUNT_INVALID", f"routing_audit.{field} is out of bounds"
            )
    for field in ROUTING_AUDIT_FIELDS:
        if field in {"attempt_index", "effort_escalations", "model_escalations"}:
            continue
        item = result[field]
        limit = MAX_ID_LENGTH if field in _ID_FIELDS else MAX_TEXT_LENGTH
        if not isinstance(item, str) or not item or len(item) > limit or any(ord(char) < 32 for char in item):
            raise PolicyContractError(
                "ROUTING_AUDIT_STRING_INVALID", f"routing_audit.{field} is invalid"
            )
        if field in _ID_FIELDS and not _SAFE_ID.fullmatch(item):
            raise PolicyContractError(
                "ROUTING_AUDIT_ID_INVALID", f"routing_audit.{field} is not a safe identifier"
            )
        if field == "surface_schema_fingerprint" and not _SHA256.fullmatch(item):
            raise PolicyContractError(
                "ROUTING_AUDIT_FINGERPRINT_INVALID", "surface fingerprint must be SHA-256"
            )
        if field in _ENUMS and item not in _ENUMS[field]:
            raise PolicyContractError(
                "ROUTING_AUDIT_ENUM_INVALID", f"routing_audit.{field} is outside its enum"
            )
    return result


def canonical_policy_fingerprint(policy: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            policy, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PolicyContractError(
            "POLICY_NOT_CANONICALIZABLE", "policy cannot be fingerprinted"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()
