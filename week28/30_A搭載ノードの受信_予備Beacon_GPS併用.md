# A搭載ノード：受信・予備Beacon・GPS/BME280の併用

2026-11-14実施。研究用PoC。ZKP、DRIP、機体認証、センサ真正性の証明を行わない。
実ドローンの受信確認と、Pi同士の識別用Beacon実験を区別する。

## 構成

Aはドローン搭載用。以下を別サービスとして有効化する。

- `zkp-rid-observer.service`：Wi-FiのRID候補を受信し、時刻・RSSI・生Vendor IE・解析結果をJSONL/TXTへ記録。
- `zkp-flight-sensors.service`：USB GPSとBME280を記録。GPSのMSL高度・ジオイド分離・楕円体高を区別し、気圧高度も別フィールドに保持。
- `zkp-flight-marker.service`：専用の研究用 `PI-RID-*` を予備Beaconとして送信。GPS有効時は位置を含め、無効・古い場合は位置を捏造せずIDのみ送信。

ドローンの申告IDとPiの研究IDは別々に扱う。既存の`receiver_sources.json`を上書きしない。
ラベルは操作者の分類であり、受信IDだけでDJI機や機体真正性を認証したことにはならない。
B・Cは完成済みとして設定・デプロイを変更していない。今回の確認時は取り外されていた。

## 実機試験

Aで既存のGPS記録・予備送信を継続し、DからLocationなしの識別用Pi Beaconを50秒間送信。
Aでは同一チャネル2452MHzを対象に30秒間受信した。

| 項目 | 設定・結果 |
|---|---|
| Aのポーリング | 0.25秒 |
| Aのスキャン要求 | 0.5秒間隔、2452MHz限定 |
| スキャン要求／受理／失敗 | 59／59／0 |
| 新しい解析済みRID記録 | 59件 |
| RSSIあり／なし | 59／0件 |
| 更新間隔中央値／95百分位 | 約0.509秒／0.513秒 |
| 最大更新間隔 | 約0.526秒 |
| A受信終了コード | 0 |
| D送信 | 時間制限で正常終了、一時AP削除確認 |
| AのGPS・予備送信 | 試験後も両サービスactive |

これはLinuxの受信キャッシュ更新の評価であり、59個の独立した無線パケットを識別した値ではない。
Dの送信は合成IDによる実電波試験。Matrice 300/350からの受信試験ではない。

失敗も記録した。最初の試験ではDにhostapdがなく送信失敗。依存導入後の再試験では、残存する一時領域の再利用拒否、長い実験IDによるSSID長超過により送信失敗した。
それらの試行のA受信0件を、成功や無線受信能力の限界とは扱わない。
既存領域を削除せず、短い一意な実験IDで最終試験を実施した。各試行のログは非公開capturesに保持。

Dを新しい受信releaseへ更新後、AのGPS付きBeaconを71件受信した。直近のA送信内容と一致する70件すべてに、位置・RSSI・GPS高度・気圧高度が存在することを確認した。これは同じVendor IE内容の一致であり、物理的な同一パケットを識別したという意味ではない。

匿名化した集計：[summary.json](results/a-dual-role-20261114/summary.json)。実座標や生受信は含めない。

### 自動起動用adaptive設定での追試

固定チャネルの一時受信を終了し、実際の`zkp-rid-observer`サービスを動かしたまま、Dから別の時間制限付きBeaconを40秒送信した。Aは別IDの新しい受信記録90件を保存し、全件でRSSIを確認した。センサ・送信・受信の3サービスはいずれもactive。Dは試験終了後に受信へ戻した。

ただし、送信源のない探索期間に完了した60秒セグメント3本では、各35要求中9受理・26失敗が記録されている。全チャンネル探索と短い要求周期の共用無線競合が残るため、0.25秒の要求周期を受信更新周期と同一視しない。この要求失敗割合をRFパケット損失率と呼ばない。今回の併用確認によってスキャン競合が解決したとは主張しない。

## 起動設定と再現

Aの3サービスをenabled/activeとして確認した。物理的な電源再投入による確認は未実行。

```sh
python3 experiments/field-kit/build.py --output .cache/field-kit-new
# 作成したキットをAへ転送後、Pi上で実行する
python3 field-kit-new/install_pi.py --kit field-kit-new \
  --node-id observer-a --role dual --activate
systemctl is-enabled zkp-rid-observer zkp-flight-sensors zkp-flight-marker
systemctl is-active zkp-rid-observer zkp-flight-sensors zkp-flight-marker
```

`dual`はA専用。送信・センサ起動後に既存の受信インストーラを呼ぶ。
既定の`transmitter`は従来どおり受信停止の構成を維持する。
版管理した新releaseへ配置し、旧release・収録・設定を保持する。
受信は自動起動時に0.25秒の要求と全チャネル探索を含むadaptive設定を使う。
上表の同一チャネル0.5秒試験と同じ条件ではない。

## 制約

内蔵Wi-Fi一系統をAP送信とスキャンで共用する。他チャネル探索中のBeacon中断、送受信欠落、混雑や距離による性能低下は未評価。
3サービスがactiveでも無欠損の同時送受信を保証しない。安定性が必要なら対応USB Wi-Fiなどで無線系統を分離して評価する。
スマートフォンの登録・DB・権限設定は今回変更していない。実DJIとPiの同時受信、長時間・飛行中・電源再投入の確認は今後の実験。
生受信、実座標、個体ID、設定、認証情報はGitに含めず、owner-onlyのcapturesに保存する。

## ローカル検証

- Pi Pythonテスト：52件成功（送受信併用時のサービス順序、従来送信専用動作を含む）。
- キット検証：2件成功（A以外へのdual指定拒否を含む）。
- UAV Python：88件成功。
- aggregator Go：全パッケージ成功。
- contracts：48件成功。
