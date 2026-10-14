# Kimchi・Binius64・Joltの追加比較

[Week24結果](../../week24/07_Kimchi_Binius64_Joltの追加評価.md)に実行段階・成功／停止・残件を記録する。
合成整数ユークリッド距離のみ。実RID、観測の真値、DRIP、sensor／observer hardware、航空機認証の評価ではない。

|package|固定source|実装|
|---|---|---|
|kimchi|o1-labs/proof-systems `92274448`|Vesta IPA、Generic gate＋copy permutation。座標16bit／d2 33bit／r17bit／slack18bit。SRSは必要domainサイズで透明生成、RAMのみ|
|binius64|binius-zk/binius64 `4428e759`|64bit整数演算・overflow／borrow／範囲を拘束。ZKProver／ZKVerifier、SHA256、log_inv_rate1。coordsはwitness、d2/rのみinout|
|jolt|a16z/jolt `8b6099f7`|PrivateInput＋host zk（BlindFold）。public d2/r、return true、panic=falseを確認。guest private入力をverifier引数へ渡さない|

[共通7ケースと6不正入力](cases.rs)は合成値。Joltは6不正入力でpanic=trueとなり、panic=falseとする成功計算のclaimを実verifierが拒否することを検査する。
Kimchiの6負例はindex witnessチェック、Binius64の6負例はfrontend populationチェック。
公開d2／r・proof改変の検査は実verifierを呼ぶ。frontend拒否と、不正assignmentを強制して実proofを生成／拒否する検査を混同しない。

Kimchiは上流helperのprecomputed SRS読み込みを使わず、custom SRS factoryを通じて
`SRS::create(domain_size)`とLagrange basisをRAMで生成。回路・gates checks・blindingを保持する。
Macに埋め込まれたfixtureパスがPiに存在しない問題を、filesystem移植やチェック省略で回避しない。

Binius64は上流と同じrand0.10.1でOS由来のrngを使用。
Linux ARM64への標準cross buildはBlake3のC/NEON toolchain不足で失敗したため、
`portable-blake3` featureで同じBLAKE3を純Rust実装で計算するvariantを追加。
暗号方式・ZK設定・制約は変更しない。portableとnative SIMDの性能を同条件扱いにしない。

Jolt依存workspaceのarkworks patchは最上位host manifestにも必要。
crates.ioと上流forkを混在させず、上流のdev/twist-shoutをlock内のcommitへ固定する。
`PrivateInput`だけでは十分ではなく、hostの`zk` featureを外さない。
これは単一Proverのproof秘匿評価で、Week23の跨Prover状態引継ぎの不採用判断を変更しない。

## ビルド

Rust stable1.97.1（Kimchi/Jolt）と1.98.1（Binius64）を使用。default toolchainは変更しない。

```sh
rustup toolchain install 1.98.1 --profile minimal --target aarch64-unknown-linux-musl
rustup target add aarch64-unknown-linux-musl riscv64imac-unknown-none-elf
python3 experiments/pi4-euclidean-next/build.py kimchi
python3 experiments/pi4-euclidean-next/build.py binius64
python3 experiments/pi4-euclidean-next/build.py jolt
python3 experiments/pi4-euclidean-next/build.py jolt --target aarch64-unknown-linux-musl
python3 experiments/pi4-euclidean-next/build.py kimchi --target aarch64-unknown-linux-musl
python3 experiments/pi4-euclidean-next/build.py binius64 --target aarch64-unknown-linux-musl --portable-blake3
```

Git dependencyの標準取得では、proofと無関係なOptimism／Solidity／RISC-Vテストsubmoduleまで取得して停滞した。
`build.py`はignored checkoutのHEAD・tracked sourceの一致を確認し、同じpackageをpath dependencyで構築する。
使うsourceやfeatureを省かず、無関係なtest submoduleのnetwork取得だけを避ける。
実効manifest・registry lock・build結果は保存する。公開manifestのGit設定と実効path設定は別なので、
再現時はこのdriverを使う。既存／不完全dependency・proof／setup cacheは削除しない。

Macは[host monitor](../pi4-euclidean-followup/run_host_guarded.py)でRSS4GiB／OS swap増分512MiB／timeoutを監視。
Piはroot slice1536MiB、Swap0、OS available1GiB、外置きwatchdog、SSH -900を確認し、
CPUQuota25%と子unitのMemoryMaxを明示して実行する。
setup keys／VK／proof／private assignment実体はRAMのみで、Git公開・deployしない。

Jolt CLIは固定checkoutを`cargo +stable build --locked --release --bin jolt -j1`で構築。
CLIだけはrelease LTO=false、debug0でビルド資源を抑えた。guest/proofの制約・ZK featureはそのまま。
実行時は`JOLT_PATH`をCLIへ指定し、driver生成のhost package directoryから実行する。
Jolt hostのproofサイズはbincode、Kimchiはrmp-serde、Binius64はraw transcriptであり、形式は異なる。


公開guest ELFをMacで生成・hash検査してPiへ送れば、PiにRust／CLIを追加せず実行できる。
`week24-euclidean-jolt --elf <public-guest-ELF> --quick` は3–4–5の正常1件とroot low/highの不正2件。
`--quick`を外すと正常7件・不正6件。quickのcase_id0は共通CASES[1]。
SRS／proofをELFに含めない。`PrivateInput`と`zk` featureを維持する。
初回ARMバイナリは変更前の起動経路でCLI不足により停止し、source mtimeを更新して再buildした。
driverはcopy2のmtime保持によるCargo fingerprint再利用を避け、copy時にmtimeを更新する。

記録の検査（新しい証明生成は行わない）：

```sh
python3 experiments/pi4-euclidean-next/check_results.py
python3 experiments/pi4-euclidean-next/plot_results.py
```
