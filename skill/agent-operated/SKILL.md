---
name: agent-operated
description: Recover GTP v1 task state and apply AO actor, credential, publication, runtime-wiring, and exact-head handoff gates. Use for GitHub mutation performed through a declared Machine Account, GTP-managed task recovery, candidate-bound firing evidence, Human Account handoff, or post-merge acceptance readback.
---

# Agent Operated

Treat GTP recovery, AO conformance, and GitHub native facts as separate authorities. Run the attached
detectors; do not reproduce their decisions from prose.

## Workflow

1. Resolve the canonical GitHub Issue URL and whether the repository is public or private.
2. For a private Issue, read [credential-bridge-policy.md](references/credential-bridge-policy.md), verify
   the declared read actor, and run `scripts/recover_gtp.py --private`. For a public Issue, run it without a
   credential bridge.
3. Read `gtp_projection` without renaming `state`, `next_action`, `authority`, or `acquisition`. If acquisition
   is incomplete, stop only the transition that needs the missing observation. A GTP `halt` is an observed
   protocol state, not an acquisition failure.
4. Resolve the task scope, acceptance conditions, design references, actor profile, and named stop conditions.
   GTP output and AO output both retain `authority: none`; neither grants mutation permission.
5. For architecture, executable wiring, hook, workflow, entry-point, or implementation-order work, invoke the
   separate `doctrine-planner` skill before mutation.
6. Immediately before each GitHub mutation, run `scripts/verify_actor.py` against the declared Machine Account.
   Require both login and numeric ID to match.
7. Before publishing an Issue comment, PR body, Check Run text, or committed Evidence artifact, run
   `scripts/check_durable_record.py`. Never publish a blocked input or reproduce the matched value.
8. When runtime attachment is in scope, run `scripts/verify_wiring_evidence.py` with the task-selected real
   trigger and candidate head from a clean worktree checked out at that exact head. Keep `present`, `attached`,
   `fired`, and `validated` separate.
9. Before Human Account handoff, run `scripts/verify_pr_handoff.py --phase readiness`. Do not require a Human
   decision in this phase and do not interpret `proceed` as merge authority.
10. After a native merge, rerun live GTP recovery and run `scripts/verify_pr_handoff.py --phase
    acceptance_readback`. Compare PR `head.sha`, `merged_at`, and `merged_by` with the handed-off candidate and
    declared Human Account.

## Gate behavior

- Treat exit `0` as detector execution success only; inspect `verdict` and the embedded GTP projection.
- Treat exit `1` as `repair_then_proceed` where a script defines it.
- Treat exit `2` as a named dependent-transition block.
- Treat malformed input or an unavailable executable as a finding; do not infer the missing observation.
- Use `--allow-fixture` only inside deterministic tests. Fixture results use `decision_scope:
  ao_detector_test` and are never AO conformance or durable Evidence.
- Keep secret values, credential paths, private prompts, reasoning transcripts, local absolute paths, and
  ephemeral runtime identifiers out of durable artifacts.
- Never merge, close a task, or claim GTP completion from an AO detector verdict.

## Detector inputs

- Use [gtp-v1-adapter.md](references/gtp-v1-adapter.md) for supported GTP CLI and projection boundaries.
- Validate actor profiles against [actor-profile.schema.json](references/actor-profile.schema.json).
- Apply [record-policy.md](references/record-policy.md) to outbound durable content.
- Pass repository-relative paths and full 40-character lowercase commit SHAs to wiring and handoff detectors.
- Treat task and Evidence references as opaque durable references unless GitHub native readback is explicitly
  owned by the detector.
- Pass complete candidate-bound detector envelopes to the handoff gate. Caller-authored booleans such as
  `verified: true` or `fired: true` are not evidence.

## Portable-core limit

This bundle does not register repository-root discovery, install itself, create a Check Run, configure branch
protection, publish a package, or prove a full GTP Done-to-Human-merge path. Name these as repository-integration
unknowns until a separate contract supplies real attachment points and Evidence.
