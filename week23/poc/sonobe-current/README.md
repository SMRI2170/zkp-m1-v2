# HyperNova依存修正と最新Sonobeの実行検査

前提：固定ソースのignored clones（`../../manifests/sources.json`）、Rust stable、Python。
新しい出力directoryを作る。既存なら停止し、fixture/元失敗ログを保存する。

## HyperNova

```sh
python3 week23/poc/sonobe-current/prepare_hypernova.py
CARGO_TARGET_DIR=.cache/week23/target-hypernova-fixed cargo +stable test --release -j 2 --manifest-path .cache/week23/sources/sonobe-hypernova-fixed-v1/Cargo.toml -p sonobe-primitives -p sonobe-fs --lib
python3 week23/poc/sonobe-current/run_api_probes.py
```

prepareは元ツリーを保存し、別ツリーへ2ファイルだけの依存/API互換patchを適用する。
`hypernova-ark06.patch`と`hypernova.Cargo.lock`を保存。新規prepare後は保存lockをcopyして`--locked`で再現できる。
core arkworksは0.6.0、公式proc-macro helper 0.5.0は意図的な依存である。
probeはcompile結果を検査後、Cargoの通常targetから外して`.rs.checked`に保存する。
NovaBlindFold名の不在（expected failure）と、HyperNova IVC adapterの存在（expected success）を別に検査する。

## 最新mainの生状態・改竄・漏洩

```sh
CARGO_TARGET_DIR=.cache/week23/target-sonobe-current cargo +stable build --release -j 2 --locked --manifest-path week23/poc/sonobe-current/Cargo.toml
```

上流mainは無変更。wire adapterはProofの各fieldを明示serializeする。raw Witnessは意図的に含むため秘密保護転送には使わない。
A/B/Cを別プロセスで実行する：

```sh
.cache/week23/target-sonobe-current/release/week23-sonobe-current true .cache/week23/private/sonobe-current-h-true-v1 1
.cache/week23/target-sonobe-current/release/week23-sonobe-current true .cache/week23/private/sonobe-current-h-true-v1 2
.cache/week23/target-sonobe-current/release/week23-sonobe-current true .cache/week23/private/sonobe-current-h-true-v1 3
```

falseも別directoryで同様に実行する。各段で正常verify・22改竄拒否・Witness省略拒否をassertし、7合成canaryのfield/byte一致位置を出す。
実データ/秘密鍵は使わない。生proof/keyを公開しない。ログは公開可能なphase/count/一致位置のみ。
[評価と限界](../../10_HyperNova実行と最新Sonobe安全性と秘密引継ぎ.md)。

## 秘密非共有の一般再帰フォールバックを新しい観測で再実行

preflightでmemory/swapを確認する。既存private pcd setupを意図的に保存・検査して利用する。

```sh
cd week23/poc/private-pcd
go build -o ../../../.cache/week23/private-pcd-fresh .
cd ../../..
python3 week23/poc/private-pcd/run_fresh_chain.py
.cache/week23/private-pcd-fresh fresh-negative .cache/week23/private/zk-carry-fresh-v1
```

`inspected-fixtures.json`のsource/全artifact hash、現在ソースから再構築したCCS一致を必須とし、mismatch時は保存して停止。
A/B/Cは別process、前段からproof/publicのみを読む。private assignmentはRAMのみ。
RSS/swap停止上限あり。以前のfixtureを削除・上書きしない。再実行時はrunnerのOUTを新しい名前にする。
新しい合成観測はGPSを実測したものではない。
