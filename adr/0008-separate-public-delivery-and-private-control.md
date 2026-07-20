# ADR-0008: Public Delivery RouteとPrivate Control Routeを分離する

- Status: Accepted
- Date: 2026-07-20
- Decision owner: operator
- Scope: PR #1 / Issue #2
- Supersedes: ADR-0007のprivate policy integration境界

## Context

ADR-0007はAOを薄いrouting-and-binding Hubへ限定したが、private policy checkを公開Operationとして扱い、
source identity、version、rule、planning provenanceをOperation Receipt、設計文書、PR、Issueへ投影できる構造を
残していた。この構造では、AOがprivate policyの公開projectionと第二のcanonical ownerになり得る。

一方、publication artifactからsecret-shaped value、credential location、private context、local absolute path、
ephemeral runtime IDを検出するcheckは、private policy provenanceがなくても独立した利用価値を持つ。

## Decision

AOのroutingを次の二経路へ分離する。

- **Public Delivery Route**は、GTP、Publication Screening、将来のread-only acceptance report等、Human Accountへ
  提示する独立したOperation resultを取得する。resultは固有語彙を保ったままOperation Receiptへ束縛できる。
- **Private Control Route**は、host固定providerによるInternal Policy Gateをphase transition前に呼ぶ。decisionは
  invocation-localに使用し、Operation、Operation Receipt、acceptance Evidence、設計provenanceへ変換しない。

Internal Policy Gate portは`check_plan`、`check_candidate`、`check_projection`を持つ。providerはhostがin-processで
注入し、task content、environment variable、filesystem path、argvから選択できない。AOが受け取るdecisionは
`proceed`または`blocked`とtarget-native findingだけであり、private rule、provider identity、version、非公開診断、
provenanceを公開data modelへ追加しない。

Publication Screeningはsource-neutralな公開Operationとして
`scripts/operations/publication/check.py`に置く。matched valueを再掲せず、公開適合全体またはsecret absenceを
Claimしない。

既にpushされたcommit履歴は書き換えない。current treeと変更可能なPR・Issue本文を新しい境界へ合わせ、履歴に残る
旧projectionはcurrent design authorityまたはcurrent candidate evidenceとして再利用しない。

## Consequences

- AO Coreはphaseとroute selectionを所有するが、private policyの意味またはproviderを所有しない。
- Human Accountへ渡すReceiptからprivate control metadataを除外できる。
- production providerの実装と実発火はhost integrationで別に証明する必要がある。
- pushed historyには旧projectionが残るため、current treeだけで過去の非公開性をClaimできない。
- history rewriteを伴わずPR #1を同じbranchで修正できる。
