import 'dart:async';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/raw_ble_device.dart';
import 'ble_provider.dart';

/// 全BLEスキャン結果（解析可否問わず）を最新50件保持するNotifier。
/// BleService の rawResults ストリームを共有し、自前スキャンは行わない。
class RawBleNotifier extends Notifier<List<RawBleDevice>> {
  StreamSubscription<List<ScanResult>>? _sub;

  @override
  List<RawBleDevice> build() {
    final service = ref.watch(bleServiceProvider);
    ref.onDispose(() => _sub?.cancel());
    _sub = service.rawResults.listen(_onResults);
    return const [];
  }

  void _onResults(List<ScanResult> results) {
    final updated = Map<String, RawBleDevice>.fromEntries(
      state.map((d) => MapEntry(d.deviceId, d)),
    );
    for (final r in results) {
      final device = RawBleDevice.fromScanResult(r);
      updated[device.deviceId] = device;
    }
    final sorted = updated.values.toList()
      ..sort((a, b) => b.rssi.compareTo(a.rssi));
    state = sorted.take(50).toList();
  }

  void clear() => state = const [];
}

final rawBleProvider =
    NotifierProvider.autoDispose<RawBleNotifier, List<RawBleDevice>>(
  RawBleNotifier.new,
);
