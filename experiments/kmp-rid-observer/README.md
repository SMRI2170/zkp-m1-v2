# KMP RID Observer

Wi-Fi BeaconのOpenDroneID Vendor IEを解析・表示・保存する研究用PoC。
既存Flutter版とは別パッケージ `org.smri.ridobserver.kmp`。

本アプリをZKPなしのRemote ID受信アプリとして使用する。
証明生成・検証、証明鍵、ウォレット、ブロックチェーンへの依存はない。
受信した申告ID・申告位置・RSSIをアプリ内SQLiteへ自動保存する。画面は保存値の手動テキスト表示。エクスポートは補助機能。
現行の対応はWi-Fi Beacon形式のみ。v0.3でForeground Serviceによる継続収録を実装した。Pixel 8の各30秒Smoke testで消灯中の新規観測と通知停止を確認済み。長時間・Doze・M350実機は未検証。

| モジュール | 内容 | 対象 |
|---|---|---|
| shared | ODID v2解析、重複排除、鮮度判定、RSSI履歴、JSONL・集計CSV | Android / JVM |
| androidApp | Wi-Fi ScanResult入力、SQLite自動保存、手動テキスト表示・SAF書き出し | Android 7以上（旧OSのIE取得は端末依存） |
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
3. 受信した観測はSQLiteへ自動保存する。「記録開始」は不要。
4. 「データ表示・更新」でDBの最新50件を文字列で確認する。表示は手動更新、グラフ描画なし。
5. 「受信停止」後、保存待ち0件を確認。「書き出し」→「DB全件JSONL」で保存全件を取り出す。
6. 「最新50件テキスト」はDBの最新値をTXTに出力する。
7. 「記録開始」→「記録停止」は任意の追加JSONL／監査ログ。DBの自動保存とは独立。

権限はACCESS_WIFI_STATE、CHANGE_WIFI_STATE、ACCESS_FINE_LOCATION、ACCESS_COARSE_LOCATION。インターネット権限なし。
標準のスキャン要求は30秒間隔で、OSの制限を維持。ScanResultはキャッシュ・Probe Response由来を含み得るため、生パケット数・受信率ではない。
画面の「受信開始」で継続通知付きサービスを開始する。Android 10以上ではlocation型、旧OSでは対応する2引数のForeground Serviceを使う。
画面を離れてもサービス側で受信・記録を継続し、通知または画面から停止できる。
Android 13以上では通知の許可も要求する。拒否時は画面に「通知非表示」と表示し、画面で停止できる。
通知拒否で継続通知の通常表示は保証されない。位置情報権限の拒否・剥奪等は開始失敗または停止になる。
追加権限はFOREGROUND_SERVICE・FOREGROUND_SERVICE_LOCATION・POST_NOTIFICATIONS。
サービスは非公開、表示中の利用者操作からのみ開始する。ACCESS_BACKGROUND_LOCATION・起動時自動再開・START_STICKY・WakeLockは使わない。
OS・Doze・画面消灯によるスキャン制約は維持する。常時取得・毎秒取得・プロセス終了後の継続は保証しない。
取り込み時点の観測年齢30秒を基準とし、時刻不明・未来値は古い観測扱い。
共通エンジンのメモリはRSSI履歴最大120件／対象、対象最大128、重複キー最大4096件。画面のグラフは廃止した。
メモリ上の受信全体CSVはプロセス再起動でリセットされるが、SQLite履歴は残る。追加JSONLは記録開始前の値を遡及保存しない。
保存はアプリ専用領域、ディレクトリ0700・ファイル0600、1記録20MiBまで。
観測JSONL・監査events.jsonl・終了時summary.csvを保存する。停止理由のため32KiBを予約する。
既存記録が108MiBを超える場合や空き領域64MiB以下では新規記録を開始せず、過去記録は自動削除しない。
収録状態、要求拒否・重複累計、最終新規観測時刻、PSS、CPU時間、画面・Doze・充電・電池状態を各要求時とスキャン通知時に記録する（標準の要求は30秒間隔）。
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
集計はJSON/CSVと5枚のSVG（新規観測数、同一送信元内更新間隔の中央値・p95、端点込み最大空白時間、最大サンプルPSS）。
送信元間をまたいだ間隔や、異なる充電状態の電池差を性能として扱わない。
観測数が0なら、更新間隔は欠測、空白時間は観測期間として報告する。
通知からの停止、権限剥奪、保存上限、force-stop等の試験は別途実施して報告する。

```sh
python3 -m unittest discover -s experiments/kmp-rid-observer/tests -v
```

Android実機上のFGS・画面消灯動作は、ホストの単体テストやAPKビルド成功だけでは実証されない。

公式仕様：[FGSの種類](https://developer.android.com/develop/background-work/services/fgs/service-types)、[開始制限](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start)、[Wi-Fiスキャン](https://developer.android.com/develop/connectivity/wifi/wifi-scan)。

## v0.4：開発用の高速測定

「スキャン要求」の行から、標準30秒／開発用5秒／開発用1秒を選ぶ。
変更は受信停止中のみ。**これは要求間隔であり、新しいRIDが得られる間隔ではない。**
アプリはOS設定を変更しない。高速モードは公式の開発者向け「Wi-Fiスキャン スロットリング」を利用者がOFFにした測定専用。
WifiManager.isScanThrottleEnabledで実際の状態を確認し、ONのまま高速モードを開始することは拒否する。実行中にONになった場合も停止する。
モード・OS状態は監査ログへ保存する。標準のevaluate_pixel.pyも記録開始時にAPIのONと30秒要求を確認し、開発用測定が正常条件に混入することを防ぐ。
測定後はスロットリングONと標準30秒へ戻す。電池消費・端末負荷・全バンドスキャン時間・送信機の送信周期により実効間隔は変わる。

今回のPixel 8＋PiテストBeaconの各約30秒・1回測定では、5秒要求の実効中央値5.09秒、1秒要求の実効中央値1.51秒（最小1.37秒・最大1.61秒）だった。
開発用設定・表示中・USB充電の結果であり、M350や背景・消灯での同じ性能は未検証。通常設定に一般化しない。
詳細：`week28/13_Pixel8の高速スキャン要求と実効取得間隔.md`。

## v0.6：SQLiteを標準保存先にする

受信開始で観測を自動保存し、再起動後もDB件数・内容を復元する。エクスポート操作をしなくても保存される。
DBはAndroidプラットフォームのSQLiteOpenHelperを使用し、解析・JSON／テキスト生成はKMP共通コード。
iOS/JVMのDB実装を追加したものではない。

保存先はアプリ専用 `files/captures/database/observations.sqlite`。ディレクトリ0700、DB・保持ジャーナル0600。
列は申告ID・申告座標／高度、RSSI、周波数、観測時刻、観測種別、鮮度、解析状態、正規化JSON、文字列。
JSONのrid_messagesに解析済みBasic ID／Locationを入れ、payloadの16進数も保持する。完全な802.11フレームを保存するものではない。

単一ワーカーでSQLiteへ書き込み、待ちキュー最大256件。画面の「DB件数」は保存済み、「保存待ち」は未確定。
受信停止後もキューは書き込みを継続する。保存待ち0件を確認してからプロセス終了・全件エクスポートを行う。
プロセス強制終了時の未確定キューまで永続化できる保証はない。
DB本体上限64MiB・10万行。失敗・満杯・キュー超過では受信を停止してエラー表示し、既存データを自動削除しない。
破損時の自動削除や破壊的マイグレーションは実装しない。

同じ起動期間内の同じ観測時刻・送信元・周波数・Vendor内容はDBの一意キーで重複排除する。
端末再起動の前後を混同しないようBOOT_COUNTを使う。不明時はプロセススコープへ退避し、完全な跨プロセス重複排除は保証しない。
時刻不明の観測もプロセスを跨いで同一と断定しない。物理パケット同一性や機体認証を証明する処理ではない。

DBの最新50件表示・TXT書き出しはメモリ履歴に依存しない。全件JSONLは受信停止・保存待ち0件でストリーム書き出しする。
全件書き出し中は受信を開始させず、保存ワーカーを長時間待たせない。
以前のJSONLファイルは保持し、DBへ勝手に取り込まない。アンインストール・アプリのデータ消去でDBは消えるため、必要なときは明示的にエクスポートする。

Pixel 8のPiテスト送信で3件の自動保存、APK更新・プロセス再起動後の保持、DB全件JSONLとTXTの照合を確認した。
M350実機・長時間・容量上限・DB破損・書込み途中の強制終了は未検証。グラフ廃止による取得速度向上も未計測。

## v0.7：送信元登録と解析失敗時の文字列

「送信元登録」でドローン／搭載Pi／不明の表示名と、申告RID・BSSIDのどちらかをローカル登録できる。両方指定した規則は両方一致が必要。受信停止・保存完了後に編集し、次の観測からJSONと文字列へ分類を記録する。過去のDB行は書き換えない。設定はアプリ内private SharedPreferencesへ保持し、外部へ送信しない。

文字列にBSSID・ローカル分類・Vendor IE全体の`raw_vendor_ie_hex`を追加。対象ODID IEがデコード不能でも、元バイト列・RSSI・観測時刻をSQLiteへ残す。未知の全通信方式を捕捉できるという意味ではない。正常に解析できない値からIDや位置を創作しない。

同じ申告IDでも異なるBSSIDは別の観測として記録する。より具体的な登録を優先し、競合は不明とする。`PI-RID-`は「Piマーカー（申告）」とだけ表示し、その他を自動でドローンと断定しない。JSONの`identity_verified`は常にfalse。ID・BSSIDを両方偽装された場合の機体認証はできない。

APK・共通コードのテストは確認済みだが、v0.7のPixel実機インストールと登録UI操作は端末未接続のため未実行。以前のv0.6実機結果をv0.7の実機結果として扱わない。

## v0.8：Android 7の互換経路

アプリ・共通AndroidライブラリともminSdk24、targetSdk36を維持。API30以上は公開IE API、API24〜29は既存Flutter版と同じフィールド読取りを利用する。取得不可なら診断に経路と例外型を残し、受信成功とは扱わない。root化・hidden API制限変更は行わない。

通知チャネル、Foreground Service開始、location有効判定、画面insetsをOSで分岐。日時文字列はAPI26のjava.timeに依存しない。旧OSでスキャン制限状態が取得できない場合はnullとして記録し、高速モードを許可しない。まず標準30秒で使用する。

ASUS_Z017DA／Android 7.0／API24で、インストール、一般Wi-Fi IE読取り、Piマーカー5件のRSSI付きDB保存、送信元登録、文字列表示、プロセス再起動後の保持を実機確認。Pixel 8のv0.8回帰実機評価やM350受信は未実行。

RID・BSSID入力はIMEの全角変換を避ける入力種別にし、登録ファイルも0700／0600へ制限する。以前のDB・登録情報を消さずに更新する。旧端末向け互換経路は端末依存で、すべてのAndroid 7端末を保証するものではない。

既存の3条件自動評価スクリプトはスキャン制限状態を確認できるOSが前提。API24の今回評価はADBによる段階的な操作であり、非対応の事前検査を無視して成功扱いにしない。詳細はWeek28の20番の報告。


## 0.9：受信文字列と端末方位の記録

標準30秒のスキャン要求・SQLiteの自動保存を継続。`データ表示・更新`で時刻・RSSI・BSSID・申告RID・生Vendor IE HEXを選択可能な文字列として確認できる。受信失敗を空の正常レコードに置き換えない。解析不能なODID Vendor IEも文字列・DBに残すが、独自のDJI方式を含む全無線フレームの捕捉を保証する機能ではない。

受信サービスの稼働中だけ回転ベクトルセンサーを約10Hzで要求し、スキャンの起動後時刻と最も近い方位を250ms以内・精度MEDIUM以上・水平から25度以内で対応付ける。結果通知時の方位を古いキャッシュに代用しない。対応不能なら`direction.missing_reason`を保存。履歴は1200点、対象ごとの推定用RSSIも1200点、最大32対象。追加権限・ネットワーク送信はない。

`方位・RSSI推定を確認`は磁北基準・端末の自然向きの上端（+Y軸）のRSSI最大方位を表示する。横画面の表示上端とは限らない。Wi-Fiの同一観測時刻は繰り返し加算しない。24点・8区画中6区画・角度範囲270度以上、振幅2dB・方向成分R² 0.35以上が必要。方位区画の逆数を重みとし、定数＋cos方位＋sin方位＋線形時刻の回帰を使う。以前のRadio Probeの計算を共通Kotlinへ移した独立した探索用実装で、閾値は精度保証ではない。標準30秒では24点の取得だけでも約12分以上かかり得る。

**端末方位・RSSI最大の端末方位・送信元の到来方向は異なる。** この版では送信元の方向は`transmitter_bearing_deg=null`、`aoa_measured=false`、`accuracy_validated=false`。回転方向と送信電力の変化が相関すると良い回帰でも誤る。移動体・反射・持ち方・アンテナ特性・磁気外乱に対する方向精度、独立した正解による校正は未検証。生の磁気方位・RSSIの保存が第一段階であり、未校正の矢印をドローン方向として表示しない。受信停止／再開始で推定用履歴はリセットする。過去のDB行は書き換えない。

Android公式：[ScanResultのRSSI・時刻](https://developer.android.com/reference/android/net/wifi/ScanResult)、[端末方位センサー](https://developer.android.com/develop/sensors-and-location/sensors/sensors_position)。通常のScanResultにはRF到来角の項目はない。センサーの磁北方位をその代替として扱わない。


## 端末での追加スモークテスト

```sh
cd experiments/kmp-rid-observer
python3 scripts/smoke_device_persistence.py --phase-seconds 30 --output ../../captures/NEW_DEVICE_SMOKE
```

リポジトリルートからなら `--output captures/NEW_DEVICE_SMOKE`。既存のDBを削除・初期化せず、通常表示／ホーム／画面消灯を各30秒実行し、受信サービスの存続・プロセスPSS・観測時刻別の新規行・停止後とプロセス再起動後のDBを確認する。既存受信が稼働中なら試験を開始しない。RF送信はこのスクリプトに含まれず、別途時間制限付きの管理された試験送信が必要。電波がない試験で受信成功を主張しない。

APKの再インストール・権限付与・スキャン設定の変更・端末の再起動は行わない。PIN等の認証画面は操作しない。Androidが非セキュアと報告したスワイプ画面のみ解除する。ユーザーが既に始めた受信を止めない。途中失敗や停止を確認できない場合はplan.jsonへ記録して失敗終了するため、端末の受信状態を確認する。生データ・UI XML・DB・時刻境界はowner-only captures内。最大3分＋起動停止処理の短時間試験であり、長期・Doze・方向精度・実ドローン試験の代わりではない。


## v0.10：自位置・現地書き出し・移行

GPS/networkの測位値を受信中のForeground Serviceで要求し、`receiver_fixes`へSQLite保存する。位置はWGS84緯度経度・水平精度・provider・GPS等のUTC・elapsedRealtime・mockフラグ・取得できる楕円体高度を保存。Wi-Fiの観測時刻に±2秒以内の測位がある場合だけ`receiver_position`に対応付け、時刻差も残す。測位なし・古いキャッシュは欠測理由を残す。端末自身の位置であり、RIDの申告位置とは別。

「DB明細CSV（自位置・距離付き）」「自位置履歴CSV」「診断CSV」を追加。保存はDB schema1→2の非破壊移行。古い観測のraw_json/text_lineを変更せず、新列はNULLのままにする。権限・OS・スキャン受付成否は追加記録ボタンなしでもDBへ残る。旧来の「受信全体CSV」は集計用で、DB明細CSVとは異なる。

明細CSVの距離はスマホ位置とRID申告位置の水平距離であり真値ではない。30m参考判定はスマホの水平精度だけで判定し、RIDの誤差は未知。模擬位置では距離判定を保留する。GPSの1秒要求や画面消灯中の継続を保証しない。

調査用に「未解析のWi-Fi保存」を明示的にONにすると、ODID以外のVendor IEや、IE未取得でもBSSID/RSSI/時刻を候補として保存する。非ODIDをRemote ID・DJIと自動分類しない。既定OFF、SSID保存なし。OSが返さない生電波データは保存できない。

[Pi/Android移行キットと現地手順](../field-kit/README.md)。コードだけのbundle、debug APK、チェックサムを生成可能。生データと認証情報は移行bundleに入れない。


### 主対象端末

Google Pixel 8を主対象として開発・実機確認する。今回接続された端末はAPI37。API30以降の公開Wi-Fi IE APIとlocation Foreground Serviceを基本経路とし、他社の比較的新しいAndroidは同じAPK＋診断CSVで適用可否を確認する。minSdk24の旧端末互換コードは残すが、全端末の同じ権限・頻度・バックグラウンド継続を保証しない。Kotlin/JVM共通テストやASUS旧端末での確認を、Pixelの実受信検証の代用にしない。

明細CSVと測位CSVはnode_id＋boot_scope＋elapsedRealtimeで照合する。旧行でboot_scopeが欠ける場合は再起動をまたぐ時刻照合を推測で埋めない。
