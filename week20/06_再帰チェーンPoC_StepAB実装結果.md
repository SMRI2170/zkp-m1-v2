# 再帰チェーン PoC Step A/B ── 実装結果と分かったこと

作成日: 2026-07-23 / 目的: `NEXT_STEPS.md` §1「Step A」（gnark で 2〜3 ステップの逐次再帰検証を回し、
前を内包できることを実証する）と §3「Step B」（RSSI整合を step 回路に折り込む）を実装し、
そこで分かった技術的な制約・知見を記録する。
関連: `week20/04_再帰ZKP_証明チェーン設計.md`（設計）、`week20/05`（内包の詳説）。

**結論を先に**: **Step A・Step B とも成功**。gnark(BN254, `std/recursion/groth16`) で π_1→π_2→π_3 の
3ステップ連結を実証（Step A）。さらに `circuits/remoteid_consistency_rel.circom` と同じ「相対許容帯」
RSSI整合判定を回路内計算に置き換え、consistent/suspiciousの両方が正しく育つこと、なりすまし観測を
「整合した」と偽って計上しようとしても回路が拒否することを確認（Step B）。各 π_k は単体で検証可能。
実装過程で **「自己再帰の器のサイズ問題」** という設計上の落とし穴が実測で見つかり、対処（段ごとの
回路立て直し）と、残る課題（不動点への収束確認）が明らかになった。

---

## 0. 前提: 環境構築（M2 Mac、今回初めて着手）

M2 Mac 移行後、`go` が未インストールだったため今回導入。

```bash
brew install go   # go1.26.5 darwin/arm64 が入った（CLAUDE.md の要求は go1.25+ なので満たす）
```

`aggregator/` の既存資産は無変更で動いた:
- `go build ./...` … OK
- `go test ./...` … `completeness`/`membership` とも green
- `go run .`（Spike A: snarkjs証明のinterop検証）… `zk-distance/build/` が gitignore され未生成のため未実行
  （circom/snarkjs も M2 Mac に未インストール。今回のStep AはGo単体で完結する設計にしたため、
  この2つが無くても支障はなかった。Step B以降でcircom回路の実観測を繋ぐ際に要インストール）。

---

## 1. 実装したもの

`aggregator/cmd/chainpoc/main.go`（新規）。既存の `cmd/aggregate/main.go`（N証明を1回で並列検証する
"木"集約, M2）とは別に、**逐次チェーン(IVC)** 版を作った。

### 1.1 回路構成（2種類・自己再帰のブートストラップ）

```
GenesisCircuit（起点・参加者1、前の証明なし）
  public: DroneID, TimeBucket, ConsistentCount, SuspiciousCount, StepCount
  private: DroneLat/Lon/Alt（放送位置の申告値）, TargetLat/Lon/Alt（自分の位置）,
           MeasuredRangeCm（RSSIから算出した実測レンジ）
  制約:
    ok = rssiConsistencyOk(...)                              ← RSSI整合を回路内で計算(Step B)
    ConsistentCount == ok, SuspiciousCount == 1-ok, StepCount == 1

ChainCircuit（参加者2以降・前を再帰検証して内包）
  public: DroneID, TimeBucket, ConsistentCount, SuspiciousCount, StepCount   ← 新しい z_i
  private: DroneLat/Lon/Alt, TargetLat/Lon/Alt, MeasuredRangeCm,
           PrevVK, PrevProof, PrevWit                        ← 前の証明 π_{i-1} 一式
  制約:
    ok = rssiConsistencyOk(...)                               ← RSSI整合を回路内で計算(Step B)
    1. verifier.AssertProof(PrevVK, PrevProof, PrevWit)       ← 前を再帰検証(内包)
    2. DroneID == prevDroneID, TimeBucket == prevTimeBucket   ← 同一ドローン/時間窓
    3. ConsistentCount == prevConsistentCount + ok            ← 状態更新
       SuspiciousCount == prevSuspiciousCount + (1-ok)
    4. StepCount == prevStepCount + 1
```

`z`（公開状態）は `week20/04` §4 の最小版に `suspicious_count` を加えたもの（drone_id_commitment /
time_bucket / consistent_count / suspicious_count / step_count の5つ）。座標・生RSSIは回路の外＝
完全に秘匿のまま。Step A では `Ok` を「入力で可」としていたが、Step B で
`circuits/remoteid_consistency_rel.circom` と**同じ計算式**（下記1.4）を回路内に移植し、`ok` を
回路が自分で計算するように置き換えた。

`PrevVK/PrevProof/PrevWit` の再帰検証は `aggregator/cmd/aggregate/main.go` と同じ手法
（`std/recursion/groth16` の `Verifier.AssertProof` ＋ `recompose`（emulated要素→native変数への
limb再合成）で前の public 信号を読む）を流用。BN254のまま（cross-curveなし）なので EVM 着地に有利
という設計判断（`week20/04` §0 採用理由）をそのまま踏襲できた。

### 1.2 見つかった落とし穴 ── 「前の証明を受け取る箱」のサイズは検証対象の回路形状に依存する

最初は `ChainCircuit` を1種類だけ作り、step2（Genesisを検証）にも step3（Chain自身を検証）にも
使い回そうとした。これは失敗した:

```
[step3] ... invalid witness size, got 229, expected 181
```

**原因**: gnark の `recursion.PlaceholderVerifyingKey/Proof/Witness(ccs)` は、`PrevVK` 等の
フィールドサイズ（配列長）を **検証対象にする内側回路(ccs)の構造** から決める。この構造は
「公開信号の数」だけでなく、内側回路が内部でいくつ "commitment"（gnark Groth16 が大きい/非ネイティブ
算術を扱うために使う機構）を持つかにも依存する。

- `GenesisCircuit`: 再帰検証器を含まない単純な回路 → commitment 少（浅い構造）
- `ChainCircuit`: 内部に再帰検証器(`recursion.Verifier`)を持つ → commitment が増える（深い構造）

両者は **公開信号の数こそ同じ(4個)だが、内部構造が違うため「箱」のサイズが違う**。
`Genesis用に作った箱`で`ChainCircuit(=Chain自身)の証明`を受けようとすると、実際のVK/Proofが
箱より大きくてサイズ不一致になる。これが `got 229, expected 181` の実体。

**対処（今回の実装）**: 段ごとに回路を立て直した。

| 回路 | 検証対象 | 制約数 | 役割 |
|---|---|---:|---|
| `GenesisCircuit` | なし | 3 | 起点。π_1 を出す |
| `ChainCircuit`（chainA） | Genesis | 1,167,919 | step2。π_1 を内包し π_2 を出す |
| `ChainCircuit`（chainB） | chainA | 1,643,801 | step3。π_2 を内包し π_3 を出す |

`ChainCircuit` の **Go の型（構造体・Define()）は1つ**で、コンパイル時に「どの ccs を基準に
箱のサイズを決めるか」だけを変えて2回コンパイルした（`recursion.PlaceholderVerifyingKey(...)` 等に
渡す `ccs` を `genesisCcs` → `chainCcsA` に変更）。

### 1.3 残る課題 ── 無限に延長するには「不動点」への収束確認が要る

今回は3ステップ限定なので「段ごとに専用回路（chainA, chainB）」で済ませた。任意の長さ N のチェーンに
一般化するには、`ChainCircuit` が **自分自身の証明を検証できる形に収束するか**（chainB を検証できる
`chainC` を作ったら、chainC は chainB と同じ形になるか＝不動点）を確認する必要がある。

- 直感的には収束するはず（「内側の証明の公開信号4個」という条件は変わらないので、内部の commitment 数も
  ほぼ安定するはず）だが、**今回は未検証**。
- 確認方法: `chainC = compile(placeholder sized by chainB)` を作り、`chainC` の制約数/VK形状が
  `chainB` と一致するか比較。一致すれば `chainC`（＝安定した「Chain from Chain」回路）を step4 以降も
  使い回せる。
- これは `week20/04` §10 論点6「端末で〜が回るか」や§13「残りの論点はPoCで確定」に対応する、
  **Step A で新たに具体化された論点**として記録しておく（Step B/C 着手前に確認する価値あり）。

### 1.4 Step B: RSSI整合の回路内計算（circomからgnarkへの移植）

`circuits/remoteid_consistency_rel.circom`（`RemoteIdConsistencyRel`）が行っている計算をそのまま
gnarkの`frontend.API`で再実装した。円周率やsqrt/除算を避けて整数のまま比較する設計（元のcircom回路の
工夫）はgnark側でも踏襲できた。

```
入力: droneLat/Lon/Alt（放送位置の申告値）, targetLat/Lon/Alt（自分の位置）, measuredRangeCm（RSSI実測レンジ）
計算:
  dLat, dLon, dAlt = |drone - target|                      （AbsDiff: gnarkでは cmp.IsLess + api.Select）
  latScaled = dLat * LAT_CM_NUM,  lonScaled = dLon * LON_CM_NUM,  altScaled = dAlt * GEO_DEN
  claimedDistSq = latScaled² + lonScaled² + altScaled²      ← 申告位置と自位置の幾何距離の二乗(スケール後)
  base = measuredRangeCm * GEO_DEN
  lowerSq = (base*(DEN-NUM))²,  upperSq = (base*(DEN+NUM))² ← 相対許容帯 ±90% (NUM=90, DEN=100)
  claimedScaled = claimedDistSq * DEN²
  ok = (lowerSq <= claimedScaled) AND (claimedScaled <= upperSq)
```

**circomとの対応**:
- 係数（`LAT_CM_NUM=11132000`, `LON_CM_NUM=9128800`, `GEO_DEN=10000000`, `TOL_NUM=90`, `TOL_DEN=100`）は
  circom側と完全に同一の値を使用。
- `AbsDiff`（circom: `LessThan`の比較結果でSelect）→ gnark: `cmp.IsLess(api,a,b)` ＋ `api.Select`。
- `LessEqThan(200)`（circomのビット分解ベース比較器、200bit幅を明示指定）→ gnark:
  `std/math/cmp.IsLessOrEqual(api,a,b)`。ビット幅は明示不要（`api.Compiler().FieldBitLen()`,
  BN254で約254bit）を自動で使うため、circomの200bitより余裕を持った比較になる（今回の値の桁数
  ～2^125 程度に対しては十分すぎるほど余裕があり、性能上の実害はなし）。

**テストデータ**: 新規に作らず、既存の `zk-distance/samples/sample_remoteid_consistent.json` /
`sample_remoteid_spoof.json` をそのまま使い回した（申告位置・自位置は共通、`measured_range_cm` だけ
`341`(整合) / `5000`(なりすまし)で切り替え。幾何距離は実測で ≈341cm なので、前者はok=1、
後者はmeasuredが実際の距離から大きく乖離し許容帯を外れてok=0になることを確認済み）。

**Step Bで追加した否定系（最も重要な新規テスト）**: なりすまし観測(`obsSpoofed`, 本当は`ok=0`)を
使いながら、`ConsistentCount`だけを「本当は+0のはずが+1」と偽って`Prove`しようとした。
**回路が自分でRSSI整合を計算する**ため、この偽りは制約違反として拒否された
（`constraint #157971 is not satisfied: 1 ⋅ 3 != 2`）。Step Aまでは「Okは入力（信頼が必要）」
だったのに対し、Step Bで「Okは回路が計算する（参加者は結果を偽れない）」に変わったことを直接示す、
設計上いちばん意味のあるテスト。

---

## 2. 実行結果

環境: M2 Mac（Apple Silicon, arm64）、go1.26.5、`go run ./cmd/chainpoc`。総所要時間 **約5分**（Step A時と
ほぼ同じ。RSSI計算の追加コストは相対的に小さい）。

### 2.1 コンパイル + Setup（1回だけ発生するコスト）

| 段階 | 制約数（Step A） | 制約数（Step B・RSSI計算込み） | 体感時間 |
|---|---:|---:|---:|
| Genesis compile+setup | 3 | **6,400** | 一瞬 |
| chainA compile | 1,167,919 | **1,266,485** | 〜2秒 |
| chainA Groth16 Setup | 同上 | 同上 | **約2分** |
| chainB compile | 1,643,801 | **1,742,367** | 〜3秒 |
| chainB Groth16 Setup | 同上 | 同上 | **約2分40秒** |

→ **セットアップ（trusted setup 相当の鍵生成）が支配的コスト**なのはStep Aと同じ。RSSI整合計算
（`cmp.IsLessOrEqual`によるビット分解ベースの大小比較×2回、AbsDiff×3、二乗×6ほど）が乗った分だけ
chainA/chainBの制約数が約9.8万〜10万増（+8%程度）。Genesisは再帰検証器を含まない分、
RSSI計算のコストがそのまま見える（3→6,400）。全体としては軽微な増分で、セットアップ時間への影響も
誤差の範囲内だった。

### 2.2 正常系: 3ステップ連結（RSSI整合の回路内計算あり）

| step | 内容 | solve | prove | verify | 結果 |
|---|---|---:|---:|---:|---|
| 1 (genesis) | 整合観測(距離≈341cm, measured=341cm) → ok=1、z_1=(consistent=1, suspicious=0, step=1) | 0.65ms | 16.6ms | 0.9ms | π_1 単体検証 OK |
| 2 (chainA) | π_1 内包 + 整合観測 → ok=1、z_2=(consistent=2, suspicious=0, step=2) | 725ms | 5.36s | 1.8ms | π_2 単体検証 OK |
| 3 (chainB) | π_2 内包 + **なりすまし観測**(measured=5000cmだが幾何距離≈341cm) → ok=0、z_3=(consistent=2, **suspicious=1**, step=3) | 989ms | 6.22s | 1.8ms | π_3 単体検証 OK |

- `consistent_count` は 1→2→2、`suspicious_count` は 0→0→1 と設計通り成長。**なりすまし観測を
  混ぜても証明自体は正しく成立し**、その矛盾が `suspicious_count` として正しく記録される
  （＝「危険を検知したこと」自体を証明できる、`week20/04` §14 目的②の方向性を確認）。
- 各 π_k は単体で `groth16.Verify(proof, vk, publicWitness)` だけで検証できることを確認済み。
- **verify は常に数ミリ秒**、**prove（再帰検証+RSSI計算を内包する側）が重い**という非対称性は
  Step Aと同じ傾向のまま（M2 Mac で ~5〜6秒/ステップ）。RSSI計算の追加による目立った悪化はなかった
  （制約数+8%程度の増分がprove時間にもおおむね比例して反映されている程度）。

### 2.3 否定系

| テスト | やったこと | 結果 |
|---|---|---|
| 1. time_bucket 食い違い | π_1(time_bucket=100001) を内包しつつ、新しい z の time_bucket に 100002 を主張 | `Prove` が `constraint #129204 is not satisfied: 1 ⋅ 100002 != 100001` で失敗（拒否成功） |
| 2. 偽の前証明（公開値改ざん） | 本物の π_1 はそのまま使い、「π_1が証明したはずの公開値(z_1)」だけを consistent_count=99 に改ざんして渡す | `Prove` が `constraint #124077 is not satisfied: 1 ⋅ 0 != 1` で失敗（拒否成功） |
| 3.（Step B新規）なりすまし観測を「整合」と偽って計上 | `obsSpoofed`（本当はok=0）を使いながら `ConsistentCount` だけ「+1された」と偽って主張 | `Prove` が `constraint #157971 is not satisfied: 1 ⋅ 3 != 2` で失敗（拒否成功） |

否定系2はGroth16の「証明は特定の公開入力にしか結びつかない（malleability耐性）」という性質そのものを
突く形になっており、**相手を信頼せず回路内検証だけで弾ける**という `week20/04` §5.3 の主張を実測で
裏付けた。**否定系3がStep Bでいちばん重要**: Step Aまでは「Okは外部入力＝参加者の自己申告を信頼する
必要があった」のに対し、Step Bで「Okは回路が計算する＝参加者は結果を偽れない」に変わったことを直接示す。

---

## 3. Step C 以降への申し送り

- **不動点の確認**（§1.3、未着手）: Step C で回路がさらに複雑化する前に、「Chain from Chain」が
  安定するかを確認しておくと、N ステップへの一般化コストの見積りが立つ。
- **membership/二重計上（Step C）**: 既存 `aggregator/membership/` をそのまま `ChainCircuit` に
  組み込める見込み（`cmd/aggregate/main.go` で使っているのと同じ `membership.ComputeRoot` パターン）。
- **circom実観測との接続**: 現状 `DroneLat/Lon/Alt` 等はGoコードにハードコードした手動値
  （`zk-distance/samples/`の既存サンプルを再利用）。実際の端末witness証明
  （`uav_witness_attestation`, circom/snarkjs）と繋ぐには `zk-distance/build/` の再生成
  （circom/snarkjs のインストールを含む、§0参照）が必要。将来的には、この chainpoc の
  RSSI整合計算をcircom側の leaf 証明に任せて gnark 側は再帰検証だけに戻す設計（＝現行
  `cmd/aggregate/main.go` に近い形）と、今回のように gnark 側でRSSI計算まで内製する設計の
  どちらを採るか、比較検討の余地がある（後者はcircom依存を減らせる一方、回路が肥大化する）。
- **入力真正性・GPS真正性（week20/04 §14 (b)(c)）**: 今回の `DroneLat/Lon/Alt` はまだ「申告値を
  無条件に信じる」状態（ドローン署名検証・freshness・GPS真正性は未実装）。Step B はあくまで
  「申告値と実測RSSIの整合を計算で確認する」ところまでで、「申告値自体が本物か」はまだ担保していない
  （既知の限界として `week20/04` に明記済み）。
- **性能の実機確認**: M2 Mac での実測（prove 5〜6秒/ステップ）はラズパイでの実際の重さの参考値には
  ならない。Step C/D に進む前に、対象ハードウェア（Raspberry Pi 4/5等）での実測を1回挟むと、
  `week20/04` §6 の役割分担（ラズパイ=重い再帰、スマホ=軽いwitness証明のみ）の妥当性を確認できる。

---

## 4. 参照

- 実装: `aggregator/cmd/chainpoc/main.go`
- 設計: `week20/04_再帰ZKP_証明チェーン設計.md` §0, §3, §4, §5.3, §6, §10, §13, §14
- RSSI整合の元ロジック: `circuits/remoteid_consistency_rel.circom`, `circuits/lib_uav_safety.circom`
- テストデータ: `zk-distance/samples/sample_remoteid_consistent.json`, `sample_remoteid_spoof.json`
- 着手時のスコープ定義: `NEXT_STEPS.md` §1「Step A」, §3「Step B」
