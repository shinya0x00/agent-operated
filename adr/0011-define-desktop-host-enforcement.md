# ADR-0011: Codex DesktopをHost Enforcementのproduction surfaceとする

- Status: Accepted
- Date: 2026-07-23
- Decision owner: operator
- Scope: Issue #25
- Supersedes: ADR-0001のagent-selected skillとCLI canaryを中心にしたOperational Baseline
- Preserves: ADR-0006のPortable Core boundary、ADR-0008からADR-0010のpublic／private routeとtransition boundary
- Predecessor task: Issue #7、unmerged PR #24

## Context

Issue #7はmacOS Codex CLIを最初のproduction targetとするimmutable GTP Contractで開始した。しかし実際に日常利用するsurfaceは
Codex Desktopであり、CLIは主な運用入口ではない。CLI向けHost Guard、sandbox launcher、Workspace Leaseを完成しても、Desktopが
同じboundaryを使用しなければ「AOを呼び忘れてもwrite capabilityが残らない」という親Issueの目的を満たさない。

production surfaceの変更はIssue #7のmaterialなContract変更になるため、Contractを編集または追加せず、Issue #7をGTP Stopで
Issue #25へsupersedeし、PR #24をunmerged closeとした。

Codex Desktopのcurrent公開documentationから、次を観測した。

- Desktopのlocal commandはmacOSのOS-enforced sandbox内で動作し、`read-only`、`workspace-write`、writable roots等の概念を持つ。
- Desktop、CLI、IDE extensionはCodex configuration layerを共有する。
- user-level、managed、plugin-bundled lifecycle Hookを利用でき、`SessionStart`と`PreToolUse`を観測できる。
- current `PreToolUse` command Hookは、対応toolを`permissionDecision: "deny"`、legacy `decision: "block"`、またはexit code 2で実行前に拒否できる。
- `continue: false`は`PreToolUse`で非対応であり、このunsupported outputはHook failureとなってtool callが続く。
- 一部specialized tool pathはdefault Hook pathを外れ得るため、Hookは完全なenforcement boundaryではない。
- app-serverとSDKはthread／turn単位でcwdとsandbox presetを指定できる。
- DesktopはCodex-managed worktreeとpermission controlを持つ。

一方、既存Codex Desktop clientのthread開始へ外部Host Guard、canonical Issue Binding、Workspace Leaseを強制注入し、user操作やHook
無効化から独立してwritable rootを固定する公開extension pointは確認できていない。app-serverのcustom client capabilityが、そのまま
first-party Desktopへのextension pointであるとはClaimできない。

official evidence basisは次である。

- [Hooks](https://learn.chatgpt.com/docs/hooks)
- [Sandbox](https://learn.chatgpt.com/docs/sandboxing)
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Codex app-server](https://learn.chatgpt.com/docs/app-server)

documentationに記載がないことは実装不存在の証明ではない。未確認capabilityはabsenceではなくunknownとして扱う。

### Investigation status

| Category | Current state | Evidence boundary |
|---|---|---|
| documented fact | 上記4件の公開documentationを取得した | documentationが明記するsandbox、configuration、Hook、app-server capabilityまで |
| Desktop-native observation | 未取得 | 実Desktop sessionまたはhost processを観測したEvidenceはない |
| 未実施probe | Desktop version、registration point、trigger、oracleの取得 | いずれも未実施であり、値を推測しない |
| unknown | first-party DesktopへHost Guard、Issue Binding、Workspace Leaseを固定注入できるextension pointの有無 | 現在のunknownは公開documentation調査だけに基づく |

実Desktop surfaceでextension pointが存在しないとはClaimしない。

## Decision

実際のproduction surfaceをCodex Desktopとする。Codex CLIとcustom app-server clientはbring-up／validation surfaceとし、
component contract、negative case、typed boundaryを制御可能に検査する。ただし、そのEvidenceをDesktop Evidenceへ代用しない。

Host Enforcementのtarget designはPortable Coreをsupersedeしない。Portable CoreはAO Core、Operation、binding、portable testを所有する。
host-level Repository IntegrationはDesktop Host Attachment、process sandbox、Issue Binding、Workspace Lease、credential、broker、user-level
integrationを所有する。

### Issue requirement

「必ずIssue」はrepositoryまたはGitHubのmutationに適用する。

- Issueなしの調査、説明、repository readは許可する。
- file edit、create、delete、rename、commit、branch、push、Issue／PR mutationには一つのcanonical Issue Bindingを要求する。
- prompt、task本文、tool outputにIssue URLが含まれても自動bindingしない。
- repository identity、Issue repository、GTP state、expected branchを照合できなければread-onlyを維持する。

### Surface evidence boundary

| Surface | Role | Evidence may prove | Evidence must not prove |
|---|---|---|---|
| Codex Desktop | production | Desktop Host Guard、Hook observation、sandbox、Workspace Lease、credential boundary、failure matrix | 未観測component |
| Codex CLI | bring-up／validation | Host component interface、broker、sandbox profile、negative case、canary actor | Desktop attachmentまたは#6 completion |
| custom app-server client | bring-up／validation | thread／turn sandbox control、cwd、event stream、custom client integration | first-party Desktop injection point |
| unit／contract test | deterministic validation | schema、state mapping、lifecycle、failure token | native Desktop firing |

### Desktop Host Attachment admission

最初のruntime workは、Desktopの次のattachment pointをread-onlyで観測する。

1. thread開始前にHost Guardを発火できるregistration point
2. canonical Issue Bindingをprompt解析以外から渡せるcontrol path
3. current Desktop sandboxをunbound read-onlyまたはlease worktree一つへ固定できるAPI
4. Desktop worktree identityをIssue、branch、binding generation、expiryへ照合できるAPI
5. Desktop process、shell、connectorからMachine Account credentialを除外しbrokerへ限定するboundary

各pointについてregistration point、real trigger、observable oracleを取得できた場合だけ、feature depth zeroのdeny-only walking skeletonを
同じDesktop pathへ接続する。確認できないpointは`desktop_host_attachment_unavailable`としてunknown、必要なupstream API、Evidence request、
停止するtransitionを記録する。内部mockまたはCLI wrapperでDesktop attachment済みとClaimしない。

### Hook boundary

Hook Adapterは`SessionStart`でrepository、Issue Binding、GTP state、next Human actionを表示する。`PreToolUse`ではtool名とargumentを
観測してsource-neutralなfindingを提示し、対応toolをsupported deny shapeまたはexit code 2で実行前に拒否できる。

Hook未読込、disabled、trust未承認、Hook failure、specialized tool bypassでもwrite capabilityが増えないことを、Desktop sandbox、
Workspace Lease、broker-only credential boundaryで証明する。Hookは早期denyを持つUX guardとobservation pointだが、enforcementの正本ではない。

### Sandbox and Workspace Lease boundary

Workspace LeaseはRepository Identity、canonical Issue、expected branch、Desktop worktree identity、binding generation、expiryを束縛する。
GTP `halt`／terminal、unbind、branch変更、generation更新、expiry、handoff freezeで失効する。

Desktopへworkspace-writeを与えるのは、current threadのwritable rootをlease worktree一つへ固定でき、root repository、他worktree、home、
`.git`、git-common-dirをdenyできるextension pointを実観測した後だけとする。API未確認時はunbound read-only targetを維持し、CLI launcherへ
自動fallbackしない。

### Broker-only GitHub write

GitHub Mutation BrokerだけがMachine Account credentialを保持する。Desktop、CLI、raw shell、generic connector、repository processへ
credentialを渡さない。Broker Requestはsession、repository、Issue、binding generation、closed typed operationを毎回検証する。

public interfaceへ任意command、argv、raw REST path、raw GraphQL、credential値、local absolute path、private diagnosticを追加しない。
一つのaccepted requestを一つのnative mutationへ対応させる。

### Operational state and unknown

Host Operational Stateは公式GTP ProjectionからDesktop capabilityを選ぶhost projectionであり、GTP state machineを再実装しない。
Issueなしは`unbound`、GTP Acquisition Errorはstateなし、GTP `halt`は`halted`として一般writeを拒否する。

Desktop Host Attachment APIが未確認である間、次を維持する。

- CLI bring-up済みとDesktop production completionを区別する。
- CLI、custom client、fixture、task本文、environment、repository markerからDesktop activationを選ばない。
- parent #6、Desktop failure matrix、Workspace Lease acceptanceを未完了として扱う。
- unknown解消に必要なofficial APIまたは実Desktop observationをsuccessor runtime Issueのentry conditionにする。

## Consequences

### Positive

- 実際に使用するDesktopをcompletion boundaryにできる。
- CLIで先にcomponentを検証しつつ、Desktop Evidenceへの誤昇格を防げる。
- Hook APIのcurrent limitationを明示し、Hook failureがfail-open routeになる設計を避けられる。
- Desktop APIの不確実性をnamed unknownとして持ち、存在を推測したshim実装を避けられる。
- Issueなしread-onlyとIssue必須mutationの境界を利用者の実運用へ合わせられる。

### Negative and limits

- Desktop Host Attachmentの公開extension pointがなければ、#6の実運用完成はblockedのままになる。
- CLI bring-upが進んでもDesktop acceptanceを別に実施する必要がある。
- Desktop app updateでHook、sandbox、worktree、app-server behaviorが変化し得るため、exact versionとnative observationが必要になる。
- permission profileまたはuser configだけでは、Issue／branch／generationへ束縛された動的leaseを証明できない。
- managed Hookは組織管理surfaceを必要とし、個人環境で利用可能とは限らない。

## Alternatives considered

### Codex CLIをproduction surfaceのままにする

実際の利用surfaceを保護せず、CLI completionがDesktopの安全性を示さないため採用しない。

### DesktopからCLI wrapperを必ず起動する運用に変える

Desktopの通常threadを使わない別surfaceへ利用者を移し、現在のproduction workflowを検証しないため採用しない。

### `PreToolUse` Hookを唯一のdeny authorityにする

対応toolの事前拒否はsupportするが、Hookは無効化可能で、一部tool pathもHookを外れ得るため採用しない。

### app-server custom clientをDesktopとみなす

custom clientのsandbox controlは検証できるが、first-party Desktop clientと同一surfaceではないため採用しない。

### API未確認でもCLI implementationを先に完成扱いする

unknownを隠し、親Issueのproduction acceptanceを別surfaceのEvidenceで満たすため採用しない。

## Acceptance for this decision

- `DESIGN.md`と`PURPOSE.md`がDesktop production、CLI bring-up、Evidence非代替を明記する。
- `CONTEXT.md`がProduction Surface、Bring-up Surface、Desktop Host Attachment等の用語を所有する。
- Desktop Host Guard、Hook、sandbox、worktree、Workspace Leaseについてobserved factとunknownを分離する。
- canonical Issueなしのread-onlyを許可し、repository／GitHub mutationを禁止する。
- current `PreToolUse` Hookを唯一のenforcement boundaryにしない。
- Desktop attachment API未確認時に`desktop_host_attachment_unavailable`を残し、#6 completionをClaimしない。
- #20の最終failure matrixをDesktop native observationへ束縛する。
- Portable Coreをsupersedeせず、旧Operational Baselineだけを更新する。
- runtime code、credential設定、production provider、実GitHub mutation behaviorを変更しない。
