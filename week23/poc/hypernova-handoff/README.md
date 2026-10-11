# HyperNova IVCとrandom-fold引継ぎの実行probe

前提：10で作成した固定revamp/hypernova＋arkworks 0.6互換patch、Rust stable。
上流のrelation/verifier/gadgetは変更しない。新規exampleを追加するだけ。
実行前にmemory/swapを確認する。今回16 GiB/free 56%/swap used約5.20 GiB、cargo -j 2、test-threads=1。

```sh
CARGO_TARGET_DIR=.cache/week23/target-hypernova-fixed cargo +stable test --release -j 2 --manifest-path .cache/week23/sources/sonobe-hypernova-fixed-v1/Cargo.toml -p sonobe-ivc hypernova -- --nocapture --test-threads=1
cp week23/poc/hypernova-handoff/blinding.rs .cache/week23/sources/sonobe-hypernova-fixed-v1/crates/ivc/examples/week23_blinding.rs
CARGO_TARGET_DIR=.cache/week23/target-hypernova-fixed cargo +stable run --release -j 2 --manifest-path .cache/week23/sources/sonobe-hypernova-fixed-v1/Cargo.toml -p sonobe-ivc --example week23_blinding
```

IVC3段、valid random running instanceのsample、2→1 random foldとNIMFS verify、
full IVC差替え拒否、公開hash更新のみの拒否、無効状態からprove後のfinal verify拒否、
Witness削除拒否、公開state5項目改竄拒否をassertする。
単一processのAPI/関係検査であり、秘密非共有A/B/C network実証ではない。
key/proof/witnessはメモリ内、stdoutはphase/件数/公開できるerrorのみ。Groth16/VK/proofのdeploy/publishはない。
[結果と限界](../../11_HyperNova_IVCとブラインド状態引継ぎの検証.md)。
