# Pixel 8のDB・Flutterログの保全

接続されたPixel 8（Android 17）を確認し、KMP受信アプリとFlutter版アプリの受信ログを別々に保全した。既存のPixel 6 Pro・ASUS 2台の保存先は上書きしていない。端末のアプリ更新・時計変更・新規受信開始・データ削除は行っていない。

## KMP受信アプリ

導入されていたのは`org.smri.ridobserver.kmp`の`0.10-field-location`。確認時にReceiverServiceは見つからなかった。別端末の0.13と同じ版として比較しない。

| 項目 | 結果 |
|---|---:|
| 保全ファイル数 | 27 |
| 保全ファイル合計 | 96,651,821 bytes |
| DB観測行 | 14,674 |
| RSSIあり | 14,674 |
| 自己位置記録（receiver_fixes） | 2,271 |
| 診断イベント | 3,414 |
| アプリ上の解析済み | 20 |
| UNCLASSIFIED_VENDOR_IE | 14,654 |
| 受信観測に自己位置あり | 14,005 |
| 記録UTCの11月16日14〜18時相当の観測 | 11,938 |

最後の観測は記録UTCで11月16日06:11:46（日本時間15:11:46）。DBには過去の試験も含まれる。この時刻抽出だけでは実験区間確定とはしない。

参照Message Pack実装で解釈可能な20行を再確認したが、ユーザー照合済みの今回の機体IDはなかった。未分類行にも、そのID文字列やBで受信した実機候補と同じBSSIDは見つからなかった。ただし、未分類データを全て解析できたわけではなく、電波を一切受けていなかったと証明した結果ではない。

## Flutter版のWi-Fiログ

`com.example.rapidsnark_app`の`files/wifi-run-*`だけを追加保全した。他のアプリデータ・鍵等は収集していない。

- 7セッション・7ファイル・11,050 bytes。
- 有効JSON行10件、不完全行0件。
- Message Packは10行・内容1種類で、対象実機IDは0件。
- KMPのDB件数へ合算せず、別の保存元として保持した。

## 保存量と停止原因についての手掛かり

KMPのSQLite本体は67,108,864 bytes（64MiB）、page_count 16,384、page_size 4,096、freelist_count 0だった。アプリのDB上限と同じ大きさで、保存余裕がない状態を示す手掛かりになる。

一方、最終観測より後の15:18:44にも診断callbackが残る。受信・スキャン・DB書込みを区別して解析する必要がある。過去のreceiver_stopped理由にはuser_stop 13件とcapture_size_limit 1件があるが、これを最終停止の原因と自動で結び付けない。SQLiteFull例外の直接確認は未実施。

したがって、ここでは保存上限到達を最終原因と断定せず、[#90の停止原因調査](https://github.com/SMRI2170/zkp-m1-v2/issues/90)の追加入力として扱う。保全後もDBを削除・縮小・更新していない。

## 保存先・検証

入口：`captures/week29/nodes/android/device-4/`

- `raw/`：KMPアプリのsnapshot。
- `preserved/`：tar原本・manifest・端末情報などを含む保全先。
- `analysis/`：非公開のDB全件CSV・参照解釈・診断集計。
- `flutter-wifi/`：FlutterのWi-Fiログsnapshot。

実体は`captures/week29-android-pixel8-<取得時刻>/device-4/`。全てGit対象外、ディレクトリ0700・ファイル0600。

KMPとFlutterの双方で、端末側のコピー前後SHA-256と全保全ファイルのSHA-256が一致。KMP SQLiteはread-onlyで整合性検査ok。DB各テーブルを非公開CSVへ出力した。保全済みSQLiteのハッシュが解析後も変わらないことを確認した。

公開可能な集計のみ以下に記録した。実ID・BSSID・座標・生行は含めない。

- [Pixel 8のDB保全集計](results/android-initial-audit/device-4.json)
- [参照解釈・実機ID探索](results/android-initial-audit/device-4-reference.json)
- [Flutter版の集計](results/android-initial-audit/device-4-flutter.json)

既存の3D図へはまだ追加していない。対象実機IDの共通Packがないため、他端末と同じ時計補正を根拠なく適用せず、自己位置・時刻・停止状態の追加監査を先に行う。
