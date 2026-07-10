import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/uav_telemetry.dart';
import '../services/ble_service.dart';

/// BleService の単一インスタンスを管理する Provider。
final bleServiceProvider = Provider<BleService>((ref) {
  final service = BleService();
  service.start();
  ref.onDispose(service.dispose);
  return service;
});

/// 最新20件の BLE パケット履歴を提供する StreamProvider。
final bleHistoryProvider = StreamProvider<List<UavTelemetryPacket>>((ref) {
  final service = ref.watch(bleServiceProvider);
  final history = <UavTelemetryPacket>[];
  return service.packets.map((packet) {
    history.add(packet);
    if (history.length > 20) history.removeAt(0);
    return List.unmodifiable(history);
  });
});

/// 最新の BLE パケット（1件のみ必要な場合）。
final latestDroneTelemetryProvider = Provider<UavTelemetryPacket?>((ref) {
  return ref.watch(bleHistoryProvider).asData?.value.lastOrNull;
});
