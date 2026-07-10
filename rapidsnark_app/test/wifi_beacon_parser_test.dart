import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:rapidsnark_app/main.dart';

// WiFi Beacon 経由で受信する OpenDroneID のパース処理を、合成サンプルで検証する。
// 実機ドローンが無くても、IE 抽出 → メッセージ展開 → Location/BasicID 解析の
// 一連のパイプラインが正しく動くことを保証する。

/// Location メッセージ (25B, type=1 proto=2) を組み立てる。
List<int> buildLocation({
  required double lat,
  required double lon,
  required double altMeters,
  bool airborne = true,
}) {
  final b = Uint8List(25);
  final d = ByteData.sublistView(b);
  b[0] = (1 << 4) | 2; // MessageType=1, ProtoVersion=2
  b[1] = (airborne ? 2 : 1) << 4; // Status[7:4], ewDir=0, speedMult=0
  d.setInt32(5, (lat * 1e7).round(), Endian.little);
  d.setInt32(9, (lon * 1e7).round(), Endian.little);
  final altRaw = ((altMeters + 1000) / 0.5).round(); // 逆変換: raw*0.5-1000
  d.setUint16(13, altRaw, Endian.little); // AltitudeBaro
  d.setUint16(15, altRaw, Endian.little); // AltitudeGeo
  d.setUint16(21, 0xFFFF, Endian.little); // Timestamp 未設定 → now
  return b;
}

/// BasicID メッセージ (25B, type=0 proto=2) を組み立てる。
List<int> buildBasicId(String uasId) {
  final b = Uint8List(25);
  b[0] = (0 << 4) | 2; // MessageType=0
  final id = uasId.codeUnits;
  for (var i = 0; i < id.length && i < 20; i++) {
    b[2 + i] = id[i]; // ID は byte2..21
  }
  return b;
}

/// Message Pack (type=0xF) を組み立てる。
List<int> buildMessagePack(List<List<int>> messages) {
  final out = <int>[(0xF << 4) | 2, 0x19, messages.length];
  for (final m in messages) {
    out.addAll(m);
  }
  return out;
}

/// WiFi Beacon ベンダ固有 IE content（OUI + type + counter + pack）を組み立てる。
List<int> wrapWifiBeacon(List<int> messagePack, {int counter = 1}) {
  return [0xFA, 0x0B, 0xBC, 0x0D, counter, ...messagePack];
}

void main() {
  group('WiFi Beacon OpenDroneID パース', () {
    test('IE content から Location と BasicID を抽出できる', () {
      final pack = buildMessagePack([
        buildBasicId('TEST-DRONE-1'),
        buildLocation(lat: 35.6895, lon: 139.6917, altMeters: 50.0),
      ]);
      final ie = wrapWifiBeacon(pack);

      final odid = UavTelemetryPacket.extractFromWifiBeacon(ie);
      expect(odid, isNotNull);

      final messages = UavTelemetryPacket.extractAllMessages(odid!);
      expect(messages.length, 2);

      final uasId = UavTelemetryPacket.tryParseUasId(messages[0]);
      expect(uasId, 'TEST-DRONE-1');

      final loc = UavTelemetryPacket.tryParseLocation(messages[1], 0);
      expect(loc, isNotNull);
      expect(loc!.latitude, closeTo(35.6895, 1e-4));
      expect(loc.longitude, closeTo(139.6917, 1e-4));
      expect(loc.altitudeMeters, closeTo(50.0, 0.5));
      expect(loc.statusIsAirborne, isTrue);
    });

    test('OUI ヘッダーが残っていても除去して解析できる', () {
      final pack = buildMessagePack([
        buildLocation(lat: 1.0, lon: 2.0, altMeters: 10.0),
      ]);
      // ネイティブが OUI を除去せず渡してきたケース
      final withHeader = wrapWifiBeacon(pack);
      final odid = UavTelemetryPacket.extractFromWifiBeacon(withHeader);
      expect(odid, isNotNull);
      expect(UavTelemetryPacket.extractAllMessages(odid!).length, 1);
    });

    test('既に message pack（OUI 除去済み）でもそのまま解析できる', () {
      final pack = buildMessagePack([
        buildLocation(lat: 1.0, lon: 2.0, altMeters: 10.0),
      ]);
      // ネイティブ側で 5 バイト除去済みのケース（本番の通常経路）
      final odid = UavTelemetryPacket.extractFromWifiBeacon(pack);
      expect(odid, isNotNull);
      final messages = UavTelemetryPacket.extractAllMessages(odid!);
      expect(messages.length, 1);
      final loc = UavTelemetryPacket.tryParseLocation(messages[0], 0);
      expect(loc, isNotNull);
      expect(loc!.latitude, closeTo(1.0, 1e-4));
    });

    test('空の入力は null を返す', () {
      expect(UavTelemetryPacket.extractFromWifiBeacon(const []), isNull);
    });

    test('座標がゼロの Location は null（未設定として扱う）', () {
      final loc = UavTelemetryPacket.tryParseLocation(
        buildLocation(lat: 0.0, lon: 0.0, altMeters: 0.0),
        0,
      );
      expect(loc, isNull);
    });

    test('単一 Location メッセージ（pack でない）もそのまま展開できる', () {
      final single = buildLocation(lat: -33.8688, lon: 151.2093, altMeters: 5.0);
      final messages = UavTelemetryPacket.extractAllMessages(single);
      expect(messages.length, 1);
      final loc = UavTelemetryPacket.tryParseLocation(messages[0], 0);
      expect(loc, isNotNull);
      expect(loc!.latitude, closeTo(-33.8688, 1e-4));
      expect(loc.longitude, closeTo(151.2093, 1e-4));
    });
  });
}
