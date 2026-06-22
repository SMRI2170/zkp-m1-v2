"""音響ドローン検知のための「解釈可能な特徴」抽出。

設計方針（drone_detection_design_2026-06-22.md より）:
  - 重い処理(STFT)はここ(回路の外)で行い、少数次元の解釈可能特徴に落とす。
  - 出力特徴は最終的に ZK 回路 (feature_classifier) の内積へ流せるよう、
    すべて [0, 1] 付近のスカラにそろえる（後段で固定小数=bps に量子化）。

特徴ベクトル (6 次元):
  0 harmonic_comb_strength  プロペラ倍音(BPF + ハーモニクス)のエネルギー比。ドローンで高い。
  1 f0_norm                 推定基本周波数(BPF) を 400Hz で正規化。
  2 f0_stability            BPF の時間安定度。定常トーンほど高い(ドローン的)。
  3 tonality                1 - スペクトル平坦度。トーン性が高い(=雑音でない)ほど高い。
  4 low_mid_ratio           100-1000Hz 帯のエネルギー比。ドローン音は低中域に集中。
  5 doppler_slope           BPF の時間傾き(移動音源で非ゼロ)。固定スピーカー識別の手掛かり。

注意: これは検知の最小構成。最終的な「本物保証」は単独では不可能であり、
RemoteID / 映像との時空間整合で担保する（設計メモ参照）。
"""

from __future__ import annotations

import numpy as np
from scipy import signal

FEATURE_NAMES = [
    "harmonic_comb_strength",
    "f0_norm",
    "f0_stability",
    "tonality",
    "low_mid_ratio",
    "doppler_slope",
]

TARGET_SR = 16000
# BPF(基本周波数)の探索範囲。マルチコプターのプロペラ基本音は概ねこの帯域。
F0_MIN_HZ = 60.0
F0_MAX_HZ = 400.0
N_HARMONICS = 6  # 倍音をいくつまで足し合わせるか


def load_mono(path: str) -> np.ndarray:
    """wav を読み込み、モノラル・TARGET_SR・振幅正規化して返す。"""
    import soundfile as sf

    data, sr = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != TARGET_SR:
        n_out = int(round(len(data) * TARGET_SR / sr))
        if n_out <= 1:
            return np.zeros(1, dtype=np.float32)
        data = signal.resample(data, n_out).astype(np.float32)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1e-9:
        data = data / peak
    return data.astype(np.float32)


def _stft_mag(x: np.ndarray):
    """短時間フーリエ変換の振幅スペクトログラムと周波数軸を返す。"""
    nperseg = 1024
    noverlap = nperseg // 2
    freqs, _, zxx = signal.stft(
        x, fs=TARGET_SR, nperseg=nperseg, noverlap=noverlap, window="hann"
    )
    mag = np.abs(zxx)  # (freq, frame)
    return freqs, mag


def _harmonic_sum_f0(freqs: np.ndarray, frame_mag: np.ndarray):
    """1 フレームの振幅から、倍音和スペクトルで基本周波数と倍音スコアを推定する。

    戻り値: (f0_hz, harmonic_score[0..1])
    """
    total = float(frame_mag.sum()) + 1e-9
    df = freqs[1] - freqs[0]
    cand_idx = np.where((freqs >= F0_MIN_HZ) & (freqs <= F0_MAX_HZ))[0]
    best_f0 = 0.0
    best_score = 0.0
    n_freq = len(freqs)
    for ci in cand_idx:
        f0 = freqs[ci]
        acc = 0.0
        for h in range(1, N_HARMONICS + 1):
            bin_idx = int(round((f0 * h) / df))
            if bin_idx >= n_freq:
                break
            # 近傍 ±1 bin のピークを拾う(漏れ対策)
            lo = max(0, bin_idx - 1)
            hi = min(n_freq, bin_idx + 2)
            acc += float(frame_mag[lo:hi].max())
        if acc > best_score:
            best_score = acc
            best_f0 = f0
    return best_f0, min(1.0, best_score / total)


def _spectral_flatness(frame_mag: np.ndarray) -> float:
    """スペクトル平坦度(0=トーン的, 1=雑音的)。"""
    p = frame_mag**2 + 1e-12
    gmean = np.exp(np.mean(np.log(p)))
    amean = np.mean(p)
    return float(np.clip(gmean / amean, 0.0, 1.0))


def extract_features(path: str) -> np.ndarray:
    """1 クリップから固定長 6 次元の特徴ベクトルを返す。"""
    x = load_mono(path)
    if x.size < TARGET_SR // 4:  # 0.25 秒未満は無効
        return np.zeros(len(FEATURE_NAMES), dtype=np.float32)

    freqs, mag = _stft_mag(x)
    n_frames = mag.shape[1]
    if n_frames == 0:
        return np.zeros(len(FEATURE_NAMES), dtype=np.float32)

    f0s = np.zeros(n_frames)
    hscores = np.zeros(n_frames)
    flatness = np.zeros(n_frames)
    for t in range(n_frames):
        frame = mag[:, t]
        f0, hs = _harmonic_sum_f0(freqs, frame)
        f0s[t] = f0
        hscores[t] = hs
        flatness[t] = _spectral_flatness(frame)

    # 低中域(100-1000Hz)エネルギー比
    band = np.where((freqs >= 100) & (freqs <= 1000))[0]
    low_mid_ratio = float(mag[band, :].sum() / (mag.sum() + 1e-9))

    # 安定した倍音が出ているフレームのみで f0 統計を取る
    voiced = hscores > np.maximum(0.05, np.median(hscores))
    f0_voiced = f0s[voiced] if voiced.any() else f0s

    harmonic_comb_strength = float(np.clip(np.mean(hscores), 0.0, 1.0))
    f0_mean = float(np.mean(f0_voiced)) if f0_voiced.size else 0.0
    f0_norm = float(np.clip(f0_mean / F0_MAX_HZ, 0.0, 1.0))
    f0_std = float(np.std(f0_voiced)) if f0_voiced.size > 1 else F0_MAX_HZ
    f0_stability = float(1.0 / (1.0 + f0_std / 20.0))  # std 小→1 に近づく
    tonality = float(np.clip(1.0 - np.mean(flatness), 0.0, 1.0))

    # ドップラー傾き: voiced フレームでの f0 の時間一次回帰の傾き
    doppler_slope = 0.0
    if f0_voiced.size > 2:
        idx = np.where(voiced)[0].astype(float) if voiced.any() else np.arange(n_frames, dtype=float)
        slope = np.polyfit(idx, f0_voiced, 1)[0]  # Hz / frame
        doppler_slope = float(np.clip(abs(slope) / 5.0, 0.0, 1.0))

    return np.array(
        [
            harmonic_comb_strength,
            f0_norm,
            f0_stability,
            tonality,
            low_mid_ratio,
            doppler_slope,
        ],
        dtype=np.float32,
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python features.py <wav> [<wav> ...]")
        raise SystemExit(1)
    for p in sys.argv[1:]:
        feats = extract_features(p)
        pairs = ", ".join(f"{n}={v:.3f}" for n, v in zip(FEATURE_NAMES, feats))
        print(f"{p}\n  {pairs}")
