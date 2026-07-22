# ADR-0011: default-on Host EnforcementをmacOS Codex CLIから導入する

- Status: Accepted
- Date: 2026-07-23
- Decision owner: operator
- Scope: Issue #7
- Supersedes: ADR-0001のagent-selected skillと隔離CLI profileを中心にしたOperational Baseline
- Preserves: ADR-0006のPortable Core boundary、ADR-0008からADR-0010のpublic／private routeとtransition boundary
- Refines: ADR-0012のPre-activation Bootstrap Lane delivery state

## Context

現在のAOはPortable Core、agent-facing skill、live Actor Observation、GTP Operation、Internal Policy Gate port、
Projection Batch、Acceptance Readbackを持つ。しかしrepository mutationの入口は、agentがskillを選び、適切なcredential circuitを
使用することに依存している。Plugin／Hookを読み込まないprocess、raw shell、generic connector、Issue未束縛sessionについて、
hostがwrite capability自体を除去する境界はまだない。

Operational Baselineも、repository `AGENTS.md`からAOを発見し、隔離GitHub CLI profileでMachine Account canaryを行う
actor-separation skeletonを中心にしている。このbaselineはactor attributionを観測できるが、次を保証しない。

- AOを選択しなかったCodex processがread-onlyであること
- Machine Account credentialがbroker以外へ渡らないこと
- IssueとGTP stateへ束縛された専用worktreeだけがwritableであること
- Plugin／Hookがdisabledでも同じdeny boundaryが残ること
- broker、credential、GTP、private controlの取得不能時にmutation capabilityが残らないこと

一方、Portable Coreはrepository固有のinstallation、macOS sandbox、launchd、Keychain、Codex user configを意図的に所有しない。
Host EnforcementをPortable Coreへ吸収すると、この分離を壊し、外部GTP stateまたはprivate providerの意味までportable modelへ
複製する危険がある。

## Decision

AOのOperational Baselineを、user-levelでdefault-onとなるHost Enforcementへ変更する。最初のproduction targetは
macOS上のCodex CLIとする。Codex Desktopはunbound read-only protectionの対象に含めるが、Issue-bound workspace-write leaseの
受入対象には含めない。Desktopのwritable host APIを確認したsuccessor Issueなしにscopeを拡張しない。

このdecisionはPortable Coreをsupersedeしない。Portable CoreはAO Core、Operation、binding、portable testを所有し続ける。
Host EnforcementはRepository Integrationのhost側としてprocess launch、filesystem sandbox、user-level config、credential、
GitHub write capabilityを所有する。

### Default-on boundary

一度のuser-level installで全Git repositoryへ適用する。repository markerによるopt-in／opt-outを使わない。

- 通常の`codex`起動は常にunbound read-only、Machine Account credentialなし、workspace networkなしとする。
- `ao codex --issue ISSUE_URL`だけを明示binding付き起動経路とする。
- prompt、task本文、tool outputからURLを発見してもIssue Bindingへ昇格しない。
- remoteなし、複数GitHub remote候補、repository mismatch、GTP Acquisition Errorではread-onlyを維持する。
- 自動Issue作成、自動merge、raw shell fallbackを行わない。

### Host component boundary

Host Enforcementを次の責務へ分ける。

1. **Host Guard**はhost-observed process、Repository Identity、Issue Binding、Workspace Leaseからsandboxと起動可能なAdapterを決める。
2. **Plugin／Hook Adapter**はSessionStart／PreToolUseでstateと次のHuman actionを表示し、明白なdenyを早期に返す。
3. **Issue Binder**は明示操作、canonical Issue URL、Repository Identity、公式GTP Projectionからgeneration付きIssue Bindingを作る。
4. **Workspace Lease Manager**は`active`なbindingだけへ専用linked worktree一つの期限付きwritable rootを発行する。
5. **GitHub Mutation Broker**はMachine Account credentialを排他的に保持し、closedなtyped operationだけを一回のnative mutationへ変換する。

Plugin／HookはUX guardであり、enforcementの正本ではない。無効化可能なAdapterへcredential、lease発行authority、sandbox変更authorityを
与えない。write capabilityの正本はHost Guard、Workspace Lease、broker-only credential circuitである。

### Layout

公開repositoryの責務を次へ固定する。

| Path | Responsibility |
|---|---|
| `host/core/` | host-neutral contract、Repository Identity、Issue Binding、Host Operational State、operation policy、lease lifecycle |
| `host/broker/` | Broker Request／Result、typed dispatch、generation検証、GitHub transport port |
| `host/macos/` | installer、launchd、Keychain、Unix domain transport、sandbox、worktree launcher |
| `host/integrations/` | Codex、GTP Projection、private gate、publication、handoff/readback Adapter |
| `plugins/agent-operated-host/` | Codex SessionStart／PreToolUseのUX guard |

private providerの規則、identity、version、diagnostic、private error sink、Activation Latch storageはこのlayoutへ置かない。
それらはhost-private Repository IntegrationとIssue #16が所有する。

### GTP-derived operation policy

Host Operational StateはGTPの新しいstate machineではない。公式GTP Projectionを入力に、host capabilityを次へ写像する。

| Observation | Host state | Capability |
|---|---|---|
| Issueなし | `unbound` | read-only |
| 明示binding検証中 | `binding` | read-only |
| GTP `unmanaged` | `contract_required` | Contract用typed operationだけを候補化 |
| GTP `ready` | `start_required` | branch／Start用typed operationだけを候補化 |
| GTP `in_progress`かつbinding／branch一致 | `active` | typed broker policyとvalid Workspace Leaseの範囲だけ |
| checked candidate freeze | `handoff` | repository writeを拒否しHuman handoffだけ |
| GTP `halt` | `halted` | 一般write拒否、原因URL表示 |
| GTP `done`／`stopped` | `terminal` | mutation拒否 |
| Acquisition Error | stateなし | `gtp_unavailable`でdependent transition停止 |

GTP Record、transition、Evidence validationは再実装しない。`handoff`はGTP stateではなく、同じCandidate Headの差替えを防ぐ
host-local freezeである。

### Broker-only GitHub write

GitHub Mutation BrokerだけがMachine Account credentialを保持する。Codex、raw shell、generic connector、repository processへ
credentialを渡さない。broker clientはUnix domain transportを使い、launcherが発行する短命session capabilityを要求する。
capabilityはenvironment、argv、repository fileへ置かず、sandboxから読めないhost-private runtime fileをbroker adapterだけへ渡す。

production credentialはlaunchd serviceだけがmacOS Keychainから取得する。standalone broker processはlaunchd check-inなしに
credentialを取得できない。各requestでsession、repository、Issue、binding generation、typed operationを再検証する。

Broker Operationのclosed vocabularyは次をbaselineとする。

```text
post_issue_comment
create_task_branch
create_commit
push_branch
create_or_update_pull_request
publish_projection_artifact
```

任意command、argv、raw REST path、raw GraphQL、credential値、local absolute path、private diagnosticをpublic interfaceへ追加しない。
一つのaccepted Broker Requestを一つのnative mutationへ対応させ、native actor readbackとmutation accountingを可能にする。

### Issue-bound Workspace Lease

Workspace Leaseはopaque lease ID、Repository Identity、Issue、branch、専用linked worktree identity、binding generation、expiryを
束縛する。valid leaseをCodex processの唯一のwritable rootへ変換し、root repository、他worktree、home、`.git`、git-common-dirを
denyする。必要なGit operationはhost adapterまたはtyped brokerへ限定する。

GTP `halt`／terminal、Issue unbind、branch変更、generation更新、expiry、handoff freezeでleaseを失効する。既存sessionからの
再利用、duplicate lease、任意path、wrong branch、wrong worktreeを拒否する。

Human-only exceptionはhost admin commandだけが発行でき、repository、scopeとしてのallowed operations、reason、expiry、max uses、
Human Actor Observationを必須とする。prompt、environment、repository marker、Agent toolから作成、延長、scope拡張できない。

### Public contracts and findings

public contractは`RepositoryIdentity`、`IssueBinding`、`HostOperationalState`、`BrokerOperation`、`BrokerRequest`、`BrokerResult`、
`WorkspaceLease`、`HumanException`を持つ。fieldとclosed vocabularyのcurrent ownerは`DESIGN.md`、用語のownerは`CONTEXT.md`とする。

stable findingのbaselineは次である。

```text
issue_required
invalid_issue_url
repository_mismatch
github_remote_required
gtp_unavailable
gtp_halt
stale_binding
branch_mismatch
broker_unavailable
credential_unavailable
lease_required
lease_expired
internal_check_unavailable
projection_incomplete
publication_mismatch
stale_candidate
```

private diagnosticをfindingへ投影しない。取得不能とpolicy rejectionを同じGTP `halt`へ変換しない。

### Delivery bootstrap and implementation order

ADR-0012のPre-activation Bootstrap Laneを、PR作成前と作成後に分ける。

- PR作成前は対象branchのPR 0件を要求し、scope内file edit、commit、branch push、単一Draft PR作成だけを許可する。
- 最初のpush後は、そのDraft PR作成以外のmutationを許可しない。
- PR作成後は、同じIssue／branchの唯一のPRがDraftである間だけlaneを継続する。
- Ready、merge、別Issue、別branch、別repository、追加PR、scope拡張ではmutationを停止する。

Host Enforcementのfeature実装前に、全runtime attachmentを実登録するdeny-only walking skeletonを作る。feature depth zeroでは全操作を
stable findingで拒否し、実macOS sessionで各attachmentの発火とfilesystem／GitHub mutation 0件を観測する。後続Issueはこの実配線を
feature sliceとして埋め、内部境界をtest providerまたはmockへ置き換えない。

実装順序は、deny-only attachment、typed broker、exclusive credential circuit、repository discovery、Issue binding、Hook UX、
Workspace Lease、sandbox、lease invalidation、production private control、Projection Batch、handoff/readback、admission decision、
実環境failure matrixとする。各sliceは1 Issue = 1 branch = 1 PRを維持する。

## Consequences

### Positive

- agentがAOを手動選択しないprocessもhost boundaryの対象になる。
- Plugin／Hookがdisabledでもwrite capabilityを増やさない。
- filesystem writeとGitHub writeをWorkspace Leaseとtyped brokerへ分離できる。
- GTPを再実装せず、公式Projectionからhost capabilityを決められる。
- broker停止、credential取得不能、Issueなしでnative mutation 0件をacceptanceにできる。
- Portable Coreとhost-specific enforcementのcanonical ownerを分離したまま実装できる。

### Negative and limits

- macOS user-level installer、launchd、Keychain、sandbox、Codex configの保守が必要になる。
- Codex Desktopのlease-bound writeは、このdecisionだけでは受理できない。
- Host Operational StateはGTPとは別のcapability Projectionなので、外部stateとの混同を防ぐtestが必要になる。
- deny-only walking skeletonだけではbroker mutation、credential circuit、lease、production providerの完成をClaimできない。
- host-private runtime fileのconfidentialityとlifecycleは実macOS acceptanceで検証する必要がある。

## Alternatives considered

### Plugin／Hookを唯一のenforcement boundaryにする

ユーザーまたはruntimeが無効化でき、raw shellとgeneric connectorのcredential／filesystem capabilityを除去できないため採用しない。

### repository markerでopt-inする

未設定repositoryが無保護になり、default-onの目的を満たさないため採用しない。opt-out markerもAgentが作れる恒久例外になる。

### prompt内URLを自動bindingする

任意文章がpermissionへ昇格し、repository mismatchと意図しないIssue bindingを生むため採用しない。

### brokerをraw commandまたはAPI proxyにする

operation policyを迂回し、credentialを任意GitHub writeへ使える汎用executorになるため採用しない。

### Codex Desktopを最初のwritable targetにする

leaseを唯一のwritable rootへ変換できるhost APIをまだ確認していないため採用しない。read-only protectionだけを維持する。

### full Workspace Brokerを先行実装する

Issue-bound leaseで防げない名前付き事故と機械観測signalがまだないため採用しない。admission条件を満たした場合も実装はsuccessor Issueへ分離する。

## Acceptance for this decision

- `DESIGN.md`がHost Enforcement component、trust boundary、state、capability、failure behaviorを所有する。
- `PURPOSE.md`がdefault-on Host Enforcementをrequired outcomeとし、Portable Coreの目的を維持する。
- `CONTEXT.md`がHost Guard、Issue Binding、Workspace Lease、GitHub Mutation Broker等の用語を所有する。
- macOS Codex CLIを最初のproduction targetとし、Desktop writable supportをscope外にする。
- Plugin／HookをUX guardとし、sandbox、lease、credential boundaryをenforcementの正本にする。
- GitHub writeをtyped broker-only、workspace writeをIssue-bound leaseに分離する。
- Issueなし、remoteなし、GTP halt、broker／credential取得不能、Plugin disabledのfailure behaviorを定義する。
- Human-only exceptionにscope、理由、expiry、max uses、Human Actor Observationを要求する。
- Portable Coreをsupersedeせず、旧Operational Baselineだけを更新する。
- runtime code、credential設定、実GitHub mutationを変更しない。
