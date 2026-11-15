# Bの復旧・配置とAndroid 7端末への観測機能導入

2026-11-10。ユーザーのSDカード挿し直し後、Bのネットワーク・ログインを確認し、A/Cと同じreleaseを配置。並行して、接続されたAndroid端末へ更新アプリを導入した。資格情報・IP・端末シリアル・周辺AP識別子は公開結果へ保存しない。

## Bの結果

- Raspberry Pi 4 Model B Rev 1.5、aarch64、約3.8GiB RAM。
- 機器名observer-b、ユーザーpi。変更後の資格情報でログイン成功。
- 当初は旧IPに応答がなく、mDNSでobserver-b-2を発見。OSの機器名はobserver-bであり、avahiを再起動してobserver-b.localの名前解決を確認した。IP変更をパスワード不正と取り違えなかった。
- Python 3.13.5／iw 6.9。A/Cより新しい版だが、同じコードで16件の合成テストが成功した。
- `~/zkp-beacon-observer/releases/0cdddec858bf/`へ同じ観測コードを配置。設定のnode_idはobserver-b。
- 128MiBメモリ上限、1ファイル20MiB、nice+10、期間指定の手動起動。無期限・自動起動の収録は設定していない。
- 12秒・4秒間隔のキャッシュ読み取り3回、延べBSS項目3、ODID 0件。終了コード3は新鮮なODIDなしという状態で、クラッシュや「正常なドローン」の判定ではない。
- 子プロセス最大RSS 23,856KiB（約23.3MiB）。NTP同期yes、定量的な時計精度は未測定。
- Pi内のログファイル0600を確認。原始キャッシュや実位置をGitへ追加していない。

A/B/Cは全台、次の同一コマンドで実行する。

```sh
~/zkp-beacon-observer/run --check
~/zkp-beacon-observer/run --self-test
~/zkp-beacon-observer/run --duration 60 --interval 5
```

## Android端末と互換処理

接続された端末はPixelではなくASUS_Z017DA、Android 7.0/API24、arm64。既存アプリは未インストールだったため、今回は新規インストールとなった。更新APKのminSdk24、アプリID `com.example.rapidsnark_app`。

従来のWifiOdidScannerはAndroid 11/API30より前ではIE取得とWi-Fiスキャン配信を停止していた。今回、[OpenDroneID参照受信機のWiFiBeaconScanner.handleResult](https://github.com/opendroneid/receiver-android/blob/master/Android/app/src/main/java/org/opendroneid/android/bluetooth/WiFiBeaconScanner.java)で使われる方式を参考に、旧ScanResultのinformationElements／id／bytesフィールドを読む互換経路を追加した。

- API30以降：従来の公開APIを維持。
- API24〜29：端末が許可するフィールド読取り。取得失敗時は理由を診断ログへ出し、取得成功と見なさない。
- root化、OSのhidden API制限の無効化、位置権限の迂回はしていない。Wi-Fiスキャン用の位置権限を付与した。
- Wi-Fi NANはAPI26以降だけで初期化し、API24では呼び出さない。
- ネイティブ診断は取得経路・IE件数・例外型のみ。SSID、MAC、ペイロード、座標を診断ログへ出さない。
- 画面の「Android 11以上が必要」という固定文言を、旧Androidでは端末依存である旨に変更した。

参照実装の構造を使えることと、すべてのAndroid 7端末で取得できることは別。今回のASUSで実際に確認した結果として以下を報告する。

## Android実行確認

1. 1 worker、Java heap1536MiB、metaspace768MiB、arm64指定、コマンド上のみJetifier無効でAPKビルド成功（31秒）。
2. ADB install成功、MainActivity起動成功。アプリの最初の権限画面が出た後、起動を確認した。
3. WiFi Raw画面に実測スキャン結果14件が表示された1時点を確認。14独立送信や14ドローンとは数えない。
4. RSSI・周波数を表示し、`ie_access=legacy_field`と情報要素件数の実行ログを確認。これは一般APを含むWi-Fiスキャンの確認であり、実Remote ID受信ではない。
5. 観測記録開始・停止ボタンを操作し、端末内にJSONLが作成されたこと、権限0600を確認。今回のODID記録は0行。
6. 画面・原始UI XML・端末内ログのパスはowner-privateのcapturesだけに保存し、周辺AP名や端末シリアルをGitへ掲載しない。

Flutterの新規ログ3件＋既存Beaconパーサ6件は計9件成功、変更Dart2ファイルの静的解析は指摘なし。Python77件、Go、contracts48件も成功。API30以降の端末で今回版を再実機評価したものではない。

## 未確認

- Pi送信機を起動してA/B/CとAndroidが実際にRIDを受信する試験は未実行。
- DJI実機の受信・パケット比較・検出性能の追加評価は未実行。
- 端末間の同一物理パケット照合、受信機差、受信局の座標、時計精度、GhostBuster FPR/TPRは未評価。

集計・ビルド／テストログは `results/b-asus-setup-20261110-a/`。研究PoCであり、センサの正直さ・DRIP trust chain・受信機ハードウェア・機体同一性を認証した成果ではない。
