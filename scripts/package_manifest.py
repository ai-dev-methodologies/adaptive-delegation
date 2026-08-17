"""Define the files that belong in the installed runtime package."""

from __future__ import annotations

import json
import re
from pathlib import Path


MANAGED_ROLE_NAME = re.compile(r"^adaptive-[a-z0-9-]+$")
STATIC_RUNTIME_PATHS = (
    "VERSION",
    "SKILL.md",
    "TOKEN_EFFICIENCY_CONTINUITY.md",
    "agents/openai.yaml",
    "config/model-routing.defaults.json",
    "references/CODEX-ISSUE-REPORT-PROMPT.md",
    "scripts/adaptive_dispatch_attestation.py",
    "scripts/dispatch_policy.py",
    "scripts/model_routing_audit.py",
    "scripts/read_continuity.py",
)


class PackageManifestError(RuntimeError):
    """The runtime package manifest cannot be resolved safely."""


def runtime_relative_paths(package: Path) -> tuple[str, ...]:
    """Return the exact allowlisted runtime files for ``package``."""
    config_path = package / "config" / "model-routing.defaults.json"
    try:
        policy = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageManifestError(f"invalid policy config: {exc}") from exc
    bindings = policy.get("role_bindings") if isinstance(policy, dict) else None
    if not isinstance(bindings, dict) or not bindings:
        raise PackageManifestError("policy role_bindings must be a non-empty object")

    role_paths: list[str] = []
    for role_name in sorted(bindings):
        if not isinstance(role_name, str) or MANAGED_ROLE_NAME.fullmatch(role_name) is None:
            raise PackageManifestError(f"unsafe managed role name: {role_name!r}")
        role_paths.append(f"roles/{role_name}.toml")

    relative_paths = (*STATIC_RUNTIME_PATHS, *role_paths)
    for relative in relative_paths:
        path = package / relative
        if path.is_symlink() or not path.is_file():
            raise PackageManifestError(f"runtime package file is missing or unsafe: {path}")
    return tuple(sorted(relative_paths))
