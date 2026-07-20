"""Enforce invocation-local AO transitions around real callbacks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Callable, Mapping, TypeVar

from actor_contract import ActorObservation, ActorProfile, FULL_DIGEST, FULL_SHA
from internal_policy_gate import (
    GateDecision,
    GateFinding,
    GateStatus,
    InternalPolicyGate,
    ProjectionArtifact,
    ProjectionBatch,
)


ISSUE_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*$")
T = TypeVar("T")


class TransitionBlocked(RuntimeError):
    def __init__(self, findings: tuple[GateFinding, ...]) -> None:
        super().__init__("AO transition blocked")
        self.findings = findings


class PublicOperationBlocked(RuntimeError):
    def __init__(self, result: Mapping[str, object]) -> None:
        super().__init__("public operation blocked publication")
        self.result = dict(result)


def require_proceed(decision: GateDecision) -> None:
    if not isinstance(decision, GateDecision):
        raise TypeError("decision must be GateDecision")
    if decision.status is GateStatus.BLOCKED:
        raise TransitionBlocked(decision.findings)


def _canonical_json(value: Mapping[str, object]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("checked values must be mappings")
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise TypeError("checked values must be JSON-compatible") from error


def _frame(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


@dataclass(frozen=True)
class PlanDraft:
    plan_json: str
    publication_artifact: ProjectionArtifact

    def __post_init__(self) -> None:
        try:
            plan = json.loads(self.plan_json)
        except json.JSONDecodeError as error:
            raise ValueError("plan JSON is invalid") from error
        if not isinstance(plan, dict):
            raise TypeError("plan must be an object")
        if not isinstance(self.publication_artifact, ProjectionArtifact):
            raise TypeError("publication_artifact must be ProjectionArtifact")
        if self.publication_artifact.target_ref != "PLAN_BODY":
            raise ValueError("plan publication artifact must target PLAN_BODY")

    @classmethod
    def build(
        cls,
        *,
        plan: Mapping[str, object],
        publication_artifact: ProjectionArtifact,
    ) -> "PlanDraft":
        return cls(_canonical_json(plan), publication_artifact)

    @property
    def plan(self) -> dict[str, object]:
        return json.loads(self.plan_json)


@dataclass(frozen=True)
class CheckedPlan:
    task_ref: str
    task_projection_json: str
    plan_json: str
    publication_artifact: ProjectionArtifact
    digest: str

    def __post_init__(self) -> None:
        if ISSUE_URL.fullmatch(self.task_ref) is None:
            raise ValueError("task_ref must be a canonical GitHub Issue URL")
        try:
            task_projection = json.loads(self.task_projection_json)
            plan = json.loads(self.plan_json)
        except json.JSONDecodeError as error:
            raise ValueError("checked plan JSON is invalid") from error
        if not isinstance(task_projection, dict) or not isinstance(plan, dict):
            raise TypeError("checked plan values must be objects")
        if not isinstance(self.publication_artifact, ProjectionArtifact):
            raise TypeError("publication_artifact must be ProjectionArtifact")
        self.validate_digest()

    @classmethod
    def build(
        cls,
        *,
        task_ref: str,
        task_projection: Mapping[str, object],
        draft: PlanDraft,
    ) -> "CheckedPlan":
        if ISSUE_URL.fullmatch(task_ref) is None:
            raise ValueError("task_ref must be a canonical GitHub Issue URL")
        if not isinstance(draft, PlanDraft):
            raise TypeError("draft must be PlanDraft")
        projection_json = _canonical_json(task_projection)
        digest = cls.compute_digest(
            task_ref,
            projection_json,
            draft.plan_json,
            draft.publication_artifact,
        )
        return cls(
            task_ref,
            projection_json,
            draft.plan_json,
            draft.publication_artifact,
            digest,
        )

    def validate_digest(self) -> None:
        if self.digest != self.compute_digest(
            self.task_ref,
            self.task_projection_json,
            self.plan_json,
            self.publication_artifact,
        ):
            raise ValueError("checked plan digest does not match its content")

    @staticmethod
    def compute_digest(
        task_ref: str,
        task_projection_json: str,
        plan_json: str,
        publication_artifact: ProjectionArtifact,
    ) -> str:
        return hashlib.sha256(
            _frame(task_ref.encode("utf-8"))
            + _frame(task_projection_json.encode("utf-8"))
            + _frame(plan_json.encode("utf-8"))
            + _frame(publication_artifact.artifact_id.encode("ascii"))
            + _frame(publication_artifact.target_ref.encode("utf-8"))
            + _frame(publication_artifact.content)
        ).hexdigest()

    @property
    def task_projection(self) -> dict[str, object]:
        return json.loads(self.task_projection_json)

    @property
    def plan(self) -> dict[str, object]:
        return json.loads(self.plan_json)


@dataclass(frozen=True)
class InvocationContext:
    checked_plan: CheckedPlan
    actor_profile_digest: str
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.checked_plan, CheckedPlan):
            raise TypeError("checked_plan must be CheckedPlan")
        if not isinstance(self.actor_profile_digest, str) or FULL_DIGEST.fullmatch(
            self.actor_profile_digest
        ) is None:
            raise ValueError("actor_profile_digest is invalid")
        self.validate_digest()

    @classmethod
    def build(cls, checked_plan: CheckedPlan, profile: ActorProfile) -> "InvocationContext":
        if not isinstance(profile, ActorProfile):
            raise TypeError("profile must be ActorProfile")
        digest = cls.compute_digest(checked_plan.digest, profile.digest)
        return cls(checked_plan, profile.digest, digest)

    @staticmethod
    def compute_digest(checked_plan_digest: str, actor_profile_digest: str) -> str:
        return hashlib.sha256(
            _frame(checked_plan_digest.encode("ascii"))
            + _frame(actor_profile_digest.encode("ascii"))
        ).hexdigest()

    def validate_digest(self) -> None:
        self.checked_plan.validate_digest()
        if self.digest != self.compute_digest(
            self.checked_plan.digest,
            self.actor_profile_digest,
        ):
            raise ValueError("invocation context digest does not match its content")

    @property
    def task_ref(self) -> str:
        return self.checked_plan.task_ref


@dataclass(frozen=True)
class CheckedCandidate:
    invocation_digest: str
    task_ref: str
    candidate_head_sha: str

    def __post_init__(self) -> None:
        if FULL_DIGEST.fullmatch(self.invocation_digest) is None:
            raise ValueError("invocation_digest is invalid")
        if ISSUE_URL.fullmatch(self.task_ref) is None:
            raise ValueError("task_ref must be a canonical GitHub Issue URL")
        if FULL_SHA.fullmatch(self.candidate_head_sha) is None:
            raise ValueError("candidate_head_sha must be a full lowercase commit SHA")


@dataclass(frozen=True)
class HandoffReady:
    candidate: CheckedCandidate

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CheckedCandidate):
            raise TypeError("candidate must be CheckedCandidate")


@dataclass(frozen=True)
class ProjectionRequest:
    task_ref: str
    checked_plan_digest: str
    candidate_head_sha: str | None

    def __post_init__(self) -> None:
        if ISSUE_URL.fullmatch(self.task_ref) is None:
            raise ValueError("task_ref must be a canonical GitHub Issue URL")
        if FULL_DIGEST.fullmatch(self.checked_plan_digest) is None:
            raise ValueError("checked_plan_digest is invalid")
        if self.candidate_head_sha is not None and FULL_SHA.fullmatch(
            self.candidate_head_sha
        ) is None:
            raise ValueError("candidate_head_sha is invalid")


class TransitionCoordinator:
    def __init__(
        self,
        gate: InternalPolicyGate,
        *,
        actor_profile: ActorProfile,
        recover_task: Callable[[str], Mapping[str, object]],
        build_plan: Callable[[Mapping[str, object]], PlanDraft],
        observe_actor: Callable[[str, str | None], ActorObservation],
        batch_source: Callable[[ProjectionRequest], ProjectionBatch],
        screening: Callable[[ProjectionBatch], Mapping[str, object]],
        publisher: Callable[[ProjectionBatch], object],
    ) -> None:
        if not isinstance(gate, InternalPolicyGate):
            raise TypeError("gate must be InternalPolicyGate")
        if not isinstance(actor_profile, ActorProfile):
            raise TypeError("actor_profile must be ActorProfile")
        for name, dependency in (
            ("recover_task", recover_task),
            ("build_plan", build_plan),
            ("observe_actor", observe_actor),
            ("batch_source", batch_source),
            ("screening", screening),
            ("publisher", publisher),
        ):
            if not callable(dependency):
                raise TypeError(f"{name} must be callable")
        self._gate = gate
        self._actor_profile = actor_profile
        self._recover_task = recover_task
        self._build_plan = build_plan
        self._observe_actor = observe_actor
        self._batch_source = batch_source
        self._screening = screening
        self._publisher = publisher
        self._context: InvocationContext | None = None
        self._checked_candidates: dict[str, CheckedCandidate] = {}

    def prepare_plan(self, *, task_ref: str) -> InvocationContext:
        try:
            task_projection = self._recover_task(task_ref)
        except Exception:
            raise TransitionBlocked(self._fixed_finding("task_recovery_unavailable")) from None
        if not isinstance(task_projection, Mapping):
            raise TransitionBlocked(self._fixed_finding("task_recovery_unavailable"))
        try:
            draft = self._build_plan(task_projection)
        except Exception:
            raise TransitionBlocked(self._fixed_finding("plan_build_unavailable")) from None
        if not isinstance(draft, PlanDraft):
            raise TransitionBlocked(self._fixed_finding("plan_build_unavailable"))
        checked = CheckedPlan.build(
            task_ref=task_ref,
            task_projection=task_projection,
            draft=draft,
        )
        require_proceed(
            self._gate.check_plan(
                task_ref=task_ref,
                task_projection=checked.task_projection,
                plan=checked.plan,
                publication_artifact=checked.publication_artifact,
            )
        )
        context = InvocationContext.build(checked, self._actor_profile)
        self._context = context
        self._checked_candidates.clear()
        return context

    def run_github_mutation(
        self,
        context: InvocationContext,
        *,
        operation_class: str,
        mutation: Callable[[], T],
        candidate_head_sha: str | None = None,
    ) -> T:
        self._require_current_context(context)
        if not callable(mutation):
            raise TypeError("mutation must be callable")
        try:
            observation = self._observe_actor(operation_class, candidate_head_sha)
        except Exception:
            raise TransitionBlocked(self._fixed_finding("actor_observation_unavailable")) from None
        if not isinstance(observation, ActorObservation):
            raise TransitionBlocked(self._fixed_finding("actor_observation_failed"))
        try:
            observation.validate_for(
                self._actor_profile,
                operation_class=operation_class,
                candidate_head_sha=candidate_head_sha,
            )
        except (TypeError, ValueError):
            raise TransitionBlocked(self._fixed_finding("actor_observation_failed")) from None
        return mutation()

    def check_candidate(
        self,
        context: InvocationContext,
        *,
        candidate_head_sha: str,
        observations: Mapping[str, object],
    ) -> CheckedCandidate:
        self._require_current_context(context)
        require_proceed(
            self._gate.check_candidate(
                task_ref=context.task_ref,
                candidate_head_sha=candidate_head_sha,
                observations=observations,
            )
        )
        candidate = CheckedCandidate(context.digest, context.task_ref, candidate_head_sha)
        self._checked_candidates[candidate_head_sha] = candidate
        return candidate

    def publish_plan(
        self,
        context: InvocationContext,
    ) -> tuple[dict[str, object], object]:
        self._require_current_context(context)
        batch = ProjectionBatch.build(
            checked_plan_digest=context.checked_plan.digest,
            candidate_head_sha=None,
            artifacts=(context.checked_plan.publication_artifact,),
        )
        return self._publish_batch(context, batch, operation_class="plan_publication")

    def publish_projection(
        self,
        context: InvocationContext,
        *,
        candidate: CheckedCandidate | None,
    ) -> tuple[dict[str, object], object]:
        self._require_current_context(context)
        candidate_head_sha = None
        if candidate is not None:
            self._require_candidate(context, candidate)
            candidate_head_sha = candidate.candidate_head_sha
        request = ProjectionRequest(
            task_ref=context.task_ref,
            checked_plan_digest=context.checked_plan.digest,
            candidate_head_sha=candidate_head_sha,
        )
        try:
            batch = self._batch_source(request)
        except Exception:
            raise TransitionBlocked(self._fixed_finding("projection_batch_unavailable")) from None
        if not isinstance(batch, ProjectionBatch):
            raise TransitionBlocked(self._fixed_finding("projection_batch_unavailable"))
        if batch.candidate_head_sha != candidate_head_sha:
            raise TransitionBlocked(self._fixed_finding("projection_candidate_mismatch"))
        if batch.checked_plan_digest != context.checked_plan.digest:
            raise TransitionBlocked(self._fixed_finding("projection_plan_mismatch"))
        return self._publish_batch(
            context,
            batch,
            operation_class="projection_publication",
        )

    def prepare_handoff(
        self,
        context: InvocationContext,
        *,
        candidate: CheckedCandidate,
        observations: Mapping[str, object],
    ) -> HandoffReady:
        self._require_current_context(context)
        self._require_candidate(context, candidate)
        require_proceed(
            self._gate.check_candidate(
                task_ref=context.task_ref,
                candidate_head_sha=candidate.candidate_head_sha,
                observations=observations,
            )
        )
        return HandoffReady(candidate)

    def _publish_batch(
        self,
        context: InvocationContext,
        batch: ProjectionBatch,
        *,
        operation_class: str,
    ) -> tuple[dict[str, object], object]:
        self._require_current_context(context)
        if batch.checked_plan_digest != context.checked_plan.digest:
            raise TransitionBlocked(self._fixed_finding("projection_plan_mismatch"))
        try:
            batch.validate_digest()
        except ValueError:
            raise TransitionBlocked(self._fixed_finding("projection_digest_mismatch")) from None
        require_proceed(self._gate.check_projection(task_ref=context.task_ref, batch=batch))
        try:
            result = self._screening(batch)
        except Exception:
            raise PublicOperationBlocked({}) from None
        if not isinstance(result, Mapping) or result.get("verdict") != "proceed":
            native_result = dict(result) if isinstance(result, Mapping) else {}
            raise PublicOperationBlocked(native_result)
        try:
            batch.validate_digest()
        except ValueError:
            raise TransitionBlocked(self._fixed_finding("projection_digest_mismatch")) from None
        published = self.run_github_mutation(
            context,
            operation_class=operation_class,
            candidate_head_sha=batch.candidate_head_sha,
            mutation=lambda: self._publisher(batch),
        )
        return dict(result), published

    def _require_current_context(self, context: InvocationContext) -> None:
        if not isinstance(context, InvocationContext) or self._context is not context:
            raise TransitionBlocked(self._fixed_finding("plan_not_checked"))
        try:
            context.validate_digest()
        except ValueError:
            raise TransitionBlocked(self._fixed_finding("plan_digest_mismatch")) from None
        if context.actor_profile_digest != self._actor_profile.digest:
            raise TransitionBlocked(self._fixed_finding("actor_profile_mismatch"))

    def _require_candidate(
        self,
        context: InvocationContext,
        candidate: CheckedCandidate,
    ) -> None:
        if not isinstance(candidate, CheckedCandidate) or (
            candidate.invocation_digest != context.digest
            or candidate.task_ref != context.task_ref
            or self._checked_candidates.get(candidate.candidate_head_sha) is not candidate
        ):
            raise TransitionBlocked(self._fixed_finding("candidate_context_mismatch"))

    @staticmethod
    def _fixed_finding(code: str) -> tuple[GateFinding, ...]:
        return (
            GateFinding(
                code=code,
                message="必要なtransition preconditionを確認できませんでした",
            ),
        )
