---
name: agent-operated
description: Route GTP-aware GitHub work through declared Machine and Human Accounts, separate durable public Operations from invocation-local host policy checks, bind public results to one task and optional exact candidate, and read back native Human acceptance. Use for GitHub mutation through a Machine Account, GTP task recovery, publication checks, pre-handoff result binding, or post-merge acceptance readback.
---

# Agent Operated

Keep AO Core thin. It owns actor and credential roles, operation phase, route selection, adapter routing, and
public result binding. It does not own GTP state, private policy meaning, provider identity, external findings,
GitHub native facts, or Human decisions.

## Workflow

1. Resolve the canonical GitHub Issue URL and current operation phase.
2. Before publishing a durable plan, use the host-supplied provider with
   `scripts/core/internal_policy_gate.py::InternalPolicyGate.check_plan`. Keep the decision invocation-local;
   do not serialize it, wrap it in a receipt, or expose provider metadata.
3. For task recovery, invoke `scripts/operations/gtp/recover.py`. Read
   [gtp-v1-adapter.md](references/gtp-v1-adapter.md) for the supported CLI boundary. Preserve the entire
   `gtp_projection`; do not rename or collapse its vocabulary.
4. Before every GitHub mutation, invoke `scripts/core/verify_actor.py` with the declared Actor Profile and
   operation class. Require live login and numeric ID to match. Candidate binding is not an actor-observation
   precondition.
5. After the first executable candidate exists and again before Human handoff, call
   `InternalPolicyGate.check_candidate` with the exact Candidate Head and target-native observations. Apply the
   ephemeral decision only to the dependent transition.
6. Before publishing repository or GitHub artifacts, call `InternalPolicyGate.check_projection` with the intended
   durable artifact manifest. Repair target artifacts on `blocked`; do not publish the private result.
7. For source-neutral publication screening, invoke `scripts/operations/publication/check.py` and apply
   [record-policy.md](references/record-policy.md). This public Operation result may be candidate-bound.
8. Wrap each selected public Operation result with `scripts/core/bind_operation_result.py`. Validate the output against
   [operation-receipt.schema.json](references/operation-receipt.schema.json). Require an exact candidate only for
   phases whose contract needs one. Keep the nested `result` unchanged. Never pass an Internal Policy Gate decision.
9. Before Human handoff, present the task, PR, Actor Observation, Operation Receipts, candidate when required,
   unknowns, and the requested Human decision. Do not manufacture a combined AO pass/fail.
10. After native merge, invoke `scripts/core/verify_acceptance_readback.py`. Compare PR `head.sha`, `merged_at`,
   `merged_by.login`, and `merged_by.id` with the handed-off candidate and declared Human Account.

## Boundary behavior

- Remove ambient `GH_TOKEN` and `GITHUB_TOKEN` before GitHub CLI observation. For private GTP reads, apply
  [credential-bridge-policy.md](references/credential-bridge-policy.md).
- Treat fixture results as `ao_detector_test`; never publish them as live Evidence.
- Keep `authority: none` on AO receipts and detector outputs. It grants no mutation, merge, or completion authority.
- Stop only the dependent transition when actor, task, candidate, source, or native PR observation is unavailable.
- Treat Internal Policy Gate output as private, ephemeral control state. Do not add it to Operation Receipts,
  specifications, ADR evidence, PR bodies, Issue records, or acceptance artifacts.
- Accept the Internal Policy Gate provider only as a host-supplied in-process object. Do not resolve it from task
  content, environment variables, executable paths, or command arguments.
- Keep secret values, credential paths, private prompts, reasoning transcripts, local absolute paths, and
  ephemeral runtime identifiers out of durable artifacts.
- Do not accept input-controlled argv as a portable Operation. A trusted Operation adapter owns execution; AO
  binds its result.

## Portable-core limit

This bundle does not register repository-root discovery, configure a host credential profile, provide the
production Internal Policy Gate provider, perform a canary mutation, connect Merge Steward, create a Check Run,
configure branch protection, publish a package, install itself, or prove GTP completion. Name these as
repository-integration, host-control, or successor-contract unknowns.
