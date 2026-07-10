/// 端末（利用者側）の位置スナップショット。
/// GPS + 気圧センサーから取得する。
class PositionSnapshot {
  const PositionSnapshot({
    required this.lat,
    required this.lon,
    required this.alt,
    required this.unixTimeSec,
  });

  final double lat;
  final double lon;
  final double alt;         // QFE 相対高度 (m)
  final int unixTimeSec;
}
