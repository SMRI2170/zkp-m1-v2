# 署名付き観測statement v1：GoとRustの共有契約

対象Issue #50 の最初のタスク。既存の`gnark-signed-batch-v1`を読み取り専用の基準とする。
今回は**共有statement・入力表現・ネイティブ参照検証器**まで。Joltのguest証明、Kimchi/Binius64回路は未実装。

## 1. 何を検証するか

1つの観測者公開鍵に対し、1／2／4件の秘密観測について、整数距離・切捨て平方根・署名・公開集合rootが整合すること。
公開鍵が期待する観測者のものかは呼出側の責務。4観測は4観測者を意味しない。
Policyは識別子の拘束だけで、資格・失効・期限のチェックではない。
claimed RIDを束ねたobserver-signed statementの研究PoCであり、DRIP trust chain、センサー真値、ハードウェア／航空機認証を保証しない。

| 入力 | 意味・範囲 | 公開／秘密 |
|---|---|---|
| count | 1、2、4。観測配列長と一致 | 回路ごとに固定（Go）、明示値（Rust） |
| Session | u32 | 公開 |
| Policy | u16 | 公開 |
| claimed RID | u64 | 公開 |
| Root | BN254 scalar field要素 | 公開 |
| PK.x、PK.y | 同じ観測者公開鍵の展開座標 | 公開 |
| X1、Y1、X2、Y2 | 各u16、合成座標 | 秘密 |
| D2、R | u33、u17 | 秘密 |
| signature Rx、Ry、S | 署名の展開座標とscalar | 秘密Witness |

Rustの配列・JSONは互換性検査用の表現であり、gnarkのpublic witness serializationと同一wire formatではない。
JSON自体を署名しない。署名とhashには、次の正規化したfield列を使う。

## 2. 距離と整数範囲

```text
D2 = (X1-X2)^2 + (Y1-Y2)^2
R^2 <= D2 < (R+1)^2
0 <= D2-R^2 < 2^18
0 <= (R+1)^2-D2-1 < 2^18
```

差の符号を保つ平方と`abs_diff`の平方は同じ。先に各値の幅を検査し、u64演算のoverflowを避ける。
Goの`ToBinary`と同じ整数幅・slack条件を保つ。

## 3. MiMCと署名対象の順序

- Field：`p = 21888242871839275222246405745257275088548364400416034343698204186575808495617`。
- 整数／fieldのhash入力は、各値を**32 byte・big endian・leading zeroあり**で符号化。
- field座標・Rootの入力は`0 <= v < p`。Rust decoderはp以上を拒否し、暗黙のmod還元をしない。
- MiMC：gnark-crypto v0.21.0 BN254/Fr、110 rounds、指数5、Miyaguchi–Preneel。
- round定数：legacy Keccak256の`seed`系列。`c0 = Keccak256(Keccak256("seed")) mod p`、以後直前の32 byte digestをKeccakしてmod p。
- 暗号定数の導出におけるmod還元と、外部field入力の正規性検査は別処理。

観測index i（0始まり）の署名メッセージ：

```text
DOMAIN = 0x574B3234
m_i = MiMC(DOMAIN, count, Session, Policy, RID, i, X1, Y1, X2, Y2, D2, R)
Root = MiMC(DOMAIN, count, Session, Policy, RID, m_0, ..., m_(count-1))
```

順序を入れ替えるとindexへの署名拘束が変わる。countも署名対象・Rootの両方に入る。
Goではcountを回路形状／検証鍵で固定し、Rust参照器はpublic.countと配列長の一致を検査する。
公開Rootは低entropyな観測に対する辞書推測耐性を保証しない。

## 4. 曲線・署名検査

BN254/Fr上のgnark twisted Edwards曲線：`-x²+y² = 1+d*x²*y²`。

```text
d  = 12181644023421730124874158521699555681764249180949974110617291017600649128846
Gx = 9671717474070082183213120605117400219616337014328744928644933853176787189663
Gy = 16950150798460657717958625567821834550301663161624707787222815936182638968203
ell= 2736030358979909402780800718157159386076813972158567259200215660948447373041
cofactor = 8
h = MiMC(Rx, Ry, PKx, PKy, m_i)
[8*S]G = [8](R + [h]PK)
```

Sは32 byte big endianで、`S < ell`を要求する。Ed25519とは異なる曲線・hash・署名形式。
Rustはextended Edwards座標でこの式を計算する参照実装であり、独立監査済みの汎用署名ライブラリではない。

### 入力受付の境界差

**すべての任意入力についてGoとRustが同じ受付集合とは主張しない。** 今回照合するのは、Goで正しく生成した公開鍵・署名を基準にした合成入力と、その改変。

| 検査 | 既存gnark回路 | Rust参照器 |
|---|---|---|
| 正規field encoding | Witnessへ変換する前の呼出側の責務 | 32 byteからdecode時に明示検査 |
| PKがon-curve・非identity・prime subgroup | 独立した明示検査はない。期待する登録鍵を呼出側で検査する前提 | 明示検査 |
| Rがon-curve | 独立した明示検査はない | 明示検査 |
| S < ell、cofactor署名式 | 検査 | 検査 |

gnark-cryptoの**native** `PublicKey.Verify`／`Signature.SetBytes`は、回路gadgetとは別にPK／RのsubgroupやS非zero等も検査する。
Rust参照器はnative compressed signature parserの完全な再実装ではなく、展開したfield列と上記式を扱う。
今回の正常鍵・署名はnative generatorで生成する。将来外部入力を受け付けるときは、この受付境界を揃えてから性能を比較する。
既存回路を弱めたり、新しいチェックを既存測定へ遡及適用したりしない。

## 5. 証拠と保存ルール

Goは固定済み元sourceのSHAを検査して一時packageへ複製し、生成したtest key・assignmentをRAMで扱う。
合成assignmentはGo stdoutからRust stdinへの匿名pipeだけで受け渡す。
公開ログにはcase名・count・判定・version・source hashだけを残し、key・assignment・Root/PK/署名・proof bodyを残さない。
この処理はconstraint solverとnative referenceの比較であり、Proof生成／ZK／RV64実行／Pi評価を意味しない。

## 一次ソース

- 基準：[既存gnark回路](../pi4-euclidean-evaluation/workload/main.go)、gnark v0.16.3／gnark-crypto v0.21.0。
- `gnark/std/signature/eddsa/eddsa.go`：IsValid、S範囲・cofactor検査。
- `gnark-crypto/ecc/bn254/fr/mimc/mimc.go`：round定数・encrypt・checksum。
- `gnark-crypto/ecc/bn254/twistededwards/{curve.go,eddsa/eddsa.go,eddsa/marshal.go}`：curve・native APIの入力境界。
- Rust依存：ark-ff／ark-bn254 0.5.0、sha3 0.10.9。Cargo.lockを固定。既存SonobeやJoltのarkworks依存を変更しない。
