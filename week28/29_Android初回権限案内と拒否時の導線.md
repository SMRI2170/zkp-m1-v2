# Android v0.11：アプリ内の権限案内

従来も「受信開始」で位置権限を要求していたが、初回の説明・許可状態表示・拒否後の再設定経路が不足していた。アプリ内で用途を説明し、OSの許可画面へ進めるようにした。端末の設定を外から変更したり、ADBで許可を自動付与する変更ではない。

- 初回、必要な権限が未許可なら説明を表示。「権限を確認」からOSの位置許可へ進む。
- 初回案内で許可しただけでは受信を開始しない。「受信開始」を選んだ場合のみ、必要な許可の後に受信を開始する。
- 画面に「正確を許可／概算のみ／未許可」と通知状態を表示。いつでも権限案内を開ける。
- 正確な位置が拒否された場合は受信を開始せず案内を表示。再要求可能ならOSダイアログ、再要求できない場合はアプリ設定へ誘導する。
- Android13以上の通知許可は任意。通知拒否だけで受信不可とはせず、必要な位置許可と明示した開始操作を条件にする。Android12では通知の追加許可は要求しない。
- Wi-Fiや位置情報サービスがOFFの場合の設定案内は維持。言語・権限・OSのスキャン制限を回避しない。

## 実機確認

接続中のPixel 6 Pro（Android12/API31）へv0.11を更新インストールし、APKハッシュ一致・既存観測不変を確認。アプリ内説明→OSの位置許可ダイアログの表示を確認した。許可ボタンは自動操作せず、利用者の選択に残した。案内・許可画面を開いただけでは受信サービスが開始していないことも確認した。

最初のUI照会は消灯中でSystemUIしか読めなかった。認証ロックと取り違えて案内したが、点灯して再確認し、実際のアプリ内説明とOSダイアログを確認した。許可の自動付与や認証回避は行っていない。

JVM/Android Host各43件、APK/Test APK/Lint成功。追加の4テストは、初回許可だけで開始しない、拒否後の別コールバックで勝手に開始しない、任意の通知を必須条件にしない、初回要求・再要求・設定誘導の区別を確認する。実機の恒久拒否・概算のみ・API33以上の通知ダイアログ操作は未実施で、共通ロジックのテストとは分ける。

[匿名検証JSON](results/permission-guide-v011/validation.json)。画面・端末ID・DBバックアップ・インストールログはowner-only capturesへ保存し、Gitへ追加しない。受信・測位・CSVの機能はv0.10から維持し、今回の確認を実ドローン受信や30m実験の成功として扱わない。

## 設定済みPiとAndroidの目安

同日の再確認でA（送信/BME280記録）、B/C（RSSI受信）はactive/enabled。AのUSB GPSは未検出、Dは接続未確認。収録上限の保護停止は維持する。

本実験ではAndroid12以上を動作の目安とする。Vendor IE取得の公開APIはAndroid11/API30以降だが、バージョンだけで機種ごとの取得可否・頻度・位置精度を保証しない。現行の主対象はPixel。最低SDK24の旧端末互換は補助経路で、現行Androidでの確認と混同しない。

公式資料：[権限要求とrationale](https://developer.android.com/reference/android/app/Activity#shouldShowRequestPermissionRationale(java.lang.String))、[Android12の正確／概算位置](https://developer.android.com/about/versions/12/behavior-changes-all)、[Wi-Fi IE公開API](https://developer.android.com/reference/android/net/wifi/ScanResult#getInformationElements())。
