# #42：PCD・個別ZKP・Besu比較 / ADR

状態: IN_PROGRESS（個別proof・再帰分岐・ローカルQBFTを実測）。採用判断: **保留**。未実装・未測定を失敗としない。

| 観点 | A: 個別Groth16＋共同署名 | B: 秘密保護型再帰/PCD | C: Besu個別Groth16 | D: PCD＋Besu |
|---|---|---|---|---|
| 原Witness非共有 | 個別proofのZK仮定に依存 | 継続用転送物の評価が必要 | 個別proofのZK仮定に依存 | Bに依存 |
| 最終proofサイズ | proof+public 1,392 bytes＋署名192 bytes | C proof+public 496 bytes（固定3段） | ZKP提出は未実測 | EVM圧縮実装存在時のみ測定 |
| 独立検証 | 各proofと共同署名 | 前段と最終proof | コントラクト検証 | 最終verifier |
| 提出集合の完全性 | 受付証拠/共同署名の設計に依存 | proofだけでは未提出の観測を証明しない | 未受付/未包含txの存在まで合意から自動証明しない | Cと同様 |
| 順序・重複・確定履歴 | 署名ログの競合解決に依存 | statementと外部状態に依存 | レジストリとvalidator合意 | 同左 |
| RF/観測の真実性 | 保証しない | 保証しない | 保証しない | 保証しない |
| prove/verify/setup/RAM/bytes | singleton 20回測定、後節 | 再帰は単回・追加2分岐、後節 | QBFT基盤のみ測定、ZKP未測定 | 未実装/未測定 |
| 合意遅延/Gas | 署名共同確定時間は未測定 | proof単体に合意なし | 自己転送のreceipt遅延のみ測定。ZKP Gas未測定 | 未測定 |

## 比較条件

同一ホスト、同一7入力の合成観測、3参加者、同一session/policy/member条件を使う。
回路関係やセキュリティ条件が異なる測定は別表に記載し、速度比を計算しない。
各構成は固定依存、warmup 1回、測定20回を原則とし、p50/p95・peak RAM・transfer bytes・
setup/prove/verify/受付/確定を分離する。1回しか実行できない段階では単回測定と表示する。
局所速報（受信→暫定通知）は暗号学的検証・BC確定の外で別計測する。

## ソース上の注意（測定ではない）

`contracts/besu-qbft/README.md` は構成テンプレート。今回の起動/測定は別の `week23/poc/besu-local/` に記録する。
同READMEの「正直quorumがあれば提出Txは必ず入る」「検閲不可」は、この比較の確認済み保証に採用しない。
合意安全性と、受付・包含・運営主体の独立性は別々に検証する必要がある。
1PCの4validatorを起動できてもBFT機能PoCとして記載する。

## 判断条件

Bが秘密非共有・否定テスト・端末予算を満たし、共通確定履歴が不要ならPCD単体候補。
Aが要件を満たすなら署名ログを候補に残す。
複数運営主体間の共通順序/資格/確定履歴が必要でCの追加コストが許容されればBC採用候補。
Dは最終圧縮proofの生成とEVM検証の実行証拠が揃った場合だけ実装済みとして評価する。
ライブラリ/APIでBが未達でも、Nova全般の不可能性やBC必須の証明にはならない。

## 現時点の実行証拠

比較対象Aの小規模baselineを同じ相対許容帯関係・同じ合成観測で実装し、
3個別Groth16と同一提出集合への3共同署名をローカルで検証した。
これはIssue #26全体の実機実証ではなく、Week23専用の合成baseline。
[共同検証ログ](logs/baseline-joint.log): proof+public合計1,392 bytes、Ed25519署名合計192 bytes。
全proof/署名は検証成功。提出集合digestの改竄は署名検証で拒否。
署名鍵はtest-onlyでメモリ内に生成し、ログやGitには保存しない。

Nova生状態転送の8,441,240 bytesは元Witnessを含むため、秘密非共有PCDの性能列へ流用しない。
一般再帰B/Cも単回生成・検証まで成立した。p50/p95が揃っていないので速度の優劣はまだ出さない。
固定session・member順のfinite recursionと、独立proofの集合は保証が異なる。

初回のBesu環境確認ではDocker CLIは存在するがdaemon socketへ接続できず、PATHにBesu CLIも見つからなかった。
[環境ログ](logs/besu-environment.log)。これはローカル環境の未準備であり、Besu構成が実装不可能という意味ではない。
既存コントラクトテスト48件は成功したが、Besu/QBFTの合意・確定時間の計測としては扱わない。
既存Python 61件とGoパッケージテストも成功。ログは `logs/*-tests.log`。

QBFTの4validator最小構成・合意の即時finality・稼働数条件は
[Besu公式仕様](https://docs.besu-eth.org/private-networks/concepts/poa) を参照する。
この仕様から、未受付の観測や未包含のtxがすべて履歴へ入るとは推論しない。

採用判断は引き続き保留。未計測のp50/p95、RAM比較、Gas、独立運営・受付拒否の評価を埋めてから更新する。

## 個別proofの繰り返し測定

warmup 1回＋測定20回、GOMAXPROCS=2。分位点はsorted samplesの線形補間。
共有ホスト上で一般再帰setupが同時に動作する条件を明示し、専有端末性能と扱わない。

| singleton | prove p50 / p95 (ms) | peak RSS (bytes) |
|---|---|---|
| A | 45.201 / 53.092 | 26,918,912 |
| B | 41.829 / 44.304 | 27,131,904 |
| C | 42.036 / 45.920 | 27,328,512 |

正本は [percentiles summary](logs/baseline-percentiles-summary.json) と `baseline-*-percentiles.log`。
旧 `baseline-*-benchmark.log` は初回の分位点定義によるログとして保存し、表には使用しない。
このRSSはkeyを読み込んでprove/verifyするbenchmark processの値であり、setup込みのピークではない。
再帰Bのsetup込みpeak RSSと同一列で速度・メモリの倍率を計算しない。

## ローカルPoCについての暫定ADR

事実: BCを使わない有限3段Groth16一般再帰で元assignment非共有とCの最終検証に成功した。
測定: Bはprove約16.05秒、Cは約19.79秒（いずれも単回、setupは別）。最終proof+publicは496 bytes。
解釈: この固定3人の計算連鎖にBCは必須ではない。署名付き転送の補助テストもローカルで成立した。
判断: **このローカル計算PoCにはBCを追加しない。一般再帰を秘密継続の成立例、個別proof＋共同署名を比較基準として保持する。**

全体構成のBC採否は保留。外部の共通受付・資格・競合解決・確定履歴が必要という要件が得られ、
Besuの同等条件実測で追加コストが予算内なら判断を更新する。
即時警告の遅延予算も未確定であり、約16〜20秒の逐次proveを即時警告経路に採用したとは主張しない。
未測定の同等回路Besu ZKP性能や実機性能を推定で埋めず、Issue #42全体をDONEとしない。


## ローカル競合制御と共通履歴の差：実験による追加根拠

#41では同じBから別観測のC proofを2本生成し、両方が正しくverifyされた。
単一SQLite DBでは同時提出の1件だけをtransactionで受理できたが、独立DBでは異なる分岐を各々受理できた。
[実行結果](logs/private-pcd-persistent-gate.json)。
したがってproof連鎖の正しさと、複数受信者が共通の1履歴へ合意する機能は区別できる。
署名ログでも署名者集合の交差・二重署名拒否/証拠・競合処理を設計すれば共通確定を検討できるので、
この結果だけでBCが唯一の解決策だとは言えない。有限順序ではBが提出しないとCは進まないことも確認した。
任意参加者の動的再編と独立運営者の評価は残る。

## Besu実測の範囲と鍵の制約

Besu 26.9.0の公式binary/checksumを取得し、既存OpenJDK 26.0.2でnative起動した。
[固定版/hash](manifests/besu.json)、[再現手順](poc/besu-local/README.md)。Docker daemonを必要としない。
[公式Java要件](https://docs.besu-eth.org/private-networks/get-started/install/binary-distribution) はJava 25+。
4個のvalidator/RPC/P2Pを同一Macのloopbackに限定し、genesisとvalidator/転送鍵はignored owner-only領域へ生成する。

リポジトリの指示「Disposable single-contributor Groth16 setup outputs are test fixtures, never release keys.
Never publish/deploy their ... VK, or proofs.」に従い、今回の使い捨てZKP VK/proofをBesuへデプロイしない。
今回のworkloadはEOA自己転送であり、Cの個別Groth16検証・資格registry・同条件の3観測比較は未実測。
21000 Gasは自己転送の値であり、ZKP検証Gasとして使わない。
これは暗号学的・ローカル実装上の不可能性ではなく、現在の鍵の使用制約と比較対象の未整備を区別した記録である。


## ローカルQBFT実測結果

[正本の測定データ](logs/besu-qbft-local.json)、[実行ログ](logs/besu-qbft-local-run.log)。
1 warmup＋20 sequential自己転送、2秒block period、receipt poll 50ms、loopback、4 native JVM。
RPC提出開始→receipt取得のp50 **1.985秒**、p95 **2.058秒**。
20件すべて成功、4ノードのreceipt blockHash一致。各転送Gasは21000、gasPriceは0の合成設定。
各validatorのpollで観測したpeak RSSは約404.7–410.6 MiB（JVM heap上限384 MiB）。
1台停止後height 23→26、3block進行。
2台停止後height 26→26、12秒の観測窓で停止。
初回は1blockだけの進行確認だったため、停止前に決定済みblockの影響を減らすよう3block進行に強めて再実行した。
[初回ログ](logs/besu-qbft-local-first.json)も保存し、正本の表へ混ぜない。
全validatorは実験終了時に停止。鍵・チェーンDB・raw tx・ノード詳細ログはignored owner-onlyで保存。

測定から確認したのはQBFT機能・ローカルreceipt遅延・停止台数に応じた進行差であり、
独立運営者・悪意ノード・観測受付の完全性・検閲不可・ZKP Gasの実証ではない。
一般再帰約20秒と自己転送約2秒はworkloadが違うため、BC/PCDの速度比を計算しない。
既存の暫定ADRを維持し、固定3段の秘密非共有計算はBCなし、共通履歴の要件と同等回路の評価が揃えば採否を再検討する。
#42は同等条件のオンチェーンZKP検証、独立運営者、実機、速報経路の計測が残るためIN_PROGRESS。
