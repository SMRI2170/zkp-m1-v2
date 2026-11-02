# RID Radio Probe：専用Android検証アプリ

新規パッケージ `org.smri.ridprobe`。既存受信アプリのインストールや改名ではなく、このリポジトリ内に作成した独立したJavaアプリ。Flutter、既存のrapidsnarkアプリ、クラウドを利用しない。

## 0.2の画面・機能

- **測定**：受信開始／停止、BLE・Wi-Fi・RID形式候補の絞り込み、対象選択、方向表示、収集進捗、受信強度グラフ。
- **記録**：端末内の測定履歴、対象名を含まない推定結果CSV、識別情報を含む電波ログJSONLの明示的な書き出し。
- **設定**：権限、Wi-Fi更新、機能確認、機器名表示、方向の校正・解除・独立データでの誤差記録。

測定画面から校正入力や技術的な数値を移した。振幅・R²等の情報は詳細から確認する。新しい外部ライブラリや権限は追加していない。

方向推定では回転を分割し、有効な2周のピーク方位差を表示する。**繰り返しの一致度は真の角度誤差ではない**。電力操作や同じ偏りによって、繰り返し良くても間違う場合がある。

## 目的と実装範囲

- BLE広告のRSSI、PHY、観測時刻を取得。0xFFFA Service DataにあるODIDの構造を検査。
- Wi-Fiスキャン結果のRSSI、周波数、時刻、Information Elementsを取得。Vendor IEの `FA:0B:BC / 0x0D / counter` 以下のODID構造を検査。
- 回転ベクトルセンサから磁北基準の端末方位を取得。各受信のelapsed realtime時刻に近い姿勢を対応付け。
- 対象ごとにRSSIと端末方位の関係を当てはめ、RSSIが最大となる端末方位を推定。
- 既知の送信方向を入力して方向補正を校正。校正データを消去し、別の回転による実測誤差を記録。
- UWB／Ranging API等の能力を照会する。Bluetooth CTEのI/Q取得、Wi-Fi CSI、位相差AoAは実装していない。

**RSSI最大の端末方位と送信元の方向は同じとは限らない。** アンテナ特性、持ち方、人体、反射によって変わる。校正前の結果を真のAoAと扱わない。校正後も精度の実測が必要。

## 推定の計算

同じBLE送信元／PHY、またはWi-Fi BSSID／周波数について、

`RSSI = a + b cos(heading) + c sin(heading) + d × elapsed_minutes + error`

を方位区画別の件数の逆数で重み付けして当てはめる。磁北基準のRSSI最大端末方位は `atan2(c,b)`。時刻項は単純な線形ドリフトの影響を減らすためのもので、任意の電力変更を除去しない。

採用条件は24点以上、8方位区画中6区画以上、角度の最大空白が90°以下（回転範囲270°以上）、振幅2dB以上、時刻項のみのモデルに対する方向成分R² 0.35以上。これらは探索用の品質ゲートであり、校正済みの信頼確率・角度誤差保証ではない。条件不足は角度0°や北向きに置き換えず「推定不可」とする。

姿勢は観測時刻と250ms以内で対応付け、信頼できない姿勢や水平から25°以上の傾きを除外。対象の受信間隔250ms未満を間引き、各対象最大1,200点。Wi-Fiの同じキャッシュ時刻は追加の推定データにしない。受信しても姿勢が不足すれば生ログに理由だけ残す。

**別時刻のRSSIを使うため、方向に相関した送信電力操作で見かけ上良い当てはめを作れる。** ホストテストはこの失敗例も含む。未知電力に対する一般的な偽装検知、機体認証、センサの正直さの保証ではない。

## ビルド

JDK 21、Android SDK 36、Gradle 9.1.0、AGP 9.0.1。minSdk31／targetSdk36。実機確認はPixel 8、Android 17／API37。

```sh
cd experiments/android-radio-probe
# local.properties に sdk.dir=/自分のAndroid/sdk を設定（Git対象外）
./gradlew --no-daemon :app:assembleDebug
sh scripts/test_math.sh
```

APKは `app/build/outputs/apk/debug/app-debug.apk`。Gradleラッパーは配布ZIPのSHA-256を固定。新規プロジェクトのbuild、.gradle、SDKローカル設定、APK、署名鍵はGit対象外。

### Wi-Fi経由でPixelへ入れる場合

ビルドはMac等のホスト側で行い、無線ADBでAPKを転送する。通常のAndroidアプリからOSのワイヤレスデバッグを勝手に有効化したり、ペアリングを省略したりはしない。

```sh
# Pixelの開発者向けオプションでワイヤレスデバッグを有効化する。
# 初回：端末に表示されたペアリング用IP:ポート。コードは対話入力。
adb pair PAIRING_IP:PAIRING_PORT
# 接続用のポートはペアリング用と異なる場合がある。
adb connect DEVICE_IP:CONNECT_PORT
adb -s DEVICE_IP:CONNECT_PORT install -r experiments/android-radio-probe/app/build/outputs/apk/debug/app-debug.apk
adb -s DEVICE_IP:CONNECT_PORT shell am start -n org.smri.ridprobe/.MainActivity
```

再試験スクリプトには `--device DEVICE_IP:CONNECT_PORT` を渡す。IP、ポート、ペアリングコードはGitへ保存しない。Android端末自体でGradleビルドする構成ではない。

ビルド時にWifiManager.startScan等の非推奨APIの注意が出る。Androidのスキャン実機診断のため公式APIを使用しており、制限や非推奨状態を隠していない。OSのスキャン制限は自動変更しない。

## Pixelでの使い方

1. 「権限」で位置情報・Bluetooth等を許可し、Wi-Fiと位置情報を有効にする。
2. 「測定」の「受信開始」。必要ならここで権限を許可すると受信を開始する。対象一覧で、十分に受信できるBLEまたはWi-Fiを選ぶ。既定では機器名を一時ハッシュに置き換える。
3. 同じ場所でスマホを水平に持ち、ゆっくり1周する。まずはBLEで試す。移動や持ち方の変更を避ける。
4. 結果は自動更新される。進捗と回転ごとの一致度を確認する。校正前の矢印はRSSI最大の端末方位。
5. 「設定」で正解の磁北基準方向を入力して「校正」。データが消去された後、別の1周で「誤差を測る」。
6. 「停止」。アプリが背景へ移った場合も停止し、停止理由を記録する。通常の手動開始には自動停止タイマーを付けない。

Wi-Fiのスキャンは一般に前景アプリでも4回／2分等のOS制限がある。35秒間隔の要求で24点を集めるには約12〜15分かかる場合があり、初回の短時間試験だけでは方向推定しにくい。プラットフォームの結果はキャッシュ・間引きを含み、全Beaconフレームの連続捕捉ではない。開発者設定での制限変更はこのアプリや実機試験では行っていない。

## 記録・再試験

アプリにInternet権限はなく、自動バックアップを無効化。生の受信識別子、IE、広告、RSSI、姿勢、校正・評価方向はアプリのprivate領域だけに保存する。USB経由で取り出したものはignoredのcaptures内、フォルダ700・ファイル600とする。

```sh
# リポジトリルートで実行。USB接続1台を対象。端末固有IDは公開出力しない。
python3 experiments/android-radio-probe/scripts/run_device_probe.py \
  --apk experiments/android-radio-probe/app/build/outputs/apk/debug/app-debug.apk \
  --output captures/NEW_RADIO_PROBE_RUN --seconds 25

# 公開してよい集計値だけを別ファイルにする（生データ・角度・対象識別子を除外）
python3 experiments/android-radio-probe/scripts/summarize_probe.py captures/NEW_RADIO_PROBE_RUN \
  --apk experiments/android-radio-probe/app/build/outputs/apk/debug/app-debug.apk \
  --output week26/results/NEW_RADIO_PROBE_AGGREGATE.json
```

生データはobservations.jsonl、実行末尾の状態はsummary.json、対象別推定はestimates.csv。実測の取得に成功したこと、RIDを検出したこと、方向誤差を確認したことを別々に報告する。RIDが0件でも端末非対応とは結論しない。ID構造検査は完全なフィールド検証や署名認証ではない。

アプリの「記録」からも推定結果CSVを書き出せる。CSVは対象別集計と回転の一致度で、生の時系列はJSONLを使う。JSONLには周囲の機器識別情報が含まれるため、ユーザーが形式と保存先を選ぶ。自動送信は行わない。

### UIの確認

```sh
# 隔離したエミュレーター専用。実機RFや方向精度を検証するコマンドではない。
python3 experiments/android-radio-probe/scripts/smoke_ui.py --device emulator-5580 \
  --apk experiments/android-radio-probe/app/build/outputs/apk/debug/app-debug.apk \
  --output .cache/NEW_RADIO_UI_CHECK
```

ナビゲーション、受信開始／停止、詳細ダイアログ、Androidの保存先選択によるCSV出力を確認する。エミュレーターをPixelの実電波の評価として扱わない。

## 根拠と詳細記録

- [Week26実機記録23](../../week26/23_Pixel8専用アプリの実装とWiFi_BLE実機確認.md)
- [調査22：AndroidでのAoAと方式の区別](../../week26/22_AndroidでのAoA実現方法とRemote_IDへの適用条件.md)
- [Android公式Wi-Fiスキャン](https://developer.android.com/develop/connectivity/wifi/wifi-scan)
- [Android ScanResult.InformationElements](https://developer.android.com/reference/android/net/wifi/ScanResult#getInformationElements())
- [OpenDroneIDのWi-Fi Beaconフレーミング実装](https://github.com/opendroneid/transmitter-linux/blob/main/wifi_beacon.c)
- [Kandulaら2024：スマホ回転によるRSSI／DoA推定](https://doi.org/10.3390/network4020010)。着想の関連研究。今回の調和回帰は独立実装であり、原アルゴリズムの追試や論文精度の再現ではない。
