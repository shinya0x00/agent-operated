"""Enforce invocation-local AO transitions around real callbacks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Callable, Mapping, TypeVar

from internal_policy_gate import (
    GateDecision,
    GateFinding,
    GateStatus,
    InternalPolicyGate,
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


@dataclass(frozen=True)
class CheckedPlan:
    task_ref: str
    task_projection_json: str
    plan_json: str
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
        self.validate_digest()

    @classmethod
    def build(
        cls,
        *,
        task_ref: str,
        task_projection: Mapping[str, object],
        plan: Mapping[str, object],
    ) -> "CheckedPlan":
        if ISSUE_URL.fullmatch(task_ref) is None:
            raise ValueError("task_ref must be a canonical GitHub Issue URL")
        projection_json = cls._canonical_json(task_projection)
        plan_json = cls._canonical_json(plan)
        digest = cls.compute_digest(task_ref, projection_json, plan_json)
        return cls(task_ref, projection_json, plan_json, digest)

    def validate_digest(self) -> None:
        if self.digest != self.compute_digest(
            self.task_ref,
            self.task_projection_json,
            self.plan_json,
        ):
            raise ValueError("checked plan digest does not match its content")

    @classmethod
    def compute_digest(cls, task_ref: str, task_projection_json: str, plan_json: str) -> str:
        return hashlib.sha256(
            cls._frame(task_ref.encode("utf-8"))
            + cls._frame(task_projection_json.encode("utf-8"))
            + cls._frame(plan_json.encode("utf-8"))
        ).hexdigest()

    @property
    def task_projection(self) -> dict[str, object]:
        return json.loads(self.task_projection_json)

    @property
    def plan(self) -> dict[str, object]:
        return json.loads(self.plan_json)

    @staticmethod
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

    @staticmethod
    def _frame(value: bytes) -> bytes:
        return len(value).to_bytes(8, "big") + value


class TransitionCoordinator:
    def __init__(
        self,
        gate: InternalPolicyGate,
        *,
        recover_task: Callable[[str], Mapping[str, object]],
        build_plan: Callable[[Mapping[str, object]], Mapping[str, object]],
        observe_actor: Callable[[], object],
        batch_source: Callable[[str | None], ProjectionBatch],
        screening: Callable[[ProjectionBatch], Mapping[str, object]],
        publisher: Callable[[ProjectionBatch], object],
    ) -> None:
        if not isinstance(gate, InternalPolicyGate):
            raise TypeError("gate must be InternalPolicyGate")
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
        self._recover_task = recover_task
        self._build_plan = build_plan
        self._observe_actor = observe_actor
        self._batch_source = batch_source
        self._screening = screening
        self._publisher = publisher
        self._checked_plan: CheckedPlan | None = None

    def prepare_plan(self, *, task_ref: str) -> CheckedPlan:
        try:
            task_projection = self._recover_task(task_ref)
        except Exception:
            raise TransitionBlocked(self._fixed_finding("task_recovery_unavailable")) from None
        if not isinstance(task_projection, Mapping):
            raise TransitionBlocked(self._fixed_finding("task_recovery_unavailable"))
        try:
            plan = self._build_plan(task_projection)
        except Exception:
            raise TransitionBlocked(self._fixed_finding("plan_build_unavailable")) from None
        if not isinstance(plan, Mapping):
            raise TransitionBlocked(self._fixed_finding("plan_build_unavailable"))
        checked = CheckedPlan.build(
            task_ref=task_ref,
            task_projection=task_projection,
            plan=plan,
        )
        require_proceed(
            self._gate.check_plan(
                task_ref=task_ref,
                task_projection=checked.task_projection,
                plan=checked.plan,
            )
        )
        self._checked_plan = checked
        return checked

    def publish_plan(self, checked_plan: CheckedPlan) -> tuple[dict[str, object], object]:
        self._require_current_plan(checked_plan)
        return self.publish_projection(
            task_ref=checked_plan.task_ref,
            candidate_head_sha=None,
        )

    def run_first_mutation(
        self,
        checked_plan: CheckedPlan,
        *,
        mutation: Callable[[], T],
    ) -> T:
        self._require_current_plan(checked_plan)
        try:
            observation = self._observe_actor()
        except Exception:
            raise TransitionBlocked(self._fixed_finding("actor_observation_unavailable")) from None
        proceeded = observation is True or (
            isinstance(observation, Mapping) and observation.get("verdict") == "proceed"
        )
        if not proceeded:
            raise TransitionBlocked(self._fixed_finding("actor_observation_failed"))
        return mutation()

    def continue_candidate(
        self,
        *,
        task_ref: str,
        candidate_head_sha: str,
        observations: Mapping[str, object],
        callback: Callable[[], T],
    ) -> T:
        require_proceed(
            self._gate.check_candidate(
                task_ref=task_ref,
                candidate_head_sha=candidate_head_sha,
                observations=observations,
            )
        )
        return callback()

    def publish_projection(
        self,
        *,
        task_ref: str,
        candidate_head_sha: str | None,
    ) -> tuple[dict[str, object], object]:
        try:
            batch = self._batch_source(candidate_head_sha)
        except Exception:
            raise TransitionBlocked(self._fixed_finding("projection_batch_unavailable")) from None
        if not isinstance(batch, ProjectionBatch):
            raise TransitionBlocked(self._fixed_finding("projection_batch_unavailable"))
        if batch.candidate_head_sha != candidate_head_sha:
            raise TransitionBlocked(self._fixed_finding("projection_candidate_mismatch"))
        batch.validate_digest()
        require_proceed(self._gate.check_projection(task_ref=task_ref, batch=batch))
        try:
            result = self._screening(batch)
        except Exception:
            raise PublicOperationBlocked({}) from None
        if not isinstance(result, Mapping) or result.get("verdict") != "proceed":
            native_result = dict(result) if isinstance(result, Mapping) else {}
            raise PublicOperationBlocked(native_result)
        batch.validate_digest()
        published = self._publisher(batch)
        return dict(result), published

    def handoff(
        self,
        *,
        task_ref: str,
        candidate_head_sha: str,
        observations: Mapping[str, object],
        callback: Callable[[], T],
    ) -> T:
        return self.continue_candidate(
            task_ref=task_ref,
            candidate_head_sha=candidate_head_sha,
            observations=observations,
            callback=callback,
        )

    def _require_current_plan(self, checked_plan: CheckedPlan) -> None:
        if not isinstance(checked_plan, CheckedPlan) or self._checked_plan != checked_plan:
            raise TransitionBlocked(self._fixed_finding("plan_not_checked"))
        try:
            checked_plan.validate_digest()
        except ValueError:
            raise TransitionBlocked(self._fixed_finding("plan_digest_mismatch")) from None

    @staticmethod
    def _fixed_finding(code: str) -> tuple[GateFinding, ...]:
        return (GateFinding(code=code, message="必要なtransition preconditionを確認できませんでした"),)
