# KMP受信文字列・端末方位の保存と方向推定の限界

## 目的と結論

最小限の受信記録として時刻・RSSI・送信元・生Vendor IE HEXをSQLiteへ保存し、利用可能なら同じ観測時刻の端末方位を併記する。ASUS／Android 7でPiのID-only試験Beaconを受信し、新規3行すべてで方位との時刻対応を確認した。これは端末の磁北方位の保存であり、RF到来角の測定ではない。

本研究PoCは申告RID・観測者の申告を扱う。ドローンやセンサーの正直さ、DRIP、観測ハードを認証していない。Matrice 350 RTKの実電波受信、飛行中の方向精度は今回未検証。

## 追加したもの

- 共通KotlinのObservationに任意のdirectionメタデータを追加。DBの既存raw_json／text_lineに記録するので、過去行の書換え・DB初期化・破壊的なスキーマ変更はない。
- Androidの回転ベクトルセンサーを受信サービス中だけ約10Hzで要求。実センサー周期の保証ではない。停止時に解除し、再開始で推定履歴を消去する。
- ScanResult.timestampとセンサー時刻を起動後マイクロ秒で比較し、250ms以内・精度MEDIUM以上・水平から25度以内の場合だけ端末方位を対応付ける。後から届いたスキャン結果に現在の向きを代入しない。
- 対応できない場合は方位nullと理由を保存。方位が取れなくても受信文字列・RSSIを失わせない。
- 「方位・RSSI推定を確認」に点数・方位区画・保留状態を表示。未校正のRF方向矢印は表示しない。
- 以前のRadio Probeの探索用回帰を共通Kotlinに移植。32対象・各1200点、同一スキャン時刻／250ms未満を重複加算しない。BSSID・周波数・申告ID別に扱うが物理機体の同一性は保証しない。

時刻のreceived_at_utcはスキャンの起動後時刻と端末時計から換算した観測時刻で、サーバー／GNSS同期保証はない。時刻不明はnull。Wi-Fiスキャンキャッシュ観測と全無線パケット受信は異なる。

## 方向の意味

| 値 | 得られる意味 | 得られない保証 |
|---|---|---|
| phone_heading_magnetic_deg | 端末自然座標の+Y軸（上端）の磁北方位 | 送信源の方向・真北基準 |
| peak_phone_heading_deg | 回転中にRSSIが最大となる端末方位の回帰値 | ドローンの方向・精度保証 |
| transmitter_bearing_deg | この版では常にnull | RF到来角・校正済み方位 |
| aoa_measured / accuracy_validated | 常にfalse | AoA測定・独立精度検証 |

モデルは `RSSI = a + b cos(h) + c sin(h) + d × time_minutes + error`。各45度区画の件数の逆数で重み付けする。24点以上、8区画中6区画以上、最大角度空白90度以下、振幅2dB以上、線形時刻のみの回帰に対する方向成分R² 0.35以上が必要。これらは探索上の品質ゲートであり、正解方位への誤差保証ではない。

端末アンテナ・人体・反射・送信源の移動／電力変化がRSSIを変える。特に回転と相関した電力操作は良い回帰を作れる。線形時刻項で任意電力変化を消去できるとは主張しない。原則として同じ場所・持ち方・静止送信源での校正試験から始める。標準30秒では24点に約12分以上かかる場合があり、今すぐ短時間で方向が分かる機能ではない。

## 実行・失敗の記録

1. 最初のビルドは共通モジュールのnullable IntをAndroid側でsmart castできず失敗。値をローカル変数に取得して修正した。検査を無効にしていない。
2. 修正後はAPK・Lint、共通JVM／Android host各34件成功。合成回転の既知ピーク、線形ドリフト、平坦信号、回転不足、時刻ずれ、低センサー精度、傾き、方向連動電力による見かけの成功をテストした。合成テストを実環境の方向精度と扱わない。
3. ASUSのアプリ更新はデータ保持のinstall -r。既存5行を保持し、Piの新規試験で3行追加、合計8行。新規3行すべてに時刻・RSSI・生HEX・方位情報があり、方位時刻差の絶対値は最大9800µs。RSSIは3行とも−46dBm。SQLite integrity_check=ok。
4. 回転操作をしていないため、3行ともINSUFFICIENT_ROTATION、送信源方位はnull。期待通りの保留であり、方向推定成功ではない。
5. 方位保存は動作したが、画面のプロセス内対象一覧が未注釈のObservationを参照する不具合を発見。受信サービスで注釈後の同一観測を対象一覧にも反映するよう修正し、再ビルドした。修正前の3行を修正後APKでの受信件数として扱わない。
6. 最初の試験はSSH制御接続が途中で終了し、通常の終了receipt回収に失敗。再接続してPi内のreceiptを取得し、STOPPED_AFTER_BOUNDED_TEST、一時AP撤去、ap0不在を確認した。SSH終了の原因は未特定。Google Playストアの既存クラッシュダイアログは一時終了と閉じる操作で対処し、データ削除・無効化はしていない。

7. 最終版も追加で実機確認。既存8行に3行を追加し合計11行。うち2行は古いキャッシュで方位対応なし、1行は新規スキャンで方位対応あり。古い2行に現在の方位を代入していない。画面は「1点／1方位区画・保留・対応あり」でDBと整合した。全新規行の内容ダイジェストが送信receiptと一致。再起動後11行保持、最初の5行の全カラムが更新前と一致した。最終版の試験送信でもSSHの回収失敗があり、再接続で終了receiptとAP撤去を確認した。最終確認用に準備した追加送信は認証入力前に中止し、実行件数に数えていない。

最終版実機確認の集計は[validation.json](results/kmp-heading-20261111/validation.json)に記録する。生DB・方位・ID・BSSID・receipt・画面はignored captures、ディレクトリ0700／ファイル0600で保持する。Gitへ含めない。

## 再現手順

```sh
cd experiments/kmp-rid-observer
./gradlew :androidApp:assembleDebug :androidApp:lintDebug :shared:jvmTest :shared:testAndroidHostTest --no-daemon --max-workers=1
adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk
```

1. 位置情報・Wi-Fi・位置権限を確認して標準30秒で受信開始。
2. 手動開始の時間制限付きPi試験Beaconを受信。SQLite保存は受信開始だけで有効。
3. 「データ表示・更新」で文字列、「方位・RSSI推定を確認」で対応状況と推定保留を確認。
4. 受信停止・保存待ち0の後に書き出す。DBは再起動後も保持。
5. 方向精度を評価する場合は独立した既知の磁北基準送信方向を用意し、校正用と評価用の回転を分けて角度誤差を測る。この試験は未実行。

既存チェック：UAV88件、Go、contracts48件、KMP補助Python12件成功。最初のPython実行は親ディレクトリ指定で0件だったため、testsディレクトリを指定し直して12件を実行した。0件の終了を検証成功とは扱わない。

## 根拠

- [Android ScanResult](https://developer.android.com/reference/android/net/wifi/ScanResult)：RSSI levelはdBm、timestampは起動後µs。通常の結果にRF到来角フィールドはない。
- [Android Position sensors](https://developer.android.com/develop/sensors-and-location/sensors/sensors_position)：回転ベクトル等から端末姿勢・磁北方位を得る。電波の方向を測るAPIではない。
- [既存Radio Probeのモデルと失敗条件](../experiments/android-radio-probe/README.md)：今回の回帰移植元。スマホ回転によるRSSI推定は独立した探索用実装で、論文の精度の再現ではない。
