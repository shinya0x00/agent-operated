# agent-operated Purpose

Status: private design baseline

Decision records: [ADR-0001](adr/0001-redefine-agent-operated.md), [ADR-0002](adr/0002-record-gtp-artifact-generation-provenance.md), [ADR-0003](adr/0003-require-host-sourced-model-identity.md), [ADR-0004](adr/0004-separate-handoff-readiness-and-human-acceptance.md), [ADR-0005](adr/0005-require-live-firing-evidence-acquisition.md), [ADR-0006](adr/0006-define-portable-core-boundary.md), [ADR-0007](adr/0007-define-operation-hub-boundary.md), [ADR-0008](adr/0008-separate-public-delivery-and-private-control.md), [ADR-0009](adr/0009-bind-private-control-to-transitions.md)

Language: Japanese is canonical

## Definition

`agent-operated`（AO）は、AI agentによるGitHub mutationを宣言済みMachine Accountへ分離し、
作業phaseに応じてPublic Delivery RouteまたはPrivate Control Routeを選択し、公開Operationのresultを
同じtaskと必要なCandidate Headへ束縛してHuman Accountへ返す、個人用Operation Hubである。

AOが信頼するのは「agentが十分に賢い」という推定ではない。GitHubが観測したactor、現在のcandidate
head、公開Operationの実発火、および人間の判断を、同じ作業記録へ結び付けられることを信頼の根拠にする。

## Primary purpose

AOの第一目的は、GitHub上で次の操作主体を区別可能にすることである。

- Human Accountによる依頼、candidateの直接確認、acceptance decision
- Machine Accountを使用したAI agentによるbranch、commit、push、Issue、PR等のmutation

Machine AccountはGitHub principalを識別する。共有Machine Accountを使用する場合、Codex、Claude等の
runtime、model、個別sessionまでは識別しない。この限界を越える帰属は主張しない。

## Required outcomes

### AO-ATTRIBUTION-001: Actor attribution

agentによるGitHub mutationは、タスク開始前に宣言されたMachine Accountから行われる。判定では表示名だけでなく、
GitHubが返す安定したnumeric actor IDを使用する。

### AO-CREDENTIAL-001: Credential isolation

agent用credential routeは、人間が通常使用するGitHub credential routeから分離される。書き込み前にlive actorを
読み戻し、宣言済みactorと一致しなければmutationを停止する。Machine AccountとHuman Accountは異なるnumeric IDを
持ち、fixtureまたは型のない真偽値をwrite authorizationとして扱わない。

### AO-HANDOFF-001: Direct human acceptance

agentは、現在のcandidate head SHAに結び付いたPRとevidenceを人間へ引き渡す。acceptance decisionはHuman
Accountが直接行う。通常laneでは、宣言済みHuman Accountによる同headのnative mergeをbaseline acceptance
evidenceとし、Approve、review comment、reactionを必須にしない。検査後にcandidate headが変化した場合、以前の
判断を新しいheadへ流用しない。

### AO-DETECTION-001: Detectable violations

wrong actor、unknown actor、stale Candidate Binding、欠落したOperation result、およびnative acceptanceの
不一致を、依存するtransitionの前に検知できるようにする。Operation固有のfindingはそのOperationが所有し、AOの
総合合否へ変換しない。

### AO-BOUNDARY-001: Public and private route separation

Public Delivery Routeは、Human Accountへ提示する独立したOperation resultだけをOperation Receiptへ束縛する。
Private Control Routeはhost固定のInternal Policy Gateをphase transition前に呼ぶが、そのdecision、provider identity、
version、内部規則、診断情報をdurable artifactへ投影しない。
`blocked`なら依存するmutation、publication、handoffを発火させない。GTP recovery後に作ったtarget-native planと
公開予定bytesを同じInvocation Contextへ固定し、すべての保護transitionへ要求する。GitHub writeは回数にかかわらず、
各callbackの直前にGitHub Mutation Gateを通す。

## Supporting purposes

- agentが最初に読む入口をAOへ一本化し、operation phaseに応じたrouteとAdapterを選択できるようにする。
- architecture、runtime wiring、実装順序を変更する場合、hostが提供するInternal Policy Gateを公開前に通す。
- operatorがPRだけを見ても、誰が作業し、どの公開Operationが実行され、どのheadに対して判断するのかを日本語で
  理解できるartifactを残す。
- rule、task state、operation implementationの正本を混同しない。

## Canonical ownership

| Concern | Canonical owner |
|---|---|
| AO domain language | [CONTEXT.md](CONTEXT.md) |
| Task contract、state、Evidence eligibility、post-merge task recovery | GTP |
| PR受理reportの意味、findings、questions、UI | Merge Steward |
| Actor Profile、credential role、operation phase、route selection、Operation Receipt、Candidate Binding | AO |
| Internal Policy Gateのprovider、内部規則、非公開診断 | host-private control boundary |
| Observed actor、任意のreview、check、head、merge fact | GitHub |
| merge、保留、修正依頼等の最終判断 | Human Account |

AOはGTP、Merge Steward、またはprivate providerの内容を複製しない。Public Delivery Routeは外部正本を
immutable referenceまたは各Operationが定める参照方法で解決し、Operation resultを変換せずOperation Receiptへ
束縛する。Private Control Routeはsource-neutralなtransition decisionだけをinvocation-localに使用する。

AOのportable coreは、AO Core、agent-facing skill、GTP Operation、Publication Screening、Internal Policy Gate port、
Transition Coordinator、Projection Batch、Acceptance Readbackとtestを所有する。repository rootのprotocol配置、agent
discovery、workflow、settings、release、installation、private provider実装、production batch sourceはRepository
Integrationまたはhostが所有する。

## Non-goals

AOは次を目的にしない。

- agentの長時間稼働、queue、heartbeat、scheduler、retry orchestration
- 人間不在での自動acceptanceまたは自動公開
- Human Accountによる通常laneのacceptanceとMachine Accountによる自動昇格を同一視すること
- modelの能力評価、会話履歴の保存、session transcriptによる監査
- GTPのRecord、state、transition、Evidence validationの再実装
- private providerの規則、identity、version、診断、provenanceの公開または複製
- Internal Policy Gate decisionのOperation Receipt化
- blocked decision後に依存するcallbackを実行すること
- 最初のwriteに対するActor Observationを後続writeへ流用すること
- fixture、boolean、またはfield不足のMappingをGitHub mutationの前提として受理すること
- 検査後に再構築したpublication payloadを公開すること
- Merge Steward findings、report UI、または判断語彙の再実装
- 外部Operation resultを一つのAO pass/failまたは総合安全スコアへ変換すること
- inputから任意commandまたはInternal Policy Gate providerを選択できる汎用executor
- GTPと並行する独自task ledger
- Plugin、executor、特定言語のscriptを必須の配布形態にすること
- すべての対象repositoryでAO専用ファイルをzeroにすること
- Human AccountとMachine Accountの区別だけで、変更内容の正しさを証明すること
- portable coreだけでrepository integrationまたはoperational baselineを完成扱いすること

## Success condition

### Portable core baseline

portable coreは、repository名へ依存しないraw skill pathからActor Observation、GTP Operation、Publication
Screening、Internal Policy Gate、Transition Coordinator、Operation Receipt binding、Acceptance Readbackが実発火したとき
完成する。GTP recoveryはplan作成より先に発火し、current Invocation Contextがcandidate、publication、handoffへ
要求され、blocked private decisionでは依存callbackが発火しない。plan公開は検査済みbytesを直接使用し、一般publicationは
同じChecked Planに束縛されたProjection Batchをcheck、screening、publishへ渡す。各GitHub writeの直前にはlive Machine
Accountを再観測する。
公開Operation固有resultは変更せずtaskとoptional Candidate Headへ束縛でき、private decisionはReceiptまたは
durable Evidenceへ出力されない。Publication Screeningはtrusted candidate-content acquisitionがない間
`not_applicable`であり、Acceptance ReadbackはInvocation Contextと同じcontent digestを持つversioned Actor Profileの
Human Accountだけを使用する。このbaselineはGTP
task completion、Human Account acceptance、production provider、production batch completeness、Repository Integration、
Merge Steward接続をClaimしない。

### Operational baseline

AOは、少なくとも一つの実repositoryで次のwalking skeletonが実証されたとき、最初のoperational baselineに到達する。

1. repositoryの`AGENTS.md`からAOを発見する。
2. versioned Actor Profileを読む。
3. Machine Account用の隔離GitHub CLI profileを使用する。
4. ambient `GH_TOKEN`と`GITHUB_TOKEN`を除外する。
5. write直前にlive actorのloginとnumeric IDを確認する。
6. `agent-operated-bot`でcanary mutationを行う。
7. GitHub native factからactor、ref、pushed headをread backする。

このwalking skeletonがないcredential routeは`configured`とは呼べても`proven`とは呼ばない。GTP、Publication
Screening、Internal Policy Gate、Merge Stewardの追加接続とHuman acceptance flowは、このactor-separation
baselineを保持した独立contractで接続し、それぞれのcompletion claimを分離する。

## Privacy and record boundary

GitHub上のdurable recordへ、次を保存しない。

- secret、token、credential、またはそれらに見える値
- private prompt、reasoning、session transcript
- ローカルの絶対ファイルパス
- 一時的なruntime IDまたはsession ID
- Internal Policy Gateのdecision、provider identity、version、内部規則、診断、provenance

GTPが定義し、repositoryから解決可能なdurable identifierとrepository-relative pathは、上記の一時識別子とは
区別する。
