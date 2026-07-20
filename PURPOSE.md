# agent-operated Purpose

Status: private design baseline

Decision records: [ADR-0001](adr/0001-redefine-agent-operated.md), [ADR-0002](adr/0002-record-gtp-artifact-generation-provenance.md), [ADR-0003](adr/0003-require-host-sourced-model-identity.md), [ADR-0004](adr/0004-separate-handoff-readiness-and-human-acceptance.md), [ADR-0005](adr/0005-require-live-firing-evidence-acquisition.md), [ADR-0006](adr/0006-define-portable-core-boundary.md)

Language: Japanese is canonical

## Definition

`agent-operated`（AO）は、GitHub Task Protocol（GTP）で管理される作業において、
AI agentによるGitHub mutationを宣言済みのMachine Accountへ帰属させ、候補PRを
宣言済みのHuman Accountによる直接確認へ引き渡す、個人用のAgent Operationである。

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

wrong actor、unknown actor、stale head、欠落したfiring evidence、およびdurable recordへの
禁止情報の混入を、完了主張の前に検知できるようにする。

## Supporting purposes

- agentが最初に読む入口を一つにし、GTPのdurable stateから作業を再開できるようにする。
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
| Actor binding、credential role、human-only operation、AO detector | AO |
| Observed actor、任意のreview、check、head、merge fact | GitHub |
| Agent-facing discovery and routing | Skill Hub |

AOはDoctrineやGTPの内容を複製しない。外部正本をimmutable referenceまたはGTPが定める
参照方法で解決し、AO固有のenforcementだけを所有する。

AOのportable coreは、skill、GTP consumer adapter、actor/record/wiring/handoff detectorとtestを所有する。
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
- Plugin、executor、特定言語のscriptを必須の配布形態にすること
- すべての対象repositoryでAO専用ファイルをzeroにすること
- Human AccountとMachine Accountの区別だけで、変更内容の正しさを証明すること
- portable coreだけでrepository integrationまたはoperational baselineを完成扱いすること

## Success condition

### Portable core baseline

portable coreは、repository名へ依存しないraw skill pathからGTP recovery、actor preflight、record gate、
wiring detector、handoff detectorが実発火し、positive/negative testでdependent transitionを正しく
進行または停止できたとき完成する。このbaselineはGTP task completion、Human Account acceptance、
repository integrationをClaimしない。

### Operational baseline

AOは、少なくとも一つの実repositoryで次のwalking skeletonが実証されたとき、最初の
operational baselineに到達する。

1. agent credential routeのlive actorが宣言済みMachine Accountと一致する。
2. agentがcanary branchへpushする。
3. GitHub native evidenceでactor ID、ref、pushed headを照合する。
4. 同じcandidate headに対する検査の実発火とvalidation結果を別々に参照できる。
5. Human Accountがそのcandidate headのPRを直接確認し、native mergeする。
6. GTPのdurable recordからactor evidence、firing/validation evidence、native human mergeを解決できる。

ファイル、workflow、checkerが存在するだけでは成功としない。task-selected live acquisitionで実際の
発火とvalidationを観測し、GTPのdurable referenceとGitHub native actor、head、merge factへ到達できることを
必要とする。

## Privacy and record boundary

GitHub上のdurable recordへ、次を保存しない。

- secret、token、credential、またはそれらに見える値
- private prompt、reasoning、session transcript
- ローカルの絶対ファイルパス
- 一時的なruntime IDまたはsession ID

GTPが定義し、repositoryから解決可能なdurable identifierとrepository-relative pathは、
上記の一時識別子とは区別する。
