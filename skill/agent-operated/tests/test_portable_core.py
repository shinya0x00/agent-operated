from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
REPOSITORY = SKILL.parents[1]
CORE = SKILL / "scripts" / "core"
GTP = SKILL / "scripts" / "operations" / "gtp" / "recover.py"
PUBLICATION = SKILL / "scripts" / "operations" / "publication" / "check.py"
BINDER = CORE / "bind_operation_result.py"
ACCEPTANCE = CORE / "verify_acceptance_readback.py"
ISSUE_URL = "https://github.com/example/project/issues/7"

sys.path.insert(0, str(CORE))
from internal_policy_gate import (  # noqa: E402
    CandidateCheckRequest,
    GateDecision,
    GateFinding,
    GateStatus,
    InternalPolicyGate,
    PlanCheckRequest,
    ProjectionArtifact,
    ProjectionCheckRequest,
)


class RecordingPolicyProvider:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def check_plan(self, request: PlanCheckRequest) -> GateDecision:
        self.requests.append(request)
        return GateDecision(GateStatus.PROCEED)

    def check_candidate(self, request: CandidateCheckRequest) -> GateDecision:
        self.requests.append(request)
        return GateDecision(GateStatus.PROCEED)

    def check_projection(self, request: ProjectionCheckRequest) -> GateDecision:
        self.requests.append(request)
        return GateDecision(GateStatus.PROCEED)


class PortableCoreTests(unittest.TestCase):
    def run_json(
        self,
        command: list[str],
        *,
        environment: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> tuple[int, dict, str]:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            cwd=cwd,
            timeout=30,
        )
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"invalid JSON: {error}; stdout={completed.stdout!r}; stderr={completed.stderr!r}")
        self.assertIsInstance(value, dict)
        return completed.returncode, value, completed.stderr

    def write_json(self, directory: Path, name: str, value: object) -> Path:
        path = directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def make_executable(self, directory: Path, name: str, source: str) -> Path:
        path = directory / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o755)
        return path

    def actor_profile(self) -> dict:
        return {
            "profile_version": 1,
            "machine_actor": {"login": "machine", "id": 101},
            "human_actor": {"login": "human", "id": 202},
            "human_only_operations": ["acceptance_decision"],
            "merge_policy": "human_only",
        }

    def bind(self, directory: Path, name: str, value: dict) -> tuple[int, dict, str]:
        source = self.write_json(directory, name, value)
        return self.run_json([sys.executable, str(BINDER), str(source)])

    def test_smoke_fires_every_registered_attachment(self) -> None:
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        attachments = {
            "actor_preflight": CORE / "verify_actor.py",
            "operation_result_binding": BINDER,
            "acceptance_readback": ACCEPTANCE,
            "gtp_operation": GTP,
            "publication_screening": PUBLICATION,
        }
        observed: set[str] = set()
        for attachment, script in attachments.items():
            relative = script.relative_to(SKILL).as_posix()
            self.assertIn(relative, skill)
            code, output, _ = self.run_json([sys.executable, str(script), "--smoke"])
            self.assertEqual(0, code)
            self.assertEqual(attachment, output["attachment"])
            self.assertTrue(output["fired"])
            self.assertTrue(output["validated"])
            self.assertEqual("none", output["authority"])
            observed.add(attachment)
        self.assertEqual(set(attachments), observed)

        provider = RecordingPolicyProvider()
        gate = InternalPolicyGate(provider)
        candidate = "a" * 40
        decisions = (
            gate.check_plan(task_ref=ISSUE_URL, plan={"scope": "candidate"}),
            gate.check_candidate(
                task_ref=ISSUE_URL,
                candidate_head_sha=candidate,
                observations={"tests": "passed"},
            ),
            gate.check_projection(
                task_ref=ISSUE_URL,
                artifacts=(ProjectionArtifact("PURPOSE.md", "public content"),),
            ),
        )
        self.assertTrue(all(item.status is GateStatus.PROCEED for item in decisions))
        self.assertEqual(
            [PlanCheckRequest, CandidateCheckRequest, ProjectionCheckRequest],
            [type(item) for item in provider.requests],
        )

    def test_internal_policy_gate_is_host_supplied_and_invocation_local(self) -> None:
        provider = RecordingPolicyProvider()
        gate = InternalPolicyGate(provider)
        decision = gate.check_plan(task_ref=ISSUE_URL, plan={"scope": "candidate"})

        self.assertFalse(hasattr(gate, "to_json"))
        self.assertFalse(hasattr(decision, "to_dict"))
        with self.assertRaises(TypeError):
            json.dumps(decision)

        module_source = (CORE / "internal_policy_gate.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess.run", module_source)
        self.assertNotIn("os.environ", module_source)
        self.assertNotIn("argparse.ArgumentParser", module_source)

    def test_internal_policy_gate_validates_candidate_and_provider_result(self) -> None:
        provider = RecordingPolicyProvider()
        gate = InternalPolicyGate(provider)

        with self.assertRaises(ValueError):
            gate.check_candidate(
                task_ref=ISSUE_URL,
                candidate_head_sha="short",
                observations={},
            )

        class InvalidProvider(RecordingPolicyProvider):
            def check_projection(self, request: ProjectionCheckRequest) -> GateDecision:
                return {"status": "proceed"}  # type: ignore[return-value]

        with self.assertRaises(TypeError):
            InternalPolicyGate(InvalidProvider()).check_projection(
                task_ref=ISSUE_URL,
                artifacts=(ProjectionArtifact("PURPOSE.md", "public content"),),
            )

        with self.assertRaises(TypeError):
            GateDecision("proceed")  # type: ignore[arg-type]

        finding = GateFinding(
            code="candidate_evidence_missing",
            message="candidate validation evidence is missing",
            target_ref="tests/",
        )
        self.assertEqual(
            GateStatus.BLOCKED,
            GateDecision(GateStatus.BLOCKED, (finding,)).status,
        )

    def test_actor_observation_does_not_require_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            profile = self.write_json(directory, "profile.json", self.actor_profile())
            matched = self.write_json(directory, "matched.json", {"login": "machine", "id": 101})
            wrong = self.write_json(directory, "wrong.json", {"login": "machine", "id": 999})
            code, output, _ = self.run_json([
                sys.executable,
                str(CORE / "verify_actor.py"),
                "--profile",
                str(profile),
                "--user-json",
                str(matched),
                "--allow-fixture",
            ])
            self.assertEqual(0, code)
            self.assertIsNone(output["candidate_head_sha"])
            self.assertEqual("ao_detector_test", output["decision_scope"])
            self.assertEqual("proceed", output["verdict"])

            code, output, _ = self.run_json([
                sys.executable,
                str(CORE / "verify_actor.py"),
                "--profile",
                str(profile),
                "--user-json",
                str(wrong),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("wrong_actor", output["findings"][0]["kind"])

            code, output, _ = self.run_json([
                sys.executable,
                str(CORE / "verify_actor.py"),
                "--profile",
                str(profile),
                "--user-json",
                str(matched),
            ])
            self.assertEqual(2, code)
            self.assertEqual("fixture_not_authoritative", output["findings"][0]["kind"])

    def receipt_input(self, result: dict, *, required: bool, candidate: str | None = None) -> dict:
        value = {
            "operation": "sample_operation",
            "phase": "pre_handoff" if required else "task_recovery",
            "task_ref": ISSUE_URL,
            "implementation_version": "1",
            "source_ref": "https://github.com/example/project/actions/runs/9",
            "candidate_required": required,
            "result": result,
        }
        if candidate is not None:
            value["candidate_head_sha"] = candidate
            value["observed_head_sha"] = candidate
        return value

    def test_operation_receipt_preserves_result_and_binding_states(self) -> None:
        opaque_result = {
            "state": "halt",
            "next_action": "inspect_halt",
            "verdict": "repair_then_proceed",
            "authority": "none",
        }
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            code, receipt, _ = self.bind(
                directory,
                "not-applicable.json",
                self.receipt_input(opaque_result, required=False),
            )
            self.assertEqual(0, code)
            self.assertEqual("not_applicable", receipt["candidate_binding"]["status"])
            self.assertEqual(opaque_result, receipt["result"])
            self.assertNotIn("verdict", receipt)

            candidate = "a" * 40
            code, receipt, _ = self.bind(
                directory,
                "bound.json",
                self.receipt_input(opaque_result, required=True, candidate=candidate),
            )
            self.assertEqual(0, code)
            self.assertEqual("bound", receipt["candidate_binding"]["status"])

            stale = self.receipt_input(opaque_result, required=True, candidate=candidate)
            stale["observed_head_sha"] = "b" * 40
            code, receipt, _ = self.bind(directory, "stale.json", stale)
            self.assertEqual(2, code)
            self.assertEqual("stale", receipt["candidate_binding"]["status"])
            self.assertEqual("stale_candidate", receipt["findings"][0]["kind"])

            unavailable = self.receipt_input(opaque_result, required=True)
            code, receipt, _ = self.bind(directory, "unavailable.json", unavailable)
            self.assertEqual(2, code)
            self.assertEqual("unavailable", receipt["candidate_binding"]["status"])

    def test_receipt_rejects_invalid_reference_without_echo(self) -> None:
        secret = "private-reference-value"
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            value = self.receipt_input({}, required=False)
            value["task_ref"] = secret
            source = self.write_json(directory, "invalid.json", value)
            completed = subprocess.run(
                [sys.executable, str(BINDER), str(source)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(2, completed.returncode)
            self.assertNotIn(secret, completed.stdout + completed.stderr)

            value = self.receipt_input({}, required=False)
            value["source_ref"] = "https://example.com/result?token=" + secret
            source = self.write_json(directory, "invalid-source.json", value)
            completed = subprocess.run(
                [sys.executable, str(BINDER), str(source)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(2, completed.returncode)
            self.assertNotIn(secret, completed.stdout + completed.stderr)

    def fake_gtp(self, directory: Path) -> Path:
        return self.make_executable(
            directory,
            "gtp",
            """#!/usr/bin/env python3
import json
import os
import sys
if sys.argv[1:] == ["--version"]:
    print(os.environ.get("FAKE_GTP_VERSION", "1.0.1"))
    raise SystemExit(0)
mode = os.environ.get("FAKE_GTP_MODE", "halt")
if os.environ.get("FAKE_GTP_REQUIRE_TOKEN") == "1" and os.environ.get("GITHUB_TOKEN") != os.environ.get("FAKE_GTP_TOKEN"):
    raise SystemExit(8)
issue = sys.argv[2]
state = None if mode == "incomplete" else mode
print(json.dumps({
    "gtp": "1.0",
    "command": "status",
    "issue_url": issue,
    "state": state,
    "halt_reason": "invalid_binding" if mode == "halt" else None,
    "next_action": "retry_acquisition" if mode == "incomplete" else "inspect_halt" if mode == "halt" else "post_contract",
    "primary_url": issue,
    "authority": "none",
    "acquisition": "incomplete" if mode == "incomplete" else "complete"
}, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(2 if mode == "incomplete" else 0)
""",
        )

    def fake_gh(self, directory: Path) -> Path:
        return self.make_executable(
            directory,
            "gh",
            """#!/usr/bin/env python3
import json
import os
import sys
if sys.argv[1:] == ["api", "user"]:
    print(json.dumps({"login": "machine", "id": 101}))
    raise SystemExit(0)
if sys.argv[1:] == ["auth", "token"]:
    print(os.environ["FAKE_GTP_TOKEN"])
    raise SystemExit(0)
raise SystemExit(9)
""",
        )

    def test_gtp_halt_and_acquisition_failure_remain_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            fake = self.fake_gtp(directory)
            environment = os.environ.copy()
            environment["FAKE_GTP_MODE"] = "halt"
            code, output, _ = self.run_json([
                sys.executable,
                str(GTP),
                "--issue-url",
                ISSUE_URL,
                "--gtp-command",
                str(fake),
            ], environment=environment)
            self.assertEqual(0, code)
            self.assertEqual("halt", output["gtp_projection"]["state"])

            environment["FAKE_GTP_MODE"] = "incomplete"
            code, output, _ = self.run_json([
                sys.executable,
                str(GTP),
                "--issue-url",
                ISSUE_URL,
                "--gtp-command",
                str(fake),
            ], environment=environment)
            self.assertEqual(2, code)
            self.assertEqual("acquisition_incomplete", output["findings"][0]["kind"])
            self.assertIsNone(output["gtp_projection"]["state"])

    def test_private_gtp_bridge_does_not_output_token(self) -> None:
        token = "private-test-token-value"
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            profile = self.write_json(directory, "profile.json", self.actor_profile())
            environment = os.environ.copy()
            environment.update({
                "FAKE_GTP_MODE": "unmanaged",
                "FAKE_GTP_REQUIRE_TOKEN": "1",
                "FAKE_GTP_TOKEN": token,
                "GH_TOKEN": "wrong-ambient-value",
                "GITHUB_TOKEN": "wrong-ambient-value",
            })
            completed = subprocess.run(
                [
                    sys.executable,
                    str(GTP),
                    "--issue-url",
                    ISSUE_URL,
                    "--gtp-command",
                    str(self.fake_gtp(directory)),
                    "--private",
                    "--profile",
                    str(profile),
                    "--gh-command",
                    str(self.fake_gh(directory)),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
                timeout=30,
            )
            self.assertEqual(0, completed.returncode)
            self.assertNotIn(token, completed.stdout + completed.stderr)
            self.assertNotIn("wrong-ambient-value", completed.stdout + completed.stderr)

    def test_publication_operation_does_not_echo_forbidden_values(self) -> None:
        secret = "ghp_abcdefghijklmnopqrstuvwx"
        local_path = "/Users/example/private/credential"
        with tempfile.TemporaryDirectory() as raw:
            unsafe = Path(raw) / "unsafe.md"
            unsafe.write_text(
                f"token={secret}\npath={local_path}\n"
                '"reasoning_transcript": "hidden"\n"session_id": "runtime-7"\n',
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(PUBLICATION), str(unsafe)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(2, completed.returncode)
            self.assertNotIn(secret, completed.stdout + completed.stderr)
            self.assertNotIn(local_path, completed.stdout + completed.stderr)
            output = json.loads(completed.stdout)
            self.assertEqual("publication_screening", output["decision_scope"])
            self.assertEqual(
                {"secret_value", "local_absolute_path", "private_context", "ephemeral_runtime_id"},
                {item["kind"] for item in output["findings"]},
            )

    def acceptance_input(self, directory: Path, candidate: str) -> Path:
        return self.write_json(
            directory,
            "acceptance.json",
            {
                "task_ref": ISSUE_URL,
                "candidate_head_sha": candidate,
                "pr_ref": "https://github.com/example/project/pull/8",
                "human_actor": {"login": "human", "id": 202},
            },
        )

    def test_acceptance_readback_reports_native_states(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = self.acceptance_input(directory, candidate)
            pr = self.write_json(
                directory,
                "pr.json",
                {
                    "head": {"sha": candidate},
                    "merged_at": "2026-07-20T00:00:00Z",
                    "merged_by": {"login": "human", "id": 202},
                },
            )
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(0, code)
            self.assertEqual("observed", output["acceptance_state"])
            self.assertNotIn("verdict", output)

            value = json.loads(pr.read_text(encoding="utf-8"))
            value["head"]["sha"] = "b" * 40
            pr.write_text(json.dumps(value), encoding="utf-8")
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("stale", output["acceptance_state"])

            value["head"]["sha"] = candidate
            value["merged_by"] = {"login": "service", "id": 303}
            pr.write_text(json.dumps(value), encoding="utf-8")
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("conflicting", output["acceptance_state"])

            value["merged_at"] = None
            value["merged_by"] = None
            pr.write_text(json.dumps(value), encoding="utf-8")
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--pr-json",
                str(pr),
                "--allow-fixture",
            ])
            self.assertEqual(2, code)
            self.assertEqual("missing", output["acceptance_state"])
            self.assertEqual({"native_merge_missing"}, {item["kind"] for item in output["findings"]})

    def test_acceptance_fixture_is_never_live_evidence(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = self.acceptance_input(directory, candidate)
            pr = self.write_json(
                directory,
                "pr.json",
                {"head": {"sha": candidate}, "merged_at": None, "merged_by": None},
            )
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--pr-json",
                str(pr),
            ])
            self.assertEqual(2, code)
            self.assertIn("fixture_not_authoritative", {item["kind"] for item in output["findings"]})
            self.assertEqual("unavailable", output["acceptance_state"])

    def test_acceptance_live_route_removes_ambient_tokens(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = self.acceptance_input(directory, candidate)
            fake_gh = self.make_executable(
                directory,
                "acceptance-gh",
                """#!/usr/bin/env python3
import json
import os
import sys
if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
    raise SystemExit(8)
if sys.argv[1:] == ["api", "repos/example/project/pulls/8"]:
    print(json.dumps({
        "head": {"sha": os.environ["CANDIDATE"]},
        "merged_at": "2026-07-20T00:00:00Z",
        "merged_by": {"login": "human", "id": 202}
    }))
    raise SystemExit(0)
raise SystemExit(9)
""",
            )
            environment = os.environ.copy()
            environment.update({
                "CANDIDATE": candidate,
                "GH_TOKEN": "ambient-value",
                "GITHUB_TOKEN": "ambient-value",
            })
            code, output, _ = self.run_json([
                sys.executable,
                str(ACCEPTANCE),
                str(source),
                "--gh-command",
                str(fake_gh),
            ], environment=environment)
            self.assertEqual(0, code)
            self.assertEqual("observed", output["acceptance_state"])
            self.assertEqual("live_github_api", output["observation_source"])

    def test_generic_command_executor_is_absent(self) -> None:
        self.assertFalse((SKILL / "scripts" / "verify_wiring_evidence.py").exists())
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("verify_wiring_evidence.py", skill)
        for script in (SKILL / "scripts").rglob("*.py"):
            source = script.read_text(encoding="utf-8")
            self.assertNotIn("acquisition.command", source, script)
            self.assertNotIn("subprocess.run(\n                        command", source, script)

    def test_skill_bundle_is_repository_neutral(self) -> None:
        origin = subprocess.run(
            ("git", "config", "--get", "remote.origin.url"),
            check=False,
            capture_output=True,
            text=True,
            cwd=REPOSITORY,
        ).stdout.strip()
        identity = origin.removesuffix(".git").rsplit("/", 2)[-2:]
        identity_text = "/".join(identity) if len(identity) == 2 else ""
        for path in SKILL.rglob("*"):
            if (
                not path.is_file()
                or "tests" in path.parts
                or path.suffix not in {".json", ".md", ".py", ".yaml", ".yml"}
            ):
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("TODO", source, path)
            self.assertNotIn(str(REPOSITORY), source, path)
            if identity_text:
                self.assertNotIn(identity_text, source, path)

    def test_schema_and_domain_language_define_hub_boundary(self) -> None:
        schema = json.loads(
            (SKILL / "references" / "operation-receipt.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("verdict", schema["properties"])
        context = (REPOSITORY / "CONTEXT.md").read_text(encoding="utf-8")
        for term in (
            "AO Core",
            "Operation",
            "Adapter",
            "Operation Receipt",
            "Actor Observation",
            "Candidate Binding",
        ):
            self.assertIn(f"**{term}**", context)
        for implementation_term in ("scripts/", "bind_operation_result.py", "recover.py"):
            self.assertNotIn(implementation_term, context)

    def test_all_relative_markdown_links_resolve(self) -> None:
        link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for markdown in REPOSITORY.rglob("*.md"):
            source = markdown.read_text(encoding="utf-8")
            for target in link.findall(source):
                if target.startswith(("http://", "https://", "#", "<")):
                    continue
                relative = target.split("#", 1)[0]
                if relative:
                    self.assertTrue((markdown.parent / relative).resolve().exists(), f"{markdown}: {target}")


if __name__ == "__main__":
    unittest.main()
