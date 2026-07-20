# GitHub Task Protocol (GTP) v1

GTPは、GitHub Issue上のRecordとGitHubの観測事実から、AI coding taskの現在地を再構成するための最小protocolである。このファイルだけを公開仕様の正本とする。

GTPは作業、完了宣言、review、mergeの権限を与えない。actorの本人性、credential、権限、Evidenceの内容の真実性、悪意あるrepository管理者への耐性も証明しない。

## 1. 導入

1. repository rootへこの`GTP.md`をコピーする。
2. `AGENTS.md`、`CLAUDE.md`など、agentが必ず読む文書へ「共通adapter文」を1段落追加する。
3. taskごとに1 Issueを作り、下記のCarrierをIssue commentとして投稿する。

CLIは任意である。Issue、comment、branch、commit、PRだけでもprotocolを実行できる。

## 2. 固定語彙

Record typeは4種類だけである。

```text
contract | start | done | stop
```

公開stateは6種類だけである。

```text
unmanaged | ready | in_progress | halt | done | stopped
```

`halt_reason`は7種類だけである。細かな原因は`details`で説明し、この語彙を増やさない。

```text
invalid_record
conflicting_records
invalid_transition
invalid_binding
invalid_evidence
stale_evidence
terminal_violation
```

## 3. Exact Carrier

1件のRecordは、1件のGitHub Issue comment全文であるCarrierに入れる。正準形は次のとおりである。

````markdown
<!-- gtp-record:v1 -->
契約を確定した

<details><summary>記録(JSON)</summary>

```json
{ ... }
```

</details>
````

Carrierは次の条件をすべて満たす。

- Exact Marker `<!-- gtp-record:v1 -->`が最初の非空行に完全一致する。
- markerの次の非空行は、空でない1行の人向け要約である。
- 要約の後は、上記と完全に同じ`<details>`、`summary`、`json` fenceを使う。
- JSON fenceは1個だけで、内容はRecord object 1個だけである。
- `</details>`の後にproseを置かない。指定箇所の空行だけを許す。
- JSONはduplicate key、`NaN`、`Infinity`を認めないstrict JSONである。

markerのないcommentは通常commentとして無視する。markerのtypoもlive readerは推測せず通常commentとして扱う。Exact MarkerがあるのにCarrier、JSON、schemaが壊れている場合は`halt / invalid_record`である。

投稿後に本文が編集され、GitHub metadataの`updated_at`と`created_at`が異なるCarrierは`halt / invalid_record`である。訂正は編集ではなく、後述の`stop`と新Issueで行う。

## 4. 共通scalar

- `gtp`は文字列`"1.0"`だけを許す。
- `id`はlowercase canonical UUID v4とする。
- SHAはlowercase 40桁hexのfull commit SHAとする。
- condition IDは`^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$`とする。
- textは空でなく、前後whitespaceとcontrol characterを持たない文字列とする。
- `scope` pathはrepository-relativeな正確なfileまたは末尾`/`付きdirectoryとする。`.`だけはrepository全体を表す。絶対path、glob、空segment、`.` segment、`..` segmentを拒否する。
- branchはshort nameとする。URL、`refs/heads/`、空文字を拒否する。
- GitHub URLは`https://github.com`のcanonical URLだけを許し、query、独自port、credentialを拒否する。

Resource URLは次の形だけを使う。`N`は先頭0のない正整数、`SHA`はfull commit SHAである。

```text
Issue:         https://github.com/OWNER/REPO/issues/N
Issue comment: https://github.com/OWNER/REPO/issues/N#issuecomment-N
PR:            https://github.com/OWNER/REPO/pull/N
Check Run:     https://github.com/OWNER/REPO/runs/N
Artifact:      https://github.com/OWNER/REPO/blob/SHA/PATH
```

## 5. Closed schema

すべてのobjectはclosed schemaである。以下にないfield、未知のRecord type、未知versionを拒否する。`author`、`created_at`、`supersedes`などをRecordへ追加しない。投稿者、comment ID、時刻、URLはGitHub metadataをObservationとして使う。

### 5.1 `contract`

taskの目標、変更範囲、完了条件を確定する。fieldは次だけである。

| field | type | 規則 |
|---|---|---|
| `gtp` | string | `"1.0"` |
| `type` | string | `"contract"` |
| `id` | string | UUID v4 |
| `goal` | string | text |
| `scope` | array of string | 1件以上、重複なし |
| `done_conditions` | object | 1件以上のcondition map |

`done_conditions`のkeyはcondition IDである。各valueは`text`と`evidence_kind`だけを持つ。`evidence_kind`は`check`または`artifact`である。

### 5.2 `start`

有効なContractと唯一の作業branchを束縛する。fieldは次だけである。

| field | type | 規則 |
|---|---|---|
| `gtp` | string | `"1.0"` |
| `type` | string | `"start"` |
| `id` | string | UUID v4 |
| `contract_ref` | string | 同じIssue内の先行Contract comment URL |
| `branch` | string | Issue repository内のbranch short name |

### 5.3 `done`

特定source headについて、完了条件ごとのEvidenceを持つDone Claimを示す。Task Completionそのものではない。fieldは次だけである。

| field | type | 規則 |
|---|---|---|
| `gtp` | string | `"1.0"` |
| `type` | string | `"done"` |
| `id` | string | UUID v4 |
| `pr_ref` | string | Start branchをheadに持つ同一repository PR URL |
| `head_sha` | string | PR source headのfull commit SHA |
| `evidence` | object | condition IDからEvidence URLへのmap |

`evidence`のkey集合は、Bound Contractの`done_conditions`のkey集合と完全一致しなければならない。各URL kindは、対応する`evidence_kind`と一致しなければならない。

### 5.4 `stop`

完了を主張せずIssueを放棄する。fieldは次だけである。

| field | type | 規則 |
|---|---|---|
| `gtp` | string | `"1.0"` |
| `type` | string | `"stop"` |
| `id` | string | UUID v4 |
| `reason` | string | `"abandoned"`または`"superseded"` |
| `successor_ref` | string or null | `superseded`では後継Issue URL、`abandoned`では`null` |

## 6. 完全な記入例

値は例であり、実際のIssue、comment、branch、PR、SHA、Evidenceへ置き換える。

### Contract

````markdown
<!-- gtp-record:v1 -->
GTPの仕様正本を作成する契約を確定した

<details><summary>記録(JSON)</summary>

```json
{
  "gtp": "1.0",
  "type": "contract",
  "id": "123e4567-e89b-42d3-a456-426614174000",
  "goal": "GTP.mdだけでprotocolへ参加できるようにする",
  "scope": ["GTP.md", "DECISIONS.md"],
  "done_conditions": {
    "spec_exists": {
      "text": "GTP.mdが400行以内で存在する",
      "evidence_kind": "artifact"
    },
    "tests_pass": {
      "text": "仕様conformance checkが成功する",
      "evidence_kind": "check"
    }
  }
}
```

</details>
````

### Start

````markdown
<!-- gtp-record:v1 -->
契約と作業branchを束縛して開始した

<details><summary>記録(JSON)</summary>

```json
{
  "gtp": "1.0",
  "type": "start",
  "id": "223e4567-e89b-42d3-a456-426614174001",
  "contract_ref": "https://github.com/example/project/issues/6#issuecomment-1001",
  "branch": "issue-6-minimal-spec"
}
```

</details>
````

### Done

````markdown
<!-- gtp-record:v1 -->
source headに完了条件ごとのEvidenceを提示した

<details><summary>記録(JSON)</summary>

```json
{
  "gtp": "1.0",
  "type": "done",
  "id": "323e4567-e89b-42d3-a456-426614174002",
  "pr_ref": "https://github.com/example/project/pull/20",
  "head_sha": "0123456789abcdef0123456789abcdef01234567",
  "evidence": {
    "spec_exists": "https://github.com/example/project/blob/0123456789abcdef0123456789abcdef01234567/GTP.md",
    "tests_pass": "https://github.com/example/project/runs/3001"
  }
}
```

</details>
````

### Stop

````markdown
<!-- gtp-record:v1 -->
このIssueを放棄して後継Issueへ移る

<details><summary>記録(JSON)</summary>

```json
{
  "gtp": "1.0",
  "type": "stop",
  "id": "423e4567-e89b-42d3-a456-426614174003",
  "reason": "superseded",
  "successor_ref": "https://github.com/example/project/issues/21"
}
```

</details>
````

## 7. Server Order、retry、履歴規則

Issue commentはGitHub comment IDの昇順で読む。record内の自己申告時刻は使わない。

同じ`id`かつ構造的に同じJSONの再投稿だけをsafe retry aliasとして1 Logical Recordへ畳む。object key順、JSON whitespace、人向け要約は同一性へ含めない。配列順と値は含める。同じ`id`で異なるJSONは`halt / invalid_record`である。

通常commentは履歴へ影響しない。Carrierを削除または編集して履歴を修復してはならない。複雑な訂正、Recordのjoin、Recordの置換は定義しない。

## 8. lifecycleとstate

### `unmanaged`

有効なRecordがない。通常commentだけの場合を含む。

### `ready`

有効なContractが1件あり、Startがない。

### `in_progress`

Startが唯一の先行Contractを`contract_ref`で指し、branchを束縛している。valid Doneがあってもnative merge前は`in_progress`であり、merge待ちとして説明する。

### `done`

valid Doneが指す`head_sha`を、Bound PRがnative mergeし、その後にterminal violationがない。比較対象はmerge commitではなくDoneが指したsource headである。branch削除後もIssue、Done、PR、merge factから再構成する。

### `stopped`

証明済み`done`より前に、最後のrecognized Carrierとして唯一のvalid Stopがあり、その後に対象PRのmergeがない。Stopはpre-terminalな矛盾が先にあっても安全に放棄できる非常口である。

### `halt`

完全なObservationを取得できたが、Record、履歴、binding、Evidence、terminal規則の不適合により、次のprotocol actionを一意に進められない。

## 9. transition規則

- ContractはStartより前に1件だけ置く。複数Contractは`conflicting_records`である。
- Startは先行する唯一のContractを指す。Start後はContractとbranchを凍結する。
- StartなしのDone、Start後のContract、Record順序違反は`invalid_transition`である。
- Start、Done、Stopを複数の異なるLogical Recordとして置かない。
- 1 Issue = 1 branch = 1 PRとする。分割、統合、別branchへの移動はStopと新Issueで行う。
- Doneの`head_sha`はBound PRのsource headと一致し、全Evidenceも同じrepositoryとSHAへ束縛される。
- Stop後の新Recordまたは対象PR merge、証明済みDone後のStopや新Recordは`halt / terminal_violation`である。先に成立したterminal resultを別のterminal resultへ書き換えない。
- safe retry aliasは新Recordではないため、同一内容ならterminal後でも畳める。

## 10. halt reasonの境界

| reason | 意味 |
|---|---|
| `invalid_record` | Carrier、strict JSON、closed schema、scalar、編集、identity collisionが不適合 |
| `conflicting_records` | 同じ役割の異なるLogical Recordが複数存在 |
| `invalid_transition` | Recordの順序またはlifecycleが不適合 |
| `invalid_binding` | Contract、branch、PR、repositoryの参照関係が不適合 |
| `invalid_evidence` | Evidence key、kind、resource、success条件が不適合 |
| `stale_evidence` | Done後にPR source headが変わり、DoneまたはEvidenceのSHAが古い |
| `terminal_violation` | `done`または`stopped`成立後に新Recordや対象外mergeを観測 |

不適合結果には、最初に確認すべきGitHub commentまたはresource URLを必ず含める。

## 11. Stopによる安全な放棄

同一Issue内で壊れた履歴を複雑に修復しない。続行不能なら、最後のrecognized Carrierとしてvalid Stopを1件投稿し、必要なら新Issueを作る。

`reason: "superseded"`では`successor_ref`へ後継Issueを示す。`reason: "abandoned"`では`successor_ref: null`とする。Stop後は元Issueへ新Recordを投稿しない。

証明済みDoneは後のStopで`stopped`へ上書きできない。Stop後に対象PRがmergeされた場合も`done`へ変えない。どちらもpublic stateは`halt`、理由は`terminal_violation`とし、先に成立していたterminal resultを`details`へ残す。

## 12. Evidenceとnative merge

Evidence kindは`check`と`artifact`だけである。

- `check`は同じrepositoryのGitHub Check Runで、`status: completed`、`conclusion: success`、`head_sha == done.head_sha`を満たす。
- `artifact`は同じrepositoryの`done.head_sha`に存在するfileのimmutable blob permalinkである。

Check Runが証明するのはGitHubが指定SHAへsuccessを返したことまでであり、test内容の十分性までは証明しない。Artifactが証明するのは指定commitにfileが存在することまでであり、内容の真実性までは証明しない。

人間の最終受理はGitHub native PR mergeへ一本化する。Done ClaimとEvidenceだけではTask Completionにならない。

## 13. Acquisition Error

state決定に必要なIssue comments、branch、PR、Check Run、artifact、merge factを完全に取得できない場合、stateを出してはならない。これは`halt`ではなくAcquisition Errorである。

network、authentication、rate limit、pagination途中失敗をprotocol不適合と推測しない。取得できたresourceの不一致と、resourceを取得できないことを分離する。

## 14. Level 0とLevel 1

- Level 0はCLIを使わず、異なるruntimeのAgent AからAgent BへIssue URLだけを渡し、同じbranchとPRで重複なく再開できることを実GitHubで確認する。
- Level 1はrelease candidateのCLIを実GitHubへ接続し、原因URL付き`halt`、Evidence付きDone、native merge後の`done`、人間が日本語表示から判断できることを確認する。

unit testはLevel 0またはLevel 1の代わりではない。未実施の受け入れを完了と書かない。

## 15. 共通adapter文

次の1段落を`AGENTS.md`、`CLAUDE.md`などへコピーする。

> このrepositoryはrootの`GTP.md`をtask protocolの唯一の正本とする。GitHub Issue URLを受け取ったら、Issue commentをServer Orderで読み、4 Record、6 state、7 halt reasonに従って既存branch・PR・次のprotocol actionを再構成する。Recordを推測、編集、独自拡張せず、矛盾時は原因URLを示して止まり、取得不能はhaltと混同しない。GTPの表示やRecordは変更・完了・mergeの権限を与えない。

## 16. 公開v1に含めないもの

Repair Group、任意数leafのjoin、同一Issue内のRecord置換、Done active interval、Late Done専用機構、細分化されたtransition token、`human` Evidence、自己申告`author`・`created_at`、runtime別adapter、bot、自動投稿、自動merge、mutation command、dry-run、plan管理、dashboard、database、cacheは定義しない。

複数repository、fork PR、GitHub Enterprise Serverも公開v1の対象外である。
