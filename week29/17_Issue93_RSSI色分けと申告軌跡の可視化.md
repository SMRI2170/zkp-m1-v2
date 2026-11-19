# Issue93：申告軌跡をRSSIで色分け

既存のWGS84→ENU変換と空白で線を切る処理を再利用し、端末切替・上面／側面・RSSI共通色尺度の3D図を作成した。Geo高度とHeightは別ファイルとし、数値や基準を混ぜていない。

## ローカル成果物

座標を含むため、実データの図はGitに追加しない。

- `captures/week29/issue93-rssi-d/01_rssi_geo_3d.html`：Geo高度・RSSI色分け・端末切替。
- `captures/week29/issue93-rssi-d/02_rssi_height_3d.html`：Heightの別表示。
- `captures/week29/issue93-rssi-d/03_rssi_track_and_time.png`：端末別の上面図とRSSI時間推移。
- 同フォルダの`tracks-private.csv`と`inputs-private.json`：派生点列と入力manifest。
- [公開できる匿名集計](results/issue93-rssi-d/summary.json)。

描画対象はB 531、Pixel 132、ASUS-1 146、ASUS-2 46行の保存記録。保存行数は独立パケット数ではない。Bの観測時刻再利用24行を含むため、重なる点を多くの独立観測と読まない。RSSI共通範囲は−87〜−40dBm。RSSI欠損は灰色×、高さ不明は点を描かず線を切る実装。今回の対象にはRSSI欠損はなかった。

## 読み方と未確認事項

色は受信端末が保存した未校正RSSI。点の場所はそのメッセージが申告する機体位置であり、RSSIから機体位置を推定した結果ではない。端末ごとの受信ゲイン・配置を補正していないため、色だけで受信機性能を順位付けしない。

端末時計を無理に結合せず、各時計対応群内だけを線で接続する。60秒を超える空白、およびHeight基準タイプが変わった箇所で線を切る。各端末の経過0分は同時刻を意味しない。別端末でのみ観測された軌跡を補間して、他端末が受信したようには描いていない。

受信機の設置位置が未確認なので、固定ノードの配置点は描かない。Androidの移動自己位置は別の既存3D再生（報告12）で示す。この図への距離重ね描きは実施していない。

受信空白のサービス状態との時刻対応はNOT_EVALUABLE。空白を電波未受信・電源断・通信範囲外と断定できない。送信総数も不明で、PDRや通信可能距離は計算しない。

## 再現・検証

```sh
.cache/week26-mac-venv/bin/python week29/scripts/plot_rssi_tracks.py \
  --observations captures/week29/issue89-audit-c/target-observations-private.jsonl \
  --private-output captures/week29/issue93-rssi-new \
  --output week29/results/issue93-rssi-new
python3 -m unittest discover -s week29/tests -v
```

既存出力を上書きしないため新しいprivate-outputを指定する。入力前後SHA-256一致、0700/0600の非公開保存、共通色範囲を確認。ENUの既存テストに加え、60秒境界・Height基準変更・欠損RSSI・同じ監査行の二重描画をテストした。PNGを目視確認し、狭い上面図の目盛り重なりを修正。Orca内蔵ブラウザでGeo／Height両HTMLの描画、端末ドロップダウンによるBの3トレースのみ表示、上面ボタンでのカメラ変更を確認。タイトル・注記・凡例の重なりを修正し、最終Geo図を目視確認した。旧a〜c出力は保持。サービス状態との照合と公開CI確認は残件。
