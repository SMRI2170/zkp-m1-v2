# Issue45追加候補：同じユークリッド距離のPi評価

既存7構成へ、arkworks Groth16、Halo2 KZG/BN254、Spartan、Bulletproofs R1CS、
Plonky2、Plonky3を追加。zkVMのRISC Zero／SP1は事前条件・native CLIの評価と実proofを分ける。
[Week24結果](../../week24/05_追加フレームワークのPi評価.md)が状態・制約・ログの正本。

仕様は[既存Euclidean](../pi4-euclidean/README.md)と同じ：private u16座標4つ、
public d2（u33）とfloor sqrt（u17）、平方根の2slack（u18）。
合成7ケース、公開d2／r／proof改変、root上下誤り・不正出力・範囲外・負座標を検査。
観測の真値、実RID、DRIP、observer hardware、航空機認証の評価ではない。

|source|方式／版|注意|
|---|---|---|
|arkworks/|ark-groth16・BN254、arkworks0.6|Piで使い捨てsetup、鍵はRAMのみ。canonical compressed proof128Bはgnarkの164Bとは形式が異なる|
|halo2-kzg/|PSE Halo2 be955686、KZG／BN254、SHPLONK|元のIPA/Pastaと別backend。archive済みrepoの固定tag。k9、random test SRSをPiで生成。native Blake2b verifierのみ、EVM未検証|
|spartan/|Microsoft Spartan d62b961f、Ristretto SNARK|手動R1CS。163制約／158private変数を256へpad。public2。trusted setup不要、bincode形式|
|bulletproofs/|zkcrypto04bce4e6、5.0.1、Ristretto R1CS|実験専用yoloproofs。公開5.0.0のCtOption API不整合を上流修正で解消。clear_on_dropのメモリ消去を維持|
|plonky2/|5d9da5a6、Goldilocks PLONK／FRI|上流ZK config、nominal100bits。Poseidon実効securityの上流注記を結果に記録。通常負荷とCPU quotaの条件を混ぜない|
|plonky3/|f9833168、Goldilocks AIR＋HidingFRI／Keccak|双方のMMCSもhiding、OS乱数でseed。num_queries100／blowup2／PoW16+10を保持。ZK budget不足を避けtrace256row。1入力を256回反復するAIR、256独立観測ではない|

Spartanのinput assignmentは別public vector、Bulletproofsはpublic d2/rを
Merlin transcriptと回路の定数に拘束する。どちらも端末署名や元観測へのcommitmentは含まない。
各方式のpublic integer statementは同じでも、曲線、セキュリティ仮定、シリアライズ形式は異なる。

## ビルドと実行

Mac上でLinux ARM64 muslへcross compile。PiにRust compiler全体は入れない。
Cargo.lock・Git revを固定し、build job1。default Rust toolchainは変更しない。

```sh
rustup target add aarch64-unknown-linux-musl
rustup component add llvm-tools
rustup toolchain install nightly-2026-10-01 --profile minimal --target aarch64-unknown-linux-musl
python3 experiments/pi4-euclidean-additional/build.py
```

BulletproofsのC helperはclangのARM64 Linux targetとRust llvm-toolsのllvm-arで構築。
AppleのarではELF symbol indexが正しく解決されずlink失敗した。
`no_cc`等で消去機能を外してビルドを通していない。

ビルド成功とPi proof成功は別。転送したbinaryのSHA256をmanifest・host binaryと照合する。
切断中のpartial transferは保存し、別名で完成binaryを転送して再照合する。
Pi再起動後は[既存guard](../pi4-zkp-bench/README.md)を再設置し、メモリ／SSH保護を確認。

```sh
# Pi上。pathとNEWは未使用のものを指定。
sudo systemd-run --unit=week24-additional-NEW --wait --pipe \
 -p User=pi -p Slice=week24.slice -p MemoryAccounting=yes \
 -p MemoryHigh=192M -p MemoryMax=256M -p MemorySwapMax=0 \
 -p OOMScoreAdjust=500 -p OOMPolicy=stop -p CPUWeight=10 -p RuntimeMaxSec=630 \
 python3 /home/pi/.cache/week24/run_guarded_additional.py --timeout-s 600 \
 --out /home/pi/.cache/week24/runs/NEW -- /home/pi/.cache/week24/week24-euclidean-arkworks
```

追加runnerは既存runnerの強いpreflightを維持し、監視例外でもprocess groupを止めて資源ログを保存。
監視失敗、低電圧、OOM、timeoutを成功扱いにしない。
Plonky2は別条件として上限512MiBと1536MiB、CPU25%条件を区別する。
親slice1536MiB／Swap0、OS available1GiB、watchdog外置き、SSH -900は全条件で同じ。

使い捨てGroth16／KZG setup・PK・VK・proof・private assignmentはRAMのみ。
Gitへの実体追加やチェーンdeployはしない。公開ログに含めるのは時間・byte数・検査結果のみ。
新規run名を使い、失敗・不完全runを削除／再利用しない。

## zkVM

SP1 v6.9.0のofficial Linux ARM64 CLIをhash検査してPiで`cargo-prove prove --version`を実行。
この操作はguestの実行・証明生成ではない。mockやnetwork provingをローカルproofと扱わない。
RISC Zero v3.0.6のofficial CLI releaseにはLinux ARM64 binaryが見つからない。
source buildや別版での可能性を否定する結論ではない。
resource／toolchainの前提を満たした後にguest→実proof→native verifyを別段階で評価する。
