#!/usr/bin/env python3
"""RSSI → 距離 の較正モデル（log-distance path loss）。

RemoteID ビーコンの受信強度 RSSI から、consistency 回路に渡す measured_range_cm を得る。
実機 DJI で (rssi, 真の距離) を収集して fit すれば A(1m時RSSI) と n(伝搬指数) が定まる。

モデル:
    RSSI(d) = A - 10 * n * log10(d)          … d は m
    ⇔ 距離推定: d = 10 ** ((A - RSSI) / (10 * n))

重要な性質:
    RSSI 誤差 σ[dB] は距離では「乗法的」に効く（log スケールのため）。
        d の相対誤差 ≒ 10 ** (σ / (10 * n)) 倍
    → 許容誤差は「固定 m」ではなく「相対 %」で設計すべき（回路 TOL への示唆）。

依存なし（標準ライブラリのみ）。
"""
from __future__ import annotations
import math
import statistics
from dataclasses import dataclass


@dataclass
class RssiModel:
    A: float          # 1m での RSSI [dBm]
    n: float          # path-loss 指数（自由空間 2.0、市街地 2.5〜4）
    sigma_db: float   # フィット残差の標準偏差 [dB]

    def distance_m(self, rssi: float) -> float:
        return 10.0 ** ((self.A - rssi) / (10.0 * self.n))

    def distance_from_samples(self, rssi_samples: list[float]) -> float:
        """複数 RSSI サンプルの中央値から距離推定（マルチパス外れ値にロバスト）。"""
        return self.distance_m(statistics.median(rssi_samples))

    def rel_band(self, k: float = 1.0) -> float:
        """距離推定の相対誤差係数（±k σ）。d を [d/factor, d*factor] にする factor。"""
        return 10.0 ** (k * self.sigma_db / (10.0 * self.n))

    def distance_band_m(self, rssi: float, k: float = 1.0):
        d = self.distance_m(rssi)
        f = self.rel_band(k)
        return d / f, d, d * f

    def measured_range_cm(self, rssi: float) -> int:
        """回路 (remoteid_consistency.circom) に渡す measured_range_cm。"""
        return int(round(self.distance_m(rssi) * 100.0))

    def recommend_tol_ratio(self, k: float = 2.0) -> float:
        """回路の許容帯として推奨する相対幅（±k σ）。例 0.9 = ±90%。"""
        return self.rel_band(k) - 1.0

    def tau(self, k: float = 2.0) -> float:
        """整合判定しきい値（log10 比）。inconsistency <= tau なら整合。"""
        return k * self.sigma_db / (10.0 * self.n)

    def is_consistent(self, d_claim_m: float, d_meas_m: float, k: float = 2.0) -> bool:
        """放送距離 d_claim と実測距離 d_meas が RSSI 誤差帯内で整合するか。"""
        return log_inconsistency(d_claim_m, d_meas_m) <= self.tau(k)


def log_inconsistency(d_claim_m: float, d_meas_m: float) -> float:
    """|log10(d_claim / d_meas)|。RSSI 誤差は乗法的なので log 比で測る。"""
    if d_claim_m <= 0 or d_meas_m <= 0:
        return float("inf")
    return abs(math.log10(d_claim_m / d_meas_m))


def fit(samples: list[tuple[float, float]]) -> RssiModel:
    """samples: [(distance_m, rssi_dBm), ...] を log 空間で最小二乗フィット。
       y = A - 10n * x,  x = log10(d)  →  線形回帰。"""
    xs = [math.log10(d) for d, _ in samples]
    ys = [r for _, r in samples]
    m = len(samples)
    mx = sum(xs) / m
    my = sum(ys) / m
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx            # = -10n
    intercept = my - slope * mx  # = A
    A = intercept
    n = -slope / 10.0
    resid = [y - (A - 10.0 * n * x) for x, y in zip(xs, ys)]
    sigma = math.sqrt(sum(r * r for r in resid) / max(m - 2, 1))
    return RssiModel(A=A, n=n, sigma_db=sigma)


# ── 合成データによる自己検証（実機データが来るまでの代替）──────────────────────
def _demo():
    import random
    random.seed(7)
    TRUE_A, TRUE_N, NOISE = -40.0, 2.5, 4.0  # 1m=-40dBm, 市街地寄り, 実測ノイズ4dB
    dists = [1, 2, 3, 5, 8, 12, 20, 30, 50, 80]
    samples = []
    for d in dists:
        for _ in range(6):
            rssi = TRUE_A - 10 * TRUE_N * math.log10(d) + random.gauss(0, NOISE)
            samples.append((d, rssi))

    model = fit(samples)
    print("=== fit result (synthetic) ===")
    print(f"  A={model.A:.2f} dBm (true {TRUE_A})   n={model.n:.3f} (true {TRUE_N})   "
          f"sigma={model.sigma_db:.2f} dB (true {NOISE})")
    print(f"  相対誤差 ±1σ = ±{(model.rel_band(1)-1)*100:.0f}%   "
          f"±2σ = ±{(model.rel_band(2)-1)*100:.0f}%")
    print("\n=== 距離推定と誤差帯 (±2σ) ===")
    for d in [3, 10, 30]:
        rssi = TRUE_A - 10 * TRUE_N * math.log10(d)
        lo, mid, hi = model.distance_band_m(rssi, k=2)
        print(f"  真 {d:>2}m: rssi={rssi:6.1f}dBm → 推定 {mid:5.1f}m  帯[{lo:5.1f}, {hi:6.1f}]m  "
              f"measured_range_cm={model.measured_range_cm(rssi)}")
    print(f"\n=== 回路 TOL への示唆 ===")
    print(f"  固定 TOL_CM ではなく相対許容 ±{model.recommend_tol_ratio(2)*100:.0f}% を推奨")

    print("\n=== 集約のロバスト化（真30m, 外れ値混入）: 単発 vs 中央値 ===")
    true_d = 30.0
    trials, M = 400, 9
    single_err, med_err = 0.0, 0.0
    for _ in range(trials):
        pack = []
        for _ in range(M):
            noise = random.gauss(0, NOISE)
            if random.random() < 0.2:      # 20% は大きなマルチパス外れ値
                noise += random.choice([-1, 1]) * 12.0
            pack.append(TRUE_A - 10 * TRUE_N * math.log10(true_d) + noise)
        single_err += abs(model.distance_m(pack[0]) - true_d)
        med_err += abs(model.distance_from_samples(pack) - true_d)
    print(f"  単発 平均絶対誤差   = {single_err/trials:5.1f} m")
    print(f"  中央値({M}件) 誤差  = {med_err/trials:5.1f} m")


if __name__ == "__main__":
    _demo()
