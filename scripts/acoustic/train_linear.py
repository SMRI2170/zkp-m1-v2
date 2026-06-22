"""解釈可能特徴 + 線形分類器でドローン音検知器を学習・評価し、
ZK 回路 (feature_classifier) 用の量子化重みを書き出す。

データ配置(どちらか):
  <data_dir>/drone/*.wav      ポジティブ(ドローン音)
  <data_dir>/not_drone/*.wav  ネガティブ(環境音; ESC-50 等)

使い方:
  python train_linear.py --data-dir data/audio --out zk_audio_params.json

設計意図:
  - ロジスティック回帰の線形部分 (w·x + b) をそのまま ZK 内積に対応させる。
  - 特徴は features.py で [0,1] 付近にそろえてあるので、bps(=×10000) で整数量子化。
  - 出力 JSON は回路パラメータ(FEATURE*_WEIGHT, THRESHOLD)へ写像する素。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from features import FEATURE_NAMES, extract_features


def _collect(data_dir: Path):
    rows, labels, paths = [], [], []
    for label, sub in [(1, "drone"), (0, "not_drone")]:
        d = data_dir / sub
        if not d.is_dir():
            continue
        for wav in sorted(d.rglob("*.wav")):
            feats = extract_features(str(wav))
            rows.append(feats)
            labels.append(label)
            paths.append(str(wav))
    if not rows:
        raise SystemExit(
            f"音声が見つかりません: {data_dir}/drone, {data_dir}/not_drone に wav を置いてください。"
        )
    return np.array(rows, dtype=np.float64), np.array(labels), paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--out", default="zk_audio_params.json", type=Path)
    ap.add_argument("--folds", default=5, type=int)
    args = ap.parse_args()

    X, y, _ = _collect(args.data_dir)
    print(f"サンプル数: {len(y)} (drone={int(y.sum())}, not_drone={int((1 - y).sum())})")
    print(f"特徴次元: {X.shape[1]} -> {FEATURE_NAMES}")

    clf = LogisticRegression(max_iter=1000, class_weight="balanced")

    # 交差検証で誤検知傾向を確認(セッション分割が理想だがPoCはStratified)
    n_splits = min(args.folds, int(min(y.sum(), (1 - y).sum())))
    if n_splits >= 2:
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
        proba = cross_val_predict(clf, X, y, cv=cv, method="predict_proba")[:, 1]
        print(f"\n[CV] ROC-AUC = {roc_auc_score(y, proba):.3f}")
        print(classification_report(y, (proba >= 0.5).astype(int),
                                    target_names=["not_drone", "drone"], digits=3))
    else:
        print("\n[警告] データが少なく交差検証をスキップしました。")

    # 全データで最終学習 → ZK 親和な整数量子化
    clf.fit(X, y)
    w = clf.coef_[0]
    b = float(clf.intercept_[0])

    # --- 負の重みに対応する非負量子化 ---------------------------------------
    # 決定境界: w·x + b >= 0 (x は features.py 出力 0..1)。
    # 整数化: x_int = round(x * S_X), w_int = round(w * S_W)。
    #   score_int = sum(w_int_i * x_int_i),  B = round(b * S_X * S_W)
    #   決定: score_int + B >= 0
    # 重みの符号で正(WP)/負(WN)に分離し、すべて非負で比較する:
    #   pos = sum(WP_i * x_int_i),  neg = sum(WN_i * x_int_i)
    #   決定: neg + ADD_NEG <= pos + ADD_POS   (B の符号でオフセット側を決める)
    S_X = 1000  # 特徴スケール (0..1 -> 0..1000)
    S_W = 1000  # 重みスケール
    w_int = [int(round(wi * S_W)) for wi in w]
    WP = [max(wi, 0) for wi in w_int]
    WN = [max(-wi, 0) for wi in w_int]
    B = int(round(b * S_X * S_W))
    ADD_POS = max(B, 0)
    ADD_NEG = max(-B, 0)

    # 検証用に「実ドローンクリップ1件」の量子化特徴をサンプル入力にする
    drone_idx = [i for i in range(len(y)) if y[i] == 1]
    proba_all = clf.predict_proba(X)[:, 1]
    best = max(drone_idx, key=lambda i: proba_all[i])
    x_int = [int(round(float(v) * S_X)) for v in X[best]]
    pos = sum(WP[i] * x_int[i] for i in range(len(x_int)))
    neg = sum(WN[i] * x_int[i] for i in range(len(x_int)))
    model_ok = int((neg + ADD_NEG) <= (pos + ADD_POS))

    params = {
        "feature_names": FEATURE_NAMES,
        "feature_scale_S_X": S_X,
        "weight_scale_S_W": S_W,
        "weights_float": [float(wi) for wi in w],
        "bias_float": b,
        "WP": WP,
        "WN": WN,
        "ADD_POS": ADD_POS,
        "ADD_NEG": ADD_NEG,
        "sample_features_x_int": x_int,
        "sample_model_ok": model_ok,
        "note": (
            "回路 distance_30m_time_feature_classifier(6次元)へ: "
            "WP/WN を正負の重み配列、ADD_POS/ADD_NEG をオフセットに割り当てる。"
            "特徴 x は features.py 出力(0..1)を ×feature_scale_S_X した整数で渡す。"
            "判定: neg + ADD_NEG <= pos + ADD_POS。"
        ),
    }
    args.out.write_text(json.dumps(params, ensure_ascii=False, indent=2))
    print(f"\nZK パラメータを書き出しました: {args.out}")
    for n, wf, wp, wn in zip(FEATURE_NAMES, w, WP, WN):
        print(f"  {n:24s} w={wf:+.4f}  WP={wp:d} WN={wn:d}")
    print(f"  ADD_POS={ADD_POS}  ADD_NEG={ADD_NEG}")
    print(f"  sample x_int={x_int}  -> model_ok={model_ok} (期待値: 1)")


if __name__ == "__main__":
    main()
