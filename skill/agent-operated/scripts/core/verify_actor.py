#!/usr/bin/env python3
"""Observe a GitHub principal and compare it with an AO actor profile."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from actor_contract import ActorIdentity, ActorProfile


OPERATION_CLASS = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def emit(value: dict[str, Any]) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")


def load_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def observe_live_user(gh_command: str) -> dict[str, Any] | None:
    environment = os.environ.copy()
    environment.pop("GH_TOKEN", None)
    environment.pop("GITHUB_TOKEN", None)
    try:
        result = subprocess.run(
            [gh_command, "api", "user"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    try:
        ActorIdentity.from_observation(value)
    except (TypeError, ValueError):
        return None
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--role", choices=("machine_actor", "human_actor"), default="machine_actor")
    parser.add_argument("--operation-class", default="github_mutation")
    parser.add_argument("--candidate-head")
    parser.add_argument("--user-json", type=Path)
    parser.add_argument("--allow-fixture", action="store_true")
    parser.add_argument("--gh-command", default="gh")
    parser.add_argument("--observed-at")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    if args.smoke:
        emit({
            "decision_scope": "ao_operation_wiring",
            "attachment": "actor_preflight",
            "fired": True,
            "validated": True,
            "authority": "none",
        })
        return 0

    if OPERATION_CLASS.fullmatch(args.operation_class) is None:
        emit({
            "decision_scope": "ao_actor_observation",
            "findings": [{"kind": "invalid_operation_class"}],
            "verdict": "blocked",
            "authority": "none",
        })
        return 2

    if args.candidate_head is not None and FULL_SHA.fullmatch(args.candidate_head) is None:
        emit({
            "decision_scope": "ao_actor_observation",
            "operation_class": args.operation_class,
            "findings": [{"kind": "invalid_candidate_head"}],
            "verdict": "blocked",
            "authority": "none",
        })
        return 2
    try:
        profile = ActorProfile.load(args.profile)
    except (TypeError, ValueError):
        emit({
            "decision_scope": "ao_actor_observation",
            "operation_class": args.operation_class,
            "findings": [{"kind": "invalid_actor_profile"}],
            "verdict": "blocked",
            "authority": "none",
        })
        return 2
    expected_identity = (
        profile.machine_actor if args.role == "machine_actor" else profile.human_actor
    )
    expected = expected_identity.to_mapping()

    if args.user_json and not args.allow_fixture:
        emit({
            "decision_scope": "ao_actor_observation",
            "operation_class": args.operation_class,
            "findings": [{"kind": "fixture_not_authoritative"}],
            "verdict": "blocked",
            "authority": "none",
        })
        return 2

    fixture_mode = args.user_json is not None
    observed = load_object(args.user_json) if fixture_mode else observe_live_user(args.gh_command)
    try:
        observed_identity = ActorIdentity.from_observation(observed)
    except (TypeError, ValueError):
        emit({
            "decision_scope": "ao_actor_observation",
            "operation_class": args.operation_class,
            "findings": [{"kind": "actor_acquisition_failed"}],
            "verdict": "blocked",
            "authority": "none",
        })
        return 2

    matches = observed_identity == expected_identity
    observed_at = args.observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    envelope: dict[str, Any] = {
        "decision_scope": "ao_detector_test" if fixture_mode else "ao_actor_observation",
        "operation_class": args.operation_class,
        "candidate_head_sha": args.candidate_head,
        "actor_role": args.role,
        "observed_at": observed_at,
        "observed_actor": observed_identity.to_mapping(),
        "expected_actor": expected,
        "observation_source": "fixture" if fixture_mode else "live_github_api",
        "live_actor_verified": not fixture_mode and matches,
        "findings": [],
        "verdict": "proceed",
        "authority": "none",
    }
    if not matches:
        envelope["findings"] = [{"kind": "wrong_actor"}]
        envelope["verdict"] = "blocked"
        envelope["blocker_ref"] = "actor_profile"
        emit(envelope)
        return 2
    emit(envelope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
