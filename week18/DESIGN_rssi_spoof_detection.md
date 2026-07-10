# 設計 — RSSI による RemoteID なりすまし検知

作成日: 2026-07-09 / ブランチ: `acoustic-detection-zk`
関連: [week18/TASKS.md](TASKS.md) / [week17/DESIGN_multi_witness_blockchain.md](../week17/DESIGN_multi_witness_blockchain.md)
既存資産: `circuits/remoteid_consistency.circom` / `scripts/rssi/rssi_ranging.py` / `rapidsnark_app/lib/core/rssi_ranging.dart`

---

## 1. 目的とスコープ

RemoteID は「自己申告」。放送位置が本物かを、**ドローンを改造せず地上側の RSSI だけで**判定する。
本設計は「RSSI で偽りを検知する」パイプラインの技術設計（原理・判定式・多 witness 融合・評価法・回路）。

対象外: AoA/TDoA など受信ハード依存の精密測位（将来）、映像/音響との融合（別トラック）。

---

## 2. 検知原理 — 2つの独立距離推定の突き合わせ

各 witness（端末）は、同じドローン放送について**2通りの独立な距離**を得る:

- `d_claim = || P_claim − P_witness ||` … 放送位置 P_claim と自端末 GPS から計算（幾何）
- `d_meas` … RSSI から推定（電波の物理）

**放送が本物なら両者は一致する。位置詐称・中継では乖離する。**
放送だけ見れば区別できないが、物理実測（RSSI）を突き合わせて初めて矛盾が出る。

---

## 3. 距離推定と整合判定

### 3.1 RSSI → 距離（log-distance path loss）
```
RSSI(d) = A − 10 n log10(d)     ⇔     d_meas = 10^((A − RSSI) / (10 n))
```
- `A`=1m時RSSI, `n`=伝搬指数。実機 DJI の (rssi, 真距離) で fit（`rssi_ranging.py`）。

### 3.2 誤差は「相対（乗法的）」— 判定は log 比で
RSSI 誤差 σ[dB] は距離では乗法的（`d` の相対誤差 ≈ `10^(σ/10n)` 倍）。よって整合判定は
**log 比の絶対値がしきい値以内か**が自然:
```
inconsistency = | log10(d_claim / d_meas) |
consistent  ⇔  inconsistency ≤ τ ,   τ = k · σ / (10 n)   （k=2 で ~2σ）
```
（回路では平方根/log を避け、相対帯 `d_meas/(1+r) ≤ d_claim ≤ d_meas·(1+r)` の二乗比較に落とす）

### 3.3 ロバスト集約（単発 RSSI は粗すぎる）
同一 UAS_ID の RSSI を短窓で **M サンプル集めて中央値**（マルチパス外れ値に強い）。
`d_meas` は集約後の値を使い、実効 σ を縮める。

---

## 4. 単 witness と多 witness

### 4.1 単 witness の限界
±2σ 帯は広い（30m で [16,57]m）。**単独では"粗い矛盾"しか検知できない**
（例: 放送 5m だが実測 50m）。位置詐称で遠方に飛ばす類は粗い矛盾なので単独でも捕捉可。

### 4.2 多 witness 融合（本命）— 2 方式
- **(a) 合意カウント（まず実装）**: 相異なる位置の N 端末が各自 `consistent/suspicious` を判定。
  `K` 台以上 consistent → 放送を信頼 / `K` 台以上 suspicious → なりすまし警報。
  → 既存 `AttestationRegistry` の集計にそのまま乗る。
- **(b) 多辺測量残差（実装・評価済）**: N 個の `(P_witness_i, d_meas_i)` から
  最小二乗で発信源の水平位置 `P_hat` を推定し、`|| P_hat − P_claim ||` を評価。閾値超で詐称。
  地上(z=0)端末では高さは解けないが、参照式との差で h² が消え水平位置は解ける（`multilaterate2d`）。

  **評価結果（重要）**: 多辺測量は (a) を自動的には上回らない。
  | 条件 (Δ=20m) | 合意カウント TPR | 多辺測量 TPR |
  |---|---|---|
  | N=6, σ=4dB（現実的） | **83%** | 58% |
  | N=6, σ=2dB（低ノイズ） | 99% | 99% |
  | N=12, σ=4dB | 94% | 93% |
  - 現実的な RSSI ノイズ（σ≈4dB）＋少数端末では、**中央値合意の方が優れる**（地上のみの
    悪条件で最小二乗解が暴れ、正常系の残差が大きく FPR しきい値を押し上げるため）。
  - 低ノイズ or 多端末（N≥12）でようやく同等。
  - **結論: 既定は (a) 中央値合意（回路・レジストリの実装と一致）。多辺測量は低ノイズ/多端末の
    好条件でのみ上乗せ**。この負の結果自体が設計判断（簡素な合意を採る）の裏付け。

**なぜ多 witness が効くか**: 放送位置は1点だが witness は空間分散。位置詐称は、真の発信源近くの
witness で必ず矛盾を生む。単一の偽装源では全端末の幾何を同時に満たせない。

---

## 5. 脅威モデルと検知可否

| 攻撃 | 内容 | RSSI で検知できるか |
|---|---|---|
| 位置詐称 | 放送位置だけ真値と別地点に書換 | ○ 真の発信源近くの witness が矛盾を出す |
| 捏造 | 存在しない機体の放送をでっち上げ | △〜○ 放送に見合う RSSI が伴わない/不整合 |
| 中継/ワームホール | 遠方の本物信号を近くで再放送 | ✕ RSSI は中継点を反映。原理的限界（distance-bounding 無し） |
| 単純ジャミング/DoS | 妨害 | 対象外（可用性の問題） |

→ **検知の主眼は「位置詐称」**。中継は限界として明示し、将来 TDoA/実測裏取りで補完。

---

## 6. 評価方法（"本当に検知できるか"の定量化）

実機前に**合成データで先に答えを出す**（`scripts/rssi/eval_spoof_detection.py`）:

1. 真の発信源 `P_true` を置き、N 端末を分散配置。
2. 各端末 RSSI = `pathloss(||P_true−P_i||) + N(0,σ)`。
3. 放送 `P_claim`: 正常系 = `P_true` / 詐称 = `P_true` を Δ[m] ずらす。
4. 単 witness 判定 + 融合判定を計算。
5. **Δ・N・σ を掃引して ROC（TPR/FPR）** と検知下限 `Δ_min` を出す。

**出したい答え**: 「N=5, σ=4dB のとき、位置詐称 ≥ Δ_min m を TPR X / FPR Y で検知」。
→ ここから設計値 `τ`(相対幅) と `K`(必要台数) を決める。

---

## 7. 回路設計

- **`remoteid_consistency.circom`（相対許容版）**: witness ごとに
  `d_meas/(1+r) ≤ d_claim ≤ d_meas·(1+r)` を二乗比較 → `consistency_ok` を公開。
- **`uav_witness_attestation.circom` へ統合**: 入力に `measured_range_cm` を追加、
  `consistency_ok` を public 出力に追加（同一 `drone_id_commitment` に束縛）。座標は private のまま。
- **`AttestationRegistry`**: `(drone_id, time_bucket)` ごとに `consistency_ok` を集計。
  `consistent ≥ K → trusted` / `suspicious ≥ K → spoofAlert` を記録。

---

## 8. データパイプライン

```
アプリ(受信) ──▶ ログ (uas_id, rssi[], P_claim, P_gps, t)  ── CSV/JSON 保存
                       │
                較正: (rssi, 真距離) → fit A/n/σ  (rssi_ranging.py)
                       │
              実行時: 集約(中央値) → d_meas → 整合判定 → consistency_ok
                       │
                回路 → proof → レジストリ集計 → trusted / spoofAlert
```

---

## 9. パラメータ

| 記号 | 意味 | 初期値 | 確定方法 |
|---|---|---|---|
| `A` | 1m での RSSI | −40 dBm(暫定) | 実機 fit |
| `n` | 伝搬指数 | 2.5(市街地寄り) | 実機 fit |
| `σ` | RSSI 残差標準偏差 | 3.5 dB(暫定) | 実機 fit |
| `M` | 集約サンプル数 | 5〜10 | ノイズと応答性の兼合い |
| `τ`/`r` | 整合許容（log比/相対幅） | ~±90%(2σ) | 評価(6章)で決定 |
| `K` | 合意しきい値 | 3(暫定) | 評価(6章)で決定 |

---

## 10. 限界（設計に明記）

- **中継/ワームホール攻撃は RSSI 単独では防げない**（distance-bounding が要る）。
- RSSI は環境依存（マルチパス・遮蔽）。屋内/市街地では `n` が変動 → 環境プロファイル必須。
- witness の GPS 自体が信頼前提（詐称され得る）→ 端末アテステーション(M3)で補完。
- **単独では粗い矛盾のみ**。実用検知率は多 witness の冗長に依存。
- **較正ズレは致命的**（`eval_spoof_detection.py` で定量化）: Δ=30m/N=5 で較正一致 91% に対し、
  想定 n が −0.5 ズレると **7.7%**、A が +6dB ズレると **8%** まで崩壊。
  → 実機較正（Phase 3）は任意でなく必須。要求精度の目安は A を数 dB 以内、n を ±0.5 未満。

---

## 11. 週18マイルストーン対応

| Phase(TASKS.md) | 本設計の該当 |
|---|---|
| P1 判定ロジック | §3（相対判定・ロバスト集約・環境プロファイル） |
| P2 評価（核） | §5 脅威モデル + §6 合成ROC → `τ`,`K` 確定 |
| P3 実機較正 | §8 データパイプライン + §9 パラメータ fit |
| P4 多witness統合 | §4(a) + §7 回路・レジストリ統合 |
| P5 まとめ | 週18スライド |
