# KMP RID Observer

Wi-Fi BeaconのOpenDroneID Vendor IEを解析・表示・保存する研究用PoC。
既存Flutter版とは別パッケージ `org.smri.ridobserver.kmp`。

本アプリをZKPなしのRemote ID受信アプリとして使用する。
証明生成・検証、証明鍵、ウォレット、ブロックチェーンへの依存はない。
受信した申告ID・申告位置・RSSIを表示し、端末内JSONLと集計CSVに保存する。
現行の対応はWi-Fi Beacon形式のみ。v0.3でForeground Serviceによる継続収録を実装した。Pixel 8の各30秒Smoke testで消灯中の新規観測と通知停止を確認済み。長時間・Doze・M350実機は未検証。

| モジュール | 内容 | 対象 |
|---|---|---|
| shared | ODID v2解析、重複排除、鮮度判定、RSSI履歴、JSONL・集計CSV | Android / JVM |
| androidApp | Wi-Fi ScanResult入力、ネイティブ画面・グラフ、保存・SAF書き出し | Android 11以上 |
| replay | TSVから共通コードで再生（無線受信なし） | JVM / Mac / Linux |

解析・状態管理がKMP共通コード。画面はAndroid固有。
iOS・Compose Multiplatform・BLE・Wi-Fi NANは未実装。
Piの既存Python受信器は変更しない。JVMツールはライブ受信器ではない。

## ビルド

JDK 17以上、Android SDK 36が必要。検証環境はJDK 21。
Git対象外の `local.properties` に `sdk.dir` を指定する。

```sh
cd experiments/kmp-rid-observer
./gradlew :shared:jvmTest :shared:testAndroidHostTest :androidApp:assembleDebug :replay:installDist --no-daemon --max-workers=1
adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk
```

Gradle 9.1.0 / Kotlin 2.3.20 / AGP 9.0.1。Java/Kotlin出力17。
APKはデバッグ署名。配布用署名鍵は作成していない。

## Androidの操作

1. Wi-Fi・位置情報サービスを有効にする。
2. 「受信開始」で正確な位置情報を許可する。
3. RIDカードを選んで申告位置と形式検査結果を表示する。
4. 「記録開始」→「記録停止」でJSONL保存する。
5. 「書き出し」で集計CSVまたは生JSONLを選択する。

権限はACCESS_WIFI_STATE、CHANGE_WIFI_STATE、ACCESS_FINE_LOCATION、ACCESS_COARSE_LOCATION。インターネット権限なし。
スキャン要求30秒間隔、OSの制限を維持。ScanResultはキャッシュ・Probe Response由来を含み得るため、生パケット数・受信率ではない。
v0.3は画面で「受信開始」を押すとlocation型Foreground Serviceを開始する。
画面を離れてもサービス側で受信・記録を継続し、通知または画面から停止できる。
Android 13以上では通知の許可も要求する。拒否時は画面に「通知非表示」と表示し、画面で停止できる。
通知拒否で継続通知の通常表示は保証されない。位置情報権限の拒否・剥奪等は開始失敗または停止になる。
追加権限はFOREGROUND_SERVICE・FOREGROUND_SERVICE_LOCATION・POST_NOTIFICATIONS。
サービスは非公開、表示中の利用者操作からのみ開始する。ACCESS_BACKGROUND_LOCATION・起動時自動再開・START_STICKY・WakeLockは使わない。
OS・Doze・画面消灯によるスキャン制約は維持する。常時取得・毎秒取得・プロセス終了後の継続は保証しない。
取り込み時点の観測年齢30秒を基準とし、時刻不明・未来値は古い観測扱い。
グラフは新しい有効RSSI最大120件、対象最大128、重複キー最大4096件。
履歴はメモリのみ。記録開始前の値を遡及保存しない。
保存はアプリ専用領域、ディレクトリ0700・ファイル0600、1記録20MiBまで。
観測JSONL・監査events.jsonl・終了時summary.csvを保存する。停止理由のため32KiBを予約する。
既存記録が108MiBを超える場合や空き領域64MiB以下では新規記録を開始せず、過去記録は自動削除しない。
収録状態、要求拒否・重複累計、最終新規観測時刻、PSS、CPU時間、画面・Doze・充電・電池状態を約30秒間隔の要求時とスキャン通知時に記録する。
Doze等で処理されなかった期間は監査サンプル自体も欠ける。推定のゼロ件を実測サンプルとして埋めない。
終了イベントがない記録は中断・不明として扱い、自動追記再開しない。
CSVは「受信全体」と「記録セッション」を分ける。終了時にセッションCSVを確定する。
プロセス再起動後も最新記録の生JSONL・確定済みセッションCSVを書き出せる。メモリ上の全履歴は復元しない。
生ログにはID・BSSID・申告位置を含む。書き出しは利用者が保存先を選ぶ。

## JVM再生

入力TSVは以下の6列。実際の区切りはタブ、数値は整数、欠測は空欄。
Vendor IEはID/長さを除く本体の16進文字列。

```text
observed_us delivered_us rssi_dbm frequency_mhz vendor_hex source_key
```

```sh
# リポジトリルートで実行。captures/exampleと入力TSVは事前に作成する。
java -Drid.repoRoot="$PWD" -cp 'experiments/kmp-rid-observer/replay/build/install/replay/lib/*' \
  org.smri.ridobserver.replay.MainKt \
  --input captures/example/input.tsv --output captures/example/output.jsonl
```

出力は無視対象captures/またはuav/captures/内のみ。親ディレクトリ0700、入力・出力0600で扱う。
既存出力は上書きしない。異常終了時の空・部分出力も自動削除しない。
必ずsource_type=replay、physical_packet_match=unconfirmedとする。

## 保証範囲

形式解析であり、機体・申告位置・センサー・観測者ハードウェアの真正性、DRIPは検証しない。
ZKP・署名集約・既存V2への送信は未接続。絶対電力校正・同一物理パケット対応・方向推定も行わない。

## 公式資料

- [Android-KMP Gradle plugin](https://developer.android.com/kotlin/multiplatform/plugin)
- [AGP 9移行](https://kotlinlang.org/docs/multiplatform/multiplatform-project-agp-9-migration.html)
- [Kotlin 2.3.20](https://kotlinlang.org/docs/whatsnew2320.html)

## バックグラウンド評価の実行

Pixel 8を接続し、APKを更新してから、アプリの正確な位置情報・通知を許可する。
画面ロックを解除し、Wi-Fi・位置情報を有効にする。既存の受信・記録は利用者が停止しておく。
比較に使う送信源は別途用意する。このスクリプトは電波を送信せず、OSのスキャン制限も変更しない。
以下はリポジトリルートで実行する。出力先は新しいディレクトリにする。

```sh
python3 experiments/kmp-rid-observer/scripts/evaluate_pixel.py \
  --source-kind test_beacon --phase-seconds 1800 \
  --output captures/kmp-background-run1
python3 experiments/kmp-rid-observer/scripts/analyze_capture.py \
  --capture captures/kmp-background-run1 --output captures/kmp-background-run1-analysis
```

表示中→ホーム画面→画面消灯を各30分ずつ評価し、操作終了後は画面を点灯して記録・受信を停止する。
実行中は端末に触れない。短いSmoke testは `--phase-seconds 30`。実行時間は測った秒数を報告する。
収録中のログを15秒ごとにホストへ.partialとして回収する。切断時は既存証拠を残し、cleanup未確認なら通知から停止する。ロック等で停止を確認できなければ、スクリプトはエラー終了する。
自動実行は現在認識されたPixel 8だけを対象にし、他機種や未接続の端末へ操作しない。
集計はJSON/CSVと4枚のSVG（新規観測数、同一送信元内更新間隔p95、端点込み最大空白時間、最大サンプルPSS）。
送信元間をまたいだ間隔や、異なる充電状態の電池差を性能として扱わない。
観測数が0なら、更新間隔は欠測、空白時間は観測期間として報告する。
通知からの停止、権限剥奪、保存上限、force-stop等の試験は別途実施して報告する。

```sh
python3 -m unittest discover -s experiments/kmp-rid-observer/tests -v
```

Android実機上のFGS・画面消灯動作は、ホストの単体テストやAPKビルド成功だけでは実証されない。

公式仕様：[FGSの種類](https://developer.android.com/develop/background-work/services/fgs/service-types)、[開始制限](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start)、[Wi-Fiスキャン](https://developer.android.com/develop/connectivity/wifi/wifi-scan)。
