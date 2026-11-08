# uli-net-sim導入とRemote ID相当Beaconの再現（Issue #70 / PR1）

実施日：2026-11-08。**本報告はシミュレータ導入・通信・既存位置偽装のSmokeを対象とする。検出性能の評価や実UAV実測ではない。** 最終実行状態は後述の集計JSONを正本とし、未実行の段階を完了扱いしない。

## Issueの確認と既存実装との境界

[#70](https://github.com/SMRI2170/zkp-m1-v2/issues/70)、[#66](https://github.com/SMRI2170/zkp-m1-v2/issues/66)、[#67](https://github.com/SMRI2170/zkp-m1-v2/issues/67)、[#68](https://github.com/SMRI2170/zkp-m1-v2/issues/68)の全文を取得し、コメントも確認した（4件ともコメントなし）。

| 正本 | 今回維持した条件 |
|---|---|
| #66 | 本来条件は非同期・別パケット・1観測1RSSI・各送信の電力は自由に変わり得る |
| #67 | RSSI予測・物理位置の識別・不整合検出・ZKPの計算検証を区別する |
| #68 | 実測取得・実測評価は別トラック。Dataset-21の取得失敗をsimulationで置換したことにしない |
| #70 | PR1の成功確認前にPR2の電力拡張・PR3の観測条件比較・PR4の検出性能評価へ進めない |

新規実装は`experiments/week27-rid-sim/`へ隔離した。Week25/26の数値実験、Week27の実測解析、ZKP、Flutter、観測者署名や既存の証明回路は変更していない。重い3D UIは作成しない（#69と重複させない）。

## 上流と利用範囲

[uli-net-sim](https://github.com/brycethebjorkman/uli-net-sim)の`main`は開始時に再取得し、SHA `3cf9474fe960955556de118065591915a7be2bc1`へ固定した。論文保存用`scitech26`は`c2ffa9d5d66594297b5875a9382572e56c94d12f`で、差分は194ファイル・23,655行追加・85,765行削除。今回のmainを動かしても、[SciTech論文](https://doi.org/10.2514/6.2026-2665)の性能を再現したことにはならない。

上流ルートにLICENSEはなく、個別ファイルのSPDX表記をリポジトリ全体の許諾とは扱わない。上流ソースは`.cache/issue70/uli-net-sim/`に置いた**ローカル依存**であり、ソース・バイナリ・コンテナ・改変版は本Gitへ追加しない。今回追加したものは独自の構築アダプタ・設定・監査・テスト・報告である。

## 環境と導入時の試行

| 項目 | 内容 |
|---|---|
| 実行ホスト | macOS 27.0.1 / Apple Silicon arm64 / RAM 16 GiB |
| コンパイラ | Apple clang 21.0.0 |
| OMNeT++ | 6.2.0 core版、配布SHA-256照合済み |
| INET | 4.5.4、配布SHA-256照合済み |
| Eigen | 5.0.0、配布SHA-256照合済み |
| 実行用Python | 3.12、最小Smoke用venv。上流全ML依存の導入ではない |
| メモリ・容量 | `memory_pressure`、`vm.swapusage`、空きディスクを確認。ビルドは2並列まで |
| GUI | Qtenvなし。OSGライブラリは必要。GUI/3D画面の起動は未実行 |
| Linux | ネイティブシミュレータのビルド・実行は未実行 |
| Docker | CLIあり、daemon未起動。コンテナ経路は未実行 |

導入時の失敗も残した。

1. 初回configureは`pkg-config`なしで失敗。依存を導入して再試行。
2. macOS標準GNU Make 3.81は`$(file ...)`を利用するOMNeT++のビルドで失敗。Homebrew GNU Makeを導入して再試行。
3. Qtenv/OSGを両方無効にした構成でOMNeT++・INETはビルド成功。しかし上流本体の`MultirotorMobility::drawWaypointPath()`は`if constexpr`内のOSG型を参照し、OSGなしでコンパイル失敗。非テンプレート関数内の条件分岐だけでは未定義型を排除できない。
4. モジュールや物理モデルを削除せず、OpenSceneGraph 3.6.5を導入。Qtenvなし・OSGありのCLI構成でビルド成功。
5. 最初の実行は`WITH_NETBUILDER=no`のためNED読み込みで終了コード1。設定を`WITH_NETBUILDER=yes`へ修正して再ビルド。偽装ケースはこの試行では未実行。
6. 途中で実行中のビルドスクリプトを更新してしまい、シェルの読み取り位置がずれて`se: command not found`（127）となった試行も保存。安定した内容で再実行して成功。再発防止として、setupはスクリプトの固定コピーとハッシュを実行ごとに保存するよう修正した。

## PR1の実験設定

`config/smoke.json`と`config/smoke.ini`を正本とする。

| 条件 | 設定 |
|---|---|
| ケース | Normal / StaticSpoof |
| seed | 両方2170 |
| 時間 | 4 simulator seconds |
| ノード | 移動する送信UAV 1、地上の固定受信専用ノード2 |
| 送信 | 0.5秒間隔、初回オフセット0.1秒、startup jitter 0、固定13dBm |
| PHY | INET 4.5.4既定のFreeSpacePathLoss、Ieee80211DimensionalRadio、DipoleAntenna、Wi-Fi channel 6、背景雑音−100dBm |
| 正常 | 上流RidBeaconMgmtの実位置申告 |
| 攻撃 | 上流の既存StaticLocationSpooferMgmtによる固定偽位置申告 |
| paired条件 | seed・実軌跡・管理層送信時刻・送信電力の一致をログで検査 |
| 判定器 | なし。全件UNDETERMINED、score/FPR/TPRはnull |

同じ送信を2局が受ける構成は、通信・packet ID・GCSの監査に使う**追加条件の比較対照**であり、本来の非同期問題を解く方式としない。申告位置変更の再現と、RSSIから偽装を検出できたことは別である。

## 記録と監査

正規化は上流Parquetの行順に依存せず、実際の`.vec`のETVイベント番号・時刻・管理モジュールを使用する。TX/RXはpacket tree IDで厳密に対応させる。申告ID・申告時刻の近接だけで結合しない。

- 管理層のenqueueを全TX候補母数に保存する。PHYで実送信された件数と断定しない。
- TX×設定受信機の機会を作り、受信がなければ`NOT_OBSERVED`とする。PHY拒否・MAC drop・終了時の未完了は未分離。
- `Reception Power`が同じ受信イベントに存在する場合だけRSSI値を使う。欠けた場合はnull。0dBmの初期値を測定値に見立てない。
- GCSの受信報告総数とRX総数を検査する。ただし上流GCSは`(serial, ridTimestamp)`で束ね、Pythonへは先頭レポートのpacket IDのみ渡す。衝突・再利用耐性を実証したことにはならない。
- 上流StaticLocationSpooferの`fillRidMsg`は位置だけを設定し、基底実装の識別子・時刻設定を呼ばない。受信ログに現れた値を維持し、正常なID・時刻へ補修しない。
- 真位置・真の送信電力・攻撃ラベルはシミュレーションの監査用真値。検出器の入力ではない。

列の由来・null条件は[field-map.md](../experiments/week27-rid-sim/schema/field-map.md)、形式は[JSON Schema](../experiments/week27-rid-sim/schema/observation.schema.json)を参照。

## 再現コマンド

```sh
python3 experiments/week27-rid-sim/scripts/setup.py \
  --stage build --jobs 2 --out .cache/issue70/build-NEW

.cache/issue70/python/bin/python experiments/week27-rid-sim/scripts/run_smoke.py \
  --raw-dir captures/issue70-smoke-NEW \
  --summary-dir week27/results/uli-net-sim-smoke-NEW

python3 -m unittest discover -s experiments/week27-rid-sim/tests -v
```

詳細な依存コマンド・pin SHA・終了コードの意味は[README](../experiments/week27-rid-sim/README.md)に記載。出力先は既存結果を上書きしない名前にする。

生の`.vec/.sca`、実コマンド・ログ、正規化CSV/Parquet、TX ledger・GCS CSVはignored `captures/`へ所有者のみアクセス可能な状態で保存する。Gitには集計件数・ログハッシュ・個人情報を含まない構築ログのみを追加する。

## 段階ごとの実行状態

**PR1の最終状態は`PR1_SMOKE_PASSED`。** 正本は[最終集計JSON](results/uli-net-sim-pr1-20261108-c/summary.json)、[ケース別CSV](results/uli-net-sim-pr1-20261108-c/case-summary.csv)、[対比較監査](results/uli-net-sim-pr1-20261108-c/paired-audit.json)。

| 実際に記録された値 | Normal | StaticSpoof |
|---|---:|---:|
| 実行終了コード | 0 | 0 |
| 管理層enqueue件数 | 8 | 8 |
| TX×受信局の機会数 | 16 | 16 |
| RX件数／RSSI値数 | 16／16 | 16／16 |
| 受信記録なし／RSSI欠測 | 0／0 | 0／0 |
| GCS処理件数／受信報告総数 | 8／16 | 8／16 |
| 真位置と申告位置のずれ | 0m | 約100.000〜100.582m |
| 受信された申告serial | 1 | 0 |
| 申告時刻の異なる値の数 | 8 | 1 |
| FPR／TPR | 未評価 | 未評価 |

実軌跡・enqueue時刻・送信電力の一致を確認し、同じ機会のRSSI差の最大値は0dBだった。RSSIの範囲は両方とも約−63.599〜−63.583dBm。これは**この設定で既存の偽申告と正常通信を再現できた**結果であり、RSSIを用いて偽装を検出できたことではない。

特に、既存StaticLocationSpooferでは**位置以外にID・申告時刻も正常実装と異なる**。従って「位置だけを変えた公平な攻撃性能比較」はまだ成立していない。PR2以降ではID・時刻の差を除いた対照が必要。PR1では上流の挙動を隠さず残した。

建物を追加せず、独立したRSSIノイズ・相関遮蔽・マルチパスの校正もしていない。4秒・1seedの通信Smokeのため、この100%受信を実環境の到達率や方式の頑健性へ一般化しない。

未実行：PR2〜PR4、KF/MLAT/MLPの性能評価、20seed評価、非同期1時間ケース、動的電力の物理反映、30m安全距離判定、実UAV Remote ID測定、GUI、Linux上のシミュレータ実行。

## テストとログ

- アダプタ専用テスト：18件成功。ETV対応、欠けたRSSIのnull保持、受信なしの母数、ID厳密結合、重複拒否、GCS件数、環境不成立時の`NOT_RUN`を検査。
- 既存必須チェック：UAV Python 61件、`aggregator`のGoテスト、`contracts`の48件が成功。
- 既存Week27解析＋前作業のローカル取得ゲート：54件成功。うち5件は先行するDataset-21取得作業の未コミットテストで、本PR1の変更には含めない。
- CIのアダプタテストは合成unit fixtureのみ。OMNeT++実行成功の証拠はローカルの実行ログと集計であり、CIの緑をシミュレータ実行と呼ばない。

[公開ログ](results/uli-net-sim-pr1-20261108-c/logs/)には、実シミュレーション・変換ログ、テスト出力、ビルド試行の診断とハッシュ、コマンドの記録を保存した。絶対ワークスペースパスを`${REPO}`へ置換し、公開ログの末尾空白を整形している。元の全ビルドログは`.cache/issue70/logs/`および`.cache/issue70/build-final-cli/`、生データは`captures/issue70-smoke-20261108-c/`に保持。

[初回失敗の集計](results/uli-net-sim-pr1-20261108-a/summary.json)も保存し、最終成功で上書きしていない。再実行bとcは独立seed試行ではなく、コード変更後の再確認である。GitHub Actionsの結果は公開後に確認し、別途記録する。
