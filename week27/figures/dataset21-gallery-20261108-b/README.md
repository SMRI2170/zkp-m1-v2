# Dataset-21：図の一覧

**全て入力診断。位置偽装の検出率ではない。新しい実験は実行せず、保存済み集計を別の形で描画した。**

| 形 | 読み取ること |
|---|---|
| [欠測率×局数のヒートマップ](05_missing_heatmap.png) | 実測時刻＋合成欠測。時刻幅200ms、評価54窓。欠測ありは20マスク平均。検出率ではなく入力成立率。 |
| [入力成立／不足の積み上げ棒](06_ready_vs_unavailable.png) | 同じ54窓が分母。20マスクの平均。灰色は不正の見逃しではなく、必要な観測が不足した窓。 |
| [欠測パターンごとの箱ひげ図](07_mask_boxplot.png) | 点は合成欠測20マスク。左右のずれは重なり回避用。実飛行は1つであり、20回の飛行結果や信頼区間ではない。 |
| [局×時間のRSSヒートマップ](08_rss_time_heatmap.png) | D1実測。全局・両chで同じ色尺度。灰色は区間データなし。局間の受信ゲイン差を含み、独立校正済み絶対電力や位置の地図ではない。 |
| [候補の絞り込みウォーターフォール](09_candidate_waterfall.png) | 5局・時刻幅200ms・追加遅れ／人工欠測なし。単位は全て観測候補数。残る666件も同一送信と確認されたものではない。 |
| [学習・校正・評価の時系列図](10_split_timeline.png) | 同じ1飛行の時系列分割。各隔離区間は約46秒。隔離はRF欠測ではなく評価手順で、別飛行への一般化を確認したものではない。 |

## 元の4図

- [折れ線：実測RSSの時間変動](../../results/dataset21-eval-20261108-e/figures/01_measured_rss.png)
- [折れ線：局数と近接候補率](../../results/dataset21-eval-20261108-e/figures/02_receiver_availability.png)
- [折れ線：欠測率と入力成立率](../../results/dataset21-eval-20261108-e/figures/03_missingness.png)
- [折れ線：観測時刻差と入力成立率](../../results/dataset21-eval-20261108-e/figures/04_observation_lag.png)

各図はPNGと編集可能なSVGを保存。

再現：`.cache/issue77/python/bin/python experiments/week27-data-audit/plot_dataset21_gallery.py --source week27/results/dataset21-eval-20261108-e --out 新しい出力先`
