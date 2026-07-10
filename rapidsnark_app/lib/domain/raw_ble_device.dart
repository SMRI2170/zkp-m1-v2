import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import 'uav_telemetry.dart';

/// BLEスキャンで受信した生の広告データ。解析可否に関わらずすべて保持する。
class RawBleDevice {
  RawBleDevice({
    required this.deviceId,
    required this.deviceName,
    required this.rssi,
    required this.serviceUuids,
    required this.serviceData,
    required this.manufacturerData,
    required this.receivedAt,
  }) : odidPayload = _extractOdid(serviceData, manufacturerData);

  final String deviceId;
  final String deviceName;
  final int rssi;
  final List<String> serviceUuids;
  final Map<String, List<int>> serviceData;       // UUID → bytes
  final Map<int, List<int>> manufacturerData;     // companyId → bytes
  final DateTime receivedAt;

  /// OpenDroneID として解析できたペイロード（解析不可なら null）
  final List<int>? odidPayload;

  bool get isOdid => odidPayload != null;

  static List<int>? _extractOdid(
    Map<String, List<int>> svcData,
    Map<int, List<int>> mfgData,
  ) {
    return UavTelemetryPacket.extractFromServiceData(svcData) ??
        UavTelemetryPacket.extractFromManufacturerData(mfgData);
  }

  static RawBleDevice fromScanResult(ScanResult r) {
    final ad = r.advertisementData;
    final svcData = ad.serviceData.map(
      (k, v) => MapEntry(k.toString().toLowerCase(), v),
    );
    return RawBleDevice(
      deviceId: r.device.remoteId.str,
      deviceName: ad.advName.isNotEmpty ? ad.advName : r.device.remoteId.str,
      rssi: r.rssi,
      serviceUuids: ad.serviceUuids.map((u) => u.toString().toLowerCase()).toList(),
      serviceData: svcData,
      manufacturerData: ad.manufacturerData,
      receivedAt: DateTime.now(),
    );
  }
}

/// bytes → "0A 1B 2C ..." 形式の hex 文字列
String bytesToHex(List<int> bytes) =>
    bytes.map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase()).join(' ');

/// Company ID から人が読めるブランド名を返す（不明なら hex 表記）
String companyIdLabel(int id) {
  const known = <int, String>{
    0x2005: 'DJI (legacy)',
    0x2006: 'DJI',
    0x0043: 'Parrot',
    0x0417: 'Autel Robotics',
    0x06D6: 'Skydio',
    0x004C: 'Apple',
    0x0006: 'Microsoft',
    0x000F: 'Broadcom',
  };
  return known[id] ?? '0x${id.toRadixString(16).padLeft(4, '0').toUpperCase()}';
}
