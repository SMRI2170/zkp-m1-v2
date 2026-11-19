# Week29：Android権限取消し・復帰とGPS要求の実機確認

2026-11-19、Issue #84。実ドローン・Pi送信機は使用しない。接続ASUS_Z017DA 2台（Android 7.0/API24）を対象とする。Pixel・現行Android・自然Dozeへの一般化はしない。

## 発見した復帰不具合と修正

位置権限取消しでプロセス／書込みが中断された後、有効なrollback journalが残るsegmentを読み取り専用で開くと、SQLiteの復旧書込みができず、DBを開けない状態になった。実機ログにSQLite `(776) attempt to write a readonly database`、UIにDB未初期化・受信開始無効を確認。旧データの削除で解消していない。

v0.15は、hot journal候補のsegment本体とjournalを非公開 `captures/database/recovery/` へ0700/0600で退避し、SHA-256一致を確認後、SQLiteの標準rollbackとintegrity_checkを実行する。legacy DBは従来どおり書込み不可。容量不足・退避不一致・復旧失敗は停止し、失敗資料を削除しない。未commitのトランザクションのrollbackは、保存済み行の削除とは区別する。キュー上の全件保持を保証するものではない。

[SQLite公式：hot journalとrollback](https://www.sqlite.org/lockingv3.html#hot_journals)が復旧の根拠。独自にDB内容を書き換える修復は実装していない。

## 試験設計

1. 初期のFINE/COARSE位置権限が許可済み、受信サービス停止を確認。生DB・journal・設定を所有者専用で保全。
2. アプリ操作で受信・追加記録を開始し、20秒待つ。OSの現在のGPS/network要求を記録。
3. ADBから既存の位置権限2種を取消し、サービス停止、権限案内、旧DBの保持を検査。
4. 元から許可されていた2権限だけをADBで復元。UIから受信・記録を再開し、20秒待つ。
5. UIから正常停止し、旧行・測位の保持、integrity、元の権限、停止状態を確認。

再許可は試験制御用ADB操作。OSの「許可」ボタン操作のE2E試験ではない。未知の権限を新しく付与せず、Wi-Fiスキャン設定、Doze、電池模擬、他ノードは変更していない。受信源を制御していないため、送信機別のRID受信性能やPDRは評価しない。

## 試験中の失敗も保持

- 初回：稼働中DBの単純コピーが整合性検査に失敗し、権限取消し前に中断。生DB破損とは扱わない。以後はサービス停止・プロセス停止後にDB/journalを保全し、別コピーで復旧する。
- 次の試行：権限取消し後に自動表示される案内ダイアログを試験UI処理が扱えず中断。元の権限／受信停止状態へ復元。
- その次：取消し後のhot journalを旧版が読み取り専用で開き、受信開始できず中断。ここをv0.15で修正した。各試行のログ・snapshotは非公開で保持。
- v0.15導入後の最初のUI試験は、別アプリのGoogle Playストアが繰り返し停止するシステムダイアログに遮られて中断。表示を確認して「アプリを閉じる」を押し、無効化・設定変更はせず再実行した。再表示も発生したため、試験補助に当該のOSクラッシュ表示だけを有限回閉じる処理と、権限ダイアログや別アプリを閉じない単体テストを追加した。この中断をDB復旧修正の失敗と混同しない。
- 解析補助の単体テストでも、類似パッケージ名を誤一致する問題を検出し、正確なpackage名とOS表示のUID付き形式を区別するよう修正。

## 実機結果

| 項目 | Android-1 | Android-2 |
|---|---:|---:|
| 取消し後のサービス停止・権限案内 | 確認 | 確認 |
| 再許可後の新セッション・FGS再開 | 確認 | 確認 |
| 試験前の観測／測位保持 | 両方確認 | 両方確認 |
| 試験前→終了時の観測行 | 13,180→15,123 | 212→212 |
| SQLite integrity_check | ok | ok |
| GPS／networkの現在の要求 | 両方あり | 両方あり |
| 新規GNSS fix | 0 | 0 |
| 新規network fix | 4 | 0 |
| 終了時：元の権限へ復元・受信停止 | 確認 | 確認 |

各許可状態の観測区間は約20秒ずつ。一般Wi-Fiの保存設定が異なるうえ、今回は制御送信源を起動していない。Android-2の新規観測0件を受信故障・PDR 0と解釈しない。受信性能ではなく起動・権限・保存復帰を調べた。Android-1の元判定の再解析は次節のとおり。

[匿名JSON](results/android-permissions-20261119T012730Z/summary.json)／[匿名CSV](results/android-permissions-20261119T012730Z/summary.csv)。両台へv0.15を上書き導入済み。導入前にはfiles/shared_prefs全体も別途保全した。


## 解析形式の差と判定の修正

ASUS API24の完全なpackage dumpでは、取消し後のruntime permissions一覧が空になり、`granted=false`行自体が出ない。最終のAndroid-1試行は全操作を完了したが、この形式をunknownとしたため元の実行判定は`failed_acceptance`だった。元結果は変更せず、宣言済み権限・空のruntime一覧・ASUS終端を確認できる場合のみ未許可とする解析と単体テストを追加し、保持したdumpから再評価した。入力不足や途中切れはunknownのまま。アプリ本体の権限判定は緩めていない。

この機種のdumpにpermission flagsは表示されなかったため、flagsの一致は未確認（JSONではnull）。許可済み／未許可と、flagsが取得できることを混同しない。

## DozeとGPSについて言える範囲

前回報告32の強制Doze中の新規受信停止は、今回のDB復帰修正で解消したとは言えない。AndroidのDozeはWi-Fi/GPS等を制限するため、FGSの生存だけを収録継続の証拠にしない。[AOSPのDoze仕様](https://source.android.com/docs/core/power/platform_mgmt)、[AndroidのDoze試験手順](https://developer.android.com/training/monitoring-device-state/doze-standby)を参照。

測位要求が1秒間隔でも、GNSS fixが毎秒得られるとは限らない。GPSとnetworkへの現在の要求、実際に保存したprovider別の新規fixを区別する。過去のlast-known位置や履歴にある要求を、新規測位・稼働中要求として扱わない。設置環境・衛星見通しを統制していないため、新規GNSSがない原因を遮蔽・故障等に断定しない。

## コード・再現・検証

- `DatabaseSegments.kt`：中断segmentの退避と復旧。`FieldPersistenceTest.kt`：operator DBを開かない隔離fixtureでhot journalを再現し、退避SHA・rollback・再起動時の重複退避なしを確認。
- `scripts/test_device_permissions.py`：有限時間の実機試験。例外時も元の権限と停止状態へ戻し、復元失敗を結果に残す。
- `scripts/permission_evidence.py`：権限／active要求の厳密な選択、派生SQLite snapshotの復旧。元snapshotは変更しない。
- `week29/scripts/summarize_android_permissions.py`：許可した集計項目だけを公開JSONへ出力。座標・serial・実ID・元UI／位置dumpは公開しない。

```sh
python3 experiments/kmp-rid-observer/scripts/test_device_permissions.py \
  --serial "$AUTHORIZED_DEVICE" --output "$NEW_PRIVATE_OUTPUT" --phase-seconds 20
python3 week29/scripts/summarize_android_permissions.py \
  --private-input "$PRIVATE_STUDY_ROOT" --output "$ANONYMOUS_SUMMARY_JSON"
python3 -m unittest discover -s experiments/kmp-rid-observer/tests -v
```

Android補助Python36件、Week29 81件、UAV50件、Go、contracts21件が成功。APK/test APK、Android JVMテスト、Lintのビルドが成功。実機の隔離保存試験5件も成功。合成fixtureと実際の権限試験は別の証拠。

公開先は[PR #101](https://github.com/SMRI2170/zkp-m1-v2/pull/101)。コードSHA `006c647e687ce167778ffc9640332d8f46a29afc` をpush後、GitHub Actions 6 runs / 8 job checksすべて成功し、完了ログを確認した。Android補助36件・Week29 81件・UAV50件・contracts21件・Go・Androidビルドの成功をCIでも確認。外部CodeRabbitのSKIPPEDは実行済みレビューに数えない。

[CI実行とjobの記録](results/android-permissions-20261119T012730Z/ci-code-006c647.json)。これはコードSHAに対する記録であり、実機の権限試験・隔離fixtureの実行証拠とは区別する。

## 残件

- 復旧時の退避I/O・起動時間と容量余力の追加評価。
- Pixel／新しいAndroidの権限・Doze・実放電・長時間試験。
- 屋外GNSS条件の統制、初回fix待ち時間・継続間隔・位置精度の評価。
- OS許可ダイアログを利用者が操作する経路、通知停止・再起動等の追加評価。
- 実ドローンは後日 #99。今回の試験は機体認証・真位置・センサ真正性を保証しない研究PoC。
