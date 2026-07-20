#!/usr/bin/env python3
"""Bind one opaque Operation result to an AO task and optional candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
ISSUE_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*$")
PHASES = {
    "task_recovery",
    "pre_mutation",
    "pre_publication",
    "pre_handoff",
    "post_merge",
}


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


def valid_source_ref(value: object) -> bool:
    if not isinstance(value, str) or any(character.isspace() for character in value):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and "@" not in parsed.netloc
        and bool(parsed.path)
        and not parsed.query
        and not parsed.fragment
    )


def invalid(kind: str) -> int:
    emit({
        "receipt_version": 1,
        "operation": None,
        "phase": None,
        "task_ref": None,
        "implementation_version": None,
        "source_ref": None,
        "candidate_binding": {
            "required": None,
            "status": "unavailable",
            "candidate_head_sha": None,
            "observed_head_sha": None,
        },
        "result": {},
        "findings": [{"kind": kind}],
        "authority": "none",
    })
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    if args.smoke:
        emit({
            "decision_scope": "ao_operation_wiring",
            "attachment": "operation_result_binding",
            "fired": True,
            "validated": True,
            "authority": "none",
        })
        return 0

    data = load_object(args.input)
    if data is None:
        return invalid("invalid_receipt_input")

    operation = data.get("operation")
    phase = data.get("phase")
    task_ref = data.get("task_ref")
    implementation_version = data.get("implementation_version")
    source_ref = data.get("source_ref")
    candidate_required = data.get("candidate_required")
    candidate = data.get("candidate_head_sha")
    observed = data.get("observed_head_sha")
    result = data.get("result")

    if not isinstance(operation, str) or IDENTIFIER.fullmatch(operation) is None:
        return invalid("invalid_operation")
    if phase not in PHASES:
        return invalid("invalid_phase")
    if not isinstance(task_ref, str) or ISSUE_URL.fullmatch(task_ref) is None:
        return invalid("invalid_task_ref")
    if not isinstance(implementation_version, str) or not implementation_version:
        return invalid("invalid_implementation_version")
    if not valid_source_ref(source_ref):
        return invalid("invalid_source_ref")
    if not isinstance(candidate_required, bool):
        return invalid("invalid_candidate_requirement")
    if not isinstance(result, dict):
        return invalid("invalid_operation_result")

    candidate_valid = isinstance(candidate, str) and FULL_SHA.fullmatch(candidate) is not None
    observed_valid = isinstance(observed, str) and FULL_SHA.fullmatch(observed) is not None
    findings: list[dict[str, str]] = []
    if candidate is not None and not candidate_valid:
        return invalid("invalid_candidate_head")
    if observed is not None and not observed_valid:
        return invalid("invalid_observed_head")

    if candidate is None and observed is None and not candidate_required:
        binding_status = "not_applicable"
    elif candidate_valid and observed_valid and candidate == observed:
        binding_status = "bound"
    elif candidate_valid and observed_valid:
        binding_status = "stale"
        findings.append({"kind": "stale_candidate"})
    else:
        binding_status = "unavailable"
        findings.append({"kind": "candidate_binding_unavailable"})

    receipt = {
        "receipt_version": 1,
        "operation": operation,
        "phase": phase,
        "task_ref": task_ref,
        "implementation_version": implementation_version,
        "source_ref": source_ref,
        "candidate_binding": {
            "required": candidate_required,
            "status": binding_status,
            "candidate_head_sha": candidate,
            "observed_head_sha": observed,
        },
        "result": result,
        "findings": findings,
        "authority": "none",
    }
    emit(receipt)
    return 0 if binding_status in {"not_applicable", "bound"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
