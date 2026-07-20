# agent-operated Design

Status: private design baseline

Supersession: [ADR-0001](adr/0001-redefine-agent-operated.md)

Later decisions: [ADR-0002](adr/0002-record-gtp-artifact-generation-provenance.md), [ADR-0003](adr/0003-require-host-sourced-model-identity.md), [ADR-0004](adr/0004-separate-handoff-readiness-and-human-acceptance.md), [ADR-0005](adr/0005-require-live-firing-evidence-acquisition.md), [ADR-0006](adr/0006-define-portable-core-boundary.md), [ADR-0007](adr/0007-define-operation-hub-boundary.md)

Language: Japanese is canonical

## 1. Scope

この文書はAOのcurrent designを所有する。AOは、AI agentのGitHub mutationをMachine Accountへ分離する
現在のOperationであり、作業phaseに応じてGTP、Doctrine、Merge Steward等を選択できる個人用Operation Hubである。

AOは統合対象の意味を内部化しない。AO Coreはroutingとbindingを所有し、外部正本または検査器の意味は
各Operationが保持する。repository固有のdiscovery、credential注入、workflow、settings、releaseは
Repository Integrationとして分離する。

## 2. Problem statement

agentがHuman Accountと同じGitHub principalを使用すると、GitHubのdurable recordだけでは人間とagentの
mutationを区別できない。さらに、GTP、Doctrine、Merge Stewardの結果を一つのAO総合判定へ変換すると、
AOがそれらの第二のcanonical ownerになる。

AOは二つの問題を別々に扱う。

1. live GitHub actorを観測し、Machine AccountとHuman Accountを分離する。
2. phase-specificなOperation resultを、意味を変えずtaskと必要なCandidate Headへ束縛する。

## 3. Design principles

1. **Identity before mutation** — write直前にlive actorを読み戻す。
2. **Stable identity** — loginとnumeric actor IDの両方をActor Profileへ固定する。
3. **Actor is not candidate** — Actor Observationの成立にCandidate Headを要求しない。
4. **Exact candidate when applicable** — candidate-dependentなresultだけをfull SHAへ束縛する。
5. **Route, do not absorb** — 外部の語彙、state、finding、authorityをAOの語彙へ変換しない。
6. **One canonical owner** — 同じFactをAOと外部正本で重複所有しない。
7. **No aggregate safety verdict** — 異なるOperation resultを一つのAO pass/failへ潰さない。
8. **No generic executor** — 実commandはtrusted Operation Adapterが所有し、AOはresultだけを束縛する。
9. **Human decision remains Human** — AOとMerge Stewardはmerge判断を代行しない。

## 4. Responsibility model

| Element | Canonical ownership | AO behavior |
|---|---|---|
| GTP | task contract、branch、PR、Evidence、task state | 公式ProjectionをGTP Operationから取得し、不変のresultとして束縛する |
| Doctrine | Safe-to-Fail Ruleの意味 | exact commitを固定し、適用可能なDoctrine Operationを呼ぶ |
| Merge Steward | PR受理report、deterministic findings、questions、UI | 対応Adapterが存在する場合にreport refとheadを束縛する |
| AO | Actor Profile、credential role、operation phase、routing、Operation Receipt、Candidate Binding | phaseに対応するOperationを選択し、resultをtaskへ束縛する |
| GitHub | actor、commit、ref、PR head、check、merge等のnative fact | actor、candidate、acceptanceの観測元として読む |
| Human Account | merge、保留、修正依頼等の最終判断 | AOはdecision requestを提示し、native resultをread backする |

## 5. AO Core

AO Coreは次の4責務だけを所有する。

1. actorとcredential role
2. operation phase
3. Adapter routing
4. task・Candidate Head・Operation resultのbinding

Human acceptance readbackは、Human AccountとCandidate Bindingを扱うためAO Coreに含める。

AO CoreはGTP state、Doctrine Rule、Merge Steward findings、GitHub native fact、Human decision、汎用executor、
独自task ledger、総合安全スコアを所有しない。

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

AO skillがagent-facing entryを所有する。repositoryの`AGENTS.md`等はAOを発見するProjectionになり得るが、
operation phaseとrouting順序を所有しない。

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

Receipt自身は総合`verdict`を持たない。nested `result`にGTPまたはDoctrineの`verdict`が存在しても、
AOは変更も昇格も行わない。

## 6. Credential boundary

### 6.1 Machine mutation circuit

local CodexはMachine Account用の隔離GitHub CLI profileをCodex subprocessへ限定して使用する。

- ambient `GH_TOKEN`と`GITHUB_TOKEN`を除外する。
- Git remoteはHTTPSを使用する。
- URLへusernameまたはtokenを埋め込まない。
- write直前にActor Observationを再取得する。
- loginまたはnumeric IDが一致しなければmutationを停止する。

commit author metadataとpush actorは異なるidentity surfaceである。repository-local identityを使う場合も、
push actorのnative readbackを代替しない。

### 6.2 Read-only consumer circuits

public readはcredentialなしを優先する。private read consumerは必要最小のread-only credentialを使用する。
AO mutation circuitのwrite credentialをMerge Steward等のread-only consumerへ渡さない。

### 6.3 GTP private-read bridge

GTP 1.0.1がprivate read tokenをenvironmentから取得するため、GTP Operationは次の限定bridgeを使用する。

1. ambient tokenを除外する。
2. 同じ隔離profileのActor Observationを確認する。
3. profileからtokenを取得する。
4. GTP child processだけへ`GITHUB_TOKEN`として渡す。
5. token、credential path、raw stderrをoutputへ出さない。

bridge failureはAcquisition Errorであり、GTP `halt`ではない。

## 7. Operations

### 7.1 GTP Operation

GTP Operationは公式`gtp status ISSUE_URL`を実行し、machine JSONを`gtp_projection`として保持する。
GTP Record、state machine、Evidence validationを再実装しない。

compatibility targetはCLI `1.0.1`、protocol projection `gtp: "1.0"`である。`state`、`halt_reason`、
`next_action`、`primary_url`、`acquisition`、`authority`を変換しない。

GTP `halt`は取得済みprotocol stateである。CLI exit 2、`state: null`、`acquisition: incomplete`は
Acquisition Errorとして分離する。

### 7.2 Doctrine Operations

DoctrineはRuleの意味を所有し、Operationがcheck実装を所有する。portable baselineはPublication Operationだけを
同梱し、secret-shaped value、credential location、private context、local absolute path、ephemeral runtime IDを
screeningする。

このcheckはDoctrine適合全体を証明しない。finding kindとlineだけを返し、matched valueを再掲しない。

wiring、walking skeleton、Doubt Pass等のDoctrine Operationは、trusted Adapterが取得したcandidate-bound observationを
検証する。Evidence入力から任意argvを選択する汎用executorをAO Coreまたは共通Operationへ置かない。

### 7.3 Merge Steward Adapter

Merge Steward接続はportable baselineに含めない。接続contractはcanonical endpoint、report schema、supported version、
read credentialを固定し、reportのPRとheadがCandidate Bindingに一致することだけをAOで確認する。

AOはMerge Steward findingsを再計算せず、独自`blocked`へ自動変換しない。

## 8. Human handoff and acceptance

### 8.1 Handoff Readiness

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

### 8.2 Acceptance Readback

通常laneは`merge_policy: human_only`とする。native merge後に次をread backする。

- PR `head.sha`がhandoff Candidate Headと一致する。
- `merged_at`が存在する。
- `merged_by.login`と`merged_by.id`がHuman Accountと一致する。

`merge_commit_sha`をCandidate Headの代用にしない。headが変わった場合、前のhandoffとdecisionをstaleとする。

Acceptance Readbackは`observed / missing / stale / conflicting / unavailable`を報告する。Human decisionの意味を
再定義せず、GTP completionもClaimしない。

## 9. Skill and portable layout

```text
skill/agent-operated/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── core/
│   │   ├── verify_actor.py
│   │   ├── bind_operation_result.py
│   │   └── verify_acceptance_readback.py
│   └── operations/
│       ├── gtp/
│       │   └── recover.py
│       └── doctrine/
│           └── check_publication.py
├── references/
│   ├── actor-profile.schema.json
│   ├── operation-receipt.schema.json
│   ├── credential-bridge-policy.md
│   ├── gtp-v1-adapter.md
│   └── record-policy.md
└── tests/
```

`SKILL.md`はphase routingと必須boundaryだけを記載する。詳細policyとschemaはreferences、deterministic mechanismは
scriptsへ置く。skill folder名とfrontmatter nameは`agent-operated`で一致させる。

portable coreはroot `GTP.md`、root discovery、host credential注入、workflow、repository settings、Check Run、
branch protection、release、automatic installationを含めない。

## 10. Runtime attachment and Evidence

runtime behaviorを変更するcontractは、各attachmentについてregistration point、real trigger、oracle、full candidate
headを定める。walking skeletonはfeature fillより先に全attachmentを実発火させる。

AOはOperationが返したEvidenceの意味を所有しない。Operation Receiptはsource refとCandidate Bindingを保持する。
present、attached、fired、validated等の判定が必要な場合、その語彙を定めるDoctrine Operationが所有する。

fixtureはexternal boundary testに限定し、`ao_detector_test`としてlive Evidenceから分離する。

## 11. Operational baseline

最初のOperational Baselineはactor separationだけを端から端まで証明する。

1. repository `AGENTS.md`からAOを発見する。
2. versioned Actor Profileを読む。
3. Machine Account用の隔離GitHub CLI profileを使用する。
4. ambient tokenを除外する。
5. write直前にActor Observationを取得する。
6. `agent-operated-bot`でcanary mutationを行う。
7. GitHub native factからactor、ref、pushed headをread backする。

このbaselineはRepository Integrationのsuccessor contractが所有する。portable coreのtestだけではprovenとClaimしない。

## 12. Privacy and authority

durable recordへsecret、token、credential location、private prompt、reasoning、session transcript、local absolute path、
ephemeral runtime IDを保存しない。

AO detectorとOperation Receiptは`authority: none`を保持する。actor match、candidate binding、publication screening、
acceptance readbackの成功は、それぞれのscope外のmutation、merge、task completionをauthorizeしない。
