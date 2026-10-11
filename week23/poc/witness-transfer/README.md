# 旧API Witness転送の再現

```sh
python3 week23/poc/witness-transfer/prepare.py
CARGO_BUILD_JOBS=1 CARGO_TARGET_DIR="$PWD/.cache/week23/target" cargo build --release --locked --manifest-path week23/poc/witness-transfer/Cargo.toml
mkdir -p .cache/week23/private
chmod 700 .cache/week23/private
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer a false .cache/week23/private/new-false
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer b false .cache/week23/private/new-false
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer a true .cache/week23/private/new-true
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer b true .cache/week23/private/new-true
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer zk true .cache/week23/private/new-true
```

新しいdirectory名を使う。既存setup/private状態は上書きしない。A/Bは別processで、Bはstateとpp/vpのみ読み込む。
7入力は架空の識別用canary。元回路はコピーし、nova_pocを変更していない。

**commitment改竄の拒否assertは現時点で失敗する**。これは旧版の検証挙動の発見としてレポートし、
成功扱いするためにassertを除去しない。Bは全6caseを出力してからこのassertで非ゼロ終了する。
通常のAPI使用例としてこのraw resume処理を採用しない。
受信verifyだけでなく、incoming witnessから再計算したcommitmentとの一致も別列で確認する。
これだけで全体の暗号安全性監査を完了したとは主張しない。

追加の受信ゲート実験（元の `b` の失敗テストは残す）:

```sh
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer guard false .cache/week23/private/new-false
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer guard true .cache/week23/private/new-true
```

ゲートは元verifyと3組のcommitment再計算を両方要求する。秘密非共有を与えるものではない。

単一NIFSの逆算と元構成KZG/Pedersenの比較:

```sh
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer inverse false .cache/week23/private/new-false
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer inverse true .cache/week23/private/new-true
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer a kzg .cache/week23/private/new-kzg
RAYON_NUM_THREADS=2 .cache/week23/target/release/week23-witness-transfer b kzg .cache/week23/private/new-kzg
```

KZGの比較はH=false。Bの元assertはcmW改竄の受理があれば非ゼロ終了する。使い捨てsetupはテストfixtureで、公開しない。
