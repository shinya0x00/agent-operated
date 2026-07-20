# ADR-0010: すべてのGitHub writeをlive actorとInvocation Contextへ束縛する

- Status: Accepted
- Date: 2026-07-20
- Decision owner: operator
- Scope: PR #1 / Issue #2
- Refines: ADR-0009

## Context

ADR-0009でprivate decisionとpublication bytesをtransitionへ接続したが、最初のmutationだけがActor Observationを要求し、
fixtureまたはbooleanでもwrite callbackを実行できた。candidate、publication、handoffもfresh Coordinatorから直接呼べたため、
GTP recoveryとplan checkを通った同じtaskへ構造的に束縛されていなかった。

検査済みplanとplan公開bytesの間にもorigin bindingがなく、Projection Batchの`target_ref`やscreening findingからlocal path、
URL、内部識別子が公開経路へ出る余地があった。Actor ProfileのMachine AccountとHuman Accountも同じnumeric IDを許容し、
Actor ObservationとAcceptance Readbackが同じProfile内容を使用したことを照合できなかった。

## Decision

AO Coreは一つのtyped GitHub Mutation Gateを持ち、すべてのGitHub write callback直前にoperation-scopedなlive Machine Account
Actor Observationを取得する。fixture、boolean、field不足のMappingはこの型へ変換せず、write authorizationに使用しない。

GTP task projection、検査済みplan、plan公開予定bytes、Actor Profile digestを一つのinvocation-local `InvocationContext`へ
束縛し、candidate check、publication、handoffへ同じcontextを要求する。candidate checkとhandoff preparationは任意callbackを
実行せず、context-boundな値だけを返す。GitHubへの効果はGitHub Mutation Gateまたはactor-gated publication routeだけが発火する。

plan publicationはchecked plan内のexact artifact bytesから直接batchを作る。一般Projection BatchはChecked Plan digestと
opaque artifact IDを持ち、`target_ref`をrepository-relative pathまたはclosed outbound-body vocabularyへ限定する。
Publication Screeningはfindingへraw `target_ref`を返さず、opaque artifact IDだけを返す。

Actor Profile parsingは一つのshared contractへ統合し、Machine AccountとHuman Accountに異なるnumeric IDを要求する。
Acceptance ReadbackはInvocation ContextのProfile content digestと一致するProfileだけを受理し、digestやpathを公開結果へ出さない。

## Consequences

- 最初のwriteが正しくても後続writeごとにactorを再確認する。
- 新しいCoordinator、stale plan、別task、別Profile、別candidateからprotected transitionを開始できない。
- plan check後の本文差し替えと、Projection identifier経由の非公開情報投影をportable coreで拒否できる。
- permissiveな旧Coordinator APIとの後方互換は維持しない。未release baselineの境界を一つの安全なrouteへ置き換える。
- production credential、provider、完全なbatch列挙、repository integration、native mergeは引き続きscope外である。
