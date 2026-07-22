# agent-operated Design

Status: pre-alpha design and implementation baseline

Supersession: [ADR-0001](adr/0001-redefine-agent-operated.md)

Later decisions: [ADR-0002](adr/0002-record-gtp-artifact-generation-provenance.md), [ADR-0003](adr/0003-require-host-sourced-model-identity.md), [ADR-0004](adr/0004-separate-handoff-readiness-and-human-acceptance.md), [ADR-0005](adr/0005-require-live-firing-evidence-acquisition.md), [ADR-0006](adr/0006-define-portable-core-boundary.md), [ADR-0007](adr/0007-define-operation-hub-boundary.md), [ADR-0008](adr/0008-separate-public-delivery-and-private-control.md), [ADR-0009](adr/0009-bind-private-control-to-transitions.md), [ADR-0010](adr/0010-bind-every-write-to-live-actor-and-invocation.md), [ADR-0011](adr/0011-define-default-on-host-enforcement.md), [ADR-0012](adr/0012-define-pre-activation-bootstrap-lane.md)

Language: Japanese is canonical

## 1. Scope

この文書はAOのcurrent designを所有する。AOは、AI agentのGitHub mutationをMachine Accountへ分離する
現在のOperationであり、作業phaseに応じてPublic Delivery RouteまたはPrivate Control Routeを選択できる個人用
Operation Hubである。

AOは統合対象の意味を内部化しない。AO Coreはroutingとbindingを所有し、外部正本または検査器の意味は
各Operationが保持する。repository固有のdiscovery、credential注入、workflow、settings、releaseは
Repository Integrationとして分離する。

## 2. Problem statement

agentがHuman Accountと同じGitHub principalを使用すると、GitHubのdurable recordだけでは人間とagentの
mutationを区別できない。さらに、外部resultとprivate control decisionを一つのAO総合判定またはReceiptへ
変換すると、AOが外部の第二のcanonical ownerになり、内部規則を公開成果物へ投影する。

AOは二つの問題を別々に扱う。

1. live GitHub actorを観測し、Machine AccountとHuman Accountを分離する。
2. phase-specificな公開Operation resultを、意味を変えずtaskと必要なCandidate Headへ束縛する。
3. private control decisionをinvocation-localに保ち、依存するphase transitionだけへ適用する。

## 3. Design principles

1. **Identity before every mutation** — 各write callbackの直前にlive actorを読み戻す。
2. **Stable and separate identity** — loginとnumeric actor IDをActor Profileへ固定し、MachineとHumanに異なるIDを要求する。
3. **Actor is not candidate** — Actor Observationの成立にCandidate Headを要求しない。
4. **Exact candidate when applicable** — candidate-dependentなresultだけをfull SHAへ束縛する。
5. **Route, do not absorb** — 外部の語彙、state、finding、authorityをAOの語彙へ変換しない。
6. **One canonical owner** — 同じFactをAOと外部正本で重複所有しない。
7. **No aggregate safety verdict** — 異なるOperation resultを一つのAO pass/failへ潰さない。
8. **No generic executor** — 実commandはtrusted Operation Adapterが所有し、AOはresultだけを束縛する。
9. **Human decision remains Human** — AOとMerge Stewardはmerge判断を代行しない。
10. **Public result, private control** — 公開Operation resultはReceiptへ束縛できるが、Internal Policy Gate
    decisionはdurable artifactへ保存しない。
11. **Host-fixed provider** — Internal Policy Gate providerをtask入力、環境変数、command pathから選択しない。
12. **Blocked means unfired** — private decisionが`blocked`なら依存するcallbackを呼ばない。
13. **Check what is published** — 一つのProjection Batchの同じbytesをcheck、screening、publishへ渡す。
14. **One invocation context** — protected transitionを同じtask、checked plan、Actor Profileへ束縛する。
15. **Fixture is never authority** — fixture、boolean、field不足のMappingをwrite preconditionとして受理しない。
16. **Default-on and fail-closed** — host attachmentはrepository markerを要求せず、必要なbinding、lease、broker、credentialを取得または検証できなければwrite capabilityを残さない。

## 4. Responsibility model

| Element | Canonical ownership | AO behavior |
|---|---|---|
| GTP | task contract、branch、PR、Evidence、task state | 公式ProjectionをGTP Operationから取得し、不変のresultとして束縛する |
| Merge Steward | PR受理report、deterministic findings、questions、UI | 対応Adapterが存在する場合にreport refとheadを束縛する |
| Internal Policy Gate provider | private rule、provider identity、version、非公開診断 | hostが固定したproviderをphase transition前に呼び、decisionをinvocation-localに扱う |
| AO | Actor Profile、credential role、operation phase、route selection、Operation Receipt、Candidate Binding | phaseに対応するrouteを選択し、公開resultだけをtaskへ束縛する |
| GitHub | actor、commit、ref、PR head、check、merge等のnative fact | actor、candidate、acceptanceの観測元として読む |
| Human Account | merge、保留、修正依頼等の最終判断 | AOはdecision requestを提示し、native resultをread backする |

## 5. AO Core

AO Coreは次の4責務だけを所有する。

1. actorとcredential role
2. operation phase
3. Public Delivery RouteとPrivate Control Routeの選択およびtransition enforcement
4. task・Candidate Head・Operation resultのbinding

Human acceptance readbackは、Human AccountとCandidate Bindingを扱うためAO Coreに含める。

AO CoreはGTP state、private rule、Internal Policy Gate provider、Merge Steward findings、GitHub native fact、
Human decision、汎用executor、独自task ledger、総合安全スコアを所有しない。

### 5.1 Actor Profile and Actor Observation

Actor Profileはsecretを含めず、少なくとも次を宣言する。

```yaml
profile_version: 1
machine_actor:
  login: agent-operated-bot
  id: 301814874
human_actor:
  login: shinya0x00
  id: 236178224
human_only_operations:
  - acceptance_decision
merge_policy: human_only
```

Actor Observationは一つのcredential circuitに対して`gh api user`相当を実行し、loginとnumeric IDを照合する。
Candidate Headが存在しないIssue作成、Contract投稿、branch準備等でもActor Observationは成立できる。
candidateが存在する場合は補助contextとして記録できるが、actor matchの成立条件にはしない。

Machine AccountとHuman Accountのnumeric IDは異ならなければならない。Actor Profileは一回だけcanonical digestへ固定し、
Actor ObservationとAcceptance Readbackは同じdigestを使用する。fixture outputは`ao_detector_test`のまま保持できるが、
typedなlive Actor Observationへ変換できず、GitHub Mutation Gateを通過しない。

GitHub Mutation Gateの一つのcallbackは一つのGitHub mutationだけを表す。hostが複数writeを行う場合はwriteごとにgateを
再実行し、publisher callback内へ未観測の追加writeを隠さない。

共有Machine Accountが証明するのはGitHub principalであり、model、runtime、process、sessionは証明しない。

### 5.2 Operation phase

portable baselineは次のclosed vocabularyを使用する。

- `task_recovery`
- `pre_mutation`
- `pre_publication`
- `pre_handoff`
- `post_merge`

phaseは実行順序とcandidate requirementを選ぶAO-owned contextであり、外部Operationのstateではない。

### 5.3 Adapter routing

Host Guardがdefault-onのprocess admissionを所有し、AO skillはadmission後のportableなphase routingを所有する。
repositoryの`AGENTS.md`やPlugin／Hookは状態とrouteを発見するProjectionになり得るが、write capability、
operation phase、routing順序を所有しない。

Adapterはtransportとversion compatibilityだけを所有する。外部resultのfield名、state、verdict、finding、
authorityを翻訳しない。Adapterが外部resultを取得できない場合、そのOperationに依存するtransitionだけを止める。

### 5.4 Operation Receipt

Operation Receiptは共通の外枠だけを持つ。

```json
{
  "receipt_version": 1,
  "operation": "gtp",
  "phase": "task_recovery",
  "task_ref": "https://github.com/OWNER/REPOSITORY/issues/1",
  "implementation_version": "1.0.1",
  "source_ref": "https://github.com/OWNER/REPOSITORY/issues/1",
  "candidate_binding": {
    "required": false,
    "status": "not_applicable",
    "candidate_head_sha": null,
    "observed_head_sha": null
  },
  "result": {},
  "findings": [],
  "authority": "none"
}
```

`candidate_binding.status`は次の意味を持つ。

| Status | Meaning |
|---|---|
| `not_applicable` | このphaseではcandidateを要求しない |
| `bound` | required candidateとobserved headが一致する |
| `stale` | 両方を取得したが一致しない |
| `unavailable` | required bindingの入力を取得できない |

Receipt自身は総合`verdict`を持たない。nested `result`に公開Operation固有の`verdict`が存在しても、AOは
変更も昇格も行わない。Internal Policy Gate decisionはOperation resultではなく、Receiptへ格納しない。

invalid binder inputはReceiptではない。`error_version`、`decision_scope: operation_receipt_binding`、
`error: invalid_input`、source-neutralな`findings`、`authority: none`だけを持つ専用error envelopeを返す。

## 6. Credential boundary

### 6.1 Machine mutation circuit

production Host Enforcementでは、launchdから起動されたGitHub Mutation BrokerだけがMachine Account credentialを取得する。
Codex subprocess、raw shell、generic connector、repository processへwrite-capable GitHub CLI profileまたはtokenを渡さない。

- broker processでもambient `GH_TOKEN`と`GITHUB_TOKEN`を除外する。
- production credentialはlaunchd check-in後にmacOS Keychainから取得する。
- Git remoteはHTTPSを使用し、URLへusernameまたはtokenを埋め込まない。
- 各typed requestの直前に、そのoperation class向けのActor Observationを再取得する。
- loginまたはnumeric IDが一致しなければmutationを停止し、client-side CLIへfallbackしない。

Portable CoreのActor Observation contractとdeterministic testは維持するが、隔離CLI profileをCodexへ注入する旧Operational
Baselineをproduction credential routeとして再利用しない。

commit author metadataとpush actorは異なるidentity surfaceである。repository-local identityを使う場合も、
push actorのnative readbackを代替しない。

### 6.2 Read-only consumer circuits

public readはcredentialなしを優先する。private read consumerは必要最小のread-only credentialを使用する。
AO mutation circuitのwrite credentialをMerge Steward等のread-only consumerへ渡さない。

### 6.3 GTP private-read bridge

GTP 1.0.1がprivate read tokenをenvironmentから取得するため、GTP OperationはMachine Account write credentialとは別の
host-owned read-only circuitから次の限定bridgeを使用する。

1. ambient tokenを除外する。
2. target repositoryへのreadだけを許すcredential sourceをhostで選択する。
3. GTP child processだけへ`GITHUB_TOKEN`として渡す。
4. token、credential path、raw stderrをoutputへ出さない。

read-only credentialを取得できないbridge failureはAcquisition Errorであり、GTP `halt`ではない。brokerのMachine Account
credentialをread bridgeまたはCodex environmentへexportしない。

## 7. Operations

### 7.1 GTP Operation

GTP Operationは公式`gtp status ISSUE_URL`を実行し、machine JSONを`gtp_projection`として保持する。
GTP Record、state machine、Evidence validationを再実装しない。

compatibility targetはCLI `1.0.1`、protocol projection `gtp: "1.0"`である。`state`、`halt_reason`、
`next_action`、`primary_url`、`acquisition`、`authority`を変換しない。

GTP `halt`は取得済みprotocol stateである。CLI exit 2、`state: null`、`acquisition: incomplete`は
Acquisition Errorとして分離する。

### 7.2 Publication Screening

Publication Screeningはsource-neutralな公開Operationである。secret-shaped value、credential location、private
context、local absolute path、ephemeral runtime IDをscreeningし、finding kindとlineだけを返してmatched valueを
再掲しない。

このOperationは公開適合全体またはsecret absenceを証明しない。trusted Adapterがexact candidateからscreen対象bytesを
取得するまではCandidate Bindingを`not_applicable`とする。callerがexpected SHAとobserved SHAへ同じ値を書いたことを
candidate observationへ昇格しない。

### 7.3 Merge Steward Adapter

Merge Steward接続はportable baselineに含めない。接続contractはcanonical endpoint、report schema、supported version、
read credentialを固定し、reportのPRとheadがCandidate Bindingに一致することだけをAOで確認する。

AOはMerge Steward findingsを再計算せず、独自`blocked`へ自動変換しない。

## 8. Internal Policy Gate

Internal Policy GateはOperationではない。Transition Coordinatorが次のtransitionでhost固定providerをin-processで呼ぶ。

1. `check_plan` — GTP recoveryからtarget-native planと公開予定のexact bytesを作った後、plan公開または実装mutationの早い方の前
2. `check_candidate` — 最初の実candidateが存在した後、およびHuman handoff前
3. `check_projection` — hostがrepository、PR、Issue、Receipt等の完全なProjection Batchを確定した後

providerはtask入力、環境変数、filesystem path、argvから解決しない。AOはprovider objectをhostから受け取り、
`proceed`または`blocked`とtarget-native findingだけをtransitionへ適用する。private rule、provider identity、version、
診断、provenanceをAOの公開data modelへ追加しない。

Gate decisionはinvocation-localであり、JSON serializer、CLI、Operation Receipt、acceptance Evidenceを持たない。
`blocked`は対象transitionのcallbackを呼ばず、repair後の新しいplan、candidate、projectionを再検査する。
provider exceptionまたはinvalid returnは`internal_check_unavailable`へ変換し、raw errorはhost-private sinkだけへ渡す。

GTP task projection、plan、plan公開予定bytesをcanonical digestへ束縛した`CheckedPlan`とActor Profile digestから
`InvocationContext`を作り、すべてのprotected transitionへ要求する。新しいinvocation、task projection変更、materialなplan変更、
Actor Profile変更は新しいcontextを要求する。どちらもmutation authorityではない。

`prepare_plan`を開始した時点で以前のInvocation ContextとChecked Candidateを失効させる。canonical GitHub Issue URLを
host recoveryより先に検査し、recovery、plan build、plan check、入力検査のいずれが失敗しても旧contextへ戻さない。
一つのInvocation Contextが保持できるcurrent Checked Candidateは一つだけである。current contextで新candidateの検査を
始めると旧tokenを先に失効させ、検査失敗時も復活させない。rollbackは過去headを再検査して新tokenを発行する。

plan publicationは`CheckedPlan`内のexact artifact bytesから直接Projection Batchを作る。一般Projection BatchはChecked Plan
digest、optional Candidate Head、uniqueなopaque artifact ID、public-safe target ref、immutable bytes、SHA-256 digestを持つ。
host-owned sourceが作った同じbatch objectをprivate check、Publication Screening、publisherへ渡し、publish直前にdigestを
再検査する。target refはrepository-relative pathまたはAOのclosed vocabularyに限定し、findingにはopaque artifact IDだけを出す。
portable coreはhost sourceが列挙したbatchの同一性を保証するが、production artifactの完全列挙自体はClaimしない。

## 9. Human handoff and acceptance

### 9.1 Handoff Readiness

Human Accountへ次を提示する。

- task reference
- PR reference
- Actor Observation
- selected Operation Receipts
- requiredな場合のCandidate Head
- unknownとunresolved finding
- Human Accountへ求めるdecision

このphaseでHuman decision、Approve、review comment、reaction、merge factを要求しない。Operation Receiptの存在は
merge authorityまたはtask completionを意味しない。

### 9.2 Acceptance Readback

通常laneは`merge_policy: human_only`とする。native merge後に次をread backする。

- expected Human Accountを、Invocation Contextと同じcontent digestを持つversioned Actor Profileから取得する。
- task Issue、PR URL、native PR base repositoryが一致する。
- PR `head.sha`がhandoff Candidate Headと一致する。
- `merged_at`が存在する。
- `merged_by.login`と`merged_by.id`がHuman Accountと一致する。

`merge_commit_sha`をCandidate Headの代用にしない。headが変わった場合、前のhandoffとdecisionをstaleとする。

Acceptance Readbackは`observed / missing / stale / conflicting / unavailable`を報告する。Human decisionの意味を
再定義せず、GTP completionもClaimしない。acceptance inputの`human_actor`は拒否する。

## 10. Skill and portable layout

```text
skill/agent-operated/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── core/
│   │   ├── actor_contract.py
│   │   ├── verify_actor.py
│   │   ├── bind_operation_result.py
│   │   ├── internal_policy_gate.py
│   │   ├── transition_coordinator.py
│   │   └── verify_acceptance_readback.py
│   └── operations/
│       ├── gtp/
│       │   └── recover.py
│       └── publication/
│           └── check.py
├── references/
│   ├── actor-profile.schema.json
│   ├── operation-receipt.schema.json
│   ├── operation-receipt-error.schema.json
│   ├── credential-bridge-policy.md
│   ├── gtp-v1-adapter.md
│   └── record-policy.md
└── tests/
```

`SKILL.md`はphase routingと必須boundaryだけを記載する。詳細policyとschemaはreferences、deterministic mechanismは
scriptsへ置く。skill folder名とfrontmatter nameは`agent-operated`で一致させる。

portable coreはroot `GTP.md`、root discovery、host credential注入、workflow、repository settings、Check Run、
branch protection、release、automatic installation、production Internal Policy Gate providerを含めない。

## 11. Runtime attachment and Evidence

runtime behaviorを変更するcontractは、各attachmentについてregistration point、real trigger、oracle、full candidate
headを定める。walking skeletonはfeature fillより先に全attachmentを実発火させる。

AOはOperationが返したEvidenceの意味を所有しない。Operation Receiptはsource refとCandidate Bindingを保持する。
Internal Policy Gateの発火はinvocation-localに検証し、そのtraceをOperation Evidenceへ昇格しない。
blocked transitionはcallback call countがzeroであること、各GitHub write直前にtyped live Actor Observationが発火すること、
plan publicationがchecked bytesを使うこと、一般Projection Batchが同一objectとdigestでpublisherへ到達することをportable testで
観測する。plan replacement失敗後の旧context、candidate replacement後の旧token、invalid task入力がhost recoveryへ
到達しないことも負例で観測する。

fixtureはexternal boundary testに限定し、`ao_detector_test`としてlive Evidenceから分離する。

## 12. Operational baseline

[ADR-0011](adr/0011-define-default-on-host-enforcement.md)は、actor separationだけを手動skill入口から実証する旧baselineを、
user-level default-on Host Enforcementへsupersedeする。Portable Coreの責務とtestは維持し、host attachmentをその外側へ置く。

最初のproduction targetはmacOS上のCodex CLIである。Codex Desktopはunbound read-onlyの保護対象に含めるが、
Issue-bound workspace-write leaseの受入対象には含めない。Desktopのwritable host APIを確認できるまで、対応はsuccessor Issueが所有する。

最初のOperational Baselineは、feature depthを持たないdeny-only walking skeletonである。

1. user-level installerがHost Guard、broker service、Codex Plugin／Hook Adapter、Codex user configを同時に登録する。
2. 通常の`codex`起動を常にunbound read-only、Machine Account credentialなし、workspace networkなしにする。
3. 明示的な`ao codex --issue ISSUE_URL`だけをIssue bindingの入口にし、prompt内URLをbindingへ昇格しない。
4. SessionStart、PreToolUse、Host Guard、broker、lease launcher、private gate adapter、projection publisher、handoff/readback adapterを実runtimeへ登録する。
5. 未実装featureは`issue_required`、`broker_unavailable`、`lease_required`等の安定findingでdenyする。
6. 実macOS sessionで各attachmentの発火と、filesystem／GitHub mutationが0件であることを観測する。
7. PR headに束縛されたhost contract Check Runを作り、後続feature sliceが同じattachmentを埋める。

このbaselineはPlugin／Hookの存在だけでは成立しない。Pluginを無効化してもsandbox、credential separation、broker-only writeが
同じdeny境界を維持しなければならない。Machine Account canary mutationはtyped brokerとcredential circuitを実装する後続Issueで
初めて実行し、deny-only skeletonの完成条件へ混ぜない。

## 13. Privacy and authority

durable recordへsecret、token、credential location、private prompt、reasoning、session transcript、local absolute path、
ephemeral runtime ID、Internal Policy Gate decision、provider identity、version、private rule、診断、provenanceを保存しない。

AO detectorとOperation Receiptは`authority: none`を保持する。actor match、candidate binding、publication screening、
acceptance readbackの成功は、それぞれのscope外のmutation、merge、task completionをauthorizeしない。

## 14. Host Enforcement activationと自己bootstrap

### 14.1 Activation state

Host Enforcementの導入状態は次の二つを区別する。

| State | Meaning | Authority |
|---|---|---|
| `Host Enforcement Installed` | root admission、Portable Core、または配布物が存在するが、production Internal Policy Gate providerを実host transitionへ固定注入できるとはまだ観測されていない | repository artifactは存在を示せるが、activationを宣言できない |
| `Production Active` | host-level Repository Integrationがproduction providerをin-processで固定注入し、real transitionでcurrent `InvocationContext`を作り、host-ownedな単調`Activation Latch`を設定した | host-level Repository Integrationのtyped observationとActivation Latchだけ |

task本文、prompt、environment variable、filesystem marker、repository config、agent request、fixture、test providerは
activation sourceまたはlatch resetにならない。初回activation observationを取得できない場合、AOは`Production Active`と
推測しない。設定済み`Activation Latch`を取得できない場合は通常laneを停止し、未設定と推測しない。

`Production Active`はproviderの存在だけでは成立しない。少なくともhostが固定したproviderで`check_plan`を実transitionに
発火させ、source-neutralな結果からcurrent `InvocationContext`を作れることをhost integrationが観測する。観測成功時に
target repository外のhost-owned `Activation Latch`を単調に設定する。provider実装、private rule、identity、version、
diagnostic、error sink、latch storageはIssue #16が所有し、repository artifactへ投影しない。

### 14.2 Pre-activation Bootstrap Lane

`Host Enforcement Installed`かつ`Production Active`ではない期間に、通常laneが自身のproviderを実装する前から
current `InvocationContext`を要求すると自己bootstrap不能になる。この期間だけ、Human/adminが明示した
`Pre-activation Bootstrap Lane`を使用できる。

laneは次のすべてを同じtaskへ束縛する。

1. canonical GitHub Issue URL
2. 同じIssueの有効なGTP Contract
3. Contractを参照する有効なGTP Start
4. Startに束縛された唯一のnon-default branch
5. Contract `scope`に列挙されたrepository-relative path
6. delivery targetを同じIssueとbranchの単一Draft PRだけへ限定する不変条件
7. Human/adminによる明示的な開始と、各GitHub actorのnative observation

PR作成前の`pre-PR state`では対象branchのPRが0件であることを要求し、scope内file edit、commit、branch push、単一Draft PR作成だけを
許可する。最初のpush後はそのDraft PR作成以外のmutationを許可しない。PR作成後は、同じIssueとbranchの唯一のPRがDraftである間だけ
laneを継続する。PR ready化、merge、default branch direct push、別Issue、別branch、別repository、追加PR、Contract scopeの拡張は
許可しない。一つでも入力を取得できない、または不一致ならdependent mutationを発火させない。

このlaneはInternal Policy Gateの代替provider、例外token、Operation、Operation Receiptではない。private decisionを生成せず、
test providerをauthorityへ昇格せず、GTP Recordの意味も変更しない。最初のIssue #22 repair PRはlane自体がまだroot adapterに
存在しないためHuman/admin経路で作成する。この一回限りのrepairは後続taskのauthorizationにならない。

### 14.3 Activation後の境界

hostが`Production Active`を観測し`Activation Latch`を設定した時点から、`Pre-activation Bootstrap Lane`は利用不能である。activation後のすべての
repository mutationはGTP recovery、production `check_plan`、current `InvocationContext`を要求する。taskやAgentはactivationを
falseへ戻せず、bootstrap laneを再有効化できない。provider unavailableは通常laneの`internal_check_unavailable`であり、
pre-activationへ自動fallbackしない。設定済みlatchのread failureも通常laneを停止し、未設定として扱わない。

Draft PRの存在、Human approval、Machine Account actor match、GTP `in_progress`のいずれも、それだけではmerge、task completion、
または`Production Active`を意味しない。Human Accountはrepair candidateを直接確認し、native mergeを別のdecisionとして行う。

## 15. Default-on Host Enforcement

### 15.1 Production targetと適用範囲

Host Enforcementは一度のuser-level installでmacOS上の全Git repositoryへdefault-onで適用する。repository markerによるopt-in／opt-out、
prompt内URLの自動binding、自動Issue作成、自動mergeは行わない。repositoryを解決できないprocess、GitHub remoteを一意に解決できない
repository、Issueへ束縛されていないsessionはread-onlyのままにする。

Repository resolverはcurrent directoryからrepository root、linked worktree、git common identityを取得し、subdirectoryからの起動も同じ
Repository Identityへ正規化する。GitHub remoteはSSH／HTTPS表記を同じowner/repositoryへ正規化する。remoteなし、GitHub以外、または
複数候補を一意に選べない場合は`github_remote_required`で停止し、promptやrepository markerで補わない。

Host EnforcementはPortable Coreを置き換えない。Portable CoreはAOのrouting、binding、Operation、portable testを所有し、host側は
process launch、filesystem sandbox、credential、user-level integration、GitHub write capabilityを所有する。GTPはtask stateの正本のままで、
hostは公式GTP Projectionからoperation policyを導出し、Record、state machine、Evidence validationを再実装しない。

### 15.2 Host layoutと責務

| Path | Responsibility | Must not own |
|---|---|---|
| `host/core/` | Repository Identity、Issue Binding、Host Operational State、operation policy、lease lifecycleのhost-neutral contract | macOS API、GitHub credential、GTP state machine |
| `host/broker/` | closedなBroker Request／Result、typed operation dispatch、binding generation再検証、GitHub transport port | raw command、raw REST path、raw GraphQL、credential値の公開interface |
| `host/macos/` | user-level installer、launchd service、Keychain access、Unix domain transport、sandbox profile、linked worktree launcher | AO portable policy、private provider rule |
| `host/integrations/` | Codex、GTP Projection、private gate、publication、handoff/readbackのAdapter | 外部正本の意味、private diagnosticの公開projection |
| `plugins/agent-operated-host/` | SessionStart／PreToolUseで状態と次のHuman actionを表示し、明白なdenyを早期に返すUX guard | write capabilityの正本、credential、lease発行authority |

user-level installはAO所有configを原子的に導入し、既存configをbackupする。uninstallはAOが所有する変更だけを戻す。partial install、broker停止、
credential取得不能ではwrite capabilityを残さない。

### 15.3 Trust boundary

| Component | Trusted input | Granted capability | Fail-closed boundary |
|---|---|---|---|
| Host Guard | host-observed process、Repository Identity、binding／lease result | sandbox profileとadapter processの起動 | bindingまたはleaseを検証できなければread-only |
| Plugin／Hook Adapter | Host Guardがsanitiseしたstateとfinding | 状態表示とPreToolUseの早期deny | 未読込・disabledでもwrite capabilityは増えない |
| Issue Binder | 明示的な`bind_issue`入力、canonical Issue URL、Repository Identity、公式GTP Projection | generation付きIssue Binding | URL discoveryだけではbindingせず、取得不能ではstateを作らない |
| Workspace Lease Manager | `active`なbinding、expected branch、Repository／worktree identity | 専用linked worktree一つの期限付きwritable root | root repository、他worktree、`.git`、git-common-dir、homeを許可しない |
| GitHub Mutation Broker | launchd check-in、短命session capability、Issue Binding、typed Broker Operation | Machine Accountによる一回のGitHub mutation | 各requestでsession、repository、Issue、generation、operationを再検証する |

Plugin／HookはUX guardであり、無効化可能なのでenforcementの正本ではない。write capabilityの正本はHost Guardのsandbox、
Workspace Lease、broker-only credential boundaryである。Codex、raw shell、generic connector、repository processへMachine Account credentialを渡さない。

broker clientはUnix domain transportを使用する。launcherが発行する短命session capabilityはenvironment、argv、repository fileへ置かず、
sandboxから読めないhost-private runtime fileをbroker adapter processだけへ渡す。production credentialはlaunchd serviceだけがmacOS Keychainから取得し、
standalone broker processはlaunchd check-inなしにcredentialを取得できない。

### 15.4 Issue bindingとHost Operational State

Issue bindingは専用操作だけが作る。任意文章、prompt、tool outputからIssue URLを発見しても候補表示に留め、permissionへ昇格しない。
repository owner/name、git common identity、worktree identity、Issue repositoryが一致しなければbindingしない。generation更新は既存binding、lease、
session capabilityをstaleにする。

| Observation | `HostOperationalState` | General write policy |
|---|---|---|
| Issueなし | `unbound` | filesystem／GitHub mutationを拒否 |
| 明示bindingを検証中 | `binding` | read-only |
| GTP `unmanaged` | `contract_required` | Contractに必要なtyped broker operationだけを候補化 |
| GTP `ready` | `start_required` | branch／Startに必要なtyped operationだけを候補化 |
| GTP `in_progress`かつbindingとbranchが一致 | `active` | typed broker policyとvalid Workspace Leaseの範囲だけ許可 |
| checked candidateをfreeze | `handoff` | repository writeとcandidate差替えを拒否しHuman handoffだけを許可 |
| GTP `halt` | `halted` | 一般writeを拒否し原因URLを表示 |
| GTP `done`／`stopped` | `terminal` | mutationを拒否 |
| GTP Acquisition Error | stateなし | `gtp_unavailable`でdependent transitionを停止 |

`HostOperationalState`はGTPの新しいstateではない。host capabilityを決めるProjectionであり、GTP固有語彙を変更しない。`handoff`もGTP stateではなく、
同じCandidate Headの差替えを止めるhost-local freezeである。

### 15.5 Workspace LeaseとHuman-only exception

Workspace Leaseはopaque lease ID、Repository Identity、canonical Issue URL、expected branch、専用linked worktree identity、binding generation、expiryを
束縛する。`active`だけが新規leaseを取得でき、duplicate lease、任意path、wrong branch、wrong worktreeを拒否する。Codex起動時のwritable rootは
leaseが指す専用worktree一つだけである。

GTP `halt`／terminal、Issue unbind、branch変更、generation更新、expiry、handoff freezeでleaseを失効する。既存processは失効済みleaseを再利用できない。
Git metadataとgit-common-dirはleaseの外側に置き、必要なGit operationはhost adapterまたはtyped brokerへ限定する。

Human-only exceptionはhost admin commandだけが作成でき、repository、allowed operations、理由、expiry、max uses、Human Actor Observationを必須とする。
prompt、environment、repository marker、Agent toolから作成、延長、scope拡張できない。scope外、期限切れ、利用回数超過では無効である。

### 15.6 Public interfaces

| Type | Required fields and boundary |
|---|---|
| `RepositoryIdentity` | GitHub owner/repository、worktree identity、git common identity。local absolute pathはpublic resultへ出さない |
| `IssueBinding` | canonical Issue URL、Repository Identity、GTP Projection digest、expected branch、generation |
| `HostOperationalState` | `unbound | binding | contract_required | start_required | active | halted | handoff | terminal` |
| `BrokerOperation` | `post_issue_comment | create_task_branch | create_commit | push_branch | create_or_update_pull_request | publish_projection_artifact` |
| `BrokerRequest` | version、request ID、invocation/session ID、repository、Issue URL、binding generation、typed payload |
| `BrokerResult` | `accepted | rejected | unavailable`、stable finding、sanitized observation reference |
| `WorkspaceLease` | opaque lease ID、repository、Issue、branch、worktree identity、binding generation、expiry |
| `HumanException` | repository、scopeとしてのallowed operations、reason、expiry、max uses、Human Actor Observation |
| `FindingCode` | `issue_required`等のclosed vocabulary。raw errorまたはprivate diagnosticを値へ含めない |

public interfaceへ任意command、argv、raw REST path、raw GraphQL、credential値、local absolute path、private diagnosticを追加しない。
Broker transportはpayload schemaをoperationごとにclosedにし、一つのaccepted requestを一つのnative mutationへ対応させる。

### 15.7 Stable findingsとfailure behavior

Host Enforcementが公開できるfindingは次のclosed vocabularyをbaselineとする。

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

| Failure | Required behavior |
|---|---|
| Host attachment未読込、partial install | unbound read-only。credentialとwritable rootを渡さない |
| Issueなし、invalid URL、repository mismatch | workspace／GitHub native mutationを0件にする |
| remoteなし、複数GitHub remote候補 | `github_remote_required`でread-onlyを維持する |
| GTP取得不能 | operational stateを推測せず`gtp_unavailable`でdependent transitionだけを停止する |
| GTP `halt` | `gtp_halt`と原因URLを表示し一般writeを拒否する |
| stale generation、wrong branch／worktree | bindingまたはleaseを失効し既存sessionからの再利用を拒否する |
| broker停止、credential取得不能 | GitHub mutationを0件にし、raw shellへfallbackしない |
| Plugin／Hook disabled | UX表示は失われてもHost Guard、sandbox、credential boundaryのdenyを維持する |
| projection omission、check後差替え、native body mismatch | publicationを発火させずstable findingだけを公開する |

### 15.8 Deferred decisions

full Workspace Brokerはこのbaselineへ先行実装しない。Issue-bound leaseで防げなかった名前付き事故またはnear missと、filesystem、process、artifactから
機械観測できるsignalの両方がある場合だけadmission candidateにする。条件未達ではruntime codeを追加せずADRへ不採用または保留を記録する。

production Internal Policy Gate provider、private error sink、Activation Latch storageはIssue #16が所有し、target repository、GTP、test providerへ置かない。
Codex Desktopのlease-bound workspace-write、full Workspace Broker実装、受入中に見つかったbugは、それぞれ名前付きsuccessor Issueなしにscopeへ追加しない。
