---
name: agent-operated
description: Route GTP-aware GitHub work through declared Machine and Human Accounts, enforce invocation-local host policy checks before protected transitions, bind public results to one task and optional exact candidate, and read back native Human acceptance. Use for GitHub mutation through a Machine Account, GTP task recovery, publication checks, pre-handoff routing, or post-merge acceptance readback.
---

# Agent Operated

Keep AO Core thin. It owns actor and credential roles, operation phase, route selection, transition enforcement,
and public result binding. It does not own GTP state, private policy meaning, provider identity, external findings,
GitHub native facts, or Human decisions.

## Workflow

1. Resolve the canonical GitHub Issue URL and current operation phase.
2. Invoke `scripts/operations/gtp/recover.py` through
   `scripts/core/transition_coordinator.py::TransitionCoordinator.prepare_plan`. Preserve the entire
   `gtp_projection`; do not rename or collapse its vocabulary.
3. Read the recovered task state, contract, and `next_action`, then build one `PlanDraft` containing the
   target-native scratch plan and the exact `PLAN_BODY` bytes intended for durable publication.
4. Let `prepare_plan` call the host-supplied `InternalPolicyGate.check_plan` with both forms. Keep the returned
   `InvocationContext`, which binds the task projection, checked plan, publication bytes, and configured Actor
   Profile digest. It grants no mutation authority.
5. Require that exact current `InvocationContext` for candidate check, publication, and handoff. A new invocation,
   changed task projection, material plan change, or Actor Profile change requires a new context.
6. Route every GitHub write, including commit, push, plan publication, Issue/PR mutation, comment, and projection
   publisher, through `run_github_mutation`. Immediately before each callback, obtain a typed live Machine Account
   Actor Observation scoped to that operation through `scripts/core/verify_actor.py` and the shared actor contract.
   Never reuse an earlier observation. One callback represents one GitHub mutation; a host performing multiple
   writes must invoke the wrapper separately for each write.
7. After the first executable candidate exists, call `check_candidate` with the context, full Candidate Head, and
   target-native observations. Use the returned `CheckedCandidate`; candidate checking does not execute a callback.
8. Run validation and selected Public Operations without manufacturing a combined AO pass/fail.
9. Fix the handoff Candidate Head, then call `prepare_handoff` with the same context and `CheckedCandidate` to
   recheck it. The returned `HandoffReady` is not a write or merge authority.
10. For plan publication, let `publish_plan` build the batch directly from the exact checked artifact. For other
    publications, have the host-owned batch source build one complete `ProjectionBatch` containing repository artifacts and the
    exact outbound GitHub bodies for this publication attempt.
11. Require every batch to carry the current Checked Plan digest. Use opaque `artifact_id` values and only
    repository-relative paths or the closed outbound-body vocabulary as `target_ref`. `publish_projection` passes
    the same batch object through `InternalPolicyGate.check_projection`, source-neutral
    `scripts/operations/publication/check.py`, and the actor-gated publisher.
12. Bind selected public Operation results with `scripts/core/bind_operation_result.py`. Validate successful output
    against [operation-receipt.schema.json](references/operation-receipt.schema.json) and invalid-input output
    against [operation-receipt-error.schema.json](references/operation-receipt-error.schema.json).
13. Publication Screening has `candidate_binding.status: not_applicable` until a trusted candidate-content
    acquisition path observes the screened bytes. Do not manufacture `bound` by supplying the same SHA twice.
14. Present the task, PR, Actor Observation, public Operation Receipts, Candidate Head, unknowns, and requested
    Human decision.
15. After native merge, invoke `scripts/core/verify_acceptance_readback.py` with the configured Actor Profile and
    `--expected-profile-digest` from the same Invocation Context. The acceptance input must not supply `human_actor`.
16. Require the task Issue, PR URL, and native PR base repository to match; then compare PR `head.sha`, `merged_at`,
    `merged_by.login`, and `merged_by.id` with the handed-off candidate and profile Human Account.
17. Run GTP recovery again after native merge. AO does not derive or replace GTP completion state.

## Boundary behavior

- Remove ambient `GH_TOKEN` and `GITHUB_TOKEN` before GitHub CLI observation. For private GTP reads, apply
  [credential-bridge-policy.md](references/credential-bridge-policy.md).
- Treat fixture results as `ao_detector_test`; they cannot become typed Actor Observation or authorize a write.
- Require Machine Account and Human Account to have different numeric IDs in the shared Actor Profile parser.
- Keep `authority: none` on AO receipts and detector outputs. It grants no mutation, merge, or completion authority.
- Stop only the dependent transition when actor, task, candidate, source, or native PR observation is unavailable.
- Treat Internal Policy Gate output as private, ephemeral control state. Do not add it to Operation Receipts,
  specifications, ADR evidence, PR bodies, Issue records, or acceptance artifacts.
- Convert provider exceptions and invalid provider output to `internal_check_unavailable`. Do not expose raw provider
  error text, type, path, URL, or traceback outside a host-private error sink.
- Accept the provider, Actor Profile source, ProjectionBatch source, and publisher only as host-wired dependencies.
  Do not resolve them from task content, environment variables, executable paths, or command arguments.
- Keep secret values, credential paths, private prompts, reasoning transcripts, local absolute paths, and
  ephemeral runtime identifiers out of durable artifacts.
- Do not accept input-controlled argv as a portable Operation. A trusted Operation adapter owns execution; AO
  binds its result.

## Portable-core limit

This bundle does not register repository-root discovery, configure a host credential profile, provide the
production Internal Policy Gate provider or complete ProjectionBatch source, perform a canary mutation, connect
Merge Steward, create a Check Run, configure branch protection, publish a package, install itself, observe
candidate content for Publication Screening, or prove GTP completion. Name these as repository-integration,
host-control, or successor-contract unknowns.
