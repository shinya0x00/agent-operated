"""Shared Actor Profile and live Actor Observation contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping


FULL_DIGEST = re.compile(r"^[0-9a-f]{64}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
OPERATION_CLASS = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
PROFILE_FIELDS = {
    "profile_version",
    "machine_actor",
    "human_actor",
    "human_only_operations",
    "merge_policy",
}
OBSERVATION_FIELDS = {
    "decision_scope",
    "operation_class",
    "candidate_head_sha",
    "actor_role",
    "observed_at",
    "observed_actor",
    "expected_actor",
    "observation_source",
    "live_actor_verified",
    "findings",
    "verdict",
    "authority",
}


@dataclass(frozen=True)
class ActorIdentity:
    login: str
    id: int

    def __post_init__(self) -> None:
        if not isinstance(self.login, str) or not self.login:
            raise ValueError("actor login must not be empty")
        if not isinstance(self.id, int) or isinstance(self.id, bool) or self.id <= 0:
            raise ValueError("actor id must be a positive integer")

    @classmethod
    def from_mapping(cls, value: object) -> "ActorIdentity":
        if not isinstance(value, Mapping) or set(value) != {"login", "id"}:
            raise ValueError("actor identity is invalid")
        return cls(login=value["login"], id=value["id"])  # type: ignore[arg-type]

    @classmethod
    def from_observation(cls, value: object) -> "ActorIdentity":
        if not isinstance(value, Mapping):
            raise ValueError("actor observation is invalid")
        return cls(login=value.get("login"), id=value.get("id"))  # type: ignore[arg-type]

    def to_mapping(self) -> dict[str, object]:
        return {"login": self.login, "id": self.id}


@dataclass(frozen=True)
class ActorProfile:
    profile_version: int
    machine_actor: ActorIdentity
    human_actor: ActorIdentity
    human_only_operations: tuple[str, ...]
    merge_policy: str
    digest: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_version, int)
            or isinstance(self.profile_version, bool)
            or self.profile_version != 1
        ):
            raise ValueError("unsupported Actor Profile version")
        if not isinstance(self.machine_actor, ActorIdentity) or not isinstance(
            self.human_actor, ActorIdentity
        ):
            raise TypeError("profile actors must be ActorIdentity values")
        if self.machine_actor.id == self.human_actor.id:
            raise ValueError("Machine Account and Human Account must have different ids")
        if self.human_only_operations != ("acceptance_decision",):
            raise ValueError("human-only operations are invalid")
        if self.merge_policy != "human_only":
            raise ValueError("merge policy is invalid")
        if not isinstance(self.digest, str) or FULL_DIGEST.fullmatch(self.digest) is None:
            raise ValueError("profile digest is invalid")
        if self.digest != self.compute_digest(self.to_mapping()):
            raise ValueError("profile digest does not match its content")

    @classmethod
    def from_mapping(cls, value: object) -> "ActorProfile":
        if not isinstance(value, Mapping) or set(value) != PROFILE_FIELDS:
            raise ValueError("Actor Profile fields are invalid")
        machine = ActorIdentity.from_mapping(value.get("machine_actor"))
        human = ActorIdentity.from_mapping(value.get("human_actor"))
        operations = value.get("human_only_operations")
        if not isinstance(operations, list) or not all(
            isinstance(item, str) for item in operations
        ):
            raise ValueError("human-only operations are invalid")
        normalized = {
            "profile_version": value.get("profile_version"),
            "machine_actor": machine.to_mapping(),
            "human_actor": human.to_mapping(),
            "human_only_operations": operations,
            "merge_policy": value.get("merge_policy"),
        }
        return cls(
            profile_version=value.get("profile_version"),  # type: ignore[arg-type]
            machine_actor=machine,
            human_actor=human,
            human_only_operations=tuple(operations),
            merge_policy=value.get("merge_policy"),  # type: ignore[arg-type]
            digest=cls.compute_digest(normalized),
        )

    @classmethod
    def load(cls, path: Path | None) -> "ActorProfile":
        if path is None:
            raise ValueError("Actor Profile path is required")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Actor Profile is unavailable") from error
        return cls.from_mapping(value)

    @staticmethod
    def compute_digest(value: Mapping[str, object]) -> str:
        try:
            encoded = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ValueError("Actor Profile is not canonicalizable") from error
        return hashlib.sha256(encoded).hexdigest()

    def to_mapping(self) -> dict[str, object]:
        return {
            "profile_version": self.profile_version,
            "machine_actor": self.machine_actor.to_mapping(),
            "human_actor": self.human_actor.to_mapping(),
            "human_only_operations": list(self.human_only_operations),
            "merge_policy": self.merge_policy,
        }


@dataclass(frozen=True)
class ActorObservation:
    """A verified live Machine Account observation, never a fixture result."""

    operation_class: str
    candidate_head_sha: str | None
    observed_at: str
    actor: ActorIdentity
    profile_digest: str

    def __post_init__(self) -> None:
        if OPERATION_CLASS.fullmatch(self.operation_class) is None:
            raise ValueError("operation_class is invalid")
        if self.candidate_head_sha is not None and FULL_SHA.fullmatch(
            self.candidate_head_sha
        ) is None:
            raise ValueError("candidate_head_sha is invalid")
        if not isinstance(self.observed_at, str) or not self.observed_at:
            raise ValueError("observed_at must not be empty")
        if not isinstance(self.actor, ActorIdentity):
            raise TypeError("actor must be ActorIdentity")
        if not isinstance(self.profile_digest, str) or FULL_DIGEST.fullmatch(
            self.profile_digest
        ) is None:
            raise ValueError("profile_digest is invalid")

    @classmethod
    def from_mapping(
        cls,
        value: object,
        *,
        profile: ActorProfile,
    ) -> "ActorObservation":
        if not isinstance(profile, ActorProfile):
            raise TypeError("profile must be ActorProfile")
        if not isinstance(value, Mapping) or set(value) != OBSERVATION_FIELDS:
            raise ValueError("Actor Observation fields are invalid")
        observed = ActorIdentity.from_mapping(value.get("observed_actor"))
        expected = ActorIdentity.from_mapping(value.get("expected_actor"))
        required = (
            value.get("decision_scope") == "ao_actor_observation"
            and value.get("actor_role") == "machine_actor"
            and value.get("observation_source") == "live_github_api"
            and value.get("live_actor_verified") is True
            and value.get("verdict") == "proceed"
            and value.get("authority") == "none"
            and value.get("findings") == []
            and observed == expected == profile.machine_actor
        )
        if not required:
            raise ValueError("Actor Observation is not an authoritative live machine observation")
        return cls(
            operation_class=value.get("operation_class"),  # type: ignore[arg-type]
            candidate_head_sha=value.get("candidate_head_sha"),  # type: ignore[arg-type]
            observed_at=value.get("observed_at"),  # type: ignore[arg-type]
            actor=observed,
            profile_digest=profile.digest,
        )

    def validate_for(
        self,
        profile: ActorProfile,
        *,
        operation_class: str,
        candidate_head_sha: str | None,
    ) -> None:
        if (
            not isinstance(profile, ActorProfile)
            or self.profile_digest != profile.digest
            or self.actor != profile.machine_actor
            or self.operation_class != operation_class
            or self.candidate_head_sha != candidate_head_sha
        ):
            raise ValueError("Actor Observation does not match the requested mutation")
