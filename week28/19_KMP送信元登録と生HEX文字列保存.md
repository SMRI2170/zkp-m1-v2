# KMP v0.7：送信元登録と生データ文字列

ドローン自身と搭載Piを別記録として確認するため、ローカル送信元ラベルと生Vendor IE HEXを追加した。ZKP・機体認証は行わない。

## 操作

1. 受信停止・保存待ち0件で「送信元登録」。
2. 区分（ドローン／搭載Pi／不明）、表示名、申告RIDまたはBSSIDを設定。両方指定した場合は両方一致が必要。
3. 「受信開始」。SQLiteへ通常どおり自動保存する。
4. 「データ表示・更新」でBSSID・分類・申告ID・RSSI・時刻・生HEXを文字列表示。

登録は端末内private SharedPreferences、最大32件。登録変更は次の受信からJSON／TXTに反映し、過去のDB行を変更しない。SQLiteスキーマは既存v1を維持し、分類は保存JSON／文字列の追加項目として残す。

## 分類の意味

- 具体的な登録を優先。競合する登録は不明にする。
- `PI-RID-`は「Piマーカー（申告）」であり、本物のPiや同乗機体を認証するものではない。
- 未登録IDをドローンと自動判定しない。同じIDでも異なるBSSIDは別観測として保存する。
- IDとBSSIDの両方を偽装された場合は、この情報だけでは識別できない。
- `source_annotation.identity_verified=false`を常に保持する。

## 最低限残すデータ

対象ODID Vendor IEを解釈できなくても、`raw_vendor_ie_hex`、BSSID、時刻、RSSI、解析失敗状態をDBへ保存する。
ASCIIの意味が不明なバイナリを無理に文字へ変換せず、HEX文字列で元バイト列を保持する。正常に読めないID・位置は創作しない。
既存の保存量・キュー上限・所有者権限・明示書き出しを維持。全通信方式や全物理パケットを取得する機能ではない。

## 実行した確認と未実行

- Android/JVM共通テスト各29件成功。同じ正常Basic IDを異なるBSSIDで取り込み、両方のIDが正しく復号されて別記録になることを確認。登録競合、未検証Piマーカー、解析不能時の生HEXも検査。
- Python12件、APK生成・Lint・JVM配布物成功。v0.7-source-labels / versionCode 7。
- Piでの実RF事前試験では2種類の送信を別記録でき、解析不能データも文字列で保存できた。ただしAndroid実機の結果と混同しない。
- PixelはADB・mDNSに見えず、v0.7のインストール、登録UI、実機SQLiteへの今回追加項目の書込みは未実行。以前のv0.6の実機結果を流用しない。
- M350実機のID登録・同時受信、飛行中の動作は未実行。

生成APKは `experiments/kmp-rid-observer/androidApp/build/outputs/apk/debug/androidApp-debug.apk`。ビルド成果物と生キャプチャはGitへ追加しない。
[検証記録](results/kmp-source-labels-20261111-a/validation.json)とビルド／テストログを保持する。既存Flutter版・Pi版・過去DBを削除しない。
