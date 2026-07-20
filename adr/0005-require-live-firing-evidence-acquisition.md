# ADR-0005: actual firingはtask-selected live acquisitionで証明する

- Status: Accepted
- Date: 2026-07-18
- Decision owner: operator
- Scope: `00-lab/agent-operated/`
- GTP task: [Issue #8](https://github.com/shinya0x00/00-lab/issues/8)
- Blocks: [Issue #7](https://github.com/shinya0x00/00-lab/issues/7)
- Doctrine ref:
  [`849a86f70ef315dbc9cbc5560579f39158b8f103`](https://github.com/shinya-reiji/doctrine/blob/849a86f70ef315dbc9cbc5560579f39158b8f103/DOCTRINE.md)

## Context

ADR-0001と`DESIGN.md`は、artifactの存在、runtimeへのattachment、actual firingを区別すると定めた。
しかし、genericな`verify-wiring-evidence`へcallerが`fired: true`またはnon-emptyなURLを渡すだけでは、
実際に何かが呼ばれたことを証明できない。Evidenceを検査するscript自身が、未検査の主張をEvidenceへ
昇格させる循環になる。

一方、正しいfiring mechanismはprojectごとに異なる。GitHub Actionsへ統一すれば、Codex hook、CLI、
Web service等のreal triggerを人工的なworkflowへ押し込むことになる。AOが一つのtransportを選ぶのではなく、
各taskがactual attachmentとobservable oracleを固定する必要がある。

## Decision

runtime wiringを変更または検証するtask contractは、各attachment pointについて少なくとも次を明記する。

| Field | Meaning |
| --- | --- |
| `attachment_point` | artifactが接続される実際のhost、entry point、registration point |
| `real_trigger` | runtimeがそのattachmentを呼ぶ具体的な条件または操作 |
| `acquisition` | triggerと結果をどのlive sourceから、どのcommandまたはAPIでread backするか |
| `oracle` | 何を観測すれば呼出しまたは期待結果を判定できるか |
| `candidate_head` | Evidenceを結び付けるfull 40-character commit SHA |

AOはacquisition mechanismを全projectへ一律指定しない。task contractが対象runtimeに合う実物を選ぶ。
contract作成時にcandidateがまだ存在しない場合は、`candidate_head`のcanonical ownerと解決時点を定め、
最初のcandidate-bound evidenceでfull SHAを固定する。空値、short SHA、branch名をcandidate bindingとして扱わない。

### Four-state model

状態を次の四つへ分離する。

| State | Required observation |
| --- | --- |
| `present` | candidate headに対象artifactが存在する |
| `attached` | artifactが宣言済みregistration pointとreal triggerへ接続されている |
| `fired` | live acquisitionが、candidate headに対するreal triggerの実呼出しを観測した |
| `validated` | firing後のoracleがtask contractの期待結果を満たした |

`fired`と`validated`を混同しない。失敗したActions run、nonzeroのCLI、gateがmutationを停止したnegative
caseでも、実際に呼ばれたなら`fired`であり得る。task contractのoracleまたは期待結果を満たすかは
`validated`で別に判定する。

### Evidence acquisition boundary

bare URL、caller-provided boolean、model-authored summary、存在するだけのlog fileは、単独で`fired`または
`validated`を証明しない。detectorはtask contractが指定したlive sourceを実際に取得し、少なくとも次を
照合する。

- acquisition targetが宣言済みattachment pointとtriggerに対応する。
- 観測されたheadがfull candidate SHAと一致する。
- oracleのraw status、exit、output、result、またはstate changeが取得できる。
- acquisition時刻またはnative object identityへ再到達できる。
- secret、credential location、private prompt、reasoning、session transcript、local absolute pathをdurable recordへ出さない。

scriptのinput/outputはAO-owned detector adapterであり、GTP canonical evidence schemaではない。GTP task referenceと
Evidence referenceはopaqueなdurable referenceとして受け渡し、AOがGTP lifecycleやserializationを推測しない。

### Acquisition examples

| Target | Live acquisition | Firing observation | Validation oracle |
| --- | --- | --- | --- |
| GitHub Actions | Actions run API | exact head、workflow、event、run start | conclusion、job/log result |
| Codex hook | host hook event | registered hookのevent | script exit/output、期待したgate behavior |
| CLI | 実commandのhost-side invocation | process startと対象command | exit code、artifact、state readback |
| Web service | request、log、trace | handlerまたはservice trace | response、state change、health check |

この表はprofile catalogではなく例である。具体的なfield、command、freshness、failure behaviorはtask contractが
選び、未対応sourceを既知のsourceへ見せかけない。

### Issue #7 skill walking skeleton

初期skill taskでは、次のlaneをreal triggerとして使用できる。

1. cleanなCodexがrepositoryのraw skill pathを読む。
2. GitHub mutation requestを受ける。
3. skill entryが`verify-actor.sh`を実行する。
4. wrong actor caseではmutationを停止する。
5. correct actor caseでは次の宣言済みgateへ進む。
6. hostが観測したcommand、exit、sanitized outputをcandidate headへ結び付ける。

SKILL.mdまたはscriptの存在だけ、事前に書いたexpected outputだけ、modelが後から要約した結果だけでは、この
laneの`fired`または`validated`にならない。

## Relationship to ADR-0001 and ADR-0003

このADRはADR-0001のpresence-versus-firing boundaryを四状態へ拡張する。ADR-0003と同じく、観測対象を
model自身の文章へ置き換えない。model identityはhost-sourced evidence、runtime firingはtask-selected live
acquisitionが所有し、どちらもmodel self-reportから昇格させない。

## Consequences

### Positive

- URLやbooleanだけでoperational wiringを完成扱いにできない。
- projectはruntimeに合うnative acquisitionを選べる。
- 「呼ばれた」と「正しく動いた」を別のfailure surfaceとして診断できる。
- generic AO scriptがGTP schemaまたはproject-specific runtimeをforkせずに済む。
- negative caseのactual firingを、validation failureと混同せずEvidenceにできる。

### Negative and limits

- taskごとにacquisition commandとoracleを具体化する必要がある。
- source-specific adapterがないruntimeでは`fired`または`validated`をClaimできない。
- live readbackがthird-party retentionやpermissionへ依存する場合、freshnessとdurabilityを別途設計する必要がある。
- command outputはhost-side captureが必要で、modelの再記述だけでは代替できない。

## Alternatives considered

### GitHub Actionsを全taskへ必須にする

Actions以外のhost、hook、CLI、serviceを正しく表現できず、AOがproject architectureを不必要に所有するため
採用しない。

### Non-empty evidence referenceをfiringとみなす

参照先の取得、candidate binding、oracleを検証せず、presenceをfiringへ昇格できるため却下する。

### Callerの`fired: true`を信頼する

detectorが検査対象のClaimをそのまま受理する循環になるため却下する。

### `fired`と`validated`を一つにする

「呼ばれたが失敗した」と「一度も呼ばれていない」を区別できず、repair orderを誤るため却下する。

## Acceptance evidence for implementation

- task contractに五つのrequired fieldがない場合、dependent `wired / proven` claimを停止する。
- bare URL、boolean、model summaryだけのfixtureを`fired`として拒否する。
- declared acquisitionを実行し、candidate headと実測headの完全一致を確認する。
- wrong-actor negative caseでskill entryからcheckerが実発火し、mutation停止をvalidatedとして観測する。
- correct-actor caseで次のgateへ進むことを別に観測する。
- fired-but-failedとfired-and-validatedを別のresultとして返す。
- unsupported acquisitionは推測せず`unknown`とし、そのclaimに依存するtransitionだけを止める。

## Known unknowns

- mergeしないHuman Account decision用GTP recordと同様、source-specific acquisitionのcanonical evidence field名はGTP側で未確定である。
- Machine Account merge laneが採用するcheck、dependency、promotion oracleは、将来のtaskとADRで決める。

これらはgeneric AO detectorのbooleanまたは互換schemaで埋めない。
