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
ISSUE_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*$")
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

    task_ref = data.get("task_ref")
    candidate = data.get("candidate_head_sha")
    pr_ref = data.get("pr_ref")
    expected_actor = actor(data.get("human_actor"))
    if not isinstance(task_ref, str) or ISSUE_URL.fullmatch(task_ref) is None:
        findings.append({"kind": "invalid_task_ref"})
        task_ref = None
    if not isinstance(candidate, str) or FULL_SHA.fullmatch(candidate) is None:
        findings.append({"kind": "invalid_candidate_head"})
        candidate = None
    if not isinstance(pr_ref, str) or PR_URL.fullmatch(pr_ref) is None:
        findings.append({"kind": "invalid_pr_ref"})
        pr_ref = None
    if expected_actor is None:
        findings.append({"kind": "invalid_human_actor"})

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
    if not findings:
        acceptance_state = "observed"
    elif kinds & {
        "invalid_acceptance_input",
        "invalid_task_ref",
        "invalid_candidate_head",
        "invalid_pr_ref",
        "invalid_human_actor",
        "fixture_not_authoritative",
        "pr_acquisition_failed",
    }:
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
