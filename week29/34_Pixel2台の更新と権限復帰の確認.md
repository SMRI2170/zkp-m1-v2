# Week29：追加Pixel 2台のv0.15更新と確認

2026-11-19、Issue #84。接続されたPixel 6 ProとPixel 8を対象とする。前報33のASUS 2台とは別の試験。アプリのデータを消去・アンインストールせず、停止状態から更新した。

| 端末 | 端末申告Android / API | 更新前→後 | 実機の隔離保存fixture |
|---|---|---|---|
| Pixel 6 Pro | 12 / 31 | v0.14→v0.15 | 5件成功 |
| Pixel 8 | 17 / 37 | v0.14→v0.15 | 5件成功 |

OS/APIはADBのgetpropによる端末申告で、公式配布版・安定版であることを独立検証した値ではない。APKは報告33と同じv0.15。隔離fixtureは実機で動かした合成テストであり、実ドローン受信ではない。

## 保全と更新

- 受信サービス停止を確認し、アプリのfiles/shared_prefs全体を所有者専用の非公開tarへ保全。バックアップのSHA-256を私的記録へ保存。
- `adb install -r`による上書き更新。アンインストール・DB消去・OS設定変更は実施しない。
- 各端末で、legacy不変・容量停止・hot journal復旧等の隔離fixture5件を実行。fixtureはoperator DBを開かない。
- FINE/COARSE位置権限は当初から両台で許可済み。Pixel 8の通知も許可済み。Pixel 6 ProはAPI31なのでPOST_NOTIFICATIONSの実行時許可の対象ではない。

## 短時間の権限・保存復帰試験

報告33の有限時間スクリプトを利用。許可状態で20秒受信・記録し、元から許可されていた位置権限2種を取消し、停止と権限案内を確認。元の許可だけをADBで復元し、UIから新しい記録セッションを開始して20秒観測。最後に正常停止・既存行保持・SQLite整合性を確認する。制御RF源・実ドローンは使用しない。

Pixel 8の最初の試行は、アプリ初回の「GPS・Wi-Fi受信の許可」案内に遮られ、受信開始前に中断。位置・通知は許可済みであり、案内の「許可を確認」を操作してから新しい出力先で再試行した。初回の失敗ログ・snapshotは保持する。これを受信やDB復旧の失敗とは解釈しない。

| 項目 | Pixel 6 Pro | Pixel 8（再試行） |
|---|---:|---:|
| 権限取消し後の停止・案内 | 確認 | 確認 |
| 再許可後の新セッション・FGS | 確認 | 確認 |
| 試験前→終了時の観測行 | 174→174 | 14,674→16,553 |
| 旧観測・独立保存測位の保持 | 確認 | 確認 |
| SQLite integrity | ok | ok |
| 新規gps由来fix | 0 | 0 |
| 新規network由来fix | 0 | 4 |
| 元の許可・permission flags・受信停止 | 確認 | 確認 |

[匿名JSON](results/android-additional-20261119T053606Z/summary.json)／[匿名CSV](results/android-additional-20261119T053606Z/summary.csv)／[端末対応表](results/android-additional-20261119T053606Z/devices.json)。Pixel 6 Proの新規観測0件は、制御送信源なしの本試験における結果であり、受信機能の故障を意味しない。


更新前tarの観測・測位と試験後DBを照合し、両台とも旧行の欠落・変更0件、integrity=okを確認した。[更新前からの保持](results/android-additional-20261119T053606Z/pre-update-preservation.json)。

## 解釈と限界

- 両端末を同じ時刻・配置・受信対象・保存設定で統制した性能比較ではない。新規保存行数を機種の優劣、物理パケット数、PDRにしない。
- 試験前データの保持と、更新前tarからの保持検証は別に記録。稼働中DBの単純コピーはせず、停止後に本体・journalを保全し、派生コピーで復旧・比較する。
- 現行のOS要求解析補助は旧UpdateRecord形式向け。API31/37の現在の位置要求は自動解釈せず、公開JSONでnull/NOT_EVALUATEDとする。保存された新規fixのprovider別件数はSQLiteの実レコードから集計する。
- GNSSの1Hz継続取得、屋外精度、Pixelの自然Doze・消灯長時間、実ドローン受信はこの試験では未確認。元の権限と受信停止状態へ戻す。新規実ドローンは後日 #99。

## 成果物・再現

`week29/scripts/summarize_android_permissions.py`に公開端末manifestの指定を追加。機種・APIをASUS固定で誤表示せず、追加端末の別名と対応付ける。serial等の未許可フィールド、パス逸脱、重複ラベルを拒否する。生DB・座標・実ID・serial・UI/位置dump・バックアップはignored captures配下0700/0600へ保持。

```sh
python3 experiments/kmp-rid-observer/scripts/test_device_permissions.py \
  --serial "$AUTHORIZED_DEVICE" --output "$NEW_PRIVATE_OUTPUT" --phase-seconds 20
python3 week29/scripts/summarize_android_permissions.py \
  --private-input "$PRIVATE_STUDY_ROOT" --device-manifest "$PUBLIC_DEVICE_MANIFEST" \
  --output "$ANONYMOUS_SUMMARY_JSON"
python3 -m unittest discover -s week29/tests -v
```

Week29の84件（新規manifest試験3件）、Android補助36件、UAV50件、Go、contracts21件が成功。APK本体は前報33で検証したv0.15と同一であり、今回も両実機で隔離保存fixture各5件が成功。公開先はPR #101。push後のCIは別途確認し、実機試験と区別して記録する。
