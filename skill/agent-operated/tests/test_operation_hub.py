from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
CORE = SKILL / "scripts" / "core"
GTP = SKILL / "scripts" / "operations" / "gtp" / "recover.py"
PUBLICATION = SKILL / "scripts" / "operations" / "publication" / "check.py"
ISSUE_URL = "https://github.com/example/project/issues/7"

sys.path.insert(0, str(CORE))
from internal_policy_gate import (  # noqa: E402
    CandidateCheckRequest,
    GateDecision,
    GateStatus,
    InternalPolicyGate,
    PlanCheckRequest,
    ProjectionArtifact,
    ProjectionCheckRequest,
)


class ProceedingPolicyProvider:
    def __init__(self) -> None:
        self.phases: list[str] = []

    def check_plan(self, request: PlanCheckRequest) -> GateDecision:
        self.phases.append("plan")
        return GateDecision(GateStatus.PROCEED)

    def check_candidate(self, request: CandidateCheckRequest) -> GateDecision:
        self.phases.append("candidate")
        return GateDecision(GateStatus.PROCEED)

    def check_projection(self, request: ProjectionCheckRequest) -> GateDecision:
        self.phases.append("projection")
        return GateDecision(GateStatus.PROCEED)


class OperationHubEndToEndTests(unittest.TestCase):
    def write_json(self, directory: Path, name: str, value: object) -> Path:
        path = directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def run_json(self, command: list[str], *, environment: dict[str, str] | None = None) -> tuple[int, dict]:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"invalid JSON: {error}; stdout={completed.stdout!r}; stderr={completed.stderr!r}")
        self.assertIsInstance(value, dict)
        return completed.returncode, value

    def make_fake_gtp(self, directory: Path) -> Path:
        path = directory / "gtp"
        path.write_text(
            """#!/usr/bin/env python3
import json
import sys
if sys.argv[1:] == ["--version"]:
    print("1.0.1")
    raise SystemExit(0)
issue = sys.argv[2]
print(json.dumps({
    "gtp": "1.0",
    "command": "status",
    "issue_url": issue,
    "state": "unmanaged",
    "halt_reason": None,
    "next_action": "post_contract",
    "primary_url": issue,
    "authority": "none",
    "acquisition": "complete"
}, ensure_ascii=False, indent=2, sort_keys=True))
""",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def bind(self, directory: Path, name: str, value: dict) -> tuple[int, dict]:
        source = self.write_json(directory, name, value)
        return self.run_json([sys.executable, str(CORE / "bind_operation_result.py"), str(source)])

    def test_raw_hub_path_preserves_results_and_separates_candidate_binding(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            provider = ProceedingPolicyProvider()
            gate = InternalPolicyGate(provider)
            plan_decision = gate.check_plan(
                task_ref=ISSUE_URL,
                plan={"scope": "portable boundary repair"},
            )
            self.assertEqual(GateStatus.PROCEED, plan_decision.status)
            profile = self.write_json(
                directory,
                "profile.json",
                {
                    "profile_version": 1,
                    "machine_actor": {"login": "machine", "id": 101},
                    "human_actor": {"login": "human", "id": 202},
                    "human_only_operations": ["acceptance_decision"],
                    "merge_policy": "human_only",
                },
            )
            observed_user = self.write_json(directory, "user.json", {"login": "machine", "id": 101})
            code, actor_result = self.run_json([
                sys.executable,
                str(CORE / "verify_actor.py"),
                "--profile",
                str(profile),
                "--user-json",
                str(observed_user),
                "--allow-fixture",
            ])
            self.assertEqual(0, code)
            self.assertIsNone(actor_result["candidate_head_sha"])
            self.assertEqual("proceed", actor_result["verdict"])

            fake_gtp = self.make_fake_gtp(directory)
            code, gtp_result = self.run_json([
                sys.executable,
                str(GTP),
                "--issue-url",
                ISSUE_URL,
                "--gtp-command",
                str(fake_gtp),
            ])
            self.assertEqual(0, code)
            code, recovery_receipt = self.bind(
                directory,
                "recovery-input.json",
                {
                    "operation": "gtp",
                    "phase": "task_recovery",
                    "task_ref": ISSUE_URL,
                    "implementation_version": "1.0.1",
                    "source_ref": ISSUE_URL,
                    "candidate_required": False,
                    "result": gtp_result,
                },
            )
            self.assertEqual(0, code)
            self.assertEqual("not_applicable", recovery_receipt["candidate_binding"]["status"])
            self.assertEqual(gtp_result, recovery_receipt["result"])
            self.assertNotIn("verdict", recovery_receipt)

            publication = directory / "publication.md"
            publication.write_text("candidate: " + candidate + "\n", encoding="utf-8")
            candidate_decision = gate.check_candidate(
                task_ref=ISSUE_URL,
                candidate_head_sha=candidate,
                observations={"actor": actor_result, "recovery": gtp_result},
            )
            projection_decision = gate.check_projection(
                task_ref=ISSUE_URL,
                artifacts=(ProjectionArtifact("publication.md", publication.read_text()),),
            )
            self.assertEqual(GateStatus.PROCEED, candidate_decision.status)
            self.assertEqual(GateStatus.PROCEED, projection_decision.status)
            code, publication_result = self.run_json([sys.executable, str(PUBLICATION), str(publication)])
            self.assertEqual(0, code)
            code, publication_receipt = self.bind(
                directory,
                "publication-input.json",
                {
                    "operation": "publication_screening",
                    "phase": "pre_publication",
                    "task_ref": ISSUE_URL,
                    "implementation_version": "1",
                    "source_ref": ISSUE_URL,
                    "candidate_required": True,
                    "candidate_head_sha": candidate,
                    "observed_head_sha": candidate,
                    "result": publication_result,
                },
            )
            self.assertEqual(0, code)
            self.assertEqual("bound", publication_receipt["candidate_binding"]["status"])
            self.assertEqual(publication_result, publication_receipt["result"])
            self.assertEqual(["plan", "candidate", "projection"], provider.phases)
            self.assertNotIn("internal_policy", json.dumps(publication_receipt))

            acceptance_input = self.write_json(
                directory,
                "acceptance.json",
                {
                    "task_ref": ISSUE_URL,
                    "candidate_head_sha": candidate,
                    "pr_ref": "https://github.com/example/project/pull/8",
                    "human_actor": {"login": "human", "id": 202},
                },
            )
            pr = self.write_json(
                directory,
                "pr.json",
                {
                    "head": {"sha": candidate},
                    "merged_at": "2026-07-20T00:00:00Z",
                    "merged_by": {"login": "human", "id": 202},
                },
            )
            code, acceptance = self.run_json([
                sys.executable,
                str(CORE / "verify_acceptance_readback.py"),
                str(acceptance_input),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(0, code)
            self.assertEqual("observed", acceptance["acceptance_state"])
            self.assertNotIn("verdict", acceptance)


if __name__ == "__main__":
    unittest.main()
