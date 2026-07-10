#!/usr/bin/env python3
"""RSSI なりすまし検知の評価ハーネス（合成データ）。

設計 week18/DESIGN_rssi_spoof_detection.md §6 の実装。
実機前に「位置詐称を RSSI でどの程度検知できるか」を数値で出す。

シナリオ:
  真の発信源 P_true の周りに N 端末を分散配置。各端末の RSSI は
  pathloss(真距離)+ノイズ。放送 P_claim は 正常系=P_true / 詐称=Δ[m]ずらす。
  各端末は d_claim(放送+自GPS) と d_meas(RSSI) の log 比を不整合スコアに。
  融合 = 端末スコアの中央値（多 witness 合意の連続版）。

出力: ROC(AUC) / 目標 FPR での検知率(TPR) / Δ掃引 / N掃引。
依存なし（標準ライブラリのみ）。
"""
from __future__ import annotations
import math
import random
import statistics

from rssi_ranging import RssiModel, log_inconsistency


# ── 幾何 ─────────────────────────────────────────────────────────────────────
def dist3(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def sim_measured_range(true_dist_m, env: RssiModel, m_samples, rng):
    """真距離から RSSI を M サンプル生成し、中央値で距離推定（ロバスト集約）。"""
    ests = []
    for _ in range(m_samples):
        rssi = env.A - 10 * env.n * math.log10(max(true_dist_m, 0.1)) + rng.gauss(0, env.sigma_db)
        ests.append(env.distance_m(rssi))
    return statistics.median(ests)


def fusion_score(delta_m, n_wit, env, est_model, rng, radius=40.0, alt=20.0, m_samples=8):
    """1 試行の融合不整合スコア（端末ごとの log 不整合の中央値）。"""
    p_true = (0.0, 0.0, alt)
    if delta_m == 0.0:
        p_claim = p_true
    else:
        ang = rng.uniform(0, 2 * math.pi)
        p_claim = (delta_m * math.cos(ang), delta_m * math.sin(ang), alt)

    scores = []
    for _ in range(n_wit):
        w = (rng.uniform(-radius, radius), rng.uniform(-radius, radius), 0.0)
        true_dist = dist3(w, p_true)
        d_meas = sim_measured_range(true_dist, env, m_samples, rng)
        d_claim = dist3(w, p_claim)
        scores.append(log_inconsistency(d_claim, d_meas))
    return statistics.median(scores)


# ── ROC ──────────────────────────────────────────────────────────────────────
def roc_auc(honest, spoof):
    """スコアが高いほど詐称。AUC を Mann-Whitney U で厳密計算。"""
    n_pos, n_neg = len(spoof), len(honest)
    allv = [(s, 1) for s in spoof] + [(s, 0) for s in honest]
    allv.sort(key=lambda x: x[0])
    rank_sum_pos = 0.0
    i = 0
    r = 1
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        avg_rank = (r + (r + (j - i) - 1)) / 2.0
        for k in range(i, j):
            if allv[k][1] == 1:
                rank_sum_pos += avg_rank
        r += (j - i)
        i = j
    auc = (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return auc


def threshold_at_fpr(honest, target_fpr):
    """正常系スコアの上側 target_fpr 分位点をしきい値に。"""
    s = sorted(honest)
    idx = min(len(s) - 1, int(math.ceil((1.0 - target_fpr) * len(s))) - 1)
    return s[max(idx, 0)]


def tpr_at_threshold(spoof, thr):
    return sum(1 for x in spoof if x > thr) / len(spoof)


# ── 実験 ─────────────────────────────────────────────────────────────────────
def run(env, est_model, trials=3000, target_fpr=0.05, seed=11):
    rng = random.Random(seed)
    print("=== 設定 ===")
    print(f"  環境(真): A={env.A} n={env.n} sigma={env.sigma_db}dB   "
          f"半径40m / 高度20m / 集約M=8 / 試行={trials} / 目標FPR={target_fpr:.0%}")

    print("\n=== Δ 掃引（N=5 端末）: 位置詐称 Δm を検知できるか ===")
    print(f"  {'Δ(m)':>6} {'AUC':>7} {'検知率TPR':>10} {'@FPR':>6}")
    honest = [fusion_score(0.0, 5, env, est_model, rng) for _ in range(trials)]
    thr = threshold_at_fpr(honest, target_fpr)
    for delta in [5, 10, 20, 30, 50, 100]:
        spoof = [fusion_score(float(delta), 5, env, est_model, rng) for _ in range(trials)]
        auc = roc_auc(honest, spoof)
        tpr = tpr_at_threshold(spoof, thr)
        print(f"  {delta:>6} {auc:>7.3f} {tpr:>9.1%} {target_fpr:>6.0%}")

    print("\n=== N 掃引（Δ=30m 固定）: 何台の witness で実用検知率か ===")
    print(f"  {'N':>4} {'AUC':>7} {'検知率TPR':>10} {'@FPR':>6}")
    for n_wit in [1, 3, 5, 8, 12]:
        h = [fusion_score(0.0, n_wit, env, est_model, rng) for _ in range(trials)]
        s = [fusion_score(30.0, n_wit, env, est_model, rng) for _ in range(trials)]
        t = threshold_at_fpr(h, target_fpr)
        auc = roc_auc(h, s)
        tpr = tpr_at_threshold(s, t)
        print(f"  {n_wit:>4} {auc:>7.3f} {tpr:>9.1%} {target_fpr:>6.0%}")

    print("\n=== ノイズ掃引（N=5, Δ=30m）: RSSI ノイズが効く ===")
    print(f"  {'sigma(dB)':>10} {'AUC':>7} {'検知率TPR':>10}")
    for sig in [2.0, 4.0, 6.0, 8.0]:
        e = RssiModel(A=env.A, n=env.n, sigma_db=sig)
        h = [fusion_score(0.0, 5, e, e, rng) for _ in range(trials)]
        s = [fusion_score(30.0, 5, e, e, rng) for _ in range(trials)]
        t = threshold_at_fpr(h, target_fpr)
        print(f"  {sig:>10} {roc_auc(h, s):>7.3f} {tpr_at_threshold(s, t):>9.1%}")


if __name__ == "__main__":
    # 暫定パラメータ（実機 fit 前）。est_model=env（較正一致）で理想上限を見る。
    env = RssiModel(A=-40.0, n=2.5, sigma_db=4.0)
    run(env, env)
    print("\n※ 実機較正後は rssi_ranging.fit() の A/n/sigma に差し替えて再実行する。")
