# Issue93：採否と警報の説明図・非公開の1観測ビューア

2026-11-19。#89の同じ採用マスクと#96の固定モデル・閾値を表示へ接続した。可視化用の新しい検出器は作っていない。

## 公開する4図

| 図 | 横軸・縦軸／内容 | 読み取ること |
|---|---|---|
| [01：品質と用途](results/research-review-20261119-f/01_quality_and_capabilities.png) | 匿名端末／採用・保留行数、評価不能の用途 | 採用105・保留219、何が不足するか |
| [02：固定モデルの失敗](results/research-review-20261119-f/02_frozen_model_failure.png) | 学習/校正/評価／残差、警報割合。連続観測ブロック／警報割合 | 校正2/26→評価13/27。独立runの比較ではない |
| [03：警報の中身](results/research-review-20261119-f/03_paired_alarms_and_synthetic_example.png) | 合成条件／同じ27行の警報遷移。完全合成例／残差dB | 元からの13警報と追加14警報を区別。補償は元スコアを保つ |
| [04：採用条件の感度](results/research-review-20261119-f/04_claim_dependent_gate.png) | 合成申告変位m／条件を通る行数 | 採用基準が申告距離にも依存。検知改善ではない |

公開図に実座標・実ID・実測個票は入れない。03右だけは完全合成の説明例であると図中へ明示し、実測集計と混ぜない。閾値以下は「真位置が正しい」の意味ではない。

## 非公開の1観測ビューア

生成物：`captures/week29/research-review-20261119-f/event-explanation-private.html`。

実測個票を含むためGitへ追加しない。ローカルの自己完結HTMLで、外部送信やサーバへの送信は行わない。1440×1000のデスクトップ表示で、次の内容が1画面内に収まることを確認した。狭い画面は縦配置へ切り替わる。

1. 評価内の観測と、申告方向・変位・合成電力条件を選択。
2. 元RSSI／元の申告水平距離と、合成変更後の値を分離。
3. 未改変・変更後のスコアと固定閾値を表・横棒で比較。
4. 警報／閾値以下／保留と理由を表示。受信局を越える近方条件では無理に距離を丸めず、スコア棒を消して保留にする。
5. 品質で保留した219行の理由を別セレクタで確認。モデル判定を適用しない。
6. 全体13/27警報・50m変更の27警報の内訳と対応させる。

同一物理送信未確認、端末間時刻未確定、3D距離評価不能を常時表示する。軌跡や受信局配置は今回描いていない。推測した配置や別時刻パケット間の線を追加しない。

#95の既存集計では、B/Pixel等に共通内容があっても確認済み同一物理送信は0件。今回の各評価行へcandidate/ambiguousを付与できる確定対応はないため、**行単位ではUNVERIFIED／NOT_EVALUABLE**とする。候補を物理一致に昇格しない。[既存#95を参照した状態JSON](results/research-review-20261119-f/packet-status.json)に元集計のhashと候補の粒度を記録した。新しいパケット照合を実行したと主張しない。

サービス停止・保存なし・RF未受信も同じではない。今回の固定した保存行だけから無観測区間のRF状態は決定できず、空白を断定的な送信停止や未受信として描かない。LoRa/LoRaIQ SNR・PHY完全合成の数値は本図へ混ぜていない。

## 検証と失敗の記録

- 4枚のPNGを画像で目視確認。Matplotlibの実際のartist値7系列と、別途読み込んだJSON/CSVを比較して一致を確認。
- 81条件で警報遷移4区分の合計＝評価行、評価＋保留＝元の27行を検証。
- 既存図の棒を1本変更する改竄テストでは検証が失敗する。
- ブラウザで初期表示・保留時のスコア非表示・理想補償時のスコア一致・219保留理由・横はみ出しなしを確認。最初の縦長レイアウトは1画面に収まらず、2列へ修正して再確認した。個票スクリーンショットもprivateにだけ保存。
- 初期描画にあったフォントの記号欠けは日本語表記へ修正。
- 描画値のJSON化でNumPy int64を直接保存しようとした試行はTypeErrorで失敗。未完了出力を成功にせず保持し、有限floatへの正規化と回帰テストを追加。最終の別出力へ全段階を再実行した。
- 参照デコーダ未準備の最初のテストは1スキップだった。固定ソースを構築し、`WEEK29_REQUIRE_REFERENCE=1`で再実行して100件・スキップ0を確認した。

[描画系列](results/research-review-20261119-f/figure-series.json)、[一致検証](results/research-review-20261119-f/figure-verification.json)、[表示確認](results/research-review-20261119-f/visual-verification.json)、[試行記録](results/research-review-20261119-f/attempts.json)を残す。

```sh
python3 week29/scripts/validate_field_review.py \
  --results week29/results/research-review-20261119-f
WEEK29_REQUIRE_REFERENCE=1 python3 -m unittest discover -s week29/tests -v
```

全段階の再現は[35](35_Issue89_元観測照合と評価可能範囲の確定.md)。入力条件・モデルの解釈は[36](36_Issue96_固定モデルの失敗診断と採用条件の感度.md)。研究PoCであり、申告ID・観測者署名・計算の一致から、機体認証・DRIP・センサ／観測ハードの真正性を導かない。

## 公開・CI確認

[PR #102](https://github.com/SMRI2170/zkp-m1-v2/pull/102)、コードSHA `e8a5a74`。push/PRのActions 4 runs・6 job checksがすべて成功し、完了ログを確認した。Week29 100件（参照必須・skip0）、UAV50件、Go、contracts21件、既存Dataset-21/数値テストの検証もCIで成功。[CI記録](results/research-review-20261119-f/ci-code-e8a5a74.json)。外部CodeRabbitのSKIPPEDは実行済みレビューではない。PR #101に依存し、未マージ。
