import 'dart:math' as math;
import 'dart:ui';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/yuv_to_rgb.dart';
import '../detection/detection_state.dart';
import '../detection/uav_yolo_detector.dart';

/// UavYoloDetector の単一インスタンス（autoDispose）。
/// ページが破棄されると TFLite リソースを解放する。
final detectorProvider =
    NotifierProvider.autoDispose<DetectorNotifier, DroneDetectionState>(
  DetectorNotifier.new,
);

class DetectorNotifier extends Notifier<DroneDetectionState> {
  UavYoloDetector? _detector;
  bool _processing = false;

  @override
  DroneDetectionState build() {
    ref.onDispose(() => _detector?.dispose());
    Future.microtask(_initialize);
    return DroneDetectionState.loading();
  }

  Future<void> _initialize() async {
    try {
      final detector = await UavYoloDetector.tryCreateFromCandidates([
        UavYoloDetector.newModelConfigAsset,
        UavYoloDetector.visdroneFinetunedConfigAsset,
        UavYoloDetector.roboflowDroneConfigAsset,
        UavYoloDetector.defaultConfigAsset,
      ]);
      if (detector == null) {
        state = state.copyWith(
          status: DetectorStatus.error,
          errorMessage: 'モデルが見つかりません。assets に配置してください。',
        );
        return;
      }
      _detector = detector;
      state = state.copyWith(status: DetectorStatus.ready);
    } catch (e) {
      state = state.copyWith(
        status: DetectorStatus.error,
        errorMessage: 'モデル読み込みエラー: $e',
      );
    }
  }

  Future<void> changeModel(String newModelPath) async {
    _detector?.dispose();
    _detector = null;
    state = DroneDetectionState.loading(selectedModelPath: newModelPath);
    await _initialize();
  }

  UavYoloDetector? get detector => _detector;

  /// カメラストリームから受け取った YUV420 フレームを推論する。
  /// 推論中のフレームはスキップする（キューが詰まるのを防ぐ）。
  Future<void> processFrame(CameraImage frame, int sensorOrientation) async {
    final detector = _detector;
    if (_processing || detector == null || !state.isReady) return;

    _processing = true;
    final startedAt = DateTime.now();

    try {
      // YUV420 → RGB（共通実装）
      final rgbImage = yuv420ToRgb(frame);

      // YOLO 推論
      final rawDetections = await detector.detectImage(rgbImage);

      // 絶対座標 → 正規化座標・回転補正
      final normalized = rawDetections
          .take(10)
          .map((d) {
            double nxLeft   = d.left   / frame.width;
            double nxTop    = d.top    / frame.height;
            double nxRight  = d.right  / frame.width;
            double nxBottom = d.bottom / frame.height;

            double finalLeft = nxLeft;
            double finalTop = nxTop;
            double finalRight = nxRight;
            double finalBottom = nxBottom;

            if (sensorOrientation == 90) {
              finalLeft = 1.0 - nxBottom;
              finalTop = nxLeft;
              finalRight = 1.0 - nxTop;
              finalBottom = nxRight;
            } else if (sensorOrientation == 270) {
              finalLeft = nxTop;
              finalTop = 1.0 - nxRight;
              finalRight = nxBottom;
              finalBottom = 1.0 - nxLeft;
            }

            return DroneDetection(
              label: d.label,
              score: d.score,
              box: Rect.fromLTRB(
                math.max(0.0, math.min(1.0, finalLeft)),
                math.max(0.0, math.min(1.0, finalTop)),
                math.max(0.0, math.min(1.0, finalRight)),
                math.max(0.0, math.min(1.0, finalBottom)),
              ),
            );
          })
          .toList();

      state = state.copyWith(
        detections: normalized,
        latencyMs:
            DateTime.now().difference(startedAt).inMilliseconds.toDouble(),
      );
    } catch (e) {
      debugPrint('Frame processing error: $e');
    } finally {
      _processing = false;
    }
  }
}
