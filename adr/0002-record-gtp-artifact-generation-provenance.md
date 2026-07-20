# ADR-0002: GTP artifact generation provenanceを記録する

- Status: Accepted
- Date: 2026-07-18
- Decision owner: operator
- Scope: `00-lab/agent-operated/`
- Doctrine ref:
  [`849a86f70ef315dbc9cbc5560579f39158b8f103`](https://github.com/shinya-reiji/doctrine/blob/849a86f70ef315dbc9cbc5560579f39158b8f103/DOCTRINE.md)

## Context

ADR-0001は、共有Machine Accountが証明するのはGitHubが観測したprincipalであり、どのmodel、
runtime、process、sessionが操作したかは証明しないと定めた。この境界は維持する。

一方、operatorがPR本文、Issue本文、task-significant comment、review response、handoff、closeout等を
後から確認するとき、GitHub actorだけでは次を判断できない。

- どのGTP taskとgenerationに基づくartifactか
- 生成時点のGTP stateまたはtransitionは何か
- どのcandidate headを対象にしたか
- どのmodel metadataがruntimeから観測されたか
- いつ生成され、いつGitHubへ公開されたか
- 確認している本文が生成時の本文と同じrevisionか

会話履歴やmodel自身の申告だけに依存すると、再開可能な証拠にならない。反対に、prompt、reasoning、
session transcriptをGitHubへ保存すると、private情報の露出と不安定なruntime identifierへの依存を
招く。

## Decision

GitHub principal attributionとは別に、GTP taskへ結び付く`artifact generation provenance`を導入する。
これはactor attributionを置き換えず、別の主張として検証する。

### Canonical ownership

同じ事実をAO内へ複製せず、正本を次のように分ける。

| Fact | Canonical owner |
| --- | --- |
| task reference、generation、state、transition、evidence lifecycle | GTP |
| model identifier、model revision、生成時刻等の生成観測 | 実行runtimeが提供するmetadataまたはattestation |
| publication actor、artifact URL、GitHub上の公開時刻 | GitHub native record |
| 上記事実のbinding、record gate、handoff時の照合 | AO |

完全なprovenance envelopeは、GTPが許可するdurable evidence recordまたはそこから直接解決できる
artifactへ保存する。AOは独自のtask ledgerやGTP state machineを作らない。GitHub本文にはoperatorが
確認できる短いprojectionと、完全なenvelopeへのdurable referenceだけを置く。

GTP側のcanonical evidence schemaが未確定の場合、AOは互換schemaを推測して正本化しない。
必要fieldと不足しているauthorityを示し、該当provenance claimを`unknown`として扱う。

### Provenance envelope

envelopeは少なくとも次の意味を表現できなければならない。具体的なfield名とserializationはGTP側の
canonical evidence schemaで決める。

| Group | Required meaning |
| --- | --- |
| Envelope | schema/profile version、provenance record ID |
| Task | authoritative task reference、generation、生成時のGTP state、対象transition |
| Candidate | repository、candidate head SHA |
| Artifact | kind、GitHub artifact reference、revision、content SHA-256 |
| Generation | generated-at、model provider、model ID、model revision、identity source、trust class、runtime surface |
| Publication | published-at、GitHub actor login、numeric actor ID、artifact URL |

`model revision`、`runtime surface`等をruntimeが提供しない場合は、値を捏造せず`unknown`または
`not_observed`とする。optionalな観測値の欠如だけでtask全体を停止せず、その値に依存する帰属主張だけを
弱める。

### Evidence and trust classes

model identityはmodelの文章中の自己申告から確定しない。少なくとも次を区別する。

- `attested`: 検証可能なruntime attestationまたは同等の署名済み証拠に結び付く。
- `runtime-reported`: runtimeが提供したmetadataとして観測したが、独立した署名検証はない。
- `self-reported`: model出力内の申告だけであり、identityの検証証拠として使わない。
- `unknown`: authoritativeな観測値を取得できない。

provenance recordには値だけでなく`identity source`と`trust class`を保存する。将来より強いattestationを
追加できるが、Machine Account名やcommit authorからmodel identityを推論してはならない。

### Time and revision semantics

`generated-at`と`published-at`を別々に記録する。前者は本文revisionの生成が完了した時刻、後者は
GitHub native artifactとして公開された時刻である。予約投稿、review待ち、再試行があっても同じ時刻と
みなさない。

content hashはUTF-8、LF改行へ正規化した表示本文からprovenance projection自体を除いて計算する。
これによりhashの自己参照を避ける。GitHubで本文が編集された場合はsilent overwriteせず、新しい
revisionとして次を記録する。

- prior revisionとprior content hash
- new content hash
- revision reason
- editorまたはpublishing actor
- human editの有無

人間がmodel生成文を修正した最終本文は、純粋なmodel出力として表示しない。生成revisionと公開revisionの
関係を残し、誰が最終化したかを区別する。

### GitHub projection

GitHub artifactの末尾には、本文の可読性を壊さない短いprovenance projectionを置く。projectionは
少なくとも次をoperatorへ示す。

- task referenceとgeneration
- 生成時のGTP stateまたはtransition
- candidate headの短縮表示
- model IDとtrust class。未観測なら`unknown`
- generated-at
- provenance record reference

projectionは便利な表示であって正本ではない。projectionと完全なenvelopeまたはGitHub native recordが
競合した場合は、canonical ownerのrecordを採用し、競合をfindingとして残す。

### Public record boundary

provenance envelopeとGitHub projectionへ、次を保存しない。

- secret、token、credential location
- private prompt、reasoning、session transcript
- ローカル絶対path
- 再解決できない一時的なprocess IDまたはsession ID
- model identityの証明にならない自由記述の自己申告

必要なprivate evidenceがある場合は、durable recordへ値そのものではなく、許可された保管先の
non-secret referenceと検証結果を残す。

## Prior art boundary

このdecisionは[W3C PROV-DM](https://www.w3.org/TR/prov-dm/)のEntity、Activity、Agent、Generation、
Attributionという分離を概念上の先行例とする。

- GitHub本文revisionはprovenance対象のEntityに相当する。
- 本文の生成はActivityに相当する。
- runtime/modelの生成側identityとGitHub publication principalは、異なる責任を持つAgentとして
  区別する。
- content revisionは前revisionから派生した別Entityとして扱える。

ただし、現段階でPROV-O、RDF、PROV-XML等の完全なserializationを要件にしない。AOに必要なのは
GTP task、candidate head、生成観測、GitHub native evidenceを小さく結ぶprofileであり、標準全体の
導入は実装とreview負荷が目的を上回る。将来GTP側が標準serializationを採用できるよう、概念の対応は
壊さない。

## Relationship to ADR-0001

このADRはADR-0001をsupersedeせず、そのAttribution limitを拡張する。

- Machine Accountは引き続きGitHub principalだけを証明する。
- artifact generation provenanceは、別の観測とbindingによってmodel/runtime/GTP contextを示す。
- provenanceが欠けてもMachine Accountのactor evidenceは無効にならない。
- actor evidenceが欠けてもprovenanceだけでGitHub publication principalを主張しない。

初回bootstrap PRは空repositoryへdesign baselineを導入した例外であり、このADRのprovenance envelopeを
遡及して必須にしない。次のmaterialなGTP taskを最初のwalking skeletonとする。

## Consequences

### Positive

- operatorはGitHub画面から、artifactのtask、generation、GTP段階、model観測、生成時刻へ辿れる。
- actor attributionとgeneration attributionの主張が混線しない。
- candidate headとcontent hashに結び付けるため、古い本文や編集後の本文を見分けられる。
- runtime metadataが取れない場合も、虚偽のmodel名ではなく`unknown`をdurableに残せる。
- promptやtranscriptを保存せず、reviewに必要なprovenanceだけを残せる。

### Negative and limits

- GTP側のevidence schemaとruntime metadata取得方法を別taskで確定する必要がある。
- GitHub本文の編集ごとにrevision管理とreadbackが必要になる。
- `runtime-reported`は署名済みattestationではなく、model binaryやprovider内部revisionの完全な証明ではない。
- projectionとcanonical recordの整合を検査するdetectorが必要になる。
- providerやCodex surfaceがimmutableなmodel revisionを公開しない場合、その粒度は`unknown`のまま残る。

## Alternatives considered

### Machine Account名だけをmodel帰属として使う

GitHub principalと生成modelは別のidentityであり、同じaccountを複数runtimeが共有できるため却下した。

### GitHub本文へmodel名と時刻だけを書く

task、candidate head、content revision、identity sourceへ結び付かず、自由記述を検証できないため
却下した。

### Prompt、reasoning、session transcriptを保存する

必要以上のprivate情報をdurable recordへ持ち込み、runtime依存の不安定な監査になるため却下した。

### AO独自のGTP provenance schemaを正本にする

GTPのevidence lifecycleと二重のauthorityを作るため却下した。AOは必要な意味と検証境界を定め、
canonical serializationはGTP側で解決する。

### W3C PROV一式を必須にする

概念上の対応は有用だが、現在の小さなwalking skeletonにRDF等を必須化する根拠がないため却下した。

## Future implementation order

このADR自体はruntime wiringを変更しない。実装は別のGTP task contractで許可を得て、exact Doctrineを
再取得したうえで次のwalking skeletonから始める。

1. GTP側のcanonical evidence schemaとdurable provenance record referenceを解決する。
2. runtime metadataを観測し、取得不能なfieldを`unknown`で返す最小adapterを作る。
3. 一種類のGitHub artifactで、task、candidate head、本文hash、生成観測をenvelopeへ記録する。
4. artifactをMachine Accountで公開し、GitHub native actor、published-at、公開本文をread backする。
5. envelope、projection、GitHub native recordを照合するdetectorを同じwalking skeletonで実発火させる。
6. revisionとhuman editを検証した後、対象artifact kindを段階的に広げる。

schemaだけ、footerだけ、detectorだけを先に完成扱いしない。最初のartifactで端から端まで観測できた後に
抽象化する。

## Acceptance evidence

このdecisionの実装完了には、少なくとも次が必要である。

- GTPのauthoritative task referenceからcanonical provenance recordへ到達できる。
- 一つの実GitHub artifactで、task generation、GTP stateまたはtransition、candidate head、content hashを
  照合できる。
- model identityの値とsourceとtrust classを区別し、未観測値を`unknown`として残せる。
- `generated-at`とGitHub native `published-at`を別々に確認できる。
- publication actorのloginとnumeric IDをGitHub native evidenceで確認できる。
- 本文編集が新revisionとして記録され、human editをmodel生成文と誤表示しない。
- record gateが禁止情報を含むenvelopeとprojectionを拒否する。
- operatorが会話履歴なしでGitHub artifactから上記evidenceへ辿れる。

このADR fileの存在だけでは、GTP schema、runtime metadata acquisition、GitHub projection、detectorの
operational wiringが完成したことを意味しない。

## Known unknowns

- Codexの各surfaceが、外部から検証可能なimmutable model revisionまたは署名済みattestationを提供するか。
- GTPのcanonical evidence schemaで、provenance envelopeとartifact revisionをどのfield名で表現するか。
- GitHub artifact kindごとのnative revision historyを、どのevidence acquisitionで安定してread backできるか。

これらは推測で埋めず、実装taskのdurable recordへ`unknown`または`evidence_request`として残す。
