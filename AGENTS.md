# Repository agent instructions

## GitHub Task Protocol adapter

> このrepositoryはrootの`GTP.md`をtask protocolの唯一の正本とする。GitHub Issue URLを受け取ったら、Issue commentをServer Orderで読み、4 Record、6 state、7 halt reasonに従って既存branch・PR・次のprotocol actionを再構成する。Recordを推測、編集、独自拡張せず、矛盾時は原因URLを示して止まり、取得不能はhaltと混同しない。GTPの表示やRecordは変更・完了・mergeの権限を与えない。

## AO task admission

- read-onlyの調査、説明、状態確認はtask Issueなしで行ってよい。
- 通常のrepository mutationを始める前に、対象repositoryのcanonical GitHub Issue URLを一つ確定する。file編集、branch作成、commit、push、PR作成を先行させない。
- Issue URLがない変更依頼では、repositoryを変更しない。依頼がIssue作成を含む場合に限り、live Machine Accountを確認した上で、task Issueを一件作成する。このtask-Issue bootstrapだけがIssue URL確定前に許されるGitHub mutationである。
- Issue作成後、root `GTP.md`に従って公式task stateをrecoverする。`unmanaged`ではContract投稿だけ、`ready`では唯一のnon-default branch作成とStart投稿だけを次のprotocol actionとして扱う。
- Host Enforcementのactivation stateはhost-level Repository Integrationだけが観測し、target repository外の単調な`Activation Latch`へ保持する。repository、Issue、task本文、prompt、environment variable、marker、agent request、fixture、test providerから`Production Active`、latch reset、例外を選択してはならない。
- `Production Active`では、repository fileの最初の変更は、Start投稿後のrecoveryで同じIssueとbranchが`in_progress`として観測され、production providerによるtarget-native plan検査からcurrent `InvocationContext`が作られた後に限る。
- `Host Enforcement Installed`だが`Production Active`ではない期間は、次のすべてをHuman/admin経路が明示的に確認した場合だけ`Pre-activation Bootstrap Lane`を使用できる。
  - 一つのcanonical GitHub Issue URL
  - 同じIssue内の有効なGTP Contractと、そのContractを参照する有効なGTP Start
  - Startに束縛された唯一のnon-default branchと、現在checkoutしているbranchの一致
  - Contract `scope`に列挙されたrepository-relative pathだけを変更すること
  - delivery targetが同じIssue・branchの単一Draft PRだけに限定されていること。PR作成前は対象branchのPRが0件、作成後は同じIssue・branchのDraft PRが1件だけであること
- PRが0件の`pre-PR state`では、scope内file edit、commit、branch push、単一Draft PR作成だけを許可し、push後はそのDraft PR作成以外のmutationを許可しない。
- PR作成後は、そのPRがDraftかつ同じIssue・branchの唯一のPRである間だけ`Pre-activation Bootstrap Lane`を継続する。PRのready化、merge、default branch direct push、別Issue・別branch・別repository・追加PR、scope拡張を許可しない。条件の欠落または取得不能ではmutationを発火させない。
- `Production Active`をhostが観測して`Activation Latch`を設定した後は`Pre-activation Bootstrap Lane`を利用または再有効化せず、current `InvocationContext`を要求する通常laneだけを使用する。設定済みlatchまたはproviderの取得不能は通常laneを停止し、pre-activationへ戻さない。
- このlaneを導入する最初のrepair PRだけは、現在のgate自身が認可できないためIssue #22のHuman/admin経路で作成する。この一回限りの事実を後続taskのauthorizationとして再利用しない。
- `halt`、`done`、`stopped`、Acquisition Error、Issue・branch・contextの不一致ではrepository mutationを開始しない。
- current `Activation Latch`が設定済みのtaskは、`in_progress`へ進んだ時点にかかわらず[`skill/agent-operated/SKILL.md`](skill/agent-operated/SKILL.md)をagent-facing entryとし、production `check_plan`とcurrent `InvocationContext`を要求する通常laneを使用する。
- current `Activation Latch`が未設定で、`Host Enforcement Installed`だが`Production Active`ではないtaskだけが、通常skillの`prepare_plan`／Internal Policy Gate経路へ入らず、このroot admissionに列挙した`Pre-activation Bootstrap Lane`のclosed条件をagent-facing entryとして使用する。Agentが行うすべてのGitHub writeはMachine Accountのlive Actor Observationへ束縛する。Issue #22の最初のHuman/admin repairだけを上記の一回限りの例外とする。
- 1 Issue = 1 branch = 1 PRを維持する。別scope、別branch、別PRへ移る場合は、GTPのStopと新Issueを使用する。

GTP自体の初回setupまたはversion更新は、公開releaseをexact commitへ固定する専用setup branchとDraft PRで行う。default branchへ直接pushせず、人間がsetup PRをmergeするまで導入完了と扱わない。
