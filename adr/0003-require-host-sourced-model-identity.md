# ADR-0003: model identityはhost側の観測から取得する

- Status: Accepted
- Date: 2026-07-18
- Decision owner: operator
- Scope: `00-lab/agent-operated/`
- GTP task: [Issue #5](https://github.com/shinya0x00/00-lab/issues/5)
- Rework of: [Issue #3](https://github.com/shinya0x00/00-lab/issues/3)
- Doctrine ref: unresolved（`agent-operated-bot`によるcurrent `main`取得が404だったため、このADRはDoctrine準拠を主張しない）

## 何が起きたか

[PR #4](https://github.com/shinya0x00/00-lab/pull/4)のprovenance projectionには、生成modelとして
`GPT-5`、trust classとして`runtime-reported`が記録された。しかし、その値をCodex hostやOpenAI APIの
responseから取得した証拠はなかった。operatorが画面で確認していたmodelは`GPT-5.6 Sol`だった。

問題は、model名の単純な書き間違いではない。生成を行うmodel自身が書いた文章を、hostが観測したmetadataの
ように扱ったことにある。modelは自分へ渡されたsystem prompt、製品表示、backend routing、aliasの解決結果、
provider内部のrevisionを完全には観測できない。したがって、modelの自然言語による自己申告はmodel identityの
authorityにならない。

ADR-0002は既に、model identityをmodelの自己申告から確定しないと定めていた。それでもPR #4で誤記を防げなかった
ため、identityを「誰が本文へ書くか」まで実行境界として固定する必要がある。

## Decision

artifactを生成したmodelのidentityは、modelが生成する本文の一部として決めない。Codex host、API client wrapper、
または同等のmodel外部のprovenance builderが、生成後にhost側の観測値を取得してartifactへ付与する。

modelが生成してよいのはprovenanceを除くcore bodyと、provenance builderが必要とする非identityのcontextまでとする。
`model_id`、`model_revision`、identity source、trust classはhost側が所有する。model outputからこれらを抽出して
検証済みidentityへ昇格させてはならない。

### 取得元の優先順位

#### Codex local session

1. Codex hostがhook inputへ渡す`model` fieldを、local sessionの第一候補とする。Codex hooksの公式仕様では、
   common inputにある`model`はactive model slugを示すCodex-specific extensionである。
2. CLIの`/status`表示またはDesktopのmodel selectorを人間が確認した値は、`operator-observed`の補助証拠として
   記録できる。ただしhostから機械的に取得した値へ昇格させない。
3. model output内の自己申告は`self-reported`であり、identityの検証や自動gateには使用しない。
4. host hookを利用できない、または発火を確認できないsurfaceでは、値を推測せず`unknown`とする。

公式資料:

- [Codex hooks](https://learn.chatgpt.com/docs/hooks.md)
- [Codex CLI slash commands](https://learn.chatgpt.com/docs/developer-commands.md?surface=cli)
- [Codex models](https://learn.chatgpt.com/docs/models.md)

#### OpenAI API

OpenAI Responses APIを使うclientでは、作成されたresponse objectの`model` fieldを、そのresponseを生成したmodel IDの
host側観測値として記録する。requestの`model` fieldは「要求したmodel」であり、生成結果から読み返した観測値とは
別に扱う。

公式資料:

- [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)

### model IDとmodel revisionを分離する

`gpt-5.6-sol`のような値はmodel IDまたはactive model slugとして記録する。それだけで、provider内部のweights、
deployment、snapshot、immutable backend revisionまで特定できたとは主張しない。

hostまたはproviderが検証可能なrevisionを提供しない場合、`model_revision`は`unknown`とする。model IDをrevision fieldへ
複製したり、時刻や製品名からrevisionを推測したりしない。

### 最小evidence

model identity evidenceは、値だけでなく少なくとも次を分離して保存する。

| Field | Meaning |
| --- | --- |
| `model_provider` | hostが報告したprovider。取得できなければ`unknown` |
| `model_id` | hostまたはAPI responseが報告したmodel ID / slug |
| `model_revision` | 検証可能なimmutable revision。取得できなければ`unknown` |
| `runtime_surface` | CLI、Desktop、API等。hostが特定できなければ`unknown` |
| `identity_source.kind` | `codex_hook`、`api_response`、`operator_ui`等の取得方法 |
| `identity_source.field` | `model`、`response.model`等、値を読んだfield |
| `identity_source.ref` | hook event、response ID、durable evidence等へのnon-secret reference |
| `observed_at` | identity値をhost側で取得した時刻 |
| `trust_class` | その値がどの強さの証拠か |

`generated-at`は本文生成の完了時刻、`observed_at`はidentity metadataの取得時刻であり、同じ意味として扱わない。

### trust class

ADR-0002の`runtime-reported`は、model自身のruntime認識とhost metadataを混同できる曖昧な名前だったため、model identity
については次へ置き換える。

- `attested`: 検証可能なproviderまたはhost attestationへ結び付く。
- `host-reported`: Codex hookやAPI response等、model外部のhost fieldから取得した。署名済みattestationとは限らない。
- `operator-observed`: 人間がCLI statusやUI selectorで確認した。機械的なhost readbackではない。
- `self-reported`: model output内の申告だけ。identity verificationには使用しない。
- `unknown`: 許可された取得元から値を観測できない。

自由記述の`source`だけでtrust classを決めない。provenance builderは取得方法に応じてclassを割り当て、modelにclassを
選ばせない。

### artifact生成と付与の境界

provenance builderは次の責任を持つ。

- model outputからprovenance projectionを除いたcore bodyを受け取る。
- 同じ生成runについて、host fieldをmodel外部から取得する。
- model identity evidenceを構成し、core bodyのcontent hashと結び付ける。
- projectionをartifactへ付与した後、GitHub native artifactをread backする。
- local evidence、projection、GitHub上の本文が競合した場合はpublicationを完了扱いにせず、findingを残す。

modelに「自分のmodel名を書いて」と依頼し、その回答をprovenance builderへ渡す実装は禁止する。これはセンサーを外して、
メーターの針を運転手に手描きさせるのと同じだからだ。

### 取得失敗時

host側のidentity evidenceを取得できない場合は、policyに応じて次のどちらかにする。

- exact model identityがacceptance conditionなら、GitHub mutation前に停止する。
- identityが補助情報なら、`model_id: unknown`、`trust_class: unknown`として公開し、欠落した取得元と次のprobeを残す。

別のmodel名、commit author、GitHub actor、Machine Account名、request configurationからmodel identityを補完しない。

## PR #4の扱い

PR #4の`GPT-5 / runtime-reported`は、host evidenceへ結び付かないため無効なidentity claimとして扱う。PR本文、Issue #3、
ADR-0002をsilent editせず、このADRとIssue #5から誤りと補正規則へ辿れるようにする。

この会話でoperatorが確認した`GPT-5.6 Sol`は`operator-observed`の現在値である。PR #4生成時のCodex hook eventやAPI responseが
保存されていないため、これを過去の`host-reported` evidenceとしてbackdateしない。

## ADR-0002との関係

ADR-0002の次の判断は維持する。

- GitHub publication principalとgeneration model identityを分離する。
- task、candidate head、artifact revision、content hash、生成時刻、公開時刻を結び付ける。
- prompt、reasoning、session transcript、secretをpublic provenanceへ保存しない。
- model revisionを取得できなければ`unknown`にする。
- complete envelopeのcanonical serializationはGTP側で決める。

このADRは、ADR-0002のうちmodel identityの取得責任とtrust vocabularyをsupersedeする。特に、曖昧な
`runtime-reported`を`host-reported`と`operator-observed`へ分離し、provenance builderをmodel外部に置くことを必須にする。

## 今回変更しないもの

このADR fileはruntime wiringを変更しない。次は未実装である。

- Codex hook registration
- hook eventのdurable capture
- API responseからのprovenance builder
- GTP canonical evidence schema
- GitHub projection writerとreadback detector
- identity取得失敗時のpublication gate

これらは別のGTP taskで許可を得る。実装taskは開始時にcurrent Doctrineを取得し、実際のattachment point、real trigger、
observable oracleをcontractへ固定しなければならない。このADRは取得できなかったDoctrineへの準拠や、未発火のhook wiringを
完成扱いしない。

## Acceptance evidence for future implementation

runtime実装を完了と判断するには、少なくとも次の実証が必要である。

- 実Codex sessionのhook eventから`model` fieldを取得し、同じrunのartifactへ結び付けられる。
- Desktopを対象にする場合、Desktopでhookが実際に発火したnative evidenceがある。
- APIを対象にする場合、request valueとresponse `model` readbackを別fieldとして記録できる。
- model outputへ偽のmodel名を書いても、host-sourced evidenceが変化しないnegative testが通る。
- host fieldが欠落した場合、別の値を推測せず`unknown`またはstopになる。
- `model_id`だけ取得できる場合に`model_revision`が`unknown`のまま残る。
- projection、durable evidence、GitHub native artifactのcontent hashとcandidate headを照合できる。
- operatorが会話履歴なしで、値、取得元、取得時刻、trust class、未確認事項へ辿れる。

## Consequences

### Positive

- modelが自分の型番ラベルを貼り間違えても、host evidenceは独立して残る。
- model slugとimmutable revisionを混同しない。
- UI確認、hook metadata、API response、model自己申告の証拠強度を区別できる。
- evidenceがないとき、もっともらしいmodel名より`unknown`を選べる。
- 過去の誤記を消さず、どのdecisionが補正したか追跡できる。

### Negative and limits

- host側のwrapperまたはhookが必要になり、model単体ではcomplete provenanceを作れない。
- Desktop、CLI、APIで取得surfaceが異なるため、surfaceごとのcanaryが必要になる。
- `host-reported`でもprovider署名がなければbackend weightsの暗号学的証明にはならない。
- hook eventやresponse referenceを保存するとき、secretとlocal absolute pathを除くrecord gateが必要になる。

## Alternatives considered

### modelへ自己申告させる

modelはhost routingやimmutable revisionをauthorityとして観測できず、PR #4で実際に誤ったため却下した。

### requestで指定したmodel名だけを記録する

requested valueと生成結果のreadbackを混同するため却下した。requestは意図、responseまたはhost eventは観測として分ける。

### operatorのUI確認だけを正本にする

補助証拠としては使えるが、自動取得、同一run binding、再現可能なreadbackが弱いため第一候補にはしない。

### `runtime-reported`をそのまま使う

誰が報告したruntimeなのか曖昧で、model自己申告をhost metadataへ昇格できてしまうため却下した。

## Known unknowns

- Codex Desktopがこのrepositoryと設定でhookを実際に発火させるか。
- Codex hostが`gpt-5.6-sol`より細かいimmutable model revisionを提供するか。
- provider署名済みattestationをlocal CodexとResponses APIのどこから取得できるか。
- GTP canonical evidence schemaがidentity sourceとtrust classをどのfield名で表現するか。
- `agent-operated-bot`にprivate Doctrineのread権限を与えるか、別のread-only authority circuitを用意するか。

これらは推測で埋めず、future taskのdurable contractへ`unknown`とnext probeを残す。
