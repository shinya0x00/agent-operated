# ADR-0009: private controlを実transitionとProjection Batchへ束縛する

- Status: Accepted
- Date: 2026-07-20
- Decision owner: operator
- Scope: PR #1 / Issue #2
- Refines: ADR-0008
- Refined by: ADR-0010

## Context

ADR-0008はPublic Delivery RouteとPrivate Control Routeを分離したが、private checkを呼べるportだけでは、
`blocked`後のmutation、publication、handoffを機械的に止められない。plan checkもGTP recoveryより前または最初の
mutation後に回避でき、projection checkへ渡した一部artifactや古いbytesと実際のpublicationを区別できなかった。

Acceptance Readbackはrequest内の`human_actor`を期待値にでき、Operation Receipt binderはinvalid inputへschema不適合な
null入りReceiptを返していた。Publication Screeningもcandidate contentを観測せず、callerが同じSHAを二つ渡しただけで
`bound`とClaimできた。

## Decision

薄いTransition CoordinatorをAO Coreへ追加する。CoordinatorはGTP recovery後にtarget-native planを作り、task projectionと
planをdigest-boundなinvocation-local `CheckedPlan`へ固定する。plan公開または最初のmutationの早い方、最初のcandidate、
publication、Human handoffをprivate decisionでgateし、`blocked`なら依存callbackを呼ばない。`CheckedPlan`はmutation
authorityではなく、新しいinvocation、task projection変更、materialなplan変更で作り直す。

provider exceptionとinvalid returnは固定された`internal_check_unavailable`へ変換する。raw errorはhost-private sinkだけへ
渡し、公開caller、stdout、stderr、Receipt、PR、Issueへ出さない。

publicationはhost-owned sourceが作る一つのimmutable Projection Batchを使用する。batchはoptional Candidate Head、uniqueな
target ref、artifact bytes、SHA-256 digestを持ち、同じobjectをprivate check、Publication Screening、publisherへ渡す。
portable coreはbatch内bytesの同一性を保証するが、production artifactの完全列挙はhost integrationが所有する。

Publication Screeningはtrusted candidate-content acquisitionが追加されるまでCandidate Bindingを`not_applicable`とする。
Acceptance Readbackはrequestの`human_actor`を拒否し、Actor Observationと同じconfigured Actor ProfileのHuman Accountを
使用する。task Issue、PR URL、native PR base repositoryの一致も要求する。invalid Receipt inputは専用error envelopeを返し、
Receipt schemaへnullを入れない。

## Consequences

- portの存在ではなく、blocked callbackが発火しないことをportable testで観測できる。
- check後のpublication payload差し替えを同一batchとdigestで検知できる。
- production provider、private error sink、完全なbatch列挙、candidate-content acquisitionはhost側の残存責務になる。
- pushed historyは書き換えず、current designとmutable delivery recordだけを新しい境界へ合わせる。
