# agent-operated

> [!WARNING]
> **Status: Pre-alpha / design and implementation baseline**
>
> 現在はportable coreの設計・実装検証段階です。
> repository integration、production credential設定、実リポジトリでの
> canary mutationなどは完成していません。

`agent-operated`（AO）は、AI agentによるGitHub mutationを宣言済みMachine Accountへ分離し、
作業phaseに応じて外部の正本・検査器・支援機構を呼び分け、その結果を同じtaskと必要なCandidate Headへ
束縛してHuman Accountへ返す、個人用Operation Hubです。

AOは外部systemの意味やstate machineを複製しません。誰が操作するか、どのoperationをいつ呼ぶか、
結果がどのtask・candidateに属するか、そしてHuman Accountへ何を判断してもらうか、というroutingとbindingを扱います。

## 想定している運用

現在の設計では、GitHub上の作業を次の順序で扱います。

```text
GitHub Issueを解決
→ GTPからtask stateとcontractを取得
→ planと公開予定bytesを検査
→ Invocation Contextを固定
→ GitHub write直前にMachine Accountをlive確認
→ candidateを検査してexact headへ束縛
→ 必要なOperationを実行
→ 公開予定artifactを同じbatchで検査・公開
→ Human Accountへhandoff
→ native merge後にcandidateとmerge actorをread back
```

`Private Control Route`という用語は、内部検査結果を公開Recordへ投影しないoperation上の境界を指します。
repository自体の公開・非公開状態を意味するものではありません。

## 現在の実装範囲

現時点で実装・local検証されているのは、repository固有設定を含まないPortable Coreです。

- Machine AccountとHuman Accountを分離する共通Actor Profile
- GitHubが返したloginとnumeric actor IDを照合するActor Observation
- GitHub writeごとにtyped Actor Observationを要求するGitHub Mutation Gate
- task、plan、公開予定bytes、Actor Profileを束縛するInvocation Context
- current candidateを一つに限定するCandidate Bindingとhandoff preparation
- GTPの公式projectionを保持するGTP Operation adapter
- host-suppliedな内部検査をtransitionへ適用するInternal Policy Gate port
- exact plan bytesとProjection Batchを使ったpublication route
- 公開不適切な値の候補を検出するPublication Screening
- Operation resultをtask・phase・candidateへ束縛するOperation Receipt
- native PR factからHuman Accountのmergeを確認するAcceptance Readback
- 上記の正常系・負例・source-neutral failureを確認するlocal test suite

実装のagent-facing entryは[`skill/agent-operated/SKILL.md`](skill/agent-operated/SKILL.md)です。
ただし、現時点では配布済みpackageや自動installation entryではありません。

## 未実装・未実証

次の項目は、このrepositoryの現在の完成範囲に含まれません。

- 対象repositoryの`AGENTS.md`等からAOを発見するrepository-root integration
- Machine Account用GitHub CLI profileのproduction設定とcredential配布
- production Internal Policy Gate providerとhost-private error sink
- repository変更とIssue／PR／comment本文を完全列挙するproduction Projection Batch source
- exact candidate contentを取得してPublication Screeningへ束縛する経路
- 実repository上でのcanary mutationとGitHub native actor readback
- GitHub Actions、Check Run、branch protection、repository settings
- Merge Steward等の外部consumer／adapter接続
- package release、installer、automatic discovery
- Human Accountによる実運用でのmergeからpost-merge recoveryまでのwalking skeleton

Portable Coreのlocal testが通ることは、production credential circuit、repository integration、
外部provider、GitHub上の実mutation、またはtask completionを証明しません。

## Repository guide

- [`PURPOSE.md`](PURPOSE.md) — 目的、責務、non-goals、完成条件
- [`DESIGN.md`](DESIGN.md) — current architectureと境界
- [`CONTEXT.md`](CONTEXT.md) — AO固有のdomain language
- [`adr/`](adr/) — materialなdecisionとsupersession履歴
- [`skill/agent-operated/`](skill/agent-operated/) — Portable Coreのskill、schema、script、test

日本語が設計文書のcanonical languageです。code identifier、schema key、command、protocol tokenは
original formを使用します。

## Security and credentials

このrepositoryへtoken、secret、credential path、private prompt、reasoning transcript、session transcript、
local absolute pathをcommitしないでください。公開repositoryであることと、write credentialを公開・共有することは別です。

## License

ライセンスは未確定です。現在は`LICENSE`ファイルがなく、利用・複製・改変・再配布に関する条件は提示していません。
ライセンスが追加されるまでは、公開されていることだけを根拠に利用条件を推定しないでください。
