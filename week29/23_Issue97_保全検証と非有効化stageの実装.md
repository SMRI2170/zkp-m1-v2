# Issue97：保全検証と「有効化しないstage」の実装

> 後続更新：B/E/Fへの実機適用・OS再起動・5分監視を実施した。[最新報告25](25_B_E_F保存修正とOS再起動確認.md)を参照。この文書の未実行表記は当時の状態として保持する。

## 今回進めた範囲

B〜Fの接続を再確認したが、今回も既知のホスト名・IPではTCP接続できなかった。実機への転送・更新・再起動は0件。接続待ちを繰り返す代わりに、次の2つを実装した。

1. `experiments/field-kit/preserve_receiver.py`：全releaseのcapturesと設定を保存し、集合・サイズ・SHA-256を検証する保全処理。
2. `experiments/field-kit/stage_receiver.py`：更新直前の実機保全が成立した場合だけ、新releaseの配置とテストを行う処理。**サービスは有効化しない**。

## 回収済みBデータで実際に検証

`captures/week29/nodes/b/raw`が指す保全済みコピーを入力に、オフラインモードで実行した。公開するのは集計だけで、生記録とアーカイブはignored `captures/`に所有者専用で保存する。

| 項目 | 結果 |
|---|---:|
| 対象 | 保全済みBの11 releaseにあるcaptureファイル |
| 検証ファイル数 | 5,563 |
| 元ファイル合計 | 407,925,237 bytes（約389MiB） |
| 作成アーカイブ | 22,113,700 bytes（約21.1MiB） |
| 処理時間 | 約3.28秒 |
| 子プロセスのピークRSS | 約41.2MiB |
| 元ファイルの最終照合 | ファイル集合・サイズ・SHA-256・stat情報が一致 |
| 更新直前の実機保全として採用 | 不可：オフラインコピーの検証 |
| 今回の入力に設定ファイル | 含まれない |

[匿名集計JSON](results/issue97-offline-b-preserve-b/summary.json)／[集計CSV](results/issue97-offline-b-preserve-b/metrics.csv)／[検証記録](results/issue97-offline-b-preserve-b/validation.json)。処理時間・RSSは今回のMac上の値であり、Pi上の性能ではない。旧a出力も保持した。アーカイブのchecksumと詳細manifestは非公開receipt内に保持し、公開JSONには掲載しない。

## 保全処理の条件

- 通常モードでは、対象node_idと既存設定の一致、および受信サービスがinactive／failedかつMainPID=0であることを確認する。停止操作はプログラム自身では行わない。
- `--offline-copy`は既存コピーの検証用。実機の停止状態を確認したことにせず、manifestにも別モードを明記する。
- 全releaseのcaptureとconfigに限定。symlink、FIFO等の非通常ファイル、範囲外パス、空のcapture集合は拒否する。
- 同じ元ファイルを読みながらハッシュを計算し、アーカイブへの書込み前後と最後の再走査でも確認する。新しいファイルの追加や途中の変更を検出したら成功扱いにしない。
- 不完全なJSONL末尾もバイト列のまま保持し、パース修復・切捨てをしない。
- 既存アーカイブは上書きしない。失敗した`.partial`も保持する。検証が成立したものだけ正式名へ確定する。
- 圧縮・ハッシュはストリーム処理。ファイル全体をRAMへ読み込まない。件数・総サイズ・処理時間と保存先の空き容量に上限／余力の確認を設けた。

これはファイルが観測範囲内で変わらないことの検査であり、OSの原子的なfilesystem snapshotや悪意ある機器の真正性証明ではない。

## stageの条件と検証

新releaseの配置前に、保全アーカイブの全内容を再検証する。オフライン保全は拒否し、実機の現ファイル集合・設定・サービス定義と保全時の情報が一致することを要求する。

コードkitはmanifest、source_hash、Piソース集合、インストーラとアーカイブのハッシュを照合する。既存`install_pi.py`を**`--activate`なし**で使用し、Linux・RAM・SD空き・依存関係の既存チェックを維持する。配置後はソースハッシュを確認し、既存インストーラのWi-Fiテストに加えてPi関連テストも実行する。その後、旧capture・設定・currentポインタ・サービス定義が変わっていないことを確認する。

今回の実データアーカイブをstageへ渡したところ、`Offline copies cannot authorize live staging`で期待どおり拒否した。インストーラ実行には到達していない。これをstage成功や導入成功とは数えない。

stage成功経路は合成fixtureとmockインストーラで試験した。実Piへのstageは未実行。kitのハッシュ検証は配布者署名やハードウェア認証ではない。

## 再現コマンド

回収済みコピーの検証（出力名は新しくする）：

```sh
python3 experiments/field-kit/preserve_receiver.py \
  --base captures/week29/nodes/b/raw \
  --archive captures/week29/issue97-offline-next/preserved.tar.gz \
  --receipt captures/week29/issue97-offline-next/receipt-private.json \
  --offline-copy --timeout 600
```

接続復帰後、別途受信を正常停止して状態を確認したうえで、Pi上のコードcheckoutから通常モードで保全する。生アーカイブの保存先は元の`zkp-beacon-observer`ツリーの外のowner-privateなcapturesに置く。`--offline-copy`を付けた結果を導入の根拠にしない。

```sh
# 以下は実Piで未実行の手順。既存接続・保全・資源条件を満たす場合のみ使用
python3 experiments/field-kit/preserve_receiver.py \
  --base "$HOME/zkp-beacon-observer" --node-id observer-b \
  --archive captures/pre-update-b/preserved.tar.gz \
  --receipt captures/pre-update-b/preservation-private.json

python3 experiments/field-kit/stage_receiver.py \
  --base "$HOME/zkp-beacon-observer" --node-id observer-b \
  --archive captures/pre-update-b/preserved.tar.gz \
  --kit .cache/receiver-kit \
  --receipt captures/pre-update-b/stage-private.json
```

2つ目のコマンドを実行できても、新サービスの有効化は行わない。次の有効化・旧設定保持・復旧確認は別段階である。アーカイブ・receipt・失敗ログをGitへ追加しない。

## テストと残件

field-kit全24件が成功（保全7件、stage5件、既存監査・kit12件）。既存Pi 58件、UAV 88件、aggregatorのGoテスト、contracts 48件も成功。旧データ保持、不完全末尾、symlink／非許可パス、途中で増えたファイル、失敗partial保持、改竄／欠落／重複したtar、稼働中サービス、node_id不一致、kit改変、オフライン結果の誤採用防止、stage失敗時の旧current保持を検証した。

今回、B〜Fへの実機変更、更新直前の実機保全、実機stage・有効化、順次SSH転送と中断からの再開、自動起動復旧、4時間収録は未実行。実機へ接続できる状態が必要。コードはローカルでありcommit／push・CIは未実施。
