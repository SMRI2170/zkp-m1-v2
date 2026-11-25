# 整数参照実装と、proof公開入力からの受付検証

2026-11-25。[前回の評価](EVALUATION.md)を受け、臨時ディレクトリ内で実装・テストした。実測の単局logモデルを採用する判断、位置偽装検知の実証、実端末への導入は行っていない。

## 今回できたこと

1. **同じ整数仕様で、回路外と回路内の判定を比較できるようにした。**
2. **受付情報をproofの公開入力から取り出し、その同じ入力でproofを検証する入口を作った。**
3. **現在より未来のclaim時刻を、既定では拒否するようにした。**

## 1. 整数モデルを共有

[`profiles/synthetic-four-band-v1.json`](profiles/synthetic-four-band-v1.json)を合成profileの共通入力にした。回路テストのfixtureもこのprofileを読む。距離二乗cm²、shifted centi-dBm、ミリ秒、cm/sの仕様は従来回路と同じ。

[`integer_model.go`](integer_model.go)に追加した関数：

| 関数/型 | 役割 |
|---|---|
| IntegerPolicy / IntegerObservation | 整数単位と範囲を持つ判定入力 |
| EvaluateInteger | 時間・位置誤差から距離範囲を作り、整合/警報/保留を算出 |
| IntegerPolicy.Digest | 回路と同じ順序・domainで承認候補policyのdigestを計算 |
| BuildUncertaintyAssignment | 参照実装の結果、policy、contextから回路割当を構成 |

時刻差×速度はuint64を超え得るため、big.Intで切上げ除算してから回路の20bit移動半径へ制限する。距離二乗は検査済み入力の範囲でuint64に収まる。欠損を推定値で埋める機能ではなく、入力の単位・既知フラグ・epochの妥当性は上流の責任として残す。

### 比較結果

固定seedの合成96条件で、参照実装が算出した割当をR1CS solverへ入力し、**96/96一致**を確認した。整合42、警報29、保留25。2D/3D、誤差半径、RSSI境界付近、時間半径、未知フラグ、最大入力を含む。

追加で座標/誤差/時刻/時計/RSSIの範囲外、空の距離帯、大きい時刻差×速度、切上げ境界を検査した。これは実装間の一致であり、検出精度の統計評価や回路の形式証明ではない。

**実測のlogモデルとの不一致は解消していない。** 今回共有したのは合成4距離帯モデル。実測評価側の閾値・採用105行・評価27行を、このprofileへ合わせて変更していない。採用する実測モデルが決まった後、その仕様を同じ経路へ接続する必要がある。

[比較集計](results/verification-integration-20261125/integer-parity-summary.json)

## 2. proofと受付情報を一つの入口で検証

[`verify_entry.go`](verify_entry.go)に次を追加した。

- `DecodeSignedPublic`：BN254・public-only・正しい要素数を確認し、SignedCircuitのschema順で値を読み取る。手書きindex表や別JSONを使わない。
- public witnessが同じ要素数でもsecret要素を含むヘッダなら拒否する。別curve、full witness、nilも拒否する。
- 受け取ったvectorをコピーし、そのsnapshotから受付値を取得する。元vectorの後からの変更でsnapshotが変わらないことを試験した。
- `ReceiptFromSignedPublic`：正規化した受付値と鍵を取り出す。
- `VerifySignedProof`：同じsnapshotに対して受付条件と実際のGroth16検証を実行し、両方が通った場合だけ検証済みreceiptを返す。

`VerifySignedProof`には、依頼者が渡すPublicReceipt引数がない。proofとは別に都合のよいreceiptを作り、受付検査だけを通す構成を避けた。

### 信頼境界

VKとExpectedContextは**サーバー側の承認済み設定**から渡す。依頼者が持ち込んだVKやcontextをそのまま承認しない。curveと公開要素数の確認だけではVKが正しい回路版だと認定できないため、実運用入口では回路/ソース/依存版/schemaを固定したVK管理が必要。

この関数は永続保存をしない。mapによる既受理ID照会は単体試験用であり、並行受付の原子的重複排除、障害・再起動後の復元、同一観測の別RecordIDでの再署名防止はまだ未実装。

`CheckAdmission`単体は引き続き事前検査にすぎない。実際の受付で別receiptと別proofを個別に検査する古い使い方へ戻さない。

## 3. 未来時刻の方針

ExpectedContextへ`MaxFutureSkewMS`を追加した。

- 既定0：claim時刻がnowより未来なら拒否。
- 明示した許容幅以内：境界を含め許容。
- 許容幅を超える場合や32bit外の設定：拒否。

加算のoverflowを避けるため、未来の場合の差分で比較する。0ms/1ms境界と範囲外を検査した。前回の診断（now150000、claim170000）は拒否へ変わった。

現在のreceiptで公開されるclaim時刻に対する方針であり、非公開の観測時刻が現在時刻に対して常に正しいと認証したものではない。元RIDの毎時時刻・UTC・単調時計の対応や実時計誤差を得る工程も別途必要。

## 4. 実proofの統合試験

合成1件のsetup/proveに続き、**新しいVerifySignedProof経由**で検証した。検証結果から取り出したcommitmentが割当と一致すること、公開status/session/commitment/observerの変更、受付済みID、未来claimを拒否することを確認した。

ヘッダのpublic-only検査を追加した後も、資源条件を満たす場合に最終ソースの統合試験を再実行する。実行/未実行は[実行状態](results/verification-integration-20261125/proof-run-status.json)と[proof集計](results/verification-integration-20261125/signed-proof-summary.json)を正とする。初回成功のログ/集計は`before-header-check-*`として保持する。追加の安全検査を入れたための回帰試験であり、性能平均を得るための反復実験ではない。

資源確認は同日の[preflight](results/verification-integration-20261125/proof-preflight.json)。事前閾値を下げず、並列度2・Go soft GC target 1GiB・テスト120秒の単体試験のみ。再帰setupではない。メモリ不足なら未実行として記録し、チャット内で無期限に待たない。

鍵・proof・witnessはメモリ内だけで、ファイル保存なし。使い捨て単独setupでありrelease鍵ではない。実captureを使った署名/proof、Pi/Android、EVM、再帰は未実施。

## 5. 再現

```sh
cd week_tmp/circuit-design
mkdir -p results/NEW_RUN
DRAFT_SUMMARY_PATH=results/NEW_RUN/constraint-summary.json go test -count=1 -v ./...
```

通常試験ではsetup/proofを起動しない。単体proofは資源を確認後、次で明示的に実行する。

```sh
GOMAXPROCS=2 GOMEMLIMIT=1GiB DRAFT_RUN_PROOF=1 \
  DRAFT_SUMMARY_PATH=results/NEW_RUN/constraint-summary.json \
  go test -count=1 -timeout 120s -run '^TestSignedProof$' -v ./...
```

[通常試験](results/verification-integration-20261125/unit-tests.log)、[Python](results/verification-integration-20261125/python-tests.log)、[UAV](results/verification-integration-20261125/uav-tests.log)、[aggregator](results/verification-integration-20261125/aggregator-tests.log)、[contracts](results/verification-integration-20261125/contracts-tests.log)。aggregatorは既存cache利用を含む。

作業開始時、出力先の相対パスを誤ってログ出力前に停止した。空の誤作成ディレクトリのみ除去し、正しいmodule相対パスで再実行した。入力・既存実験結果は削除していない。

## 6. 残っていること

- 実測で採用できるモデル、正常基準、独立run・真位置・時計・高度精度の根拠。
- 元IE/GPSと整数割当、claim token、観測者署名を結ぶ実データアダプタ。
- 受付の永続/原子処理、再起動復旧、同じ観測の再発行方針。
- 観測者資格・失効・匿名性、実機鍵の保存/署名。
- 実測/Pi/Androidでの検証。現回路を位置真実性・機体認証の保証にしない。

今回の変更もローカル保存。commit/push・CI・リリースは未実施。

## 最終確認

最終ソースのヘッダ検査を含む統合proof試験は成功。compile363ms、setup19,503ms、prove981ms、統合受付＋verify1,044µs。合成1件・Mac単体・並列度2の参考値であり、端末性能や平均値ではない。公開入力4種の変更、受付済みID、許容外の未来claimを拒否し、proofから取り出したreceiptで検証した。

通常回帰、96条件の整数一致、Python27件、UAV98件、aggregator、contracts48件を確認。setup鍵/proof/witnessのファイルは存在しない。公開入力のヘッダ検査前の初回ログも保持した。実測検知性能の評価値・元記録・閾値・採用マスクは変更していない。
