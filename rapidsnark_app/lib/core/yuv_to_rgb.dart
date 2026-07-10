import 'package:camera/camera.dart';
import 'package:image/image.dart' as img;

/// BT.601 YUV420 → RGB 変換（単一の正規実装）
/// drone_detector_provider.dart, uav_live_detection_page.dart, main.dart の
/// 3箇所の重複を統合した共通実装。
img.Image yuv420ToRgb(CameraImage image) {
  final w = image.width;
  final h = image.height;
  final output = img.Image(width: w, height: h);
  final planeY = image.planes[0];
  final planeU = image.planes[1];
  final planeV = image.planes[2];
  final yRowStride = planeY.bytesPerRow;
  final uvRowStride = planeU.bytesPerRow;
  final uvPixelStride = planeU.bytesPerPixel ?? 1;
  for (var row = 0; row < h; row++) {
    final yBase = row * yRowStride;
    final uvBase = (row >> 1) * uvRowStride;
    for (var col = 0; col < w; col++) {
      final uvOffset = uvBase + (col >> 1) * uvPixelStride;
      final yVal = planeY.bytes[yBase + col];
      final uVal = planeU.bytes[uvOffset];
      final vVal = planeV.bytes[uvOffset];
      final r = _clamp((yVal + 1.402 * (vVal - 128)).round());
      final g = _clamp(
          (yVal - 0.344136 * (uVal - 128) - 0.714136 * (vVal - 128)).round());
      final b = _clamp((yVal + 1.772 * (uVal - 128)).round());
      output.setPixelRgba(col, row, r, g, b, 255);
    }
  }
  return output;
}

int _clamp(int v) => v < 0 ? 0 : (v > 255 ? 255 : v);
