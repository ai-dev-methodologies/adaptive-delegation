#!/usr/bin/env python3
"""Install the portable adaptive-delegation package into a Codex home."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import re
import shlex
import shutil
import stat
import sys
import tempfile
import uuid
from pathlib import Path

try:
    from package_manifest import PackageManifestError, runtime_relative_paths
except ModuleNotFoundError:  # pragma: no cover - importlib-based test loading
    from scripts.package_manifest import (
        PackageManifestError,
        runtime_relative_paths,
    )

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - requires Python <= 3.10
    raise SystemExit("adaptive-delegation requires Python 3.11 or newer") from exc


PACKAGE_NAME = "adaptive-delegation"
DISPATCHER_NAME = "adaptive_dispatch_attestation.py"
CONTINUITY_READER_NAME = "read_continuity.py"
CONTROLLER_GATE_NAME = "controller_gate.py"
CONTROLLER_TRUST_START = "# adaptive-delegation-controller-trust:start"
CONTROLLER_TRUST_END = "# adaptive-delegation-controller-trust:end"
MANAGED_ROLE_NAME = re.compile(r"^adaptive-[a-z0-9-]+$")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


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


def _load_policy(package: Path) -> dict:
    config_path = package / "config" / "model-routing.defaults.json"
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallError(f"invalid policy config: {exc}") from exc
    if not isinstance(value, dict):
        raise InstallError("policy config must be a JSON object")
    return value


def _load_package_version(package: Path) -> str:
    version_path = package / "VERSION"
    try:
        value = version_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise InstallError(f"invalid package version: {exc}") from exc
    match = SEMVER_PATTERN.fullmatch(value)
    if match is None:
        raise InstallError("package VERSION must contain one Semantic Version")
    prerelease = match.group(4)
    if prerelease and any(
        identifier.isdigit() and len(identifier) > 1 and identifier[0] == "0"
        for identifier in prerelease.split(".")
    ):
        raise InstallError("package VERSION has an invalid numeric prerelease")
    return value


def _validate_package(package: Path) -> list[Path]:
    required = [
        package / "VERSION",
        package / "SKILL.md",
        package / "agents" / "openai.yaml",
        package / "config" / "model-routing.defaults.json",
        package / "scripts" / DISPATCHER_NAME,
        package / "scripts" / CONTINUITY_READER_NAME,
        package / "scripts" / CONTROLLER_GATE_NAME,
        package / "scripts" / "dispatch_policy.py",
        package / "scripts" / "model_routing_audit.py",
    ]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise InstallError(
            "package is incomplete: " + ", ".join(str(path) for path in missing)
        )

    _load_package_version(package)
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
            CONTROLLER_GATE_NAME,
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


def _load_hooks(path: Path) -> dict:
    _reject_symlink(path, "Codex hooks file")
    if not path.exists():
        return {"hooks": {}}
    if not path.is_file():
        raise InstallError(f"Codex hooks path is not a file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallError(f"invalid Codex hooks file: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("hooks"), dict):
        raise InstallError("Codex hooks file must contain a hooks object")
    return value


def _controller_hook_command(target_skill: Path) -> str:
    controller = target_skill / "scripts" / CONTROLLER_GATE_NAME
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(controller))}"


def _is_managed_controller_command(existing: object, expected: str) -> bool:
    if not isinstance(existing, str):
        return False
    try:
        existing_parts = shlex.split(existing)
        expected_parts = shlex.split(expected)
    except ValueError:
        return False
    return (
        len(existing_parts) == 2
        and len(expected_parts) == 2
        and existing_parts[1] == expected_parts[1]
    )


def _reconcile_controller_hooks(value: dict, command: str) -> dict:
    updated = json.loads(json.dumps(value))
    hooks = updated["hooks"]
    for event in ("UserPromptSubmit", "PreToolUse"):
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            raise InstallError(f"Codex hooks {event} entry must be a list")
        retained = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise InstallError(f"Codex hooks {event} group is invalid")
            filtered = []
            for hook in group["hooks"]:
                if not isinstance(hook, dict):
                    raise InstallError(f"Codex hooks {event} command is invalid")
                if not _is_managed_controller_command(hook.get("command"), command):
                    filtered.append(hook)
            if filtered:
                retained.append({**group, "hooks": filtered})
        retained.append(
            {"hooks": [{"type": "command", "command": command}]}
        )
        hooks[event] = retained
    return updated


def _atomic_json(value: dict, target: Path) -> None:
    _reject_symlink(target, "Codex hooks file")
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def _load_config_text(path: Path) -> str:
    _reject_symlink(path, "Codex config file")
    if not path.exists():
        return ""
    if not path.is_file():
        raise InstallError(f"Codex config path is not a file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        tomllib.loads(text)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise InstallError(f"invalid Codex config file: {exc}") from exc
    return text


def _controller_trust_entries(
    hooks_document: dict, hooks_path: Path, command: str
) -> list[tuple[str, str]]:
    labels = {
        "PreToolUse": "pre_tool_use",
        "UserPromptSubmit": "user_prompt_submit",
    }
    entries: list[tuple[str, str]] = []
    for event, label in labels.items():
        for group_index, group in enumerate(hooks_document["hooks"].get(event, [])):
            for hook_index, hook in enumerate(group.get("hooks", [])):
                if hook.get("command") != command:
                    continue
                identity = {
                    "event_name": label,
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                            "timeout": hook.get("timeout", 600),
                            "async": hook.get("async", False),
                        }
                    ],
                }
                if event == "PreToolUse" and group.get("matcher"):
                    identity["matcher"] = group["matcher"]
                canonical = json.dumps(
                    identity,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                key = f'{hooks_path}:{label}:{group_index}:{hook_index}'
                entries.append((key, f"sha256:{digest}"))
    if len(entries) != 2:
        raise InstallError("controller hook trust entries could not be resolved exactly")
    return sorted(entries)


def _controller_trust_keys(
    hooks_document: dict, hooks_path: Path, command: str
) -> set[str]:
    labels = {
        "PreToolUse": "pre_tool_use",
        "UserPromptSubmit": "user_prompt_submit",
    }
    keys: set[str] = set()
    for event, label in labels.items():
        groups = hooks_document.get("hooks", {}).get(event, [])
        if not isinstance(groups, list):
            continue
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            for hook_index, hook in enumerate(group["hooks"]):
                existing = hook.get("command") if isinstance(hook, dict) else None
                if _is_managed_controller_command(existing, command):
                    keys.add(f"{hooks_path}:{label}:{group_index}:{hook_index}")
    return keys


def _strip_exact_trust_tables(config_text: str, keys: set[str]) -> str:
    result = config_text
    for key in sorted(keys):
        result = re.sub(
            rf'(?m)^\[hooks\.state\."{re.escape(key)}"\]\n'
            r'(?:(?:trusted_hash|enabled)\s*=.*\n|\s*\n)*',
            "",
            result,
        )
    return result


def _render_controller_trust(
    config_text: str,
    hooks_document: dict,
    hooks_path: Path,
    command: str,
    stale_keys: set[str] | None = None,
) -> str:
    block_pattern = re.compile(
        rf"(?ms)^\s*{re.escape(CONTROLLER_TRUST_START)}\n.*?"
        rf"{re.escape(CONTROLLER_TRUST_END)}\s*\n?"
    )
    cleaned = block_pattern.sub("\n", config_text)
    entries = _controller_trust_entries(hooks_document, hooks_path, command)
    replacement_keys = {key for key, _ in entries}
    cleaned = _strip_exact_trust_tables(
        cleaned, replacement_keys | (stale_keys or set())
    ).rstrip()
    if not re.search(r"(?m)^\[hooks\.state\]\s*$", cleaned):
        cleaned += ("\n\n" if cleaned else "") + "[hooks.state]"
    rendered = [CONTROLLER_TRUST_START]
    for key, digest in entries:
        escaped_key = key.replace("\\", "\\\\").replace('"', '\\"')
        rendered.extend(
            [
                f'[hooks.state."{escaped_key}"]',
                f'trusted_hash = "{digest}"',
                "",
            ]
        )
    rendered.append(CONTROLLER_TRUST_END)
    result = cleaned + "\n\n" + "\n".join(rendered) + "\n"
    try:
        tomllib.loads(result)
    except tomllib.TOMLDecodeError as exc:
        raise InstallError(f"controller hook trust would invalidate config.toml: {exc}") from exc
    return result


def _atomic_text(value: str, target: Path) -> None:
    _reject_symlink(target, "Codex config file")
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        os.write(descriptor, value.encode("utf-8"))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def _atomic_package(
    source: Path, target: Path, runtime_paths: tuple[str, ...]
) -> None:
    _reject_symlink(target, "installed skill")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{PACKAGE_NAME}.staging-", dir=target.parent)
    )
    backup = target.parent / f".{PACKAGE_NAME}.backup-{uuid.uuid4().hex}"
    moved_existing = False
    try:
        shutil.rmtree(staging)
        staging.mkdir()
        for relative in runtime_paths:
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, destination)
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
    try:
        runtime_paths = runtime_relative_paths(source)
    except PackageManifestError as exc:
        raise InstallError(str(exc)) from exc
    package_version = _load_package_version(source)
    target_skill = skills_root / PACKAGE_NAME
    dispatcher_target = codex_home / "scripts" / DISPATCHER_NAME
    hooks_target = codex_home / "hooks.json"
    config_target = codex_home / "config.toml"
    controller_command = _controller_hook_command(target_skill)
    original_hooks = _load_hooks(hooks_target)
    stale_controller_trust_keys = _controller_trust_keys(
        original_hooks, hooks_target, controller_command
    )
    reconciled_hooks = _reconcile_controller_hooks(original_hooks, controller_command)
    reconciled_config = _render_controller_trust(
        _load_config_text(config_target),
        reconciled_hooks,
        hooks_target,
        controller_command,
        stale_controller_trust_keys,
    )
    managed_roles = [role for role in role_paths if role.stem.startswith("adaptive-")]
    agent_targets = [codex_home / "agents" / role.name for role in managed_roles]
    previous_roles = _previous_managed_role_names(target_skill)
    current_roles = {role.stem for role in managed_roles}
    obsolete_role_targets = [
        codex_home / "agents" / f"{name}.toml"
        for name in sorted(previous_roles - current_roles)
    ]

    print(f"skill: {target_skill}")
    print(f"package version: {package_version}")
    print(f"dispatcher: {dispatcher_target}")
    print(f"controller hooks: UserPromptSubmit, PreToolUse in {hooks_target}")
    print(f"controller hook trust: {config_target}")
    print(f"role bindings: {len(agent_targets)} under {codex_home / 'agents'}")
    if dry_run:
        print("dry-run: validation passed; no files changed")
        return

    _ensure_directory(codex_home)
    _ensure_directory(skills_root)
    _ensure_directory(codex_home / "scripts")
    _ensure_directory(codex_home / "agents")

    _atomic_package(source, target_skill, runtime_paths)
    _atomic_file(
        target_skill / "scripts" / DISPATCHER_NAME,
        dispatcher_target,
        0o700,
    )
    _atomic_json(reconciled_hooks, hooks_target)
    _atomic_text(reconciled_config, config_target)
    for source_role, target_role in zip(managed_roles, agent_targets, strict=True):
        _atomic_file(target_skill / "roles" / source_role.name, target_role, 0o600)
    for obsolete_role in obsolete_role_targets:
        _remove_obsolete_role(obsolete_role)

    if stat.S_IMODE(dispatcher_target.stat().st_mode) != 0o700:
        raise InstallError("dispatcher permission verification failed")
    print(
        "installed: package version "
        f"{package_version}, dispatcher, controller hooks, and policy-matched role bindings"
    )
    print("Start a fresh Codex process before validating the installed controller hooks.")


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
