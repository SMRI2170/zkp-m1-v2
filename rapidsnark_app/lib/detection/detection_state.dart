import 'dart:ui';

/// 単一のドローン検出結果。
/// [box] は元画像に対する正規化座標 (0.0〜1.0)。
class DroneDetection {
  const DroneDetection({
    required this.box,
    required this.label,
    required this.score,
  });

  final Rect box;       // left/top/right/bottom が 0.0〜1.0
  final String label;
  final double score;
}

enum DetectorStatus { loading, ready, error }

/// Riverpod プロバイダが公開するスナップショット。
class DroneDetectionState {
  const DroneDetectionState({
    required this.status,
    required this.detections,
    required this.selectedModelPath,
    this.latencyMs,
    this.errorMessage,
  });

  factory DroneDetectionState.loading({String selectedModelPath = 'assets/models/new-models/best_float32.tflite'}) => DroneDetectionState(
        status: DetectorStatus.loading,
        detections: const [],
        selectedModelPath: selectedModelPath,
      );

  final DetectorStatus status;
  final List<DroneDetection> detections;
  final String selectedModelPath;
  final double? latencyMs;   // 直近推論の所要時間 (ms)
  final String? errorMessage;

  bool get isReady => status == DetectorStatus.ready;

  DroneDetectionState copyWith({
    DetectorStatus? status,
    List<DroneDetection>? detections,
    String? selectedModelPath,
    double? latencyMs,
    String? errorMessage,
  }) =>
      DroneDetectionState(
        status: status ?? this.status,
        detections: detections ?? this.detections,
        selectedModelPath: selectedModelPath ?? this.selectedModelPath,
        latencyMs: latencyMs ?? this.latencyMs,
        errorMessage: errorMessage ?? this.errorMessage,
      );
}
