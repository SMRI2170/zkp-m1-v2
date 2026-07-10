import 'dart:math' as math;

// 1e-7度あたりの緯度方向cm換算（緯度によらずほぼ一定）
const _latCmPerDegreeE7 = 11132000.0;
const _geoDen = 10000000.0;

/// 経度方向の1e-7度あたりcm換算（緯度に依存するため動的に計算）
double _lonCmPerDegreeE7(double latDeg) =>
    math.cos(latDeg * math.pi / 180.0) * 11132000.0;

/// 緯度を正規化座標に変換（+90 してE7スケール）
int normalizeLatitude(double lat) => ((lat + 90.0) * 10000000).round();

/// 経度を正規化座標に変換（+180 してE7スケール）
int normalizeLongitude(double lon) => ((lon + 180.0) * 10000000).round();

/// メートルをセンチメートルに変換
int metersToCentimeters(double meters) => (meters * 100).round();

/// 2点間の3次元ユークリッド距離（メートル）を近似計算する。
/// 小距離（数km以内）の近似に適している。
double approxDistanceMeters({
  required double droneLat,
  required double droneLon,
  required double droneAlt,
  required double targetLat,
  required double targetLon,
  required double targetAlt,
}) {
  final midLat = (droneLat + targetLat) / 2.0;
  final latDiffE7 = (targetLat - droneLat).abs() * 10000000;
  final lonDiffE7 = (targetLon - droneLon).abs() * 10000000;
  final altDiffCm = (targetAlt - droneAlt).abs() * 100;

  final latMeters = (latDiffE7 * _latCmPerDegreeE7 / _geoDen) / 100;
  final lonMeters = (lonDiffE7 * _lonCmPerDegreeE7(midLat) / _geoDen) / 100;
  final altMeters = altDiffCm / 100;

  return math.sqrt(
    latMeters * latMeters + lonMeters * lonMeters + altMeters * altMeters,
  );
}
