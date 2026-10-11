# #42：PCD・個別ZKP・Besu比較 / ADR

状態: IN_PROGRESS（比較条件固定と合成baseline実行）。採用判断: **保留**。未実装・未測定を失敗としない。

| 観点 | A: 個別Groth16＋共同署名 | B: 秘密保護型再帰/PCD | C: Besu個別Groth16 | D: PCD＋Besu |
|---|---|---|---|---|
| 原Witness非共有 | 個別proofのZK仮定に依存 | 継続用転送物の評価が必要 | 個別proofのZK仮定に依存 | Bに依存 |
| 最終proofサイズ | 3proof＋署名/statement | 実装選定後に測定 | 3tx/proof | EVM圧縮実装存在時のみ測定 |
| 独立検証 | 各proofと共同署名 | 前段と最終proof | コントラクト検証 | 最終verifier |
| 提出集合の完全性 | 受付証拠/共同署名の設計に依存 | proofだけでは未提出の観測を証明しない | 未受付/未包含txの存在まで合意から自動証明しない | Cと同様 |
| 順序・重複・確定履歴 | 署名ログの競合解決に依存 | statementと外部状態に依存 | レジストリとvalidator合意 | 同左 |
| RF/観測の真実性 | 保証しない | 保証しない | 保証しない | 保証しない |
| prove/verify/setup/RAM/bytes | 未測定 | 未測定 | 未測定 | 未実装/未測定 |
| 合意遅延/Gas | 対象外（署名確定時間は別計測） | 対象外 | 未測定 | 未測定 |

## 比較条件

同一ホスト、同一7入力の合成観測、3参加者、同一session/policy/member条件を使う。
回路関係やセキュリティ条件が異なる測定は別表に記載し、速度比を計算しない。
各構成は固定依存、warmup 1回、測定20回を原則とし、p50/p95・peak RAM・transfer bytes・
setup/prove/verify/受付/確定を分離する。1回しか実行できない段階では単回測定と表示する。
局所速報（受信→暫定通知）は暗号学的検証・BC確定の外で別計測する。

## ソース上の注意（測定ではない）

`contracts/besu-qbft/README.md` は構成テンプレートであり、この環境で4validatorの起動証拠はない。
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

Besu環境確認ではDocker CLIは存在するがdaemon socketへ接続できず、Besu CLIも見つからなかった。
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
未計測のBesu性能や実機性能を埋めず、Issue #42全体をDONEとしない。
