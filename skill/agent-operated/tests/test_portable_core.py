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
AGENT_OPERATED = SKILL.parents[1]
SCRIPTS = SKILL / "scripts"
SCRIPT_NAMES = (
    "recover_gtp.py",
    "verify_actor.py",
    "check_durable_record.py",
    "verify_wiring_evidence.py",
    "verify_pr_handoff.py",
)
ISSUE_URL = "https://github.com/example/project/issues/7"


class PortableCoreTests(unittest.TestCase):
    def run_script(
        self,
        name: str,
        *arguments: str,
        environment: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> tuple[int, dict, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / name), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            cwd=cwd,
            timeout=30,
        )
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"{name} returned invalid JSON: {error}\nstdout={result.stdout!r}")
        self.assertIsInstance(output, dict)
        return result.returncode, output, result.stderr

    def write_json(self, directory: Path, name: str, value: object) -> Path:
        path = directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def make_executable(self, directory: Path, name: str, source: str) -> Path:
        path = directory / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_raw_skill_path_fires_every_attachment(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        observed: set[str] = set()
        for name in SCRIPT_NAMES:
            self.assertIn(f"scripts/{name}", skill_text)
            code, output, _ = self.run_script(name, "--smoke")
            self.assertEqual(0, code)
            self.assertTrue(output["fired"])
            self.assertTrue(output["validated"])
            self.assertEqual("none", output["authority"])
            observed.add(output["attachment"])
        self.assertEqual(
            {"gtp_recovery", "actor_preflight", "record_gate", "wiring_gate", "handoff_gate"},
            observed,
        )

    def test_actor_requires_login_and_numeric_id(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            profile = self.write_json(
                directory,
                "profile.json",
                {
                    "profile_version": 1,
                    "machine_actor": {"login": "machine", "id": 101},
                    "human_actor": {"login": "human", "id": 202},
                    "human_only_operations": ["acceptance_decision"],
                    "merge_policy": "human_only",
                },
            )
            matched = self.write_json(directory, "matched.json", {"login": "machine", "id": 101})
            wrong = self.write_json(directory, "wrong.json", {"login": "machine", "id": 999})

            code, output, _ = self.run_script(
                "verify_actor.py",
                "--profile",
                str(profile),
                "--candidate-head",
                "a" * 40,
                "--user-json",
                str(matched),
                "--allow-fixture",
                "--observed-at",
                "2026-07-20T00:00:00Z",
            )
            self.assertEqual(0, code)
            self.assertEqual("proceed", output["verdict"])
            self.assertEqual({"login": "machine", "id": 101}, output["observed_actor"])
            self.assertEqual("ao_detector_test", output["decision_scope"])
            self.assertFalse(output["live_actor_verified"])

            code, output, _ = self.run_script(
                "verify_actor.py",
                "--profile",
                str(profile),
                "--candidate-head",
                "a" * 40,
                "--user-json",
                str(matched),
            )
            self.assertEqual(2, code)
            self.assertEqual("fixture_not_authoritative", output["findings"][0]["kind"])

            code, output, _ = self.run_script(
                "verify_actor.py",
                "--profile",
                str(profile),
                "--candidate-head",
                "a" * 40,
                "--user-json",
                str(wrong),
                "--allow-fixture",
            )
            self.assertEqual(2, code)
            self.assertEqual("blocked", output["verdict"])
            self.assertEqual("wrong_actor", output["findings"][0]["kind"])

            code, output, _ = self.run_script(
                "verify_actor.py",
                "--profile",
                str(profile),
                "--user-json",
                str(matched),
                "--allow-fixture",
            )
            self.assertEqual(2, code)
            self.assertEqual("candidate_head_required", output["findings"][0]["kind"])

    def test_record_gate_does_not_echo_forbidden_values(self) -> None:
        secret = "ghp_abcdefghijklmnopqrstuvwx"
        local_path = "/Users/example/private/credential"
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            safe = directory / "safe.md"
            safe.write_text("candidate head: " + "a" * 40 + "\n", encoding="utf-8")
            unsafe = directory / "unsafe.md"
            unsafe.write_text(
                f"token={secret}\npath={local_path}\n"
                '"reasoning_transcript": "hidden"\n"session_id": "runtime-7"\n',
                encoding="utf-8",
            )

            code, output, _ = self.run_script("check_durable_record.py", str(safe))
            self.assertEqual(0, code)
            self.assertEqual("proceed", output["verdict"])

            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "check_durable_record.py"), str(unsafe)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(2, result.returncode)
            output = json.loads(result.stdout)
            self.assertEqual("blocked", output["verdict"])
            combined = result.stdout + result.stderr
            self.assertNotIn(secret, combined)
            self.assertNotIn(local_path, combined)
            self.assertEqual(
                {"secret_value", "local_absolute_path", "private_context", "ephemeral_runtime_id"},
                {item["kind"] for item in output["findings"]},
            )

    def fake_gtp(self, directory: Path) -> Path:
        return self.make_executable(
            directory,
            "fake-gtp",
            """#!/usr/bin/env python3
import json
import os
import sys
if sys.argv[1:] == ["--version"]:
    print(os.environ.get("FAKE_GTP_VERSION", "1.0.1"))
    raise SystemExit(0)
if sys.argv[1] != "status":
    raise SystemExit(9)
issue = sys.argv[2]
mode = os.environ.get("FAKE_GTP_MODE", "halt")
if os.environ.get("FAKE_GTP_REQUIRE_TOKEN") == "1" and os.environ.get("GITHUB_TOKEN") != os.environ.get("FAKE_GTP_TOKEN"):
    raise SystemExit(8)
state = None if mode == "incomplete" else mode
value = {
    "gtp": "1.0",
    "command": "status",
    "issue_url": issue,
    "state": state,
    "halt_reason": "invalid_binding" if mode == "halt" else None,
    "next_action": "retry_acquisition" if mode == "incomplete" else "inspect_halt" if mode == "halt" else "post_contract",
    "primary_url": issue,
    "authority": "none",
    "acquisition": "incomplete" if mode == "incomplete" else "complete"
}
print("状態: " + (state or "不明"))
print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(2 if mode == "incomplete" else 0)
""",
        )

    def fake_gh(self, directory: Path) -> Path:
        return self.make_executable(
            directory,
            "fake-gh",
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

    def test_gtp_halt_and_acquisition_error_remain_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            fake = self.fake_gtp(directory)
            environment = os.environ.copy()
            environment["FAKE_GTP_MODE"] = "halt"
            code, output, _ = self.run_script(
                "recover_gtp.py",
                "--issue-url",
                ISSUE_URL,
                "--gtp-command",
                str(fake),
                environment=environment,
            )
            self.assertEqual(0, code)
            self.assertEqual("proceed", output["verdict"])
            self.assertEqual("halt", output["gtp_projection"]["state"])

            environment["FAKE_GTP_MODE"] = "incomplete"
            code, output, _ = self.run_script(
                "recover_gtp.py",
                "--issue-url",
                ISSUE_URL,
                "--gtp-command",
                str(fake),
                environment=environment,
            )
            self.assertEqual(2, code)
            self.assertEqual("blocked", output["verdict"])
            self.assertEqual("acquisition_incomplete", output["findings"][0]["kind"])
            self.assertIsNone(output["gtp_projection"]["state"])

    def test_gtp_adapter_rejects_version_and_does_not_echo_invalid_url(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            fake = self.fake_gtp(directory)
            environment = os.environ.copy()
            environment["FAKE_GTP_VERSION"] = "9.9.9"
            code, output, _ = self.run_script(
                "recover_gtp.py",
                "--issue-url",
                ISSUE_URL,
                "--gtp-command",
                str(fake),
                environment=environment,
            )
            self.assertEqual(2, code)
            self.assertEqual("incompatible_gtp_version", output["findings"][0]["kind"])

            invalid = "https://github.com/example/project/issues/7?token=private-value"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "recover_gtp.py"),
                    "--issue-url",
                    invalid,
                    "--gtp-command",
                    str(fake),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(2, result.returncode)
            self.assertNotIn("private-value", result.stdout + result.stderr)

    def test_private_gtp_bridge_never_outputs_token(self) -> None:
        token = "private-test-token-value"
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            fake_gtp = self.fake_gtp(directory)
            fake_gh = self.fake_gh(directory)
            profile = self.write_json(
                directory,
                "profile.json",
                {
                    "profile_version": 1,
                    "machine_actor": {"login": "machine", "id": 101},
                    "human_actor": {"login": "human", "id": 202},
                    "human_only_operations": ["acceptance_decision"],
                    "merge_policy": "human_only",
                },
            )
            environment = os.environ.copy()
            environment.update(
                {
                    "FAKE_GTP_MODE": "unmanaged",
                    "FAKE_GTP_REQUIRE_TOKEN": "1",
                    "FAKE_GTP_TOKEN": token,
                    "GH_TOKEN": "wrong-ambient-value",
                    "GITHUB_TOKEN": "wrong-ambient-value",
                }
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "recover_gtp.py"),
                    "--issue-url",
                    ISSUE_URL,
                    "--gtp-command",
                    str(fake_gtp),
                    "--private",
                    "--profile",
                    str(profile),
                    "--gh-command",
                    str(fake_gh),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
                timeout=30,
            )
            self.assertEqual(0, result.returncode)
            self.assertEqual("proceed", json.loads(result.stdout)["verdict"])
            self.assertNotIn(token, result.stdout + result.stderr)
            self.assertNotIn("wrong-ambient-value", result.stdout + result.stderr)

    def initialize_candidate_repository(self, directory: Path) -> str:
        (directory / "scripts").mkdir()
        (directory / "scripts" / "tool.py").write_text("print('tool')\n", encoding="utf-8")
        (directory / "SKILL.md").write_text("run scripts/tool.py\n", encoding="utf-8")
        commands = (
            ("git", "init", "-q"),
            ("git", "config", "user.name", "Test"),
            ("git", "config", "user.email", "test@example.invalid"),
            ("git", "add", "SKILL.md", "scripts/tool.py"),
            ("git", "commit", "-qm", "candidate"),
        )
        for command in commands:
            subprocess.run(command, cwd=directory, check=True, capture_output=True, text=True)
        return subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=directory,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_wiring_evidence_uses_real_candidate_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            repository = directory / "repository"
            repository.mkdir()
            candidate = self.initialize_candidate_repository(repository)
            evidence = self.write_json(
                directory,
                "evidence.json",
                {
                    "task_ref": ISSUE_URL,
                    "candidate_head_sha": candidate,
                    "attachment_point": "sample",
                    "artifact_path": "scripts/tool.py",
                    "registration": {"path": "SKILL.md", "contains": "scripts/tool.py"},
                    "acquisition": {
                        "kind": "local_command",
                        "command": [sys.executable, "-c", "print('AO_OK')"],
                        "expected_exit": 0,
                        "stdout_contains": "AO_OK",
                    },
                },
            )
            code, output, _ = self.run_script(
                "verify_wiring_evidence.py",
                str(evidence),
                "--repository",
                str(repository),
            )
            self.assertEqual(0, code)
            self.assertEqual("proceed", output["verdict"])
            self.assertTrue(output["required"])
            self.assertEqual("local_command", output["observation_source"])
            self.assertTrue(all(output["states"].values()))

            value = json.loads(evidence.read_text(encoding="utf-8"))
            value["acquisition"]["stdout_contains"] = "missing"
            evidence.write_text(json.dumps(value), encoding="utf-8")
            code, output, _ = self.run_script(
                "verify_wiring_evidence.py",
                str(evidence),
                "--repository",
                str(repository),
            )
            self.assertEqual(1, code)
            self.assertTrue(output["states"]["fired"])
            self.assertFalse(output["states"]["validated"])
            self.assertEqual("repair_then_proceed", output["verdict"])

            value["acquisition"]["stdout_contains"] = "AO_OK"
            evidence.write_text(json.dumps(value), encoding="utf-8")
            (repository / "scripts" / "tool.py").write_text("print('dirty')\n", encoding="utf-8")
            code, output, _ = self.run_script(
                "verify_wiring_evidence.py",
                str(evidence),
                "--repository",
                str(repository),
            )
            self.assertEqual(2, code)
            self.assertFalse(output["states"]["fired"])
            self.assertIn("repository_not_clean", {item["kind"] for item in output["findings"]})

    def handoff(self, candidate: str) -> dict:
        return {
            "task_ref": ISSUE_URL,
            "actor_profile_ref": "https://github.com/example/project/blob/" + candidate + "/profile.json",
            "candidate_head_sha": candidate,
            "actor_evidence": {
                "decision_scope": "ao_detector_test",
                "candidate_head_sha": candidate,
                "observation_source": "fixture",
                "live_actor_verified": False,
                "verdict": "proceed",
                "authority": "none",
            },
            "validation_evidence": {
                "decision_scope": "ao_detector_test",
                "candidate_head_sha": candidate,
                "observation_source": "fixture",
                "verdict": "proceed",
                "authority": "none",
            },
            "wiring_evidence": {
                "required": True,
                "decision_scope": "ao_detector_test",
                "candidate_head_sha": candidate,
                "observation_source": "fixture",
                "states": {"present": True, "attached": True, "fired": True, "validated": True},
                "verdict": "proceed",
                "authority": "none",
            },
            "human_decision_requested": "acceptance_decision",
            "human_actor": {"login": "human", "id": 202},
            "pr_ref": "https://github.com/example/project/pull/8",
        }

    def test_handoff_readiness_and_acceptance_are_separate(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            data = self.handoff(candidate)
            path = self.write_json(directory, "handoff.json", data)
            pr = {"head": {"sha": candidate}, "merged_at": None, "merged_by": None}
            pr_path = self.write_json(directory, "pr.json", pr)
            code, output, _ = self.run_script(
                "verify_pr_handoff.py",
                str(path),
                "--phase",
                "readiness",
                "--pr-json",
                str(pr_path),
                "--allow-fixture",
            )
            self.assertEqual(0, code)
            self.assertEqual("proceed", output["verdict"])
            self.assertEqual("none", output["authority"])
            self.assertEqual("ao_detector_test", output["decision_scope"])

            code, output, _ = self.run_script(
                "verify_pr_handoff.py",
                str(path),
                "--phase",
                "readiness",
                "--pr-json",
                str(pr_path),
            )
            self.assertEqual(2, code)
            self.assertIn("fixture_not_authoritative", {item["kind"] for item in output["findings"]})

            pr["head"]["sha"] = "b" * 40
            pr_path.write_text(json.dumps(pr), encoding="utf-8")
            code, output, _ = self.run_script(
                "verify_pr_handoff.py",
                str(path),
                "--phase",
                "readiness",
                "--pr-json",
                str(pr_path),
                "--allow-fixture",
            )
            self.assertEqual(2, code)
            self.assertEqual("stale_pr_head", output["findings"][0]["kind"])

            data = self.handoff(candidate)
            path.write_text(json.dumps(data), encoding="utf-8")
            pr = {
                "head": {"sha": candidate},
                "merged_at": "2026-07-20T00:00:00Z",
                "merged_by": {"login": "human", "id": 202},
            }
            pr_path.write_text(json.dumps(pr), encoding="utf-8")
            code, output, _ = self.run_script(
                "verify_pr_handoff.py",
                str(path),
                "--phase",
                "acceptance_readback",
                "--pr-json",
                str(pr_path),
                "--allow-fixture",
            )
            self.assertEqual(0, code)
            self.assertEqual("proceed", output["verdict"])

            pr["merged_by"] = {"login": "service", "id": 303}
            pr_path.write_text(json.dumps(pr), encoding="utf-8")
            code, output, _ = self.run_script(
                "verify_pr_handoff.py",
                str(path),
                "--phase",
                "acceptance_readback",
                "--pr-json",
                str(pr_path),
                "--allow-fixture",
            )
            self.assertEqual(2, code)
            self.assertIn("wrong_merge_actor", {item["kind"] for item in output["findings"]})

    def test_handoff_does_not_echo_invalid_references(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            data = self.handoff(candidate)
            data["task_ref"] = "secret-task-reference"
            data["actor_profile_ref"] = "secret-profile-reference"
            path = self.write_json(directory, "handoff.json", data)
            pr_path = self.write_json(
                directory,
                "pr.json",
                {"head": {"sha": candidate}, "merged_at": None, "merged_by": None},
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "verify_pr_handoff.py"),
                    str(path),
                    "--pr-json",
                    str(pr_path),
                    "--allow-fixture",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(2, result.returncode)
            self.assertNotIn("secret-task-reference", result.stdout + result.stderr)
            self.assertNotIn("secret-profile-reference", result.stdout + result.stderr)

    def test_handoff_rejects_unscoped_boolean_evidence(self) -> None:
        candidate = "a" * 40
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            data = self.handoff(candidate)
            data["actor_evidence"] = {"verified": True}
            data["validation_evidence"] = {"passed": True}
            data["wiring_evidence"] = {"required": True, "fired": True, "validated": True}
            path = self.write_json(directory, "handoff.json", data)
            pr_path = self.write_json(
                directory,
                "pr.json",
                {"head": {"sha": candidate}, "merged_at": None, "merged_by": None},
            )
            code, output, _ = self.run_script(
                "verify_pr_handoff.py",
                str(path),
                "--phase",
                "readiness",
                "--pr-json",
                str(pr_path),
                "--allow-fixture",
            )
            self.assertEqual(2, code)
            self.assertEqual(
                {"invalid_actor_evidence", "invalid_validation_evidence", "invalid_wiring_evidence"},
                {item["kind"] for item in output["findings"]},
            )

    def test_handoff_accepts_direct_wiring_detector_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            repository = directory / "repository"
            repository.mkdir()
            candidate = self.initialize_candidate_repository(repository)
            evidence = self.write_json(
                directory,
                "evidence.json",
                {
                    "task_ref": ISSUE_URL,
                    "candidate_head_sha": candidate,
                    "attachment_point": "sample",
                    "artifact_path": "scripts/tool.py",
                    "registration": {"path": "SKILL.md", "contains": "scripts/tool.py"},
                    "acquisition": {
                        "kind": "local_command",
                        "command": [sys.executable, "-c", "print('AO_OK')"],
                        "expected_exit": 0,
                        "stdout_contains": "AO_OK",
                    },
                },
            )
            code, wiring, _ = self.run_script(
                "verify_wiring_evidence.py",
                str(evidence),
                "--repository",
                str(repository),
            )
            self.assertEqual(0, code)

            handoff = self.handoff(candidate)
            handoff["actor_evidence"] = {
                "decision_scope": "ao_conformance",
                "candidate_head_sha": candidate,
                "observation_source": "live_github_api",
                "live_actor_verified": True,
                "verdict": "proceed",
                "authority": "none",
            }
            handoff["validation_evidence"] = {
                "decision_scope": "ao_conformance",
                "candidate_head_sha": candidate,
                "observation_source": "live_acquisition",
                "verdict": "proceed",
                "authority": "none",
            }
            handoff["wiring_evidence"] = wiring
            handoff_path = self.write_json(directory, "handoff.json", handoff)
            fake_gh = self.make_executable(
                directory,
                "handoff-gh",
                """#!/usr/bin/env python3
import json
import os
import sys
if sys.argv[1:] == ["api", "repos/example/project/pulls/8"]:
    print(json.dumps({"head": {"sha": os.environ["CANDIDATE"]}, "merged_at": None, "merged_by": None}))
    raise SystemExit(0)
raise SystemExit(9)
""",
            )
            environment = os.environ.copy()
            environment["CANDIDATE"] = candidate
            code, output, _ = self.run_script(
                "verify_pr_handoff.py",
                str(handoff_path),
                "--phase",
                "readiness",
                "--gh-command",
                str(fake_gh),
                environment=environment,
            )
            self.assertEqual(0, code)
            self.assertEqual("proceed", output["verdict"])
            self.assertEqual("live_github_api", output["observation_source"])
            self.assertEqual("caller_provided_detector_projection", output["evidence_input_trust"])

    def test_skill_bundle_is_repository_neutral_and_has_no_template_markers(self) -> None:
        local_repository = str(Path.cwd())
        origin = subprocess.run(
            ("git", "config", "--get", "remote.origin.url"),
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        repository_identity = origin.removesuffix(".git").rsplit("/", 2)[-2:]
        repository_identity_text = "/".join(repository_identity) if len(repository_identity) == 2 else ""
        for path in SKILL.rglob("*"):
            if not path.is_file() or "tests" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("TODO", source, path)
            if repository_identity_text:
                self.assertNotIn(repository_identity_text, source, path)
            self.assertNotIn(local_repository, source, path)

    def test_skill_name_schema_and_domain_glossary_are_portable(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual("agent-operated", SKILL.name)
        self.assertRegex(skill_text, r"(?m)^name: agent-operated$")
        schema = json.loads((SKILL / "references" / "actor-profile.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        context = (AGENT_OPERATED / "CONTEXT.md").read_text(encoding="utf-8")
        for implementation_term in ("scripts/", ".github/", "recover_gtp.py", "verify_actor.py"):
            self.assertNotIn(implementation_term, context)

    def test_all_relative_markdown_links_resolve(self) -> None:
        link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for markdown in AGENT_OPERATED.rglob("*.md"):
            source = markdown.read_text(encoding="utf-8")
            for target in link.findall(source):
                if target.startswith(("http://", "https://", "#", "<")):
                    continue
                relative = target.split("#", 1)[0]
                if relative:
                    self.assertTrue((markdown.parent / relative).resolve().exists(), f"{markdown}: {target}")


if __name__ == "__main__":
    unittest.main()
