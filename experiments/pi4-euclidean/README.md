# Pi4：同じ整数ユークリッド距離を各方式で検証

2次元の合成整数座標を使う研究用ベンチ。実座標、Remote ID、センサーの真値、
航空機やobserver hardwareの認証を含まない。ユークリッドの互除法ではない。

- private：`x1,y1,x2,y2 ∈ [0,65535]`（u16）。
- public：`d2=(x1-x2)²+(y1-y2)²`（u33）、`r=floor(sqrt(d2))`（u17）。
- `d2-r²`、`(r+1)²-d2-1`をそれぞれu18に制限し、`r² ≤ d2 < (r+1)²`を拘束する。
- 座標は無符号オフセット整数。小数・負座標・3次元・実地較正は対象外。

平方根の候補は整数oracleがwitness生成時に計算し、回路で上記不等式を検証する。
平方根の浮動小数点近似をpublic出力として信用しない。
有効なd2は最大8,589,672,450、rは最大92,680。18bit slackはこの範囲に十分で、
全中間積は各方式のscalar fieldより小さい。負の差はfield演算で二乗するが、
入力・出力・slackのbit制約により整数演算との対応とfield wrapの拒否を保証する。
Noirはu64/u32 public型＋明示上限、Halo2はPasta field、他はBN254。

|実装|回路／native実行|証明の境界|
|---|---|---|
|gnark Groth16|`gnark/main.go`、R1CS|距離2値の個別ZKP|
|gnark PLONK|同じDefine、SCS|距離2値の個別ZKP、unsafe test SRSを使用|
|Circom/RapidSnark|`circom/euclidean.circom`、`bench.cjs`|距離2値の個別Groth16|
|Nova/CycleFold|`sonobe/src/main.rs nova`|単一Prover IVC、最終ZKなし|
|HyperNova/CycleFold|同ファイル `hypernova`|単一Prover IVC、最終ZKなし|
|Noir/Barretenberg|`noir/src/main.nr`、`bench.py`|UltraHonk、bb `-t evm` ZKモード、native検証のみ|
|Halo2|`halo2/src/main.rs`|zcash halo2_proofs 0.3.2、IPA/Pasta、native検証|

IVCはpublic state `[step_count,last_d2,last_r]`を更新する。
前stepのd2/rを最終stateへ全保存する仕様ではない。raw IVCにはWitnessが含まれるので、
公開用のZK proofや跨Proverの秘密非共有として扱わない。Week23の不採用判断は維持する。
個別ZKPとIVCのpublic statement、setup時間、証明サイズを混ぜて優劣を結論しない。

`reference.py`の7ケースを共通使用：zero、3-4-5、逆順、非平方数、最大差、最大差の逆順、隣接。
誤ったd2、平方根の上下誤り、bit範囲外、負座標を各APIの対応範囲で拒否する。
gnarkは独立big.Int.Sqrt oracleの107入力でも正常・出力改変・root改変をテストする。
Noirのtyped入力はu16で制限する。各方式の実行ログに実施した負例の数・種類を記録する。

## 再現

ホストでコンパイルしたLinux ARM64 binaryをPiへ転送する。Go/Rustのコンパイラ自体は
Piへインストールしていない。RapidSnarkだけPi上で単一jobビルドした。
秘密・鍵・証明をGitへ入れない。fixtureはignored `.cache/week24/private/`、dir700/file600。
同名fixture／run directoryを上書きせず、不完全・不一致は保存して新しい名前で再実行する。

```sh
python3 experiments/pi4-euclidean/build_gnark.py
.cache/week24/euclidean-gnark-darwin-arm64 setup groth16 .cache/week24/private/NEW-G16
.cache/week24/euclidean-gnark-darwin-arm64 setup plonk .cache/week24/private/NEW-PLONK
(cd experiments/pi4-euclidean/gnark && go test ./...)
python3 experiments/pi4-euclidean/circom/setup.py .cache/week24/private/NEW-CIRCOM
```

Circom2.2.3、snarkjs0.7.6を実測時に使用（版はmanifestを参照）。
セットアップは単独貢献の使い捨てfixture。phase1/phase2の貢献とzkey verifyを要求する。
初期未貢献のptau/zkeyをそのまま使うと、公開入力を拘束しない退化した鍵になる。
その失敗は報告に保存し、通常runnerは未貢献fixtureを拒否する。
これらのptau/zkey/VK/proofを公開・チェーンdeploy・release keyとして利用しない。
PLONKのunsafekzg.NewSRSもテスト専用で公開／deployしない。

RustはPR246 headとarkworks0.6互換patchを固定した既存ignored sourceを利用する。
`prepare_sonobe.py`は元sourceまたはpatch済みsourceのhashを検査する。新規checkoutは
Week23のsource取得・`prepare_hypernova.py`を実行してから同じhashか検査する。

```sh
python3 experiments/pi4-euclidean/prepare_sonobe.py
rustup target add aarch64-unknown-linux-musl
CARGO_TARGET_DIR=.cache/week24/target-euclidean \
CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER=rust-lld \
  cargo build --locked --release --target aarch64-unknown-linux-musl -j 1 \
  --manifest-path experiments/pi4-euclidean/sonobe/Cargo.toml
# Halo2はmanifest-pathを halo2/Cargo.toml に変更
```

Noirはbb5.2.0がvendoredするNoir commit75061fabのbeta25を使用。
rc2もPiへ取得したが本proof試験に使わない。ARM64公式releaseをignored toolsへ展開する。
`nargo test`とwitness生成、bb prove/write_vk/native verifyをPi上で実行する。
Noir/RapidSnark CLIの一時witness/proof/VKはowner-only `/dev/shm`に限定し、正常・例外終了時に削除。
強制SIGKILLや電源断はfinallyが走らないため、次回試験前に専用tmpfs残存directoryを確認する。
試験中の全childとtmpfsメモリもcgroupの上限に含まれる。

Piの保護設定は[既存runner](../pi4-zkp-bench/README.md)で再設置・検査する。
`run_gnark.py --backend groth16|plonk`と`run_guarded.py -- COMMAND...`は
上限・親slice・watchdog・sshd保護が欠けると実行しない。

```sh
# Pi上、保護設定を確認後に実行。パスは転送先へ合わせる。
sudo systemd-run --unit=week24-euclidean-NEW --wait --pipe \
 -p User=pi -p Slice=week24.slice -p MemoryAccounting=yes \
 -p MemoryHigh=192M -p MemoryMax=256M -p MemorySwapMax=0 \
 -p OOMScoreAdjust=500 -p OOMPolicy=stop -p CPUWeight=10 -p RuntimeMaxSec=330 \
 python3 /home/pi/.cache/week24/run_guarded.py --timeout-s 300 \
 --out /home/pi/.cache/week24/runs/NEW -- /home/pi/.cache/week24/week24-euclidean-halo2-final
```

gnark/RapidSnark/Halo2は256MiB、IVCは512MiB、Noirは1024MiBで別runとして指定。
親sliceは常に1536MiB、Swap0、OS available1GiBを確保。
1CPU affinity、GOMAXPROCS/RAYON/OMP各1。native CLI起動、setup、warmup条件は方式ごとに異なる。
今回はsmoke＋短期資源測定で、1Hz・長期・RSSI・外部秘匿状態引継ぎの評価ではない。
低電圧・現在のthrottlingを検出すると実験だけ停止する。電源やネットワークによるSSH断は
メモリ保護だけでは防げない。Pi再起動後はruntime-only guardを再設置する。

実行状況・性能・失敗を[Week24報告](../../week24/03_ユークリッド距離_各方式のPi実装.md)に記録する。
