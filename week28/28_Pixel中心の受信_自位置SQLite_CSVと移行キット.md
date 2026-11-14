# Pixel中心の受信・自位置保存・現地書き出しと移行キット

## 今回できたこと

Google Pixel 8を主対象にKMPアプリv0.10を実装・更新し、接続端末API37でPiの研究用Beacon受信、自位置保存、時刻対応、SQLite保持、ダウンロードへのCSV保存を確認した。起動識別子追加後の再試験も実施し、最終DB481件をCSV481件として書き出した。他の比較的新しいAndroidへ同じソース/APKを移行し、機種ごとのAPI・権限・取得失敗を診断できる形にした。旧ASUS経路も残すが、今回の主対象はPixel。

Pi側にはJSONLからCSV／JSON配列への書き出しと、旧ログを保持する移行キットを追加。A/B/Cを新しい収録先で再開した。生データはGitへ追加していない。

研究用PoCであり、ZKPは含まない。機体認証・DRIP・観測者ハードや位置の真正性を保証するものではない。

## 機能と保存場所

| 対象 | 機能 | 保存・書き出し |
|---|---|---|
| Android受信 | Wi-FiキャッシュのRSSI・BSSID・時刻・申告位置・元Vendor IE・解析失敗理由 | ローカルSQLite、全件JSONL・明細CSV・最新テキスト |
| Android自位置 | GPS/networkへ1秒間隔を要求。測位UTC・elapsedRealtime・精度・provider・mock・取得できる楕円体高度 | 別のreceiver_fixesテーブル、自位置履歴CSV |
| 時刻照合 | 受信キャッシュ時刻に±2秒以内の最寄り測位を対応。現在位置を古い受信へ流用しない | 受信行のreceiver_position、時刻差、対応できない理由 |
| 距離の参考値 | RID申告位置と自位置の水平距離、スマホの精度だけを考慮した30m参考区分 | 明細CSVの距離・精度・判定区分。真距離ではない |
| 調査用候補 | 明示ONで非ODIDのVendor IEも保存。IEがなければ取得できたBSSID/RSSI/時刻と欠測理由 | invalid/unclassifiedとして保存。DJI/RIDとは自動断定しない |
| 診断 | Android/API・権限・位置情報状態・要求成否・OS制限状態・IE取得経路/例外 | 診断SQLite/CSV、観測のie_access |
| Pi | 標準の未解析ODID保持に加え、明示オプションで未分類Wi-Fi候補保存 | owner-only JSONL/TXT、CSV／JSON配列へ変換 |

明細と測位履歴はnode_id＋boot_scope＋elapsedRealtimeで照合できる。旧行の起動識別子を推測で埋めない。

SQLite schema1→2は列追加と測位・診断テーブル追加。過去のraw_json/text_lineを変更せず、新しい列は欠測のまま保持する。JSONLのraw値をCSVにも含め、CSVの引用符・改行・表計算ソフトの数式解釈に対処した。新しいCSV出力は全件ストリーミングで、全DBをメモリへ展開しない。

## Pixel 8の実機結果

最初の収録はアプリ更新で中断したため、正常終了した連続試験として扱わない。ただし保存済みの受信・測位・診断は実測として残した。最終APKでは別途UIから開始・停止し、実際のダウンロード保存を確認した。

| 試験 | 結果 | 解釈 |
|---|---|---|
| 既存データ保持 | Pixelの既存3件の従来カラム値を保持、schema2へ移行 | 未検証の履歴復元や別端末へのDB自動移植ではない |
| 最初の収録（更新で中断） | 受信8件、RSSI全8件、自位置89件（GPS80/network9）、時刻対応6件 | 正常終了・長期運転成功とは数えない |
| 同収録の位置精度 | 最小約8.55m、中央値約10.58m、mockは0件 | OS申告の水平精度。独立した真位置誤差ではない |
| 最終版の短時間収録 | 新規受信2件、RSSI/IE診断2件、自位置1件、時刻対応1件、UIで正常停止 | 受信元はAの位置なしPi Beacon |
| ホーム画面 | 約8.26秒でFGS生存確認、新規測位0件 | この区間だけではバックグラウンド測位頻度を実証していない |
| 最終短時間の対応位置 | network、水平精度100m | 30m離隔の判定には不十分 |
| 未解析候補ON | 追加466件中、未分類Vendor IE461件をinvalidとして保存。461件で元HEXあり | 一般Wi-Fi候補であって461台のドローンではない。試験後OFFへ復元 |
| ダウンロードCSV | 候補保存後のDB479件とCSV479件の件数一致、全raw_jsonをJSONとして読出し可能 | 自位置列も含む。最初の13件CSVも保持 |
| 最終APK | 端末上APKとキット内APKのSHA-256一致。起動識別子付き新規受信2件も保存 | コードの転送整合性。機体認証ではない |

端末の再接続後は端末IDを明示して操作した。最初の端末はASUSだったが、その後のPixel用DBバックアップ・テストは別のprivateディレクトリへ分け、混同しない。

画面操作の途中で別タスクが前面になることがあり、最初のエクスポート照会は保存先画面を確認できず失敗した。新規UI階層ファイルで再確認し、実際のAndroid DocumentsUIのローカルDownloadsへ保存した。DB479件との照合を完了している。実行失敗を「受信0件」として埋めていない。

## 30m実験について言える範囲

今回確認したのは取得・保存・照合・書き出しの経路。**実ドローンとスマホが真に30m離れていることの実証は未実施。** AはUSB GPSが見つからずBasicIDのみを送信しているため、実受信から位置申告距離を計算する試験も未実施。距離計算・境界・mock時の保留は合成入力によるテスト。

RID申告位置とスマホの測位値を使った距離は、申告位置との参考比較。スマホ精度が100mなら30mを議論できない。GPS精度が約10mと表示されても、その値は保証された誤差限界ではなく、RID側の誤差・申告時刻・改ざんも未検証。

Wi-Fiとスマホ測位は同一端末のelapsedRealtimeで照合する。RID位置の申告時刻はCSVに残すが、送信機の時計・申告時刻との同期検証は別途必要。キャッシュ受信時刻とRID位置の生成時刻を同じだと仮定しない。現地では独立して測った離隔距離と合わせて評価する。

## バックグラウンド・端末移行

Kotlin/KMPの共通処理を継続し、Androidのネイティブlocation Foreground ServiceがWi-Fi・測位・DBを担当する。表示中の利用者操作から開始し、継続通知と停止操作を提供する。言語変更によるOS制約回避、root、START_STICKY、起動時の無断収録は追加していない。

主経路はAPI30以降の公開Wi-Fi IE API。旧API24〜29は既存互換経路で、機種依存。現行Pixel以外の新しいAndroid、長時間・Doze・非充電・OS再起動後の継続は未評価。標準Wi-Fiスキャン要求は30秒で、測位の1秒要求とは別。どちらも毎回の新規取得を保証しない。

## Piと移行キット

Aは送信＋BME280記録、B/Cは受信として新releaseを有効化。以前の収録量上限に達したrelease/capturesを保持し、明示的な新セッションで再開した。上限を緩めたり、古いログを自動削除する変更はない。

Bの実受信167行、Cの115行をCSV／JSON配列へ書き出し、全行のraw_jsonと元JSONLが一致し、入力ハッシュ不変・出力owner-onlyを確認した。Bでは既存の能動受信に重複スキャン要求を出さず、5秒の受動キャッシュ読取りで未知候補モードも試験した。最終キットのPiソース集合が導入済み版と一致することを確認。

キットはコードだけのPi/Androidソースtar、debug APK、インストーラ、manifest、README、ビルドログ。生ログ・座標・DB・認証情報・privateキー・SDK設定は含めない。インストーラはハッシュとtarのファイル集合・パストラバーサル・リンクを検査し、RAM/ディスク/依存を確認。activateしなければ配置検証だけ、有効化時のみsudoでサービスを更新する。

[移行・ビルド手順](../experiments/field-kit/README.md)／[Android操作](../experiments/kmp-rid-observer/README.md)。他端末のDBを自動同期するものではない。新端末は新しいDBで開始し、過去データは利用者がCSV/JSONLへ書き出して保管する。

## 検証・成果物

- Kotlin共通：JVM39件・Android Host39件成功。
- Pixel実機：専用fixture DBで旧schema移行・CSV・再オープン・0600保存を確認するInstrumentationテスト1件成功。実フィールド位置をfixtureへ流用しない。
- Android APK/Test APKのビルド・Lint成功。最初のテストAPKは旧AndroidTestCase参照でコンパイル失敗したため、標準Instrumentationを使うテストランナーに修正した。
- Pi Python50件、移行キット1件、モバイル解析Python17件、既存UAV88件、Go、contracts48件成功。
- CIでもAndroidのビルドとキット生成を実行し、コードとAPKのキットを成果物に含める。実機RF試験はCIとは分ける。

[匿名検証JSON](results/field-kit-pixel8-20261114/validation.json)。原始受信・位置・端末ID・スクリーンショット・DB・エクスポート原本はignored/owner-onlyのcaptures内。Gitへ追加しない。

## 残件

実DJI機のこのアプリでの受信、独立真値での30m実験、長時間/Doze、別の現行Android機種、AのUSB GPS実測は未検証。OSが公開しないVendor IEや生フレームは復元できない。その場合は得られたメタデータ・欠測理由を残す。

位置の時刻・水平精度・楕円体高度の意味は[Android Location公式仕様](https://developer.android.com/reference/android/location/Location)、測位更新は[LocationManager公式仕様](https://developer.android.com/reference/android/location/LocationManager)を参照。
