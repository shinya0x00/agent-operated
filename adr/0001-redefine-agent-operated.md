# ADR-0001: agent-operatedをprivate identity-separating GTP Operationとして再定義する

- Status: Accepted
- Date: 2026-07-18
- Decision owner: operator
- Scope: `00-lab/agent-operated/`

## Context

旧agent-operatedは、agentがIssueからimplementation、validation、PR、merge、closeoutまでを
長時間自律実行するdelivery systemとして設計された。Embedded v2を実装し、将来標準として
Plugin-first / target-zeroを採用していた。

現在の運用前提は変わった。

- GTPがtask contract、state、evidence、closeout、recoveryを所有する。
- operatorがcandidate PRを直接確認する。
- agentにはMachine Accountを使用させ、人間のGitHub操作と区別したい。
- model性能の向上により、AO独自のlong-run orchestrationを主要価値としない。
- operationの相当部分は公開checkとhost側の内部controlで足りる。
- AOは個人用であり、public productとしての配布要件を負わない。
- agent-facing entryを一つに集約し、公開成果物とhost-private controlの責務を分離したい。

したがって、旧AOの中心目的を継ぎ足すのではなく、新しいcanonical purposeを定義する必要がある。

## Decision

`agent-operated`という名称を維持し、その意味を「agentの長時間自律配送」から
「GTP taskにおけるagent operationのidentity separationとhuman handoff」へ変更する。

新AOは次を所有する。

1. Human AccountとMachine Accountのactor profile
2. agent subprocess用credential routeの分離
3. GitHub write前のlive actor verification
4. human-only acceptance decision
5. candidate headとactor/evidence/human reviewを照合するhandoff detector
6. durable recordへ禁止情報を出さないrecord gate
7. artifact presence、attachment、actual firingを区別するwiring proof
8. GTP等のPublic Delivery RouteとPrivate Control Routeの選択

責務境界は次のとおりとする。

- GTPはtask stateとevidence lifecycleの正本である。
- AOはidentity、credential role、human-only operation、route selection、bindingを所有する。
- host-private control boundaryは内部規則とproviderを所有する。
- GitHub native recordは実際のactor、head、review、check、merge factを所有する。
- Skill Hubは単一のdiscovery/routing entryであり、canonical ruleを所有しない。

user-facing AOは一つの`agent-operated` skillから開始する。deterministicな公開checkerは同skillの
`scripts/`へ置き、`references/`へschemaと詳細policyを置く。内部controlはhost固定providerを通じて
invocation-localに適用し、公開OperationまたはReceiptへ変換しない。Plugin化とPythonは要件にしない。

Machine AccountはGitHub principalを区別するものであり、共有accountを使う個別model、runtime、
sessionを識別しない。この限界をAOの保証として明記する。

## Supersedes

このADRは、新AOのscopeにおいて次をsupersedeする。

- 旧AO commit
  [`b6095f2cdd47631c20cc02326c5346a0eb4a5976`](https://github.com/agent-operated/agent-operated/tree/b6095f2cdd47631c20cc02326c5346a0eb4a5976)
  の`PURPOSE.md`および`DESIGN.md`が定めた、human-free autonomous deliveryを中心とするpurpose
- 同commitの
  [`docs/adr/0006-plugin-first-target-zero.md`](https://github.com/agent-operated/agent-operated/blob/b6095f2cdd47631c20cc02326c5346a0eb4a5976/docs/adr/0006-plugin-first-target-zero.md)
  が定めた、Plugin-first / target-zeroを将来標準とするdecision
- Embedded v2を新AOへ継続配布するという暗黙のcompatibility expectation

supersessionは旧AOの歴史的事実やEmbedded v2の検証結果を削除しない。それらは旧systemの
historical evidenceとして残るが、新AOのcurrent design authorityではない。

## Inherited operational rules

旧operator-handbook由来の次の知見は、責務を修正して継承する。

### Durable bootstrap order

agentはGTPのdurable entryからcurrent taskとauthoritative referencesを解決する。READMEやskillは
入口であってtask stateの正本ではない。参照不足を推測で補わず、欠けた対象を示し、依存する
transitionだけを停止する。

### Public record safety

GitHubのdurable recordへsecret/tokenらしき値、private prompt/session transcript、ローカル絶対
path、一時的runtime/session IDを残さない。公開前のsource-neutral screeningとhost側のprojection checkを
別経路として適用する。

### Presence versus firing

checker、workflow、hookが存在することと、実際に接続され発火したことを区別する。GTP evidenceに
candidate headへ結び付くActions run、Check Run、log、observable oracle等の実発火参照を残す。

## Consequences

### Positive

- operatorとagentのmutationをGitHub native actorで区別できる。
- GTPとAOの二重task stateを避けられる。
- operatorはPRとcandidate headを直接確認する責任を維持できる。
- agent-facing entryを一つにしつつ、private controlを公開data modelから分離できる。
- target repositoryへのAO専用file数を目的化せず、必要なenforcementだけを選べる。
- AO実装は小さなdetectorとcredential boundaryからwalking skeletonを作れる。

### Negative and limits

- Machine Account credentialの管理と失効対応が必要になる。
- connector、browser、cloud runtime等はlocal CLIとは別circuitとして個別に実証する必要がある。
- 共有Machine Accountだけでは個別agent/runtimeを識別できない。
- actor separationは変更内容の正しさを保証しない。validationとhuman judgmentは別に必要である。
- target-zero、Plugin配布、旧Embedded v2との互換性は保証しない。

## Alternatives considered

### Keep using the Human Account for agent work

GitHub record上で人間とagentを区別できず、primary purposeを満たさないため却下した。

### Keep the old autonomous-delivery purpose and add Machine Account support

GTPと責務が重複し、不要になったlong-run operationを中心に残すため却下した。

### Make AO only an actor profile file

profileの存在だけではcredential route、live actor、exact-head handoff、firing evidenceを実証できない
ため却下した。AOはprofileを含むOperationとする。

### Merge private policy meaning into the AO skill

private ruleとprovider identityがAO実装および公開成果物へ埋まり、canonical ownershipが曖昧になるため
却下した。単一入口からhost固定のPrivate Control Routeへ接続する。

### Require a Plugin or Python implementation

現在必要なのはcredential separationとdeterministic checksであり、配布形態や言語を固定する根拠が
ないため却下した。

## Migration

1. 新repositoryの`PURPOSE.md`、`DESIGN.md`、このADRをcanonical baselineにする。
2. GTP taskのscopeを`agent-operated/**`に限定して初期implementationを管理する。
3. actor profile schemaとprivate profileを作る。secretまたはcredential locationは含めない。
4. AO skillのwalking skeletonを作り、GTP recovery、actor preflight、record gate、handoff checkを接続する。
5. architecture/runtime workのplanは、公開前にhost固定のInternal Policy Gateで検査する。
6. 実repositoryでMachine Accountのcanary pushとnative actor observationを行う。
7. 同じcandidate headへcheckを実発火させ、Human Accountのdirect reviewまで通す。
8. 必要なら旧repositoryへ新AOへのsupersession pointerを追加する。旧artifactは削除しない。

## Acceptance evidence

このdecisionの実装完了には、少なくとも次が必要である。

- `PURPOSE.md`と`DESIGN.md`がこのADRを参照する。
- actor profileのloginとnumeric IDをlive API responseで照合できる。
- canary pushのactor、ref、headをGitHub native evidenceで照合できる。
- candidate headに対するcheckerのactual firing evidenceがある。
- Human Accountが同じcandidate headを直接確認した記録がある。
- GTP closeoutから上記evidenceへ到達できる。

このADRと設計fileが存在するだけでは、operational wiringの完成を意味しない。
