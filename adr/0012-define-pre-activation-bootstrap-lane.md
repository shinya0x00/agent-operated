# ADR-0012: Production Active前のHuman-approved bootstrap laneを限定する

- Status: Accepted
- Date: 2026-07-22
- Decision owner: operator
- Scope: Issue #22
- Refines: ADR-0009、ADR-0010

## Context

ADR-0009とADR-0010は、repository mutationより前にhost固定providerの`check_plan`を発火させ、検査済みplanと
Actor Profileからcurrent `InvocationContext`を作る境界を定めた。root `AGENTS.md`もこの境界を最初のfile mutationへ
要求した。

しかしproduction providerの実装と実host transitionへの接続はIssue #16が所有し、その前にHost Enforcementの設計、
broker、bootstrap、binding、leaseを実装する必要がある。provider未接続の状態からprovider接続に必要な最初のrepository
変更までcurrent `InvocationContext`を要求すると、通常gateは自分自身を実装できない。test providerを使用すれば循環は
見かけ上解消するが、fixtureまたはtask-controlled providerをwrite preconditionへ昇格するため採用できない。

## Decision

Host Enforcementの導入状態を`Host Enforcement Installed`と`Production Active`へ分離する。

- `Host Enforcement Installed`はroot admissionまたは配布物の存在を示すが、production providerの実host接続をClaimしない。
- `Production Active`はhost-level Repository Integrationがproduction providerをin-processで固定注入し、real transitionで
  current `InvocationContext`を作れることをtyped observationで示し、target repository外の単調な`Activation Latch`へ保持する。

activation sourceと`Activation Latch`のownerはhost-level Repository Integrationだけとする。task本文、prompt、environment variable、
filesystem marker、repository config、agent request、fixture、test providerからactivation、latch reset、provider、例外を選択しない。
provider実装、内部規則、identity、version、diagnostic、private error sink、latch storageはIssue #16が引き続き所有し、
このdecisionへ移さない。

`Host Enforcement Installed`かつ`Production Active`ではない期間だけ、Human/adminが明示する
`Pre-activation Bootstrap Lane`を認める。laneは次を同じtaskへ完全に束縛する。

1. canonical GitHub Issue URL
2. 同じIssueの有効なGTP Contract
3. Contractを参照する有効なGTP Start
4. Startに束縛された唯一のnon-default branch
5. Contractが列挙するrepository-relative scope
6. 同じIssueとbranchの単一Draft PR
7. Human/adminによる明示的な開始とGitHub native actor observation

laneが許可するoperationはscope内file edit、commit、push、Draft PR作成までとする。PR ready化、merge、default branch
direct push、別Issue、別branch、別repository、追加PR、Contract scopeの拡張を許可しない。入力の欠落、取得不能、不一致では
dependent mutationを発火させない。

このlaneはInternal Policy Gate、provider、Operation、Operation Receipt、Human-only Exceptionの代用品ではない。
private decisionを生成せず、GTP Recordの意味またはauthorityを変更しない。Issue #22の最初のrepair PRはlaneがまだroot
adapterに存在しないため、Operatorが明示したHuman/admin経路で作成する。この一回限りの経路を後続taskへ再利用しない。

hostが`Production Active`を観測し`Activation Latch`を設定した時点でlaneは利用不能になる。Agent、task、repositoryはactivationを
falseへ戻せず、laneを再有効化できない。active後のprovider unavailableまたは設定済みlatchのread failureは通常laneを停止し、
pre-activation laneへfallbackしない。latchを読めないことを未設定と推測しない。

## Considered options

### Issue #16を前倒しする

providerはhost-level Repository Integration、private error sink、実transitionを必要とし、#12と#15のattachmentがない状態では
real firingを検証できない。内部境界をmockして接続済みとClaimすることになるため採用しない。

### test providerで最初のInvocation Contextを作る

fixtureまたはtask-controlled objectをproduction write preconditionへ昇格し、現在のPortable Coreが守る境界を破るため採用しない。

### provider unavailable時は常にHuman approvalで続行する

恒久的なfail-open経路となり、Production Active後も通常gateを迂回できるため採用しない。

### Human/adminがdefault branchを直接修復する

review可能なcandidate、scope差分、native PR recordを失うため採用しない。

## Consequences

- provider接続前でも、名前付きtaskと限定scopeから単一Draft PRまでをHumanが監督してbootstrapできる。
- test providerまたはprivate provider情報をrepositoryへ置かず、Issue #16のcanonical ownershipを維持できる。
- first repairを含むpre-activation変更は通常のcurrent `InvocationContext`保護を受けないため、その限界をPRへ明示しHumanが直接確認する必要がある。
- Draft PR作成はmerge authorityまたはtask completionを意味しない。Human Accountによるnative mergeは別decisionである。
- Production Active後は通常laneだけになり、pre-activation経路をincident recoveryや利便性のために再利用できない。

## Acceptance for this decision

- root admissionがInstalledとProduction Activeを区別する。
- activation sourceと単調なActivation Latchがhost-level Repository Integrationへ固定される。
- bootstrap laneのIssue、Contract、Start、branch、scope、Draft PR条件がclosedである。
- test provider、environment、task本文、prompt、marker、agent requestがactivation sourceにならない。
- Issue #16のprovider実装scopeを変更しない。
- Issue #22のcandidateはHuman/admin経路の一つのbranchとDraft PRに限定される。
