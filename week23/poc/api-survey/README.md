# #39 実装/API調査のビルド再現

```sh
python3 week23/poc/api-survey/prepare_arecibo.py
cd .cache/week23/sources/arecibo
RAYON_NUM_THREADS=2 cargo +stable test --locked --release -j 2 supernova::snark::test::test_nivc_trivial_with_compression -- --exact
```

upstreamのRust 1.79指定を今回stable 1.97.1で上書きした。ソースpatchは不要な括弧と未使用importの除去のみ。
依存のsppark 0.1.6 / proptest 1.2.0 / rand_chacha 0.3.1等を固定Cargo.lockで再現する。
暗号回路、検証条件、テストのassertは変更しない。1 testが実行されたことをログで確認する。
この標準テストはSuperNova/圧縮の実行確認で、Week23の分散秘密非共有PoCではない。

HyperNova開発ブランチの初回ビルド失敗はレポートとlogに保存。再現用lockは `manifests/sonobe-hypernova.Cargo.lock`。
ソースcommitは `9c4e61f8d1a5be87c00f28838a0ef657a3cf479f`、テストコマンドはレポート参照。
