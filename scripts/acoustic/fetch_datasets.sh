#!/usr/bin/env bash
# 音響ドローン検知 PoC 用の公開データセット取得スクリプト。
#   - ポジティブ: DroneAudioDataset (Sara Al-Emadi)
#   - ネガティブ: ESC-50 (環境音)
# 取得後、data/audio/{drone,not_drone} へ wav を振り分ける雛形を用意する。
#
# 注意:
#   - ESC-50 は CreativeCommons NonCommercial。研究/教育用途のみ。
#   - 本番端末マイクで録った自前データを必ず drone/ not_drone へ追加すること
#     (マイク特性のドメインギャップで精度が落ちるため)。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DATA="${ROOT}/data"
RAW="${DATA}/raw"
OUT="${DATA}/audio"
mkdir -p "${RAW}" "${OUT}/drone" "${OUT}/not_drone"

echo "== DroneAudioDataset (ポジティブ) =="
if [ ! -d "${RAW}/DroneAudioDataset" ]; then
  git clone --depth 1 https://github.com/saraalemadi/DroneAudioDataset.git \
    "${RAW}/DroneAudioDataset"
else
  echo "  既に取得済み: ${RAW}/DroneAudioDataset"
fi

echo "== ESC-50 (ネガティブ) =="
if [ ! -d "${RAW}/ESC-50-master" ]; then
  curl -L -o "${RAW}/esc50.zip" \
    https://github.com/karolpiczak/ESC-50/archive/master.zip
  unzip -q "${RAW}/esc50.zip" -d "${RAW}"
  rm -f "${RAW}/esc50.zip"
else
  echo "  既に取得済み: ${RAW}/ESC-50-master"
fi

cat <<'EOF'

== 取得完了 ==
次の手順で学習用ディレクトリへ振り分けてください(例):

  # ポジティブ(ドローン音)を drone/ へ
  find scripts/acoustic/data/raw/DroneAudioDataset -name '*.wav' \
    -exec cp {} scripts/acoustic/data/audio/drone/ \;

  # ネガティブ(環境音)を not_drone/ へ
  #   ESC-50 は meta/esc50.csv にラベルがある。全クラスを使うか、
  #   鳥・風・雨・エンジン等の紛らわしいクラスに絞ると誤検知評価に有効。
  find scripts/acoustic/data/raw/ESC-50-master/audio -name '*.wav' \
    -exec cp {} scripts/acoustic/data/audio/not_drone/ \;

その後:
  pip install -r scripts/acoustic/requirements.txt
  python scripts/acoustic/train_linear.py --data-dir scripts/acoustic/data/audio
EOF
