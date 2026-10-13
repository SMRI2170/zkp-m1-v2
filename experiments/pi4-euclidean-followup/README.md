# 未完了方式の追加実行

既存の版・source／binary hashと失敗runを保持し、別package・別runで追加評価する。
[結果](../../week24/06_未完了方式の追加実行.md)ではPiとMac、guest buildと実proof、Coreと最終ZKを分ける。

- Plonky2：元packageを変更せず同一binaryをPiでCPUQuota25%、親／子Max1536MiB、Swap0、watchdog／SSH保護の下で再実行。Macにも同一sourceをnative build。
- Halo2 KZG：別packageで公開r単独改変の拒否検査を追加。元のd2改変・proof改変・6負例も保持。
- SP1 6.9.0／RISC Zero3.0.6：private座標4つ、public d2とrの合成guestを実装。座標16bit、d2 33bit、r17bit、平方根slack18bitを同じ条件でassert。実観測・RID／センサ真正性の証明ではない。
- SP1 hostは明示的local CPU。Core proofはcompressed／最終ZK wrapperではない。
- RISC Zero hostは明示的LocalProver。Bonsai／network／dev-modeへのfallbackを使わない。

`run_host_guarded.py`はMacのprocess-tree RSS4GiB／swap増分512MiB／timeoutを監視する。
100ms samplingによるsoft monitorであり、Piのcgroup hard limitと同等ではない。Mac結果はPiグラフへ混ぜない。
使い捨て鍵・proof・private assignmentを保存・Git追加・deployしない。

## SP1

公式v6.9.0 CLIで`cargo-prove prove install-toolchain`を実施。デフォルトRustは変更しない。

```sh
# program directoryで実行。TARGET／CLI／ELF_DIRはignored directoryの絶対path。
CARGO_BUILD_JOBS=1 CARGO_TARGET_DIR="$TARGET" "$CLI" prove build --output-directory "$ELF_DIR"
# repository rootでhostを構築。再現時はlockを使用。
CARGO_TARGET_DIR="$HOST_TARGET" cargo build --manifest-path experiments/pi4-euclidean-followup/sp1/host/Cargo.toml --locked --release -j 1
python3 experiments/pi4-euclidean-followup/run_host_guarded.py --out "$NEW_RUN" -- "$HOST_BINARY" "$GUEST_ELF"
```

## RISC Zero

公式cargo-risczero3.0.6の`install`はrzupへ移行済み。rzup0.5.0を公式S3から取得し、
Rust1.88.0をtask用RISC0_HOMEへ導入。MetalToolchainはXcodeの公式component downloadで導入。
Docker CLIは存在したがdaemonが起動していなかったため、guestはnative toolchainでbuild。host側で上流risc0-buildと同じV1COMPAT kernelを包みProgramBinaryを生成する（RAMのみ）。bare ELFのままではMalformed ProgramBinaryで拒否される。

新規の依存解決ではruint1.20.1等のMSRVがguest Rust1.88を超える。
固定releaseのCargo.lockに合わせruint1.16.0、enum-ordinalize4.3.0／derive4.3.1を固定した。

```sh
# guest directory。上流risc0-build3.0.6と同じatomic lowering、TEXT_START、panic/entry flags。
CARGO_BUILD_JOBS=1 CARGO_TARGET_DIR="$TARGET" \
 RUSTFLAGS='-C passes=lower-atomic -C link-arg=-Ttext=0x00200800 -C link-arg=--fatal-warnings -C panic=abort --cfg getrandom_backend="custom"' \
 cargo +risc0 build --locked --release --target riscv32im-risc0-zkvm-elf
CARGO_TARGET_DIR="$HOST_TARGET" cargo build --manifest-path experiments/pi4-euclidean-followup/risc0/host/Cargo.toml --locked --release -j 1
python3 experiments/pi4-euclidean-followup/run_host_guarded.py --out "$NEW_RUN" -- "$HOST_BINARY" "$GUEST_ELF"
```

Pi向けcross buildではLinux ARM64 sysroot／C・C++ヘッダーも必要。
現在のclang＋rust-lldだけではzkVM hostの依存C codeを構築できず、実エラーを結果に残す。
`RISC0_SKIP_BUILD_KERNELS`やmock、制約削除でビルド・検証を成功扱いにしない。
