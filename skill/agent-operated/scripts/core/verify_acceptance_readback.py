#!/usr/bin/env python3
"""Read back native Human Account acceptance for one exact PR candidate."""

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
ISSUE_URL = re.compile(
    r"^https://github\.com/([^/\s]+)/([^/\s]+)/issues/([1-9][0-9]*)$"
)
PR_URL = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/([1-9][0-9]*)$")


def emit(value: dict[str, Any]) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")


def load_object(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
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


def human_actor_from_profile(path: Path | None) -> tuple[str, int] | None:
    profile = load_object(path)
    if profile is None:
        return None
    if (
        profile.get("profile_version") != 1
        or profile.get("merge_policy") != "human_only"
        or profile.get("human_only_operations") != ["acceptance_decision"]
        or actor(profile.get("machine_actor")) is None
    ):
        return None
    return actor(profile.get("human_actor"))


def repository_from(match: re.Match[str] | None) -> tuple[str, str] | None:
    if match is None:
        return None
    owner, repository = match.group(1), match.group(2)
    return owner.casefold(), repository.casefold()


def observe_live_pr(pr_ref: str, gh_command: str) -> dict[str, Any] | None:
    parsed = PR_URL.fullmatch(pr_ref)
    if parsed is None:
        return None
    owner, repository, number = parsed.groups()
    environment = os.environ.copy()
    environment.pop("GH_TOKEN", None)
    environment.pop("GITHUB_TOKEN", None)
    try:
        completed = subprocess.run(
            [gh_command, "api", f"repos/{owner}/{repository}/pulls/{number}"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--pr-json", type=Path)
    parser.add_argument("--allow-fixture", action="store_true")
    parser.add_argument("--gh-command", default="gh")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    if args.smoke:
        emit({
            "decision_scope": "ao_operation_wiring",
            "attachment": "acceptance_readback",
            "fired": True,
            "validated": True,
            "authority": "none",
        })
        return 0

    data = load_object(args.input)
    findings: list[dict[str, str]] = []
    if data is None:
        findings.append({"kind": "invalid_acceptance_input"})
        data = {}
    if set(data) - {"task_ref", "candidate_head_sha", "pr_ref", "human_actor"}:
        findings.append({"kind": "unexpected_acceptance_field"})
    if "human_actor" in data:
        findings.append({"kind": "request_human_actor_forbidden"})

    task_ref = data.get("task_ref")
    candidate = data.get("candidate_head_sha")
    pr_ref = data.get("pr_ref")
    task_match = ISSUE_URL.fullmatch(task_ref) if isinstance(task_ref, str) else None
    pr_match = PR_URL.fullmatch(pr_ref) if isinstance(pr_ref, str) else None
    task_repository = repository_from(task_match)
    pr_repository = repository_from(pr_match)
    expected_actor = human_actor_from_profile(args.profile)

    if task_match is None:
        findings.append({"kind": "invalid_task_ref"})
        task_ref = None
    if not isinstance(candidate, str) or FULL_SHA.fullmatch(candidate) is None:
        findings.append({"kind": "invalid_candidate_head"})
        candidate = None
    if pr_match is None:
        findings.append({"kind": "invalid_pr_ref"})
        pr_ref = None
    if task_repository is not None and pr_repository is not None and task_repository != pr_repository:
        findings.append({"kind": "cross_repository_binding"})
    if expected_actor is None:
        findings.append({"kind": "invalid_actor_profile"})

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

    merged_by: tuple[str, int] | None = None
    if isinstance(pr, dict):
        base_full_name = pr.get("base", {}).get("repo", {}).get("full_name")
        observed_base = (
            tuple(part.casefold() for part in base_full_name.split("/", 1))
            if isinstance(base_full_name, str) and base_full_name.count("/") == 1
            else None
        )
        if observed_base is None:
            findings.append({"kind": "pr_repository_unavailable"})
        elif task_repository is not None and observed_base != task_repository:
            findings.append({"kind": "pr_repository_mismatch"})

        pr_head = pr.get("head", {}).get("sha")
        merged_at = pr.get("merged_at")
        merged_by = actor(pr.get("merged_by"))
        if candidate is not None and pr_head != candidate:
            findings.append({"kind": "stale_candidate"})
        native_merge_observed = isinstance(merged_at, str) and bool(merged_at)
        if not native_merge_observed:
            findings.append({"kind": "native_merge_missing"})
        elif expected_actor is not None and merged_by != expected_actor:
            findings.append({"kind": "wrong_merge_actor"})

    kinds = {item["kind"] for item in findings}
    unavailable = {
        "invalid_acceptance_input",
        "invalid_task_ref",
        "invalid_candidate_head",
        "invalid_pr_ref",
        "request_human_actor_forbidden",
        "unexpected_acceptance_field",
        "cross_repository_binding",
        "invalid_actor_profile",
        "fixture_not_authoritative",
        "pr_acquisition_failed",
        "pr_repository_unavailable",
        "pr_repository_mismatch",
    }
    if not findings:
        acceptance_state = "observed"
    elif kinds & unavailable:
        acceptance_state = "unavailable"
    elif "stale_candidate" in kinds:
        acceptance_state = "stale"
    elif "wrong_merge_actor" in kinds:
        acceptance_state = "conflicting"
    elif "native_merge_missing" in kinds:
        acceptance_state = "missing"
    else:
        acceptance_state = "unavailable"

    emit({
        "decision_scope": "ao_detector_test" if fixture_mode else "ao_acceptance_readback",
        "phase": "post_merge",
        "task_ref": task_ref,
        "pr_ref": pr_ref,
        "candidate_head_sha": candidate,
        "observation_source": "fixture" if fixture_mode else "live_github_api",
        "acceptance_state": acceptance_state,
        "observed_human_actor": (
            {"login": merged_by[0], "id": merged_by[1]} if merged_by is not None else None
        ),
        "findings": findings,
        "authority": "none",
    })
    return 0 if acceptance_state == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
