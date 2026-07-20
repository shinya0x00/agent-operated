# Repository agent instructions

## GitHub Task Protocol adapter

> このrepositoryはrootの`GTP.md`をtask protocolの唯一の正本とする。GitHub Issue URLを受け取ったら、Issue commentをServer Orderで読み、4 Record、6 state、7 halt reasonに従って既存branch・PR・次のprotocol actionを再構成する。Recordを推測、編集、独自拡張せず、矛盾時は原因URLを示して止まり、取得不能はhaltと混同しない。GTPの表示やRecordは変更・完了・mergeの権限を与えない。

## AO task admission

- read-onlyの調査、説明、状態確認はtask Issueなしで行ってよい。
- 通常のrepository mutationを始める前に、対象repositoryのcanonical GitHub Issue URLを一つ確定する。file編集、branch作成、commit、push、PR作成を先行させない。
- Issue URLがない変更依頼では、repositoryを変更しない。依頼がIssue作成を含む場合に限り、live Machine Accountを確認した上で、task Issueを一件作成する。このtask-Issue bootstrapだけがIssue URL確定前に許されるGitHub mutationである。
- Issue作成後、root `GTP.md`に従って公式task stateをrecoverする。`unmanaged`ではContract投稿だけ、`ready`では唯一のnon-default branch作成とStart投稿だけを次のprotocol actionとして扱う。
- repository fileの最初の変更は、Start投稿後のrecoveryで同じIssueとbranchが`in_progress`として観測され、target-native planの検査からcurrent `InvocationContext`が作られた後に限る。
- `halt`、`done`、`stopped`、Acquisition Error、Issue・branch・contextの不一致ではrepository mutationを開始しない。
- `in_progress`以後は[`skill/agent-operated/SKILL.md`](skill/agent-operated/SKILL.md)をagent-facing entryとし、すべてのGitHub writeをMachine Accountのlive Actor Observationへ束縛する。
- 1 Issue = 1 branch = 1 PRを維持する。別scope、別branch、別PRへ移る場合は、GTPのStopと新Issueを使用する。

GTP自体の初回setupまたはversion更新は、公開releaseをexact commitへ固定する専用setup branchとDraft PRで行う。default branchへ直接pushせず、人間がsetup PRをmergeするまで導入完了と扱わない。
