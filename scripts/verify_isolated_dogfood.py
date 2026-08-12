#!/usr/bin/env python3
"""Run an isolated promotion check without user installation-surface writes.

This is a release-quality gate, not a security boundary: a same-user process can
always bypass filesystem checks. It is supported on current POSIX macOS/Linux
systems with Python 3.11 and a working ``codex`` executable. Controller-only
Native execution may append normal owner-only runtime audit evidence; that
state is deliberately outside the immutable installation fingerprint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMMUTABLE_USER_RELATIVE_PATHS = (
    "skills/adaptive-delegation",
    "scripts/adaptive_dispatch_attestation.py",
    "agents",
    "hooks.json",
    "config.toml",
)
TARGET_TEST = "test_target.TargetTests.test_normalizes_whitespace_and_case"
ADJACENT_TEST = "test_adjacent.AdjacentTests.test_known_failure_is_preserved"
MAX_ROLLOUT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class GateResult:
    exit_code: int
    diagnostic: str


def fingerprint(root: Path) -> str:
    """Hash the selected managed surface without creating or changing it."""
    digest = hashlib.sha256()
    for relative in IMMUTABLE_USER_RELATIVE_PATHS:
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


def read_jsonl(path: Path, *, maximum_bytes: int = MAX_ROLLOUT_BYTES) -> list[dict]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"JSONL evidence is not a regular file: {path}")
    metadata = path.stat()
    if metadata.st_size <= 0 or metadata.st_size > maximum_bytes:
        raise ValueError(f"JSONL evidence has invalid size: {path}")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise ValueError(f"JSONL evidence is group/world writable: {path}")
    payload = path.read_bytes()
    if not payload.endswith(b"\n"):
        raise ValueError(f"JSONL evidence is not newline terminated: {path}")
    rows: list[dict] = []
    for line in payload.splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL evidence row is not an object: {path}")
        rows.append(value)
    return rows


def read_json_object(path: Path, *, maximum_bytes: int = 1024 * 1024) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"JSON evidence is not a regular file: {path}")
    metadata = path.stat()
    if metadata.st_size <= 0 or metadata.st_size > maximum_bytes:
        raise ValueError(f"JSON evidence has invalid size: {path}")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise ValueError(f"JSON evidence is group/world writable: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON evidence is not an object: {path}")
    return value


def derive_parent_session_id(output: str) -> str:
    sessions: list[str] = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            raise ValueError("fresh output JSON row is not an object")
        if value.get("type") == "thread.started" and isinstance(
            value.get("thread_id"), str
        ):
            sessions.append(value["thread_id"])
    if len(sessions) != 1 or not sessions[0]:
        raise ValueError(f"expected one fresh parent session, observed {sessions!r}")
    return sessions[0]


def controller_state_path(candidate_home: Path, session_id: str, fixture: Path) -> Path:
    material = f"{session_id}\0{fixture.resolve()}".encode("utf-8")
    key = hashlib.sha256(material).hexdigest()
    return (
        candidate_home
        / "state"
        / "adaptive-delegation"
        / "controller"
        / f"state-{key}.json"
    )


def validate_controller_lifecycle(
    candidate_home: Path, fixture: Path, session_id: str
) -> dict:
    state_path = controller_state_path(candidate_home, session_id, fixture)
    try:
        state = read_json_object(state_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"controller state is unavailable or invalid: {exc}") from exc
    workspace = str(fixture.resolve())
    planned = state.get("planned_launch")
    exact_planned = {
        "agent_type": "adaptive-luna-maker-high",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "high",
        "fork_turns": "none",
    }
    if not isinstance(planned, dict) or any(
        planned.get(key) != expected for key, expected in exact_planned.items()
    ) or not isinstance(planned.get("task_name"), str) or re.fullmatch(
        r"adaptive_[0-9a-f]{64}", planned["task_name"]
    ) is None:
        raise ValueError(f"controller planned launch is not exact: {planned!r}")
    if not (
        state.get("schema_version") == "1"
        and state.get("session_id") == session_id
        and state.get("workspace") == workspace
        and state.get("phase") == "closed"
        and state.get("terminal_status") == "complete"
        and state.get("last_outcome") == "accepted"
        and state.get("last_integration_accepted") is True
    ):
        raise ValueError("controller did not close with an accepted integrated leaf result")
    digest = state.get("objective_lock_digest")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("controller Objective Lock digest is invalid")
    activation_id = state.get("activation_id")
    if not isinstance(activation_id, str) or re.fullmatch(
        r"[0-9a-f]{64}", activation_id
    ) is None:
        raise ValueError("controller activation identity is invalid")
    ledger = state_path.parent / "controller-events.jsonl"
    ledger_rows = read_jsonl(ledger)
    if any(
        row.get("schema_version") != "1"
        or row.get("session_id") != session_id
        or row.get("workspace") != workspace
        or row.get("activation_id") != activation_id
        for row in ledger_rows
    ):
        raise ValueError("controller ledger contains foreign or malformed lifecycle evidence")
    rows = ledger_rows
    required = ["delegation_decision", "leaf_launch_authorized", "leaf_result_recorded", "controller_closed"]
    selected = [row for row in rows if row.get("event_type") in required]
    if [row.get("event_type") for row in selected] != required:
        raise ValueError("controller lifecycle is incomplete or duplicated")
    decision, launch, result, close = selected
    if not (
        decision.get("decision") == "leaf_required"
        and decision.get("planned_launch") == planned
        and launch.get("planned_launch") == planned
        and result.get("planned_launch") == planned
        and all(row.get("objective_lock_digest") == digest for row in selected)
        and result.get("outcome") == "accepted"
        and result.get("quality_verdict") == "pass"
        and result.get("integration_accepted") is True
        and close.get("terminal_status") == "complete"
    ):
        raise ValueError("controller lifecycle evidence does not match the closed state")
    return planned


def _exec_command_from_input(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r'(?:"cmd"|cmd)\s*:\s*("(?:\\.|[^"\\])*")', value)
    if match is None:
        return None
    command = json.loads(match.group(1))
    return command if isinstance(command, str) else None


def validate_child_rollout(
    candidate_home: Path, fixture: Path, session_id: str, planned: dict
) -> None:
    sessions = candidate_home / "sessions"
    if sessions.is_symlink() or not sessions.is_dir():
        raise ValueError("candidate sessions directory is unavailable or unsafe")
    transcripts = sorted(sessions.rglob("*.jsonl"))
    if len(transcripts) != 1:
        raise ValueError(f"expected one isolated child rollout, observed {len(transcripts)}")
    transcript = transcripts[0]
    resolved = transcript.resolve(strict=True)
    try:
        resolved.relative_to(sessions.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("child rollout escapes the candidate sessions directory") from exc
    rows = read_jsonl(transcript)
    if not rows or rows[0].get("type") != "session_meta":
        raise ValueError("child rollout is missing session metadata")
    metadata = rows[0].get("payload")
    source = metadata.get("source") if isinstance(metadata, dict) else None
    subagent = source.get("subagent") if isinstance(source, dict) else None
    spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
    expected_path = f"/root/{planned['task_name']}"
    if not (
        isinstance(metadata, dict)
        and isinstance(spawn, dict)
        and metadata.get("session_id") == session_id
        and metadata.get("parent_thread_id") == session_id
        and metadata.get("cwd") == str(fixture.resolve())
        and metadata.get("thread_source") == "subagent"
        and metadata.get("agent_role") == planned["agent_type"]
        and metadata.get("agent_path") == expected_path
        and spawn.get("parent_thread_id") == session_id
        and spawn.get("agent_role") == planned["agent_type"]
        and spawn.get("agent_path") == expected_path
    ):
        raise ValueError("child rollout metadata does not match the authorized launch")
    task_rows = [
        (index, row["payload"].get("turn_id"))
        for index, row in enumerate(rows)
        if row.get("type") == "event_msg"
        and isinstance(row.get("payload"), dict)
        and row["payload"].get("type") == "task_started"
    ]
    contexts = [
        row.get("payload") for row in rows if row.get("type") == "turn_context"
    ]
    if len(task_rows) != 1 or not isinstance(task_rows[0][1], str) or not task_rows[0][1]:
        raise ValueError("child rollout has no unique task turn")
    task_index, task_turn = task_rows[0]
    if not any(
        isinstance(context, dict)
        and context.get("turn_id") == task_turn
        and context.get("model") == planned["model"]
        and context.get("effort") == planned["reasoning_effort"]
        for context in contexts
    ):
        raise ValueError("child rollout model or effort does not match the authorized launch")
    state = read_json_object(controller_state_path(candidate_home, session_id, fixture))
    bound_turn = state.get("child_turn_id")
    bound_transcript = state.get("child_transcript_path")
    if bound_turn is not None or bound_transcript is not None:
        if bound_turn != task_turn or bound_transcript != str(resolved):
            raise ValueError("controller child binding does not match the rollout")
    calls: dict[str, str] = {}
    outputs: dict[str, object] = {}
    all_unittests: list[str] = []
    for row in rows[task_index + 1 :]:
        payload = row.get("payload")
        if row.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        if payload.get("type") == "custom_tool_call" and payload.get("name") == "exec":
            command = _exec_command_from_input(payload.get("input"))
            call_id = payload.get("call_id")
            if command is not None and "-m unittest" in command and isinstance(call_id, str):
                if call_id in calls:
                    raise ValueError("child rollout duplicates a verification call identity")
                all_unittests.append(command)
                calls[call_id] = command
        elif payload.get("type") == "custom_tool_call_output" and isinstance(
            payload.get("call_id"), str
        ):
            call_id = payload["call_id"]
            if call_id in outputs:
                raise ValueError("child rollout duplicates a tool output identity")
            outputs[call_id] = payload.get("output")
    expected = f"python3 -m unittest -v {TARGET_TEST}"
    if all_unittests != [expected]:
        raise ValueError(
            "child must run exactly the declared targeted Python verification once; "
            f"observed {all_unittests!r}"
        )
    call_id = next(iter(calls))
    if call_id not in outputs:
        raise ValueError("child targeted verification has no matching tool output")
    rendered = json.dumps(outputs.get(call_id), ensure_ascii=False)
    if "Ran 1 test" not in rendered or re.search(r"(?:^|\\n)OK(?:\\n|$)", rendered) is None:
        raise ValueError("child targeted verification does not contain Ran 1 test and OK")


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


def _split_simple_shell_command(command: str) -> list[str] | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    shell_names = {"bash", "sh", "zsh"}
    if tokens and Path(tokens[0]).name in shell_names:
        if len(tokens) != 3 or tokens[1] != "-lc":
            return None
        try:
            tokens = shlex.split(tokens[2])
        except ValueError:
            return None
        if (
            len(tokens) >= 2
            and Path(tokens[0]).name in shell_names
            and tokens[1] in {"-c", "-lc"}
        ):
            return None
    return tokens


def product_work_violations(commands: list[str]) -> list[str]:
    """Reject main-session commands that edit or verify the fixture product."""
    markers = ("target.py", TARGET_TEST.lower())
    violations: list[str] = []
    for command in commands:
        normalized = command.lower()
        if not any(marker in normalized for marker in markers):
            continue
        tokens = _split_simple_shell_command(command)
        if tokens is None:
            violations.append(command)
            continue
        if any(token in {"&&", "||", ";", "|"} for token in tokens):
            violations.append(command)
            continue
        controller_index = next(
            (
                index
                for index, token in enumerate(tokens)
                if token.endswith("controller_gate.py")
            ),
            None,
        )
        if (
            controller_index is None
            or controller_index + 1 >= len(tokens)
            or tokens[controller_index + 1] not in {"result", "close"}
        ):
            violations.append(command)
            continue
        if any(
            any(marker in token.lower() for marker in markers)
            and (index == 0 or tokens[index - 1] != "--evidence-ref")
            for index, token in enumerate(tokens)
        ):
            violations.append(command)
    return violations


def run(command: list[str], cwd: Path, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=environment, text=True, capture_output=True, check=False)


def failed(diagnostic: str) -> GateResult:
    return GateResult(1, f"isolated promotion gate failed: {diagnostic}")


def checked_result(result: GateResult, user_codex_home: Path, before: str) -> GateResult:
    """Make installation-surface immutability the final post-snapshot verdict."""
    if fingerprint(user_codex_home) != before:
        return failed(
            "user-level adaptive installation-surface fingerprint changed; "
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
        fixture.mkdir()
        write_fixture(fixture)
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
            "codex", "exec", "--ephemeral", "--json",
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
        completed_commands = read_completed_commands(output)
        violations = preflight_violations(completed_commands)
        if violations:
            return checked_result(
                failed(
                    "fresh main exceeded the Objective Lock during routing preflight: "
                    + repr(violations)
                ),
                user_codex_home,
                before,
            )
        product_violations = product_work_violations(completed_commands)
        if product_violations:
            return checked_result(
                failed(
                    "fresh main performed product edit or verification activity: "
                    + repr(product_violations)
                ),
                user_codex_home,
                before,
            )
        try:
            session_id = derive_parent_session_id(output)
            planned = validate_controller_lifecycle(candidate_home, fixture, session_id)
            validate_child_rollout(candidate_home, fixture, session_id, planned)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            return checked_result(
                failed(f"fresh controller/child evidence is invalid: {exc}"),
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
