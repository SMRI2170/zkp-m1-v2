import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/raw_ble_device.dart';
import '../../domain/uav_telemetry.dart';
import '../../providers/raw_ble_provider.dart';

/// 全BLEデバイスの広告データをリアルタイムで表示するページ。
/// OpenDroneID として解析できなかったデータも含め、hex dump で確認できる。
class BleRawScanPage extends ConsumerWidget {
  const BleRawScanPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final devices = ref.watch(rawBleProvider);

    return Scaffold(
      backgroundColor: const Color(0xFF0A0F0D),
      appBar: AppBar(
        title: const Text('BLE Raw Scan'),
        backgroundColor: const Color(0xFF0A0F0D),
        foregroundColor: Colors.white,
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 4),
            child: Center(
              child: Text(
                '${devices.length} 件',
                style: const TextStyle(color: Colors.white54, fontSize: 13),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.delete_sweep_outlined),
            tooltip: 'リストをクリア',
            onPressed: () => ref.read(rawBleProvider.notifier).clear(),
          ),
        ],
      ),
      body: devices.isEmpty
          ? const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 32,
                    height: 32,
                    child: CircularProgressIndicator(
                      color: Colors.white38,
                      strokeWidth: 2,
                    ),
                  ),
                  SizedBox(height: 16),
                  Text(
                    'BLE スキャン中...',
                    style: TextStyle(color: Colors.white38),
                  ),
                ],
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
              itemCount: devices.length,
              itemBuilder: (context, i) => _DeviceCard(device: devices[i]),
            ),
    );
  }
}

class _DeviceCard extends StatelessWidget {
  const _DeviceCard({required this.device});

  final RawBleDevice device;

  @override
  Widget build(BuildContext context) {
    final isOdid = device.isOdid;
    final borderColor = isOdid ? const Color(0xFF4CAF50) : const Color(0xFF37474F);
    final tagColor = isOdid ? const Color(0xFF4CAF50) : const Color(0xFF607D8B);

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      color: const Color(0xFF111A17),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: borderColor.withValues(alpha: 0.5), width: 1),
      ),
      child: ExpansionTile(
        tilePadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
        childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
        leading: Icon(
          isOdid ? Icons.wifi_tethering : Icons.bluetooth,
          color: isOdid ? const Color(0xFF4CAF50) : Colors.white38,
          size: 22,
        ),
        title: Text(
          device.deviceName,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Row(
            children: [
              _Tag(
                isOdid ? 'Remote ID' : 'Unknown',
                color: tagColor,
              ),
              const SizedBox(width: 6),
              Text(
                '${device.rssi} dBm',
                style: const TextStyle(color: Colors.white38, fontSize: 11),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  device.deviceId,
                  style: const TextStyle(color: Colors.white24, fontSize: 10),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
        children: [
          // Service UUIDs
          if (device.serviceUuids.isNotEmpty)
            _Section(
              label: 'Service UUIDs',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: device.serviceUuids
                    .map((u) => _MonoText(u))
                    .toList(),
              ),
            ),

          // Service Data
          if (device.serviceData.isNotEmpty)
            _Section(
              label: 'Service Data',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: device.serviceData.entries.map((e) {
                  final isOdidUuid = e.key.contains('fffa');
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          _MonoText(e.key, dim: true),
                          if (isOdidUuid)
                            const Padding(
                              padding: EdgeInsets.only(left: 6),
                              child: _Tag('OpenDroneID', color: Color(0xFF4CAF50)),
                            ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      _HexDump(bytes: e.value, isOdid: isOdidUuid),
                      if (isOdidUuid && e.value.isNotEmpty)
                        _OdidSummary(payload: e.value),
                      const SizedBox(height: 8),
                    ],
                  );
                }).toList(),
              ),
            ),

          // Manufacturer Data
          if (device.manufacturerData.isNotEmpty)
            _Section(
              label: 'Manufacturer Data',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: device.manufacturerData.entries.map((e) {
                  final label = companyIdLabel(e.key);
                  final isDrone = const {0x2005, 0x2006, 0x0043, 0x0417, 0x06D6}
                      .contains(e.key);
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          _MonoText(label, dim: true),
                          if (isDrone)
                            const Padding(
                              padding: EdgeInsets.only(left: 6),
                              child: _Tag('Drone', color: Color(0xFF2196F3)),
                            ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      _HexDump(bytes: e.value, isOdid: isDrone),
                      if (isDrone && e.value.isNotEmpty)
                        _OdidSummary(payload: e.value)
                      else if (!isDrone && e.value.isNotEmpty)
                        _UnknownDataDiag(bytes: e.value),
                      const SizedBox(height: 8),
                    ],
                  );
                }).toList(),
              ),
            ),

          // Service Data のうち ODID 以外
          for (final e in device.serviceData.entries)
            if (!e.key.contains('fffa') && e.value.isNotEmpty)
              _Section(
                label: 'Unknown Service Data (${e.key.substring(0, 8)}...)',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _HexDump(bytes: e.value),
                    _UnknownDataDiag(bytes: e.value),
                  ],
                ),
              ),

          if (device.serviceData.isEmpty &&
              device.manufacturerData.isEmpty &&
              device.serviceUuids.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text(
                '広告データなし（名前 / RSSI のみ）',
                style: TextStyle(color: Colors.white38, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }
}

/// OpenDroneID ペイロードの解析サマリー（成功・失敗どちらも詳細表示）
class _OdidSummary extends StatelessWidget {
  const _OdidSummary({required this.payload});

  final List<int> payload;

  @override
  Widget build(BuildContext context) {
    const appCode = 0x0D;
    final hasAppCode = payload.isNotEmpty && payload[0] == appCode && payload.length > 1;
    final data = hasAppCode ? payload.sublist(1) : payload;

    if (data.isEmpty) {
      return _DiagBox(color: Colors.orange, lines: ['⚠ ペイロードが空']);
    }

    final messages = UavTelemetryPacket.extractAllMessages(data);
    if (messages.isEmpty) {
      return _DiagBox(color: Colors.orange, lines: [
        '⚠ メッセージ抽出失敗',
        '  バイト数: ${data.length}',
        '  先頭バイト: 0x${data[0].toRadixString(16).padLeft(2, '0').toUpperCase()}',
      ]);
    }

    final lines = <String>[];
    if (hasAppCode) lines.add('✓ App Code (0x0D) 検出 → 除去して解析');

    bool anySuccess = false;
    for (final msg in messages) {
      if (msg.isEmpty) continue;
      final type = (msg[0] >> 4) & 0xF;
      final proto = msg[0] & 0xF;
      final prefix = '[Type $type  Proto $proto  ${msg.length}B]';

      switch (type) {
        case 0:
          final id = UavTelemetryPacket.tryParseUasId(msg);
          if (id != null && id.isNotEmpty) {
            lines.add('✓ $prefix BasicID: $id');
            anySuccess = true;
          } else {
            lines.add('⚠ $prefix BasicID: ID 文字列が空');
          }
        case 1:
          final p = UavTelemetryPacket.tryParseLocation(msg, 0);
          if (p != null) {
            lines.add('✓ $prefix Location');
            lines.add('    ${p.latitude.toStringAsFixed(6)}, ${p.longitude.toStringAsFixed(6)}');
            lines.add('    Alt(baro)=${p.altitudeMeters.toStringAsFixed(1)}m  Alt(geo)=${p.altitudeGeoMeters.toStringAsFixed(1)}m');
            lines.add('    SpeedH=${p.speedH.toStringAsFixed(1)}m/s  SpeedV=${p.speedV.toStringAsFixed(1)}m/s');
            lines.add('    Dir=${p.direction.toStringAsFixed(0)}°  ${p.statusIsAirborne ? "AIRBORNE" : "GROUND"}');
            anySuccess = true;
          } else {
            // 失敗した理由を診断
            if (msg.length < 25) {
              lines.add('✗ $prefix Location: バイト数不足 (${msg.length}/25)');
            } else {
              final latRaw = (msg[8] << 24) | (msg[7] << 16) | (msg[6] << 8) | msg[5];
              final lonRaw = (msg[12] << 24) | (msg[11] << 16) | (msg[10] << 8) | msg[9];
              if (latRaw == 0 && lonRaw == 0) {
                lines.add('✗ $prefix Location: 座標がゼロ（未設定）');
              } else {
                lines.add('✗ $prefix Location: パース失敗（データ異常）');
              }
            }
          }
        case 2:
          lines.add('○ $prefix Authentication メッセージ（未解析）');
        case 3:
          lines.add('○ $prefix SelfID メッセージ（未解析）');
        case 4:
          final sys = UavTelemetryPacket.tryParseSystem(msg);
          if (sys != null) {
            lines.add('✓ $prefix System');
            lines.add('    OpLat=${sys.operatorLatitude.toStringAsFixed(6)}, OpLon=${sys.operatorLongitude.toStringAsFixed(6)}');
            anySuccess = true;
          } else {
            lines.add('⚠ $prefix System: オペレーター座標がゼロ');
          }
        case 5:
          lines.add('○ $prefix OperatorID メッセージ（未解析）');
        case 0xF:
          lines.add('✓ $prefix MessagePack → ${messages.length} メッセージ展開');
        default:
          lines.add('? $prefix 未知タイプ');
      }
    }

    final color = anySuccess ? const Color(0xFF4CAF50) : Colors.orange;
    return _DiagBox(color: color, lines: lines);
  }
}

/// 未知データの診断（ODID でも既知メーカーでもないデータ用）
class _UnknownDataDiag extends StatelessWidget {
  const _UnknownDataDiag({required this.bytes});

  final List<int> bytes;

  @override
  Widget build(BuildContext context) {
    if (bytes.isEmpty) return const SizedBox.shrink();

    final lines = <String>[];
    lines.add('バイト数: ${bytes.length}');

    // ASCII 表示可能な文字列が含まれるか検査
    final printable = bytes
        .where((b) => b >= 0x20 && b < 0x7F)
        .map((b) => String.fromCharCode(b))
        .join();
    if (printable.length >= 4) {
      lines.add('ASCII: "$printable"');
    }

    // 先頭バイトのパターン推測
    if (bytes.isNotEmpty) {
      final first = bytes[0];
      final type = (first >> 4) & 0xF;
      final sub = first & 0xF;
      lines.add('先頭 0x${first.toRadixString(16).padLeft(2, '0').toUpperCase()}'
          ' → type=$type sub=$sub');

      // OpenDroneID っぽいか判定
      if (bytes.length >= 25 && type <= 5 || type == 0xF) {
        lines.add('⚠ OpenDroneID 形式の可能性あり（UUID が 0xFFFA 以外）');
      }
    }

    return _DiagBox(color: Colors.blueGrey, lines: lines);
  }
}

class _DiagBox extends StatelessWidget {
  const _DiagBox({required this.color, required this.lines});

  final Color color;
  final List<String> lines;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 6),
      padding: const EdgeInsets.all(8),
      width: double.infinity,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: lines
            .map((l) => Text(
                  l,
                  style: TextStyle(
                    color: color == const Color(0xFF4CAF50)
                        ? const Color(0xFF81C784)
                        : color.withValues(alpha: 0.9),
                    fontSize: 11,
                    fontFamily: 'monospace',
                    height: 1.5,
                  ),
                ))
            .toList(),
      ),
    );
  }
}

class _HexDump extends StatelessWidget {
  const _HexDump({required this.bytes, this.isOdid = false});

  final List<int> bytes;
  final bool isOdid;

  /// 16バイト区切りの hex + ASCII 行を生成
  static String _format(List<int> bytes) {
    if (bytes.isEmpty) return '(空)';
    final buf = StringBuffer();
    const cols = 16;
    for (var i = 0; i < bytes.length; i += cols) {
      final chunk = bytes.sublist(i, i + cols > bytes.length ? bytes.length : i + cols);
      final offset = i.toRadixString(16).padLeft(4, '0').toUpperCase();
      final hex = chunk.map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase()).join(' ');
      final hexPadded = hex.padRight(cols * 3 - 1);
      final ascii = chunk.map((b) => (b >= 0x20 && b < 0x7F) ? String.fromCharCode(b) : '.').join();
      buf.writeln('$offset  $hexPadded  $ascii');
    }
    return buf.toString().trimRight();
  }

  @override
  Widget build(BuildContext context) {
    final formatted = _format(bytes);
    final hex = bytesToHex(bytes);
    return GestureDetector(
      onLongPress: () {
        Clipboard.setData(ClipboardData(text: hex));
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('hex をコピーしました'),
            duration: Duration(seconds: 1),
          ),
        );
      },
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: Colors.black26,
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(
          formatted,
          style: TextStyle(
            color: isOdid ? const Color(0xFF80CBC4) : Colors.white54,
            fontSize: 10,
            fontFamily: 'monospace',
            height: 1.6,
          ),
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: Colors.white38,
              fontSize: 10,
              letterSpacing: 0.8,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 6),
          child,
        ],
      ),
    );
  }
}

class _MonoText extends StatelessWidget {
  const _MonoText(this.text, {this.dim = false});

  final String text;
  final bool dim;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: TextStyle(
        color: dim ? Colors.white38 : Colors.white70,
        fontSize: 11,
        fontFamily: 'monospace',
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.label, {required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.5), width: 0.8),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.4,
        ),
      ),
    );
  }
}
