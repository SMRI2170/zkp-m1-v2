# 実行結果

最新の追加は[署名付き回路・合成単体proof](../SIGNED_DESIGN.md)を参照。以下の未実行記述は各段階時点の履歴。

2026-11-24、Macローカル。全入力はテストコードに書いた合成値で、実capture・GPS・鍵を利用していない。

| 確認 | 実際の結果 |
|---|---|
| 試作R1CSコンパイル | BN254、93,772制約、public 26変数（定数1を含む）、private 7変数 |
| `go test -count=1 -v ./...` | 合成44ケース成功。正しい判定を通し、改変/整数範囲外などを拒否 |
| UAV unittest | 98件成功 |
| aggregator `go test ./...` | 成功、パッケージの既存テスト結果はcache利用 |
| contracts `npm test` | 48件成功 |

今回の比較は満足可能性と拒否条件の検査であり、証明生成時間やPi性能測定ではない。93,772制約は最適化前の一般比較とMiMCを含む現版の値で、方式間優劣を示すものではない。

## 見たケース

整合/警報/時刻保留/精度保留、距離帯の境界前後、RSSI両端、時刻の前後、最大座標/ゼロ距離、虚偽status、負座標/桁超過、nonceゼロ/桁超過、距離帯逆転/欠落、RSSI区間逆転、元commitmentを維持したsession/frame/claim token/座標/RSSI/時刻/nonce/方針の書換え。

各ケースはgnarkのR1CS solverで実行した。合成native hashと回路内MiMCも同じ入力で対応する。テストで利用する固定nonceは本番の乱数生成例ではない。

## 未実行

実測モデルの評価、実入力アダプタ、観測者署名との結合、setup、PK/VK、proof生成/検証、再帰証明、EVM検証、端末配備、GitHub push/CI。これらの成功を今回のテスト結果から推定しない。

## 作業中の失敗・修正

追加テスト編集の最初の呼出しで作業ディレクトリに対するファイル相対パスを誤り、ファイル読込みとgofmtが失敗した。正しいルートから編集し直した。別の再実行ではリポジトリルートからモジュール内のログ相対パスへ出力しようとして、シェルのリダイレクトが失敗した。モジュールディレクトリを明示して再実行した。これらをテスト実行成功として数えず、最終ソースに対する44ケースの非cache実行ログを保存した。

[制約集計](constraint-summary.json)、[コードhashと全体結果](validation.json)、[回路テストログ](circuit-tests.log)、[UAVログ](uav-tests.log)、[Goログ](aggregator-tests.log)、[contractsログ](contracts-tests.log)。既存ソースや受理ルールを変更して結果を合わせる修正はしていない。

## 位置・高度・時刻の誤差対応の追加

[追加報告](../uncertainty/README.md)の`UncertaintyCircuit`25ケースも加え、最新の回路テストログは旧44＋新25ケース成功。追加回路は119,990制約。実データ324行の精度コードを旧版CのLocationデコーダへ照合し、固定27行に対して13誤差設定×3合成攻撃条件を評価した。Pythonは27テスト成功。高度精度は未保存のため、実3D誤差は未評価、仮定半径による感度分析のみ。今回もproof生成・署名接続・配備は未実行。

## 署名付き回路・合成単体proofの追加

署名付き24ケース、外部受付20ケースを検査し、計算核44・誤差対応25も維持。通常テストはproof試験を明示skipし、別途opt-inで合成1件のGroth16 setup/prove/verifyを実行した。公開入力4種類の改変拒否を確認。鍵・proofはファイル出力なし。実測署名接続・Pi/Android・再帰・EVMは未実行。

[署名制約集計](signed-constraint-summary.json)、[proof集計](signed-proof-summary.json)、[proofログ](signed-proof.log)、[事前メモリ確認](signed-proof-preflight.json)。
