#!/usr/bin/env python3
"""Read a bounded, exact-match continuity slice without mutating state."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from collections import deque
from pathlib import Path
from typing import Any


MAX_FIELD_BYTES = 1_024
MAX_RECORD_BYTES = 4_096
MAX_LEDGER_BYTES = 16 * 1024 * 1024
MAX_RESULTS = 3
MAX_PUBLIC_OUTPUT_BYTES = MAX_RESULTS * (MAX_RECORD_BYTES + 1)
READ_BLOCK_BYTES = 8 * 1024
REQUIRED_RECORD_FIELDS = {
    "schema_version",
    "record_id",
    "recorded_at",
    "status",
    "workspace",
    "objective_key",
    "source_fingerprint",
    "implementation_envelope",
    "decisions",
    "changes",
    "routing",
    "verification",
    "evidence_paths",
    "side_effects",
    "carry_forward",
    "next_action",
    "stop_condition",
    "supersedes",
}


def _runtime_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _field(value: str) -> str:
    if not value or "\x00" in value or len(value.encode("utf-8")) > MAX_FIELD_BYTES:
        raise ValueError("workspace and objective-key must be non-empty, UTF-8 values within the size limit")
    return value


def _open_ledger():
    """Open the ledger once through no-follow directory descriptors."""
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    directory_fds: list[int] = []
    file_fd: int | None = None
    try:
        current_fd = os.open(_runtime_home().absolute(), directory_flags)
        directory_fds.append(current_fd)
        for component in ("state", "adaptive-delegation"):
            current_fd = os.open(component, directory_flags, dir_fd=current_fd)
            directory_fds.append(current_fd)
        file_fd = os.open("continuity.jsonl", file_flags, dir_fd=current_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("continuity ledger must be a regular non-symlink file")
        if metadata.st_size > MAX_LEDGER_BYTES:
            raise ValueError("continuity ledger exceeds the safe read limit")
        handle = os.fdopen(file_fd, "rb", closefd=True)
        file_fd = None
        return handle, metadata.st_size
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("continuity ledger could not be opened safely") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for descriptor in reversed(directory_fds):
            os.close(descriptor)


def _record(value: Any, workspace: str, objective_key: str) -> bool:
    if not isinstance(value, dict) or not REQUIRED_RECORD_FIELDS.issubset(value):
        raise ValueError("continuity record is missing required fields")
    return (
        value.get("status") == "accepted"
        and value.get("workspace") == workspace
        and value.get("objective_key") == objective_key
    )


def _reverse_lines(handle: Any, size: int):
    """Yield newline-terminated records newest-first with bounded buffering."""
    if size == 0:
        return
    handle.seek(size - 1)
    if handle.read(1) != b"\n":
        raise ValueError("continuity ledger contains an unterminated record")

    position = size
    pending = b""
    skipped_terminal_separator = False
    while position:
        chunk_size = min(READ_BLOCK_BYTES, position)
        position -= chunk_size
        handle.seek(position)
        pending = handle.read(chunk_size) + pending
        parts = pending.split(b"\n")
        if position:
            pending = parts.pop(0)
            if len(pending) > MAX_RECORD_BYTES:
                raise ValueError("continuity record exceeds the safe size limit")
        else:
            pending = b""

        for raw in reversed(parts):
            if not skipped_terminal_separator and raw == b"":
                skipped_terminal_separator = True
                continue
            if len(raw) + 1 > MAX_RECORD_BYTES:
                raise ValueError("continuity record exceeds the safe size limit")
            yield raw + b"\n"


def read_records(workspace: str, objective_key: str) -> list[dict[str, Any]]:
    """Return the newest bounded exact matches from the resolved-home ledger."""
    workspace, objective_key = _field(workspace), _field(objective_key)
    opened = _open_ledger()
    if opened is None:
        return []
    handle, ledger_size = opened
    matches: deque[dict[str, Any]] = deque()
    try:
        with handle:
            for tail_index, raw in enumerate(
                _reverse_lines(handle, ledger_size), start=1
            ):
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        f"continuity record {tail_index} from the tail is malformed"
                    ) from exc
                try:
                    matched = _record(value, workspace, objective_key)
                except ValueError as exc:
                    raise ValueError(
                        f"continuity record {tail_index} from the tail is malformed"
                    ) from exc
                if matched:
                    matches.appendleft(value)
                    if len(matches) == MAX_RESULTS:
                        break
    except OSError as exc:
        raise ValueError("continuity ledger could not be read safely") from exc
    return list(matches)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--objective-key", required=True)
    args = parser.parse_args()
    try:
        records = read_records(args.workspace, args.objective_key)
        output = b"".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            for record in records
        )
        if len(output) > MAX_PUBLIC_OUTPUT_BYTES:
            raise ValueError("continuity output exceeds the public size limit")
    except ValueError as exc:
        print(f"continuity read rejected: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
