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
PUBLICATION_DIR = SKILL / "scripts" / "operations" / "publication"
ISSUE_URL = "https://github.com/example/project/issues/7"

sys.path.insert(0, str(CORE))
sys.path.insert(0, str(PUBLICATION_DIR))
from internal_policy_gate import (  # noqa: E402
    CandidateCheckRequest,
    GateDecision,
    GateStatus,
    InternalPolicyGate,
    PlanCheckRequest,
    ProjectionArtifact,
    ProjectionBatch,
    ProjectionCheckRequest,
)
from transition_coordinator import CheckedPlan, TransitionCoordinator  # noqa: E402
from check import screen_batch  # noqa: E402


class ProceedingPolicyProvider:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def check_plan(self, request: PlanCheckRequest) -> GateDecision:
        self.events.append("check_plan")
        return GateDecision(GateStatus.PROCEED)

    def check_candidate(self, request: CandidateCheckRequest) -> GateDecision:
        self.events.append("check_candidate")
        return GateDecision(GateStatus.PROCEED)

    def check_projection(self, request: ProjectionCheckRequest) -> GateDecision:
        self.events.append("check_projection")
        return GateDecision(GateStatus.PROCEED)


class OperationHubEndToEndTests(unittest.TestCase):
    def write_json(self, directory: Path, name: str, value: object) -> Path:
        path = directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def run_json(self, command: list[str]) -> tuple[int, dict]:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
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

    def test_real_portable_route_preserves_order_and_boundaries(self) -> None:
        candidate = "a" * 40
        events: list[str] = []
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            provider = ProceedingPolicyProvider(events)
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
            fake_gtp = self.make_fake_gtp(directory)

            def recover_task(task_ref: str) -> dict:
                events.append("gtp_recovery")
                self.assertEqual(ISSUE_URL, task_ref)
                code, result = self.run_json([
                    sys.executable,
                    str(GTP),
                    "--issue-url",
                    ISSUE_URL,
                    "--gtp-command",
                    str(fake_gtp),
                ])
                self.assertEqual(0, code)
                return result

            def build_plan(projection: dict) -> dict:
                events.append("build_plan")
                self.assertEqual("unmanaged", projection["gtp_projection"]["state"])
                return {"scope": "portable boundary repair", "allowed_paths": ["skill/"]}

            actor_result: dict = {}

            def observe_actor() -> dict:
                events.append("actor_observation")
                code, result = self.run_json([
                    sys.executable,
                    str(CORE / "verify_actor.py"),
                    "--profile",
                    str(profile),
                    "--user-json",
                    str(observed_user),
                    "--allow-fixture",
                ])
                self.assertEqual(0, code)
                actor_result.update(result)
                return result

            artifact = ProjectionArtifact("publication.md", b"public candidate\n")
            published_batches: list[ProjectionBatch] = []
            coordinator = TransitionCoordinator(
                InternalPolicyGate(provider),
                recover_task=recover_task,
                build_plan=build_plan,
                observe_actor=observe_actor,
                batch_source=lambda head: ProjectionBatch.build(
                    candidate_head_sha=head,
                    artifacts=(artifact,),
                ),
                screening=screen_batch,
                publisher=lambda batch: published_batches.append(batch),
            )
            checked = coordinator.prepare_plan(task_ref=ISSUE_URL)
            self.assertIsInstance(checked, CheckedPlan)

            coordinator.run_first_mutation(
                checked,
                mutation=lambda: events.append("mutation"),
            )
            coordinator.continue_candidate(
                task_ref=ISSUE_URL,
                candidate_head_sha=candidate,
                observations={"actor": actor_result},
                callback=lambda: events.append("candidate_continuation"),
            )

            screening_result, _ = coordinator.publish_projection(
                task_ref=ISSUE_URL,
                candidate_head_sha=candidate,
            )
            self.assertEqual("proceed", screening_result["verdict"])
            self.assertEqual(1, len(published_batches))

            coordinator.handoff(
                task_ref=ISSUE_URL,
                candidate_head_sha=candidate,
                observations={"tests": "passed"},
                callback=lambda: events.append("handoff"),
            )

            code, publication_receipt = self.bind(
                directory,
                "publication-input.json",
                {
                    "operation": "publication_screening",
                    "phase": "pre_publication",
                    "task_ref": ISSUE_URL,
                    "implementation_version": "1",
                    "source_ref": ISSUE_URL,
                    "candidate_required": False,
                    "result": screening_result,
                },
            )
            self.assertEqual(0, code)
            self.assertEqual("not_applicable", publication_receipt["candidate_binding"]["status"])

            acceptance_input = self.write_json(
                directory,
                "acceptance.json",
                {
                    "task_ref": ISSUE_URL,
                    "candidate_head_sha": candidate,
                    "pr_ref": "https://github.com/example/project/pull/8",
                },
            )
            pr = self.write_json(
                directory,
                "pr.json",
                {
                    "base": {"repo": {"full_name": "example/project"}},
                    "head": {"sha": candidate},
                    "merged_at": "2026-07-20T00:00:00Z",
                    "merged_by": {"login": "human", "id": 202},
                },
            )
            code, acceptance = self.run_json([
                sys.executable,
                str(CORE / "verify_acceptance_readback.py"),
                str(acceptance_input),
                "--profile",
                str(profile),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(0, code)
            self.assertEqual("observed", acceptance["acceptance_state"])

        self.assertEqual(
            [
                "gtp_recovery",
                "build_plan",
                "check_plan",
                "actor_observation",
                "mutation",
                "check_candidate",
                "candidate_continuation",
                "check_projection",
                "check_candidate",
                "handoff",
            ],
            events,
        )


if __name__ == "__main__":
    unittest.main()
