enum DroneInputMode { manual, ble }

enum SafetyCircuitProfile {
  base,
  detectionFlag,
  detectionCommitment,
  featureClassifier,
  timeSeries,
}

class SafetyCircuitConfig {
  const SafetyCircuitConfig({
    required this.profile,
    required this.label,
    required this.assetPrefix,
    required this.description,
    this.requiresVideo = false,
  });

  final SafetyCircuitProfile profile;
  final String label;
  final String assetPrefix;
  final String description;
  final bool requiresVideo;

  /// 全プロファイルのリスト
  static const List<SafetyCircuitConfig> all = [
    SafetyCircuitConfig(
      profile: SafetyCircuitProfile.base,
      label: 'Base',
      assetPrefix: 'distance30',
      description: '距離と時刻だけを証明する最小構成です。',
    ),
    SafetyCircuitConfig(
      profile: SafetyCircuitProfile.detectionFlag,
      label: 'Detection Flag',
      assetPrefix: 'distance30_detection_flag',
      description: 'UAV 検知フラグとスコア・クラスを追加する軽量案です。',
      requiresVideo: true,
    ),
    SafetyCircuitConfig(
      profile: SafetyCircuitProfile.detectionCommitment,
      label: 'Commitment',
      assetPrefix: 'distance30_detection_commitment',
      description: '座標を Poseidon ハッシュでコミットメント化し、プライバシーを保ちながら接近と検知を証明します。',
    ),
    SafetyCircuitConfig(
      profile: SafetyCircuitProfile.featureClassifier,
      label: 'Feature Classifier',
      assetPrefix: 'distance30_feature_classifier',
      description: '外部抽出した特徴量を小さな分類器で評価する拡張案です。',
      requiresVideo: true,
    ),
    SafetyCircuitConfig(
      profile: SafetyCircuitProfile.timeSeries,
      label: 'Time Series (20点)',
      assetPrefix: 'distance30_time_series',
      description: '録画中に収集した最大 20 ペアの時系列データを使い、いずれか 1 点でも接近していれば接近を証明します。',
    ),
  ];

  /// .wcd ファイルのアセットパス
  String get wcdAssetPath {
    if (profile == SafetyCircuitProfile.base) {
      return 'assets/distance30.wcd';
    }
    return 'assets/circuits/$assetPrefix/$assetPrefix.wcd';
  }

  /// _groth16.zkey ファイルのアセットパス
  String get zkeyAssetPath {
    if (profile == SafetyCircuitProfile.base) {
      return 'assets/distance30_groth16.zkey';
    }
    return 'assets/circuits/$assetPrefix/${assetPrefix}_groth16.zkey';
  }

  /// _verification_key.json ファイルのアセットパス
  String get verificationKeyAssetPath {
    if (profile == SafetyCircuitProfile.base) {
      return 'assets/distance30_verification_key.json';
    }
    return 'assets/circuits/$assetPrefix/${assetPrefix}_verification_key.json';
  }
}
