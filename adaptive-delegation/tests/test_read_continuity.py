from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
READER = ROOT / "adaptive-delegation" / "scripts" / "read_continuity.py"


class ReadContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "isolated-codex"
        self.ledger = self.home / "state" / "adaptive-delegation" / "continuity.jsonl"
        self.ledger.parent.mkdir(parents=True)

    def run_reader(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update({"CODEX_HOME": str(self.home), "HOME": str(Path(self.temporary.name) / "other-home")})
        return subprocess.run(
            [sys.executable, str(READER), *arguments],
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )

    def write_records(self, records: list[dict]) -> None:
        self.ledger.write_text(
            "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
            encoding="utf-8",
        )

    @staticmethod
    def record(record_id: str, *, workspace: str = "/workspace", objective_key: str = "target", status: str = "accepted") -> dict:
        return {
            "schema_version": 1,
            "record_id": record_id,
            "recorded_at": "2026-08-02T00:00:00Z",
            "status": status,
            "workspace": workspace,
            "objective_key": objective_key,
            "source_fingerprint": "fingerprint",
            "implementation_envelope": {},
            "decisions": [],
            "changes": [],
            "routing": {},
            "verification": {},
            "evidence_paths": [],
            "side_effects": [],
            "carry_forward": {},
            "next_action": "stop",
            "stop_condition": "accepted",
            "supersedes": None,
        }

    def test_returns_only_latest_three_exact_accepted_matches_from_codex_home(self) -> None:
        default_ledger = (
            Path(self.temporary.name)
            / "other-home"
            / ".codex"
            / "state"
            / "adaptive-delegation"
            / "continuity.jsonl"
        )
        default_ledger.parent.mkdir(parents=True)
        default_ledger.write_text("global-home-canary\n", encoding="utf-8")
        records = [self.record(str(index)) for index in range(5)] + [
            self.record("other", objective_key="other"),
            self.record("rejected", status="rejected"),
        ]
        self.write_records(records)

        result = self.run_reader("--workspace", "/workspace", "--objective-key", "target")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row["record_id"] for row in map(json.loads, result.stdout.splitlines())], ["2", "3", "4"])
        self.assertLessEqual(len(result.stdout.encode("utf-8")), 3 * 4097)
        self.assertNotIn("global-home-canary", result.stdout + result.stderr)

    def test_stops_after_three_tail_matches_without_reading_older_noise(self) -> None:
        self.ledger.write_text(
            "malformed older record\n"
            + "".join(
                json.dumps(self.record(str(index)), separators=(",", ":")) + "\n"
                for index in range(3)
            ),
            encoding="utf-8",
        )

        result = self.run_reader(
            "--workspace", "/workspace", "--objective-key", "target"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [row["record_id"] for row in map(json.loads, result.stdout.splitlines())],
            ["0", "1", "2"],
        )

    def test_missing_ledger_returns_no_records_without_creating_state(self) -> None:
        result = self.run_reader(
            "--workspace", "/workspace", "--objective-key", "target"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.ledger.exists())

    def test_rejects_malformed_or_oversized_ledger_input_without_output(self) -> None:
        self.ledger.write_bytes(b'{"status":"accepted"}\n' + b"x" * 4097 + b"\n")

        result = self.run_reader("--workspace", "/workspace", "--objective-key", "target")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("rejected", result.stderr)

    def test_rejects_a_ledger_that_escapes_the_resolved_runtime_home(self) -> None:
        outside = Path(self.temporary.name) / "outside.jsonl"
        outside.write_text("", encoding="utf-8")
        self.ledger.symlink_to(outside)

        result = self.run_reader("--workspace", "/workspace", "--objective-key", "target")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("rejected", result.stderr)

    def test_rejects_a_symlinked_ledger_directory(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        self.ledger.parent.rmdir()
        self.ledger.parent.symlink_to(outside, target_is_directory=True)

        result = self.run_reader(
            "--workspace", "/workspace", "--objective-key", "target"
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("rejected", result.stderr)


if __name__ == "__main__":
    unittest.main()
