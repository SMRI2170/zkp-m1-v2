import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/position_snapshot.dart';
import '../services/sensor_service.dart';

/// SensorService の単一インスタンスを管理する Provider。
final sensorServiceProvider = Provider<SensorService>((ref) {
  final service = SensorService();
  service.start();
  ref.onDispose(service.dispose);
  return service;
});

/// 最新20件の位置スナップショット履歴を提供する StreamProvider。
final locationHistoryProvider = StreamProvider<List<PositionSnapshot>>((ref) {
  final service = ref.watch(sensorServiceProvider);
  final history = <PositionSnapshot>[];
  return service.snapshots.map((snap) {
    history.add(snap);
    if (history.length > 20) history.removeAt(0);
    return List.unmodifiable(history);
  });
});

/// 最新の位置スナップショット（1件のみ必要な場合）。
final latestLocationProvider = Provider<PositionSnapshot?>((ref) {
  return ref.watch(locationHistoryProvider).asData?.value.lastOrNull;
});
