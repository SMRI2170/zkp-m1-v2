import 'dart:typed_data';

import 'uav_system_packet.dart';

// ── OpenDroneID パケット (ASTM F3411-22a / opendroneid-core-c 準拠) ───────────
//
// BLE Service UUID 0xFFFA の Service Data AD から解析する。
// remote_id.py が BasicID (偶数 seq) と Location (奇数 seq) を交互に送信するため、
// スキャナーは Location メッセージを見つけ次第フォームに反映する。
//
// Location メッセージ (25 bytes) — opendroneid-core-c ODID_Location_encoded_t:
//   Byte 0    : (MessageType=1 << 4) | ProtoVersion
//   Byte 1    : Status[7:4] | Reserved[3] | HeightType[2] | EWDirection[1] | SpeedMult[0]
//   Byte 2    : Direction (uint8)
//   Byte 3    : SpeedHorizontal (uint8)
//   Byte 4    : SpeedVertical (int8, ÷0.5 m/s)
//   Bytes 5-8 : Latitude  (int32 LE, × 1e-7 degrees)
//   Bytes 9-12: Longitude (int32 LE, × 1e-7 degrees)
//   Bytes 13-14: AltitudeBaro (uint16 LE)
//   Bytes 15-16: AltitudeGeo  (uint16 LE)
//   Bytes 17-18: Height      (uint16 LE)
//   Byte 19   : HorizAcc[3:0] | VertAcc[7:4]
//   Byte 20   : BaroAcc[3:0]  | SpeedAcc[7:4]
//   Bytes 21-22: Timestamp (uint16 LE, 1/10 sec since UTC hour start)
//   Byte 23   : TSAcc[3:0] | Reserved[7:4]
//   Byte 24   : Reserved
class UavTelemetryPacket {
  const UavTelemetryPacket({
    required this.latitude,
    required this.longitude,
    required this.altitudeMeters,
    required this.altitudeGeoMeters,
    required this.speedH,
    required this.speedV,
    required this.direction,
    required this.statusIsAirborne,
    required this.unixTimeSec,
    required this.sequence,
    this.uasId,
  });

  // OpenDroneID BLE Service UUID (16-bit: 0xFFFA)
  static const serviceUuid = '0000fffa-0000-1000-8000-00805f9b34fb';

  // opendroneid-core-c ODID_MsgType_t
  static const _msgTypeBasicId  = 0;
  static const _msgTypeLocation = 1;
  static const _msgTypeSystem   = 4;
  static const _msgTypeMsgPack  = 0xF;

  // opendroneid-core-c BLE App Code (0x0D) — Service Data の先頭に付くことがある
  static const _odidAppCode = 0x0D;

  // BLE Manufacturer Data Company IDs
  // Key: company ID (little-endian uint16), Value: ブランド名（デバッグ用）
  static const _knownManufacturerIds = <int, String>{
    0x2005: 'DJI (legacy)',   // DJI 旧機種
    0x2006: 'DJI',            // DJI 新世代ファーム
    0x0043: 'Parrot',
    0x0417: 'Autel Robotics',
    0x06D6: 'Skydio',
  };

  // opendroneid-core-c ODID_Status_t
  static const _statusAirborne = 2;

  final double latitude;
  final double longitude;
  final double altitudeMeters;     // AltitudeBaro (QFE, BME280)
  final double altitudeGeoMeters;  // AltitudeGeo (GPS WGS84)
  final double speedH;             // 水平速度 m/s
  final double speedV;             // 垂直速度 m/s (正=上昇)
  final double direction;          // 進行方向 degrees (0-359)
  final bool statusIsAirborne;     // Status == AIRBORNE
  final int unixTimeSec;
  final int sequence;
  final String? uasId;

  static double _decodeAltitude(int raw) {
    if (raw == 0xFFFF) return 0.0;
    return raw * 0.5 - 1000.0;
  }

  static double _decodeDirection(int raw, int ewDir) {
    return ewDir == 1 ? raw + 180.0 : raw.toDouble();
  }

  static double _decodeSpeedH(int raw, int speedMult) {
    return speedMult == 1 ? raw * 0.75 : raw * 0.25;
  }

  static double _decodeSpeedV(int raw) {
    final signed = raw >= 128 ? raw - 256 : raw;
    return signed * 0.5;
  }

  static int _reconstructUnixTime(int tsRaw) {
    if (tsRaw == 0xFFFF) return DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final secondsWithinHour = tsRaw ~/ 10;
    final nowSec = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final hourStart = nowSec - (nowSec % 3600);
    return hourStart + secondsWithinHour;
  }

  /// Location メッセージ (type=1) をパースしてパケットを返す。
  static UavTelemetryPacket? tryParseLocation(List<int>? rawBytes, int seq) {
    if (rawBytes == null || rawBytes.length < 25) return null;
    final msgType = (rawBytes[0] >> 4) & 0x0F;
    if (msgType != _msgTypeLocation) return null;

    final byte1     = rawBytes[1] & 0xFF;
    final status    = (byte1 >> 4) & 0x0F;
    final ewDir     = (byte1 >> 1) & 0x01;
    final speedMult = byte1 & 0x01;

    final data = ByteData.sublistView(Uint8List.fromList(rawBytes));
    final latI32   = data.getInt32(5,  Endian.little);
    final lonI32   = data.getInt32(9,  Endian.little);
    final altBaro  = data.getUint16(13, Endian.little);
    final altGeo   = data.getUint16(15, Endian.little);
    final tsRaw    = data.getUint16(21, Endian.little);

    if (latI32 == 0 && lonI32 == 0) return null;

    return UavTelemetryPacket(
      latitude:         latI32 / 1e7,
      longitude:        lonI32 / 1e7,
      altitudeMeters:   _decodeAltitude(altBaro),
      altitudeGeoMeters: _decodeAltitude(altGeo),
      speedH:           _decodeSpeedH(rawBytes[3] & 0xFF, speedMult),
      speedV:           _decodeSpeedV(rawBytes[4] & 0xFF),
      direction:        _decodeDirection(rawBytes[2] & 0xFF, ewDir),
      statusIsAirborne: status == _statusAirborne,
      unixTimeSec:      _reconstructUnixTime(tsRaw),
      sequence:         seq,
    );
  }

  /// BasicID メッセージ (type=0) から UAS_ID 文字列を取り出す。
  static String? tryParseUasId(List<int>? rawBytes) {
    if (rawBytes == null || rawBytes.length < 25) return null;
    final msgType = (rawBytes[0] >> 4) & 0x0F;
    if (msgType != _msgTypeBasicId) return null;

    final idBytes = rawBytes.sublist(2, 22);
    final nullIdx = idBytes.indexOf(0);
    return String.fromCharCodes(nullIdx >= 0 ? idBytes.sublist(0, nullIdx) : idBytes)
        .trim()
        .replaceAll('\x00', '');
  }

  /// System メッセージ (type=4) をパースしてオペレーター位置等を返す。
  static UavSystemPacket? tryParseSystem(List<int>? rawBytes) {
    if (rawBytes == null || rawBytes.length < 25) return null;
    final msgType = (rawBytes[0] >> 4) & 0x0F;
    if (msgType != _msgTypeSystem) return null;

    final byte1 = rawBytes[1] & 0xFF;
    final data  = ByteData.sublistView(Uint8List.fromList(rawBytes));
    final latI32 = data.getInt32(2, Endian.little);
    final lonI32 = data.getInt32(6, Endian.little);

    if (latI32 == 0 && lonI32 == 0) return null;

    final altGeoRaw = data.getFloat32(18, Endian.little);

    return UavSystemPacket(
      operatorLatitude:    latI32 / 1e7,
      operatorLongitude:   lonI32 / 1e7,
      operatorAltitudeGeo: altGeoRaw.isFinite ? altGeoRaw : 0.0,
      areaCount:           data.getUint16(10, Endian.little),
      areaRadiusMeters:    (rawBytes[12] & 0xFF) * 10,
      areaCeilingMeters:   _decodeAltitude(data.getUint16(13, Endian.little)),
      areaFloorMeters:     _decodeAltitude(data.getUint16(15, Endian.little)),
      operatorLocationType: byte1 & 0x03,
      classificationType:   (byte1 >> 2) & 0x07,
    );
  }

  /// Service Data マップから OpenDroneID のペイロードを取り出す。
  /// flutter_blue_plus は UUID キーを 128-bit 文字列で返すため "fffa" を含むものを選択する。
  /// opendroneid-core-c の実装では先頭に App Code (0x0D) が付く場合があるため除去する。
  static List<int>? extractFromServiceData(Map<dynamic, List<int>> serviceData) {
    for (final entry in serviceData.entries) {
      final key = entry.key.toString().toLowerCase();
      if (!key.contains('fffa')) continue;
      final raw = entry.value;
      if (raw.isEmpty) continue;
      // App Code 0x0D が先頭にある場合はスキップして ODID ペイロードを返す
      if (raw[0] == _odidAppCode && raw.length > 1) return raw.sublist(1);
      return raw;
    }
    return null;
  }

  /// 全既知メーカーの Manufacturer Data から OpenDroneID ペイロードを取り出す。
  /// App Code (0x0D) プレフィックスを除去してから返す。
  static List<int>? extractFromManufacturerData(Map<int, List<int>> manufacturerData) {
    for (final id in _knownManufacturerIds.keys) {
      final raw = manufacturerData[id];
      if (raw == null || raw.isEmpty) continue;
      if (raw[0] == _odidAppCode && raw.length > 1) return raw.sublist(1);
      return raw;
    }
    return null;
  }

  /// Service Data ペイロードに含まれる全 25B OpenDroneID メッセージを返す。
  /// Message Pack (type=0xF) はヘッダーを解析して各 25B メッセージを取り出す。
  static List<List<int>> extractAllMessages(List<int> payload) {
    if (payload.isEmpty) return [];
    final type = (payload[0] >> 4) & 0xF;
    if (type != _msgTypeMsgPack) return [payload];

    if (payload.length < 3) return [];
    final count = payload[2];
    final messages = <List<int>>[];
    for (var i = 0; i < count; i++) {
      final start = 3 + i * 25;
      if (start + 25 > payload.length) break;
      messages.add(payload.sublist(start, start + 25));
    }
    return messages;
  }
}
