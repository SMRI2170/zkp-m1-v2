# Week27：Dataset-21実測RSSの監査と入力条件評価

- [全10図の一覧](figures/dataset21-gallery-20261108-b/README.md)
- [実ファイル監査と5局RSSの対応可否](18_Dataset21実ファイル監査と5局RSSの対応可否.md)
- [評価アダプタ・実行条件・未実行事項](19_Dataset21実測RSS評価アダプタと位置偽装実験の実行条件.md)

D1のRSSは実測。申告位置・電力加算・欠測は合成条件。図の入力成立率は位置偽装の検出率ではない。地上受信局座標・共通高さ基準が不足しており、実測FPR/TPRの評価は未実行。同一送信の5局受信や独立した絶対電力校正は成立を確認していない。

## mainへの反映範囲

PR #80・#81のDataset-21関連ファイルと、直接必要なGhostBuster計算・テストのみを反映。他のWeek24〜27作業を一括マージしていない。元PR・元ブランチは保持。

## 公開集計の検証

```sh
python3 -m unittest discover -s experiments/week27-data-audit -p 'test_*.py'
python3 -m unittest discover -s experiments/week27-rid-sim/tests -p test_ghostbuster.py
python3 experiments/week27-data-audit/audit_aerpaw21_results.py week27/results/dataset21-local-audit-20261108-b
python3 experiments/week27-data-audit/audit_dataset21_eval_results.py week27/results/dataset21-eval-20261108-e
```

数値テストにはNumPy/SciPyが必要。描画にはMatplotlibが必要。生RSS/GPSはGitに含めず、既存のハッシュ・集計・未実行ゲートを検証する。

## main反映時の検証

- Dataset-21テスト18件、GhostBuster数値テスト8件：成功。すべて合成fixtureによる単体検証であり、実測位置偽装検出実験ではない。
- 公開集計2種類の監査、ギャラリーの出力・元集計・描画コードのハッシュ、10図リンク：成功。
- mainのGoテスト、コントラクト21件：成功。
- mainの `python3 -m unittest discover -s uav -p 'test_*.py'`：終了コード0、対象テスト0件。作業ブランチ側の61件を実行したという意味ではない。
- 既存の画像をそのまま反映し、描画し直し・新規RF実験・新規検出性能評価は実施していない。

CI初回はPython 3.12のunittest探索が対象0件で終了コード5となった。テスト失敗を無視せず、対象が存在する場合は通常実行・失敗伝播し、存在しない場合はNOT RUNをCIのnoticeとSummaryへ明記する方式に変更。ローカルPython 3.15の0件終了コード0との違いであり、UAVテストの成功を追加主張しない。
