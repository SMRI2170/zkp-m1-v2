# Android 7のASUSでKMP受信・DB保存を確認

2026-11-11。接続されていたASUS_Z017DA（Android 7.0／API24）向けに互換処理を実装し、実機へv0.8をインストールした。

**この端末でも、PiのWi-Fi Beaconマーカーを5件受信し、RSSI・登録した送信元ラベル・生Vendor HEXをSQLiteに保存できた。プロセス再起動後も5件と登録情報を保持した。**
M350実機ではなく、位置なしの研究用Piマーカーによる事前試験である。

## 変更

| 箇所 | API24向けの処理 |
|---|---|
| 対応SDK | アプリ・共通AndroidライブラリのminSdkを24に変更。targetSdk36は維持 |
| Wi-Fi IE | API30以上は公開API、API24〜29は既存Flutter版と同じフィールド読取り |
| 位置情報有効判定 | API28未満は有効なGPS／Network providerを確認 |
| サービス | API26未満はstartServiceから前景化、API29未満は2引数startForeground |
| 通知 | API26未満はチャネルなしのNotification.Builder |
| 画面余白 | API30未満は旧insets。初期paddingも設定 |
| UTC文字列 | java.timeに依存せず、UTC固定のSimpleDateFormatで生成 |
| スキャン制限 | API30未満は取得不可のnull。高速モードは許可せず標準30秒 |
| 登録入力 | RID／BSSIDは半角英数向け入力。ASCII判定を緩めない |
| 登録保存 | source_labels.xmlを0600、親ディレクトリを0700 |

旧端末のIE読取りは端末依存。root化、hidden API制限変更、Wi-Fiスキャン制限の解除、manifestのoverrideLibraryによる強制はしていない。

## 実機結果

| 項目 | 結果 |
|---|---|
| 端末 | ASUS_Z017DA、Android 7.0、API24、arm64 |
| APK | v0.8-android7-compat、versionCode8、更新インストール成功 |
| 一般Wi-Fi情報 | 読取り成功。初期確認時11〜14件。独立パケット数ではない |
| IE経路 | legacy_field。取得した診断50件ではerror=none |
| 送信元登録 | PiのID＋BSSIDをUIから入力して保存。半角値の完全一致を照合 |
| 送信 | Pi Aの位置なしBasic IDマーカー。時間上限100秒 |
| 受信条件 | 標準30秒要求、Wi-Fiと位置権限有効。追加JSONL記録ボタンは使わない |
| 保存 | SQLiteへ5件。RSSI −48／−48／−46／−46／−46dBm |
| 内容照合 | 全5件の生HEX／内容ダイジェストがPiの送信receiptと一致 |
| 分類 | 登録ID＋BSSIDによるonboard_pi。identity_verified=false |
| 文字列 | 登録ラベル、ID、BSSID、RSSI、時刻、生HEXを表示 |
| ホーム画面 | 35.11秒後もforeground serviceが稼働 |
| 再起動 | 受信停止・保存待ち0確認後にプロセスを終了。再起動後も5件・ラベルを保持 |
| DB整合性 | integrity_check=ok |
| 権限 | captures／DBディレクトリ0700、DB・journal・登録ファイル0600 |
| 高速モード | API24で1秒要求を選ぶと開始を拒否。標準30秒へ復元 |
| 終了 | 受信停止、Piの一時AP撤去、送信終了を確認 |

画面は実機画像とUI階層で確認した。長い生HEXはスクロール領域で折り返す。画像・UI XML・DB・ID・BSSID・送信receiptはprivate capturesに保持し、Gitへ含めない。

再起動直後にWi-Fi0／RID0と表示されるのはプロセス内の現在の一覧が空だからで、DB履歴の消失ではない。「データ表示・更新」で保存済み5件を読み出せる。

## 解釈の限界

- 5件はスキャンキャッシュ観測。全Beacon数、全パケット受信率、位置情報の更新率ではない。
- ホーム35秒時点のFGS存続は確認したが、この試行ではホーム区間内だけの新規観測数を厳密に分離していない。
- 位置なしマーカーなので、実位置・GNSS・ドローンの動作を検証したものではない。
- RSSI絶対校正・端末間比較・距離推定を行っていない。
- USB接続での短時間確認。長時間、画面消灯、Doze、非充電、通知停止ボタン、権限剥奪、M350実機は未評価。
- v0.8のPixel 8回帰実機評価、他のAPI24〜29機種は未実行。すべてのAndroid 7端末でのIE取得を保証しない。

## 失敗と対処

1. 最初のビルドは共通AndroidライブラリのminSdk30と不一致で失敗した。ライブラリが使うSHA-256と共通処理を確認し、両モジュールを24へ揃えた。API呼出しは分岐・代替し、manifest検査を回避しなかった。
2. 端末側でGoogle Playストアの既存クラッシュダイアログが重なっていた。クラッシュ元はcom.android.vending。データ削除・アンインストール・無効化はせず、一時終了とダイアログを閉じてKMPアプリを確認した。
3. 最初の登録操作ではIMEがBSSIDを全角に変換し、ASCII検査で拒否された。入力種別を変更して値の完全一致を確認した。既存の判定を緩めて受け入れてはいない。
4. 初回の送信操作は日本語sudoプロンプト待ちで送信未開始だった。送信として集計せず、プロンプト処理を直して実行した。動作した送信のラッパー出力はSSH終了でreceiptを取得できず、Pi内の保存receiptを再接続して回収し、全5件の照合と一時AP撤去を確認した。SSH終了の原因は特定していない。

## テストと再現

Android/JVM共通各29件、Python12件、APK・Lint成功。既存UAV88件、Go、contracts48件も成功。共通テストはGradleのUP-TO-DATEを含むため、実機試験の代わりとは扱わない。

[検証JSON・APKハッシュ](results/kmp-android7-20261111-a/validation.json)とビルド／チェックログを保存した。最初のビルド失敗ログも保持する。

```sh
cd experiments/kmp-rid-observer
./gradlew :androidApp:assembleDebug :androidApp:lintDebug :shared:jvmTest :shared:testAndroidHostTest --no-daemon --max-workers=1
adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk
```

端末でWi-Fi・位置情報サービス・位置権限を確認し、標準30秒で「受信開始」。Piの実測周波数に依存するため、M350の周波数・送信方式をこの結果から固定しない。通常の表示・登録・保存方法は[README](../experiments/kmp-rid-observer/README.md)。
