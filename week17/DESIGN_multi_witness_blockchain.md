# マルチ端末 × ブロックチェーンによる UAV 接近証明の結合設計

作成日: 2026-07-06 / ブランチ: `acoustic-detection-zk`
関連: `circuits/distance_30m_time_detection_commitment.circom`, `circuits/uav_witness_attestation.circom`(新規),
実装プラン: `/Users/smri/.claude/plans/snazzy-petting-blum.md`

本書は「複数端末が同じドローンについて出した証明を、ブロックチェーンで結合して検証する」設計の
背景・全体像・フロー・正当性評価・入力真正性の強化策をまとめたもの。

---

## 1. 背景（なぜやるか）

各スマホ（各人）は既に「この端末がドローンに 30m 以内で接近し、映像でも検知した」を Groth16 で証明できる
（`distance_30m_time_detection_commitment.circom`：座標は private、Poseidon コミットメントと
`within30_and_detected` フラグだけ公開）。

しかし **1 端末の証明は「計算の正当性」を示すだけで「入力の真正性」を保証しない**。
スピーカー再生・GPS 詐称・RemoteID 放送値の流用で偽装しうる。

そこで **同じドローンを観測している複数端末の証明を、ブロックチェーン上で結合・検証する**。
物理的に離れた複数端末が「同一ドローン X へ各自 30m 以内」を独立に証明し、それが K 台以上一致したときに
「ドローン X が実在し接近した」と合意する。1 台のスピーカー偽装では、離れた複数端末に幾何学的に整合する
観測を同時に食わせるのは極めて困難 —— これがマルチ witness による偽装耐性の考え方。

**確定した要望**：音響は対象外（距離＋時刻＋映像検知）／統合方式は最も新規性の高いもの／
チェーン基盤は本設計で提案。

---

## 2. 結合方式の比較と採用

| 方式 | 内容 | 新規性 | 採用 |
|---|---|---|---|
| オンチェーン個別検証＋閾値カウント | 各 proof を個別に検証しレジストリで K 台数える | 低（既存パターン） | M1（de-risk） |
| SnarkPack 集約 | 同一 VK の proof を安く束ねる gas 最適化 | 低（証明間の関係を強制しない） | 不採用 |
| **再帰アグリゲータ回路** | N proof を回路内で再帰検証し「同一ドローン/端末相異/各 within30」を強制、1 証明へ凝縮 | **高** | **M2（本命）** |

再帰アグリゲータは単なる集約ではなく「**物理イベントに対するマルチ witness 合意の証明**」であり、ここが核心の新規性。

---

## 3. アーキテクチャ（3 層）

```
[端末層] 各スマホ = uav_witness_attestation.circom で Groth16 証明を 1 つ生成（rapidsnark）
   private 入力: ドローン位置/時刻, 自端末位置/時刻, 映像検知, remote_id, EdDSA 署名
   public 出力: within30_and_detected, 各コミットメント,
                drone_id_commitment(結合キー), device_pubkey(端末ID)
        │  N 個の独立 proof（同一 drone_id_commitment を共有）
        ▼
[集約層] M1: なし（各 proof をそのままチェーンへ）
        M2: 再帰アグリゲータ = N proof を再帰検証＋「同一ドローン/端末相異/各 within30」を強制
            → 集約 proof 1 個（gas 定数）
        │
        ▼
[チェーン層] EVM L2（Base / Polygon を提案）
   snarkjs 生成の Solidity Groth16 検証器で検証
   AttestationRegistry: (drone_id_commitment, time_window) ごとに、
   相異なる device_pubkey が K 台揃ったら consensus_ok を記録
```

### 3.1 同一ドローンの結合キー
各端末が受信するドローンの RemoteID（operator/uas id）は共通なので、
`drone_id_commitment = Poseidon(remote_id)` は同じドローンを見た端末間で自然に一致する。
位置/時刻は端末ごとにズレるため、位置ではなく RemoteID 由来 ID を結合キーにする。

### 3.2 端末鍵（Sybil 対策 / replay 防止）
端末は claim を自分の鍵で EdDSA-Poseidon 署名し、回路内で検証する。
- 署名対象 `M = Poseidon(drone_id_commitment, target_commitment, frame_binding, within30_and_detected)`
- `device_pubkey` を public 出力にすることで、チェーン側で「相異なる K 台」を判定できる。
- 他端末の proof を別 pubkey で使い回す replay を防ぐ。

### 3.3 チェーン基盤の提案
- **パブリック EVM L2（Base もしくは Polygon PoS/zkEVM）を推奨**。
  snarkjs `zkey export solidityverifier` がそのまま使え、オンチェーン検証が定数 gas、合意記録が公開監査可能。
- Sybil 耐性は `device_pubkey` の事前登録レジストリ（必要ならステーク）。
- 規制運用が必要になればコンソーシアム/許可型チェーンへ移植可能（検証器は EVM 互換のまま）。

---

## 4. エンドツーエンドのフロー

1. ドローンが RemoteID（operator/uas id）＋位置を BLE/WiFi 放送。
2. 近くの各端末が受信し、自端末の GPS/映像検知と合わせてオンデバイスで proof 生成。
   端末秘密鍵で claim（M）に EdDSA 署名し、回路内で検証。
3. 各端末が proof をチェーンに提出（M1）／またはアグリゲータに送って集約 proof 1 個を提出（M2）。
4. コントラクトが検証し、同一 `drone_id_commitment`・同一 time_window で
   **相異なる pubkey が K 台**揃ったら `consensus_ok=1` を記録。

---

## 5. 正当性の評価（この設計は正しいか）

**構造は整合的で正しい方向**。ただし次の穴を正しく認識しておく必要がある。

### 妥当な点
- drone_id を結合キーにする判断は正しい（放送値は共通なので自然に一致）。
- EdDSA 署名で claim を束縛 → replay 防止＋チェーン上の「相異なる K 台」判定が成立。
- 座標は private のままコミットメントだけ公開（プライバシー維持）。
- 段階化（M1 個別検証 → M2 再帰集約）はリスク順として妥当。

### 最重要の穴：入力の真正性はまだ担保されていない
`remote_id` もドローン放送位置も **公開情報**。したがって：
- 現地にいない攻撃者でも、RemoteID 放送を傍受/既知なら `drone_id_commitment` を一致させられる。
- `within30` は「自端末位置 vs ドローン位置」の判定だが、自端末位置も攻撃者が自由に入力できる private 値。
  放送位置の近くの偽座標を入れれば `within30=1` を捏造できる。

→ **M1/M2 は「Sybil 耐性のある K 個の鍵」というコストを課すだけ**で、
登録済み K 鍵を持ち放送を知る協調攻撃者は依然として偽造可能。
**「K 台合意＝真正」ではなく「K 台の登録端末の署名が揃った」に過ぎない**点を明記する。
真の耐偽装は 6 章の入力真正性の施策（＝プラン M3）に依存する。**耐偽装を主目的にするなら M3 は必須**。

### 補足
- `device_pubkey` 公開により同一端末の複数 attestation が紐付く（擬似匿名）。用途上 OK だが明示する。
- M2 の再帰集約（Groth16-in-Groth16）は重い。gnark(BW6 ラップ) か Sonobe 前提。M2 着手前に
  proof 生成コスト / EVM gas を PC で実測する。

---

## 6. 入力の真正性を高める方法（M3 の中身）

ZK 単体では真正性は出せない。真正性は必ず
「**外部の信用アンカーの署名を回路内で検証する**」か「**物理実測に置き換える**」ことで持ち込む。
回路が今「無検証で信じている」3 入力ごとに整理する。

### ① ドローン位置・ID
- **a. 署名付き RemoteID（最有力・ZK 親和）**：ASTM F3411 の Authentication Message、
  IETF DRIP（Broadcast RID, RFC 9434 / HHIT）でドローン放送を暗号署名。
  ドローン（登録オペレータ鍵）の署名を回路内で検証 → 「登録実機由来」を担保、偽ドローン ID を封じる。
- **b. 実測レンジで裏取り**（②a と共通）。

### ② 自端末位置（最も穴が大きい）
- **a. 実測距離で `within30` 判定**：自己申告 GPS でなく、RSSI / BLE 5.1 AoA・AoD / UWB・ToF の
  実測量で判定。遠隔スピーカー/リプレイは各端末で正しい信号を再現できない。
- **b. GNSS 認証**：Galileo OSNMA で「本物の衛星信号由来」を証明し GPS スプーフィングを検出。
- **c. 端末アテステーション**：Android Key Attestation / StrongBox、iOS App Attest、TEE で
  取得時刻にセンサ値を署名 → 注入値でないことを担保、回路内で署名検証。

### ③ 映像検知
- **a. zkML**：ezkl 等で「コミットしたモデルをコミットしたフレームに実行した結果 score」を証明。
  「検知した」と嘘の 1 を入れられなくする。
- **b. カメラ来歴（C2PA / Content Credentials）**：撮影時にカメラがフレームに署名、`frame_commitment`
  の署名を検証。

### ④ 横断：新鮮さ・多 witness 整合
- **新鮮さ**：署名メッセージ M に直近ブロックハッシュ or チャレンジ nonce を混ぜ、
  古い観測の使い回し・事前計算を封じる。
- **多 witness 幾何整合**：相異なる位置の複数端末が同一発生源へ実測レンジを取り、
  三角測量的に矛盾がないことを集約回路で強制。①〜③と組み合わさって初めて「K 台合意＝真正」が成立。

### 優先順位（この構成向け）
| 優先 | 施策 | 効果 / コスト |
|---|---|---|
| 高 | ドローン署名 RemoteID（DRIP/F3411 Auth）を回路内検証 | 偽ドローン ID 封じ / 中・ZK 親和 |
| 高 | 端末アテステーション（Android/iOS）で位置・時刻の出所署名 | GPS 注入封じ / 中 |
| 中 | 署名 M に直近ブロックハッシュ（新鮮さ） | リプレイ封じ / 低コスト |
| 中 | 実測レンジ（RSSI/UWB）＋多 witness 三角測量 | 遠隔偽装封じ / ハード依存 |
| 低（将来） | zkML / GNSS OSNMA / C2PA | 最強だが重い |

---

## 7. 実装ロードマップ

- **M1（de-risk / snarkjs のみ）✅ 完了**：`uav_witness_attestation.circom`（drone_id_commitment ＋
  EdDSA device_pubkey ＋ time_bucket を追加、public 出力 14、約 1.2 万制約）＋ snarkjs 生成の
  `Groth16Verifier.sol` ＋ `AttestationRegistry`（Hardhat）。
  **実証済み**：実端末 3 台ぶんの実 Groth16 証明 → 実 Verifier のオンチェーン検証 → 同一 drone_id×
  time_bucket で K=3 合意 (`consensusReached`)。改ざん public signal は実 verifier が拒否。テスト 9/9 通過。
  成果物: `contracts/`, `scripts/build_witness_attestation_assets.sh`, `scripts/gen_witness_sample.js`,
  `zk-distance/samples/witness/`。
- **M2（新規性の本体）**：オンチェーンのカウントを off-chain 再帰アグリゲータ（gnark or Sonobe）に置換。
  「同一ドローン/端末相異/各 within30」を回路内で強制、集約 proof 1 個をオンチェーン 1 回検証。
- **M3（耐偽装の核・耐偽装が主目的なら必須）**：6 章の入力真正性施策を導入。
  まず「ドローン署名 RemoteID の回路内検証」と「端末アテステーション」から。

### 変更 / 新規ファイル（想定）
- `circuits/uav_witness_attestation.circom`（作成済み）
- `circuits/uav_aggregator.*`（M2, gnark/Sonobe）
- `contracts/`：`Groth16Verifier.sol`（snarkjs 生成）＋ `AttestationRegistry.sol`
- `scripts/build_witness_attestation_assets.sh`：回路ビルド＋ Solidity 検証器出力
- `zk-distance/samples/sample_multi_witness.json`：同一 drone_id を共有する複数端末サンプル

### 検証方法（Verification）
- **M1 正常系**：同一 drone_id を持つ K 台分の proof を提出 → 各 verify=OK、`consensus_ok=1`。
- **M1 異常系**：drone_id 不一致を混ぜる → カウント K 未満で不成立。同一 pubkey 二重提出 → 重複排除。
- **M2**：N 台入力で集約 proof 1 個を生成 → オンチェーン 1 回検証で OK。関係を破る入力
  （別ドローン混入 / 同一端末重複 / within30=0）で集約 proof が生成できないことを確認。gas が台数に
  ほぼ非依存であることを計測。
