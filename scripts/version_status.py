#!/usr/bin/env python3
"""Compare the repository package with an installed Codex skill, read only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from package_manifest import PackageManifestError, runtime_relative_paths
except ModuleNotFoundError:  # pragma: no cover - importlib-based test loading
    from scripts.package_manifest import (
        PackageManifestError,
        runtime_relative_paths,
    )


PACKAGE_NAME = "adaptive-delegation"
VERSION_NAME = "VERSION"
SCHEMA_VERSION = 1
SKIP_NAMES = {".DS_Store", "__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class VersionStatusError(RuntimeError):
    """A bounded local comparison failure."""


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...]

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        match = SEMVER_PATTERN.fullmatch(value)
        if match is None:
            raise VersionStatusError(f"invalid Semantic Version: {value!r}")
        prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
        for identifier in prerelease:
            if identifier.isdigit() and len(identifier) > 1 and identifier[0] == "0":
                raise VersionStatusError(
                    f"invalid numeric prerelease identifier: {identifier!r}"
                )
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease)

    def compare(self, other: "SemVer") -> int:
        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core:
            return 1 if core > other_core else -1
        if self.prerelease == other.prerelease:
            return 0
        if not self.prerelease:
            return 1
        if not other.prerelease:
            return -1
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return 1 if int(left) > int(right) else -1
            if left_numeric != right_numeric:
                return -1 if left_numeric else 1
            return 1 if left > right else -1
        return 1 if len(self.prerelease) > len(other.prerelease) else -1


def _read_version(package: Path, *, required: bool) -> str | None:
    path = package / VERSION_NAME
    if not path.exists():
        if required:
            raise VersionStatusError(f"missing package version: {path}")
        return None
    if path.is_symlink() or not path.is_file():
        raise VersionStatusError(f"package version must be a regular file: {path}")
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise VersionStatusError(f"cannot read package version: {path}") from exc
    SemVer.parse(value)
    return value


def _file_hashes(
    package: Path, relative_paths: tuple[str, ...] | None = None
) -> dict[str, str]:
    if package.is_symlink() or not package.is_dir():
        raise VersionStatusError(f"package must be a regular directory: {package}")
    hashes: dict[str, str] = {}
    for root, directories, files in os.walk(package, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in SKIP_NAMES)
        root_path = Path(root)
        for name in sorted(files):
            path = root_path / name
            if name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES:
                continue
            relative = path.relative_to(package).as_posix()
            if relative_paths is not None and relative not in relative_paths:
                continue
            metadata = path.lstat()
            digest = hashlib.sha256()
            if stat.S_ISLNK(metadata.st_mode):
                digest.update(b"symlink\0")
                digest.update(os.readlink(path).encode("utf-8"))
            elif stat.S_ISREG(metadata.st_mode):
                digest.update(b"file\0")
                with path.open("rb") as handle:
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
            else:
                raise VersionStatusError(f"unsupported package entry: {path}")
            hashes[relative] = digest.hexdigest()
    return hashes


def _package_digest(hashes: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative, value in sorted(hashes.items()):
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(value.encode("ascii") + b"\0")
    return digest.hexdigest()


def compare(repo_root: Path, codex_home: Path) -> dict[str, Any]:
    source = repo_root / PACKAGE_NAME
    installed = codex_home / "skills" / PACKAGE_NAME
    source_version = _read_version(source, required=True)
    assert source_version is not None
    try:
        runtime_paths = runtime_relative_paths(source)
    except PackageManifestError as exc:
        raise VersionStatusError(str(exc)) from exc
    source_hashes = _file_hashes(source, runtime_paths)
    source_digest = _package_digest(source_hashes)

    if not installed.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "not_installed",
            "source": {"version": source_version, "package_digest": source_digest},
            "installed": {"exists": False, "version": None, "package_digest": None},
            "changes": {
                "source_only": sorted(source_hashes),
                "installed_only": [],
                "modified": [],
            },
            "next_action": "validate_then_install",
        }

    installed_version = _read_version(installed, required=False)
    installed_hashes = _file_hashes(installed)
    installed_digest = _package_digest(installed_hashes)
    source_paths = set(source_hashes)
    installed_paths = set(installed_hashes)
    changes = {
        "source_only": sorted(source_paths - installed_paths),
        "installed_only": sorted(installed_paths - source_paths),
        "modified": sorted(
            path
            for path in source_paths & installed_paths
            if source_hashes[path] != installed_hashes[path]
        ),
    }

    if installed_version is None:
        status = "installed_unversioned"
        next_action = "review_diff_then_validate_update"
    else:
        ordering = SemVer.parse(source_version).compare(SemVer.parse(installed_version))
        if ordering > 0:
            status = "update_available"
            next_action = "review_changelog_then_validate_update"
        elif ordering < 0:
            status = "source_older"
            next_action = "confirm_intended_rollback"
        elif source_digest == installed_digest:
            status = "current"
            next_action = "none"
        else:
            status = "same_version_drift"
            next_action = "investigate_or_reinstall_verified_source"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "source": {"version": source_version, "package_digest": source_digest},
        "installed": {
            "exists": True,
            "version": installed_version,
            "package_digest": installed_digest,
        },
        "changes": changes,
        "next_action": next_action,
    }


def _render_text(result: dict[str, Any]) -> str:
    installed_version = result["installed"]["version"] or (
        "not-installed" if not result["installed"]["exists"] else "unversioned"
    )
    lines = [
        f"status: {result['status']}",
        f"source_version: {result['source']['version']}",
        f"installed_version: {installed_version}",
        f"source_digest: {result['source']['package_digest']}",
        f"installed_digest: {result['installed']['package_digest'] or 'unavailable'}",
    ]
    for category in ("source_only", "installed_only", "modified"):
        values = result["changes"][category]
        lines.append(f"{category}: {', '.join(values) if values else 'none'}")
    lines.append(f"next_action: {result['next_action']}")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root containing adaptive-delegation/",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
        help="Codex home containing skills/adaptive-delegation/",
    )
    parser.add_argument("--json", action="store_true", help="Print stable JSON")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = compare(args.repo_root.resolve(), args.codex_home.resolve())
    except VersionStatusError as exc:
        print(f"version status failed: {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True) if args.json else _render_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
