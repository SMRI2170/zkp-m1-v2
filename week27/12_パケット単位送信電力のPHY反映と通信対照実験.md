# PR2：パケット単位の送信電力とPHY反映

2026-11-08。Issue #70のPR1で正常／既存偽装の実行とコードコミット`d01cc3e`のCI 6 run成功・全ログ確認を終えてから着手した。**全てOMNeT++/INETシミュレーション。実測RSSIへの加算ではない。位置偽装検出器は未実行。**

## 実装と観測量

上流SHA・OMNeT++・INET・EigenはPR1と同じ。上流のcheckoutは変更していない。独自のC++/NED拡張をローカルビルドに追加し、各Beaconの`SignalPowerReq`へW単位の電力を設定した。INETの既存電力パラメータは実行中変更不可であり、その制限を解除していない。

`createTransmission()`フックで、PHYのpacket tree ID、送信時刻、電力タグの有無、`computeTransmissionPower()`の値を記録する。要求値とPHY値を照合し、届かなければ失敗する。PHY記録と受信強度・受信成否の両方を検査するため、要求値をログに書いただけのテストではない。

元の`StaticLocationSpoofer`とは別の独自拡張で、基底のRID生成処理を呼んでから位置だけを変更する。受信ログでserial=1を確認し、正常のIDを別IDへ書き換えて検出しやすくすることを避けた。

管理層enqueue時刻・真位置は全ケースで同じモデル。イベント数の違いによるLinearMobilityの丸め差が最大約`6.0e-11 m`あったため、軌跡一致の検査は`1e-8 m`／時刻`1e-12 s`の数値比較とし、実差分を集計へ保存する。これは検出閾値や物理位置の許容誤差ではない。1mmの軌跡差は拒否するテストを追加した。

## 固定した条件

- macOS arm64、16 GiB、Python 3.12、seed 2170、4秒、対象UAVのenqueue 8件、受信専用2局。
- INET 4.5.4のFreeSpacePathLoss／DimensionalRadio／DipoleAntenna、channel 6、背景雑音−100dBm。実環境のマルチパス・遮蔽を校正したものではない。
- 位置偽装は水平X方向に100mの固定オフセット。PR4の30m／方向・高度掃引は未実施。
- 追加送信機は観測者ではなく、通信への干渉・媒体アクセスの対照。対象packet IDだけを評価対象にし、元の全ベクトルは保持する。
- `SignalPowerInd`欠落はnull。送信電力・真位置・攻撃ラベルはtruth-onlyで、検出器へ渡していない。

| 電力モデル | 設定と攻撃者の知識 |
|---|---|
| A 固定 | 公称13dBm、飛行中固定。検出器による推定は未実行 |
| B 確率変動 | 各パケットIID一様±3dB、専用RNG stream 1 |
| C 大変動・有界 | ±10dB範囲のランダムウォーク、変化幅は最大2dB/packet。8件で全範囲を観測した意味ではない |
| D 適応・有界 | 基準局の合成座標・真／申告位置・n=2を知り、`ΔP=10n log10(d_true/d_claim)`。±10dBで制限し、物理出力も−80〜23dBmへclamp。受信結果のフィードバックなし |

Dは白箱の合成攻撃であり、数学的な無制限出力とは別である。未知一定電力と毎送信任意電力の識別可能性比較はPR3で扱う。

## 実際の結果

正本：[集計JSON](results/uli-net-sim-power-20261108-h/summary.json)／[CSV](results/uli-net-sim-power-20261108-h/case-summary.csv)。全14ケースは実行終了コード0で、全対象112 enqueueに対応する112 PHY送信を確認した。位置偽装の検出率ではなく、通信制御の確認である。

| ケース | PHY TX | 受信成功／16機会 | 内容 |
|---|---:|---:|---|
| FixedNormal／PositionOnly | 各8 | 各16 | 固定電力・正常／位置だけ変更 |
| UniformNormal／UniformSpoof | 各8 | 各16 | 同じ確率電力系列、正常／位置変更 |
| SlewNormal／SlewSpoof | 各8 | 各16 | 同じ有界電力系列、正常／位置変更 |
| AdaptiveSpoof | 8 | 16 | 有界の適応補償。検出性能は未評価 |
| HighControl | 8 | 16 | 固定19dBm、基準から+6dB |
| AllLow | 8 | 0 | 固定−80dBm。実送信されたが正常受信なし |
| AlternatingNormal | 8 | 8 | 各パケットで13／−80dBmを交互指定 |
| InterferenceLow／High | 各8 | 各16 | 可視の追加送信機。受信件数は変わらず、対象の平均媒体アクセス遅延は0→約0.164ms |
| HiddenInterferenceLow／High | 各8 | 16→12 | 弱い対象リンクと50µs先行する別送信機。隠れ端末を意図した配置だが、厳密なCCA/SNIR監査は未実施 |

受信成功時だけRSSIを集計する。8/16や12/16は全対象PHY送信×2局に対する成功割合であり、正常／偽装分類のTPRではない。追加送信機の全送信件数を対象UAVの送信母数へ混ぜない。[対入力監査](results/uli-net-sim-power-20261108-h/paired-input-audit.json)では固定／一様／有界系列の正常・位置偽装ペアの申告ID・申告時刻・電力系列の一致も確認した。

### +6dBとRSSI差の違い

`ReceiverBase::computeSignalPower()`は、今回のINET 4.5.4では受信区間のsignal-plus-noiseの最小電力を返す。孤立した単一送信・一定背景雑音の対照では、線形電力を使って

`R_high = 10 log10((10^(R_base/10) - 10^(N/10)) * 10^(6/10) + 10^(N/10))`

と予測できる。実際の平均RSSI差は**5.999256dB**、この式との最大誤差は約**5.3e-13dB**。これは同じシミュレータ内の整合確認であり、実機の校正精度ではない。

従って、このRSSIから欲しい信号だけの電力を無条件に読み取ったり、低SNR・干渉下でもdBm差で送信電力が厳密に消えると仮定したりしない。既知雑音を差し引ける条件と、未知雑音・干渉の条件を分ける必要がある。

## 失敗を含む実行履歴

途中の出力は削除・上書きしていない。公開する[試行記録](results/uli-net-sim-power-20261108-h/attempts.json)には実際の終了コード・監査失敗・未実行ケースとログハッシュを残す。

- a：NEDのsimple／compound種別不一致で起動失敗。型宣言を訂正。
- b：実行中に不変の電力パラメータを書き換えようとして拒否。mutableへ変更せず、パケットタグで指定。
- c：PHYベクトルが初回呼び出し元RadioMediumの文脈で登録され、PHY監査が失敗。送信機初期化で明示登録した。旧case.statusはSIMULATION_FAILEDだが実行終了コード0で、失敗したのは監査である。
- d：追加送信機も受信を報告していたため観測者集合と不一致。観測者0/2と追加送信機3の役割を明示し、後者のGCS転送を無効化。元のベクトルは保持。
- e：1イベント内の複数GCS呼び出しでベクトルが重複し、曖昧な結合を拒否。明示callback_idと全フィールドの同数検査を追加。カウンタなし・欠けたフィールドは依然として拒否する。
- f：同じ軌跡の丸め差をビット単位の比較が拒否。実差分を調査し、上記の数値比較へ修正した。
- g：RSSI差を厳密な+6dBと誤認した検査が失敗。INETの雑音込みの定義を確認し、物理式による予測へ訂正。許容誤差を広げていない。
- h：14ケースとPHY／受信対照の監査が成功。

## 再現と残件

```sh
bash experiments/week27-rid-sim/scripts/build_power_extension.sh .cache/issue70
.cache/issue70/python/bin/python experiments/week27-rid-sim/scripts/run_power.py \
  --raw-dir captures/issue70-power-NEW \
  --out week27/results/uli-net-sim-power-NEW
python3 -m unittest discover -s experiments/week27-rid-sim/tests -v
```

生のledger／座標／Parquet／vecはignored captures/に0700／0600で保存。Gitには独自拡張・集計・ログ・テストのみを追加する。上流ソース・バイナリは再配布しない。

ローカル検証：専用テスト30件、既存UAV Python 61件、Go、contracts 48件が成功。[ログ](results/uli-net-sim-power-20261108-h/logs/)と[ケース実行記録・元vecのハッシュ](results/uli-net-sim-power-20261108-h/case-receipts.json)を保存。専用テストは合成unit fixtureであり、実際のPHY実行は別に上表のシミュレータで確認している。公開後のActionsは別途結果・ログを確認する。

PR2で確認したのは要求が実際の送信電力・RSSI・到達・媒体アクセスに反映されること。非同期の1時間差、1000件、無制約電力の反例、2〜5局比較、正常校正・FPR/TPR・信頼区間、20seed、30mリスク判定、実機、ZKPは**未実行**。PR3以降で分離して進める。
