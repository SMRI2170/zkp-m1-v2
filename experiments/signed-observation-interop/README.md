# 署名付き観測のGo→Rust互換性検査

Issue #50の「共有statementと入力表現」を実装する。Joltへ移す前に、既存gnarkのMiMC・EdDSA・Session/Policy/RID/index/countの意味を照合する。
[共有仕様](SPEC.md)を正本とする。元のgnark回路、過去ログ、Kimchi／Binius64／Joltの距離ベンチは変更しない。

```sh
rustup toolchain install 1.97.1 --profile minimal
python3 experiments/signed-observation-interop/run.py --out /path/to/NEW-run
cargo +1.97.1 test --manifest-path experiments/signed-observation-interop/core/Cargo.toml --locked -j 1
```

`NEW-run`は未使用のディレクトリを指定する。`run.py`はGo baseline sourceをhash照合し、一時test binaryを作る。
合成Witnessは匿名pipeだけでGo→Rustへ渡す。private key／assignmentをstdoutの公開ログやファイルへ保存しない。
保存するのは`results.json`（case名・判定）と`metadata.json`（version・source hash・限界）だけ。
一時packageはowner-onlyのignored `.cache/week24/`配下で、処理終了時に削除する。診断stderrがある場合はignored owner-only領域に保持。

- 正常3件：count=1/2/4。新しいrandom test observer keyで署名した同一の合成観測。
- 拒否37件：session／policy／RID／root／座標／root上下／S／PK／別署名者／配列切詰め、n>=2で順序入替と重複。
- Go側の拒否はconstraint solver。配列切詰めだけはenvelope形状の拒否条件。
- Rustはnative参照検証。ZKPの生成・verifier拒否ではない。

追加のcanonical field／曲線generator-orderテストをRust unit testで実施する。
同じhash・署名式でもPK/R/encodingの受付検査には境界差があるため、[仕様の差分表](SPEC.md#入力受付の境界差)を必ず読む。

## RISC-Vへ移せるかのコンパイル検査

```sh
rustup target add --toolchain 1.97.1 riscv64imac-unknown-none-elf
cargo +1.97.1 check --manifest-path experiments/signed-observation-interop/core/Cargo.toml \
 --lib --target riscv64imac-unknown-none-elf --locked -j 1
```

これはno_std libraryのtarget check。Jolt guest ELF生成、VM実行、trace測定、proof生成の成功ではない。

## 次の1タスク

このcoreを、固定Jolt版の`PrivateInput`とhost `zk`を使うn=1のguestへ接続する。
まずguest実行とtraceの規模を調べ、MacのRSS／swap制限内で実proveできるか判定する。PiはMacの正当性・資源確認後。
Kimchiのfield／非native曲線演算、Binius64のhash／署名gadgetはそれぞれ別の移植タスクとして扱う。

nativeの処理時間からJoltのprove時間・Pi性能・形式的ZKを推定しない。
DRIP trust chain、sensor honesty、observer hardware／航空機認証は対象外。
