# ADR-0006: portable coreとrepository integrationを分離する

- Status: Accepted; ownership list superseded by ADR-0008
- Date: 2026-07-20
- Decision owner: operator
- Scope: `agent-operated/`
- GTP observation ref:
  [`4390cee29c1f7433666d19ffbdd6ff02c9b44178`](https://github.com/shinya0x00/github-task-protocol/blob/4390cee29c1f7433666d19ffbdd6ff02c9b44178/GTP.md)

## Context

AOは`00-lab/agent-operated/`で設計を始めたが、独立repositoryへ昇格できる境界を先に作ることにした。
現在の設計には、`00-lab`固有path、repository rootへのGTP導入、skill bundle、GitHub workflow、
Human Account mergeを一つの完成条件へまとめて読める箇所がある。このまま実装すると、独立時にportableな
Operation codeとrepository固有のregistrationを分解し直す必要がある。

また、GTP 1.0.1のread-only CLIはprivate repository用tokenを`GITHUB_TOKEN`または`GH_TOKEN`から読む。
AOのMachine Account routeはambient tokenを除外して隔離`GH_CONFIG_DIR`を使うため、private recoveryには
credential sourceを検証した上でGTP child processだけへtokenを渡すbridgeが必要である。GTP側は変更しない。

## Decision

`agent-operated/`配下に、repository名やroot registrationへ依存しないportable coreを作る。
portable coreは次を所有する。

- `agent-operated` Codex skillとraw-path entry
- GTP公式`status` projectionを取得するconsumer adapter
- actor profile、Machine Account preflight、credential bridge
- source-neutralなPublication Screening
- host固定providerを受け取るInternal Policy Gate port
- exact-head handoff readinessとHuman Account acceptance readback
- deterministic fixtureとlocal-command test

repository rootの`GTP.md`、agent discovery file、GitHub workflow、repository settings、Check Run生成、
branch protection、release、package publication、automatic installationはrepository integrationが所有する。
portable coreには含めない。

skill bundleはSkill Creatorの名前一致規則へ従い、`skill/agent-operated/`に置く。GTP 1.0.1が
Python 3.11以上を要求するため、detectorはPython 3.11 standard libraryだけで実装する。`gh`と`gtp`は
明示されたexternal commandであり、Python package内部moduleをimportしない。

GTP adapterはGTPのRecord、state、transition、Evidence validationを再実装しない。公開CLIのmachine
projectionを保持し、AO envelopeへ格納するだけとする。`authority: none`を変更せず、GTPの`halt`と
Acquisition Errorを分離する。adapterのdefault compatibility targetは公開release `1.0.1`とし、これは
taskごとのprotocol forkではなくexecutable interfaceの検査条件である。

private recoveryでは次の順序を守る。

1. ambient `GH_TOKEN`と`GITHUB_TOKEN`を除外する。
2. 隔離GitHub CLI profileのlive actorをloginとnumeric IDで確認する。
3. 同じprofileからtokenを取得する。
4. tokenをGTP child processのenvironmentだけへ渡す。
5. token、credential path、raw stderrをAO outputまたはdurable recordへ出さない。

portable coreの完成は、raw skill pathから全detectorが実発火し、deterministic testが通り、repository固有の
authorityまたはEvidenceがないtransitionを正しく停止できることまでとする。GTP Done、exact-head Check Run、
Human Account native merge、post-merge `done` recoveryを含むoperational baselineはrepository integration後に
別candidateで実証する。

## Language

このdecisionが導入または補正する語彙のcanonical ownerは[CONTEXT.md](../CONTEXT.md)とする。
`GTP closeout`は、GTP v1に独立したcloseout Recordまたはcommandがあるように読めるため使用しない。

## Consequences

### Positive

- 独立repositoryへ移すとき、実行pathやrepository identityの意味を書き換えずに済む。
- GTP stateとAO conformanceが別のcanonical ownerを保つ。
- private read credentialをambient tokenへ戻さず、GTP CLIへ接続できる。
- root workflowがない段階でもraw-pathとlocal commandでportable attachmentの実発火を検査できる。

### Negative and limits

- portable coreだけではGTP task completionまたはHuman acceptanceを実証できない。
- GTP executableがhostへ存在しない場合、live recoveryは`unknown`となる。
- CLIのhuman-first stdoutからmachine JSONを取り出すcompatibility adapterを1.0.1に対して検査する必要がある。
- repository integration時にroot files、workflow、release policyを別contractで決める必要がある。

## Rejected alternatives

### `00-lab` root integrationを先に作る

独立repositoryへの昇格でroot filesとworkflowを作り直し、portable boundaryの検査が遅れるため採用しない。

### GTP state readerをAO内へ実装する

GTPのcanonical lifecycleをforkし、version drift時に二つの正本が生じるため採用しない。

### GTP repositoryを変更して`GH_CONFIG_DIR`を直接読む

今回のauthorityはAO側だけであり、GTP側を変更せず接続する条件にも反するため採用しない。

## Acceptance for this decision

- 変更pathが`agent-operated/**`に限定される。
- skill folder名とfrontmatter nameが`agent-operated`で一致する。
- raw-path testが全portable attachmentを実発火させる。
- credential fixtureに含まれる値がstdout、stderr、findingへ現れない。
- GTP projectionの`authority`、`state`、`next_action`をAOが別tokenへ変換しない。
- repository固有identityとroot integrationがportable executableへ混入しない。
