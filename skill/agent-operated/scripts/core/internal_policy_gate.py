"""Invocation-local port for host-controlled policy checks.

The host supplies the provider as an in-process object. AO does not resolve a
provider from task input, environment variables, filesystem paths, or command
arguments, and this module deliberately exposes no CLI or serialization API.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Mapping, Protocol, Sequence


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
FINDING_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class GateStatus(str, Enum):
    PROCEED = "proceed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class GateFinding:
    """A source-neutral finding expressed in the target's vocabulary."""

    code: str
    message: str
    target_ref: str | None = None

    def __post_init__(self) -> None:
        if FINDING_CODE.fullmatch(self.code) is None:
            raise ValueError("finding code must use target-native snake_case")
        if not self.message.strip():
            raise ValueError("finding message must not be empty")
        if self.target_ref is not None and not self.target_ref.strip():
            raise ValueError("target_ref must not be empty when present")


@dataclass(frozen=True)
class GateDecision:
    """Ephemeral transition decision; it is not an Operation result."""

    status: GateStatus
    findings: tuple[GateFinding, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise TypeError("status must be GateStatus")
        if not isinstance(self.findings, tuple) or not all(
            isinstance(item, GateFinding) for item in self.findings
        ):
            raise TypeError("findings must be a tuple of GateFinding values")
        if self.status is GateStatus.PROCEED and self.findings:
            raise ValueError("proceed must not carry blocking findings")
        if self.status is GateStatus.BLOCKED and not self.findings:
            raise ValueError("blocked requires at least one target-native finding")


@dataclass(frozen=True)
class PlanCheckRequest:
    task_ref: str
    plan: Mapping[str, object]


@dataclass(frozen=True)
class CandidateCheckRequest:
    task_ref: str
    candidate_head_sha: str
    observations: Mapping[str, object]


@dataclass(frozen=True)
class ProjectionArtifact:
    target_ref: str
    content: str


@dataclass(frozen=True)
class ProjectionCheckRequest:
    task_ref: str
    artifacts: tuple[ProjectionArtifact, ...]


class InternalPolicyProvider(Protocol):
    """Implemented and selected by the host, outside task-controlled input."""

    def check_plan(self, request: PlanCheckRequest) -> GateDecision: ...

    def check_candidate(self, request: CandidateCheckRequest) -> GateDecision: ...

    def check_projection(self, request: ProjectionCheckRequest) -> GateDecision: ...


class InternalPolicyGate:
    """Validate requests and delegate them to one host-supplied provider."""

    def __init__(self, provider: InternalPolicyProvider) -> None:
        for method in ("check_plan", "check_candidate", "check_projection"):
            if not callable(getattr(provider, method, None)):
                raise TypeError(f"provider must implement {method}")
        self._provider = provider

    def check_plan(self, *, task_ref: str, plan: Mapping[str, object]) -> GateDecision:
        self._require_task_ref(task_ref)
        if not isinstance(plan, Mapping):
            raise TypeError("plan must be a mapping")
        return self._require_decision(
            self._provider.check_plan(PlanCheckRequest(task_ref=task_ref, plan=plan))
        )

    def check_candidate(
        self,
        *,
        task_ref: str,
        candidate_head_sha: str,
        observations: Mapping[str, object],
    ) -> GateDecision:
        self._require_task_ref(task_ref)
        if FULL_SHA.fullmatch(candidate_head_sha) is None:
            raise ValueError("candidate_head_sha must be a full lowercase commit SHA")
        if not isinstance(observations, Mapping):
            raise TypeError("observations must be a mapping")
        return self._require_decision(
            self._provider.check_candidate(
                CandidateCheckRequest(
                    task_ref=task_ref,
                    candidate_head_sha=candidate_head_sha,
                    observations=observations,
                )
            )
        )

    def check_projection(
        self,
        *,
        task_ref: str,
        artifacts: Sequence[ProjectionArtifact],
    ) -> GateDecision:
        self._require_task_ref(task_ref)
        normalized = tuple(artifacts)
        if not normalized:
            raise ValueError("artifacts must not be empty")
        if not all(isinstance(item, ProjectionArtifact) for item in normalized):
            raise TypeError("artifacts must contain ProjectionArtifact values")
        if any(not item.target_ref.strip() for item in normalized):
            raise ValueError("artifact target_ref must not be empty")
        return self._require_decision(
            self._provider.check_projection(
                ProjectionCheckRequest(task_ref=task_ref, artifacts=normalized)
            )
        )

    @staticmethod
    def _require_task_ref(task_ref: str) -> None:
        if not isinstance(task_ref, str) or not task_ref.strip():
            raise ValueError("task_ref must not be empty")

    @staticmethod
    def _require_decision(value: object) -> GateDecision:
        if not isinstance(value, GateDecision):
            raise TypeError("provider must return GateDecision")
        return value
