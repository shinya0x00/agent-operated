#!/usr/bin/env python3
"""Run the published GTP reader without owning GTP lifecycle semantics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ISSUE_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*$")


def emit(value: dict[str, Any]) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")


def finding(kind: str) -> dict[str, str]:
    return {"kind": kind}


def blocked(kind: str, *, issue_url: str | None = None, blocker_ref: str | None = None) -> int:
    value: dict[str, Any] = {
        "decision_scope": "gtp_recovery_adapter",
        "issue_url": issue_url,
        "findings": [finding(kind)],
        "verdict": "blocked",
        "authority": "none",
    }
    if blocker_ref:
        value["blocker_ref"] = blocker_ref
    emit(value)
    return 2


def clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("GH_TOKEN", None)
    environment.pop("GITHUB_TOKEN", None)
    return environment


def run_executable(
    executable: str,
    *arguments: str,
    environment: dict[str, str],
    timeout: int = 30,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            [executable, *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def extract_projection(output: str) -> dict[str, Any] | None:
    lines = output.splitlines()
    for index, line in enumerate(lines):
        if line != "{":
            continue
        try:
            value = json.loads("\n".join(lines[index:]))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def verify_private_actor(profile: Path, gh_command: str, environment: dict[str, str]) -> bool:
    verifier = Path(__file__).resolve().parents[2] / "core" / "verify_actor.py"
    result = run_executable(
        sys.executable,
        str(verifier),
        "--profile",
        str(profile),
        "--role",
        "machine_actor",
        "--operation-class",
        "read_private_task",
        "--gh-command",
        gh_command,
        environment=environment,
    )
    if result is None or result.returncode != 0:
        return False
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return isinstance(value, dict) and value.get("verdict") == "proceed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue-url")
    parser.add_argument("--gtp-command", default="gtp")
    parser.add_argument("--expected-version", default="1.0.1")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--gh-command", default="gh")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    if args.smoke:
        emit({
            "decision_scope": "ao_operation_wiring",
            "attachment": "gtp_operation",
            "fired": True,
            "validated": True,
            "authority": "none",
        })
        return 0

    if not isinstance(args.issue_url, str) or ISSUE_URL.fullmatch(args.issue_url) is None:
        return blocked("invalid_issue_url")

    environment = clean_environment()
    version = run_executable(args.gtp_command, "--version", environment=environment)
    if version is None or version.returncode != 0:
        return blocked("gtp_executable_unavailable", issue_url=args.issue_url)
    observed_version = version.stdout.strip()
    if observed_version != args.expected_version:
        return blocked("incompatible_gtp_version", issue_url=args.issue_url)

    if args.private:
        if args.profile is None or not verify_private_actor(args.profile, args.gh_command, environment):
            return blocked("private_read_actor_unverified", issue_url=args.issue_url)
        token_result = run_executable(args.gh_command, "auth", "token", environment=environment)
        if token_result is None or token_result.returncode != 0 or not token_result.stdout.strip():
            return blocked("private_read_credential_unavailable", issue_url=args.issue_url)
        environment["GITHUB_TOKEN"] = token_result.stdout.strip()

    result = run_executable(
        args.gtp_command,
        "status",
        args.issue_url,
        environment=environment,
    )
    environment.pop("GITHUB_TOKEN", None)
    if result is None:
        return blocked("gtp_execution_failed", issue_url=args.issue_url)

    projection = extract_projection(result.stdout)
    if projection is None:
        return blocked("invalid_gtp_projection", issue_url=args.issue_url)
    if (
        projection.get("gtp") != "1.0"
        or projection.get("command") != "status"
        or projection.get("issue_url") != args.issue_url
        or projection.get("authority") != "none"
    ):
        return blocked("incompatible_gtp_projection", issue_url=args.issue_url)

    envelope: dict[str, Any] = {
        "decision_scope": "gtp_recovery_adapter",
        "issue_url": args.issue_url,
        "observed_cli_version": observed_version,
        "gtp_exit_code": result.returncode,
        "gtp_projection": projection,
        "authority": "none",
        "findings": [],
        "verdict": "proceed",
    }
    if result.returncode == 0:
        emit(envelope)
        return 0
    if result.returncode == 2 and projection.get("acquisition") == "incomplete" and projection.get("state") is None:
        envelope["findings"] = [finding("acquisition_incomplete")]
        envelope["verdict"] = "blocked"
        envelope["blocker_ref"] = projection.get("primary_url", args.issue_url)
        emit(envelope)
        return 2
    return blocked(
        "unexpected_gtp_exit",
        issue_url=args.issue_url,
        blocker_ref=projection.get("primary_url") if isinstance(projection.get("primary_url"), str) else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
