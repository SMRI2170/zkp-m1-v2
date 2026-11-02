# Week26：公開実測BLEデータを使ったRSSI変動の校正と追加検証

**作成：2026-11-01／実測データ取得・集計済み／合成シミュレーションへの変動追加試験済み。**
**重要：実測は「屋内BLEビーコン」であり、屋外UAV Remote IDの受信電波ではない。真のUAV距離精度の評価結果ではない。**

## 1. 取得・解析した公開実測データ

- [manwestc/ble-rssi-indoor-localization-dataset](https://github.com/manwestc/ble-rssi-indoor-localization-dataset)、[Zenodo DOI](https://doi.org/10.5281/zenodo.19055504)。
- 使用した原ファイル：`data/Tx_8.csv`、`data/Tx_4.csv`、`data/Tx0.csv`。GitHubコネクタで**実際に3ファイルの内容を取得・解析**。各2,800行、合計8,400行・50,400 RSSI値（6ビーコン×28測定セクター×100サンプル×3設定電力）。
- 測定機材：MOKO SMART H2 BLEビーコン6台、Xiaomi Mi 9T Proスマホ1台。屋内2階層、28セクター。
- 公称送信出力：−8、−4、0dBm。各地点・各ビーコン・各設定の中央値を使って、電力間のRSSI変化を比較した。

### 実測結果

| 実測値から算出した量 | 結果 |
|---|---:|
| グループ内RSSI残差の絶対値中央値 | 3.0dB |
| 絶対値の90パーセンタイル | 11.0dB |
| 絶対値の95パーセンタイル | 20.0dB |
| グループ内残差RMS | 8.21dB |
| TX−8→−4dBm（公称+4dB）のRSSI中央値の変化 | +2.0dB |
| TX−4→0dBm（公称+4dB）のRSSI中央値の変化 | +2.5dB |
| TX−8→0dBm（公称+8dB）のRSSI中央値の変化 | +4.75dB |

上記は独立した電力設定セッションの比較であり、個々の送信フレームの出力真値を測ったものではない。差は時間・姿勢・室内環境の違いを含む。

## 2. 既存の3D合成シミュレーションへどう組み込んだか

前回の`simulate_advanced.py`は、3D幾何・LOS/NLOS・shadowing・受信機差・欠測を**仮定した**伝搬モデル。今回、**実測で得たRSSI変動のヒストグラム（18階級）**から乱数をサンプリングし、既存の**受信できた**RSSI値に追加した。

変動倍率：0%、25%、50%、100%。学習・校正飛行とテスト飛行は分離。3seed、正常電力、位置＋電力偽装（±8dB）、無制約偽装を比較。単一パケットRSSI・拠点間非同期は維持。

**大きな注意**：屋内RSSI変動を屋外A2Gの分布そのものとして再利用していない。既存合成shadowingと**二重に揺らぎを数える**ため、これは**悲観的ストレステスト**であり、「現実のドローンの誤差」を予測しない。

### 正常条件：実測変動を追加した結果（3seed）

| 実測変動の混入強度 | GP距離MAE | GPの公称90%区間の実包含率 | 30m誤判定／全受信イベント |
|---|---:|---:|---:|
| 0% | 26.18m | 82.47% | 1.71% |
| 25% | 26.89m | 80.55% | 1.80% |
| 50% | 28.37m | 78.43% | 2.14% |
| 100% | 30.81m | 71.99% | 3.34% |

±8dB制限付き位置＋出力偽装で100%変動を加えると、GP距離MAE38.95m、公称90%区間実包含率59.70%、30m誤判定は全受信イベントの7.30%。**真の位置偽装や送信出力変更の原因を観測したという意味ではない。**

## 3. 論文の再現性と現状

- 解析結果は本会話で作成済みの`week26_real_data_calibration_and_sim.zip`に、原データSHA検証付き取得スクリプト、実測要約JSON、シミュレーションコード、CSV、図、READMEとして提供済み。**GitHubには本調査メモのみを保存**。元データはユーザーが原リポジトリから取得できる。
- 誤差階級の端は±25dBで近似し、元のRSSI全行は配布ZIPに含まない。
- 同じBLEデータで学習し同じ条件でテストしたわけではなく、**実測変動を合成UAVモデルへ注入するドメインシフト評価**。
- まだ「実UAV＋BLE Remote ID＋真3D距離＋受信RSSI＋出力操作真値」の同時公開データは取得できていない。

## 4. 次に取得する実測ソース（優先順位）

1. [A2G LTE UAV 3D channel data](https://github.com/Mehranbjt/Empirical-3D-Channel-Modeling-for-Cellular-Connected-UAVs)：実飛行約95,000件から11,060件を選別したRSRP、RSSI、伝搬損失、距離・高度情報。**LTE基地局→UAVという伝搬方向と無線方式の違い**に注意。
2. [AERPAW Dataset-32](https://aerpaw.org/dataset/dataset-32-aerpaw-air-to-ground-channel-sounding-and-path-loss-measurements-at-3-4-ghz-with-linear-and-zigzag-uav-trajectories/)／[Dryad 2026](https://doi.org/10.5061/dryad.2ngf1vj4r)：4飛行の3.4GHz地上送信→UAV受信、処理済みCSVと生IQ。元アーカイブは**17.27GB**。処理済みCSVを先に抽出すべき。
3. [NISTのBLE RSSI実測](https://catalog.data.gov/dataset/bluetooth-low-energy-ble-received-signal-strength-indicator-rssi-data-for-proximity-detect)：既知距離とLOS/NLOS・遮蔽の比較。**屋内／人物遮蔽**から屋外へ直接外挿しない。
4. 研究室所有の機体とPi4/Pixel8による管理下Remote ID観測で、**独立真距離（RTK等）、送信機が設定した出力、受信側RSSI、端末ID、時刻、PHY、未受信窓**を併記。申告RIDを真距離教師に流用しない。

## 5. 研究判断

**公開されている実測データはあるし、実測BLE値を解析して使うこともできた。ただし今回の主題に最も近い「実ドローンRemote IDのRSSI・3D真位置・フレームごとの送信電力真値」データではない。** したがって、この結果を論文の*実機検証*と呼んではならない。次段階はA2G実測CSVから伝搬パラメータを推定して、Bluetooth Remote ID実測と分離しつつ評価すること。
