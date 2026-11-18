# Android移動ノードを追加した新しい3D再生

関連：[可視化 #93](https://github.com/SMRI2170/zkp-m1-v2/issues/93)、[自己位置品質 #91](https://github.com/SMRI2170/zkp-m1-v2/issues/91)。前のドローン単体3D図を残し、Android 3台の自己位置記録を加えた別版を作成した。

## 追加したもの

- ドローン：Bで受信した実機RIDの申告軌跡507点。
- Pixel：独立テーブル`receiver_fixes`から8,052点。
- ASUS-1：同テーブルから7,200点。
- ASUS-2：同テーブルから4,151点。
- 4者の軌跡を色分けし、凡例で端末ごとに表示/非表示を切替可能。
- 507フレームの受信順再生。ドローンとAndroidの位置マーカーを更新する。
- 近傍3秒以内にGPS記録がない端末は、マーカーを消す。古い位置の維持や外挿をしない。
- ドローンは60秒、Androidは10秒を超える記録空白で線を切る。

点数は独立した移動回数・独立試行数ではない。スマホの軌跡には測位の揺らぎも含まれる。

## 新しい保存先（ローカル・非公開）

`captures/week29/drone-android-3d-v1/`

| ファイル | 内容 |
|---|---|
| `01_drone_android_relative_3d.html` | 各端末の初回高度からの変化量で比較する3D再生 |
| `02_drone_android_raw_altitude_3d.html` | 記録されたGeo/GPS高度を補正せず表示する3D再生 |
| `03_android_tracks_top_and_height.png` | 全員の平面移動と高度変化の図 |
| `drone_android_tracks_private.csv` | 表示に使った座標・高度・補正候補時刻・精度属性等 |
| `summary-private.json` | 抽出条件・件数・高度範囲・欠測フレーム等 |

HTMLにPlotly本体を埋め込み、外部地図やネットワーク接続なしで使用できる。マウスで回転・拡大し、「移動を再生」でマーカーを動かす。時刻表示は補正候補。再生速度・スライダーは観測順であり、実時間比例ではない。

元の`captures/week29/drone-3d/`は上書きしていない。新しい図も実座標由来なので、Gitへ追加しない。

## 高度は2通りに分けた

今回の抽出区間では、ドローンの申告Geo高度は74〜97m、スマホの記録GPS高度は約177〜197mだった。同じ場所での上下関係を表す値としては、大きな不整合がある。どちらが正しいか、基準・機体実装・測位誤差のどれに起因するかは未確認。

1つ目の図は、**各端末で「記録高度−その端末の表示区間内の最初の記録高度」**を縦軸にした。水平位置は共通ENUだが、縦軸は端末ごとの別基準なので、共通の地上高や機体とスマホの真の高度差を示さない。

2つ目の図は、生の高度差をそのまま残した。地面を勝手に0mにしたり、約100mのオフセットを差し引いて一致させたりしていない。スマホが実際に100m上にいたという結論にもならない。

スマホの上下方向の変化を、階段移動・上昇下降と直ちに解釈しない。機体の離陸点基準Heightもこの相対高度とは別の値であり、初回Geo高度差の図へ混ぜていない。

## 時刻対応・抽出条件

[Issue89監査](11_Issue89_全保存先の監査と時刻対応候補.md)の定数時計オフセット候補の中点を表示用に使用した。各端末の観測UTC−monotonicの中央値と、その端末の`fix_elapsed_us`を使い、対象観測と一致するboot_scopeだけを採用した。

GPSの`fix_utc`だけで選択していない。保存データには古い年の日付もあり、その値とホスト時計を無条件に混ぜると別時間帯の軌跡を表示するおそれがある。元の`fix_utc`は非公開CSVに残した。

表示窓はドローンの最初〜最後の対象観測の前後60秒。モデル上の候補時刻では11月16日15:16ごろ〜17:30ごろになる。絶対時刻の確定・同一物理パケットの照合は未達。GPSの近傍3秒という表示条件は、真の時計誤差が3秒以内であるという保証ではない。

端末の記録がない再生フレームはPixel 0、ASUS-1 319、ASUS-2 356だった。これはGPSの近傍記録がないフレーム数であり、無線受信の失敗回数ではない。

Pi Bの設置位置は不明なので受信ノード点を描いていない。座標原点は「機体の最初の申告点」であり、Bの位置ではない。

## 再現・検証

生成コード：`week29/scripts/build_drone_android_3d.py`。入力SQLiteはread-onlyで開く。実データ出力はignored `captures/`内に限定し、完成済み出力の上書きを拒否する。

```sh
.cache/week26-mac-venv/bin/python week29/scripts/build_drone_android_3d.py \
  --audit-private captures/week29/issue89-audit-c \
  --clock-summary week29/results/issue89-time-audit-c/clock-candidates.json \
  --drone-trajectory captures/week29/drone-3d \
  --android Pixel=captures/week29/nodes/android/device-1/raw/files/captures/database/observations.sqlite \
  --android ASUS-1=captures/week29/nodes/android/device-2/raw/files/captures/database/observations.sqlite \
  --android ASUS-2=captures/week29/nodes/android/device-3/raw/files/captures/database/observations.sqlite \
  --output captures/week29/drone-android-3d-recheck

python3 -m unittest discover -s week29/tests -v
```

実行済み：Week29テスト32件成功・skipなし。古い位置を維持しない近傍選択、空白での線切断、時計群/boot情報の条件をテストした。ローカルブラウザで2種類の3D図の8トレース・507フレームを確認し、Pixelの位置が移動すること、GPSがない区間でASUSマーカーが消え、別の区間では3台とも表示されること、時刻タイトルの更新を確認した。平面図・高度図・ブラウザ表示も目視確認した。

ドローンの位置はRID申告値、Androidは端末のGPS記録であり、いずれも独立した真位置の検証ではない。今回の版は移動を見比べるための可視化であり、位置偽装検知や安全性判定の完成を意味しない。
