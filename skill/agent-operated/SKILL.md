---
name: agent-operated
description: Route GTP-aware GitHub work through declared Machine and Human Accounts, invoke phase-specific Operations, bind opaque results to one task and optional exact candidate, and read back native Human acceptance. Use for GitHub mutation through a Machine Account, GTP task recovery, publication checks, pre-handoff result binding, or post-merge acceptance readback.
---

# Agent Operated

Keep AO Core thin. It owns actor and credential roles, operation phase, adapter routing, and result binding. It
does not own GTP state, Doctrine Rule meaning, external findings, GitHub native facts, or Human decisions.

## Workflow

1. Resolve the canonical GitHub Issue URL and current operation phase.
2. For task recovery, invoke `scripts/operations/gtp/recover.py`. Read
   [gtp-v1-adapter.md](references/gtp-v1-adapter.md) for the supported CLI boundary. Preserve the entire
   `gtp_projection`; do not rename or collapse its vocabulary.
3. Before every GitHub mutation, invoke `scripts/core/verify_actor.py` with the declared Actor Profile and
   operation class. Require live login and numeric ID to match. Candidate binding is not an actor-observation
   precondition.
4. For publication screening, invoke `scripts/operations/doctrine/check_publication.py` and apply
   [record-policy.md](references/record-policy.md). Treat its verdict as a Doctrine Operation result only.
5. Wrap each selected Operation result with `scripts/core/bind_operation_result.py`. Validate the output against
   [operation-receipt.schema.json](references/operation-receipt.schema.json). Require an exact candidate only for
   phases whose contract needs one. Keep the nested `result` unchanged.
6. Before Human handoff, present the task, PR, Actor Observation, Operation Receipts, candidate when required,
   unknowns, and the requested Human decision. Do not manufacture a combined AO pass/fail.
7. After native merge, invoke `scripts/core/verify_acceptance_readback.py`. Compare PR `head.sha`, `merged_at`,
   `merged_by.login`, and `merged_by.id` with the handed-off candidate and declared Human Account.
8. For architecture, executable wiring, entry-point, workflow, or implementation-order work, invoke the separate
   `doctrine-planner` skill before mutation.

## Boundary behavior

- Remove ambient `GH_TOKEN` and `GITHUB_TOKEN` before GitHub CLI observation. For private GTP reads, apply
  [credential-bridge-policy.md](references/credential-bridge-policy.md).
- Treat fixture results as `ao_detector_test`; never publish them as live Evidence.
- Keep `authority: none` on AO receipts and detector outputs. It grants no mutation, merge, or completion authority.
- Stop only the dependent transition when actor, task, candidate, source, or native PR observation is unavailable.
- Keep secret values, credential paths, private prompts, reasoning transcripts, local absolute paths, and
  ephemeral runtime identifiers out of durable artifacts.
- Do not accept input-controlled argv as a portable Operation. A trusted Operation adapter owns execution; AO
  binds its result.

## Portable-core limit

This bundle does not register repository-root discovery, configure a host credential profile, perform a canary
mutation, connect Merge Steward, create a Check Run, configure branch protection, publish a package, install
itself, or prove GTP completion. Name these as repository-integration or successor-contract unknowns.
