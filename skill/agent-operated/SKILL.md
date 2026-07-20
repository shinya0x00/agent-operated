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
3. Read the recovered task state, contract, and `next_action`, then build one target-native scratch plan.
4. Let `prepare_plan` call the host-supplied `InternalPolicyGate.check_plan`. The returned `CheckedPlan` is
   invocation-local and grants no mutation authority.
5. Use that `CheckedPlan` before the earlier of durable plan publication or first implementation mutation. A new
   invocation, changed task projection, or material plan change requires a new `CheckedPlan`.
6. Immediately before the first GitHub mutation, let `run_first_mutation` obtain Actor Observation from the
   declared Actor Profile through `scripts/core/verify_actor.py`. Require live login and numeric ID to match before
   calling the mutation.
7. After the first executable candidate exists, call `continue_candidate` with its full Candidate Head and
   target-native observations. A blocked decision must leave the continuation callback unfired.
8. Run validation and selected Public Operations without manufacturing a combined AO pass/fail.
9. Fix the handoff Candidate Head, then call `handoff` to recheck that exact candidate. A blocked decision must
   leave the Human handoff callback unfired.
10. Have the host-owned batch source build one complete `ProjectionBatch` containing repository artifacts and the
    exact outbound GitHub bodies for this publication attempt.
11. Use `publish_projection` to pass the same batch object through `InternalPolicyGate.check_projection`,
    source-neutral `scripts/operations/publication/check.py`, and the publisher. Do not accept a task-controlled
    artifact list or rebuild content after checking.
12. Bind selected public Operation results with `scripts/core/bind_operation_result.py`. Validate successful output
    against [operation-receipt.schema.json](references/operation-receipt.schema.json) and invalid-input output
    against [operation-receipt-error.schema.json](references/operation-receipt-error.schema.json).
13. Publication Screening has `candidate_binding.status: not_applicable` until a trusted candidate-content
    acquisition path observes the screened bytes. Do not manufacture `bound` by supplying the same SHA twice.
14. Present the task, PR, Actor Observation, public Operation Receipts, Candidate Head, unknowns, and requested
    Human decision.
15. After native merge, invoke `scripts/core/verify_acceptance_readback.py` with the same configured Actor Profile
    source used for Actor Observation. The acceptance input must not supply `human_actor`.
16. Require the task Issue, PR URL, and native PR base repository to match; then compare PR `head.sha`, `merged_at`,
    `merged_by.login`, and `merged_by.id` with the handed-off candidate and profile Human Account.
17. Run GTP recovery again after native merge. AO does not derive or replace GTP completion state.

## Boundary behavior

- Remove ambient `GH_TOKEN` and `GITHUB_TOKEN` before GitHub CLI observation. For private GTP reads, apply
  [credential-bridge-policy.md](references/credential-bridge-policy.md).
- Treat fixture results as `ao_detector_test`; never publish them as live Evidence.
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
