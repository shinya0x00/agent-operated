# agent-operated Purpose

Status: private design baseline

Decision records: [ADR-0001](adr/0001-redefine-agent-operated.md), [ADR-0002](adr/0002-record-gtp-artifact-generation-provenance.md), [ADR-0003](adr/0003-require-host-sourced-model-identity.md), [ADR-0004](adr/0004-separate-handoff-readiness-and-human-acceptance.md), [ADR-0005](adr/0005-require-live-firing-evidence-acquisition.md), [ADR-0006](adr/0006-define-portable-core-boundary.md), [ADR-0007](adr/0007-define-operation-hub-boundary.md)

Language: Japanese is canonical

## Definition

`agent-operated`（AO）は、AI agentによるGitHub mutationを宣言済みMachine Accountへ分離し、
作業phaseに応じて外部の正本と検査器をOperationとして呼び出し、そのresultを同じtaskと必要な
Candidate Headへ束縛してHuman Accountへ返す、個人用Operation Hubである。

AOが信頼するのは「agentが十分に賢い」という推定ではない。GitHubが観測したactor、
現在のcandidate head、検査の実発火、および人間の判断を、同じ作業記録へ結び付けられる
ことを信頼の根拠にする。

## Primary purpose

AOの第一目的は、GitHub上で次の操作主体を区別可能にすることである。

- Human Accountによる依頼、candidateの直接確認、acceptance decision
- Machine Accountを使用したAI agentによるbranch、commit、push、Issue、PR等のmutation

Machine AccountはGitHub principalを識別する。共有Machine Accountを使用する場合、
Codex、Claude等のruntime、model、個別sessionまでは識別しない。この限界を越える帰属は
主張しない。

## Required outcomes

### AO-ATTRIBUTION-001: Actor attribution

agentによるGitHub mutationは、タスク開始前に宣言されたMachine Accountから行われる。
判定では表示名だけでなく、GitHubが返す安定したnumeric actor IDを使用する。

### AO-CREDENTIAL-001: Credential isolation

agent用credential routeは、人間が通常使用するGitHub credential routeから分離される。
書き込み前にlive actorを読み戻し、宣言済みactorと一致しなければmutationを停止する。

### AO-HANDOFF-001: Direct human acceptance

agentは、現在のcandidate head SHAに結び付いたPRとevidenceを人間へ引き渡す。acceptance
decisionはHuman Accountが直接行う。通常laneでは、宣言済みHuman Accountによる同headのnative
mergeをbaseline acceptance evidenceとし、Approve、review comment、reactionを必須にしない。
検査後にcandidate headが変化した場合、以前の判断を新しいheadへ流用しない。

### AO-DETECTION-001: Detectable violations

wrong actor、unknown actor、stale Candidate Binding、欠落したOperation result、およびnative
acceptanceの不一致を、依存するtransitionの前に検知できるようにする。Operation固有のfindingは
そのOperationが所有し、AOの総合合否へ変換しない。

## Supporting purposes

- agentが最初に読む入口をAOへ一本化し、operation phaseに応じたAdapterを選択できるようにする。
- Architecture、runtime wiring、実装順序を変更する場合に、canonical Doctrineをexact commitで
  固定したDoctrine Plannerへ接続する。
- operatorがPRだけを見ても、誰が作業し、何が検査され、どのheadに対して判断するのかを
  日本語で理解できるartifactを残す。
- rule、task state、operation implementationの正本を混同しない。

## Canonical ownership

| Concern | Canonical owner |
|---|---|
| AO domain language | [CONTEXT.md](CONTEXT.md) |
| Safe-to-Fail rules | Doctrine |
| Task contract、state、Evidence eligibility、post-merge task recovery | GTP |
| PR受理reportの意味、findings、questions、UI | Merge Steward |
| Actor Profile、credential role、operation phase、Adapter routing、Operation Receipt、Candidate Binding | AO |
| Observed actor、任意のreview、check、head、merge fact | GitHub |
| merge、保留、修正依頼等の最終判断 | Human Account |

AOはDoctrine、GTP、Merge Stewardの内容を複製しない。外部正本をimmutable referenceまたは
各Operationが定める参照方法で解決し、Operation resultを変換せずOperation Receiptへ束縛する。

AOのportable coreは、AO Core、agent-facing skill、GTP Operation、Doctrine Publication Operationとtestを
所有する。publication findingはDoctrine Operationが所有し、AO Coreの判定ではない。
repository rootのprotocol配置、agent discovery、workflow、settings、release、installationはrepository
integrationであり、portable coreの完成条件へ含めない。

## Non-goals

AOは次を目的にしない。

- agentの長時間稼働、queue、heartbeat、scheduler、retry orchestration
- 人間不在での自動acceptanceまたは自動公開
- Human Accountによる通常laneのacceptanceとMachine Accountによる自動昇格を同一視すること
- modelの能力評価、会話履歴の保存、session transcriptによる監査
- GTPのRecord、state、transition、Evidence validationの再実装
- Doctrine ruleのforkまたはAO内への固定コピー
- Merge Steward findings、report UI、または判断語彙の再実装
- 外部Operation resultを一つのAO pass/failまたは総合安全スコアへ変換すること
- inputから任意commandを選択できる汎用executor
- GTPと並行する独自task ledger
- Plugin、executor、特定言語のscriptを必須の配布形態にすること
- すべての対象repositoryでAO専用ファイルをzeroにすること
- Human AccountとMachine Accountの区別だけで、変更内容の正しさを証明すること
- portable coreだけでrepository integrationまたはoperational baselineを完成扱いすること

## Success condition

### Portable core baseline

portable coreは、repository名へ依存しないraw skill pathからActor Observation、Operation Receipt binding、
GTP Operation、Doctrine Publication Operation、Acceptance Readbackが実発火し、Operation固有resultを
変更せずtaskとoptional Candidate Headへ束縛できたとき完成する。このbaselineはGTP task completion、
Human Account acceptance、repository integration、Merge Steward接続をClaimしない。

### Operational baseline

AOは、少なくとも一つの実repositoryで次のwalking skeletonが実証されたとき、最初の
operational baselineに到達する。

1. repositoryの`AGENTS.md`からAOを発見する。
2. versioned Actor Profileを読む。
3. Machine Account用の隔離GitHub CLI profileを使用する。
4. ambient `GH_TOKEN`と`GITHUB_TOKEN`を除外する。
5. write直前にlive actorのloginとnumeric IDを確認する。
6. `agent-operated-bot`でcanary mutationを行う。
7. GitHub native factからactor、ref、pushed headをread backする。

このwalking skeletonがないcredential routeは`configured`とは呼べても`proven`とは呼ばない。GTP、Doctrine、
Merge Stewardの追加OperationとHuman acceptance flowは、このactor-separation baselineを保持した独立contractで
接続し、それぞれのcompletion claimを分離する。

## Privacy and record boundary

GitHub上のdurable recordへ、次を保存しない。

- secret、token、credential、またはそれらに見える値
- private prompt、reasoning、session transcript
- ローカルの絶対ファイルパス
- 一時的なruntime IDまたはsession ID

GTPが定義し、repositoryから解決可能なdurable identifierとrepository-relative pathは、
上記の一時識別子とは区別する。
