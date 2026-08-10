#!/usr/bin/env python3
"""Run an isolated, fresh-context promotion check without user-home writes.

This is a release-quality gate, not a security boundary: a same-user process can
always bypass filesystem checks. It is supported on current POSIX macOS/Linux
systems with Python 3.11 and a working ``codex`` executable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGED_RELATIVE_PATHS = (
    "skills/adaptive-delegation",
    "scripts/adaptive_dispatch_attestation.py",
    "agents",
    "state/adaptive-delegation",
    "state/model-routing",
)
TARGET_TEST = "test_target.TargetTests.test_normalizes_whitespace_and_case"
ADJACENT_TEST = "test_adjacent.AdjacentTests.test_known_failure_is_preserved"


@dataclass(frozen=True)
class GateResult:
    exit_code: int
    diagnostic: str


def fingerprint(root: Path) -> str:
    """Hash the selected managed surface without creating or changing it."""
    digest = hashlib.sha256()
    for relative in MANAGED_RELATIVE_PATHS:
        path = root / relative
        digest.update(relative.encode() + b"\0")
        if not path.exists() and not path.is_symlink():
            digest.update(b"missing\0")
            continue
        for child in sorted([path, *path.rglob("*")], key=lambda item: str(item)):
            child_relative = child.relative_to(root)
            digest.update(str(child_relative).encode() + b"\0")
            metadata = child.lstat()
            digest.update(
                f"{metadata.st_mode}:{metadata.st_size}:{metadata.st_mtime_ns}".encode()
                + b"\0"
            )
            if child.is_symlink():
                digest.update(b"symlink\0" + os.readlink(child).encode() + b"\0")
            elif child.is_file():
                digest.update(b"file\0" + child.read_bytes())
            elif child.is_dir():
                digest.update(b"directory\0")
            else:
                digest.update(b"other\0")
    return digest.hexdigest()


def write_fixture(fixture: Path) -> None:
    (fixture / "target.py").write_text(
        "def normalize(value):\n    return value\n", encoding="utf-8"
    )
    (fixture / "test_target.py").write_text(
        "import unittest\nfrom target import normalize\n\n"
        "class TargetTests(unittest.TestCase):\n"
        "    def test_normalizes_whitespace_and_case(self):\n"
        "        self.assertEqual(normalize('  HeLLo  '), 'hello')\n",
        encoding="utf-8",
    )
    (fixture / "test_adjacent.py").write_text(
        "import unittest\n\nclass AdjacentTests(unittest.TestCase):\n"
        "    def test_known_failure_is_preserved(self):\n"
        "        self.fail('intentional adjacent control failure')\n",
        encoding="utf-8",
    )
    run(["git", "init", "-q"], fixture)
    run(["git", "checkout", "-qb", "main"], fixture)
    run(["git", "add", "target.py", "test_target.py", "test_adjacent.py"], fixture)
    run(
        ["git", "-c", "user.name=isolated-gate", "-c", "user.email=gate@invalid", "commit", "-qm", "fixture"],
        fixture,
    )


def write_python_trace_wrapper(directory: Path, trace: Path) -> None:
    """Trace fresh-child python3 argv, then execute the real interpreter."""
    directory.mkdir(mode=0o700)
    wrapper = directory / "python3"
    interpreter = str(Path(sys.executable).resolve())
    wrapper.write_text(
        f"#!{interpreter}\n"
        "import json, os, pathlib, sys\n"
        f"trace = pathlib.Path({str(trace)!r})\n"
        "with trace.open('a', encoding='utf-8') as handle:\n"
        "    handle.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        f"os.execv({interpreter!r}, [{interpreter!r}, *sys.argv[1:]])\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)


def read_python_trace(trace: Path) -> list[list[str]]:
    if not trace.is_file():
        return []
    commands: list[list[str]] = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("python trace entry is not a string list")
        commands.append(value)
    return commands


def read_completed_commands(output: str) -> list[str]:
    """Extract completed main-session shell commands from Codex JSONL."""
    commands: list[str] = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict) or value.get("type") != "item.completed":
            continue
        item = value.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        command = item.get("command")
        if isinstance(command, str):
            commands.append(command)
    return commands


def preflight_violations(commands: list[str]) -> list[str]:
    """Reject optional package archaeology in the fresh bounded fixture."""
    violations: list[str] = []
    for command in commands:
        segments = re.split(r"&&|\|\||[;|\n]", command)
        optional_internal_read = any(
            marker in command
            for marker in (
                "TOKEN_EFFICIENCY_CONTINUITY.md",
                "read_continuity.py",
                "MODEL_ROUTING_POLICY.md",
                "dispatch_policy.py",
            )
        )
        dispatcher_archaeology = "adaptive_dispatch_attestation.py" in command and any(
            marker in command for marker in (" --help", "sed -n", "rg -n", "rg -l")
        )
        package_enumeration = any(
            "adaptive-delegation" in segment and "rg --files" in segment
            for segment in segments
        )
        broad_config_dump = any(
            "model-routing.defaults.json" in segment
            and any(marker in segment for marker in ("// .", "cat ", "sed -n"))
            for segment in segments
        )
        if (
            optional_internal_read
            or dispatcher_archaeology
            or package_enumeration
            or broad_config_dump
        ):
            violations.append(command)
    return violations


def reported_targeted_evidence(output: str) -> bool:
    normalized = output.lower()
    named_target = (
        TARGET_TEST.lower() in normalized
        or "exact requested unittest passed" in normalized
        or "exact targeted test passed" in normalized
    )
    scoped_diff = (
        "git diff -- target.py" in normalized
        or "scoped diff contains only the requested change" in normalized
    )
    one_test = "ran 1 test" in normalized or re.search(
        r"\b1 test\b[\s\S]{0,16}\bok\b", normalized
    ) is not None
    return named_target and one_test and scoped_diff


def run(command: list[str], cwd: Path, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=environment, text=True, capture_output=True, check=False)


def failed(diagnostic: str) -> GateResult:
    return GateResult(1, f"isolated promotion gate failed: {diagnostic}")


def checked_result(result: GateResult, user_codex_home: Path, before: str) -> GateResult:
    """Make user-home immutability the final verdict on every post-snapshot path."""
    if fingerprint(user_codex_home) != before:
        return failed(
            "user-level adaptive managed-files/state fingerprint changed; "
            f"prior result: {result.diagnostic}"
        )
    return result


def run_gate(
    *,
    repo_root: Path,
    auth_source: Path,
    user_codex_home: Path,
    keep_artifacts: bool,
    environment: dict[str, str],
    extra_codex_args: list[str],
) -> GateResult:
    if not auth_source.is_file():
        return failed("--auth-source must name an existing readable credential file")
    auth_source = auth_source.resolve(strict=True)
    before = fingerprint(user_codex_home)
    root = Path(tempfile.mkdtemp(prefix="adaptive-delegation-isolated-"))
    try:
        candidate_home = root / "candidate-codex-home"
        fixture = root / "fixture"
        trace_bin = root / "trace-bin"
        python_trace = root / "fresh-python-commands.jsonl"
        fixture.mkdir()
        write_fixture(fixture)
        write_python_trace_wrapper(trace_bin, python_trace)
        installed = run(
            [sys.executable, str(repo_root / "scripts" / "install.py"), "--codex-home", str(candidate_home)],
            repo_root,
            environment,
        )
        if installed.returncode:
            return checked_result(
                failed("candidate installation failed: " + installed.stderr.strip()),
                user_codex_home,
                before,
            )
        (candidate_home / "auth.json").symlink_to(auth_source)
        initial_adjacent = (fixture / "test_adjacent.py").read_bytes()
        gate_environment = {
            key: value
            for key, value in environment.items()
            if not key.startswith("CODEX_") and key not in {"HOME", "USER_CODEX_HOME"}
        }
        gate_environment["CODEX_HOME"] = str(candidate_home)
        gate_environment["HOME"] = str(candidate_home)
        gate_environment["PATH"] = (
            str(trace_bin) + os.pathsep + gate_environment.get("PATH", "")
        )
        if extra_codex_args and extra_codex_args[0] == "--test-expose-user-home":
            gate_environment["USER_CODEX_HOME"] = str(user_codex_home)
            extra_codex_args = extra_codex_args[1:]
        prompt = """$adaptive-delegation

Model: gpt-5.6-sol; reasoning effort: high.
**OBJECTIVE LOCK**: In this fixture, edit only target.py so normalize(value)
returns value.strip().lower(). Do not edit tests or any other file.
Non-goals: do not modify tests, inspect the adjacent failure, refactor unrelated
code, or add documentation or speculative robustness.
Acceptance evidence: run exactly `python3 -m unittest -v test_target.TargetTests.test_normalizes_whitespace_and_case`.
Verification ceiling: do not run broad tests, inspect unrelated files, or perform cleanup.
After sufficient evidence exists, do not perform additional reviews, repeated
validation, repository-wide analysis, or optional model consultations.
Stop condition: when that exact command passes and `git diff -- target.py` shows only the requested change, stop.
Final evidence line (required exactly): The exact requested unittest passed (Ran 1 test — OK), and git diff -- target.py showed only the requested change.
"""
        invocation = [
            "codex", "exec", "--ephemeral", "--json", "--ignore-user-config",
            "--disable", "apps", "--disable", "plugins", "--sandbox",
            "workspace-write", "--model", "gpt-5.6-sol", "--config",
            'model_reasoning_effort="high"', "--config", 'approval_policy="never"',
            *extra_codex_args, prompt,
        ]
        fresh = run(invocation, fixture, gate_environment)
        output = fresh.stdout + fresh.stderr
        if keep_artifacts:
            output_path = root / "fresh-output.jsonl"
            output_path.write_text(output, encoding="utf-8")
            output_path.chmod(0o600)
        if fresh.returncode:
            return checked_result(
                failed(
                    f"fresh codex command exited {fresh.returncode}: "
                    f"{output.strip()[-500:]}"
                ),
                user_codex_home,
                before,
            )
        if str(user_codex_home) in output:
            return checked_result(
                failed("fresh command output references the user Codex home"),
                user_codex_home,
                before,
            )
        if "test_adjacent" in output:
            return checked_result(
                failed("fresh command exceeded the declared verification ceiling"),
                user_codex_home,
                before,
            )
        violations = preflight_violations(read_completed_commands(output))
        if violations:
            return checked_result(
                failed(
                    "fresh main exceeded the Objective Lock during routing preflight: "
                    + repr(violations)
                ),
                user_codex_home,
                before,
            )
        expected_python_commands = [["-m", "unittest", "-v", TARGET_TEST]]
        try:
            observed_python_commands = read_python_trace(python_trace)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            return checked_result(
                failed(f"fresh verification trace is invalid: {exc}"),
                user_codex_home,
                before,
            )
        observed_unittests = [
            command
            for command in observed_python_commands
            if len(command) >= 2 and command[:2] == ["-m", "unittest"]
        ]
        if observed_unittests and observed_unittests != expected_python_commands:
            return checked_result(
                failed(
                    "fresh child must run exactly the declared targeted Python "
                    f"verification once; observed {observed_unittests!r}"
                ),
                user_codex_home,
                before,
            )
        if not observed_unittests and not reported_targeted_evidence(output):
            return checked_result(
                failed(
                    "native child verification was not visible in the Python trace "
                    "and the fresh result did not report the exact targeted evidence"
                ),
                user_codex_home,
                before,
            )
        changed = run(["git", "status", "--porcelain=v1"], fixture)
        changed_paths = [line[3:] for line in changed.stdout.splitlines()]
        if changed_paths != ["target.py"]:
            return checked_result(
                failed("scope drift: changed paths are " + repr(changed_paths)),
                user_codex_home,
                before,
            )
        target = (fixture / "target.py").read_text(encoding="utf-8")
        expected_target = "def normalize(value):\n    return value.strip().lower()\n"
        if target != expected_target:
            return checked_result(
                failed("target.py is not the exact required implementation"),
                user_codex_home,
                before,
            )
        targeted = run([sys.executable, "-m", "unittest", "-v", TARGET_TEST], fixture, gate_environment)
        if targeted.returncode:
            return checked_result(
                failed("targeted unittest failed: " + targeted.stderr.strip()),
                user_codex_home,
                before,
            )
        adjacent = run([sys.executable, "-m", "unittest", "-v", ADJACENT_TEST], fixture, gate_environment)
        if adjacent.returncode == 0:
            return checked_result(
                failed("adjacent known failing test unexpectedly passed"),
                user_codex_home,
                before,
            )
        if (fixture / "test_adjacent.py").read_bytes() != initial_adjacent:
            return checked_result(
                failed("adjacent known failing test was changed"),
                user_codex_home,
                before,
            )
        return checked_result(
            GateResult(0, "isolated promotion gate passed"),
            user_codex_home,
            before,
        )
    except OSError as exc:
        return checked_result(
            failed(f"required local command could not run: {exc.filename or exc}"),
            user_codex_home,
            before,
        )
    finally:
        if keep_artifacts:
            print(f"isolated promotion artifacts retained at: {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth-source", type=Path, required=True, help="Existing auth file to expose only by symlink in the temporary candidate home.")
    parser.add_argument("--user-codex-home", type=Path, default=Path.home() / ".codex", help="Read-only user home to fingerprint (default: ~/.codex).")
    parser.add_argument("--keep-artifacts", action="store_true", help="Retain temporary fixture/candidate only for investigation.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gate(repo_root=ROOT, auth_source=args.auth_source, user_codex_home=args.user_codex_home, keep_artifacts=args.keep_artifacts, environment=dict(os.environ), extra_codex_args=[])
    print(result.diagnostic)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
