# Android 2台のデータ保全とProtocol 0再解析

接続されたPixel 6 Pro（Android 12）とASUS_Z017DA（Android 7.0）のKMP受信アプリ0.13-fastest-scanから、アプリ専用`files/captures/`全体を読み出した。アプリ停止・設定変更・更新・データ削除は行っていない。

## 保全結果

| 項目 | Pixel 6 Pro | ASUS_Z017DA |
|---|---:|---:|
| 保全ファイル数 | 17 | 17 |
| 保全ファイル合計bytes | 112,878,112 | 101,442,149 |
| DBの受信観測行 | 174 | 183 |
| RSSIあり | 174 | 183 |
| アプリで解析済み | 42 | 37 |
| アプリで未解析 | 132 | 146 |
| 受信時の端末位置あり | 132 | 146 |
| 独立テーブルの端末位置行 | 19,418 | 32,879 |
| 診断イベント行 | 53,218 | 51,541 |
| SQLite整合性検査 | ok | ok |

端末位置行はGNSS単独の測位成功回数や独立試行数を示すものではない。位置のプロバイダ・精度・時刻対応の詳細確認は次の解析で行う。観測行数も独立パケット数とは異なる。過去の試験データが混在し得るため、この全件を今回の実験成果としない。

元のSQLite、保持journal、セッションJSONL/TXT、CSV等をアーカイブ・展開コピーで保存した。SQLiteはローカルコピーをread-onlyで開き、全テーブルを非公開CSVへ出力した。全テーブルに位置等の機微情報を含み得るため公開しない。

Pixelは転送前後の端末側SHA-256とコピー全ファイルのSHA-256が一致。ASUSはAndroid 7の`sha256sum`が使用できなかったため、最初のハッシュ検証は失敗扱いとした。元のコピーは削除せず、端末側の全ファイルSHA-1を追加取得し、その前後とコピー全ファイルのSHA-1が一致することを確認した。ローカルmanifestは別途SHA-256で保存している。誤ってデータ変更があったと断定せず、古い端末の検証コマンド非対応として記録した。

## 未解析だったデータの読み出し

アプリ上の未解析理由は`invalid Message Pack header`だった。生のPack版はProtocol 0で、[B解析](04_Bノードの受信データとProtocol0の再解析.md)と同じ固定commitのOpenDroneID参照実装を用いてオフラインで解釈した。

| 項目 | Pixel | ASUS |
|---|---:|---:|
| 参照実装による解釈成功 | 132 / 132 | 146 / 146 |
| Locationメッセージあり | 132 | 146 |
| Bの未登録候補と申告IDが一致 | 132 | 146 |

**Bと両スマホで同じ申告IDのデータを保存できていた。** ただし、IDは自己申告であり、Matriceの機体認証ではない。同一物理パケット、同一実時間、真位置の一致は未検証。本番パーサ・ZKP入力条件を変更して自動承認した結果ではない。

## 時計の問題

確認時点でPixelは2021年、ASUSは2025年の日時を表示していた。DBの受信日時もそれぞれ2021年・2025年になっている。このため、11月16日という日付条件だけで抽出すると実験記録を取りこぼす可能性がある。今回は時計を変更せず、そのまま保全した。

次はRIDの時間内秒、端末の起動区分・monotonic時刻、申告軌跡、他ノードの内容を照合する。RIDの時間内秒だけで日付や時を一意に復元できるとは扱わない。

## 保存先

- `captures/week29-android-20261117/device-1/`：Pixel。圧縮なしtar、snapshot、manifest、非公開CSV・参照デコード。
- `captures/week29-android-20261117/device-2/`：ASUS。同上。
- 入口：`captures/week29/nodes/android/device-1/`、`device-2/`の`raw/`・`preserved/`・`analysis/`。

すべてGit対象外。実データのディレクトリ0700・ファイル0600を確認。公開用の集計は以下のみ。

- [Pixel集計](results/android-initial-audit/device-1.json)／[参照デコード集計](results/android-initial-audit/device-1-reference.json)
- [ASUS集計](results/android-initial-audit/device-2.json)／[参照デコード集計](results/android-initial-audit/device-2-reference.json)

未実行：実験区間の確定、機体IDとの照合、同一パケット照合、位置・距離精度の評価。今回行ったのは既存実データの保全・構文再解析であり、新しいドローン受信実験ではない。

## 追加接続：3台目のASUS

再接続時に3台を認識し、前のASUSとは別個体のASUS_Z017DA（Android 7.0、アプリ0.13-fastest-scan）を追加保全した。前回の2台分の原本は上書きしていない。現在3台ともReceiverServiceは見つからず、新たな収録は開始していない。

3台目は28ファイル、90,433,310 bytes。DBは受信観測7,740行、端末位置17,762行、診断イベント25,307行を保持。受信観測の全7,740行にRSSIがあり、7,641行に端末位置がある。SHA-1による全ファイルの転送前後・コピー一致、ローカルSHA-256 manifest、SQLite整合性ok、所有者専用権限を確認した。

DBの記録UTCで11月16日05:00〜09:00（日本時間14〜18時）に該当する観測は7,670行で、記録上の範囲は日本時間15:05:34〜16:40:14。ただし、実験時点の時計の独立確認がないため、この時刻抽出を実験区間確定とは扱わない。

アプリ分類は解析済み70行、未解析7,670行。未解析全行を固定版参照実装へ渡したところ、46行が解釈成功し、Bの候補と申告IDが一致した。残る7,624行は今回の参照Message Packデコーダでは解釈できなかった。生payloadが空の行も含まれるため、未解析全行をProtocol 0の同じドローンとは扱わない。異なるVendor形式・切出し・パーサ理由等の調査が必要で、今回推測で修復していない。

保存先は`captures/week29/nodes/android/device-3/`の`raw/`・`preserved/`・`analysis/`から参照可能。実体は`captures/week29-android-additional-<取得時刻>/device-3/`。 [3台目集計](results/android-initial-audit/device-3.json)／[参照デコード・時刻抽出](results/android-initial-audit/device-3-reference.json)。
