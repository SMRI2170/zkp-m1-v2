# ZKPなしのKMP Remote ID受信アプリ

KMP版を「Remote ID 受信」v0.2-receiverとしてPixel 8へ更新した。
Wi-Fi BeaconのOpenDroneIDを解析し、申告ID・申告位置・RSSIを表示する。
JSONL記録と集計CSV出力を備え、証明生成・検証、証明鍵、ブロックチェーン、ウォレットには依存しない。
既存Flutterアプリと以前の記録は保持した。

今回の変更はアプリ名・バージョンの整理と、スキャン更新時に記録中の表示が失われる問題の修正。
共通解析コードは変更していない。

## 検証

- ビルド成功、Android/JVM共通テスト各11件成功。
- Android Lintはエラー0、警告8。対象API・バックアップルール・描画時割り当て・アイコン・文字列連結に関する警告が残る。
- 既存UAV77件、contracts48件、Goチェック成功。
- Pixel 8へ更新・起動成功、タイトルとボタン・待機画面の表示崩れなし。
- 受信開始でWi-Fiスキャン13件を取得。今回の確認時はRID対象0件。
- 今回は新たなテスト送信をしていない。実RFのRID解析・保存・CSV出力の確認結果は前報08を参照。
- 確認後、受信・記録は停止した。

[実行集計とAPKハッシュ](results/kmp-receiver-v02-20261110-a/validation.json)

## 現在の対応範囲

Wi-Fi Beacon形式・Android 11以上。バックグラウンドに移ると受信・記録を停止する。
BLE/NAN、バックグラウンド取得、iOSは未実装。
申告位置の表示は位置の真正性の証明ではなく、DRIP・観測ハードウェアも認証しない研究PoC。

[コード・操作・再現手順](../experiments/kmp-rid-observer/README.md)
