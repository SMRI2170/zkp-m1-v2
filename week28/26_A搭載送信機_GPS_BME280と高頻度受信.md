# A搭載送信機：GPS/BME280と高頻度RSSI受信

## 実施結果

2026-11-13、Aを研究用Wi-Fi Beacon送信機、B/Cを受信機として実機導入した。AのBME280計測と送信、B/CでのRSSI・申告ID・元Vendor IE・時刻の保存を確認した。Aは電源投入時にセンサーと送信サービス、B/Cは受信サービスが起動する設定になっている。今回の役割変更後のOS再起動・屋外飛行・管理APなしでのコールドブートは未実施。

**GPSは未完了。AにUSB GPSが見つからず、実機GPS位置・GPS高度・GPS付きLocationの空中受信は未確認。** 現在はBasicIDのみ配信し、架空の座標は送らない。BME280の気圧・高度は取得・保存中。GPSが有効になれば位置とGPS楕円体高度・気圧高度をLocationに載せるコードと合成入力の往復テストは実装済み。

これは研究用PoCであり、DJI Remote IDの代替・航空機認証・位置やセンサーの真正性を保証するものではない。V2の観測者署名検証や申告RIDのグループ化とも別段階であり、今回ZKPは実行していない。

## 構成と実測

| ノード | 役割・導入状態 | 設定と観測結果 |
|---|---|---|
| A / Pi 4 | センサー・研究Beacon、enabled/active | BME280 bus1/0x76、チップID0x60を実読。USB GPSなし。受信サービスはdisabled/inactive |
| B / Pi 4 | 適応走査受信、enabled/active | Aの申告ID+BSSIDに一致したRSSIを保存、role=onboard_pi |
| C / Pi 3B+ | 適応走査受信、enabled/active | 同じ送信機を受信、role=onboard_pi |
| D | 以前の受信版 | 今回オフラインで未更新 |
| E以降 | 未導入 | 接続先と実機対応を確定できていない |

Aの最終導入版は`flight-4ce3d39abb3d`、B/Cは`flight-52f17b67f1e0`。B/Cへの最後の変更は、管理Wi-Fi未接続でもインターフェースが管理上UPなら受信を試行する起動判定。rfkill解除・強制接続・モニターモード・管理チャネル変更はしていない。

完了済みの約60秒セグメントを各1つ回収して集計した。異なるセグメント・異なる機材の探索計測であり、同時送信パケットの対応付けや反復による統計比較ではない。

| 対象 | 有効サンプル／新規更新数 | 間隔中央値 | 最大間隔 |
|---|---:|---:|---:|
| Aのセンサー記録 | 300（BME全件有効、GPS 0件有効） | 0.200秒 | 0.203秒 |
| Bの新規RSSIキャッシュ更新 | 166 | 0.277秒 | 3.868秒 |
| Cの新規RSSIキャッシュ更新 | 115 | 0.388秒 | 3.968秒 |

Bは受信167行・172回の対象周波数要求・2回の広域要求、Cは116行・121回の対象周波数要求・2回の広域要求。新規RSSIは、実行開始以降のカーネル時刻を持ち、RSSIがあり、古いキャッシュでない、AのID+BSSID一致行の重複時刻を除いた数。**全無線パケット数・受信率・損失率ではない。** 全チャネル探索とbusy待機により長い間隔も発生する。

Aは既存2.4GHz管理接続と同じチャネルでAPを作成。最終状態では設定・カーネル報告とも2452MHz/ch9。送信内容更新0.2秒、Beacon 100TU（約102.4ms）は設定値であり、実測した空中フレーム間隔ではない。`hostapd_cli set vendor_elements`に続けて`update_beacon`を呼び、両方のOKを確認する。受信側でもcounterが変化した。

集計：[JSON](results/pi-flight-20261113/summary.json)／[CSV](results/pi-flight-20261113/intervals.csv)／[ハッシュと導入版](results/pi-flight-20261113/source-manifest.json)。別の先行セグメントではBME301件、Bの更新中央値約0.28秒、C約0.39秒も観測したが、表には回収した最終版の1区間のみ採用した。

## 高度の扱い

| 保存項目 | 基準・意味 | 今回の検証 |
|---|---|---|
| GPS MSL高度 | GGAの平均海面基準高度 | 合成NMEAテストのみ |
| GPSジオイド差 | GGAの楕円体−MSLの差 | 同上、欠ければ楕円体高度は欠測 |
| GPS楕円体高度 | MSL高度＋ジオイド差 | 同上、ODID AltitudeGeoに使用 |
| 気圧高度ISA | 1013.25hPa基準の近似圧力高度 | BME280実測から算出、AltitudeBaroに使用 |
| 起動時相対高度 | 初回有効気圧を基準とする圧力換算差 | 実測から算出。離陸点高度ではない |

GGAはchecksum、Fix、範囲、鮮度2秒を検査。ホスト時刻とGPSの時刻を別に保存する。GPSが古い・ない場合はLocation自体を送らず、BMEをGPS代用にしない。速度・方位・飛行状態・精度は未測定として符号化。気圧高度は気象、ローター風、搭載位置に左右され、真の地上高の証明にはならない。

以前のGPSはUSB ACMデバイスだったが、今回ACM/USBポートは存在しなかった。GPIOのserial0はOSコンソールとgettyが使用しているため変更していない。USB GPSは接続後に自動再探索するが、受信機の実際の通信速度・NMEA出力・屋外Fix取得は要確認。既定9600bps。

ODID高度の標準unknownはwire値0。旧パーサのFFFF欠測互換は維持しつつraw値と互換注記を残した。新送信機はunknown高度にFFFFを使用しない。既存受信パーサの互換性上、FFFFの最大高度を扱う場合はraw値の確認が必要。

## ドローンと搭載Piの区別

Aは専用の`PI-RID-`研究セッションIDとBSSIDを使用し、B/Cの非公開設定へ両方の一致条件で登録した。観測JSONLの`source_annotation`、`claimed_uas_ids`、`bssid`、テキスト行のsourceに区別を残す。テキストにはデコード結果・生Vendor IEも保存する。

実ドローンのIDは未取得なので、未知のIDをDJI機と断定しない。M300/M350の電源を入れて実際のID/BSSIDを確認後、READMEの`register_source.py --role drone`で別登録する。登録は自動識別の注釈であり、ID/MACのなりすましを防がない。今回確認したのはAのBeacon受信であり、DJI実機との同時受信・DJIとの完全な規格互換・BLE/NAN受信は未評価。

## 権限拒否と高頻度化

1. Bの通常シェルはUID1000、実効capabilityなし。直接`iw ... scan trigger`はOperation not permitted (-1)、終了255となった。
2. 受信サービスはUser=pi、CAP_NET_ADMINを持つ。NoNewPrivilegesを維持した権限限定の期間試験でも同じ周波数のscan triggerが終了0になり、権限構成が原因ではないことを確認。
3. 旧全チャネル試験の失敗は主にbusy。要求32回中24回busyだった。権限拒否とは分けて記録し、busy時の1/2/4/5秒待機・連続失敗時の停止を維持した。
4. Bのiw出力は`freq: 2452.0`。整数専用の旧パーサでは周波数を学習できず、全チャネル探索のままだった。整数相当の小数表記を正規化し、2452.5のような値は丸めず拒否するテストを追加。
5. B/Cは0.25秒要求・0.25秒キャッシュ読取り。新鮮な観測から得た最大4周波数を優先し、30秒ごとに全チャネル探索、学習90秒TTL。Aと異なる周波数の実ドローンを探す機会を残す。

brcmfmacの公開対応モードにmonitorはなかった。権限を増やしてもドライバのbusyやAPIのキャッシュ性は消えない。今回の最短値を、すべての機材・電波条件での最適値や保証速度と評価しない。

## 保存・資源・再現

センサー／送信は60秒でJSONLを区切り逐次flush、受信も60秒ごとに保存。owner-onlyの各release/capturesへ保存し、新releaseで旧データを削除しない。突然の電源断直前の永続性は保証しない。

| サービス | 権限 | 上限要求・停止条件 |
|---|---|---|
| センサー | pi、dialout/i2c、capabilityなし | MemoryMax96MiB、CPU50%、収録192MiB |
| 送信 | pi、NET_ADMIN/NET_RAW、既存STAは保持 | MemoryMax96MiB、CPU50%、収録128MiB |
| 受信 | pi、NET_ADMIN | MemoryMax160MiB要求、子RLIMIT_AS128MiB、収録256MiB |

いずれも所有ファイル数・空きディスク等のガードあり。cgroup memory controllerが無効な環境ではMemoryMaxの実効性は別確認。RSSI速度測定からメモリ上限の実効性を主張しない。udevの除外は専用ridtx0のみで、既存Wi-Fiプロファイルやsudoersは変更していない。

原始ログ・個体ID・送信BSSID・位置・詳細時刻・セッション情報は非公開の`captures/pi-flight-20261113/`。最終回収分は`final/`。Gitへ追加しない。センサーCSVも同ディレクトリに生成済み。

```sh
# 回収済みprivateデータから匿名集計（出力は新規パス）
python3 experiments/week28-beacon-observers/analyze_flight_capture.py \
  --input captures/pi-flight-20261113/final \
  --output week28/results/new-flight-run/summary.json
# センサーCSV（位置等を含むためprivate出力のみ）
python3 experiments/week28-beacon-observers/export_flight_sensors.py \
  --input captures/pi-flight-20261113/final/sensor-complete.jsonl \
  --output captures/pi-flight-20261113/final/new-sensors.csv
```

[検証記録](results/pi-flight-20261113/checks.md)：Piテスト44件、既存UAV88件、Go、contracts48件成功。GPS入力・高度基準・欠測・鮮度切れ・ODID往復は合成テスト。実機試験とは区別する。

初回転送はSSH control socket期限切れで転送前に失敗し、再認証後に導入。更新待ちの未完成区間からの回収も失敗したため、完成した区間を待って回収した。初期版のAP設定と管理接続の再接続でチャネルのメタデータが不一致になり、最終版では管理接続の待機と設定値／カーネル実値の分離・定期確認を追加した。失敗時の旧ログは保持。

## 残件

- AへGPSを接続し、実際のFix・MSL/楕円体高度・LocationをB/Cで受信確認する。
- M300/M350の実機IDを確認して別登録し、Piとの同時記録を試験する。
- 管理APなしの起動、屋外持続運転、電池・搭載振動・風圧・高度の独立真値を評価する。
- Dの更新と追加ノードの同定。機材間の同一送信対応・RSSI校正・方向推定は別途必要。

## 参照

- [OpenDroneID core-c（固定版）](https://github.com/opendroneid/opendroneid-core-c/tree/849c03adbe0cdd68997a462fafab397edcfe53f3)：Locationの高度・unknown・速度等の符号化。
- [OpenDroneID transmitter-linux wifi_beacon.c（固定版）](https://github.com/opendroneid/transmitter-linux/blob/6852afd0d4bed0d139b9dac3cd3a45eb595e30f0/wifi_beacon.c)：Vendor IE更新とUPDATE_BEACON。
- [Trimble GGA仕様](https://help.fieldsystems.trimble.com/r750/nmea0183-messages-gga.htm)：MSL高度とジオイド差。
- [Bosch BME280 datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf)：気圧センサーの特性。
