"""Invocation-local port for host-controlled policy checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from pathlib import PurePosixPath
import re
from typing import Callable, Mapping, Protocol, Sequence


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
FULL_DIGEST = re.compile(r"^[0-9a-f]{64}$")
FINDING_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ARTIFACT_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
CLOSED_TARGET_REFS = {
    "PLAN_BODY",
    "PR_BODY",
    "ISSUE_BODY",
    "ISSUE_COMMENT",
    "PR_COMMENT",
}


def require_public_target_ref(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("target_ref must be a non-empty canonical value")
    if value in CLOSED_TARGET_REFS:
        return
    if (
        "\\" in value
        or "?" in value
        or "#" in value
        or URI_SCHEME.match(value)
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("target_ref is not public-safe")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value.endswith("/")
        or str(path) != value
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("target_ref must be a repository-relative POSIX path")


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
        if not isinstance(self.code, str) or FINDING_CODE.fullmatch(self.code) is None:
            raise ValueError("finding code must use target-native snake_case")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("finding message must not be empty")
        if self.target_ref is not None:
            require_public_target_ref(self.target_ref)


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
    task_projection: Mapping[str, object]
    plan: Mapping[str, object]
    publication_artifact: "ProjectionArtifact"


@dataclass(frozen=True)
class CandidateCheckRequest:
    task_ref: str
    candidate_head_sha: str
    observations: Mapping[str, object]


@dataclass(frozen=True)
class ProjectionArtifact:
    artifact_id: str
    target_ref: str
    content: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or ARTIFACT_ID.fullmatch(self.artifact_id) is None:
            raise ValueError("artifact_id must be an opaque snake_case identifier")
        require_public_target_ref(self.target_ref)
        if not isinstance(self.content, bytes):
            raise TypeError("content must be bytes")


@dataclass(frozen=True)
class ProjectionBatch:
    checked_plan_digest: str
    candidate_head_sha: str | None
    artifacts: tuple[ProjectionArtifact, ...]
    digest: str

    @classmethod
    def build(
        cls,
        *,
        checked_plan_digest: str,
        candidate_head_sha: str | None,
        artifacts: Sequence[ProjectionArtifact],
    ) -> "ProjectionBatch":
        normalized = tuple(artifacts)
        return cls(
            checked_plan_digest=checked_plan_digest,
            candidate_head_sha=candidate_head_sha,
            artifacts=normalized,
            digest=cls.compute_digest(checked_plan_digest, candidate_head_sha, normalized),
        )

    def __post_init__(self) -> None:
        if not isinstance(self.checked_plan_digest, str) or FULL_DIGEST.fullmatch(
            self.checked_plan_digest
        ) is None:
            raise ValueError("checked_plan_digest must be a lowercase SHA-256 value")
        if self.candidate_head_sha is not None and (
            not isinstance(self.candidate_head_sha, str)
            or FULL_SHA.fullmatch(self.candidate_head_sha) is None
        ):
            raise ValueError("candidate_head_sha must be a full lowercase commit SHA")
        if not isinstance(self.artifacts, tuple) or not self.artifacts:
            raise ValueError("artifacts must be a non-empty tuple")
        if not all(isinstance(item, ProjectionArtifact) for item in self.artifacts):
            raise TypeError("artifacts must contain ProjectionArtifact values")
        artifact_ids = [item.artifact_id for item in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("artifact_id values must be unique")
        if not isinstance(self.digest, str) or FULL_DIGEST.fullmatch(self.digest) is None:
            raise ValueError("digest must be a lowercase SHA-256 value")
        if self.digest != self.compute_digest(
            self.checked_plan_digest,
            self.candidate_head_sha,
            self.artifacts,
        ):
            raise ValueError("projection batch digest does not match its content")

    def validate_digest(self) -> None:
        if self.digest != self.compute_digest(
            self.checked_plan_digest,
            self.candidate_head_sha,
            self.artifacts,
        ):
            raise ValueError("projection batch digest does not match its content")

    @staticmethod
    def compute_digest(
        checked_plan_digest: str,
        candidate_head_sha: str | None,
        artifacts: Sequence[ProjectionArtifact],
    ) -> str:
        digest = hashlib.sha256()

        def add(value: bytes) -> None:
            digest.update(len(value).to_bytes(8, "big"))
            digest.update(value)

        add(checked_plan_digest.encode("ascii"))
        add((candidate_head_sha or "").encode("ascii"))
        for artifact in artifacts:
            add(artifact.artifact_id.encode("ascii"))
            add(artifact.target_ref.encode("utf-8"))
            add(artifact.content)
        return digest.hexdigest()


@dataclass(frozen=True)
class ProjectionCheckRequest:
    task_ref: str
    batch: ProjectionBatch


class InternalPolicyProvider(Protocol):
    """Implemented and selected by the host, outside task-controlled input."""

    def check_plan(self, request: PlanCheckRequest) -> GateDecision: ...

    def check_candidate(self, request: CandidateCheckRequest) -> GateDecision: ...

    def check_projection(self, request: ProjectionCheckRequest) -> GateDecision: ...


class InternalPolicyGate:
    """Validate requests and source-neutrally delegate to a host provider."""

    def __init__(
        self,
        provider: InternalPolicyProvider,
        *,
        private_error_sink: Callable[[Exception], None] | None = None,
    ) -> None:
        for method in ("check_plan", "check_candidate", "check_projection"):
            if not callable(getattr(provider, method, None)):
                raise TypeError(f"provider must implement {method}")
        if private_error_sink is not None and not callable(private_error_sink):
            raise TypeError("private_error_sink must be callable")
        self._provider = provider
        self._private_error_sink = private_error_sink

    def check_plan(
        self,
        *,
        task_ref: str,
        task_projection: Mapping[str, object],
        plan: Mapping[str, object],
        publication_artifact: ProjectionArtifact,
    ) -> GateDecision:
        self._require_task_ref(task_ref)
        if not isinstance(task_projection, Mapping):
            raise TypeError("task_projection must be a mapping")
        if not isinstance(plan, Mapping):
            raise TypeError("plan must be a mapping")
        if not isinstance(publication_artifact, ProjectionArtifact):
            raise TypeError("publication_artifact must be ProjectionArtifact")
        return self._invoke(
            self._provider.check_plan,
            PlanCheckRequest(
                task_ref=task_ref,
                task_projection=task_projection,
                plan=plan,
                publication_artifact=publication_artifact,
            ),
        )

    def check_candidate(
        self,
        *,
        task_ref: str,
        candidate_head_sha: str,
        observations: Mapping[str, object],
    ) -> GateDecision:
        self._require_task_ref(task_ref)
        if not isinstance(candidate_head_sha, str) or FULL_SHA.fullmatch(candidate_head_sha) is None:
            raise ValueError("candidate_head_sha must be a full lowercase commit SHA")
        if not isinstance(observations, Mapping):
            raise TypeError("observations must be a mapping")
        return self._invoke(
            self._provider.check_candidate,
            CandidateCheckRequest(
                task_ref=task_ref,
                candidate_head_sha=candidate_head_sha,
                observations=observations,
            ),
        )

    def check_projection(self, *, task_ref: str, batch: ProjectionBatch) -> GateDecision:
        self._require_task_ref(task_ref)
        if not isinstance(batch, ProjectionBatch):
            raise TypeError("batch must be ProjectionBatch")
        batch.validate_digest()
        return self._invoke(
            self._provider.check_projection,
            ProjectionCheckRequest(task_ref=task_ref, batch=batch),
        )

    def _invoke(self, method: Callable[[object], object], request: object) -> GateDecision:
        try:
            value = method(request)
            if not isinstance(value, GateDecision):
                raise TypeError("provider must return GateDecision")
            return value
        except Exception as error:
            self._record_private_error(error)
            return GateDecision(
                GateStatus.BLOCKED,
                (
                    GateFinding(
                        code="internal_check_unavailable",
                        message="内部検査を完了できませんでした",
                    ),
                ),
            )

    def _record_private_error(self, error: Exception) -> None:
        if self._private_error_sink is None:
            return
        try:
            self._private_error_sink(error)
        except Exception:
            pass

    @staticmethod
    def _require_task_ref(task_ref: str) -> None:
        if not isinstance(task_ref, str) or not task_ref.strip():
            raise ValueError("task_ref must not be empty")
