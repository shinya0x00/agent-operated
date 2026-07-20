from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
REPOSITORY = SKILL.parents[1]
CORE = SKILL / "scripts" / "core"
GTP = SKILL / "scripts" / "operations" / "gtp" / "recover.py"
PUBLICATION = SKILL / "scripts" / "operations" / "publication" / "check.py"
PUBLICATION_DIR = PUBLICATION.parent
BINDER = CORE / "bind_operation_result.py"
ACCEPTANCE = CORE / "verify_acceptance_readback.py"
ISSUE_URL = "https://github.com/example/project/issues/7"

sys.path.insert(0, str(CORE))
sys.path.insert(0, str(PUBLICATION_DIR))
from actor_contract import ActorObservation, ActorProfile  # noqa: E402
from internal_policy_gate import (  # noqa: E402
    CandidateCheckRequest,
    GateDecision,
    GateFinding,
    GateStatus,
    InternalPolicyGate,
    PlanCheckRequest,
    ProjectionArtifact,
    ProjectionBatch,
    ProjectionCheckRequest,
)
from transition_coordinator import (  # noqa: E402
    CheckedCandidate,
    HandoffReady,
    InvocationContext,
    PlanDraft,
    PublicOperationBlocked,
    TransitionBlocked,
    TransitionCoordinator,
)
from check import screen_batch  # noqa: E402


class RecordingPolicyProvider:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def check_plan(self, request: PlanCheckRequest) -> GateDecision:
        self.requests.append(request)
        return GateDecision(GateStatus.PROCEED)

    def check_candidate(self, request: CandidateCheckRequest) -> GateDecision:
        self.requests.append(request)
        return GateDecision(GateStatus.PROCEED)

    def check_projection(self, request: ProjectionCheckRequest) -> GateDecision:
        self.requests.append(request)
        return GateDecision(GateStatus.PROCEED)


class PortableCoreTests(unittest.TestCase):
    def run_json(
        self,
        command: list[str],
        *,
        environment: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> tuple[int, dict, str]:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            cwd=cwd,
            timeout=30,
        )
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"invalid JSON: {error}; stdout={completed.stdout!r}; stderr={completed.stderr!r}")
        self.assertIsInstance(value, dict)
        return completed.returncode, value, completed.stderr

    def write_json(self, directory: Path, name: str, value: object) -> Path:
        path = directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def make_executable(self, directory: Path, name: str, source: str) -> Path:
        path = directory / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o755)
        return path

    def actor_profile(self) -> dict:
        return {
            "profile_version": 1,
            "machine_actor": {"login": "machine", "id": 101},
            "human_actor": {"login": "human", "id": 202},
            "human_only_operations": ["acceptance_decision"],
            "merge_policy": "human_only",
        }

    def actor_profile_object(self) -> ActorProfile:
        return ActorProfile.from_mapping(self.actor_profile())

    def profile_digest(self, path: Path) -> str:
        return ActorProfile.load(path).digest

    def live_actor_observation(
        self,
        profile: ActorProfile,
        operation_class: str,
        candidate_head_sha: str | None,
    ) -> ActorObservation:
        return ActorObservation(
            operation_class=operation_class,
            candidate_head_sha=candidate_head_sha,
            observed_at="2000-01-01T00:00:00Z",
            actor=profile.machine_actor,
            profile_digest=profile.digest,
        )

    def plan_draft(self, *, body: bytes = b"target-native plan") -> PlanDraft:
        return PlanDraft.build(
            plan={"scope": "candidate"},
            publication_artifact=ProjectionArtifact("plan_body", "PLAN_BODY", body),
        )

    def bind(self, directory: Path, name: str, value: dict) -> tuple[int, dict, str]:
        source = self.write_json(directory, name, value)
        return self.run_json([sys.executable, str(BINDER), str(source)])

    def coordinator(
        self,
        provider: RecordingPolicyProvider,
        *,
        recover_task=None,
        build_plan=None,
        observe_actor=None,
        batch_source=None,
        screening=None,
        publisher=None,
        actor_profile=None,
    ) -> TransitionCoordinator:
        profile = actor_profile or self.actor_profile_object()
        return TransitionCoordinator(
            InternalPolicyGate(provider),
            actor_profile=profile,
            recover_task=recover_task or (lambda task_ref: {"state": "ready"}),
            build_plan=build_plan or (lambda projection: self.plan_draft()),
            observe_actor=observe_actor
            or (
                lambda operation_class, candidate_head_sha: self.live_actor_observation(
                    profile,
                    operation_class,
                    candidate_head_sha,
                )
            ),
            batch_source=batch_source
            or (
                lambda request: ProjectionBatch.build(
                    checked_plan_digest=request.checked_plan_digest,
                    candidate_head_sha=request.candidate_head_sha,
                    artifacts=(ProjectionArtifact("pr_body", "PR_BODY", b"public"),),
                )
            ),
            screening=screening or screen_batch,
            publisher=publisher or (lambda batch: None),
        )

    def test_smoke_fires_every_registered_attachment(self) -> None:
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        attachments = {
            "actor_preflight": CORE / "verify_actor.py",
            "operation_result_binding": BINDER,
            "acceptance_readback": ACCEPTANCE,
            "gtp_operation": GTP,
            "publication_screening": PUBLICATION,
        }
        observed: set[str] = set()
        for attachment, script in attachments.items():
            relative = script.relative_to(SKILL).as_posix()
            self.assertIn(relative, skill)
            code, output, _ = self.run_json([sys.executable, str(script), "--smoke"])
            self.assertEqual(0, code)
            self.assertEqual(attachment, output["attachment"])
            self.assertTrue(output["fired"])
            self.assertTrue(output["validated"])
            self.assertEqual("none", output["authority"])
            observed.add(attachment)
        self.assertEqual(set(attachments), observed)

        provider = RecordingPolicyProvider()
        gate = InternalPolicyGate(provider)
        candidate = "a" * 40
        plan_artifact = ProjectionArtifact("plan_body", "PLAN_BODY", b"plan")
        batch = ProjectionBatch.build(
            checked_plan_digest="f" * 64,
            candidate_head_sha=candidate,
            artifacts=(ProjectionArtifact("purpose", "PURPOSE.md", b"public content"),),
        )
        decisions = (
            gate.check_plan(
                task_ref=ISSUE_URL,
                task_projection={"state": "in_progress"},
                plan={"scope": "candidate"},
                publication_artifact=plan_artifact,
            ),
            gate.check_candidate(
                task_ref=ISSUE_URL,
                candidate_head_sha=candidate,
                observations={"tests": "passed"},
            ),
            gate.check_projection(
                task_ref=ISSUE_URL,
                batch=batch,
            ),
        )
        self.assertTrue(all(item.status is GateStatus.PROCEED for item in decisions))
        self.assertEqual(
            [PlanCheckRequest, CandidateCheckRequest, ProjectionCheckRequest],
            [type(item) for item in provider.requests],
        )

    def test_internal_policy_gate_is_host_supplied_and_invocation_local(self) -> None:
        provider = RecordingPolicyProvider()
        gate = InternalPolicyGate(provider)
        decision = gate.check_plan(
            task_ref=ISSUE_URL,
            task_projection={"state": "in_progress"},
            plan={"scope": "candidate"},
            publication_artifact=ProjectionArtifact("plan_body", "PLAN_BODY", b"plan"),
        )

        self.assertFalse(hasattr(gate, "to_json"))
        self.assertFalse(hasattr(decision, "to_dict"))
        with self.assertRaises(TypeError):
            json.dumps(decision)

        module_source = (CORE / "internal_policy_gate.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess.run", module_source)
        self.assertNotIn("os.environ", module_source)
        self.assertNotIn("argparse.ArgumentParser", module_source)

    def test_internal_policy_gate_validates_candidate_and_provider_result(self) -> None:
        provider = RecordingPolicyProvider()
        gate = InternalPolicyGate(provider)

        with self.assertRaises(ValueError):
            gate.check_candidate(
                task_ref=ISSUE_URL,
                candidate_head_sha="short",
                observations={},
            )

        private_marker = "https://private.example.invalid/config /private/provider/path"
        private_errors: list[Exception] = []

        class InvalidProvider(RecordingPolicyProvider):
            def check_projection(self, request: ProjectionCheckRequest) -> GateDecision:
                return {"status": "proceed"}  # type: ignore[return-value]

        batch = ProjectionBatch.build(
            checked_plan_digest="f" * 64,
            candidate_head_sha="a" * 40,
            artifacts=(ProjectionArtifact("purpose", "PURPOSE.md", b"public content"),),
        )
        decision = InternalPolicyGate(
            InvalidProvider(),
            private_error_sink=private_errors.append,
        ).check_projection(task_ref=ISSUE_URL, batch=batch)
        self.assertEqual(GateStatus.BLOCKED, decision.status)
        self.assertEqual("internal_check_unavailable", decision.findings[0].code)
        self.assertTrue(private_errors)

        class RaisingProvider(RecordingPolicyProvider):
            def check_plan(self, request: PlanCheckRequest) -> GateDecision:
                raise RuntimeError(private_marker)

        captured_errors: list[Exception] = []
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            decision = InternalPolicyGate(
                RaisingProvider(),
                private_error_sink=captured_errors.append,
            ).check_plan(
                task_ref=ISSUE_URL,
                task_projection={"state": "ready"},
                plan={"scope": "candidate"},
                publication_artifact=ProjectionArtifact("plan_body", "PLAN_BODY", b"plan"),
            )
        public_text = repr(decision) + str(decision) + stdout.getvalue() + stderr.getvalue()
        self.assertNotIn(private_marker, public_text)
        self.assertNotIn("private.example.invalid", public_text)
        self.assertNotIn("/private/provider/path", public_text)
        self.assertEqual(private_marker, str(captured_errors[0]))

        with self.assertRaises(TypeError):
            GateDecision("proceed")  # type: ignore[arg-type]

        finding = GateFinding(
            code="candidate_evidence_missing",
            message="candidate validation evidence is missing",
            target_ref="tests/evidence.json",
        )
        self.assertEqual(
            GateStatus.BLOCKED,
            GateDecision(GateStatus.BLOCKED, (finding,)).status,
        )

    def test_transition_coordinator_blocks_protected_callbacks(self) -> None:
        finding = GateFinding(code="plan_invalid", message="plan must be repaired")

        class BlockedProvider(RecordingPolicyProvider):
            def check_plan(self, request: PlanCheckRequest) -> GateDecision:
                return GateDecision(GateStatus.BLOCKED, (finding,))

            def check_candidate(self, request: CandidateCheckRequest) -> GateDecision:
                return GateDecision(GateStatus.BLOCKED, (finding,))

            def check_projection(self, request: ProjectionCheckRequest) -> GateDecision:
                return GateDecision(GateStatus.BLOCKED, (finding,))

        calls = {"actor": 0, "mutation": 0, "publisher": 0}
        coordinator = self.coordinator(
            BlockedProvider(),
            observe_actor=lambda operation, head: calls.__setitem__("actor", calls["actor"] + 1),
            publisher=lambda batch: calls.__setitem__("publisher", calls["publisher"] + 1),
        )
        with self.assertRaises(TransitionBlocked):
            coordinator.prepare_plan(task_ref=ISSUE_URL)
        self.assertEqual(0, calls["actor"])
        self.assertEqual(0, calls["mutation"])

        self.assertEqual({"actor": 0, "mutation": 0, "publisher": 0}, calls)

        class RaisingProvider(RecordingPolicyProvider):
            def check_plan(self, request: PlanCheckRequest) -> GateDecision:
                raise RuntimeError("https://private.example.invalid /private/provider/path")

        raising = self.coordinator(
            RaisingProvider(),
            observe_actor=lambda operation, head: calls.__setitem__("actor", calls["actor"] + 1),
        )
        with self.assertRaises(TransitionBlocked) as blocked:
            raising.prepare_plan(task_ref=ISSUE_URL)
        self.assertEqual("AO transition blocked", str(blocked.exception))
        self.assertEqual(0, calls["actor"])
        self.assertEqual(0, calls["mutation"])

        proceeding = RecordingPolicyProvider()
        owner = self.coordinator(proceeding)
        foreign_context = owner.prepare_plan(task_ref=ISSUE_URL)
        foreign_candidate = owner.check_candidate(
            foreign_context,
            candidate_head_sha="a" * 40,
            observations={},
        )
        fresh = self.coordinator(
            proceeding,
            publisher=lambda batch: calls.__setitem__("publisher", calls["publisher"] + 1),
        )
        for removed_api in ("run_first_mutation", "continue_candidate", "handoff"):
            self.assertFalse(hasattr(fresh, removed_api))
        with self.assertRaises(TransitionBlocked):
            fresh.run_github_mutation(
                foreign_context,
                operation_class="commit",
                mutation=lambda: calls.__setitem__("mutation", calls["mutation"] + 1),
            )
        with self.assertRaises(TransitionBlocked):
            fresh.check_candidate(
                foreign_context,
                candidate_head_sha="a" * 40,
                observations={},
            )
        with self.assertRaises(TransitionBlocked):
            fresh.publish_projection(foreign_context, candidate=foreign_candidate)
        with self.assertRaises(TransitionBlocked):
            fresh.prepare_handoff(
                foreign_context,
                candidate=foreign_candidate,
                observations={},
            )
        self.assertEqual(0, calls["mutation"])
        self.assertEqual(0, calls["publisher"])

    def test_actor_observation_strictly_gates_every_github_write(self) -> None:
        profile = self.actor_profile_object()
        invalid_observations: tuple[object, ...] = (
            True,
            {"verdict": "proceed"},
            {
                "decision_scope": "ao_detector_test",
                "actor_role": "machine_actor",
                "observation_source": "fixture",
                "live_actor_verified": False,
                "verdict": "proceed",
                "authority": "none",
                "findings": [],
            },
            self.live_actor_observation(profile, "push", None),
            ActorObservation(
                operation_class="commit",
                candidate_head_sha=None,
                observed_at="2000-01-01T00:00:00Z",
                actor=profile.machine_actor,
                profile_digest="f" * 64,
            ),
        )
        for invalid in invalid_observations:
            mutations: list[str] = []
            coordinator = self.coordinator(
                RecordingPolicyProvider(),
                observe_actor=lambda operation, head, value=invalid: value,
            )
            context = coordinator.prepare_plan(task_ref=ISSUE_URL)
            with self.assertRaises(TransitionBlocked):
                coordinator.run_github_mutation(
                    context,
                    operation_class="commit",
                    mutation=lambda: mutations.append("commit"),
                )
            self.assertEqual([], mutations)

        observations: list[str] = []

        def observe(operation: str, head: str | None) -> ActorObservation | object:
            observations.append(operation)
            if len(observations) == 2:
                return True
            return self.live_actor_observation(
                profile,
                operation,
                head,
            )

        mutations = []
        coordinator = self.coordinator(
            RecordingPolicyProvider(),
            actor_profile=profile,
            observe_actor=observe,
        )
        context = coordinator.prepare_plan(task_ref=ISSUE_URL)
        coordinator.run_github_mutation(
            context,
            operation_class="commit",
            mutation=lambda: mutations.append("commit"),
        )
        with self.assertRaises(TransitionBlocked):
            coordinator.run_github_mutation(
                context,
                operation_class="push",
                mutation=lambda: mutations.append("push"),
            )
        self.assertEqual(["commit", "push"], observations)
        self.assertEqual(["commit"], mutations)

    def test_projection_batch_is_same_object_for_screening_and_publish(self) -> None:
        provider = RecordingPolicyProvider()
        observed: list[ProjectionBatch] = []

        def screening(value: ProjectionBatch) -> dict:
            observed.append(value)
            return screen_batch(value)

        coordinator = self.coordinator(
            provider,
            batch_source=lambda request: ProjectionBatch.build(
                checked_plan_digest=request.checked_plan_digest,
                candidate_head_sha=request.candidate_head_sha,
                artifacts=(
                    ProjectionArtifact("purpose", "PURPOSE.md", b"public file"),
                    ProjectionArtifact("pr_body", "PR_BODY", b"public body"),
                ),
            ),
            screening=screening,
            publisher=lambda value: observed.append(value),
        )
        context = coordinator.prepare_plan(task_ref=ISSUE_URL)
        candidate = coordinator.check_candidate(
            context,
            candidate_head_sha="a" * 40,
            observations={},
        )
        coordinator.publish_projection(context, candidate=candidate)
        self.assertIs(observed[0], observed[1])
        observed[0].validate_digest()

        published: list[ProjectionBatch] = []
        blocked_coordinator = self.coordinator(
            provider,
            batch_source=lambda request: ProjectionBatch.build(
                checked_plan_digest=request.checked_plan_digest,
                candidate_head_sha=request.candidate_head_sha,
                artifacts=(
                    ProjectionArtifact("pr_body", "PR_BODY", b"GH_TOKEN=private-value"),
                ),
            ),
            screening=screen_batch,
            publisher=published.append,
        )
        blocked_context = blocked_coordinator.prepare_plan(task_ref=ISSUE_URL)
        with self.assertRaises(PublicOperationBlocked) as blocked_publication:
            blocked_coordinator.publish_projection(blocked_context, candidate=None)
        self.assertEqual([], published)
        public_result = json.dumps(blocked_publication.exception.result)
        self.assertNotIn("PR_BODY", public_result)
        self.assertIn("pr_body", public_result)

        with self.assertRaises(ValueError):
            ProjectionBatch.build(
                checked_plan_digest="f" * 64,
                candidate_head_sha="a" * 40,
                artifacts=(
                    ProjectionArtifact("duplicate", "PR_BODY", b"one"),
                    ProjectionArtifact("duplicate", "PR_BODY", b"two"),
                ),
            )

        for unsafe_ref in (
            "/Users/example/private-plan.md",
            "../private-plan.md",
            "folder\\private-plan.md",
            "https://private.example/plan",
            "PURPOSE.md?token=value",
            "PURPOSE.md#private",
        ):
            with self.assertRaises(ValueError):
                ProjectionArtifact("unsafe", unsafe_ref, b"content")

        private_marker = "/private/batch/source"

        def failing_source(request: object) -> ProjectionBatch:
            raise RuntimeError(private_marker)

        source_failure = self.coordinator(provider, batch_source=failing_source)
        source_context = source_failure.prepare_plan(task_ref=ISSUE_URL)
        with self.assertRaises(TransitionBlocked) as blocked:
            source_failure.publish_projection(source_context, candidate=None)
        self.assertNotIn(private_marker, str(blocked.exception))

        mismatch_screening: list[ProjectionBatch] = []
        mismatch = self.coordinator(
            provider,
            batch_source=lambda request: ProjectionBatch.build(
                checked_plan_digest="f" * 64,
                candidate_head_sha=request.candidate_head_sha,
                artifacts=(ProjectionArtifact("pr_body", "PR_BODY", b"public"),),
            ),
            screening=lambda batch: mismatch_screening.append(batch) or screen_batch(batch),
            publisher=published.append,
        )
        mismatch_context = mismatch.prepare_plan(task_ref=ISSUE_URL)
        with self.assertRaises(TransitionBlocked):
            mismatch.publish_projection(mismatch_context, candidate=None)
        self.assertEqual([], mismatch_screening)
        self.assertEqual([], published)

    def test_checked_plan_is_rechecked_and_digest_bound(self) -> None:
        provider = RecordingPolicyProvider()
        projections = iter((
            {"state": "ready", "contract": "v1"},
            {"state": "ready", "contract": "v2"},
        ))
        plans = iter((
            PlanDraft.build(
                plan={"scope": "one"},
                publication_artifact=ProjectionArtifact("plan_body", "PLAN_BODY", b"plan one"),
            ),
            PlanDraft.build(
                plan={"scope": "two"},
                publication_artifact=ProjectionArtifact("plan_body", "PLAN_BODY", b"plan two"),
            ),
        ))
        coordinator = self.coordinator(
            provider,
            recover_task=lambda task_ref: next(projections),
            build_plan=lambda projection: next(plans),
        )
        first = coordinator.prepare_plan(task_ref=ISSUE_URL)
        second = coordinator.prepare_plan(task_ref=ISSUE_URL)
        self.assertNotEqual(first.digest, second.digest)
        self.assertEqual(2, len([item for item in provider.requests if isinstance(item, PlanCheckRequest)]))

        calls: list[str] = []
        with self.assertRaises(TransitionBlocked):
            coordinator.run_github_mutation(
                first,
                operation_class="commit",
                mutation=lambda: calls.append("mutation"),
            )
        self.assertEqual([], calls)

        object.__setattr__(second.checked_plan, "plan_json", '{"scope":"tampered"}')
        with self.assertRaises(TransitionBlocked):
            coordinator.run_github_mutation(
                second,
                operation_class="commit",
                mutation=lambda: calls.append("mutation"),
            )
        self.assertEqual([], calls)

        fresh_coordinator = self.coordinator(provider)
        with self.assertRaises(TransitionBlocked):
            fresh_coordinator.run_github_mutation(
                first,
                operation_class="commit",
                mutation=lambda: None,
            )

    def test_context_binds_task_profile_and_candidate(self) -> None:
        provider = RecordingPolicyProvider()
        coordinator = self.coordinator(provider)
        first = coordinator.prepare_plan(task_ref=ISSUE_URL)
        first_candidate = coordinator.check_candidate(
            first,
            candidate_head_sha="a" * 40,
            observations={},
        )
        second = coordinator.prepare_plan(
            task_ref="https://github.com/example/project/issues/8"
        )
        with self.assertRaises(TransitionBlocked):
            coordinator.prepare_handoff(
                first,
                candidate=first_candidate,
                observations={},
            )

        cross_task_candidate = CheckedCandidate(
            second.digest,
            ISSUE_URL,
            "a" * 40,
        )
        with self.assertRaises(TransitionBlocked):
            coordinator.publish_projection(second, candidate=cross_task_candidate)

        object.__setattr__(second, "actor_profile_digest", "f" * 64)
        object.__setattr__(
            second,
            "digest",
            InvocationContext.compute_digest(
                second.checked_plan.digest,
                second.actor_profile_digest,
            ),
        )
        mutations: list[str] = []
        with self.assertRaises(TransitionBlocked):
            coordinator.run_github_mutation(
                second,
                operation_class="push",
                mutation=lambda: mutations.append("push"),
            )
        self.assertEqual([], mutations)

    def test_plan_publication_uses_projection_batch_route(self) -> None:
        provider = RecordingPolicyProvider()
        published: list[ProjectionBatch] = []
        coordinator = self.coordinator(
            provider,
            build_plan=lambda projection: self.plan_draft(body=b"checked plan A"),
            batch_source=lambda request: (_ for _ in ()).throw(AssertionError("unused")),
            publisher=published.append,
        )
        context = coordinator.prepare_plan(task_ref=ISSUE_URL)
        result, _ = coordinator.publish_plan(context)
        self.assertEqual("proceed", result["verdict"])
        self.assertEqual(1, len(published))
        self.assertIsNone(published[0].candidate_head_sha)
        self.assertEqual(b"checked plan A", published[0].artifacts[0].content)
        self.assertIs(context.checked_plan.publication_artifact, published[0].artifacts[0])
        plan_request = next(
            item for item in provider.requests if isinstance(item, PlanCheckRequest)
        )
        self.assertIs(plan_request.publication_artifact, published[0].artifacts[0])

    def test_actor_observation_does_not_require_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            profile = self.write_json(directory, "profile.json", self.actor_profile())
            matched = self.write_json(directory, "matched.json", {"login": "machine", "id": 101})
            wrong = self.write_json(directory, "wrong.json", {"login": "machine", "id": 999})
            code, output, _ = self.run_json([
                sys.executable,
                str(CORE / "verify_actor.py"),
                "--profile",
                str(profile),
                "--user-json",
                str(matched),
                "--allow-fixture",
            ])
            self.assertEqual(0, code)
            self.assertIsNone(output["candidate_head_sha"])
            self.assertEqual("ao_detector_test", output["decision_scope"])
            self.assertEqual("proceed", output["verdict"])

            code, output, _ = self.run_json([
                sys.executable,
                str(CORE / "verify_actor.py"),
                "--profile",
                str(profile),
                "--user-json",
                str(wrong),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("wrong_actor", output["findings"][0]["kind"])

            code, output, _ = self.run_json([
                sys.executable,
                str(CORE / "verify_actor.py"),
                "--profile",
                str(profile),
                "--user-json",
                str(matched),
            ])
            self.assertEqual(2, code)
            self.assertEqual("fixture_not_authoritative", output["findings"][0]["kind"])

    def test_actor_contract_rejects_fixture_fields_and_same_account_profile(self) -> None:
        profile = self.actor_profile_object()
        live = {
            "decision_scope": "ao_actor_observation",
            "operation_class": "commit",
            "candidate_head_sha": None,
            "actor_role": "machine_actor",
            "observed_at": "2026-07-20T00:00:00Z",
            "observed_actor": {"login": "machine", "id": 101},
            "expected_actor": {"login": "machine", "id": 101},
            "observation_source": "live_github_api",
            "live_actor_verified": True,
            "findings": [],
            "verdict": "proceed",
            "authority": "none",
        }
        observation = ActorObservation.from_mapping(live, profile=profile)
        observation.validate_for(
            profile,
            operation_class="commit",
            candidate_head_sha=None,
        )

        invalid_values = (
            {**live, "decision_scope": "ao_detector_test"},
            {**live, "actor_role": "human_actor"},
            {**live, "observation_source": "fixture"},
            {**live, "live_actor_verified": False},
            {**live, "authority": "mutation"},
            {**live, "findings": [{"kind": "wrong_actor"}]},
        )
        for invalid in invalid_values:
            with self.assertRaises(ValueError):
                ActorObservation.from_mapping(invalid, profile=profile)

        same_account = self.actor_profile()
        same_account["human_actor"] = {"login": "machine", "id": 101}
        with self.assertRaises(ValueError):
            ActorProfile.from_mapping(same_account)

        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            profile_path = self.write_json(directory, "profile.json", same_account)
            observed = self.write_json(directory, "user.json", {"login": "machine", "id": 101})
            code, output, _ = self.run_json([
                sys.executable,
                str(CORE / "verify_actor.py"),
                "--profile",
                str(profile_path),
                "--user-json",
                str(observed),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("invalid_actor_profile", output["findings"][0]["kind"])

    def receipt_input(self, result: dict, *, required: bool, candidate: str | None = None) -> dict:
        value = {
            "operation": "sample_operation",
            "phase": "pre_handoff" if required else "task_recovery",
            "task_ref": ISSUE_URL,
            "implementation_version": "1",
            "source_ref": "https://github.com/example/project/actions/runs/9",
            "candidate_required": required,
            "result": result,
        }
        if candidate is not None:
            value["candidate_head_sha"] = candidate
            value["observed_head_sha"] = candidate
        return value

    def test_operation_receipt_preserves_result_and_binding_states(self) -> None:
        opaque_result = {
            "state": "halt",
            "next_action": "inspect_halt",
            "verdict": "repair_then_proceed",
            "authority": "none",
        }
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            code, receipt, _ = self.bind(
                directory,
                "not-applicable.json",
                self.receipt_input(opaque_result, required=False),
            )
            self.assertEqual(0, code)
            self.assertEqual("not_applicable", receipt["candidate_binding"]["status"])
            self.assertEqual(opaque_result, receipt["result"])
            self.assertNotIn("verdict", receipt)
            receipt_schema = json.loads(
                (SKILL / "references" / "operation-receipt.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(set(receipt_schema["required"]), set(receipt))

            candidate = "a" * 40
            code, receipt, _ = self.bind(
                directory,
                "bound.json",
                self.receipt_input(opaque_result, required=True, candidate=candidate),
            )
            self.assertEqual(0, code)
            self.assertEqual("bound", receipt["candidate_binding"]["status"])

            stale = self.receipt_input(opaque_result, required=True, candidate=candidate)
            stale["observed_head_sha"] = "b" * 40
            code, receipt, _ = self.bind(directory, "stale.json", stale)
            self.assertEqual(2, code)
            self.assertEqual("stale", receipt["candidate_binding"]["status"])
            self.assertEqual("stale_candidate", receipt["findings"][0]["kind"])

            unavailable = self.receipt_input(opaque_result, required=True)
            code, receipt, _ = self.bind(directory, "unavailable.json", unavailable)
            self.assertEqual(2, code)
            self.assertEqual("unavailable", receipt["candidate_binding"]["status"])

    def test_receipt_rejects_invalid_reference_without_echo(self) -> None:
        secret = "private-reference-value"
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            value = self.receipt_input({}, required=False)
            value["task_ref"] = secret
            source = self.write_json(directory, "invalid.json", value)
            completed = subprocess.run(
                [sys.executable, str(BINDER), str(source)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(2, completed.returncode)
            self.assertNotIn(secret, completed.stdout + completed.stderr)
            error = json.loads(completed.stdout)
            self.assertEqual(1, error["error_version"])
            self.assertEqual("operation_receipt_binding", error["decision_scope"])
            self.assertNotIn("receipt_version", error)
            error_schema = json.loads(
                (SKILL / "references" / "operation-receipt-error.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(set(error_schema["required"]), set(error))

            value = self.receipt_input({}, required=False)
            value["source_ref"] = "https://example.com/result?token=" + secret
            source = self.write_json(directory, "invalid-source.json", value)
            completed = subprocess.run(
                [sys.executable, str(BINDER), str(source)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(2, completed.returncode)
            self.assertNotIn(secret, completed.stdout + completed.stderr)
            error = json.loads(completed.stdout)
            self.assertEqual("invalid_input", error["error"])
            self.assertNotIn("candidate_binding", error)

    def fake_gtp(self, directory: Path) -> Path:
        return self.make_executable(
            directory,
            "gtp",
            """#!/usr/bin/env python3
import json
import os
import sys
if sys.argv[1:] == ["--version"]:
    print(os.environ.get("FAKE_GTP_VERSION", "1.0.1"))
    raise SystemExit(0)
mode = os.environ.get("FAKE_GTP_MODE", "halt")
if os.environ.get("FAKE_GTP_REQUIRE_TOKEN") == "1" and os.environ.get("GITHUB_TOKEN") != os.environ.get("FAKE_GTP_TOKEN"):
    raise SystemExit(8)
issue = sys.argv[2]
state = None if mode == "incomplete" else mode
print(json.dumps({
    "gtp": "1.0",
    "command": "status",
    "issue_url": issue,
    "state": state,
    "halt_reason": "invalid_binding" if mode == "halt" else None,
    "next_action": "retry_acquisition" if mode == "incomplete" else "inspect_halt" if mode == "halt" else "post_contract",
    "primary_url": issue,
    "authority": "none",
    "acquisition": "incomplete" if mode == "incomplete" else "complete"
}, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(2 if mode == "incomplete" else 0)
""",
        )

    def fake_gh(self, directory: Path) -> Path:
        return self.make_executable(
            directory,
            "gh",
            """#!/usr/bin/env python3
import json
import os
import sys
if sys.argv[1:] == ["api", "user"]:
    print(json.dumps({"login": "machine", "id": 101, "name": "Machine Account"}))
    raise SystemExit(0)
if sys.argv[1:] == ["auth", "token"]:
    print(os.environ["FAKE_GTP_TOKEN"])
    raise SystemExit(0)
raise SystemExit(9)
""",
        )

    def test_gtp_halt_and_acquisition_failure_remain_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            fake = self.fake_gtp(directory)
            environment = os.environ.copy()
            environment["FAKE_GTP_MODE"] = "halt"
            code, output, _ = self.run_json([
                sys.executable,
                str(GTP),
                "--issue-url",
                ISSUE_URL,
                "--gtp-command",
                str(fake),
            ], environment=environment)
            self.assertEqual(0, code)
            self.assertEqual("halt", output["gtp_projection"]["state"])

            environment["FAKE_GTP_MODE"] = "incomplete"
            code, output, _ = self.run_json([
                sys.executable,
                str(GTP),
                "--issue-url",
                ISSUE_URL,
                "--gtp-command",
                str(fake),
            ], environment=environment)
            self.assertEqual(2, code)
            self.assertEqual("acquisition_incomplete", output["findings"][0]["kind"])
            self.assertIsNone(output["gtp_projection"]["state"])

    def test_private_gtp_bridge_does_not_output_token(self) -> None:
        token = "private-test-token-value"
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            profile = self.write_json(directory, "profile.json", self.actor_profile())
            environment = os.environ.copy()
            environment.update({
                "FAKE_GTP_MODE": "unmanaged",
                "FAKE_GTP_REQUIRE_TOKEN": "1",
                "FAKE_GTP_TOKEN": token,
                "GH_TOKEN": "wrong-ambient-value",
                "GITHUB_TOKEN": "wrong-ambient-value",
            })
            completed = subprocess.run(
                [
                    sys.executable,
                    str(GTP),
                    "--issue-url",
                    ISSUE_URL,
                    "--gtp-command",
                    str(self.fake_gtp(directory)),
                    "--private",
                    "--profile",
                    str(profile),
                    "--gh-command",
                    str(self.fake_gh(directory)),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
                timeout=30,
            )
            self.assertEqual(0, completed.returncode)
            self.assertNotIn(token, completed.stdout + completed.stderr)
            self.assertNotIn("wrong-ambient-value", completed.stdout + completed.stderr)

    def test_publication_operation_does_not_echo_forbidden_values(self) -> None:
        secret = "ghp_abcdefghijklmnopqrstuvwx"
        local_path = "/Users/example/private/credential"
        with tempfile.TemporaryDirectory() as raw:
            unsafe = Path(raw) / "unsafe.md"
            unsafe.write_text(
                f"token={secret}\npath={local_path}\n"
                '"reasoning_transcript": "hidden"\n"session_id": "runtime-7"\n',
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(PUBLICATION), str(unsafe)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(2, completed.returncode)
            self.assertNotIn(secret, completed.stdout + completed.stderr)
            self.assertNotIn(local_path, completed.stdout + completed.stderr)
            output = json.loads(completed.stdout)
            self.assertEqual("publication_screening", output["decision_scope"])
            self.assertEqual(
                {"secret_value", "local_absolute_path", "private_context", "ephemeral_runtime_id"},
                {item["kind"] for item in output["findings"]},
            )

    def acceptance_input(self, directory: Path, candidate: str) -> Path:
        return self.write_json(
            directory,
            "acceptance.json",
            {
                "task_ref": ISSUE_URL,
                "candidate_head_sha": candidate,
                "pr_ref": "https://github.com/example/project/pull/8",
            },
        )

    def test_acceptance_readback_reports_native_states(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = self.acceptance_input(directory, candidate)
            profile = self.write_json(directory, "profile.json", self.actor_profile())
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
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--profile",
                str(profile),
                "--expected-profile-digest",
                self.profile_digest(profile),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(0, code)
            self.assertEqual("observed", output["acceptance_state"])
            self.assertNotIn("verdict", output)

            value = json.loads(pr.read_text(encoding="utf-8"))
            value["head"]["sha"] = "b" * 40
            pr.write_text(json.dumps(value), encoding="utf-8")
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--profile",
                str(profile),
                "--expected-profile-digest",
                self.profile_digest(profile),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("stale", output["acceptance_state"])

            value["head"]["sha"] = candidate
            value["merged_by"] = {"login": "service", "id": 303}
            pr.write_text(json.dumps(value), encoding="utf-8")
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--profile",
                str(profile),
                "--expected-profile-digest",
                self.profile_digest(profile),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("conflicting", output["acceptance_state"])

            value["merged_at"] = None
            value["merged_by"] = None
            pr.write_text(json.dumps(value), encoding="utf-8")
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--profile",
                str(profile),
                "--expected-profile-digest",
                self.profile_digest(profile),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("missing", output["acceptance_state"])
            self.assertEqual({"native_merge_missing"}, {item["kind"] for item in output["findings"]})

    def test_acceptance_fixture_is_never_live_evidence(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = self.acceptance_input(directory, candidate)
            profile = self.write_json(directory, "profile.json", self.actor_profile())
            pr = self.write_json(
                directory,
                "pr.json",
                {
                    "base": {"repo": {"full_name": "example/project"}},
                    "head": {"sha": candidate},
                    "merged_at": None,
                    "merged_by": None,
                },
            )
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--profile",
                str(profile),
                "--expected-profile-digest",
                self.profile_digest(profile),
                "--pr-json",
                str(pr),
            ])
            self.assertEqual(2, code)
            self.assertIn("fixture_not_authoritative", {item["kind"] for item in output["findings"]})
            self.assertEqual("unavailable", output["acceptance_state"])

    def test_acceptance_live_route_removes_ambient_tokens(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = self.acceptance_input(directory, candidate)
            profile = self.write_json(directory, "profile.json", self.actor_profile())
            fake_gh = self.make_executable(
                directory,
                "acceptance-gh",
                """#!/usr/bin/env python3
import json
import os
import sys
if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
    raise SystemExit(8)
if sys.argv[1:] == ["api", "repos/example/project/pulls/8"]:
    print(json.dumps({
        "base": {"repo": {"full_name": "example/project"}},
        "head": {"sha": os.environ["CANDIDATE"]},
        "merged_at": "2026-07-20T00:00:00Z",
        "merged_by": {"login": "human", "id": 202, "type": "User"}
    }))
    raise SystemExit(0)
raise SystemExit(9)
""",
            )
            environment = os.environ.copy()
            environment.update({
                "CANDIDATE": candidate,
                "GH_TOKEN": "ambient-value",
                "GITHUB_TOKEN": "ambient-value",
            })
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--profile",
                str(profile),
                "--expected-profile-digest",
                self.profile_digest(profile),
                "--gh-command",
                str(fake_gh),
            ], environment=environment)
            self.assertEqual(0, code)
            self.assertEqual("observed", output["acceptance_state"])
            self.assertEqual("live_github_api", output["observation_source"])

    def test_acceptance_rejects_request_actor_and_cross_repository_binding(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            profile = self.write_json(directory, "profile.json", self.actor_profile())
            source = self.write_json(
                directory,
                "acceptance.json",
                {
                    "task_ref": ISSUE_URL,
                    "candidate_head_sha": candidate,
                    "pr_ref": "https://github.com/other/project/pull/8",
                    "human_actor": {"login": "machine", "id": 101},
                },
            )
            pr = self.write_json(
                directory,
                "pr.json",
                {
                    "base": {"repo": {"full_name": "other/project"}},
                    "head": {"sha": candidate},
                    "merged_at": "2026-07-20T00:00:00Z",
                    "merged_by": {"login": "machine", "id": 101},
                },
            )
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--profile",
                str(profile),
                "--expected-profile-digest",
                self.profile_digest(profile),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("unavailable", output["acceptance_state"])
            kinds = {item["kind"] for item in output["findings"]}
            self.assertIn("request_human_actor_forbidden", kinds)
            self.assertIn("cross_repository_binding", kinds)

    def test_acceptance_rejects_native_base_repository_mismatch(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = self.acceptance_input(directory, candidate)
            profile = self.write_json(directory, "profile.json", self.actor_profile())
            pr = self.write_json(
                directory,
                "pr.json",
                {
                    "base": {"repo": {"full_name": "other/project"}},
                    "head": {"sha": candidate},
                    "merged_at": "2026-07-20T00:00:00Z",
                    "merged_by": {"login": "human", "id": 202},
                },
            )
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--profile",
                str(profile),
                "--expected-profile-digest",
                self.profile_digest(profile),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("unavailable", output["acceptance_state"])
            self.assertIn("pr_repository_mismatch", {item["kind"] for item in output["findings"]})

    def test_acceptance_requires_the_invocation_profile_digest(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = self.acceptance_input(directory, candidate)
            profile = self.write_json(directory, "profile.json", self.actor_profile())
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
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--profile",
                str(profile),
                "--expected-profile-digest",
                "f" * 64,
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("unavailable", output["acceptance_state"])
            self.assertIn("actor_profile_mismatch", {item["kind"] for item in output["findings"]})
            self.assertNotIn("profile_digest", json.dumps(output))

    def test_generic_command_executor_is_absent(self) -> None:
        self.assertFalse((SKILL / "scripts" / "verify_wiring_evidence.py").exists())
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("verify_wiring_evidence.py", skill)
        for script in (SKILL / "scripts").rglob("*.py"):
            source = script.read_text(encoding="utf-8")
            self.assertNotIn("acquisition.command", source, script)
            self.assertNotIn("subprocess.run(\n                        command", source, script)

    def test_skill_bundle_is_repository_neutral(self) -> None:
        origin = subprocess.run(
            ("git", "config", "--get", "remote.origin.url"),
            check=False,
            capture_output=True,
            text=True,
            cwd=REPOSITORY,
        ).stdout.strip()
        identity = origin.removesuffix(".git").rsplit("/", 2)[-2:]
        identity_text = "/".join(identity) if len(identity) == 2 else ""
        for path in SKILL.rglob("*"):
            if (
                not path.is_file()
                or "tests" in path.parts
                or path.suffix not in {".json", ".md", ".py", ".yaml", ".yml"}
            ):
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("TODO", source, path)
            self.assertNotIn(str(REPOSITORY), source, path)
            if identity_text:
                self.assertNotIn(identity_text, source, path)

    def test_schema_and_domain_language_define_hub_boundary(self) -> None:
        schema = json.loads(
            (SKILL / "references" / "operation-receipt.schema.json").read_text(encoding="utf-8")
        )
        error_schema = json.loads(
            (SKILL / "references" / "operation-receipt-error.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("verdict", schema["properties"])
        self.assertFalse(error_schema["additionalProperties"])
        self.assertNotIn("receipt_version", error_schema["properties"])
        self.assertEqual("invalid_input", error_schema["properties"]["error"]["const"])
        context = (REPOSITORY / "CONTEXT.md").read_text(encoding="utf-8")
        for term in (
            "AO Core",
            "Operation",
            "Adapter",
            "Operation Receipt",
            "Actor Observation",
            "Candidate Binding",
            "Projection Batch",
            "Invocation Context",
            "GitHub Mutation Gate",
        ):
            self.assertIn(f"**{term}**", context)
        for implementation_term in ("scripts/", "bind_operation_result.py", "recover.py"):
            self.assertNotIn(implementation_term, context)

    def test_all_relative_markdown_links_resolve(self) -> None:
        link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for markdown in REPOSITORY.rglob("*.md"):
            source = markdown.read_text(encoding="utf-8")
            for target in link.findall(source):
                if target.startswith(("http://", "https://", "#", "<")):
                    continue
                relative = target.split("#", 1)[0]
                if relative:
                    self.assertTrue((markdown.parent / relative).resolve().exists(), f"{markdown}: {target}")


if __name__ == "__main__":
    unittest.main()
