# PR #85：KMP受信アプリの公開とCI確認

対象実装コミット：`75f04e6cc5b2b19e2a5e92005f09e39f403e3f38`。
元の作業ブランチ全体を公開せず、origin/mainを起点にKMPコード・専用CI・関連報告だけを分離した。
[Draft PR #85](https://github.com/SMRI2170/zkp-m1-v2/pull/85)、[Issue #84](https://github.com/SMRI2170/zkp-m1-v2/issues/84)。マージはしていない。

## 確認したGitHub Actions

| イベント | ワークフロー | 結果 |
|---|---|---|
| push | [KMP RID Observer](https://github.com/SMRI2170/zkp-m1-v2/actions/runs/42746780766) | 成功 |
| pull_request | [KMP RID Observer](https://github.com/SMRI2170/zkp-m1-v2/actions/runs/42746825264) | 成功 |
| push | [Dataset-21 main integration](https://github.com/SMRI2170/zkp-m1-v2/actions/runs/42746780646) | 成功 |
| pull_request | [Dataset-21 main integration](https://github.com/SMRI2170/zkp-m1-v2/actions/runs/42746825274) | 成功 |

4実行・計6ジョブの成功結果と完了ログを確認した。KMPのPR成果物をダウンロードし、JUnit XMLも確認した。
Androidホスト・JVMはそれぞれCoreTest 12件＋CaptureBudgetTest 3件、失敗0・エラー0。
Python集計・端末選択・保存先境界は9件成功。APK・JVM配布物・Lintも成功。

## 既存チェックの解釈

公開先mainと元のローカル作業ブランチには、既存成果の取り込み範囲の違いがある。

- ローカルの既存チェック：UAV77件、contracts48件、Go成功。
- 公開PRの既存チェック：UAVはmainにtest_*.pyがないため **NOT RUN** と明記。UAV成功とは数えない。
- 公開PRのcontractsは21件成功、Go成功。
- 公開PRのDataset-21監査系は18件、GhostBuster系は8件成功。結果ファイルの監査・ギャラリー整合確認も成功。

チェックを緩和したり、不足する既存成果をまとめて混入させたりはしていない。
CodeRabbitはDraftのためskippingであり、コードレビュー完了とは数えない。

## 残件

v0.3のPixel 8インストール、通知停止、背景・消灯中の受信、長時間測定は未実行。
接続端末がないため、実機事前監査で停止した。CI成功は実機のサービス動作を証明しない。
Issue #84を閉じず、Draftのまま実機評価へ進める。
