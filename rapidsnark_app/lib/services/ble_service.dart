import 'dart:async';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '../domain/uav_telemetry.dart';

/// イベント駆動 BLE スキャンサービス。
/// スキャンは1本に集約し、複数コンシューマーがストリームを共有する。
class BleService {
  final _packetController = StreamController<UavTelemetryPacket>.broadcast();
  final _rawController = StreamController<List<ScanResult>>.broadcast();
  StreamSubscription<BluetoothAdapterState>? _adapterSub;
  StreamSubscription<List<ScanResult>>? _scanSub;
  StreamSubscription<bool>? _isScanningSubscription;
  int _seq = 0;

  /// 解析済み OpenDroneID パケットのストリーム
  Stream<UavTelemetryPacket> get packets => _packetController.stream;

  /// 生の ScanResult ストリーム（BLE Raw タブ等が共有して使う）
  Stream<List<ScanResult>> get rawResults => _rawController.stream;

  void start() {
    _adapterSub = FlutterBluePlus.adapterState.listen((state) {
      if (state == BluetoothAdapterState.on) {
        _startScan();
      } else {
        _stopScan();
      }
    });

    // スキャン終了後、少し間を置いてから再スキャン（レート制限対策）
    _isScanningSubscription = FlutterBluePlus.isScanning.listen((scanning) async {
      if (!scanning) {
        await Future<void>.delayed(const Duration(seconds: 2));
        final adapterState = await FlutterBluePlus.adapterState.first;
        if (adapterState == BluetoothAdapterState.on) {
          _startScan();
        }
      }
    });
  }

  Future<void> _startScan() async {
    if (FlutterBluePlus.isScanningNow) return;
    await _scanSub?.cancel();
    _scanSub = FlutterBluePlus.scanResults.listen(_onScanResults);
    try {
      // タイムアウトを長くしてstart/stop頻度を下げる
      await FlutterBluePlus.startScan(timeout: const Duration(seconds: 30));
    } catch (_) {}
  }

  void _stopScan() {
    FlutterBluePlus.stopScan();
    _scanSub?.cancel();
    _scanSub = null;
  }

  void _onScanResults(List<ScanResult> results) {
    // 生データを全コンシューマーに配信
    if (_rawController.hasListener) _rawController.add(results);

    // OpenDroneID パースして配信
    for (final result in results) {
      final ad = result.advertisementData;
      final odidBytes =
          UavTelemetryPacket.extractFromServiceData(ad.serviceData) ??
          UavTelemetryPacket.extractFromManufacturerData(ad.manufacturerData);
      if (odidBytes == null) continue;

      for (final msg in UavTelemetryPacket.extractAllMessages(odidBytes)) {
        final packet = UavTelemetryPacket.tryParseLocation(msg, _seq++);
        if (packet != null) _packetController.add(packet);
      }
    }
  }

  void dispose() {
    _adapterSub?.cancel();
    _isScanningSubscription?.cancel();
    _scanSub?.cancel();
    FlutterBluePlus.stopScan();
    _packetController.close();
    _rawController.close();
  }
}
