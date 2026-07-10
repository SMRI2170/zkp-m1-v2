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


def sim_measured_range(true_dist_m, gen: RssiModel, m_samples, rng, est: RssiModel = None):
    """真距離から RSSI を生成(gen=真の環境)し、est(検出器の想定)で距離推定。
    est=None なら較正一致（gen で推定）。est≠gen で較正ズレを模擬する。"""
    if est is None:
        est = gen
    ests = []
    for _ in range(m_samples):
        rssi = gen.A - 10 * gen.n * math.log10(max(true_dist_m, 0.1)) + rng.gauss(0, gen.sigma_db)
        ests.append(est.distance_m(rssi))
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
        d_meas = sim_measured_range(true_dist, env, m_samples, rng, est=est_model)
        d_claim = dist3(w, p_claim)
        scores.append(log_inconsistency(d_claim, d_meas))
    return statistics.median(scores)


# ── 多辺測量（multilateration）─────────────────────────────────────────────
# 地上(z=0)の端末では高さ h は解けないが、参照式との差で h^2 が消えるため
# 発信源の水平位置(x,y)は最小二乗で推定できる。放送位置との水平残差を詐称スコアに。
def _solve2(a11, a12, a21, a22, b1, b2):
    det = a11 * a22 - a12 * a21
    if abs(det) < 1e-9:
        return None
    return ((b1 * a22 - a12 * b2) / det, (a11 * b2 - b1 * a21) / det)


def multilaterate2d(W, d):
    """W: [(x,y,z)...], d: レンジ。水平位置(x,y)を最小二乗推定。"""
    if len(W) < 3:
        return None
    x0, y0, _ = W[0]
    d0 = d[0]
    Sxx = Sxy = Syy = Sxb = Syb = 0.0
    for i in range(1, len(W)):
        xi, yi, _ = W[i]
        ax = 2 * (xi - x0)
        ay = 2 * (yi - y0)
        rhs = (xi * xi + yi * yi - x0 * x0 - y0 * y0) - (d[i] * d[i] - d0 * d0)
        Sxx += ax * ax; Sxy += ax * ay; Syy += ay * ay
        Sxb += ax * rhs; Syb += ay * rhs
    return _solve2(Sxx, Sxy, Sxy, Syy, Sxb, Syb)


def multilat_residual(delta_m, n_wit, env, rng, radius=40.0, alt=20.0, m_samples=8):
    """1 試行の多辺測量残差 = |推定発信源(水平) − 放送位置(水平)|。"""
    p_true = (0.0, 0.0, alt)
    if delta_m == 0.0:
        claim = (0.0, 0.0)
    else:
        ang = rng.uniform(0, 2 * math.pi)
        claim = (delta_m * math.cos(ang), delta_m * math.sin(ang))
    W, D = [], []
    for _ in range(n_wit):
        w = (rng.uniform(-radius, radius), rng.uniform(-radius, radius), 0.0)
        W.append(w)
        D.append(sim_measured_range(dist3(w, p_true), env, m_samples, rng))
    sol = multilaterate2d(W, D)
    if sol is None:
        return 0.0
    return math.hypot(sol[0] - claim[0], sol[1] - claim[1])


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

    print("\n=== 融合方式の比較（N=6, FPR=5%）: 中央値合意 vs 多辺測量 ===")
    print(f"  {'Δ(m)':>6} {'合意TPR':>9} {'多辺測量TPR':>12}")
    hc = [fusion_score(0.0, 6, env, est_model, rng) for _ in range(trials)]
    hm = [multilat_residual(0.0, 6, env, rng) for _ in range(trials)]
    tc = threshold_at_fpr(hc, target_fpr)
    tm = threshold_at_fpr(hm, target_fpr)
    for delta in [10, 20, 30, 50]:
        sc = [fusion_score(float(delta), 6, env, est_model, rng) for _ in range(trials)]
        sm = [multilat_residual(float(delta), 6, env, rng) for _ in range(trials)]
        print(f"  {delta:>6} {tpr_at_threshold(sc, tc):>8.1%} {tpr_at_threshold(sm, tm):>11.1%}")

    print("\n=== ノイズ掃引（N=5, Δ=30m）: RSSI ノイズが効く ===")
    print(f"  {'sigma(dB)':>10} {'AUC':>7} {'検知率TPR':>10}")
    for sig in [2.0, 4.0, 6.0, 8.0]:
        e = RssiModel(A=env.A, n=env.n, sigma_db=sig)
        h = [fusion_score(0.0, 5, e, e, rng) for _ in range(trials)]
        s = [fusion_score(30.0, 5, e, e, rng) for _ in range(trials)]
        t = threshold_at_fpr(h, target_fpr)
        print(f"  {sig:>10} {roc_auc(h, s):>7.3f} {tpr_at_threshold(s, t):>9.1%}")

    print("\n=== 較正ズレの頑健性（N=5, Δ=30m）: 想定 A/n が真値とズレると ===")
    print(f"  {'較正ズレ':>12} {'検知率TPR':>10}")
    cases = [
        ("一致", RssiModel(env.A, env.n, env.sigma_db)),
        ("n +0.5", RssiModel(env.A, env.n + 0.5, env.sigma_db)),
        ("n -0.5", RssiModel(env.A, env.n - 0.5, env.sigma_db)),
        ("A +6dB", RssiModel(env.A + 6, env.n, env.sigma_db)),
        ("A -6dB", RssiModel(env.A - 6, env.n, env.sigma_db)),
    ]
    for label, est in cases:
        h = [fusion_score(0.0, 5, env, est, rng) for _ in range(trials)]
        s = [fusion_score(30.0, 5, env, est, rng) for _ in range(trials)]
        t = threshold_at_fpr(h, target_fpr)
        print(f"  {label:>12} {tpr_at_threshold(s, t):>9.1%}")


if __name__ == "__main__":
    # 暫定パラメータ（実機 fit 前）。est_model=env（較正一致）で理想上限を見る。
    env = RssiModel(A=-40.0, n=2.5, sigma_db=4.0)
    run(env, env)
    print("\n※ 実機較正後は rssi_ranging.fit() の A/n/sigma に差し替えて再実行する。")
