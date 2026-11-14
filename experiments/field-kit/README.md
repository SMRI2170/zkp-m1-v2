# 現地実験用の移行・ビルドキット

研究用PoC。ZKPなし。機体・位置・観測ハードの認証やDRIPを提供しない。
既存のPi収録やAndroid DBを削除せず、新しい機材へ導入できるコードとAPKを用意する。

## ビルドするPC

Python 3、JDK 21、Android SDK 36 / build-tools 36.0.0、adbを用意する。
`experiments/kmp-rid-observer/local.properties`（Git対象外）でSDKを指定する。

```sh
python3 experiments/field-kit/build.py --output .cache/field-kit-new --build-android
adb devices -l
# 実際のPixelの端末IDをDEVICE_SERIALへ置き換える
adb -s DEVICE_SERIAL install -r .cache/field-kit-new/rid-observer-debug.apk
```

出力：Piソースtar.gz、Android再ビルド用ソースtar.gz、debug APK、Piインストーラ、ソース／ファイルのSHA-256 manifest、ビルドログ。
生受信・座標・DB・設定・個体ID・署名鍵・local.properties・ビルドキャッシュは同梱しない。
APKはテスト用debug署名。既存アプリと署名が違う場合は更新できないため、アンインストールでDBを消さず書き出し・署名を確認する。
このmanifestは転送の整合性確認であり配布者の署名ではない。

## Raspberry Piへ移行

Pi OSの一般ユーザーpiを想定。Python 3.9以上、iw、systemd、sudoが必要。
Aの送信役にはhostapd/hostapd_cli/ipとPythonのserial・smbus2・bme280、I²C設定が必要。
不足依存はインストーラが列挙して停止する。OS・Wi-Fi・SSH・sudoers・パッケージを勝手に書き換えない。

キットをPiへコピー後（認証情報はファイルに書かない）：

```sh
# 検証して配置するだけ。currentやサービスは変更しない
python3 field-kit-new/install_pi.py --kit field-kit-new --node-id observer-b
# 新しい収録セッションとして明示的に有効化
python3 field-kit-new/install_pi.py --kit field-kit-new --node-id observer-b --role receiver --activate
# Aだけを研究Beacon送信＋GPS/BME280記録にする
python3 field-kit-new/install_pi.py --kit field-kit-new --node-id observer-a --role transmitter --activate
```

毎回別releaseを作り、旧release/capturesとconfigを保持する。収録上限に達した際の自動削除・自動ロールオーバーは行わない。
有効化は既存サービスを更新しsudoを要求する。activateなしは検証のみで無線を動かさない。
新規ノードの送信元登録は実際に観測したID/BSSIDで行い、古い鍵や観測ログはコピーしない。

標準はOpenDroneID候補を保存。解析失敗でも元Vendor IE、RSSI、時刻、理由を残す。
未知方式を調べる場合は明示的な候補保存を使う。一般Wi-FiをRIDやDJI機と断定しない。

```sh
# 通常受信を停止した明示的な時間制限付き実験で、全Wi-Fiの候補も残す
~/zkp-beacon-observer/run --duration 60 --include-unknown-wifi
# 回収済みJSONLをCSV／JSON配列へ（新しいowner-private captures出力）
python3 experiments/week28-beacon-observers/export_observations.py \
  --input captures/session/observations.jsonl --output captures/session/observations.csv
python3 experiments/week28-beacon-observers/export_observations.py \
  --input captures/session/observations.jsonl --output captures/session/observations.json --format json
```

これもスキャンキャッシュであり、生パケット全数や失敗したIEをOSから復元できる機能ではない。
Piの受信局位置は現地で別途管理する。未設定の受信局位置をゼロ座標として保存しない。

## Androidの現地操作

主対象はGoogle Pixel 8。API30以降の公開APIを基本とし、他社Androidへの移行時は診断CSVと実受信試験で確認する。旧ASUS等のAPI24経路は補助互換であり主対象ではない。

1. 更新インストール後、アプリ内の初回説明で「権限を確認」を選び、OSの許可画面へ進む。Wi-Fi・位置情報サービスも有効化。許可だけでは受信は開始しない。
2. 「受信開始」。継続通知付きForeground Serviceが受信・自位置記録・SQLite保存を担当。
3. 自位置はGPS/networkへ1秒間隔を要求。実効頻度はOSと測位環境依存。「測位待ち」や精度を確認する。
4. 必要時だけ「未解析のWi-Fi保存」をON。周囲のBSSID/RSSI/Vendor IEも保存する。SSIDは保存しない。
5. 「受信停止」→保存待ち0を確認→「書き出し」。保存先にダウンロード等を選ぶ。
6. DB明細CSV／DB全件JSONL／自位置履歴CSV／診断CSVを取り出せる。追加ログの「記録開始」は必須ではない。

スマホの測位時刻とWi-Fi観測時刻を同じelapsedRealtime基準で照合し、±2秒以内のみ対応付ける。
古い観測・測位なし・模擬位置を記録し、現在位置を過去の受信位置として埋めない。
CSVの距離はRID申告位置とスマホ位置の水平距離。30m分類はスマホ精度だけを考慮した参考値で、RID側の誤差は未知。
実験の真の30m離隔や不正・安全を証明しない。独立した現地距離測定と照合する。

Kotlin/KMPのネイティブForeground Serviceを継続使用する。言語を変えてもAndroidの権限・スキャン制限・Doze制約はなくならない。
標準Wi-Fi要求は30秒。対応端末の既存の開発用モード以外では制限を解除しない。
OSからIEを取得できなければ、取得できたメタデータと欠測理由を残し、元の電波文字列を復元したとはしない。
