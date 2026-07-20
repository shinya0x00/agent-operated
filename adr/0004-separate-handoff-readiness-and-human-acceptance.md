# ADR-0004: handoff readinessとHuman Account acceptanceを分離する

- Status: Accepted
- Date: 2026-07-18
- Decision owner: operator
- Scope: `00-lab/agent-operated/`
- GTP task: [Issue #8](https://github.com/shinya0x00/00-lab/issues/8)
- Blocks: [Issue #7](https://github.com/shinya0x00/00-lab/issues/7)
- Doctrine ref:
  [`849a86f70ef315dbc9cbc5560579f39158b8f103`](https://github.com/shinya-reiji/doctrine/blob/849a86f70ef315dbc9cbc5560579f39158b8f103/DOCTRINE.md)

## Context

ADR-0001と`DESIGN.md`は、AI agentがcandidate PRをHuman Accountへhandoffし、acceptance decisionを
Human Accountだけが行うと定めた。この境界は維持する。

skill実装を開始したところ、`verify-pr-handoff`が二つの異なる時点を混同していることが分かった。

- handoff時点では、人間へこれからdecisionを求める。
- acceptance後のreadbackでは、既に存在するhuman decisionをcandidate headへ照合する。

さらに、通常運用ではoperatorがPR本文、差分、検査結果をCodexと同じ作業の流れで確認し、そのまま
Human Accountでmergeしている。別のApprove、review comment、reactionを証拠作りのためだけに要求すると、
同じ判断を二重入力する。reactionはactorをread backできても、head更新後にどのSHAへのreactionだったかが
曖昧になり、exact-head acceptanceのbaselineとして弱い。

## Decision

通常laneは`merge_policy: human_only`とし、handoff readiness、Human Account acceptance readback、
GTP closeoutを別phaseにする。

### Phase 1: handoff readiness

agentは、少なくとも次をcurrent candidate headへ結び付け、人間へ`acceptance_decision`を求める。

- GTP task referenceとactor profile reference
- full 40-character candidate head SHA
- Machine Account verification reference
- validation evidence
- wiringを変更した場合のfiringおよびvalidation evidence
- known unknownsと未解決finding

このphaseではhuman decisionはまだ存在しない。Approve、review comment、reaction、merge factを必須にしない。
readinessの`verdict: proceed`は「このexact headをHuman Accountへ提示できる」というAO conformanceだけを
示し、acceptance、merge authorization、task completion、GTP closeoutを意味しない。

### Phase 2: Human Account acceptance readback

通常laneのbaseline acceptance evidenceは、宣言済みHuman Accountがexact candidate headのPRをmergeした
GitHub native factとする。readbackは少なくとも次を照合する。

- PRの`head.sha`がhandoffしたcandidate head SHAと完全一致する。
- PRがmergedであり、`merged_at`が存在する。
- `merged_by.login`と`merged_by.id`がactor profileのHuman Accountと一致する。
- handoff後にheadが変わっていない。

`merge_commit_sha`は、open PRに対するGitHubのtest merge commitとしてmerge前から存在する場合があり、
merge後はmerge方式に応じた結果commitを指す。どちらもhandoff candidateのcanonical ownerではない。
squash、rebase、merge commitの方式にかかわらず、candidate照合にはPRの`head.sha`を使う。

Approve、review comment、reactionは追加Evidenceとして利用できるが、baselineでは必須にしない。botは
Human Accountの判断を代筆するreview commentを、acceptance evidenceとして作成しない。

会話は人間が何を確認したかを伝える作業cacheとして使えるが、単独ではdurable acceptance evidenceにしない。
Human AccountがmergeしなければacceptanceをClaimしない。headが変わった場合、以前のreadinessとacceptanceは
staleであり、新しいheadを再handoffする。

### Phase 3: GTP closeout

merge後の結果復元と完了記録はGTPが所有する。AOはactor profile、exact head、native merge factの照合結果を
GTP evidenceから参照可能にするが、AO detectorの`proceed`をcloseout authorizationとして使用しない。

### Machine Account merge lane

Machine AccountがmergeしたfactからHuman Accountの確認を推論しない。long-run operationでbot mergeが必要に
なった場合は、通常laneとは別に、少なくとも次をtask contractと新しいADRで定める。

```yaml
merge_policy: machine_allowed
machine_merge_authorization_ref: <durable policy or task-contract reference>
```

そのlaneはrequired checks、dependency PR、allowed branch、target repository、exact candidate、failure behaviorを
事前に固定する自動昇格であり、`human acceptance`とは呼ばない。今回のskill baselineへ導入しない。

## Relationship to ADR-0001

このADRはADR-0001のhuman-only acceptance boundaryを維持し、「direct review」をformalなGitHub Review eventの
必須化として解釈する部分だけを置き換える。Human Accountがcandidateを直接確認する責任は変わらない。

## Consequences

### Positive

- operatorは同じ判断をApprove、comment、reactionへ重複入力せずに済む。
- PR headとnative merge actorを一つのGitHub objectからread backできる。
- pre-decision checkerへ、まだ存在しないhuman decisionを要求しない。
- squashやrebaseでもcandidate headとmerge result commitを混同しない。
- 将来のMachine Account mergeをhuman acceptanceへ偽装せず、別laneとして拡張できる。

### Negative and limits

- merge前に「承認だけ記録して待つ」baselineは持たない。
- mergeしない却下や保留をdurable human decisionとして表す共通profileは未定である。
- native mergeはHuman Accountが内容を理解したことを機械的に証明しない。判断可能なPR artifactは引き続き必要である。
- auto-mergeやservice actorによるmergeは、Human Account actor一致を満たさない限り通常laneのacceptance evidenceにならない。

## Alternatives considered

### GitHub Approveを必須にする

mergeと別に同じ判断を入力させ、現在の個人運用では追加の証拠強度より摩擦が大きいため採用しない。

### Review commentを必須にする

Codexとの作業で解決済みの内容をGitHubへ再掲させ、botによる代筆も誘発するため採用しない。

### Reactionをacceptance evidenceにする

actorは観測できるがreactionが対象にするcandidate SHAをnative fieldで固定できず、head更新時に曖昧になるため
baselineへ採用しない。

### Conversationだけをacceptance evidenceにする

GitHubだけを読むclean sessionが復元できず、Doctrine R2とAOのdurable-state principleを満たさないため却下する。

## Acceptance evidence for implementation

- readiness modeはhuman decisionなしでexact-head handoffを検査できる。
- readinessの`proceed`にacceptance、merge、completion、closeout claimが含まれない。
- acceptance readbackはlive PRから`head.sha`、`merged_at`、`merged_by.login`、`merged_by.id`を取得する。
- stale head、wrong human actor、service actor、unmerged PRを通常laneのacceptanceとして拒否する。
- Approve、review comment、reactionがなくても、正しいHuman Account native mergeでbaseline acceptanceを満たす。
- bot-authored review commentがHuman Account evidenceへ昇格しない。

## Known unknowns

- mergeしないhuman rejectionまたはholdを、将来どのGTP recordで表すか。
- Machine Account merge laneを必要とする最初のlong-run taskが、どのauthorization policyを採用するか。

これらは通常laneのskill baselineへ推測で追加しない。
