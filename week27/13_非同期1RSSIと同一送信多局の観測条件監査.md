# PR3：非同期1RSSIと同一送信多局の観測条件

2026-11-08。PR1・PR2の実行成功後に着手。PR2のコードコミット`0ff7c9fe`はActions 6 runが全て成功し、全6 jobのログも確認した。実測データトラックではなく、Issue #70の**OMNeT++/INETシミュレーション**である。

## 今回確認したこと

1. 別時刻・別パケットから1RSSIずつ選ぶ履歴と、同じ物理送信を2〜5局が受信した記録を分離できる。
2. 1時間間隔・1000送信を、実際のシミュレータ時刻で生成できる。時刻ラベルの付け替えではない。
3. 任意の送信電力を許す1RSSI条件には数学的に非識別な世界があるため、無条件の位置正当性判定は`UNDETERMINED`にする。

**今回は観測条件と入力の監査まで。FPR/TPR・検出器の性能は未評価。** `UNDETERMINED`は数値実験から学習した結果ではなく、非識別条件を守るための判定規則である。

## 実行条件と結果

正本：[設定](results/uli-net-sim-observations-20261108-full-b/configuration.json)、[実行集計](results/uli-net-sim-observations-20261108-full-b/summary.json)、[観測条件別CSV](results/uli-net-sim-observations-20261108-full-b/view-metrics.csv)。

| 項目 | 実行した内容 |
|---|---|
| seed | 2170、1seed。24ケースは独立20seedではない |
| ケース数 | 固定／一様／有界slew／適応 × 10秒／300秒／3600秒 × 正常／X方向100m変更 = 24 |
| 送信 | 各1000 enqueue・1000 PHY TX、合計24,000 |
| 受信 | 固定5局、合計120,000成功。この条件では欠測なし |
| 真の運動 | 合成の円運動、速さ3m/s、高さ40m、半径80m |
| 電波 | PR2と同じFreeSpace・Dipole・背景雑音−100dBm、追加干渉なし |
| 実時刻の監査 | intended enqueue時刻との最大差0秒 |
| 運動の監査 | 各時刻のCircleMobility解析式との最大差約1.17e-9m。実機測位精度ではない |
| 出力 | TX/RX/GCSのCSV、観測Parquet、入力制限済みJSON、判定CSV、実ログはignored captures/ |

10／100／1000件は、同じ1000件実行のprefixであり、3回の独立実行ではない。360行の観測条件集計も360回の独立試行ではない。

### 1時間差の意味

1000件・3600秒間隔では、実TX時刻は0.1秒から3,596,400.1秒まで進む。モデル時間で999時間、約41.6日になる。これは、定常な伝搬モデルで疎な証拠を生成するための時間軸であり、連続飛行・バッテリー・昼夜の環境変化・長期同一機体IDを再現したものではない。

規格通りの短周期RID送信全てを生成したのでもない。観測対象となる疎な送信を実際に生成している。`updateInterval=0`は周期的な表示用の移動更新を止める設定であり、位置を固定する設定ではない。上流`MovingMobilityBase::getCurrentPosition()`は要求時に更新し、CircleMobilityは現在のシミュレータ時刻から位置を計算する。上記の解析式検査でも移動を確認した。

## 観測方式を混ぜない

| 方式 | 採用するデータ | 今回の出力 |
|---|---|---|
| 本来条件：非同期1RSSI | 送信ごとに受信局を順番に1局選択。常に別packet ID。選択局が欠測でも別局へ置換しない | 自由電力では全件UNDETERMINED。スコア/FPR/TPRはnull |
| 比較対照：同一送信多局 | 同じrun＋物理packet IDに属する成功観測のみ。2/3/4/5局subset | DRSS入力可能件数、4局以上のMLAT入力可能件数。検出性能は未評価 |

今回の5局は1つの合成配置の入れ子subsetであり、局数と配置の効果を分離していない。4局という数は未知3D位置＋電力の4変数に対する既存MLAT入力要件にすぎず、一意性・頑健性・安全性を保証しない。

実行ごとのpacket ID空間を分離し、異なるrunで同じ数値のpacket IDが出ても結合しない。同じserialや申告時刻の近接で同一物理送信を作らない。受信時刻と申告時刻も区別し、申告時刻を認証済みのTX時刻やToFとして扱わない。

## 数学的な反例はRF実行と別

[基本反例](results/uli-net-sim-observations-20261108-full-b/math-counterexamples.json)と[追加反例](results/uli-net-sim-observations-20261108-full-b/additional-math-counterexamples.json)を別ファイルにした。

`R_k=P_k-L(p_k,a_k)+b_k+ε_k`に対し、別の真位置`p'_k`と

`P'_k=P_k+L(p'_k,a_k)-L(p_k,a_k)`

を選べば同じRSSIを説明できる。両世界で同じ申告位置を送る場合、一方が正常でも他方は偽装となり得る。

- 距離4倍・n=2：必要な補償は約+12.0412dB。10／100／1000／5000件で数値差が丸め誤差の範囲に収まる。
- 速さ3m/sの円運動と、それを水平100m平行移動した別の滑らかな軌跡：選択受信局に合わせて各送信電力を変えれば、1000件のRSSIが一致する数学的構成を確認。非識別性は不連続なテレポートだけが原因ではない。
- 同じ半径の円周上に4受信局を置く対称配置：高度80m／20mと約−2.176dBの電力差で全局のRSSIが一致する理想log-distanceの反例。実行した5局INET配置そのものの結果ではない。

これらは**数学的なRSSIモデルの構成**であり、2つ目のRF世界を実行した意味ではない。有限の電力範囲・復号・干渉・認証済みToFまで同値と実証していない。

また、実行した適応モデルは**基準受信局0を知る±10dB制限付き補償**であり、順番に選ばれる全受信局へ毎回最適補償する最強攻撃ではない。数学的な自由電力の反例と、この有界・固定基準局の実行結果を混同しない。

## データ漏洩を避ける入力境界

`observations.py`のdetector projectionは、真位置、送信電力、攻撃ラベル、case名、seedを除去する。run名は不透明な名前空間へ変換し、packet IDの照合用メタデータとしてのみ扱う。将来のスコア関数はRSSI・受信局位置・申告位置等の明示的な観測入力だけを使い、IDやメタデータを学習特徴にしない。

観測者GPSや時刻の正しさは別の信頼仮定であり、V2の署名検証や、このシミュレータがセンサ真値・DRIP・観測ハードを認証するわけではない。

申告位置は受信成功時のpayloadログからのみ投影する。未受信行にTX ledgerの申告位置があっても検出器には渡さない。未受信のTX ID・送信母数は評価用のoracleメタデータであり、受信ノードが実運用で知る情報として特徴量に使わない。

## 大容量化で停止した試行

最初のfull-aは、長い時間軸に対して無関係なqueue incoming/outgoing rate統計が大量に出力され、約10.6GBに達したためrunnerを終了コード143で停止した。[停止記録](results/uli-net-sim-observations-20261108-full-b/resource-abort.json)。4ケースのみ監査完了で、以後を完了扱いしない。元の大きなファイルも削除せず保持している。

物理モデル・MAC・移動を削除せず、統計レコーダだけを無効化し、TX/RX/GCS/PHYの直接ベクトルは全て記録する構成へ変更した。[before/after対照](results/uli-net-sim-observations-20261108-full-b/logging-control.json)では、10件・1時間差の送受信機会・RSSIが一致した。full-bの全24ケースは約165MiB（du表示）で完走した。

今後は各sceneの出力128MiB・空き8GiBを監視し、超過すれば自分の子プロセス群だけを停止して証拠を残す。パーサにもサイズ上限を設け、巨大ファイルを成功のために黙って無視しない。

## 再現

```sh
.cache/issue70/python/bin/python experiments/week27-rid-sim/scripts/run_observations.py \
  --smoke --raw-dir captures/issue70-observation-smoke-NEW \
  --out week27/results/issue70-observation-smoke-NEW
.cache/issue70/python/bin/python experiments/week27-rid-sim/scripts/run_observations.py \
  --raw-dir captures/issue70-observation-full-NEW \
  --out week27/results/issue70-observation-full-NEW
python3 -m unittest discover -s experiments/week27-rid-sim/tests -v
```

残件：正常ケースだけによる学習・校正、独立seedでのFPR/TPR・保留・受信率比較、KF/MLAT等の入力条件確認、30mシナリオ、定量グラフ（PR4）。未実行の性能値は作らない。

ローカル検証：専用43件、既存UAV61件、Go、contracts48件が成功。専用テストには別パケット／別runの拒否、truth非投影、未受信payload非投影、非識別反例、出力予算による子プロセス停止を含む。
