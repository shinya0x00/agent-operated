# agent-operated Design

Status: private design baseline

Supersession: [ADR-0001](adr/0001-redefine-agent-operated.md)

Later decisions: [ADR-0002](adr/0002-record-gtp-artifact-generation-provenance.md), [ADR-0003](adr/0003-require-host-sourced-model-identity.md), [ADR-0004](adr/0004-separate-handoff-readiness-and-human-acceptance.md), [ADR-0005](adr/0005-require-live-firing-evidence-acquisition.md), [ADR-0006](adr/0006-define-portable-core-boundary.md)

Language: Japanese is canonical

## 1. Scope

この文書は、`agent-operated/`に置くAOの設計正本である。AOを長時間実行基盤としてではなく、
個人用のGitHub identity separationとGTP handoff operationとして定義する。portable coreは
repository identityとroot registrationへ依存せず、独立repositoryへsemantic rewriteなしで移せる形にする。

Materialな設計判断はADRで記録する。DoctrineのruleとGTPのprotocol meaningは、それぞれの
外部正本が所有する。この文書はそれらをforkせず、AOが所有する接続と検知だけを定義する。

## 2. Problem statement

GTPではoperator本人がcandidate PRを直接確認する。一方、agentがoperatorと同じGitHub
principalを使うと、GitHubのdurable recordだけでは「人間が行ったmutation」と「agentが
行ったmutation」を区別できない。

AOは、agent mutationをMachine Accountへ、candidateの直接確認とacceptance decisionをHuman
Accountへ分離する。さらに、actorを名乗るだけでなく、実際に使用されたGitHub principalと
candidate headをnative evidenceで照合する。

## 3. Design principles

1. **Identity before mutation** — writeの前にlive actorを読み戻す。
2. **Stable identity** — loginだけでなくnumeric actor IDをactor profileへ固定する。
3. **Exact candidate** — handoff、check、acceptanceはcandidate head SHAへ結び付ける。
4. **Durable state first** — 会話ではなくGTPとGitHubを再開可能な記録とする。
5. **One canonical owner** — Doctrine、GTP、AO間で同じruleやstateを重複所有しない。
6. **Presence is not firing** — artifact、attachment、実発火、validationを別々に証明する。
7. **Block the dependent transition** — 不明点は推測せず、必要な遷移だけを止める。
8. **Human-readable handoff** — operatorが日本語で判断できるPR artifactを作る。

## 4. Responsibility model

| Layer | Owns | Does not own |
|---|---|---|
| Doctrine | Safe-to-Fail rule | AO credential設定、GTP task state |
| GTP | task contract、allowed paths、state、Evidence eligibility、post-merge task recovery | GitHub credential、actorの実効値 |
| AO | actor profile、credential role、human-only operation、preflight、record gate、handoff detector | GTPの状態機械、Doctrine rule |
| GitHub | native actor、commit、ref、PR、任意のreview、check、mergeの観測事実 | AOの意図、private agent context |
| Skill Hub | agentが読む単一入口、適用skillへのrouting | ruleまたはtask stateの正本 |

## 5. Actor model

AOのactor profileは、少なくとも次のroleを宣言する。

```yaml
profile_version: 1
machine_actor:
  login: <machine-login>
  id: <stable-numeric-id>
human_actor:
  login: <human-login>
  id: <stable-numeric-id>
human_only_operations:
  - acceptance_decision
merge_policy: human_only
```

actor profileはsecretを含めない。credentialの格納場所やtoken値も記録しない。

初期private baselineは次のbindingを使用する。将来actor profile fileを作成した後は、その
versioned fileを実行時の正本とする。

| Role | Login | Stable GitHub ID |
|---|---|---:|
| Machine Account | `agent-operated-bot` | `301814874` |
| Human Account | `shinya0x00` | `236178224` |

初期baselineでは`acceptance_decision`をhuman-only operation、`merge_policy`を`human_only`とする。
Machine Account mergeは通常laneへ暗黙に許可しない。long-run operationで必要になった場合、別task
contractとADRが`machine_allowed` laneおよびauthorization referenceを定義する。

### 5.1 Machine actor

branch作成、commit push、agentが作成するIssue/PR/comment等のmutationに使用する。
Machine actorの一致はlive GitHub API readbackで確認する。

### 5.2 Human actor

candidate PRを直接確認し、current candidate headに対するacceptance decisionを行う。通常laneでは
Human Account自身のnative mergeをacceptance evidenceとしてread backする。Approve、review comment、
reactionは追加Evidenceにできるが必須にしない。

### 5.3 Service and connector actors

GitHub App、connector、browser、cloud runtime、CI serviceは、local CLIとは別credential
circuitとして扱う。actorがnative evidenceで実証され、profileに許可されるまでは、
AO対象taskのmutation routeとして使用しない。read-only observationは別途許可できる。

### 5.4 Attribution limit

共有Machine Accountが証明するのは、GitHubが観測したprincipalである。同じaccountを使う
複数runtimeのうち、どのmodel、process、sessionが操作したかは証明しない。必要になった場合は
別actorまたは署名付きattestationを、将来のADRで追加する。

## 6. Credential boundary

### 6.1 Local Codex route

local Codexは、Codex subprocessだけにMachine Account用のGitHub CLI profileを注入する。
環境変数のtokenがprofileを上書きしないよう除外し、人間の通常shellからcredential routeを
分離する。profileのローカル絶対パスはdurable recordへ保存しない。

実装形は次の性質を満たす。

- Codexのshell environment policyから専用`GH_CONFIG_DIR`を設定する。
- `GH_TOKEN`と`GITHUB_TOKEN`をsubprocess環境から除外する。
- Git remoteはHTTPSを使用する。SSH actorへ迂回しない。
- URLへusernameを埋め込まず、実効credential helperを検査する。
- write直前に`gh api user`相当のauthenticated readbackを行う。
- loginとnumeric actor IDの両方がprofileと一致しなければ停止する。

### 6.2 Git commit identity

commit author/committer metadataとpush actorは別のidentity surfaceである。AOは両方を混同しない。
bot表示が必要な場合、Machine Accountの確認済みnoreply emailをCodex subprocessへ限定して設定する。
operatorのrepository-local identityを恒久的にbotへ書き換えない。

### 6.3 Credential redlines

次の場合はfail closedとする。

- live actorを読めない。
- loginまたはnumeric actor IDが一致しない。
- credential helperの実効経路を説明できない。
- remoteが未許可のtransportを使用する。
- connector等の別circuitのactorが未実証である。

### 6.4 GTP private-read bridge

GTP 1.0.1 CLIはprivate repositoryのread credentialを`GITHUB_TOKEN`または`GH_TOKEN`から読む。
AOはambient tokenを許可せず、隔離GitHub CLI profileのactorを先に検証する。private recoveryを行う場合だけ、
同じprofileから取得したtokenをGTP child processのenvironmentへ限定して渡す。

token、credential path、raw command stderrをAO outputまたはdurable recordへ出さない。public repositoryの
read-only recoveryではtoken bridgeを使用しない。bridgeに失敗した場合はAcquisition Errorとして扱い、
GTP `halt`へ変換しない。

## 7. GTP integration

AOはGTPのtask contractとevidence modelを使用する。GTPのstate machineをAO内に複製しない。

### 7.1 Bootstrap and recovery

新しいagentは次の順序で読む。

1. public taskではGTPの`status`を直接実行する。private taskではread credentialのactorを先に検証する。
2. 公式GTP recovery projectionからcurrent taskとauthoritative next referenceを解決する。
3. task contract、allowed paths、acceptance、design/ADR referenceを読む。
4. AO actor profileと、このtaskで許可されたcredential roleを読む。
5. applicableな場合だけDoctrine Plannerを実行する。
6. mutation直前にlive actorを再検証する。

README、AGENTS、Skill Hubはdiscovery projectionであり、current task stateの正本ではない。
必要な参照が欠落または競合する場合は推測しない。欠けた対象を`unknown`または
`evidence_request`として示し、その参照に依存するtransitionだけを停止する。

### 7.2 Pre-mutation contract

agent mutationの前に、少なくとも次を解決できなければならない。

- current GTP task reference
- scopeとallowed paths
- acceptance condition
- current actor profile reference
- Machine Accountのlive actor result
- stop conditions

portable core自身を変更するtaskの初期scopeは、原則として`agent-operated/**`に限定する。
root discovery、workflow、repository settings、releaseまたはinstallationを変更するtaskはrepository
integrationとして別contractでattachment pointを明示する。

### 7.3 Work and evidence

agentは専用branchで変更し、GTPが定めるevidenceをcandidate headへ結び付ける。AO固有の
evidenceはGTP recordから参照可能にし、独自の並行task ledgerを作らない。

### 7.4 PR handoff readiness

handoffは少なくとも次を含む。

- task reference
- candidate head SHA
- Machine actor verification reference
- validation evidence reference
- wiringを変更した場合のfiring evidence reference
- known unknownsと未解決finding
- Human Accountに求めるdecision

このphaseではhuman decisionはまだ存在しない。`verify-pr-handoff`のreadiness phaseは、Approve、
review comment、reaction、merge factを要求せず、現在headをHuman Accountへ提示できるAO conformanceだけを
判定する。`proceed`はacceptance、merge authorization、completion、post-merge task stateを意味しない。

### 7.5 Human acceptance readback

通常laneの`merge_policy`は`human_only`とする。Human AccountがPRを確認してmergeした後、live PR readbackで
次を照合する。

- PRの`head.sha`がhandoffしたfull candidate head SHAと一致する。
- PRがmergedで、`merged_at`が存在する。
- `merged_by.login`と`merged_by.id`がactor profileのHuman Accountと一致する。
- handoff後にcandidate headが変化していない。

candidate照合へ`merge_commit_sha`を使わない。これはopen PRのtest merge commitとしてmerge前から存在する場合が
あり、merge後もmerge方式に応じた結果commitであってhandoff candidateのcanonical ownerではない。Approve、
review comment、reactionはbaseline acceptance evidenceにしない。
会話だけでもdurable acceptanceをClaimしない。headが変わった場合、以前のreadinessとacceptanceをstaleとして
再handoffする。

Machine Account mergeはHuman Accountの確認を証明しない。`machine_allowed` laneはrequired checks、dependency、
allowed branch、target repository、authorization reference等を別task contractとADRが固定するまで未実装とする。

### 7.6 Post-merge recovery

merge後のtask stateは公式GTP recoveryから再構成する。AOは別にnative human acceptanceをread backする。
actor separation、handoff readiness、native human acceptance readbackが欠けた状態をAO完了主張へ
昇格させない。AOはGTPに存在しないcloseout Recordまたはcommandを発明しない。

## 8. Doctrine integration

DoctrineはRuleの正本であり、AOはOperation implementationである。

Architecture integration、runtime/executable wiring、hook、entry point、workflow attachment、
delivery bootstrap、または実装順序を決めるtaskでは、独立した`doctrine-planner` skillを
併用する。

Doctrine Plannerはinvocation開始時にcanonical `main`をauthenticated APIで一度だけ解決し、
40文字のcommit SHAへ固定して全文を取得する。そのrunの`doctrine_ref`はimmutable blob URL
ではなく、exact commitを含むdocument URLとする。取得、完全読取、plan lintのいずれかに
失敗した場合、Doctrine conformanceや`verdict: proceed`を主張しない。

AOのdetector verdictはAO conformanceだけを表し、Doctrine verdict、GTP completion、
human acceptance、merge authorizationを代行しない。

## 9. Skill wiring

user-facing entryは原則として一つの`agent-operated` skillで十分とする。Pluginは必須にしない。

```text
agent-operated skill
├── bootstrap: 公式GTP recovery projectionを解決
├── actor preflight: credential roleとlive actorを検証
├── record gate: durable recordの禁止情報を検知
├── wiring gate: present、attached、fired、validatedを検証
├── handoff check: readinessとnative human merge readbackをexact headで検証
└── routing: applicableならdoctrine-plannerを呼ぶ
```

`doctrine-planner`はAOへ埋め込まず、別skillとして正本とlinterを維持する。GTPも外部protocol
として維持する。AO skillは両者への参照と適用条件だけを所有する。

deterministic checkは独立skillへ増やさず、AO skill内の`script`として実装する。GTP 1.0.1が
Python 3.11以上を要求し、JSON projection、credential subprocess、closed envelopeを扱うため、portable
baselineはPython 3.11 standard libraryへ統一する。`gtp`と`gh`はexternal commandとして扱う。

## 10. Portable core layout

```text
agent-operated/
├── PURPOSE.md
├── DESIGN.md
├── CONTEXT.md
├── adr/
│   ├── 0001-redefine-agent-operated.md
│   ├── 0002-record-gtp-artifact-generation-provenance.md
│   ├── 0003-require-host-sourced-model-identity.md
│   ├── 0004-separate-handoff-readiness-and-human-acceptance.md
│   ├── 0005-require-live-firing-evidence-acquisition.md
│   └── 0006-define-portable-core-boundary.md
└── skill/
    └── agent-operated/
        ├── SKILL.md
        ├── agents/
        │   └── openai.yaml
        ├── scripts/
        │   ├── recover_gtp.py
        │   ├── verify_actor.py
        │   ├── check_durable_record.py
        │   ├── verify_wiring_evidence.py
        │   └── verify_pr_handoff.py
        ├── references/
        │   ├── gtp-v1-adapter.md
        │   ├── credential-bridge-policy.md
        │   ├── actor-profile.schema.json
        │   └── record-policy.md
        └── tests/
```

skill folder名とfrontmatter nameは`agent-operated`で一致させる。`scripts/`はmechanism、`SKILL.md`は
適用条件とworkflow、referencesはschemaや詳細policyを担う。これらはDoctrineやGTP本文のコピーを含めない。

portable coreはroot `GTP.md`、root agent discovery file、workflow、repository settings、release metadata、
automatic installationを含めない。これらはrepository integrationが所有する。

## 11. Deterministic checks

### 11.1 Actor preflight

`verify-actor`はauthenticated user responseをactor profileと照合する。成功結果にはsecretや
ローカルprofile pathを含めず、観測時刻、login、numeric ID、対象operation classだけを残す。

### 11.2 Durable record gate

`check-durable-record`はGitHubへ投稿予定の本文とartifactを対象に、少なくとも次を拒否する。

- secret、token、credentialらしき値
- private prompt、reasoning、session transcript
- ローカル絶対パス
- ephemeral runtime ID、session ID

secret検知は既存scannerを利用できる。AO独自scannerの精度を過大評価しない。検知結果には
secret本文を再掲しない。

### 11.3 Wiring evidence

次の四状態を区別する。

| State | Required evidence |
|---|---|
| present | candidate headにworkflow、checker、hook等のartifactが存在する観測 |
| attached | 実際のregistration pointとreal triggerへ接続された観測 |
| fired | task-selected live acquisitionによるcandidate head上の実呼出し観測 |
| validated | firing後のoracleがtask contractの期待結果を満たした観測 |

runtime wiringを扱うtask contractは、各attachment pointについて`attachment_point`、`real_trigger`、
`acquisition`、`oracle`、full `candidate_head`を明記する。acquisitionはGitHub Actions run API、Codex host
hook event、実CLI command、service request/log/trace等からprojectが選ぶ。AOは一種類へ固定しない。
contract作成時にcandidateが未作成なら、candidate headのcanonical ownerと解決時点を定め、最初の
candidate-bound evidenceでfull SHAを固定する。short SHAまたはbranch名を代用しない。

bare URL、callerの`fired: true`、model-authored summaryだけでstateを昇格しない。detectorは指定されたlive
sourceを取得し、attachmentとtrigger、observed head、oracleを照合する。失敗したrunやnonzero commandも実際に
呼ばれたなら`fired`になり得るが、期待結果を満たさなければ`validated`ではない。

local command acquisitionは実行前にrepositoryの`HEAD`がfull candidate headと一致し、tracked/untrackedを
含むworktreeがcleanであることを要求する。これを満たさない場合はcommandを発火せず、未commit内容を
candidate-bound evidenceへ混入させない。

`present`だけで`wired`または`proven`と主張しない。runtime wiringを変更するtaskでは、最初のwalking
skeletonがすべてのattachment pointを通り、`fired`と必要な`validated` evidenceを示すまでverified
handoffへ進めない。source-specific acquisitionが未実装なら、そのclaimを`unknown`として停止する。

### 11.4 PR handoff

`verify-pr-handoff`はphaseを明示する。

- `readiness`: candidate head、GTP task、actor evidence、validation、wiringを変更した場合のfiring/validation
  evidence、Human Accountへ求めるdecisionを照合する。human decisionは要求しない。
- `acceptance_readback`: live PRから`head.sha`、`merged_at`、`merged_by.login`、`merged_by.id`を読み、
  candidate headとHuman Account profileへ照合する。formal review eventは要求しない。

対象headが一致しないevidenceはstaleとして扱う。どちらのphaseもGTP schemaを所有せず、opaqueなtask/evidence
referenceとGitHub native factだけを扱う。

handoff detectorへ渡すactor、validation、wiring evidenceは、同じfull candidate head、detector固有の
`decision_scope`、`verdict`、`authority`、観測sourceを含む完全なdetector envelopeとする。callerが作成した
`verified: true`、`passed: true`、`fired: true`等の単独booleanをEvidenceへ昇格しない。
portable wiring detectorはhandoffへ直接渡せるよう`required: true`と`observation_source: local_command`を
出力する。
`--allow-fixture`はdeterministic test専用で、結果を`ao_detector_test`へ隔離する。本番AO conformanceへ
fixture結果を流用しない。

## 12. Verdict envelope

AO detectorは、少なくとも次のmachine-readable envelopeを返す。

```json
{
  "decision_scope": "ao_conformance",
  "task_ref": "<durable-gtp-task-ref>",
  "actor_profile_ref": "<durable-profile-ref>",
  "candidate_head_sha": "<40-hex-sha>",
  "findings": [],
  "verdict": "proceed|repair_then_proceed|blocked"
}
```

`proceed`はAO固有のactor、record、handoff条件を満たすことだけを示す。mergeやtask completionを
許可するtokenとして使用しない。

## 13. Native evidence and canary

初期walking skeletonは、実repositoryでcanary branchへのpushを行い、次を照合する。

1. preflightのloginとnumeric IDがactor profileに一致する。
2. pushed refとlocal candidate headが一致する。
3. Organization audit logの`git.push`が利用できる場合、actor、actor ID、ref、headを照合する。
4. audit logを利用できない場合、repository eventの該当PushEventで同じ値を照合する。
5. task-selected live acquisitionで、candidate headに対するdeclared trigger/operationの`fired`と`validated`を分けて参照する。
6. Human Accountによる同headのnative PR mergeをread backする。Approve、review comment、reactionは必須にしない。

canary evidenceがないcredential routeは`configured`とは呼べても`proven`とは呼ばない。

## 14. Enforcement behavior

| Finding | Default behavior |
|---|---|
| wrong/unknown actor | mutationを停止 |
| secretまたはcredential exposure | publishを停止し、値を露出せず修復 |
| stale candidate head | acceptanceとhandoffを無効化し再検査 |
| missing authoritative task/profile ref | 依存transitionを停止しevidence request |
| missing firing evidence | wired/proven/ready claimを停止 |
| fired but not validated | validation evidenceに依存するreadiness/wired/proven claimを停止し、観測結果からrepair |
| missing/wrong native human merge | acceptance/post-merge claimを停止 |
| non-redline validation gap | findingを残しrepair then proceed |

不明点をtask全体の永久停止へ拡大しない。一方、identity redlineとsecret exposureは、解消するまで
該当mutationをfail closedにする。

## 15. Evolution

- PURPOSEの変更は、目的または境界を変更するsuperseding ADRを必要とする。
- actor role、human-only operation、credential trust boundaryのmaterial changeもADRを必要とする。
- `machine_allowed` merge laneの導入は、通常laneから分離したtask contractとADRを必要とする。
- login変更はnumeric IDを確認し、actor profileを更新する。loginだけの一致で移行しない。
- GTPやDoctrineの意味をAO内へコピーして互換層を作らない。外部正本の変更に応じてadapterを
  更新する。
- target repositoryへのAO file数はproduct invariantにしない。必要なenforcement方式に応じて
  Skill Hub、central workflow、またはtarget-local artifactを選ぶ。

## 16. Implementation-order boundary

このdesignはwalking skeletonの必須性を定めるが、詳細な実装順序をdesign canonとして固定しない。
実装taskでは、exact Doctrineを取得したDoctrine Plannerがscratch planをlintし、`verdict: proceed`
となった順序をGTP task contractへ反映する。linterを実行していない設計作業は、Doctrine準拠の
実装順序を主張しない。

## 17. External authorities

- Doctrine discovery pointer:
  <https://github.com/shinya-reiji/doctrine/blob/main/DOCTRINE.md>
- GitHub Task Protocol repository:
  <https://github.com/shinya0x00/github-task-protocol>

moving `main` URLはdiscoveryにだけ使用する。exact Doctrineが必要なrunでは、Doctrine Plannerが
authenticated APIで解決したcommit SHAを固定する。GTPのprotocol meaningはGTP側のcurrent
canonに従い、AOがtaskごとの独自GTP version pinを追加しない。
