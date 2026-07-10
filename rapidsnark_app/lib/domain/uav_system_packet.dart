/// OpenDroneID System メッセージ (type=4, ASTM F3411-22a §6.4) のデコード結果。
/// ZK 証明には使用しないが、規格準拠受信の記録として保持する。
///
/// System メッセージ 25 バイト構成:
///   Byte 0    : (MessageType=4 << 4) | ProtoVersion
///   Byte 1    : OperatorLocationType[1:0] | ClassificationType[4:2] | Reserved[7:5]
///   Bytes 2-5 : OperatorLatitude  (int32 LE, × 1e-7 degrees)
///   Bytes 6-9 : OperatorLongitude (int32 LE, × 1e-7 degrees)
///   Bytes 10-11: AreaCount        (uint16 LE)
///   Byte 12   : AreaRadius        (uint8, × 10 m)
///   Bytes 13-14: AreaCeiling      (uint16 LE, 高度エンコード: (alt+1000)/0.5)
///   Bytes 15-16: AreaFloor        (uint16 LE, 同上)
///   Byte 17   : (ClassEU << 4) | CategoryEU
///   Bytes 18-21: OperatorAltitudeGeo (float32 LE, m)
///   Bytes 22-24: Timestamp 下位 24bit
class UavSystemPacket {
  const UavSystemPacket({
    required this.operatorLatitude,
    required this.operatorLongitude,
    required this.operatorAltitudeGeo,
    required this.areaCount,
    required this.areaRadiusMeters,
    required this.areaCeilingMeters,
    required this.areaFloorMeters,
    required this.operatorLocationType,
    required this.classificationType,
  });

  final double operatorLatitude;
  final double operatorLongitude;
  final double operatorAltitudeGeo; // m, float32 から読み出し
  final int areaCount;
  final int areaRadiusMeters;       // AreaRadius × 10
  final double areaCeilingMeters;
  final double areaFloorMeters;
  final int operatorLocationType;   // 0=TakeOff, 1=LiveGNSS, 2=Fixed, 3=Dynamic
  final int classificationType;

  @override
  String toString() =>
      'System(opLat=${operatorLatitude.toStringAsFixed(6)} '
      'opLon=${operatorLongitude.toStringAsFixed(6)} '
      'opAlt=${operatorAltitudeGeo.toStringAsFixed(1)}m '
      'area=$areaCount×r${areaRadiusMeters}m '
      '[${areaFloorMeters.toStringAsFixed(0)}m-${areaCeilingMeters.toStringAsFixed(0)}m])';
}
