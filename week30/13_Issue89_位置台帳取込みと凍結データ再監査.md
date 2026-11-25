# Issue89：位置台帳取り込みと凍結データ再監査

2026-11-25。既存記録を保全したまま入力品質ゲートを進めた。新しい飛行・RF受信成功・位置偽装検知性能を示すものではない。

## 実行結果

| 対象 | 今回の結果 | 言える範囲 |
|---|---|---|
| 11月16日のAndroid元DB 4件 | 324行を再照合、105行採用・219行保留で一致 | 同boot内の水平代理評価用の凍結選択を維持 |
| 原本・採用マスク | hash一致、入力変更なし | 再解析で旧記録を上書きしていない |
| 私的bench計画 A〜F | 6台ともposition/position_trackなし | この計画だけでは固定位置・移動軌跡を結合できない |
| 保存済み接続先によるA〜F確認 | 6台ともSSH接続できず | 接続不能。電源断・故障・ネットワーク不在とは断定しない |
| #104のON/OFF/ON・新規v0受信 | 未実行 | 受信器と送信器への接続が前提。サービス変更も行っていない |

検索した範囲はリポジトリ内captures/week29・captures/week30と週別資料のファイル名、既存run計画。利用者が持つ位置台帳そのものが存在しないとは結論しない。保存先の確認が必要。過去のNTP状態を今回の同期や11月16日の同期根拠に流用していない。

## 実装した取り込み処理

`experiments/field-kit/join_position_ledger.py`は、私的なイベント配列と位置台帳配列を結合する。観測者位置は固定点または移動fix、距離計算の相手はRID申告位置であり、独立真位置ではない。

- alias/run/bootを一致させ、UTCはtimezone必須。観測時刻±時計不確かさの区間全体が台帳の有効期間内に収まることを要求。
- 出所参照・測定方法・EPSG:4326・有限の座標・正の水平精度申告を要求。曖昧な複数候補は保留。
- 移動A/Androidに固定位置を代入しない。track_fixの時刻差＋時計不確かさが2秒以内のときだけ結合。2秒は固定の研究用ポリシーであり物理精度保証ではない。
- 水平距離は申告位置までの大円距離。3Dは双方が同じMSLまたは楕円体基準で、双方に高度・垂直精度がある場合だけ計算。local_ground/AGLは共有地表基準なしでは受理しない。
- 不明な精度を0に置かない。水平・垂直精度の和は申告値の和で、実誤差の上限や信頼区間ではない。移動による不確かさ・アンテナ高さ・ジオイド変換は別途評価が必要。
- `evidence_ref`/`clock_evidence_ref`はレビュー済み資料への参照を入力する欄。文字列の存在やhash一致は測定の正直さ・時計精度・物理真値の証明ではない。結果はmetadata_onlyとして出す。
- 実座標を含む結合結果と入力hashはignored capturesに0700/0600。公開JSONは件数・理由のallowlistのみ。入力/出力のsymlink、公開権限、既存出力への上書きを拒否。

### 私的入力の形式

入力はJSON配列。実値はGitに置かない。

| 入力 | 必要なキー |
|---|---|
| events | alias(A〜F/ANDROID), run_id, boot_id, moving(bool), observed_utc, clock_uncertainty_s, clock_evidence_ref, claim |
| claim | latitude, longitude, horizontal_accuracy_m。3Dはaltitude_m, altitude_reference, vertical_accuracy_mも必要 |
| ledger | alias, run_id, boot_id, kind(fixed/track_fix), latitude, longitude, crs, horizontal_accuracy_m, method, evidence_ref, valid_from_utc, valid_until_utc |
| 移動fix追加 | fix_utc。固定位置で代用しない |
| 高度追加 | altitude_m, altitude_reference(MSL/WGS84_ellipsoid), vertical_accuracy_m |

boot紐付けはrun manifest上の観測bootと台帳を結ぶ入力。測量記録自体がbootを記録していたと主張しない。現行コードは元SQLite/JSONLを自動で推測変換しない。既存元DB監査と、今後の台帳・run対応の明示レビューを併用する。

```sh
python3 experiments/field-kit/join_position_ledger.py \
  --events captures/week30/PRIVATE_RUN/events.json \
  --ledger captures/week30/PRIVATE_RUN/ledger.json \
  --private-output captures/week30/NEW_JOIN \
  --public-output week30/results/NEW_JOIN
python3 -m unittest discover -s experiments/field-kit -p 'test_*.py'
```

18件の新規合成テストで幾何、期間端、時計根拠不足、別ノード/run/boot、移動fix鮮度、欠測、高度基準不一致、複数候補、公開出力、権限、symlink、原本保持・上書き拒否を確認。現実の台帳結合成功とは区別する。

## 根拠・残件

[元DB再監査](results/quality-followup-20261125/frozen-audit.json)、[位置計画の不足](results/quality-followup-20261125/position-readiness.json)、[接続結果](results/quality-followup-20261125/connection-summary.json)、[ローカル検証](results/quality-followup-20261125/validation.json)。接続先・実ID・時計サンプル・行単位結果はprivateのまま。

次は実際の位置台帳の所在と有効期間を確認し、run/boot/時計根拠へ結合する。高さ基準未確定なら2Dのみ。接続復帰後に#104を実行。#96の現モデル不採用判断は変更せず、独立真値・正常/攻撃ラベル・同一物理送信を今回作ったことにしない。

この時点の検証は元の作業ディレクトリ（既存未公開変更を含む）。公開する場合は独立checkoutの検証結果と区別する。研究PoCであり、DRIP、機体認証、センサー/ハード真正性を保証しない。

## 公開checkoutの検証

既存mainを起点に今回の2ソース・匿名集計・本報告・CIだけ選別。field-kit43件（新規18件を含む）、UAV50件、Go、contracts21件が成功。元の作業ディレクトリの54/98/48件との差は、以前からの未公開変更を混ぜていないため。初回はfresh checkoutにignored capturesディレクトリがなく合成テスト2件が失敗したため、テストfixtureが0700で作成するよう修正。実装の権限制約や評価ゲートは緩めていない。依存更新なし。

[公開checkout検証](results/quality-followup-20261125/publication-validation.json)。新CIも機器・実capture不要の合成テストであり、実機試験を代替しない。
