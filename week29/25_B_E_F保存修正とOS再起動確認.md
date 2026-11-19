# B・E・F：保存修正の実機適用とOS再起動確認（2026-11-17〜18）

## 結果

**B・E・Fの3台へ保存修正を適用し、旧記録・設定の保持、新セッション、OS再起動後の自動復帰を確認した。** receiver専用で有効化し、送信サービス・Wi-Fi・SSH・sudoers・既存の送信元分類は変更していない。

対象実機RIDは確認時点0行。一般Wi-Fiのキャッシュ読取りと収録処理の稼働は確認したが、実ドローン受信成功ではない。

| ノード | 実機モデル | 更新前の収録サービス | 保全・照合ファイル数（設定含む） | 元データ合計 | 更新後 |
|---|---|---|---:|---:|---|
| B | Pi 4 Model B | active | 5,810 | 408,432,473 bytes | active・新セッション |
| E | Pi 3 Model B+ | 終了コード78で停止 | 1,277 | 201,941,490 bytes | active・新セッション |
| F | Pi 3 Model B+ | 終了コード78で停止 | 1,169 | 201,750,500 bytes | active・新セッション |

更新前E/Fの終了コード78は確認したが、今回参照した過去journalから停止理由の文字列までは確定できていない。コード78だけで、過去の全停止を容量不足と断定しない。

## 保全・配置・検証の順序

1. 保存済みSSHホスト鍵、node_id／ホスト名、現行release、設定、RAM／SD余力、NTPを照合。
2. Bの収録を正常停止。E/Fもinactiveを確認して、全releaseのcaptureとconfig・unit情報を保全。
3. アーカイブをMacへ回収し、集合・サイズ・SHA-256を照合。オフラインの旧回収物で更新直前保全を代用しなかった。
4. 新releaseをstageし、Wi-Fi関連テストとPi関連58テストを通した後にreceiver専用で有効化。
5. 新セッション・boot対応・設定ハッシュを確認し、旧ファイル全件のハッシュを再照合。
6. OS再起動を各台で行い、別boot ID・別セッション・同じrelease／設定・収録サービスのactiveを確認。

旧release、既存データ、不完全な末尾、初回失敗のログとreleaseは保持。公開するのは[匿名結果](results/bef-storage-repair/final-summary.json)と[ノード別CSV](results/bef-storage-repair/node-results.csv)のみ。生アーカイブ・manifest・認証済み接続情報・個別ログはignored capturesに0700／0600で保存。ローカル保存先は`.cache/week29-issue97-live-bef-root`に記録している。

## 接続監査の問題を修正

監査側のPython TCP事前チェックで失敗した場合に、OpenSSHを試さず接続不能としていた。また私的な接続設定のHostKeyAliasが保存済み鍵の名前と一致していなかった。

通常のSSHでは到達できることを確認し、事前TCPゲートを除去して**実際のSSH結果で判定**するよう修正。aliasは保存済みknown_hostsと照合した。未知の鍵を自動受諾せず、鍵の検証・ノード指定の照合を維持した。TCPとSSHで解決・経路等のどの差が生じたかまでは未特定。

過去のTCP試行失敗だけで、電源OFF・故障・SSH停止・パスワード不正と結論しない。旧監査ログは保持し、訂正を報告22へ追記した。

## E/Fのstage失敗と修正

初回のPiテストは、`test_capture_storage`の3ケースで`DISK_HEADROOM_LOW`になった。E/Fの`/tmp`はtmpfsで約452.5MiBしかなく、製品側の1GiB予約条件を満たさない。一方、SD側には十分な空きがあった。Bの`/tmp`は約1.85GiBで同じ失敗は出なかった。

テストを無視したり、予約容量を小さくしたりせず、stageテストのTMPDIRを新release内のowner-privateなSD領域へ指定した。再stageでE/Fとも58件成功。旧失敗とpartial releaseは削除せず、[初回結果](results/bef-storage-repair/summary.json)と修正後結果を区別して残した。

## OS再起動確認

[最終確認JSON](results/bef-storage-repair/reboot-final-summary.json)。3台とも新boot、同じrelease／設定、別セッション、現在bootのheartbeatを確認した。

Eは初回の確認スクリプトでassertionにより未確認となったが、その後の再読で全比較条件が成立した。初回失敗時の候補状態を保存していなかったため、どの比較が失敗したかは確定できない。初回の未確認結果も[別ファイル](results/bef-storage-repair/reboot-summary.json)に保持した。

これはOSによる再起動試験であり、物理的な電源OFF/ON・SD断電耐性の実証ではない。

## 5分の有限時間監視

3台でsystemdの時間制限付き監視を起動し、その間に報告・Issue整理等を行った後、完了結果を回収した。チャットで無期限に待機する方式にはしていない。受信サービスとは別のプロセスで、送信や設定変更は行わない。

| ノード | 実行時間 | サンプル数 | 収録healthのFAULT数 | 観測したホスト空きRAMの最小値 | 最終状態 |
|---|---:|---:|---:|---:|---|
| B | 300.00秒 | 18 | 0 | 3391.4MiB | WAITING |
| E | 300.00秒 | 15 | 0 | 544.6MiB | WAITING |
| F | 300.00秒 | 17 | 0 | 539.7MiB | WAITING |

[監視集計](results/bef-storage-repair/monitor-collection-1/summary.json)／[CPU・RAM・空き・保存状況のCSV](results/bef-storage-repair/monitor-collection-1/resources.csv)。15秒待ちを指定したが、巡回処理時間も加わるため、厳密な15秒周期ではない。サンプル数の差を機種性能差とは扱わない。

空きRAMはホスト全体の値であり、収録プログラム単体の最大RAMではない。`MemoryCurrent`は取得できず、サービス使用量はnull／CSV空欄とした。`MemoryMax`の設定だけで実効制限を保証しない。既存のworker 128MiBアドレス空間上限、192MiB RAM余力判定、SD／セッション予算等は維持した。

FAULT 0は、監視した収録heartbeatが異常と判定されなかったという意味。WAITINGは対象RID受信待ちであり、RF全パケット取得・ドローン受信成功・4時間完走を意味しない。

## スキャン診断：権限拒否とbusyを分離

各台の直近60秒区間3本を調べた。全区間はduration_completeで終了。区間の終了コード3は新しい解析成功RIDがない場合の仕様であり、プロセス異常終了と区別する。

| ノード | スキャン要求 | 受理 | busy | permission／timeout等 | 対象ODID記録 |
|---|---:|---:|---:|---:|---:|
| B | 104 | 26 | 78 | 0 | 0 |
| E | 102 | 27 | 75 | 0 | 0 |
| F | 105 | 27 | 78 | 0 | 0 |

[診断JSON](results/bef-storage-repair/scan-diagnostics.json)。busyは残っており「すべてのエラーが解消した」とは言えない。この窓では権限拒否は確認されず、キャッシュ読取りも動いていた。要求数・受理数は物理パケット数／受信率ではない。台ごとに窓が異なるため性能比較にも用いない。busyを減らす観測・要求間隔の検討は#97の残件として扱い、新Issueを増やさない。

## テスト・残件

- ローカル：field-kit 25件、Week29解析61件、Pi関連58件、UAV 88件、Go、contracts 48件が成功。
- 実機：B/E/Fとも配置したPiコードの58件成功。E/FはSD上のTMPDIRで再実行し、実際に成功した後で有効化した。
- privateな生データや設定・鍵はGitへ追加していない。新コード／MDのcommit・push・CIは未実施。
- C/Dへの適用、Aの既存長時間監視結果回収、物理電源断、飛行中の実ドローン受信・4時間収録は未実行。
- 対象RID 0件の待機監視から、飛行時に必要な保存量を0と見積もらない。1GiB予算で4時間足りることの実測証拠はまだない。

GitHubのIssue整理は[全体管理 #88](https://github.com/SMRI2170/zkp-m1-v2/issues/88)と[整理報告](24_GitHub_Issue整理と引継ぎ.md)へ反映。実機作業は[#97](https://github.com/SMRI2170/zkp-m1-v2/issues/97)に集約し、全体OPENは9件のまま維持する。

## 利用者指示による終了（2026-11-18）

B/E/Fの収録サービスを正常停止し、MainPID=0・inactiveを確認してからsyncし、systemctl poweroffを実行した。3台ともコマンド終了0。自動起動のenabled設定は変更していない。[終了記録](results/bef-storage-repair/shutdown-summary.json)。物理的な給電停止・ケーブル抜去を確認したものではない。
