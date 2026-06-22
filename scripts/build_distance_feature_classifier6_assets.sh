#!/usr/bin/env bash
set -euo pipefail

# 6次元の音響特徴つき線形分類器回路をビルドする。
# 重み(WP/WN/ADD)は scripts/acoustic/train_linear.py の出力を
# circuits/distance_30m_time_feature_classifier6.circom の main() に反映済み前提。
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$ROOT_DIR/scripts/build_distance_variant_assets.sh" \
  distance_30m_time_feature_classifier6 \
  "$ROOT_DIR/zk-distance/samples/sample_input_feature_classifier6.json" \
  distance30_feature_classifier6
