# Agent Operated

AOでGitHub taskの主体、状態、Evidence、handoff境界を一貫して説明するための語彙である。

## Language

**Machine Account**:
AI agentによるGitHub mutationを帰属させる、宣言済みのGitHub principal。
_Avoid_: bot identity、agent identity

**Human Account**:
candidateを直接確認し、通常laneのacceptance decisionを行う宣言済みのGitHub principal。
_Avoid_: operator signal、human evidence

**Actor Profile**:
Machine AccountとHuman Accountのlogin、stable numeric ID、human-only operationを定義するAOの正本。
_Avoid_: credential profile、user config

**Candidate Head**:
validation、handoff、acceptanceの対象となるPR source branchのfull commit SHA。
_Avoid_: branch name、`merge_commit_sha`

**AO Core**:
actorとcredential role、operation phase、Adapter routing、task・Candidate Head・Operation resultのbindingを所有するAOの中心境界。
_Avoid_: Operation Hub全体、総合安全判定

**Operation**:
特定phaseで外部正本または検査器を呼び、その固有語彙のresultを返す実行単位。
_Avoid_: AO Core、AO feature

**Adapter**:
Operationと外部interfaceのtransportおよびversion境界を接続し、外部の意味を変更しない接続単位。
_Avoid_: translator、canonical owner

**Operation Receipt**:
一つのOperation resultをtask、phase、実装version、source、および必要なCandidate Headへ束縛するAOのRecord。
_Avoid_: AO verdict、総合合否

**Actor Observation**:
一つのcredential circuitからGitHubが返したloginとstable numeric IDの観測結果。
_Avoid_: Candidate Binding、actor claim

**Candidate Binding**:
Operation resultまたはHuman acceptanceを一つのCandidate Headへ結び付け、その一致、不一致、非適用、取得不能を示すAOの関係。
_Avoid_: Actor Observation、branch binding

**GTP Recovery Projection**:
GTPがGitHubのRecordとnative factから再構成したtask stateのProjection。
_Avoid_: AO state、AO verdict

**Portable Core**:
特定repository固有のintegrationを含まない、AO Coreと同梱Operationの移植可能な配布境界。
_Avoid_: standalone product、repository integration

**Repository Integration**:
Portable Coreと特定repositoryの運用面を結ぶrepository固有の構成。
_Avoid_: portable core

**Handoff Readiness**:
Human Accountへtask、PR、必要なCandidate Head、Actor Observation、Operation Receipt、unknownとdecision requestを提示できる状態。
_Avoid_: approval、acceptance

**Acceptance Readback**:
native merge後にCandidate HeadとHuman Account actorをGitHubから再取得して照合するAO phase。
_Avoid_: review comment、reaction、GTP completion

**Post-Merge Recovery**:
native merge後にGTP task stateとAO Acceptance Readbackを、それぞれのcanonical ownerから再取得するphase。
_Avoid_: GTP closeout
