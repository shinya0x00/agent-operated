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
異なるnumeric IDを持つMachine AccountとHuman Account、およびhuman-only operationを定義するAOの正本。
_Avoid_: credential profile、user config

**Invocation Context**:
一回のagent invocationで検査済みtask・planとActor Profileを同じtransition系列へ束縛するAOの一時的context。
_Avoid_: task ledger、mutation authority

**Candidate Head**:
validation、handoff、acceptanceの対象となるPR source branchのfull commit SHA。
_Avoid_: branch name、`merge_commit_sha`

**AO Core**:
actorとcredential role、operation phase、route selection、task・Candidate Head・Operation resultのbindingを所有するAOの中心境界。
_Avoid_: Operation Hub全体、総合安全判定

**Public Delivery Route**:
独立した利用価値を持つOperation resultを取得し、必要なCandidate Headへ束縛してHuman Accountへ渡すAOの経路。
_Avoid_: Private Control Route、総合安全判定

**Private Control Route**:
hostが提供する内部検査をphase transitionの前提として呼び、結果をinvocation-localに扱うAOの経路。
_Avoid_: Operation、Public Delivery Route

**Internal Policy Gate**:
host固定providerがplan、candidate、公開予定artifactを検査し、対象transitionだけを制御するinvocation-localな境界。
_Avoid_: Operation、Operation Receipt、汎用executor

**Operation**:
Public Delivery Routeの特定phaseで外部正本または検査器を呼び、独立した利用価値を持つresultを返す実行単位。
_Avoid_: AO Core、Internal Policy Gate、AO feature

**Adapter**:
Operationと外部interfaceのtransportおよびversion境界を接続し、外部の意味を変更しない接続単位。
_Avoid_: translator、canonical owner

**Operation Receipt**:
一つのOperation resultをtask、phase、実装version、source、および必要なCandidate Headへ束縛するAOのRecord。
_Avoid_: AO verdict、総合合否、Internal Policy Gate result

**Publication Screening**:
公開予定artifactから公開不適切な値の候補を検出し、matched valueを再掲せずfindingを返すsource-neutralなOperation。
_Avoid_: private policy conformance、secret absence proof

**Projection Batch**:
一回のpublicationで同じ検査済みplanに属し、検査と公開の対象になる完全かつ不変なartifact集合。
_Avoid_: caller-selected artifact list、検査後に再構築したpublication payload

**Actor Observation**:
一つのcredential circuitからGitHubがliveに返し、Actor Profileと一致したloginとstable numeric IDの観測結果。
_Avoid_: fixture result、Candidate Binding、actor claim

**GitHub Mutation Gate**:
GitHub writeの直前に、そのoperation向けのActor Observationを要求し、不一致ならwriteを発火させないAOの境界。
_Avoid_: first mutation preflight、mutation authority

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

**Production Surface**:
実運用completionとfailure matrixを、そのsurface自身のnative observationで証明しなければならないCodex実行面。現在のAOではCodex Desktop。
_Avoid_: bring-up surface、documentation-only target

**Bring-up Surface**:
component、interface、negative caseを制御可能に接続して検証する実行面。Codex CLIまたはcustom app-server clientを含むが、Production Surface Evidenceを代替しない。
_Avoid_: production fallback、acceptance substitute

**Desktop Host Attachment**:
Codex Desktop thread開始前または最初のmutation前に、Host Guard、Issue Binding、sandbox、Workspace Leaseを同じsessionへ固定するhost extension point。
_Avoid_: CLI flag、Hook output、custom client assumption

**Host Guard**:
hostが観測したrepository、binding、leaseからsession capabilityを決め、write capabilityをfail-closedに制限する境界。
_Avoid_: Hook guard、repository marker

**Hook Adapter**:
`SessionStart`／`PreToolUse`等でHost Guardがsanitiseした状態を表示・観測し、対応toolを実行前にdenyするUX境界。`continue: false`は
`PreToolUse`で非対応であり、一部tool pathもHookを通らないため、write capabilityの正本にはしない。
_Avoid_: Host Guard、write authority

**Repository Identity**:
GitHub owner/repository、git common identity、worktree identityを束縛し、repository root、linked worktree、subdirectoryを同じ対象として照合するhost contract。
_Avoid_: local path、remote URL string

**Issue Binding**:
明示操作でcanonical Issue URL、Repository Identity、GTP Projection digest、expected branch、generationを束縛したhost state。
_Avoid_: prompt URL discovery、GTP Record

**Issue Binder**:
canonical Issue URLとRepository Identityを検証し、公式GTP Projectionからgeneration付きIssue Bindingを作るhost component。
_Avoid_: URL scanner、GTP state machine

**Host Operational State**:
GTP Projectionとhost-local binding／handoff observationからcurrent capabilityを選ぶclosed projection。
_Avoid_: GTP state、AO verdict

**Workspace Lease**:
Repository Identity、Issue、branch、専用worktree、binding generation、expiryを束縛し、一つのwritable rootだけを許可するopaqueなhost capability。
_Avoid_: arbitrary path allowlist、repository marker

**Workspace Lease Manager**:
`active`なIssue BindingだけにWorkspace Leaseを発行し、branch、generation、expiry、handoff等の変化で失効させるhost component。
_Avoid_: generic worktree manager、agent-selected writable root

**GitHub Mutation Broker**:
Machine Account credentialを排他的に保持し、closedなtyped operationを一つのGitHub native mutationへ変換するhost service。
_Avoid_: generic executor、raw API proxy

**Human Exception**:
host admin surfaceだけが発行でき、repository、scopeとしてのallowed operations、reason、expiry、max uses、Human Actor Observationを束縛する期限付き例外。
_Avoid_: agent request、prompt exception、marker opt-out

**Finding Code**:
Host Enforcementがprivate diagnosticを漏らさず、拒否、取得不能、未確認attachmentの安定した理由を示すclosed token。
_Avoid_: raw error、private rule identity

**Host Enforcement Installed**:
Host Enforcementのroot admissionまたは配布物が存在するが、production Internal Policy Gate providerの実host接続はまだ成立したとみなさない導入状態。
_Avoid_: Production Active、provider configured

**Production Active**:
host-level Repository Integrationがproduction Internal Policy Gate providerをreal transitionへ固定注入し、current Invocation Contextを作れる導入状態。
_Avoid_: installed、test provider active、task-selected activation

**Activation Latch**:
Production Activeへ到達済みであることをhostが保持し、pre-activation状態への復帰を拒否する単調な記録。
_Avoid_: repository marker、task flag、resettable activation

**Pre-activation Bootstrap Lane**:
Host Enforcement InstalledからProduction Activeへ到達する前だけ、Human/adminが明示した一つのIssue、Contract、Start、branch、限定scope、Draft PRを束縛する一時的なrepair経路。
_Avoid_: Internal Policy Gate fallback、恒久例外、provider substitute

**Handoff Readiness**:
Human Accountへtask、PR、必要なCandidate Head、Actor Observation、Operation Receipt、unknownとdecision requestを提示できる状態。
_Avoid_: approval、acceptance

**Acceptance Readback**:
native merge後にCandidate HeadとHuman Account actorをGitHubから再取得して照合するAO phase。
_Avoid_: review comment、reaction、GTP completion

**Post-Merge Recovery**:
native merge後にGTP task stateとAO Acceptance Readbackを、それぞれのcanonical ownerから再取得するphase。
_Avoid_: GTP closeout
