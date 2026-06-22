# 音響ドローン検知 PoC

最小構成（**解釈可能特徴 + 線形分類器**）の音響ドローン検知。
深層学習を使わず、少数次元の特徴を ZK 回路 (`feature_classifier`) の内積へ流せる形で出す。

設計の背景は [`drone_detection_design_2026-06-22.md`](../../drone_detection_design_2026-06-22.md) を参照。

## 構成

| ファイル | 役割 |
|---|---|
| `features.py` | wav → 6次元の解釈可能特徴（倍音/BPF/安定度/トーン性/低中域比/ドップラー傾き） |
| `train_linear.py` | 線形分類器の学習・評価 → ZK 用の量子化重み(JSON)を出力 |
| `fetch_datasets.sh` | 公開データセット取得（DroneAudioDataset + ESC-50） |
| `requirements.txt` | numpy / scipy / soundfile / scikit-learn |

## 手順

```bash
# 1. 依存
pip install -r scripts/acoustic/requirements.txt

# 2. データ取得 → data/audio/{drone,not_drone} へ振り分け(スクリプト末尾の案内に従う)
bash scripts/acoustic/fetch_datasets.sh

# 3. 学習・評価・ZKパラメータ出力
python scripts/acoustic/train_linear.py --data-dir scripts/acoustic/data/audio

# 単体で特徴を見る
python scripts/acoustic/features.py path/to/clip.wav
```

## 特徴ベクトル (6次元)

| # | 名前 | 意味 | ドローンで |
|---|---|---|---|
| 0 | harmonic_comb_strength | プロペラ倍音のエネルギー比 | 高い |
| 1 | f0_norm | 推定BPF / 400Hz | — |
| 2 | f0_stability | BPFの時間安定度 | 高い |
| 3 | tonality | 1 − スペクトル平坦度 | 高い |
| 4 | low_mid_ratio | 100–1000Hz帯エネルギー比 | 高い |
| 5 | doppler_slope | BPFの時間傾き(移動音源) | 非ゼロ |

## ZK 連携

`train_linear.py` は `zk_audio_params.json` に `weights_bps` / `threshold_bps` を出力。
これを回路 `distance_30m_time_feature_classifier.circom` の
`FEATUREi_WEIGHT` / `FEATURE_SCORE_THRESHOLD` に割り当てる。
特徴 `x`（0..1）は `×bps_scale(=10000)` の整数で回路へ渡す。

## 注意

- **本番端末マイクの自前録音を必ず混ぜる**（公開データはマイク特性が異なりドメインギャップが出る）。
- 交差検証はPoC簡易版（Stratified）。本来は**録音セッション単位で分割**しないとリークする。
- ESC-50 は NonCommercial。商用化時はライセンス要確認。
- **音単独で「本物保証」はできない**。RemoteID / 映像との時空間整合で担保する（設計メモ参照）。
