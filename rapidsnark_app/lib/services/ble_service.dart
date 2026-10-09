import 'dart:async';
import 'dart:io';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '../core/v2_observer_capture.dart';
import '../domain/uav_telemetry.dart';

/// イベント駆動 BLE スキャンサービス。
/// スキャンは1本に集約し、複数コンシューマーがストリームを共有する。
class BleService {
  final _packetController = StreamController<UavTelemetryPacket>.broadcast();
  final _rawController = StreamController<List<ScanResult>>.broadcast();
  StreamSubscription<BluetoothAdapterState>? _adapterSub;
  StreamSubscription<List<ScanResult>>? _scanSub;
  StreamSubscription<bool>? _isScanningSubscription;
  V2ObserverCaptureRecorder? _v2Capture;
  int _seq = 0;

  /// 解析済み OpenDroneID パケットのストリーム
  Stream<UavTelemetryPacket> get packets => _packetController.stream;

  /// 生の ScanResult ストリーム（BLE Raw タブ等が共有して使う）
  Stream<List<ScanResult>> get rawResults => _rawController.stream;

  bool get isCapturingV2 => _v2Capture != null;
  String? get v2CapturePath => _v2Capture?.path;

  /// Save an owner-private, shared-session-tagged V2 JSONL capture from the
  /// existing scan stream. Only BLE Remote ID Service Data is included.
  Future<String> startV2Capture({
    required Directory privateDirectory,
    required V2ObserverCaptureConfig config,
  }) async {
    if (_v2Capture != null) throw StateError('a V2 capture is already active');
    final recorder = await V2ObserverCaptureRecorder.start(
      advertisements: _v2Advertisements(),
      privateDirectory: privateDirectory,
      config: config,
    );
    _v2Capture = recorder;
    return recorder.path;
  }

  Future<String> stopV2Capture() async {
    final recorder = _v2Capture;
    if (recorder == null) throw StateError('no V2 capture is active');
    try {
      return await recorder.stop();
    } finally {
      if (identical(_v2Capture, recorder)) _v2Capture = null;
    }
  }

  Stream<V2ObserverAdvertisement> _v2Advertisements() async* {
    await for (final results in rawResults) {
      for (final result in results) {
        final payload = UavTelemetryPacket.extractFromServiceData(
          result.advertisementData.serviceData,
        );
        if (payload == null || payload.isEmpty) continue;
        final immutablePayload = List<int>.unmodifiable(payload);
        final eventIdentity =
            '${result.timeStamp.microsecondsSinceEpoch}:${immutablePayload.map((b) => b.toRadixString(16).padLeft(2, '0')).join()}';
        yield V2ObserverAdvertisement(
          advertiserId: result.device.remoteId.str,
          eventIdentity: eventIdentity,
          receivedAt: result.timeStamp,
          rssiDbm: result.rssi,
          payload: immutablePayload,
        );
      }
    }
  }

  void start() {
    _adapterSub = FlutterBluePlus.adapterState.listen((state) {
      if (state == BluetoothAdapterState.on) {
        _startScan();
      } else {
        _v2Capture?.recordAcquisitionFailure(
          source: 'ble_adapter_unavailable',
          error: StateError('BLE adapter unavailable'),
        );
        _stopScan();
      }
    });

    // スキャン終了後、少し間を置いてから再スキャン（レート制限対策）
    _isScanningSubscription = FlutterBluePlus.isScanning.listen((
      scanning,
    ) async {
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
    _scanSub = FlutterBluePlus.scanResults.listen(
      _onScanResults,
      onError: (Object error, StackTrace _) {
        _v2Capture?.recordAcquisitionFailure(
          source: 'ble_scan_results',
          error: error,
        );
      },
      onDone: () {
        _v2Capture?.recordAcquisitionFailure(
          source: 'ble_scan_results',
          error: StateError('scan result stream closed'),
        );
      },
    );
    try {
      // タイムアウトを長くしてstart/stop頻度を下げる
      await FlutterBluePlus.startScan(timeout: const Duration(seconds: 30));
    } catch (error) {
      _v2Capture?.recordAcquisitionFailure(
        source: 'ble_scan_start',
        error: error,
      );
    }
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
    final capture = _v2Capture;
    _v2Capture = null;
    if (capture != null) unawaited(capture.stop());
    _adapterSub?.cancel();
    _isScanningSubscription?.cancel();
    _scanSub?.cancel();
    FlutterBluePlus.stopScan();
    _packetController.close();
    _rawController.close();
  }
}
