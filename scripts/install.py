#!/usr/bin/env python3
"""Install the portable adaptive-delegation package into a Codex home."""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
import shutil
import stat
import tempfile
import uuid
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - requires Python <= 3.10
    raise SystemExit("adaptive-delegation requires Python 3.11 or newer") from exc


PACKAGE_NAME = "adaptive-delegation"
DISPATCHER_NAME = "adaptive_dispatch_attestation.py"
CONTINUITY_READER_NAME = "read_continuity.py"
SKIP_NAMES = {".DS_Store", "__pycache__"}
MANAGED_ROLE_NAME = re.compile(r"^adaptive-[a-z0-9-]+$")


class InstallError(RuntimeError):
    """A safe, user-correctable installation failure."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
        help="Codex home directory (default: $CODEX_HOME or ~/.codex)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print targets without changing them",
    )
    return parser


def _reject_symlink(path: Path, label: str) -> None:
    if os.path.lexists(path) and path.is_symlink():
        raise InstallError(f"{label} must not be a symlink: {path}")


def _copy_allowed(source: str, names: list[str]) -> set[str]:
    del source
    return {
        name
        for name in names
        if name in SKIP_NAMES or name.endswith((".pyc", ".pyo"))
    }


def _load_policy(package: Path) -> dict:
    config_path = package / "config" / "model-routing.defaults.json"
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallError(f"invalid policy config: {exc}") from exc
    if not isinstance(value, dict):
        raise InstallError("policy config must be a JSON object")
    return value


def _validate_package(package: Path) -> list[Path]:
    required = [
        package / "SKILL.md",
        package / "agents" / "openai.yaml",
        package / "config" / "model-routing.defaults.json",
        package / "scripts" / DISPATCHER_NAME,
        package / "scripts" / CONTINUITY_READER_NAME,
        package / "scripts" / "dispatch_policy.py",
        package / "scripts" / "model_routing_audit.py",
    ]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise InstallError(
            "package is incomplete: " + ", ".join(str(path) for path in missing)
        )

    policy = _load_policy(package)
    bindings = policy.get("role_bindings")
    if not isinstance(bindings, dict) or not bindings:
        raise InstallError("policy role_bindings must be a non-empty object")

    role_paths: list[Path] = []
    for role_name, binding in sorted(bindings.items()):
        role_path = package / "roles" / f"{role_name}.toml"
        if not role_path.is_file():
            raise InstallError(f"missing role template: {role_path}")
        try:
            role = tomllib.loads(role_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise InstallError(f"invalid role template {role_path}: {exc}") from exc
        expected = (
            binding.get("model"),
            binding.get("reasoning_effort"),
        ) if isinstance(binding, dict) else (None, None)
        observed = (role.get("model"), role.get("model_reasoning_effort"))
        if role.get("name") != role_name or observed != expected:
            raise InstallError(f"role template does not match policy: {role_name}")
        role_paths.append(role_path)

    with tempfile.TemporaryDirectory(prefix="adaptive-delegation-compile-") as temp:
        for name in (
            DISPATCHER_NAME,
            CONTINUITY_READER_NAME,
            "dispatch_policy.py",
            "model_routing_audit.py",
        ):
            try:
                py_compile.compile(
                    str(package / "scripts" / name),
                    cfile=str(Path(temp) / f"{name}c"),
                    doraise=True,
                )
            except py_compile.PyCompileError as exc:
                raise InstallError(f"invalid Python source {name}: {exc.msg}") from exc
    return role_paths


def _ensure_directory(path: Path, mode: int = 0o700) -> None:
    _reject_symlink(path, "installation directory")
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise InstallError(f"installation path is not a directory: {path}")
    if not existed:
        path.chmod(mode)


def _previous_managed_role_names(installed_package: Path) -> set[str]:
    """Return only safely named roles declared by the previous package."""
    config_path = installed_package / "config" / "model-routing.defaults.json"
    if not config_path.is_file() or config_path.is_symlink():
        return set()
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set()
    bindings = value.get("role_bindings") if isinstance(value, dict) else None
    if not isinstance(bindings, dict):
        return set()
    return {
        name
        for name in bindings
        if isinstance(name, str) and MANAGED_ROLE_NAME.fullmatch(name)
    }


def _remove_obsolete_role(path: Path) -> None:
    _reject_symlink(path, "obsolete managed role")
    if not path.exists():
        return
    if not path.is_file():
        raise InstallError(f"obsolete managed role is not a file: {path}")
    try:
        path.unlink()
    except OSError as exc:
        raise InstallError(f"could not remove obsolete managed role: {path}") from exc


def _atomic_file(source: Path, target: Path, mode: int) -> None:
    _reject_symlink(target, "managed target")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as input_file:
            shutil.copyfileobj(input_file, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(mode)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_package(source: Path, target: Path) -> None:
    _reject_symlink(target, "installed skill")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{PACKAGE_NAME}.staging-", dir=target.parent)
    )
    backup = target.parent / f".{PACKAGE_NAME}.backup-{uuid.uuid4().hex}"
    moved_existing = False
    try:
        shutil.rmtree(staging)
        shutil.copytree(source, staging, ignore=_copy_allowed)
        _validate_package(staging)
        if target.exists():
            os.replace(target, backup)
            moved_existing = True
        os.replace(staging, target)
    except Exception:
        if moved_existing and not target.exists() and backup.exists():
            os.replace(backup, target)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists():
            shutil.rmtree(backup)


def install(repo_root: Path, codex_home: Path, skills_root: Path, dry_run: bool) -> None:
    source = repo_root / PACKAGE_NAME
    role_paths = _validate_package(source)
    target_skill = skills_root / PACKAGE_NAME
    dispatcher_target = codex_home / "scripts" / DISPATCHER_NAME
    managed_roles = [role for role in role_paths if role.stem.startswith("adaptive-")]
    agent_targets = [codex_home / "agents" / role.name for role in managed_roles]
    previous_roles = _previous_managed_role_names(target_skill)
    current_roles = {role.stem for role in managed_roles}
    obsolete_role_targets = [
        codex_home / "agents" / f"{name}.toml"
        for name in sorted(previous_roles - current_roles)
    ]

    print(f"skill: {target_skill}")
    print(f"dispatcher: {dispatcher_target}")
    print(f"role bindings: {len(agent_targets)} under {codex_home / 'agents'}")
    if dry_run:
        print("dry-run: validation passed; no files changed")
        return

    _ensure_directory(codex_home)
    _ensure_directory(skills_root)
    _ensure_directory(codex_home / "scripts")
    _ensure_directory(codex_home / "agents")

    _atomic_package(source, target_skill)
    _atomic_file(
        target_skill / "scripts" / DISPATCHER_NAME,
        dispatcher_target,
        0o700,
    )
    for source_role, target_role in zip(managed_roles, agent_targets, strict=True):
        _atomic_file(target_skill / "roles" / source_role.name, target_role, 0o600)
    for obsolete_role in obsolete_role_targets:
        _remove_obsolete_role(obsolete_role)

    if stat.S_IMODE(dispatcher_target.stat().st_mode) != 0o700:
        raise InstallError("dispatcher permission verification failed")
    print("installed: package, dispatcher, and policy-matched role bindings")
    print("Codex detects skill changes automatically; restart only if this update is not visible.")


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    codex_home = args.codex_home.expanduser().resolve()
    skills_root = codex_home / "skills"
    try:
        install(repo_root, codex_home, skills_root, args.dry_run)
    except InstallError as exc:
        print(f"install failed: {exc}", file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
