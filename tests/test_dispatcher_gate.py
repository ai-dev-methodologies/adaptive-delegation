from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock
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
        self.leaf_home = self.codex_home / "leaf-runtime"
        self.leaf_home.mkdir(mode=0o700)
        (self.leaf_home / "auth.json").symlink_to(self.auth)

        fake_bin = self.root / "bin"
        fake_bin.mkdir(mode=0o700)
        self.fake_log = self.leaf_home / "fake-ran"
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
            "forbidden = ('CODEX_REMOTE_PAYLOAD', 'CODEX_THREAD_ID', 'CODEX_CONFIG', 'PYTHONPATH', '"
            + "OM"
            + "X_TEAM_MARKER')\n"
            "if any(key in os.environ for key in forbidden):\n"
            " raise SystemExit(91)\n"
            "day = home / 'sessions' / '2026' / '07' / '31'\n"
            "day.mkdir(parents=True, mode=0o700, exist_ok=True)\n"
            "for path in (home, home / 'sessions', home / 'sessions' / '2026', home / 'sessions' / '2026' / '07', day): path.chmod(0o700)\n"
            "rollout = day / f'rollout-2026-07-31T12-00-00-{session_id}.jsonl'\n"
            "records = [\n"
            " {'timestamp':'2026-07-31T12:00:00Z','type':'session_meta','payload':{'id':session_id,'session_id':session_id}},\n"
            " {'timestamp':'2026-07-31T12:00:01Z','type':'turn_context','payload':{'model':model,'effort':effort}},\n"
            "]\n"
            "if (home / 'fake-over-budget').exists():\n"
            " records.append({'timestamp':'2026-07-31T12:00:02Z','type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':{'input_tokens':12000,'output_tokens':1}}}})\n"
            "rollout.write_text(''.join(json.dumps(row) + '\\n' for row in records), encoding='utf-8')\n"
            "rollout.chmod(0o600)\n"
            "(home / 'fake-ran').write_text('isolated', encoding='utf-8')\n"
            "print(f'session id: {session_id}', flush=True)\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)
        self.fake_codex = fake
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "CODEX_HOME": str(self.codex_home),
                "PATH": str(fake_bin) + os.pathsep + self.environment.get("PATH", ""),
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
            "acceptance_evidence": [
                "The typed child exits successfully.",
                "The trusted rollout matches the declared model and effort.",
            ],
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

    def load_dispatcher_module(self):
        module_name = "adaptive_dispatch_attestation_portable_test"
        spec = importlib.util.spec_from_file_location(module_name, self.dispatcher)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        previous_codex_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(self.codex_home)
        try:
            sys.modules[module_name] = module
            self.addCleanup(sys.modules.pop, module_name, None)
            spec.loader.exec_module(module)
        finally:
            if previous_codex_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_codex_home
        return module

    def write_trusted_rollout(
        self, home: Path, session_id: str, model: str, effort: str
    ) -> Path:
        day = home / "sessions" / "2026" / "07" / "31"
        day.mkdir(parents=True, mode=0o700, exist_ok=True)
        for path in (
            home,
            home / "sessions",
            home / "sessions" / "2026",
            home / "sessions" / "2026" / "07",
            day,
        ):
            path.chmod(0o700)
        rollout = day / f"rollout-2026-07-31T12-00-00-{session_id}.jsonl"
        records = [
            {
                "timestamp": "2026-07-31T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": session_id, "session_id": session_id},
            },
            {
                "timestamp": "2026-07-31T12:00:01Z",
                "type": "turn_context",
                "payload": {"model": model, "effort": effort},
            },
        ]
        rollout.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )
        rollout.chmod(0o600)
        return rollout

    def append_receipt_marker(self, module, rollout: Path, receipt: dict) -> None:
        marker = {
            "timestamp": "2026-07-31T12:00:02Z",
            "type": module.RECEIPT_MARKER_TYPE,
            "payload": {
                "receipt_kind": receipt["receipt_kind"],
                "receipt_version": receipt["receipt_version"],
                "payload_digest": module._canonical_digest(receipt),
            },
        }
        with rollout.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(marker, sort_keys=True) + "\n")
        rollout.chmod(0o600)

    def terminal_fixture(
        self, module, dispatch_id: str = "integration-terminal", write_scope=None
    ):
        packet = self.packet(dispatch_id, "gpt-5.6-sol", "high")
        packet["write_scope"] = ["read-only"] if write_scope is None else write_scope
        binding = module._role_binding(packet)
        self.assertIsNotNone(binding)
        session_id = str(uuid.uuid4())
        rollout = self.write_trusted_rollout(
            self.codex_home, session_id, binding.model, binding.effort
        )
        runtime = module._trusted_rollout(rollout, session_id)
        self.assertIsNotNone(runtime)
        terminal = module._capture_terminal_event(
            packet=packet,
            binding=binding,
            runtime=runtime,
            rollout=rollout,
            rollout_runtime_home="main",
            selected_launch_path="protected",
            child_returncode=0,
            output_digest=hashlib.sha256(b"completed-child-output").hexdigest(),
            parent_enforced=False,
        )
        self.assertIsNotNone(terminal)
        return packet, binding, runtime, rollout, terminal

    def receipt_fixture(self, module, packet: dict, binding, terminal):
        checker = module._installed_integration_checker_binding()
        self.assertIsNotNone(checker)
        checker_session_id = str(uuid.uuid4())
        checker_rollout = self.write_trusted_rollout(
            self.codex_home,
            checker_session_id,
            checker.model,
            checker.effort,
        )
        artifact = self.root / f"{packet['dispatch_id']}-evidence.json"
        artifact.write_text("verified terminal evidence\n", encoding="utf-8")
        artifact.chmod(0o600)
        evidence_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        checks = [
            {
                "name": "targeted-dispatcher-test",
                "passed": True,
                "evidence_digest": evidence_digest,
            }
        ]
        terminal_value = terminal.value
        receipt = {
            "receipt_kind": "integration",
            "receipt_version": module.RECEIPT_VERSION,
            "dispatch_id": packet["dispatch_id"],
            "packet_digest": module._canonical_digest(packet),
            "rollout_session_id": terminal_value["child"]["session_id"],
            "child_session_id": terminal_value["child"]["session_id"],
            "child_role": terminal_value["actual"],
            "terminal_digest": terminal.digest,
            "terminal": terminal_value,
            "terminal_nonce": terminal_value["terminal_nonce"],
            "terminal_result": terminal_value["terminal_result"],
            "rollout_digest": terminal_value["rollout"]["sha256"],
            "output_digest": terminal_value["output_digest"],
            "worktree_digest": terminal_value["worktree_digest"],
            "desired": terminal_value["actual"],
            "explicit": terminal_value["actual"],
            "effective": terminal_value["actual"],
            "launch_bound_role": {
                "agent_type": binding.agent_type,
                "role_config": str(binding.role_config),
            },
            "launch_bound_role_config_digest": module._role_config_digest(binding),
            "selected_launch_path": terminal_value["selected_launch_path"],
            "issuer": {
                "role": module._binding_triple(checker),
                "role_config": str(checker.role_config),
                "role_config_digest": module._role_config_digest(checker),
                "rollout_session_id": checker_session_id,
                "rollout_path": str(checker_rollout),
            },
            "finished_success": True,
            "checker_pass": True,
            "evidence_digest": evidence_digest,
            "verification_checks": checks,
            "verification_checks_digest": module._canonical_digest(checks),
            "evidence_artifact": {
                "path": str(artifact),
                "sha256": evidence_digest,
                "terminal_digest": terminal.digest,
                "verification_checks_digest": module._canonical_digest(checks),
                "output_digest": terminal_value["output_digest"],
                "worktree_digest": terminal_value["worktree_digest"],
            },
            "token_observation": {
                "semantics": (
                    "trusted_parent_monitoring"
                    if terminal_value["parent_enforced"]
                    else "unavailable"
                ),
                "parent_enforced": terminal_value["parent_enforced"],
                "quantitative_caps_enforced": terminal_value["parent_enforced"],
            },
        }
        receipt_path = self.root / f"{packet['dispatch_id']}-integration.json"
        self.replace_receipt(module, receipt_path, checker_rollout, receipt)
        return receipt, receipt_path, checker_rollout, artifact

    def replace_receipt(
        self, module, receipt_path: Path, checker_rollout: Path, receipt: dict
    ) -> None:
        receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
        receipt_path.chmod(0o600)
        self.append_receipt_marker(module, checker_rollout, receipt)

    def gate_for(self, module, packet, binding, runtime, terminal, receipt_path):
        receipt = module._load_receipt(receipt_path)
        return module._integration_gate(
            receipt,
            packet=packet,
            binding=binding,
            runtime=runtime,
            expected_session_id=runtime.session_id,
            selected_launch_path="protected",
            parent_enforced=False,
            terminal_event=terminal,
            dispatch_id=packet["dispatch_id"],
        )

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

    def test_child_success_remains_pending_until_integration_finalization(self) -> None:
        result, ledger = self.run_packet(
            self.packet("portable-success", "gpt-5.6-sol", "high")
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(self.fake_log.is_file())
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual([row["event_type"] for row in rows], ["pre_decision"])
        self.assertEqual(self.fake_log.read_text(encoding="utf-8"), "isolated")

    def test_execute_finalize_and_issue_report_records_acceptance(self) -> None:
        packet = self.packet("finalized-success", "gpt-5.6-sol", "high")
        packet["write_scope"] = ["read-only"]
        result, model_ledger = self.run_packet(packet)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(
            [json.loads(line)["event_type"] for line in model_ledger.read_text().splitlines()],
            ["pre_decision"],
        )

        module = self.load_dispatcher_module()
        dispatch_ledger = self.root / "dispatch.jsonl"
        terminal = module._load_terminal_event(dispatch_ledger, packet)
        self.assertIsNotNone(terminal)
        binding = module._role_binding(packet)
        self.assertIsNotNone(binding)
        _receipt, receipt_path, _checker_rollout, _artifact = self.receipt_fixture(
            module, packet, binding, terminal
        )
        packet_path = self.root / "finalized-success.json"
        finalize_argv = [
            sys.executable,
            str(self.dispatcher),
            "--packet",
            str(packet_path),
            "--ledger",
            str(dispatch_ledger),
            "--model-routing-ledger",
            str(model_ledger),
            "--model-routing-review-dir",
            str(self.root / "reviews"),
            "--finalize-integration",
            "--integration-receipt",
            str(receipt_path),
        ]
        contenders = [
            subprocess.Popen(
                finalize_argv,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.environment,
            )
            for _ in range(8)
        ]
        outcomes = []
        for contender in contenders:
            stdout, stderr = contender.communicate(timeout=10)
            outcomes.append((contender.returncode, stdout, stderr))
        returncodes = [outcome[0] for outcome in outcomes]
        self.assertEqual(returncodes.count(0), 1, outcomes)
        self.assertEqual(
            returncodes.count(module.EXIT_MODEL_ROUTING_AUDIT_FAILURE),
            7,
            outcomes,
        )
        rows = [json.loads(line) for line in model_ledger.read_text().splitlines()]
        self.assertEqual(
            [row["event_type"] for row in rows],
            ["pre_decision", "post_result"],
        )
        self.assertTrue(rows[-1]["accepted"])
        self.assertTrue(rows[-1]["integration_accepted"])
        self.assertEqual(rows[-1]["failure_class"], "none")
        accepted_dispatch_rows = [
            json.loads(line)
            for line in dispatch_ledger.read_text().splitlines()
            if json.loads(line).get("verdict") == "integration_accepted"
        ]
        self.assertEqual(len(accepted_dispatch_rows), 1)

        audit_script = (
            self.codex_home
            / "skills"
            / "adaptive-delegation"
            / "scripts"
            / "model_routing_audit.py"
        )
        report = subprocess.run(
            [
                sys.executable,
                str(audit_script),
                "issue-report",
                "--ledger",
                str(model_ledger),
            ],
            text=True,
            capture_output=True,
            check=False,
            env=self.environment,
        )
        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertIn("- Result: `accepted`", report.stdout)
        self.assertIn("- Integration accepted: `yes`", report.stdout)

        dispatch_rows_before_replay = dispatch_ledger.read_text().splitlines()
        replay = subprocess.run(
            finalize_argv,
            text=True,
            capture_output=True,
            check=False,
            env=self.environment,
        )
        self.assertEqual(replay.returncode, module.EXIT_MODEL_ROUTING_AUDIT_FAILURE)
        self.assertIn("exact unpaired pre_decision", replay.stderr)
        self.assertEqual(
            dispatch_ledger.read_text().splitlines(), dispatch_rows_before_replay
        )
        self.assertEqual(
            [json.loads(line)["event_type"] for line in model_ledger.read_text().splitlines()],
            ["pre_decision", "post_result"],
        )

    def test_weighted_budget_exhaustion_is_classified_for_same_route_retry(self) -> None:
        packet = self.packet("portable-budget", "gpt-5.6-sol", "high")
        packet["token_budget"] = 3000
        (self.leaf_home / "fake-over-budget").write_text("1", encoding="utf-8")

        result, ledger = self.run_packet(packet)

        self.assertEqual(result.returncode, 22, result.stderr + result.stdout)
        post = json.loads(ledger.read_text().splitlines()[-1])
        self.assertTrue(post["execution_completed"])
        self.assertFalse(post["integration_accepted"])
        self.assertEqual(post["failure_class"], "context_ceiling")
        self.assertEqual(post["oracle_verdict"], "fail")
        self.assertEqual(
            post["post_result_detail"]["observable_result_signals"],
            ["budget_exhausted", "output_incomplete"],
        )
        self.assertEqual(post["post_result_detail"]["next_action"], "raise_effort")

    def test_child_environment_drops_parent_codex_and_team_state(self) -> None:
        self.environment.update(
            {
                "CODEX_REMOTE_PAYLOAD": "untrusted-payload",
                "CODEX_THREAD_ID": "parent-thread",
                "CODEX_CONFIG": "parent-config",
                "PYTHONPATH": "parent-pythonpath",
                ("OM" + "X_TEAM_MARKER"): "parent-team",
            }
        )

        result, _ledger = self.run_packet(
            self.packet("portable-isolated-environment", "gpt-5.6-sol", "high")
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.fake_log.read_text(encoding="utf-8"), "isolated")

    def test_protected_child_environment_is_an_allowlist(self) -> None:
        module = self.load_dispatcher_module()
        forbidden = {
            "CODEX_REMOTE_PAYLOAD": "untrusted-payload",
            "CODEX_THREAD_ID": "parent-thread",
            "CODEX_CONFIG": "parent-config",
            "PYTHONPATH": "parent-pythonpath",
            ("OM" + "X_TEAM_MARKER"): "parent-team",
        }
        with mock.patch.dict(os.environ, forbidden, clear=False):
            environment = module._isolated_child_environment(self.codex_home)

        self.assertEqual(environment["CODEX_HOME"], str(self.codex_home))
        self.assertEqual(environment["HOME"], str(self.codex_home))
        self.assertTrue(set(environment).issubset({"CODEX_HOME", "HOME", *module.CHILD_ENV_ALLOWLIST}))
        self.assertTrue(set(forbidden).isdisjoint(environment))

    def test_typed_objective_binds_scope_and_stop_rules(self) -> None:
        module = self.load_dispatcher_module()
        packet = self.packet("typed-objective-lock", "gpt-5.6-sol", "high")

        objective = module._typed_objective(packet)

        self.assertTrue(objective.startswith(packet["objective"]))
        self.assertIn("OBJECTIVE_LOCK (binding):", objective)
        self.assertIn(
            "Model or reasoning escalation changes capability, not authority or scope.",
            objective,
        )
        self.assertIn("Stop as soon as the required acceptance evidence passes", objective)
        self.assertIn("A broader objective requires a new explicitly authorized packet.", objective)
        contract_text = objective.split(
            "ADAPTIVE_DISPATCH_CONTRACT (binding):\n", 1
        )[1]
        contract = json.loads(contract_text)
        self.assertEqual(contract["write_scope"], packet["write_scope"])
        self.assertEqual(
            contract["acceptance_evidence"], packet["acceptance_evidence"]
        )
        self.assertEqual(contract["stop_condition"], packet["stop_condition"])

    def test_packet_requires_typed_acceptance_evidence(self) -> None:
        module = self.load_dispatcher_module()
        packet = self.packet("acceptance-evidence-contract", "gpt-5.6-sol", "high")

        packet.pop("acceptance_evidence")
        self.assertEqual(
            module._validate_packet(packet, self.role),
            "packet_field_missing_or_empty:acceptance_evidence",
        )

        packet["acceptance_evidence"] = ["   "]
        self.assertEqual(
            module._validate_packet(packet, self.role),
            "acceptance_evidence_invalid",
        )

    def test_protected_resume_requires_isolated_canonical_argv(self) -> None:
        module = self.load_dispatcher_module()
        packet = self.packet("protected-isolated-resume", "gpt-5.6-sol", "high")
        binding = module._role_binding(packet)
        self.assertIsNotNone(binding)
        session_id = str(uuid.uuid4())
        expected_tail = [
            "exec",
            "--ignore-user-config",
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "--disable",
            "multi_agent",
            "resume",
            "--model",
            binding.model,
            "--config",
            "model_reasoning_effort=" + json.dumps(binding.effort),
            "--config",
            "developer_instructions=" + json.dumps(binding.instructions),
            "--",
            session_id,
            packet["objective"],
        ]
        with mock.patch.dict(
            os.environ,
            {"PATH": str(self.fake_codex.parent) + os.pathsep + os.environ.get("PATH", "")},
            clear=False,
        ):
            canonical = module._canonical_resume_binding(
                [str(self.fake_codex), *expected_tail],
                binding,
                session_id,
                packet["objective"],
            )

        self.assertEqual(canonical, [str(self.fake_codex.resolve()), *expected_tail])

    def test_worktree_mutation_after_terminal_event_blocks_finalization(self) -> None:
        module = self.load_dispatcher_module()
        scope = self.root / "terminal-worktree"
        scope.mkdir(mode=0o700)
        tracked = scope / "tracked.txt"
        tracked.write_text("before\n", encoding="utf-8")
        packet, binding, runtime, _rollout, terminal = self.terminal_fixture(
            module,
            "mutable-worktree",
            [str(scope)],
        )
        _receipt, receipt_path, _checker_rollout, _artifact = self.receipt_fixture(
            module, packet, binding, terminal
        )
        tracked.write_text("after\n", encoding="utf-8")

        gate = self.gate_for(module, packet, binding, runtime, terminal, receipt_path)

        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["reason"], "terminal_worktree_stale_or_mutable")

    def test_precreated_receipt_cannot_authorize_without_terminal_event(self) -> None:
        module = self.load_dispatcher_module()
        packet, binding, runtime, _rollout, terminal = self.terminal_fixture(module)
        _receipt, receipt_path, _checker_rollout, _artifact = self.receipt_fixture(
            module, packet, binding, terminal
        )

        gate = module._integration_gate(
            module._load_receipt(receipt_path),
            packet=packet,
            binding=binding,
            runtime=runtime,
            expected_session_id=runtime.session_id,
            selected_launch_path="protected",
            parent_enforced=False,
            terminal_event=None,
            dispatch_id=packet["dispatch_id"],
        )

        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["reason"], "terminal_event_missing")

    def test_receipt_requires_exact_terminal_checker_and_artifact_bindings(self) -> None:
        module = self.load_dispatcher_module()
        packet, binding, runtime, rollout, terminal = self.terminal_fixture(module)
        receipt, receipt_path, checker_rollout, artifact = self.receipt_fixture(
            module, packet, binding, terminal
        )

        self.assertEqual(
            self.gate_for(module, packet, binding, runtime, terminal, receipt_path)[
                "status"
            ],
            "passed",
        )

        stale_terminal = module._capture_terminal_event(
            packet=packet,
            binding=binding,
            runtime=runtime,
            rollout=rollout,
            rollout_runtime_home="main",
            selected_launch_path="protected",
            child_returncode=0,
            output_digest=terminal.value["output_digest"],
            parent_enforced=False,
        )
        self.assertIsNotNone(stale_terminal)
        stale_gate = self.gate_for(
            module, packet, binding, runtime, stale_terminal, receipt_path
        )
        self.assertEqual(stale_gate["status"], "blocked")
        self.assertEqual(stale_gate["reason"], "terminal_receipt_binding_mismatch")

        mutations = {
            "packet": lambda value: value.__setitem__("packet_digest", "0" * 64),
            "child session": lambda value: value.__setitem__(
                "child_session_id", str(uuid.uuid4())
            ),
            "child role": lambda value: value.__setitem__(
                "child_role",
                {
                    "agent_type": "adaptive-terra-checker-high",
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "high",
                },
            ),
            "output": lambda value: value.__setitem__("output_digest", "0" * 64),
            "worktree": lambda value: value.__setitem__("worktree_digest", "0" * 64),
            "checker role": lambda value: value["issuer"].__setitem__(
                "role",
                {
                    "agent_type": "unapproved-checker",
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "high",
                },
            ),
            "checker session": lambda value: value["issuer"].__setitem__(
                "rollout_session_id", terminal.value["child"]["session_id"]
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(receipt))
                mutate(candidate)
                self.replace_receipt(module, receipt_path, checker_rollout, candidate)
                self.assertEqual(
                    self.gate_for(
                        module, packet, binding, runtime, terminal, receipt_path
                    )["status"],
                    "blocked",
                )

        self.replace_receipt(module, receipt_path, checker_rollout, receipt)
        artifact.write_text("mutated evidence\n", encoding="utf-8")
        artifact.chmod(0o600)
        artifact_gate = self.gate_for(
            module, packet, binding, runtime, terminal, receipt_path
        )
        self.assertEqual(artifact_gate["status"], "blocked")
        self.assertEqual(artifact_gate["reason"], "evidence_artifact_invalid")

    def test_mutable_receipt_after_checker_marker_is_rejected(self) -> None:
        module = self.load_dispatcher_module()
        packet, binding, runtime, _rollout, terminal = self.terminal_fixture(module)
        receipt, receipt_path, _checker_rollout, _artifact = self.receipt_fixture(
            module, packet, binding, terminal
        )
        receipt["unbound_mutation"] = True
        receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
        receipt_path.chmod(0o600)

        gate = self.gate_for(module, packet, binding, runtime, terminal, receipt_path)

        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["reason"], "trusted_integration_checker_marker_missing")

    def test_finalization_reads_receipt_only_after_terminal_event(self) -> None:
        module = self.load_dispatcher_module()
        packet, binding, _runtime, _rollout, terminal = self.terminal_fixture(module)
        _receipt, receipt_path, _checker_rollout, _artifact = self.receipt_fixture(
            module, packet, binding, terminal
        )
        missing_ledger = self.root / "no-terminal-ledger.jsonl"

        with mock.patch.object(module, "_load_receipt") as load_receipt:
            result = module._finalize_integration(
                packet=packet,
                ledger=missing_ledger,
                receipt_path=receipt_path,
            )

        self.assertEqual(result, module.EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE)
        load_receipt.assert_not_called()

    def test_pre_gate_finalization_failure_keeps_attempt_pending_for_retry(self) -> None:
        packet = self.packet("finalize-precondition-retry", "gpt-5.6-sol", "high")
        packet["write_scope"] = ["read-only"]
        result, model_ledger = self.run_packet(packet)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        module = self.load_dispatcher_module()
        dispatch_ledger = self.root / "dispatch.jsonl"
        terminal = module._load_terminal_event(dispatch_ledger, packet)
        self.assertIsNotNone(terminal)
        binding = module._role_binding(packet)
        self.assertIsNotNone(binding)
        _receipt, receipt_path, _checker_rollout, _artifact = self.receipt_fixture(
            module, packet, binding, terminal
        )
        packet_path = self.root / "finalize-precondition-retry.json"
        command = [
            sys.executable,
            str(self.dispatcher),
            "--packet",
            str(packet_path),
            "--model-routing-ledger",
            str(model_ledger),
            "--model-routing-review-dir",
            str(self.root / "reviews"),
            "--finalize-integration",
            "--integration-receipt",
            str(receipt_path),
        ]

        missing_terminal = subprocess.run(
            [*command, "--ledger", str(self.root / "missing-terminal.jsonl")],
            text=True,
            capture_output=True,
            check=False,
            env=self.environment,
        )
        self.assertEqual(
            missing_terminal.returncode,
            module.EXIT_NATIVE_UNAVAILABLE_FALLBACK_FAILURE,
            missing_terminal.stderr,
        )
        self.assertEqual(
            [json.loads(line)["event_type"] for line in model_ledger.read_text().splitlines()],
            ["pre_decision"],
        )

        corrected = subprocess.run(
            [*command, "--ledger", str(dispatch_ledger)],
            text=True,
            capture_output=True,
            check=False,
            env=self.environment,
        )
        self.assertEqual(corrected.returncode, 0, corrected.stderr)
        self.assertEqual(
            [json.loads(line)["event_type"] for line in model_ledger.read_text().splitlines()],
            ["pre_decision", "post_result"],
        )

    def test_finalize_argument_conflict_keeps_attempt_pending_for_retry(self) -> None:
        packet = self.packet("finalize-argument-retry", "gpt-5.6-sol", "high")
        packet["write_scope"] = ["read-only"]
        result, model_ledger = self.run_packet(packet)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        module = self.load_dispatcher_module()
        dispatch_ledger = self.root / "dispatch.jsonl"
        terminal = module._load_terminal_event(dispatch_ledger, packet)
        self.assertIsNotNone(terminal)
        binding = module._role_binding(packet)
        self.assertIsNotNone(binding)
        _receipt, receipt_path, _checker_rollout, _artifact = self.receipt_fixture(
            module, packet, binding, terminal
        )
        packet_path = self.root / "finalize-argument-retry.json"
        command = [
            sys.executable,
            str(self.dispatcher),
            "--packet",
            str(packet_path),
            "--ledger",
            str(dispatch_ledger),
            "--model-routing-ledger",
            str(model_ledger),
            "--model-routing-review-dir",
            str(self.root / "reviews"),
            "--finalize-integration",
            "--integration-receipt",
            str(receipt_path),
        ]

        conflicted = subprocess.run(
            [*command, "--session-id", str(uuid.uuid4())],
            text=True,
            capture_output=True,
            check=False,
            env=self.environment,
        )
        self.assertEqual(conflicted.returncode, module.EXIT_UNSAFE_LAUNCH_PATH)
        self.assertIn("unsafe finalization path", conflicted.stderr)
        self.assertEqual(
            [json.loads(line)["event_type"] for line in model_ledger.read_text().splitlines()],
            ["pre_decision"],
        )

        corrected = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            env=self.environment,
        )
        self.assertEqual(corrected.returncode, 0, corrected.stderr)
        self.assertEqual(
            [json.loads(line)["event_type"] for line in model_ledger.read_text().splitlines()],
            ["pre_decision", "post_result"],
        )

    def test_finalization_accepts_only_persisted_exact_receipt(self) -> None:
        module = self.load_dispatcher_module()
        packet, binding, runtime, rollout, terminal = self.terminal_fixture(
            module, "integration-finalize"
        )
        _receipt, receipt_path, _checker_rollout, _artifact = self.receipt_fixture(
            module, packet, binding, terminal
        )
        ledger = self.root / "finalization-ledger.jsonl"
        module._append_attestation(
            ledger,
            packet=packet,
            binding=binding,
            expected_session_id=runtime.session_id,
            runtime=runtime,
            source={"kind": "codex_rollout", "path": str(rollout), "status": "trusted"},
            verdict="protected_completed",
            reason="protected_resume_completed",
            selected_launch_path="protected",
            terminal_event=terminal,
        )

        result = module._finalize_integration(
            packet=packet,
            ledger=ledger,
            receipt_path=receipt_path,
        )

        self.assertEqual(result, 0)
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[-1]["verdict"], "integration_accepted")
        self.assertEqual(records[-1]["integration_gate"]["status"], "passed")

    def test_main_reads_packet_once_before_audit_and_dispatch(self) -> None:
        module = self.load_dispatcher_module()
        packet = self.packet("single-packet-read", "gpt-5.6-sol", "high")
        packet_path = self.root / "single-packet-read.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        packet_path.chmod(0o600)
        with (
            mock.patch.object(module, "_load_json", return_value=packet) as load_json,
            mock.patch.object(module, "_start_adaptive_audit", return_value=(None, None)),
            mock.patch.object(module, "_dispatch_main", return_value=0) as dispatch,
        ):
            result = module.main(["--packet", str(packet_path)])

        self.assertEqual(result, 0)
        self.assertEqual(load_json.call_count, 1)
        self.assertIs(dispatch.call_args.kwargs["packet"], packet)
        self.assertTrue(dispatch.call_args.kwargs["packet_loaded"])

    def test_adaptive_audit_uses_explicit_escalated_route(self) -> None:
        module = self.load_dispatcher_module()
        packet = self.packet("explicit-escalation", "gpt-5.6-sol", "high")
        max_role = self.codex_home / "agents" / "adaptive-luna-maker-max.toml"
        packet.update(
            {
                "agent_type": "adaptive-luna-maker-max",
                "reasoning_effort": "max",
                "evidence_path": str(max_role),
            }
        )
        packet["routing_audit"].update(
            {
                "attempt_index": 2,
                "effort_escalations": 1,
                "selection_basis": "failure_action",
                "route_id": "luna_max",
                "role": "adaptive-luna-maker-max",
                "route_model": "gpt-5.6-luna",
                "route_model_tier": "spark-tier",
                "route_reasoning_effort": "max",
            }
        )
        contract, real_audit = module._adaptive_modules()

        class AuditStub:
            LINKED_SCHEMA_VERSION = real_audit.LINKED_SCHEMA_VERSION
            MODELS = real_audit.MODELS
            EFFORTS = real_audit.EFFORTS
            AuditError = real_audit.AuditError

            @staticmethod
            def record_event(*_args, **_kwargs):
                return None

        with mock.patch.object(
            module, "_adaptive_modules", return_value=(contract, AuditStub)
        ):
            context, warning = module._start_adaptive_audit(
                packet,
                ledger=self.root / "routing.jsonl",
                review_dir=self.root / "reviews",
                attestation_ledger=self.root / "dispatch.jsonl",
            )

        self.assertIsNone(warning)
        self.assertIsNotNone(context)
        self.assertEqual(context.routing["route_id"], "luna_max")
        self.assertEqual(context.routing["role"], "adaptive-luna-maker-max")

    def test_adaptive_audit_rejects_escalation_without_explicit_route(self) -> None:
        module = self.load_dispatcher_module()
        packet = self.packet("missing-escalation", "gpt-5.6-sol", "high")
        packet["routing_audit"].update(
            {
                "attempt_index": 2,
                "effort_escalations": 1,
                "selection_basis": "failure_action",
            }
        )

        with self.assertRaisesRegex(
            RuntimeError, "routing policy cannot attest the selected route"
        ):
            module._start_adaptive_audit(
                packet,
                ledger=self.root / "routing.jsonl",
                review_dir=self.root / "reviews",
                attestation_ledger=self.root / "dispatch.jsonl",
            )

    def test_adaptive_audit_rejects_explicit_orphan_escalation(self) -> None:
        module = self.load_dispatcher_module()
        packet = self.packet("orphan-escalation", "gpt-5.6-sol", "high")
        packet["routing_audit"].update(
            {
                "attempt_index": 2,
                "selection_basis": "failure_action",
                "route_id": "luna_xhigh",
                "role": "adaptive-luna-maker-xhigh",
                "route_model": "gpt-5.6-luna",
                "route_model_tier": "spark-tier",
                "route_reasoning_effort": "xhigh",
            }
        )
        ledger = self.root / "orphan-routing.jsonl"

        with self.assertRaisesRegex(
            RuntimeError, "model-routing pre_decision record failed"
        ):
            module._start_adaptive_audit(
                packet,
                ledger=ledger,
                review_dir=self.root / "reviews",
                attestation_ledger=self.root / "dispatch.jsonl",
            )

        if ledger.exists():
            self.assertEqual(ledger.read_text(encoding="utf-8"), "")

    def test_failure_escalation_action_follows_the_next_ladder_step(self) -> None:
        module = self.load_dispatcher_module()
        contract, _audit = module._adaptive_modules()
        policy = json.loads(
            (
                self.codex_home
                / "skills"
                / "adaptive-delegation"
                / "config"
                / "model-routing.defaults.json"
            ).read_text(encoding="utf-8")
        )

        def action(route_id: str) -> str:
            context = SimpleNamespace(
                contract_module=contract,
                policy=policy,
                routing={
                    "task_class": "clear_implementation_or_transformation",
                    "oracle_strength": "strong",
                    "route_id": route_id,
                },
            )
            return module._configured_escalation_action(context)

        self.assertEqual(action("luna_high"), "raise_effort")
        self.assertEqual(action("luna_max"), "raise_model")
        self.assertEqual(action("terra_max"), "main_takeover")

    def test_external_legacy_file_cannot_authorize_undeclared_role(self) -> None:
        module = self.load_dispatcher_module()
        external_role = self.codex_home / "agents" / "external-role.toml"
        external_role.write_text(
            'name = "external-role"\n'
            'model = "gpt-5.6-luna"\n'
            'model_reasoning_effort = "xhigh"\n'
            'developer_instructions = "external role"\n',
            encoding="utf-8",
        )
        external_role.chmod(0o600)
        legacy = self.codex_home / ("." + "om" + "x-config.json")
        legacy.write_text(
            json.dumps(
                {
                    "env": {("OM" + "X_DEFAULT_SPARK_MODEL"): "gpt-5.6-luna"},
                    "agentModels": {"external-role": "gpt-5.6-luna"},
                    "agentReasoning": {"external-role": "xhigh"},
                }
            ),
            encoding="utf-8",
        )
        legacy.chmod(0o600)

        packet = self.packet("external-role", "gpt-5.6-sol", "high")
        packet.update(
            {
                "agent_type": "external-role",
                "evidence_path": str(external_role),
            }
        )
        self.assertIsNone(module._role_binding(packet))

    def test_local_policy_override_cannot_alter_package_binding(self) -> None:
        module = self.load_dispatcher_module()
        override = (
            self.codex_home
            / "state"
            / "model-routing"
            / ("policy" + ".local.json")
        )
        override.parent.mkdir(mode=0o700, parents=True)
        override.write_text(
            json.dumps(
                {
                    "role_bindings": {
                        "adaptive-luna-maker-xhigh": {
                            "model_tier": "standard-tier",
                            "model": "gpt-5.6-terra",
                            "reasoning_effort": "xhigh",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        override.chmod(0o600)

        packet = self.packet("override-ignored", "gpt-5.6-sol", "high")
        binding = module._role_binding(packet)
        self.assertIsNotNone(binding)
        self.assertEqual(binding.model, "gpt-5.6-luna")
        self.assertEqual(binding.model_tier, "spark-tier")

        packet["model_tier"] = "standard-tier"
        self.assertIsNone(module._role_binding(packet))

    def test_fixed_luna_agent_type_is_native_without_model_override(self) -> None:
        module = self.load_dispatcher_module()

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

    def test_recovery_launch_is_bound_to_dispatched_packet_and_route(self) -> None:
        module = self.load_dispatcher_module()
        primary = self.packet("bound-recovery", "gpt-5.6-sol", "high")
        terra = json.loads(json.dumps(primary))
        terra_role = self.codex_home / "agents" / "adaptive-terra-maker-xhigh.toml"
        terra.update(
            agent_type="adaptive-terra-maker-xhigh",
            model_tier="standard-tier",
            evidence_path=str(terra_role),
        )
        terra["routing_audit"].update(
            selection_basis="human_override",
            override_reason="Bounded fallback substitution regression setup.",
            route_id="terra_xhigh",
            role="adaptive-terra-maker-xhigh",
            route_model="gpt-5.6-terra",
            route_model_tier="standard-tier",
            route_reasoning_effort="xhigh",
        )
        binding = module._role_binding(terra)
        self.assertIsNotNone(binding)
        with mock.patch.dict(os.environ, self.environment, clear=False):
            tail = module._typed_exec_tail(binding, terra)
            self.assertIsNotNone(tail)
            payload = {
                "launch_type": "typed_external_worker",
                "packet": terra,
                "agent_type": binding.agent_type,
                "role_config": str(binding.role_config),
                "runtime_home": str(self.leaf_home),
                "argv": [str(self.fake_codex), *tail],
            }
            self.assertIsNone(
                module._typed_launch_binding(
                    payload, "typed_external_worker", primary
                )
            )
            self.assertIsNotNone(
                module._typed_launch_binding(
                    payload, "typed_external_worker", terra
                )
            )
            altered = json.loads(json.dumps(terra))
            altered["objective"] = "Broaden the fallback objective unexpectedly."
            altered_tail = module._typed_exec_tail(binding, altered)
            self.assertIsNotNone(altered_tail)
            altered_payload = {
                **payload,
                "packet": altered,
                "argv": [str(self.fake_codex), *altered_tail],
            }
            self.assertIsNone(
                module._typed_launch_binding(
                    altered_payload, "typed_external_worker", terra
                )
            )

    def test_provenance_rejections_record_zero_child_rejected_shape(self) -> None:
        module = self.load_dispatcher_module()
        packet = self.packet("provenance-zero-child", "gpt-5.6-sol", "high")
        binding = module._role_binding(packet)
        self.assertIsNotNone(binding)
        session_id = str(uuid.uuid4())
        base = {
            "receipt_kind": "native_admission",
            "receipt_version": module.RECEIPT_VERSION,
            "dispatch_id": packet["dispatch_id"],
            "surface_identity": "codex-app.collaboration.spawn_agent",
            "original_callable_schema": {
                "agent_type": "installed-role-enum",
                "reasoning_effort": "string",
                "fork_turns": "none",
            },
            "selection_mode": "verified-fixed-agent-type",
            "desired_route": "native_v2",
            "explicit_route": "native_v2",
            "installed_binding": {
                **module._binding_triple(binding),
                "fork_turns": "none",
            },
            "explicit_arguments": {
                "agent_type": binding.agent_type,
                "reasoning_effort": binding.effort,
                "fork_turns": "none",
            },
            "allowlist": [module._binding_triple(binding)],
            "gate_events": [
                {"name": "pending_receipt", "monotonic_ns": 1},
                {"name": "native_spawn_gate", "monotonic_ns": 2},
                {"name": "child_creation_eligibility", "monotonic_ns": 3},
            ],
            "issuer": {
                "rollout_session_id": session_id,
                "role": module._binding_triple(binding),
                "role_config": str(binding.role_config),
                "role_config_digest": module._role_config_digest(binding),
            },
        }
        path = self.root / "provenance-receipt.json"
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o600)
        cases = {
            "invalid_admission_receipt": None,
            "receipt_kind_or_version_invalid": {**base, "receipt_kind": "wrong"},
            "admission_dispatch_id_mismatch": {**base, "dispatch_id": "other"},
            "trusted_precreation_issuer_missing": {
                **base,
                "issuer": {**base["issuer"], "rollout_session_id": "other-session"},
            },
            "admission_issuer_binding_mismatch": {
                **base,
                "issuer": {**base["issuer"], "role_config": str(self.role) + ".wrong"},
            },
            "admission_role_config_digest_invalid": {
                **base,
                "issuer": {**base["issuer"], "role_config_digest": "0" * 64},
            },
            "trusted_precreation_marker_missing": base,
        }
        for reason, value in cases.items():
            with self.subTest(reason=reason):
                structural_value = base if value is None else value
                envelope = module.ReceiptEnvelope(structural_value, path)
                structural = module._native_structural_admission(
                    envelope,
                    binding,
                    dispatch_id=packet["dispatch_id"],
                )
                provenance_value = None if value is None else envelope
                receipt = module._native_admission_provenance(
                    provenance_value,
                    structural,
                    binding,
                    dispatch_id=packet["dispatch_id"],
                    rollout=None,
                    session_id=session_id,
                )
                self.assertEqual(receipt["rejection_reason"], reason)
                self.assertEqual(receipt["status"], "rejected")
                self.assertEqual(receipt["child_count"], 0)
                self.assertEqual(receipt["child_tokens"], 0)
                self.assertEqual(receipt["selected_fallback"], "typed_external_worker")


if __name__ == "__main__":
    unittest.main()
