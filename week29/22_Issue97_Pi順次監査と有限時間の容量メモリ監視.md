# Issue97：Pi B〜Fの順次監査・容量／メモリ監視

> 後続更新：B/E/Fへの実機適用・OS再起動・5分監視を実施した。[最新報告25](25_B_E_F保存修正とOS再起動確認.md)を参照。この文書の未実行表記は当時の状態として保持する。

> 後続の実機接続で、事前TCP判定によるSSH試行省略とホスト鍵alias指定の問題が判明した。現在は実SSHの結果で判定し、保存済みaliasを照合した新しい接続設定を使用する。この報告の過去TCP結果だけでSSH到達不能を確定しない。後続の実機修正報告を参照。

## 今回実装して実行したこと

接続の再確認、読み取り専用の監査・有限時間監視プログラム、導入予定コードキットのローカル検証を行った。**B〜Fへの更新・サービス変更・再起動は未実行**。Issue97の完了には達していない。

`experiments/field-kit/audit_receivers.py`はB→C→D→E→Fの順で監査し、1台が接続できなくても次へ進む。今回、ホスト名と既知IPの計11候補を試したが全てTCP接続できず、5台分の失敗receiptとCSV／JSONを保存した。電源断、故障、現在のIPや所属ネットワークを確定したものではない。

| ノード | SSH接続 | 設定・サービスの監査 | 保存修正の適用 |
|---|---|---|---|
| B | 未成立 | 未実行 | 未実行 |
| C | 未成立 | 未実行 | 未実行 |
| D | 未成立 | 未実行 | 未実行 |
| E | 未成立 | 未実行 | 未実行 |
| F | 未成立 | 未実行 | 未実行 |

[匿名JSON](results/issue97-receiver-audit-b/summary.json)／[匿名CSV](results/issue97-receiver-audit-b/nodes.csv)。公開用にはアドレス・ホスト鍵・固有値・生ログを含めていない。私的な設定と詳細receiptはignored `captures/`に0700／0600で保存。

## 接続できた際に取得する項目

- 登録node_idと実ホスト名の一致、機種アーキテクチャ、OS、現行release。
- 設定ファイルのSHA-256。内容や鍵そのものは出力しない。
- systemdの稼働状態・終了理由・CPU累積値・メモリ・上限・再起動回数、unit定義。
- RAM／swap／SD空き、NTP同期状態、boot ID。
- 新保存方式のheartbeat、セッションID、保存量、件数、最終書込み情報。

ホスト鍵は保存済みknown_hostsの指定aliasを使い、`StrictHostKeyChecking=yes`を維持。未登録の鍵を自動受諾しない。任意の`--ask-password`を使う場合、端末上で入力したパスワードを一時的なSSH askpassの環境経由で渡し、公開コード・設定JSON・引数・receiptへ保存しない。既存のSSH・sudoers・Wi-Fi権限は変更しない。

## 監視・容量試算の扱い

要求する監視時間は最大6時間に制限し、サンプル間隔1〜300秒を受け付ける。開始済みの巡回や通信タイムアウトにより、実際の終了は指定時刻より後になる場合がある。全ノードが接続できない場合は初回のreceiptを保存して終了する。CSVは巡回ごとにflush・fsyncし、中断時も途中分を残す。長時間の完了をチャットで待つことを前提にしない。

実際に4時間を指定して監視モードも実行したが、全接続が成立しないため約25秒で理由付き早期終了した。[監視モードの結果JSON](results/issue97-receiver-monitor-c/summary.json)と[検証記録](results/issue97-receiver-monitor-c/validation.json)を保存。4時間完走や記録成功ではない。

保存速度は同じboot・同じセッションの有効な2点以上から求める。SSH空白、セッション変更、boot変更、設定変更、counter巻戻り、古いheartbeatをまたいで速度を算出しない。データなしを0bytes/sに置き換えない。

4時間の追加保存量は、観測速度が変わらないという条件の試算。受信セッションの64MiB予約、SDの1GiB予約を維持して収まるかを別々に判定する。試算が収まっても4時間完走の証明ではない。今回、実機サンプルを取得できなかったため、B〜Fの容量・メモリ統計・4時間試算は**NOT_EVALUABLE**。

`WAITING_FOR_OBSERVATIONS`は収録待ちでありRID受信成功ではない。古いbootのheartbeat、古い更新、サービス停止、容量停止、接続不能を別状態にする。プログラム自身は収録プロセスの停止やメモリ上限変更を行わない。

## 再実行

非公開の接続設定は今回作成済み。ローカルの`.cache/week29-issue97-audit-root`に保存先を記録している。設定JSONは`nodes`配列、各要素は`node_id`／`known_hosts`／`targets`、各targetは`host`／`host_key_alias`のみを指定する（既存ユーザーpi）。設定ファイルにパスワードを追加しない。

```sh
# 1回の順次監査。既存出力を上書きしないよう新しい出力名を指定
python3 experiments/field-kit/audit_receivers.py \
  --config "$(cat .cache/week29-issue97-connection-config-path)" \
  --private-output captures/week29/issue97-next-audit \
  --summary week29/results/issue97-next-audit/summary.json

# 接続・設定を確認できた後の4時間監視。必要なら --ask-password を追加
python3 experiments/field-kit/audit_receivers.py \
  --config "$(cat .cache/week29-issue97-connection-config-path)" \
  --private-output captures/week29/issue97-next-monitor \
  --summary week29/results/issue97-next-monitor/summary.json \
  --duration 14400 --interval 30
```

これは監査・監視用であり、自動インストーラではない。SSHを途中で切った場合も、その時点までにPCへ書き込めたCSV／receiptは残る。PC側プロセスが停止している間の値を取得したとは主張しない。

## 導入予定キット

`.cache/week29-issue97-code-kit/`へコード専用kitを生成した。Piソース46ファイルの集合・各SHA-256・全payload・source_hashを照合。`capture_storage.py`と`capture_health.py`を含み、captureディレクトリを同梱していないことを確認した。[検証JSON](results/issue97-code-kit/verification.json)。これはMac上の整合性確認であり、Piへのstageや配布者署名の検証ではない。APK再ビルドはしていない。

## テストと残件

field-kit 12件（新規監査10件＋既存2件）、既存Pi関連58件、UAV 88件、aggregatorのGoテスト、contracts 48件が成功。接続不能でも次ノードへ進みreceiptを残すこと、ホスト鍵確認維持、本人確認不一致、待機と受信の区別、古いheartbeat、boot／セッション／設定変更、容量予約境界、symlink拒否、資格情報を設定へ埋め込まないことをテストした。初回はMacの`/var`→`/private/var`を含むテスト用一時パスがsymlink拒否に該当したため、正常ケースのfixtureを正規化して修正し、拒否条件自体は維持した。

実機の設定・旧データ保全、stage、サービス切替、旧記録の前後ハッシュ照合、自動起動復旧、4時間監視、電源断試験は未実行。保全確認を省略して適用する処理は追加していない。順次導入・resumeの自動化も、この接続監査・監視とは別の残件である。コードのcommit／push・CIは未実施。
