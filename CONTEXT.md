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

**GTP Recovery Projection**:
GTPがGitHubのRecordとnative factから再構成したtask stateのProjection。
_Avoid_: AO state、AO verdict

**AO Conformance**:
actor、credential、record、wiring、handoffがAOの境界に適合するというAO固有の判定。
_Avoid_: GTP completion、merge authorization

**Portable Core**:
特定repository固有のintegrationを含まない、AOの移植可能なOperation単位。
_Avoid_: standalone product、repository integration

**Repository Integration**:
Portable Coreと特定repositoryの運用面を結ぶrepository固有の構成。
_Avoid_: portable core

**Handoff Readiness**:
Human Accountへexact Candidate Headのdecisionを求められる状態を示す、decision前のAO Conformance。
_Avoid_: approval、acceptance

**Acceptance Readback**:
native merge後にCandidate HeadとHuman Account actorをGitHubから再取得して照合するAO phase。
_Avoid_: review comment、reaction、GTP completion

**Post-Merge Recovery**:
native merge後にGTP task stateとAO Acceptance Readbackを、それぞれのcanonical ownerから再取得するphase。
_Avoid_: GTP closeout
