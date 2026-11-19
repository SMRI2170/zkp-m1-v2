<!-- ISSUE_TRIAGE_2026_11_17 -->
# 現在のIssue一覧（2026-11-17整理後）

最新の入口は[全体管理 #88](https://github.com/SMRI2170/zkp-m1-v2/issues/88)。元の64件を全体1件＋作業6件＋将来保留2件へ集約した。旧一覧は以下に履歴として保持する。

[整理結果と全55件の引継ぎ表](24_GitHub_Issue整理と引継ぎ.md)

現在の子Issue：#84 Android、#89 データ品質、#93 可視化、#95 同一送信、#96 検出評価、#97 Pi収録・保存。将来保留：#28 ZKP/P2P/BC統合、#44 ZKP比較。

<details>
<summary>整理前のWeek29一覧と当時の親子関係（履歴）</summary>

# Week29：追加分析のIssue一覧

親Issue：[実機Remote IDの保全・時刻監査・3D軌跡・RSSI比較と位置偽装評価 #88](https://github.com/SMRI2170/zkp-m1-v2/issues/88)

| 優先度 | Issue | 目的 |
|---|---|---|
| P0 | [#89 データ監査・時計ずれと実験区間の照合](https://github.com/SMRI2170/zkp-m1-v2/issues/89) | 全分析で使える入力・時刻の確定 |
| P0 | [#90 記録停止・受信空白と保存修正の確認](https://github.com/SMRI2170/zkp-m1-v2/issues/90) | 記録されない理由の切り分け |
| P1 | [#91 Android自己位置の品質・欠測](https://github.com/SMRI2170/zkp-m1-v2/issues/91) | 距離評価に使える測位条件の監査 |
| P1 | [#92 Pi／Androidの取得間隔・重複・キャッシュ](https://github.com/SMRI2170/zkp-m1-v2/issues/92) | 新しい内容の実効取得間隔の比較 |
| P1 | [#93 3D軌跡上のRSSI・受信区間](https://github.com/SMRI2170/zkp-m1-v2/issues/93) | 観測場所と電波強度の可視化 |
| P1 | [#94 申告距離・高度と実測RSSI](https://github.com/SMRI2170/zkp-m1-v2/issues/94) | 距離減衰・ばらつき・モデル誤差の分析 |
| P1 | [#95 多端末の同一送信候補・RSSI差](https://github.com/SMRI2170/zkp-m1-v2/issues/95) | 共通電力を相殺する条件の検証 |
| P2 | [#96 合成位置偽装・電力補償の検出評価](https://github.com/SMRI2170/zkp-m1-v2/issues/96) | 実測を基準にした検出可能性の評価 |

まず#89を進め、#90・#91で停止と位置品質を確認する。その上で#92〜#95を解析し、入力条件が成立する場合だけ#96を評価する。情報不足は推測で埋めず、評価不能・保留の理由として残す。

#83のPi観測基盤、#84のAndroid受信実装と関連付け、Week29で同じ実装タスクを重複管理しない。3D可視化は#69の成果を再利用する。

各Issueに作業・完了条件・CSV/JSON/グラフ/報告MD・テスト・秘密データの扱いを記載した。実測RSSI、RIDの申告位置、合成攻撃、独立真位置を明確に区別する。Issue作成は実験完了を意味しない。

## #90の導入作業の子Issue

- [#97 Pi受信ノードB〜Fへの保存容量対策・保全・起動復旧・長時間検証](https://github.com/SMRI2170/zkp-m1-v2/issues/97)

#88 → #90 → #97の親子関係で管理する。Aでの確認・Android 3台への修正と、Pi B〜Fへの導入完了を分ける。登録時点ではB〜Fへ接続できず、実機変更は未実施。接続不能・未実行の状態もIssueに記録した。

</details>
