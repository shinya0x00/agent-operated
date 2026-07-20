# ADR-0007: AOをrouting-and-binding Operation Hubへ限定する

- Status: Superseded by ADR-0008
- Date: 2026-07-20
- Decision owner: operator
- Scope: PR #1 / Issue #2

## Context

ADR-0006はportable coreをrepository integrationから分離したが、actor、GTP recovery、durable record gate、
wiring executor、handoffを同じAO固有判定の下へ置いた。この配置では、GTP、Merge Steward、private policy等を
追加するほどAOが外部正本の意味と実行方法を吸収し、第二のcanonical ownerまたは汎用executorになる。

Actor ObservationとCandidate Bindingも同じpreconditionへまとめられており、candidateが存在しないGitHub mutation前に
actorだけを確認できない。

## Decision

AOを、actorとcredential role、operation phase、Adapter routing、task・candidate・result bindingだけを所有する
薄いOperation Hubへ限定する。Human acceptance readbackはHuman AccountとCandidate Bindingを扱うAO Coreへ残す。

GTP recoveryはGTP Operation、publication screeningは公開Operationとして配置する。Operation Receiptは
共通の外枠だけを持ち、nested resultの語彙、verdict、authorityを変換しない。異なるOperation resultを一つのAO pass/fail
または安全スコアへ統合しない。

Actor ObservationはCandidate Headを成立条件にしない。candidate-dependentなresultとHuman acceptanceだけを独立した
Candidate Bindingでfull SHAへ結び付ける。

実commandはtrusted Operation Adapterが所有する。Evidence JSONから任意argvを選択して実行する共通wiring executorは
削除する。

このdecisionはADR-0006のportable boundaryを維持しつつ、portable coreの所有物を再定義する。ADR-0005の
present / attached / fired / validatedを区別する原則は維持するが、private policyに依存する機械checkは
Private Control Routeが所有する。

## Considered options

### 現在の総合AO detectorを拡張する

実装は追加しやすいが、外部正本の語彙とauthorityがAOへ移り、変更時に複数のcanonical ownerが生じるため採用しない。

### AO Coreから外部Operationをすべて除外する

routing Hubとしての実用性がなく、agentが個別skillを選ぶ二重routingへ戻るため採用しない。

### 薄いAO Coreとoperation-scoped Adapterを同梱する

AOが実行順とbindingを所有しながら、外部の意味と検査実装を分離できるため採用する。

## Consequences

- AO Coreはactor、phase、routing、bindingだけを変更理由にできる。
- GTP、Merge Steward、private providerのinterface変更は該当Adapterまたはrouteへ局所化される。
- Operation Receiptだけからmerge、task completion、総合安全性をClaimできない。
- repository discovery、host credential route、canary mutationは別のOperational Baseline contractが必要になる。
- Merge Steward接続はcanonical endpoint、schema、version、read credentialが固定されるまでunknownとして残る。
