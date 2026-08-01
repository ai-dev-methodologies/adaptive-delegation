from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.py"


class DispatcherGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.codex_home = self.root / ".codex"
        installed = subprocess.run(
            [sys.executable, str(INSTALLER), "--codex-home", str(self.codex_home)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.dispatcher = (
            self.codex_home / "scripts" / "adaptive_dispatch_attestation.py"
        )
        self.role = (
            self.codex_home / "agents" / "adaptive-luna-maker-xhigh.toml"
        )
        self.auth = self.codex_home / "auth.json"
        self.auth.write_text("{}", encoding="utf-8")
        self.auth.chmod(0o600)
        leaf_home = self.codex_home / "leaf-runtime"
        leaf_home.mkdir(mode=0o700)
        (leaf_home / "auth.json").symlink_to(self.auth)

        fake_bin = self.root / "bin"
        fake_bin.mkdir(mode=0o700)
        self.fake_log = self.root / "fake-ran"
        fake = fake_bin / "codex"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys, uuid\n"
            "from pathlib import Path\n"
            "session_id = str(uuid.uuid4())\n"
            "model = sys.argv[sys.argv.index('--model') + 1]\n"
            "effort_arg = next(v for v in sys.argv if v.startswith('model_reasoning_effort='))\n"
            "effort = json.loads(effort_arg.split('=', 1)[1])\n"
            "home = Path(os.environ['CODEX_HOME'])\n"
            "day = home / 'sessions' / '2026' / '07' / '31'\n"
            "day.mkdir(parents=True, mode=0o700, exist_ok=True)\n"
            "for path in (home, home / 'sessions', home / 'sessions' / '2026', home / 'sessions' / '2026' / '07', day): path.chmod(0o700)\n"
            "rollout = day / f'rollout-2026-07-31T12-00-00-{session_id}.jsonl'\n"
            "records = [\n"
            " {'timestamp':'2026-07-31T12:00:00Z','type':'session_meta','payload':{'id':session_id,'session_id':session_id}},\n"
            " {'timestamp':'2026-07-31T12:00:01Z','type':'turn_context','payload':{'model':model,'effort':effort}},\n"
            "]\n"
            "if os.environ.get('ADAPTIVE_FAKE_OVER_BUDGET') == '1':\n"
            " records.append({'timestamp':'2026-07-31T12:00:02Z','type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':{'input_tokens':12000,'output_tokens':1}}}})\n"
            "rollout.write_text(''.join(json.dumps(row) + '\\n' for row in records), encoding='utf-8')\n"
            "rollout.chmod(0o600)\n"
            "Path(os.environ['ADAPTIVE_FAKE_LOG']).write_text('ran', encoding='utf-8')\n"
            "print(f'session id: {session_id}', flush=True)\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "CODEX_HOME": str(self.codex_home),
                "PATH": str(fake_bin) + os.pathsep + self.environment.get("PATH", ""),
                "ADAPTIVE_FAKE_LOG": str(self.fake_log),
            }
        )

    def packet(self, dispatch_id: str, model: str, effort: str) -> dict:
        return {
            "dispatch_id": dispatch_id,
            "objective": "Run the portable dispatcher smoke worker.",
            "agent_type": "adaptive-luna-maker-xhigh",
            "model_tier": "spark-tier",
            "reasoning_effort": "xhigh",
            "write_scope": [str(self.root)],
            "resource_cap": {
                "processes": 1,
                "network": False,
                "max_tool_calls": 4,
                "max_output_tokens_per_call": 2000,
                "max_cumulative_tool_output_bytes": 32768,
                "max_child_stdout_bytes": 32768,
                "allow_repo_wide_search": False,
            },
            "evidence_path": str(self.role),
            "stop_condition": "The fake child exits once.",
            "token_budget": 8000,
            "network_access": False,
            "main_authority": {
                "model": model,
                "reasoning_effort": effort,
                "session_id": "portable-main",
            },
            "routing_audit": {
                "task_id": f"task-{dispatch_id}",
                "attempt_index": 1,
                "decision_timestamp": "2026-07-31T12:00:00Z",
                "effort_escalations": 0,
                "model_escalations": 0,
                "task_class": "bounded_complex_implementation_or_verification",
                "oracle_strength": "strong",
                "risk_class": "medium",
                "selection_basis": "policy_default",
                "workspace": str(self.root),
                "main_session_id": "portable-main",
                "surface_identity": "portable-smoke",
                "surface_schema_fingerprint": "e" * 64,
            },
        }

    def run_packet(self, packet: dict, *extra: str) -> tuple[subprocess.CompletedProcess[str], Path]:
        packet_path = self.root / f"{packet['dispatch_id']}.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        packet_path.chmod(0o600)
        model_ledger = self.root / f"{packet['dispatch_id']}-routing.jsonl"
        result = subprocess.run(
            [
                sys.executable,
                str(self.dispatcher),
                "--packet",
                str(packet_path),
                "--ledger",
                str(self.root / "dispatch.jsonl"),
                "--model-routing-ledger",
                str(model_ledger),
                "--model-routing-review-dir",
                str(self.root / "reviews"),
                "--direct-typed",
                *extra,
            ],
            text=True,
            capture_output=True,
            check=False,
            env=self.environment,
        )
        return result, model_ledger

    def test_below_floor_is_blocked_and_linked_without_child(self) -> None:
        result, ledger = self.run_packet(
            self.packet("portable-block", "gpt-5.6-terra", "high")
        )
        self.assertEqual(result.returncode, 25, result.stderr)
        self.assertIn("No child was launched", result.stderr)
        self.assertFalse(self.fake_log.exists())
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual([row["event_type"] for row in rows], ["pre_decision", "post_result"])
        self.assertEqual(rows[-1]["failure_class"], "policy_gate")

    def test_child_success_is_not_integration_acceptance(self) -> None:
        result, ledger = self.run_packet(
            self.packet("portable-success", "gpt-5.6-sol", "high")
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(self.fake_log.is_file())
        post = json.loads(ledger.read_text().splitlines()[-1])
        self.assertTrue(post["execution_completed"])
        self.assertFalse(post["integration_accepted"])
        self.assertFalse(post["accepted"])
        self.assertEqual(post["failure_class"], "none")

    def test_weighted_budget_exhaustion_is_classified_for_same_route_retry(self) -> None:
        packet = self.packet("portable-budget", "gpt-5.6-sol", "high")
        packet["token_budget"] = 3000
        self.environment["ADAPTIVE_FAKE_OVER_BUDGET"] = "1"

        result, ledger = self.run_packet(packet)

        self.assertEqual(result.returncode, 22, result.stderr + result.stdout)
        post = json.loads(ledger.read_text().splitlines()[-1])
        self.assertTrue(post["execution_completed"])
        self.assertFalse(post["integration_accepted"])
        self.assertEqual(post["failure_class"], "scope_or_retrieval_overbreadth")
        self.assertEqual(post["oracle_verdict"], "fail")
        self.assertEqual(
            post["post_result_detail"]["observable_result_signals"],
            ["budget_exhausted", "output_incomplete", "escalation_required"],
        )
        self.assertEqual(post["post_result_detail"]["next_action"], "retry_same_route")

    def test_fixed_luna_agent_type_is_native_without_model_override(self) -> None:
        module_name = "adaptive_dispatch_attestation_portable_test"
        spec = importlib.util.spec_from_file_location(module_name, self.dispatcher)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        self.addCleanup(sys.modules.pop, module_name, None)
        spec.loader.exec_module(module)

        binding = module.RoleBinding(
            agent_type="adaptive-luna-maker-xhigh",
            model_tier="spark-tier",
            model="gpt-5.6-luna",
            effort="xhigh",
            instructions="",
            role_config=self.role,
        )
        triple = {
            "agent_type": binding.agent_type,
            "model": binding.model,
            "reasoning_effort": binding.effort,
        }
        receipt_value = {
            "surface_identity": "codex-app.collaboration.spawn_agent",
            "original_callable_schema": {
                "agent_type": "installed-role-enum",
                "reasoning_effort": "string",
                "fork_turns": "none",
            },
            "selection_mode": "verified-fixed-agent-type",
            "desired_route": "native_v2",
            "explicit_route": "native_v2",
            "installed_binding": {**triple, "fork_turns": "none"},
            "explicit_arguments": {
                "agent_type": binding.agent_type,
                "reasoning_effort": binding.effort,
                "fork_turns": "none",
            },
            "allowlist": [triple],
            "gate_events": [
                {"name": "pending_receipt", "monotonic_ns": 1},
                {"name": "native_spawn_gate", "monotonic_ns": 2},
                {"name": "child_creation_eligibility", "monotonic_ns": 3},
            ],
        }
        receipt_path = self.root / "native-fixed-role-receipt.json"
        receipt_path.write_text(json.dumps(receipt_value), encoding="utf-8")
        receipt_path.chmod(0o600)

        admission = module._native_structural_admission(
            module.ReceiptEnvelope(receipt_value, receipt_path),
            binding,
            dispatch_id="portable-native-luna",
        )

        self.assertEqual(admission["status"], "structurally_eligible")
        self.assertEqual(admission["selection_mode"], "verified-fixed-agent-type")
        self.assertIsNone(admission["rejection_reason"])
        self.assertNotIn("model", receipt_value["original_callable_schema"])


if __name__ == "__main__":
    unittest.main()
