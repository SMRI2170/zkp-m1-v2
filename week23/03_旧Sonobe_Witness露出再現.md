# #40：旧SonobeのWitness露出・状態改竄再現

状態: IN_PROGRESS。実験コード: [poc/witness-transfer](poc/witness-transfer)。
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
単一foldの逆算と直接可視性を区別し、W_1/r_1による復元は未実施。

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

未完了: running foldのrを再現した逆算、KZG/Pedersen元構成での同じ再現、
複数step後のcanary回復範囲、最新mainに対する同等の改竄検証。
