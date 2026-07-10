import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';

import '../../domain/uav_telemetry.dart';

/// 周辺の WiFi ネットワークをリアルタイム表示する診断ページ（BLE Raw の WiFi 版）。
/// ベンダ固有 IE を hex dump で確認でき、OpenDroneID (DJI 等) は強調表示する。
///
/// ネイティブ (WifiRawStreamHandler) の EventChannel `uav/wifi_raw` を購読する。
/// Android 11 (API 30) 未満では IE を取得できないため空表示になる。
class WifiRawScanPage extends StatefulWidget {
  const WifiRawScanPage({super.key});

  @override
  State<WifiRawScanPage> createState() => _WifiRawScanPageState();
}

class _WifiRawScanPageState extends State<WifiRawScanPage> {
  static const _channel = EventChannel('uav/wifi_raw');
  // 一定時間見えなくなったネットワークは一覧から除去する。
  static const _staleAfter = Duration(seconds: 30);
  static const _maxItems = 60;

  final Map<String, _WifiNet> _nets = {};
  StreamSubscription<dynamic>? _sub;
  Timer? _pruneTimer;
  // 位置情報サービス（端末の位置トグル）が OFF だと WiFi スキャン結果は空になる。
  bool _locationServiceOff = false;

  @override
  void initState() {
    super.initState();
    _sub = _channel.receiveBroadcastStream().listen(_onEvent, onError: (_) {});
    unawaited(_checkLocationService());
    // 古いエントリの掃除と位置情報サービス状態の再確認を定期実行する。
    _pruneTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      final changed = _pruneStale();
      unawaited(_checkLocationService());
      if (changed && mounted) setState(() {});
    });
  }

  Future<void> _checkLocationService() async {
    try {
      final enabled = await Geolocator.isLocationServiceEnabled();
      if (mounted && enabled == _locationServiceOff) {
        setState(() => _locationServiceOff = !enabled);
      }
    } catch (_) {}
  }

  @override
  void dispose() {
    _sub?.cancel();
    _pruneTimer?.cancel();
    super.dispose();
  }

  void _onEvent(dynamic event) {
    if (event is! List) return;
    final now = DateTime.now();
    for (final item in event) {
      if (item is! Map) continue;
      final net = _WifiNet.fromMap(item)..lastSeen = now;
      if (net.bssid.isEmpty) continue;
      _nets[net.bssid] = net;
    }
    _pruneStale(now: now);
    if (mounted) setState(() {});
  }

  /// stale なエントリを除去する。削除があれば true。
  bool _pruneStale({DateTime? now}) {
    final cutoff = (now ?? DateTime.now()).subtract(_staleAfter);
    final before = _nets.length;
    _nets.removeWhere((_, net) => net.lastSeen.isBefore(cutoff));
    return _nets.length != before;
  }

  @override
  Widget build(BuildContext context) {
    final nets = _nets.values.toList()
      ..sort((a, b) => b.rssi.compareTo(a.rssi));
    final shown = nets.length > _maxItems ? nets.sublist(0, _maxItems) : nets;

    return Scaffold(
      backgroundColor: const Color(0xFF0A0F0D),
      appBar: AppBar(
        title: const Text('WiFi Raw Scan'),
        backgroundColor: const Color(0xFF0A0F0D),
        foregroundColor: Colors.white,
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 4),
            child: Center(
              child: Text(
                '${shown.length} 件',
                style: const TextStyle(color: Colors.white54, fontSize: 13),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.delete_sweep_outlined),
            tooltip: 'リストをクリア',
            onPressed: () => setState(_nets.clear),
          ),
        ],
      ),
      body: shown.isEmpty
          ? Center(
              child: _locationServiceOff
                  ? Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 32),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.location_off_rounded,
                              color: Color(0xFFFFB74D), size: 36),
                          const SizedBox(height: 14),
                          const Text(
                            '位置情報サービスが OFF です',
                            style: TextStyle(
                                color: Color(0xFFFFB74D),
                                fontSize: 14,
                                fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(height: 8),
                          const Text(
                            'WiFi スキャンには端末の位置情報を ON にする必要があります。\n'
                            '設定 → 位置情報 をオンにしてください。',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: Colors.white38, fontSize: 12),
                          ),
                          const SizedBox(height: 14),
                          OutlinedButton(
                            onPressed: () => Geolocator.openLocationSettings(),
                            child: const Text('位置情報設定を開く'),
                          ),
                        ],
                      ),
                    )
                  : const Column(
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
                        Text('WiFi スキャン中...',
                            style: TextStyle(color: Colors.white38)),
                        SizedBox(height: 6),
                        Text('（生 IE 取得には Android 11 以上が必要）',
                            style: TextStyle(color: Colors.white24, fontSize: 11)),
                      ],
                    ),
            )
          : ListView.builder(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
              itemCount: shown.length,
              itemBuilder: (context, i) => _NetCard(net: shown[i]),
            ),
    );
  }
}

// ── モデル ───────────────────────────────────────────
class _WifiNet {
  _WifiNet({
    required this.bssid,
    required this.ssid,
    required this.rssi,
    required this.frequency,
    required this.capabilities,
    required this.vendorIes,
    required this.odid,
  });

  final String bssid;
  final String ssid;
  final int rssi;
  final int frequency;
  final String capabilities;
  final List<_VendorIe> vendorIes;
  final List<int>? odid;

  /// 最後に受信した時刻（stale 判定用、_onEvent で設定）。
  DateTime lastSeen = DateTime.now();

  bool get isOdid => odid != null && odid!.isNotEmpty;

  static _WifiNet fromMap(Map<dynamic, dynamic> m) {
    final ies = <_VendorIe>[];
    final rawIes = m['vendorIes'];
    if (rawIes is List) {
      for (final e in rawIes) {
        if (e is Map) ies.add(_VendorIe.fromMap(e));
      }
    }
    final rawOdid = m['odid'];
    return _WifiNet(
      bssid: (m['bssid'] as String?) ?? '',
      ssid: (m['ssid'] as String?) ?? '',
      rssi: (m['rssi'] as num?)?.toInt() ?? 0,
      frequency: (m['frequency'] as num?)?.toInt() ?? 0,
      capabilities: (m['capabilities'] as String?) ?? '',
      vendorIes: ies,
      odid: rawOdid == null ? null : List<int>.from(rawOdid as List),
    );
  }

  /// 周波数(MHz) から WiFi チャンネル番号を概算する。
  int? get channel {
    if (frequency == 2484) return 14;
    if (frequency >= 2412 && frequency <= 2472) return (frequency - 2407) ~/ 5;
    if (frequency >= 5000 && frequency <= 5900) return (frequency - 5000) ~/ 5;
    if (frequency >= 5955 && frequency <= 7115) return (frequency - 5950) ~/ 5; // 6GHz
    return null;
  }
}

class _VendorIe {
  _VendorIe({required this.oui, required this.bytes, required this.isOdid});

  final String oui;
  final List<int> bytes;
  final bool isOdid;

  static _VendorIe fromMap(Map<dynamic, dynamic> m) => _VendorIe(
        oui: (m['oui'] as String?) ?? '',
        bytes: m['bytes'] == null ? const [] : List<int>.from(m['bytes'] as List),
        isOdid: (m['isOdid'] as bool?) ?? false,
      );
}

// ── カード ───────────────────────────────────────────
class _NetCard extends StatelessWidget {
  const _NetCard({required this.net});

  final _WifiNet net;

  @override
  Widget build(BuildContext context) {
    final isOdid = net.isOdid;
    final borderColor = isOdid ? const Color(0xFF4CAF50) : const Color(0xFF37474F);
    final tagColor = isOdid ? const Color(0xFF4CAF50) : const Color(0xFF607D8B);
    final name = net.ssid.isNotEmpty ? net.ssid : '(ステルス / 非公開 SSID)';
    final ch = net.channel;

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
          isOdid ? Icons.wifi_tethering : Icons.wifi,
          color: isOdid ? const Color(0xFF4CAF50) : Colors.white38,
          size: 22,
        ),
        title: Text(
          name,
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
              _Tag(isOdid ? 'Remote ID' : 'WiFi', color: tagColor),
              const SizedBox(width: 6),
              Text('${net.rssi} dBm',
                  style: const TextStyle(color: Colors.white38, fontSize: 11)),
              const SizedBox(width: 6),
              if (ch != null)
                Text('ch$ch',
                    style: const TextStyle(color: Colors.white38, fontSize: 11)),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  net.bssid,
                  style: const TextStyle(color: Colors.white24, fontSize: 10),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
        children: [
          _Section(
            label: '基本情報',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _MonoText('周波数: ${net.frequency} MHz'
                    '${ch != null ? '  (ch $ch)' : ''}'),
                _MonoText('セキュリティ: '
                    '${net.capabilities.isEmpty ? '(不明)' : net.capabilities}'),
              ],
            ),
          ),
          if (net.vendorIes.isNotEmpty)
            _Section(
              label: 'Vendor IE (221)',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: net.vendorIes.map((ie) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          _MonoText('OUI ${ie.oui}', dim: true),
                          if (ie.isOdid)
                            const Padding(
                              padding: EdgeInsets.only(left: 6),
                              child: _Tag('OpenDroneID', color: Color(0xFF4CAF50)),
                            ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      _HexDump(bytes: ie.bytes, isOdid: ie.isOdid),
                      const SizedBox(height: 8),
                    ],
                  );
                }).toList(),
              ),
            ),
          if (isOdid)
            _Section(
              label: 'OpenDroneID 解析',
              child: _OdidSummary(payload: net.odid!),
            ),
          if (net.vendorIes.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 6),
              child: Text(
                'ベンダ固有 IE なし（OpenDroneID 非送信）',
                style: TextStyle(color: Colors.white38, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }
}

/// OpenDroneID message pack の解析サマリー（BLE Raw と同じ表示方針）。
class _OdidSummary extends StatelessWidget {
  const _OdidSummary({required this.payload});

  final List<int> payload;

  @override
  Widget build(BuildContext context) {
    final messages = UavTelemetryPacket.extractAllMessages(payload);
    if (messages.isEmpty) {
      return const _DiagBox(color: Colors.orange, lines: ['⚠ メッセージ抽出失敗']);
    }

    final lines = <String>[];
    bool anySuccess = false;
    for (final msg in messages) {
      if (msg.isEmpty) continue;
      final type = (msg[0] >> 4) & 0xF;
      final prefix = '[Type $type  ${msg.length}B]';
      switch (type) {
        case 0:
          final id = UavTelemetryPacket.tryParseUasId(msg);
          if (id != null && id.isNotEmpty) {
            lines.add('✓ $prefix BasicID: $id');
            anySuccess = true;
          } else {
            lines.add('⚠ $prefix BasicID: ID 空');
          }
        case 1:
          final p = UavTelemetryPacket.tryParseLocation(msg, 0);
          if (p != null) {
            lines.add('✓ $prefix Location');
            lines.add('    ${p.latitude.toStringAsFixed(6)}, '
                '${p.longitude.toStringAsFixed(6)}');
            lines.add('    Alt=${p.altitudeMeters.toStringAsFixed(1)}m  '
                '${p.statusIsAirborne ? "AIRBORNE" : "GROUND"}');
            anySuccess = true;
          } else {
            lines.add('✗ $prefix Location: パース不可');
          }
        case 4:
          final sys = UavTelemetryPacket.tryParseSystem(msg);
          if (sys != null) {
            lines.add('✓ $prefix System');
            lines.add('    OpLat=${sys.operatorLatitude.toStringAsFixed(6)}, '
                'OpLon=${sys.operatorLongitude.toStringAsFixed(6)}');
            anySuccess = true;
          } else {
            lines.add('⚠ $prefix System: 座標ゼロ');
          }
        default:
          lines.add('○ $prefix type=$type（未解析）');
      }
    }
    final color = anySuccess ? const Color(0xFF4CAF50) : Colors.orange;
    return _DiagBox(color: color, lines: lines);
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

  static String _format(List<int> bytes) {
    if (bytes.isEmpty) return '(空)';
    final buf = StringBuffer();
    const cols = 16;
    for (var i = 0; i < bytes.length; i += cols) {
      final end = i + cols > bytes.length ? bytes.length : i + cols;
      final chunk = bytes.sublist(i, end);
      final offset = i.toRadixString(16).padLeft(4, '0').toUpperCase();
      final hex = chunk
          .map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase())
          .join(' ');
      final ascii = chunk
          .map((b) => (b >= 0x20 && b < 0x7F) ? String.fromCharCode(b) : '.')
          .join();
      buf.writeln('$offset  ${hex.padRight(cols * 3 - 1)}  $ascii');
    }
    return buf.toString().trimRight();
  }

  @override
  Widget build(BuildContext context) {
    final hex = bytes
        .map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase())
        .join();
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
          _format(bytes),
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
