# A・CのWi-Fi Beacon観測環境構築

2026-11-10。Bのパスワード復旧中に、ユーザーの依頼でA・Cへ同じ観測環境を用意した。

## 配置と確認結果

| 項目 | A | C |
|---|---|---|
| 機器名／観測ID | observer-a | observer-c |
| 機種 | Raspberry Pi 4 Model B Rev 1.5 | Raspberry Pi 3 Model B Plus Rev 1.3 |
| RAM | 約3.8GiB | 約0.9GiB |
| Python／iw | Python 3.11／iw 5.19 | Python 3.11／iw 5.19 |
| 受信経路 | brcmfmac内蔵Wi-Fiの通常スキャンキャッシュ | 同左 |
| Pi上の合成単体テスト | 16件成功 | 16件成功 |
| 12秒の読取り | 4秒間隔、3回成功 | 同左 |
| BSS項目 | 各回1項目、延べ3項目 | 同左 |
| ODID記録／新鮮なODID | 0／0 | 0／0 |
| 子プロセス最大RSS | 21,632KiB（約21.1MiB） | 21,472KiB（約21.0MiB） |
| 検証後MemAvailable | 3,346,128KiB | 575,884KiB |
| NTP同期状態 | yes | yes |

延べキャッシュ項目数は独立パケット数ではない。今回はODIDを検出しておらず、実ドローン受信・位置偽装検知・2局同一送信照合の成功ではない。NTPのyesは時計オフセットや同期精度の実測ではなく、時間誤差のフィールドはunknownのまま維持する。

## 使用方法（A・C共通）

各Piのユーザーpiで実行する。

```sh
# 設定・インタフェース・依存・資源上限を確認
~/zkp-beacon-observer/run --check

# 合成パケット／キャッシュ形式／保存権限の16テスト
~/zkp-beacon-observer/run --self-test

# 60秒の観測。完了時にJSON集計を出力
~/zkp-beacon-observer/run --duration 60 --interval 5
```

`run`は各Piの設定にあるobserver-a／observer-cを自動使用する。手動起動する設計であり、再起動後の自動収録や無期限のバックグラウンド処理は設定していない。

終了コード0は新鮮なODIDデコードが1件以上、3は該当ODIDなし、2は実行失敗。今回のA・Cはともに3であり、観測プログラムのクラッシュや偽装判定ではない。

## 構成・資源保護

- 配置先：`~/zkp-beacon-observer/releases/0cdddec858bf/`。
- 現行リリース：`~/zkp-beacon-observer/current`。7ファイルのSHA-256を両Piで照合済み。
- 個別設定：`~/zkp-beacon-observer/config/node.json`。受信局座標はnull、インタフェースwlan0。
- 生観測：各releaseの`captures/<node_id>/<UTC run_id>/observations.jsonl`。
- 実行サマリー：同ディレクトリの`summary.json`。失敗時stderrはprivateの`errors.log`。
- capturesディレクトリ0700、ファイル0600。原始観測・IP・端末MAC・パスワードは公開結果へ含めない。
- Linux RLIMIT_AS 128MiB、1ファイル20MiB、core dump禁止、nice +10、既定60秒・最大3600秒。
- 実行期限を20秒超えた子プロセス群は停止し、途中のログを保持する。SSHやOS全体のメモリ制限は変更しない。
- 既存設定が異なる場合は上書きせず停止する。旧releaseとAの以前の`~/zkp-beacon-adapters/20261109-a/`は保持した。
- 新しいPythonパッケージの導入は不要。今回はOS更新・Wi-Fi切断・チャネル変更・monitor切替えを実行していない。

導入用コードは `experiments/week28-beacon-observers/install_node.py` と `run_observer.py`。接続先や資格情報をコードへ固定していない。Bも復旧後に同じreleaseを配置し、`--node-id observer-b`で設定する。

## 残件

1. Bのパスワード復旧と機器名observer-bの設定後、同じ環境を配置する。
2. 既存Flutterで受信できた実ドローンを使い、A・CのVendor IE取得を確認する。
3. 通常スキャンの更新頻度・古いキャッシュ・欠測・端末差を測る。生フレーム取得が必要ならmonitor対応機材を別途用意する。
4. 時刻精度・受信局座標・独立真値等が揃うまで、GhostBusterの実測FPR/TPRは生成しない。

実行ログと集計は `results/observer-ac-setup-20261110-a/`。公開したログは合成テストと匿名化した件数・資源値のみであり、rawスキャン内容は含まない。

変更後のローカルチェックもPython77件、Go、contracts48件が成功した。
