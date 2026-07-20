#!/usr/bin/env python3
"""Acquire and classify candidate-bound local-command wiring evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ISSUE_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*$")


def emit(value: dict[str, Any]) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")


def load_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def safe_path(value: object) -> str | None:
    if not isinstance(value, str) or not value or value.startswith("/"):
        return None
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return value


def git(repository: Path, *arguments: str, capture: bool = False) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", type=Path)
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    if args.smoke:
        emit({
            "decision_scope": "ao_wiring",
            "attachment": "wiring_gate",
            "fired": True,
            "validated": True,
            "authority": "none",
        })
        return 0

    data = load_object(args.evidence) if args.evidence else None
    if data is None:
        emit({
            "decision_scope": "ao_conformance",
            "findings": [{"kind": "invalid_evidence_input"}],
            "verdict": "blocked",
            "authority": "none",
        })
        return 2

    candidate = data.get("candidate_head_sha")
    task_ref = data.get("task_ref")
    attachment_point = data.get("attachment_point")
    artifact = safe_path(data.get("artifact_path"))
    registration = data.get("registration")
    acquisition = data.get("acquisition")
    findings: list[dict[str, str]] = []
    states = {"present": False, "attached": False, "fired": False, "validated": False}

    if not isinstance(candidate, str) or FULL_SHA.fullmatch(candidate) is None:
        findings.append({"kind": "invalid_candidate_head"})
    if not isinstance(task_ref, str) or ISSUE_URL.fullmatch(task_ref) is None:
        findings.append({"kind": "invalid_task_ref"})
        task_ref = None
    if not isinstance(attachment_point, str) or IDENTIFIER.fullmatch(attachment_point) is None:
        findings.append({"kind": "invalid_attachment_point"})
        attachment_point = None
    if artifact is None:
        findings.append({"kind": "invalid_artifact_path"})

    if not findings:
        observed = git(args.repository, "cat-file", "-e", f"{candidate}:{artifact}")
        states["present"] = observed is not None and observed.returncode == 0
        if not states["present"]:
            findings.append({"kind": "artifact_not_present"})

    if states["present"] and isinstance(registration, dict):
        registration_path = safe_path(registration.get("path"))
        needle = registration.get("contains")
        if registration_path and isinstance(needle, str) and needle:
            content = git(args.repository, "show", f"{candidate}:{registration_path}", capture=True)
            states["attached"] = content is not None and content.returncode == 0 and needle in content.stdout
    if states["present"] and not states["attached"]:
        findings.append({"kind": "attachment_not_observed"})

    if states["attached"] and isinstance(acquisition, dict) and acquisition.get("kind") == "local_command":
        command = acquisition.get("command")
        expected_exit = acquisition.get("expected_exit", 0)
        stdout_contains = acquisition.get("stdout_contains")
        if (
            isinstance(command, list)
            and bool(command)
            and all(isinstance(item, str) and item for item in command)
            and isinstance(expected_exit, int)
            and not isinstance(expected_exit, bool)
            and (stdout_contains is None or isinstance(stdout_contains, str))
        ):
            head = git(args.repository, "rev-parse", "HEAD", capture=True)
            status = git(
                args.repository,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                capture=True,
            )
            head_matches = head is not None and head.returncode == 0 and head.stdout.strip() == candidate
            repository_clean = status is not None and status.returncode == 0 and not status.stdout
            if not head_matches:
                findings.append({"kind": "candidate_not_checked_out"})
            elif not repository_clean:
                findings.append({"kind": "repository_not_clean"})
            else:
                try:
                    result = subprocess.run(
                        command,
                        check=False,
                        capture_output=True,
                        text=True,
                        cwd=args.repository,
                        timeout=30,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    result = None
                states["fired"] = result is not None
                if result is not None:
                    post_head = git(args.repository, "rev-parse", "HEAD", capture=True)
                    post_head_matches = (
                        post_head is not None
                        and post_head.returncode == 0
                        and post_head.stdout.strip() == candidate
                    )
                    output_matches = stdout_contains is None or stdout_contains in result.stdout
                    states["validated"] = (
                        result.returncode == expected_exit and output_matches and post_head_matches
                    )
    elif states["attached"]:
        findings.append({"kind": "unsupported_acquisition"})

    if (
        states["attached"]
        and not states["fired"]
        and not any(
            item["kind"] in {
                "unsupported_acquisition",
                "candidate_not_checked_out",
                "repository_not_clean",
            }
            for item in findings
        )
    ):
        findings.append({"kind": "acquisition_not_fired"})
    if states["fired"] and not states["validated"]:
        findings.append({"kind": "fired_not_validated"})

    if all(states.values()):
        verdict = "proceed"
        exit_code = 0
    elif states["fired"]:
        verdict = "repair_then_proceed"
        exit_code = 1
    else:
        verdict = "blocked"
        exit_code = 2

    envelope: dict[str, Any] = {
        "decision_scope": "ao_conformance",
        "task_ref": task_ref,
        "candidate_head_sha": candidate,
        "attachment_point": attachment_point,
        "required": True,
        "observation_source": "local_command",
        "states": states,
        "findings": findings,
        "verdict": verdict,
        "authority": "none",
    }
    if verdict == "repair_then_proceed":
        envelope["repair_ref"] = findings[0]["kind"] if findings else "validation"
    elif verdict == "blocked":
        envelope["blocker_ref"] = findings[0]["kind"] if findings else "wiring_evidence"
    emit(envelope)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
