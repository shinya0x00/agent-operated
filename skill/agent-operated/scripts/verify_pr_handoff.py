#!/usr/bin/env python3
"""Verify AO handoff readiness or Human Account acceptance readback."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ISSUE_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*$")
ARTIFACT_URL = re.compile(
    r"^https://github\.com/[^/\s]+/[^/\s]+/blob/[0-9a-f]{40}/[^?\s]+$"
)
PR_URL = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/([1-9][0-9]*)$")


def emit(value: dict[str, Any]) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")


def load_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def actor(value: object) -> tuple[str, int] | None:
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("login"), str)
        or not value["login"]
        or not isinstance(value.get("id"), int)
        or isinstance(value["id"], bool)
        or value["id"] <= 0
    ):
        return None
    return value["login"], value["id"]


def evidence_matches(value: object, candidate: str, *, fixture_mode: bool) -> bool:
    accepted_scope = "ao_detector_test" if fixture_mode else "ao_conformance"
    return (
        isinstance(value, dict)
        and value.get("candidate_head_sha") == candidate
        and value.get("verdict") == "proceed"
        and value.get("authority") == "none"
        and value.get("decision_scope") == accepted_scope
    )


def actor_evidence_matches(value: object, candidate: str, *, fixture_mode: bool) -> bool:
    return (
        evidence_matches(value, candidate, fixture_mode=fixture_mode)
        and isinstance(value, dict)
        and value.get("observation_source") == ("fixture" if fixture_mode else "live_github_api")
        and value.get("live_actor_verified") is (not fixture_mode)
    )


def validation_evidence_matches(value: object, candidate: str, *, fixture_mode: bool) -> bool:
    return (
        evidence_matches(value, candidate, fixture_mode=fixture_mode)
        and isinstance(value, dict)
        and value.get("observation_source") == ("fixture" if fixture_mode else "live_acquisition")
    )


def wiring_evidence_matches(value: object, candidate: str, *, fixture_mode: bool) -> bool:
    if not isinstance(value, dict) or value.get("required") is not True:
        return False
    states = value.get("states")
    return (
        evidence_matches(value, candidate, fixture_mode=fixture_mode)
        and value.get("observation_source") == ("fixture" if fixture_mode else "local_command")
        and isinstance(states, dict)
        and states.get("fired") is True
        and states.get("validated") is True
    )


def observe_live_pr(pr_ref: str, gh_command: str) -> dict[str, Any] | None:
    parsed = PR_URL.fullmatch(pr_ref)
    if parsed is None:
        return None
    owner, repository, number = parsed.groups()
    environment = os.environ.copy()
    environment.pop("GH_TOKEN", None)
    environment.pop("GITHUB_TOKEN", None)
    try:
        result = subprocess.run(
            [gh_command, "api", f"repos/{owner}/{repository}/pulls/{number}"],
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
    return value if isinstance(value, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--phase", choices=("readiness", "acceptance_readback"), default="readiness")
    parser.add_argument("--pr-json", type=Path)
    parser.add_argument("--allow-fixture", action="store_true")
    parser.add_argument("--gh-command", default="gh")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    if args.smoke:
        emit({
            "decision_scope": "ao_wiring",
            "attachment": "handoff_gate",
            "fired": True,
            "validated": True,
            "authority": "none",
        })
        return 0

    data = load_object(args.input) if args.input else None
    if data is None:
        emit({
            "decision_scope": "ao_conformance",
            "phase": args.phase,
            "findings": [{"kind": "invalid_handoff_input"}],
            "verdict": "blocked",
            "authority": "none",
        })
        return 2

    findings: list[dict[str, str]] = []
    candidate = data.get("candidate_head_sha")
    if not isinstance(candidate, str) or FULL_SHA.fullmatch(candidate) is None:
        findings.append({"kind": "invalid_candidate_head"})

    task_ref = data.get("task_ref")
    actor_profile_ref = data.get("actor_profile_ref")
    pr_ref = data.get("pr_ref")
    if not isinstance(task_ref, str) or ISSUE_URL.fullmatch(task_ref) is None:
        findings.append({"kind": "invalid_task_ref"})
        task_ref = None
    if not isinstance(actor_profile_ref, str) or ARTIFACT_URL.fullmatch(actor_profile_ref) is None:
        findings.append({"kind": "invalid_actor_profile_ref"})
        actor_profile_ref = None
    if not isinstance(pr_ref, str) or PR_URL.fullmatch(pr_ref) is None:
        findings.append({"kind": "invalid_pr_ref"})
        pr_ref = None

    fixture_mode = args.pr_json is not None
    if fixture_mode and not args.allow_fixture:
        findings.append({"kind": "fixture_not_authoritative"})
        pr = None
    elif fixture_mode:
        pr = load_object(args.pr_json)
    elif pr_ref is not None:
        pr = observe_live_pr(pr_ref, args.gh_command)
    else:
        pr = None
    if not isinstance(pr, dict):
        findings.append({"kind": "pr_acquisition_failed"})

    pr_head = pr.get("head", {}).get("sha") if isinstance(pr, dict) else None
    if isinstance(candidate, str) and pr_head != candidate:
        findings.append({"kind": "stale_pr_head"})

    if isinstance(candidate, str):
        if not actor_evidence_matches(data.get("actor_evidence"), candidate, fixture_mode=fixture_mode):
            findings.append({"kind": "invalid_actor_evidence"})
        if not validation_evidence_matches(data.get("validation_evidence"), candidate, fixture_mode=fixture_mode):
            findings.append({"kind": "invalid_validation_evidence"})
        wiring = data.get("wiring_evidence")
        if isinstance(wiring, dict) and wiring.get("required") is True:
            if not wiring_evidence_matches(wiring, candidate, fixture_mode=fixture_mode):
                findings.append({"kind": "invalid_wiring_evidence"})

    if args.phase == "readiness":
        if not isinstance(data.get("human_decision_requested"), str) or not data["human_decision_requested"]:
            findings.append({"kind": "missing_human_decision_request"})
    else:
        expected = actor(data.get("human_actor"))
        merged_by = actor(pr.get("merged_by") if isinstance(pr, dict) else None)
        merged_at = pr.get("merged_at") if isinstance(pr, dict) else None
        if not isinstance(merged_at, str) or not merged_at:
            findings.append({"kind": "native_merge_missing"})
        if expected is None:
            findings.append({"kind": "invalid_human_actor_profile"})
        elif merged_by != expected:
            findings.append({"kind": "wrong_merge_actor"})

    verdict = "blocked" if findings else "proceed"
    envelope: dict[str, Any] = {
        "decision_scope": "ao_detector_test" if fixture_mode else "ao_conformance",
        "phase": args.phase,
        "task_ref": task_ref,
        "actor_profile_ref": actor_profile_ref,
        "pr_ref": pr_ref,
        "candidate_head_sha": candidate,
        "observation_source": "fixture" if fixture_mode else "live_github_api",
        "evidence_input_trust": "fixture" if fixture_mode else "caller_provided_detector_projection",
        "findings": findings,
        "verdict": verdict,
        "authority": "none",
    }
    if findings:
        envelope["blocker_ref"] = findings[0]["kind"]
    emit(envelope)
    return 2 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
