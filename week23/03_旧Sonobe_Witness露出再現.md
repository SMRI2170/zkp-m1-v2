# #40：旧SonobeのWitness露出・状態改竄再現

状態: LOCAL_COMPLETE_WITH_FINDINGS（固定旧APIでのIssue記載実験完了、検証漏れあり）。実験コード: [poc/witness-transfer](poc/witness-transfer)。
ビルドログ: [witness-build.log](logs/witness-build.log)。

当時の非固定依存を復元できたとは主張しない。公開旧APIcommitを固定し、arkworks 0.6.0移植パッチを保存した。
旧 `nova_poc/uav_chain_step.rs` の関係をコピーし、合成の識別可能な7入力を与える。
受信BはCanonicalDeserializeで復元し、各canaryの `w_i.W` / `W_i.W` 出現indexと配列長を記録する。
数値はすべて架空であり、現実のGPS/RSSIの回復実験ではない。range入力を生RSSIと呼ばない。

H=false/trueともPedersen/Pedersenで比較する。元PoCのKZG/Pedersenとはcommitment構成が異なる。
Hの差の比較を優先し、元構成と同じ測定値だとは扱わない。

各改竄（count、RID、bucket、incoming witness、commitment）について、受信verify、
verifyを意図的に迂回したfrom_ivc_proof、prove_step、最終verifyを別々に記録する。
迂回実験は挙動観測のみ。採用する受信経路ではverify成功前に継続しない。
単一foldの逆算と直接可視性を区別する。追加の逆算実験は後節に記録。

setup/stateは `.cache/week23/` のowner-onlyディレクトリに保存し、ログには値・秘密assignmentを出さない。

## 2026-10-11の実行結果

A/Bは異なるPIDで実行。H=false/trueとも7つの元canaryが **incoming `w_i.W[12..18]` に直接存在**した。
`W_i.W` の直接一致は0件。これだけからrunning witnessの復元不可能性は言えない。
配列長はincoming/running各63,662、CycleFold 1,347。転送stateは8,441,240 bytes。
H=trueはcommitmentの乱数を付けても、生witness配列を隠さないことを実行で確認した。

| 改竄 | 受信verify | raw restore | 次step | 最終verify |
|---|---|---|---|---|
| なし | 成功 | 成功 | 成功 | 成功 |
| count | 拒否 | 成功 | 成功 | 拒否 |
| RID | 拒否 | 成功 | 成功 | 拒否 |
| timeBucket | 拒否 | 成功 | 成功 | 拒否 |
| incoming witness[0] | 拒否 | 成功 | 成功 | 拒否 |
| incoming `u_i.cmW += generator` | **成功（拒否期待に反する）** | 成功 | 成功 | **成功** |

両Hで同じ傾向。改竄proofのrestore/prove_step成功は最終proofの有効性を意味しない。
ただしcmWケースは最終verifyも通った。旧版verifyはR1CS関係を確認するが、
この経路でincoming commitmentとincoming witnessを再計算照合する処理が見当たらない。
この観測を最新mainの脆弱性や任意statement偽造の証明に拡大しない。
拒否assertは非ゼロ終了し、未達として残す。検証を省くよう変更していない。

公開ログ: [H=false](logs/witness-h-false.jsonl)、[H=true](logs/witness-h-true.jsonl)。
単回測定（Mac arm64、2 Rayon threads）: setup約3.12/3.23秒、A prove約132/129ms、
B verify約70/70ms。原PoCの速度と比較しない。

残件（初回記録時）: running foldのrを再現した逆算、KZG/Pedersen元構成での同じ再現、
複数step後のcanary回復範囲、最新mainに対する同等の改竄検証。


## 追加実験：検証漏れの原因と受信ゲート

固定旧版 `nova/mod.rs` line 943のverifyは、state hash、incoming形式、3組のR1CS関係を確認する。
しかし `arith/mod.rs` のArithRelationの説明はcommitmentを確認しないことを明示し、
`nova/traits.rs` line 44の評価は `[u, x, W]` のR1CS残差とEだけを照合する。
この呼び出し経路に `cmW = Commit(W,rW)` のチェックがないことが、今回のincoming cmW実験の結果と一致する。
任意の公開statementを偽造した証拠ではない。

**新mainには同じ結論を当てはめない。** 固定main `7f042351` の
`crates/fs/src/nova/keys/mod.rs` line 46/64ではrunning/incomingの `CM::open` を呼ぶ。
CycleFold IVCのverifyはこれを `decide_running/decide_incoming` 経由で使用する。
これはソースで確認した相違であり、mainで同等改竄テストを実行したという主張ではない。

旧版を変更せず、研究用CLIに `guard false|true PRIVATE_DIRECTORY` を追加した。
元verify成功 **かつ** primary running/incoming・CycleFoldのcmW/cmE再計算一致を受信条件にする。
比較するのはcommitmentフィールドであり、relaxed instanceのuを通常instanceのu=1で上書きしない。
生Witness転送が必要なので、秘密非共有方式への修正ではない。

両Hでvalidを受理し、6種のcommitment改竄・count改竄・witness改竄の全8種を拒否（各9case、計18case）。
[H=false](logs/witness-guard-false.jsonl)、[H=true](logs/witness-guard-true.jsonl)。受信拒否時にはrestore/次stepを呼ばない。
ゲートの実験は受信判定までで、valid受理後の次stepは従来のvalidケースで確認済み。
元の `b` の拒否assertとその失敗ログは保存しており、ライブラリverifyが修正済みとは扱わない。


## 単一foldの逆算：追加実行済み

`inverse false|true PRIVATE_DIRECTORY` は、既存Aの正常stateをverify後、NIFS単体を実行する。
公開instance `U_i/u_i`、cross-term commitment `cmT`、固定Poseidon設定/pp_hashから
NIFS verifierでchallenge rを再生成し、proverが使ったrとの一致をassertする。
`W_next = W_prev + r * w_incoming` に対し `(W_next - W_prev) / r` を計算した。
両Hでrは非ゼロ、元incomingの**全Witness配列が一致**、7canaryはindex 12–18で回復した。
今回は `W_prev` が全ゼロであることも確認した。
[H=false](logs/witness-inverse-false.jsonl)、[H=true](logs/witness-inverse-true.jsonl)。

受信者がfold後の**生Witness**を取得し、前running Witnessを知る（今回ゼロ）という条件付きの実験である。
任意の複数step、前runningが不明な状況、RandomizedIVCProof/CompressedSNARKからの復元とは異なる。
識別用canary自体の値やrをログに出さず、一致・index・必要条件だけを保存した。


## 元構成KZG/Pedersen：追加実行済み

同じ固定旧API+移植patchに、元PoCの `KZG<BN254>` / `Pedersen<Grumpkin>`、H=falseを適用した。
A/B独立processで生成/受信/正常継続の最終verifyに成功。incomingの7canary直接一致、
count/RID/bucket/witness改竄の受信拒否、incoming cmW改竄の受信・最終verify受理も再現した。
Bは元の拒否assertを維持して終了101。
[生成](logs/witness-kzg-A.jsonl)、[受信](logs/witness-kzg-B.jsonl)、[リソース/失敗](logs/witness-kzg-B-resource.log)。
setup約1.61秒、A prove約309ms、B verify約45ms（共有Mac、単回、同時にArecibo評価中）。
本項で元commitment構成の残件を埋めたが、当時の非固定Sonobe依存commitを復元したという意味ではない。

#40のIssueに列挙されたローカル再現実験は完了し、**commitment検証漏れを発見した結果**として記録する。
任意の複数stepからの回復範囲や新mainでの実行比較は追加研究であり、未実施のまま区別する。
GitHubのチェックボックス/状態はこのローカル記録では変更しない。
