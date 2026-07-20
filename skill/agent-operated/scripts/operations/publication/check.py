#!/usr/bin/env python3
"""Screen a publication artifact without reproducing matched values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "secret_value",
        re.compile(
            r"(?:\bgh[pousr]_[A-Za-z0-9_]{12,}|\bgithub_pat_[A-Za-z0-9_]{12,}|"
            r"\bsk-[A-Za-z0-9_-]{12,}|\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|"
            r"\b(?:GH_TOKEN|GITHUB_TOKEN|OPENAI_API_KEY|PASSWORD|PRIVATE_KEY|CLIENT_SECRET)"
            r"\s*[:=]\s*[\"']?(?!<|\$\{|REDACTED|redacted)[^\s\"']{8,})",
            re.IGNORECASE,
        ),
    ),
    (
        "local_absolute_path",
        re.compile(r"(?:/Users/[^\s]+|/home/[^\s]+|/private/var/[^\s]+|[A-Za-z]:\\Users\\[^\s]+)"),
    ),
    (
        "private_context",
        re.compile(
            r"(?:[\"'](?:private_prompt|chain_of_thought|reasoning_transcript|session_transcript)[\"']\s*:|"
            r"BEGIN\s+(?:PRIVATE\s+PROMPT|CHAIN\s+OF\s+THOUGHT|REASONING\s+TRANSCRIPT))",
            re.IGNORECASE,
        ),
    ),
    (
        "ephemeral_runtime_id",
        re.compile(r"[\"'](?:session_id|runtime_id|thread_id)[\"']\s*:\s*[\"'][^\"']+[\"']", re.IGNORECASE),
    ),
    (
        "credential_location",
        re.compile(
            r"(?:GH_CONFIG_DIR\s*[:=]\s*[\"']?/(?:Users|home|private)/|"
            r"/(?:Users|home)/[^\s]+/(?:\.config/gh/hosts\.yml|\.ssh/[^\s]+))",
            re.IGNORECASE,
        ),
    ),
)


def emit(value: dict[str, Any]) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")


def screen_items(items: Iterable[tuple[str, bytes]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for artifact_id, content in items:
        try:
            source = content.decode("utf-8")
        except (AttributeError, UnicodeDecodeError):
            return {
                "decision_scope": "publication_screening",
                "source": "input",
                "findings": [{"kind": "input_unavailable", "artifact_id": artifact_id}],
                "verdict": "blocked",
                "authority": "none",
                "blocker_ref": artifact_id,
            }
        seen: set[tuple[str, int]] = set()
        for line_number, line in enumerate(source.splitlines(), start=1):
            for kind, pattern in PATTERNS:
                if pattern.search(line) is None or (kind, line_number) in seen:
                    continue
                seen.add((kind, line_number))
                findings.append({"kind": kind, "line": line_number, "artifact_id": artifact_id})

    blocked = bool(findings)
    envelope: dict[str, Any] = {
        "decision_scope": "publication_screening",
        "source": "input",
        "findings": findings,
        "verdict": "blocked" if blocked else "proceed",
        "authority": "none",
    }
    if blocked:
        first = findings[0]
        envelope["blocker_ref"] = f"{first['artifact_id']}:{first['line']}"
    return envelope


def screen_batch(batch: object) -> dict[str, Any]:
    artifacts = getattr(batch, "artifacts", None)
    if not isinstance(artifacts, tuple) or not artifacts:
        return {
            "decision_scope": "publication_screening",
            "source": "input",
            "findings": [{"kind": "input_unavailable"}],
            "verdict": "blocked",
            "authority": "none",
        }
    items: list[tuple[str, bytes]] = []
    for artifact in artifacts:
        artifact_id = getattr(artifact, "artifact_id", None)
        content = getattr(artifact, "content", None)
        if not isinstance(artifact_id, str) or not isinstance(content, bytes):
            return {
                "decision_scope": "publication_screening",
                "source": "input",
                "findings": [{"kind": "input_unavailable"}],
                "verdict": "blocked",
                "authority": "none",
            }
        items.append((artifact_id, content))
    return screen_items(items)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    if args.smoke:
        emit({
            "decision_scope": "ao_operation_wiring",
            "attachment": "publication_screening",
            "fired": True,
            "validated": True,
            "authority": "none",
        })
        return 0

    if args.path is None:
        emit({
            "decision_scope": "publication_screening",
            "findings": [{"kind": "input_unavailable"}],
            "verdict": "blocked",
            "authority": "none",
        })
        return 2
    try:
        content = args.path.read_bytes()
    except OSError:
        emit({
            "decision_scope": "publication_screening",
            "findings": [{"kind": "input_unavailable"}],
            "verdict": "blocked",
            "authority": "none",
        })
        return 2

    envelope = screen_items((("input", content),))
    emit(envelope)
    return 2 if envelope["verdict"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
