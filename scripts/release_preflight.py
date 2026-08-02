#!/usr/bin/env python3
"""Fail-closed README and Git release checks before merge or deployment."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class PreflightError(RuntimeError):
    """A release condition is absent or stale."""


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise PreflightError("required Git evidence is unavailable")
    return result.stdout.strip()


def _route_label(route_id: str, bindings: dict[str, Any]) -> str:
    route = bindings.get(route_id)
    if not isinstance(route, dict):
        raise PreflightError("policy ladder references an unknown route")
    model = route.get("model")
    effort = route.get("reasoning_effort")
    authority = route.get("authority")
    names = {
        "gpt-5.6-luna": "Luna",
        "gpt-5.6-terra": "Terra",
        "gpt-5.6-sol": "Sol",
    }
    if model not in names or not isinstance(effort, str):
        raise PreflightError("policy route has an invalid model or effort")
    prefix = "main " if authority == "main" else ""
    return f"{prefix}{names[model]} {effort}"


def validate_readme_contract(
    readme: str, version: str, changelog: str, policy: dict[str, Any]
) -> dict[str, Any]:
    """Compare user-facing README claims with canonical package state."""
    if not SEMVER_RE.fullmatch(version):
        raise PreflightError("VERSION is not Semantic Versioning")
    normalized_readme = " ".join(readme.split())
    required_text = (
        "**Codex-only skill:**",
        f"Current installable package version: `{version}`.",
        "## Invocation and `ultra` reasoning behavior",
        "labels such as `Goal` or `Ultragoal` are not route inputs.",
        "Leaf `ultra` remains forbidden.",
        "## Maintainer promotion and local deployment order",
        "scripts/release_preflight.py --mode pre-merge",
        "scripts/release_preflight.py --mode deploy",
        "issue-report-state.jsonl",
        "CODEX-ISSUE-REPORT-PROMPT.md",
        "docs/DELEGATION-FLOW.md",
        "adaptive-sol-checker-medium",
    )
    missing = [item for item in required_text if item not in normalized_readme]
    if missing:
        raise PreflightError("README is missing a current release contract")
    if f"## [{version}]" not in changelog:
        raise PreflightError("CHANGELOG has no entry for VERSION")
    allowed_efforts = policy.get("allowed_main_efforts")
    if allowed_efforts != ["high", "xhigh", "max", "ultra"]:
        raise PreflightError("main authority efforts changed without README review")
    bindings = policy.get("route_bindings")
    ladders = policy.get("escalation_ladders")
    if not isinstance(bindings, dict) or not isinstance(ladders, dict):
        raise PreflightError("policy routing tables are missing")
    expected_ladders = {
        " -> ".join(_route_label(route_id, bindings) for route_id in ladder)
        for ladder in ladders.values()
        if isinstance(ladder, list)
    }
    missing_ladders = [
        ladder for ladder in sorted(expected_ladders) if f"`{ladder}`" not in readme
    ]
    if missing_ladders:
        raise PreflightError("README route table is stale against package policy")
    return {
        "version": version,
        "unique_policy_ladders": len(expected_ladders),
        "main_efforts": allowed_efforts,
    }


def _validate_repository_docs() -> dict[str, Any]:
    try:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        version = (ROOT / "adaptive-delegation" / "VERSION").read_text(
            encoding="utf-8"
        ).strip()
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        policy = json.loads(
            (ROOT / "adaptive-delegation" / "config" / "model-routing.defaults.json")
            .read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreflightError("release documents could not be loaded") from exc
    if not isinstance(policy, dict):
        raise PreflightError("model-routing policy must be an object")
    return validate_readme_contract(readme, version, changelog, policy)


def _require_clean_worktree() -> None:
    if _git("status", "--porcelain=v1", "--untracked-files=all"):
        raise PreflightError("worktree must be clean")


def _pre_merge_checks() -> dict[str, Any]:
    branch = _git("branch", "--show-current")
    if not branch or branch == "main":
        raise PreflightError("pre-merge must run from a feature branch")
    _require_clean_worktree()
    head = _git("rev-parse", "HEAD")
    origin_main = _git("rev-parse", "origin/main")
    if head == origin_main:
        raise PreflightError("feature branch contains no commit beyond origin/main")
    upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    upstream_head = _git("rev-parse", "@{u}")
    if not upstream.startswith("origin/") or upstream_head != head:
        raise PreflightError("feature branch must be pushed before pre-merge")
    changed = set(
        filter(None, _git("diff", "--name-only", "origin/main...HEAD").splitlines())
    )
    if "README.md" not in changed:
        raise PreflightError("README must be reviewed and committed before merge")
    package_changed = any(path.startswith("adaptive-delegation/") for path in changed)
    if package_changed and not {
        "adaptive-delegation/VERSION",
        "CHANGELOG.md",
        "README.md",
    }.issubset(changed):
        raise PreflightError(
            "installable changes require VERSION, CHANGELOG, and README updates"
        )
    return {
        "branch": branch,
        "head": head,
        "origin_main": origin_main,
        "changed_paths": len(changed),
        "package_changed": package_changed,
    }


def _deploy_checks() -> dict[str, Any]:
    _require_clean_worktree()
    branch = _git("branch", "--show-current") or "detached"
    if branch not in {"main", "detached"}:
        raise PreflightError("deployment requires main or detached origin/main")
    head = _git("rev-parse", "HEAD")
    origin_main = _git("rev-parse", "origin/main")
    if head != origin_main:
        raise PreflightError("deployment commit must exactly match origin/main")
    return {"branch": branch, "head": head, "origin_main": origin_main}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pre-merge", "deploy"), required=True)
    args = parser.parse_args(argv)
    try:
        docs = _validate_repository_docs()
        git_evidence = (
            _pre_merge_checks() if args.mode == "pre-merge" else _deploy_checks()
        )
    except PreflightError as exc:
        print(f"release preflight failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"status": "passed", "mode": args.mode, "docs": docs, "git": git_evidence},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
