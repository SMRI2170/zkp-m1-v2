import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:google_mlkit_image_labeling/google_mlkit_image_labeling.dart';
import 'package:google_mlkit_object_detection/google_mlkit_object_detection.dart';
import 'package:image/image.dart' as img;
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:video_thumbnail/video_thumbnail.dart' as video_thumbnail;

import '../../core/geo_math.dart';
import '../../detection/uav_yolo_detector.dart';
import '../../domain/position_snapshot.dart';
import '../../domain/safety_circuit.dart';
import '../../domain/uav_telemetry.dart';
import '../../providers/zk_proof_provider.dart';
import '../ble_raw_scan/ble_raw_scan_page.dart';

// ── ローカルモデルクラス（内部使用）──────────────────────────────────────────

class _VideoEvidence {
  const _VideoEvidence({required this.path, required this.recordedAt});
  final String path;
  final DateTime recordedAt;
}

class _SampledVideoFrame {
  const _SampledVideoFrame({required this.path, required this.timeMs});
  final String path;
  final int timeMs;
}

class _VideoDetectionDetail {
  const _VideoDetectionDetail({
    required this.timeMs,
    required this.backend,
    required this.labels,
    this.previewPath,
    this.regions = const [],
  });
  final int timeMs;
  final String backend;
  final List<String> labels;
  final String? previewPath;
  final List<_VideoDetectedRegion> regions;
}

class _VideoDetectedRegion {
  const _VideoDetectedRegion({
    required this.left,
    required this.top,
    required this.right,
    required this.bottom,
    required this.label,
    required this.confidence,
  });
  final double left;
  final double top;
  final double right;
  final double bottom;
  final String label;
  final double confidence;
}

// ── ページ本体 ────────────────────────────────────────────────────────────────

class SafetyProofPage extends ConsumerStatefulWidget {
  const SafetyProofPage({super.key});

  @override
  ConsumerState<SafetyProofPage> createState() => _SafetyProofPageState();
}

class _SafetyProofPageState extends ConsumerState<SafetyProofPage> {
  static const _distanceLimitMeters = 30.0;
  static const _timeLimitSeconds = 5;

  int _selectedTabIndex = 0;
  DroneInputMode _droneInputMode = DroneInputMode.manual;
  SafetyCircuitProfile _selectedCircuitProfile = SafetyCircuitProfile.base;

  final _droneLatController = TextEditingController();
  final _droneLonController = TextEditingController();
  final _droneAltController = TextEditingController();
  final _droneTimeController = TextEditingController();
  final _targetLatController = TextEditingController();
  final _targetLonController = TextEditingController();
  final _targetAltController = TextEditingController();
  final _targetTimeController = TextEditingController();

  String _status = 'ドローン側は手入力または Raspberry Pi BLE 受信、利用者側は端末センサー取得で進められます。';
  final List<String> _logs = [];
  final ScrollController _logScrollController = ScrollController();

  void _log(String msg) {
    final now = DateTime.now();
    final ts = '${now.hour.toString().padLeft(2, '0')}:'
        '${now.minute.toString().padLeft(2, '0')}:'
        '${now.second.toString().padLeft(2, '0')}';
    if (!mounted) return;
    setState(() {
      _status = msg;
      _logs.add('[$ts] $msg');
      if (_logs.length > 200) _logs.removeAt(0);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_logScrollController.hasClients) {
        _logScrollController.jumpTo(_logScrollController.position.maxScrollExtent);
      }
    });
  }

  bool _isBusy = false;
  bool _isScanningDrone = false;
  DateTime? _proofStartedAt;
  Duration? _proofElapsed;
  Timer? _proofTimer;
  bool _uavDetectedInVideo = false;
  double? _groundPressureHpa;
  double? _currentAltitudeMeters;
  Timer? _bleRescanTimer;

  // カメラ
  CameraController? _cameraController;
  bool _cameraReady = false;
  String? _cameraError;
  bool _isCapturing = false;
  bool _isRecording = false;
  DateTime? _recordingStartedAt;
  Duration _recordingElapsed = Duration.zero;
  Timer? _recordingTimer;

  // ライブ検知
  List<UavYoloDetection> _liveDetections = const [];
  Size? _previewSize;
  bool _isLiveDetecting = false;
  bool _isCapturingFrame = false; // takePicture() 飛行中フラグ
  Timer? _liveDetectionTimer;

  // 履歴（最大20件）
  final List<PositionSnapshot> _locationHistory = [];
  final List<UavTelemetryPacket> _droneHistory = [];
  StreamSubscription<Position>? _locationStream;
  StreamSubscription<List<ScanResult>>? _bleScanSubscription;
  int _scanSeq = 0;

  _VideoEvidence? _videoEvidence;
  List<String> _videoDetectionLabels = const [];
  List<_VideoDetectionDetail> _videoDetectionDetails = const [];
  String _videoDetectionSummary = '「撮影して検知」でドローンを撮影すると YOLO で自動解析します。';
  UavYoloDetector? _yoloDetector;
  String _detectionBackendLabel = 'ML Kit fallback';
  String _detectionBackendStatus = 'YOLO モデルがまだ入っていないため、軽量ラベリングで解析します。';
  StreamSubscription<BarometerEvent>? _barometerSubscription;
  UavTelemetryPacket? _lastDroneTelemetry;

  bool get _hasTargetInputsReady =>
      _targetLatController.text.isNotEmpty &&
      _targetLonController.text.isNotEmpty &&
      _targetAltController.text.isNotEmpty &&
      _targetTimeController.text.isNotEmpty;

  SafetyCircuitConfig get _selectedCircuitConfig =>
      SafetyCircuitConfig.all.firstWhere(
        (config) => config.profile == _selectedCircuitProfile,
      );

  @override
  void initState() {
    super.initState();
    _applyDefaultInputs();
    _startBarometerStream();
    _startContinuousBleScan();
    unawaited(_initializeDetectionPipeline());
    // GPS → カメラの順に直列化（同時にパーミッションダイアログが出るのを防ぐ）
    unawaited(_startLocationStream().then((_) => _initCameraAndRecord()));
  }

  Future<void> _initCameraAndRecord() async {
    if (!mounted) return;
    setState(() => _cameraError = null);

    // カメラ・マイクのランタイムパーミッションを要求（直列）
    // RECORD_AUDIO は enableAudio:false でも camera plugin v0.11.x が要求する
    for (final permission in [Permission.camera, Permission.microphone]) {
      final status = await permission.request();
      if (!status.isGranted) {
        final msg = permission == Permission.camera
            ? 'カメラの権限がありません。設定から許可してください。'
            : 'マイクの権限がありません。設定から許可してください。';
        _log(msg);
        if (mounted) setState(() => _cameraError = msg);
        return;
      }
    }

    List<CameraDescription> cameras;
    try {
      cameras = await availableCameras();
    } catch (e) {
      final msg = 'カメラ取得エラー: $e';
      _log(msg);
      if (mounted) setState(() => _cameraError = 'カメラ権限を確認してください');
      return;
    }
    if (cameras.isEmpty) {
      const msg = 'カメラが見つかりません';
      _log(msg);
      if (mounted) setState(() => _cameraError = msg);
      return;
    }

    final controller = CameraController(
      cameras.first,
      ResolutionPreset.medium,
      enableAudio: false,
    );
    try {
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() {
        _cameraController = controller;
        _cameraReady = true;
        _cameraError = null;
        _previewSize = controller.value.previewSize;
      });
      _startLiveDetection();
    } catch (e) {
      await controller.dispose();
      final msg = e.toString().contains('cameraPermission')
          ? 'カメラの権限がありません。設定から許可してください。'
          : 'カメラ初期化エラー: $e';
      _log(msg);
      if (mounted) setState(() => _cameraError = msg);
    }
  }

  // ── ライブ検知 ────────────────────────────────────────────────────────────

  void _startLiveDetection() {
    if (_yoloDetector == null || _isLiveDetecting) return;
    _isLiveDetecting = true;
    _liveDetectionTimer =
        Timer.periodic(const Duration(milliseconds: 800), (_) async {
      if (!mounted || _isRecording || _isCapturing || _isCapturingFrame) return;
      final ctrl = _cameraController;
      if (ctrl == null || !ctrl.value.isInitialized) return;
      _isCapturingFrame = true;
      try {
        final photo = await ctrl.takePicture();
        final detections = await _yoloDetector!.detectImageFile(photo.path);
        await File(photo.path).delete();
        if (mounted) setState(() => _liveDetections = detections);
      } catch (_) {
      } finally {
        _isCapturingFrame = false;
      }
    });
  }

  void _stopLiveDetection() {
    _liveDetectionTimer?.cancel();
    _liveDetectionTimer = null;
    _isLiveDetecting = false;
    if (mounted) setState(() => _liveDetections = const []);
  }

  // ── 録画 ─────────────────────────────────────────────────────────────────

  Future<void> _startVideoRecording() async {
    final ctrl = _cameraController;
    if (ctrl == null || !_cameraReady || _isRecording || _isCapturing || _isBusy) return;
    _stopLiveDetection();
    // takePicture() が飛行中の場合は完了を待つ（最大1秒）
    for (var i = 0; i < 20 && _isCapturingFrame; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    if (!mounted) return;
    try {
      await ctrl.startVideoRecording();
      if (!mounted) return;
      setState(() {
        _isRecording = true;
        _recordingStartedAt = DateTime.now();
        _recordingElapsed = Duration.zero;
      });
      _recordingTimer =
          Timer.periodic(const Duration(milliseconds: 100), (_) {
        if (_recordingStartedAt != null && mounted) {
          setState(() {
            _recordingElapsed = DateTime.now().difference(_recordingStartedAt!);
          });
        }
      });
      _log('録画開始...');
    } catch (e) {
      _log('録画開始エラー: $e');
      _startLiveDetection();
    }
  }

  Future<void> _stopVideoRecordingAndAnalyze() async {
    final ctrl = _cameraController;
    if (ctrl == null || !_isRecording) return;
    _recordingTimer?.cancel();
    _recordingTimer = null;
    setState(() {
      _isRecording = false;
      _isCapturing = true;
    });
    try {
      final videoFile = await ctrl.stopVideoRecording();
      final recordedAt = DateTime.now();
      _selectBestDataPair();
      setState(() {
        _videoEvidence = _VideoEvidence(path: videoFile.path, recordedAt: recordedAt);
        _uavDetectedInVideo = false;
        _videoDetectionLabels = const [];
        _videoDetectionDetails = const [];
        _videoDetectionSummary = '動画を解析しています...';
      });
      _log('録画完了 (${recordedAt.toIso8601String()})。フレームを抽出して YOLO で検知します...');
      await _analyzeVideoEvidence();
    } catch (e) {
      _log('録画停止エラー: $e');
    } finally {
      if (mounted) setState(() => _isCapturing = false);
      _startLiveDetection();
    }
  }

  void _selectBestDataPair() {
    if (_droneHistory.isEmpty || _locationHistory.isEmpty) return;
    UavTelemetryPacket? bestDrone;
    PositionSnapshot? bestLocation;
    int minDiff = 999999;
    for (final drone in _droneHistory) {
      for (final loc in _locationHistory) {
        final diff = (drone.unixTimeSec - loc.unixTimeSec).abs();
        if (diff < minDiff) {
          minDiff = diff;
          bestDrone = drone;
          bestLocation = loc;
        }
      }
    }
    if (bestDrone != null) _applyDroneTelemetry(bestDrone);
    if (bestLocation != null && mounted) {
      setState(() {
        _targetLatController.text = bestLocation!.lat.toStringAsFixed(7);
        _targetLonController.text = bestLocation.lon.toStringAsFixed(7);
        _targetAltController.text = bestLocation.alt.toStringAsFixed(1);
        _targetTimeController.text = bestLocation.unixTimeSec.toString();
      });
      _log('撮影時点スナップショット: ドローン ${_droneHistory.length}件・位置 ${_locationHistory.length}件 → 最適ペア選択（時刻差 ${minDiff}s）。');
    }
  }

  // ── センサー ──────────────────────────────────────────────────────────────

  Future<void> _startLocationStream() async {
    _locationStream?.cancel();

    // パーミッション確認・要求
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      _log('位置情報サービスが無効です。端末の設定で有効にしてください。');
      return;
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      _log('位置情報の権限がありません。設定から許可してください。');
      return;
    }

    _locationStream = Geolocator.getPositionStream(
      locationSettings: Platform.isAndroid
          ? AndroidSettings(
              accuracy: LocationAccuracy.best,
              distanceFilter: 0,
              intervalDuration: const Duration(seconds: 1),
            )
          : const LocationSettings(
              accuracy: LocationAccuracy.best,
              distanceFilter: 0,
            ),
    ).listen(
      (position) {
        final alt = _currentAltitudeMeters ?? 0.0;
        final unixSec = DateTime.now().millisecondsSinceEpoch ~/ 1000;
        final snapshot = PositionSnapshot(
          lat: position.latitude,
          lon: position.longitude,
          alt: alt,
          unixTimeSec: unixSec,
        );
        if (!mounted) return;
        setState(() {
          _locationHistory.add(snapshot);
          if (_locationHistory.length > 20) _locationHistory.removeAt(0);
          _targetLatController.text = position.latitude.toStringAsFixed(7);
          _targetLonController.text = position.longitude.toStringAsFixed(7);
          _targetAltController.text = alt.toStringAsFixed(1);
          _targetTimeController.text = unixSec.toString();
        });
      },
      onError: (e) => _log('GPS エラー: $e'),
    );
  }

  void _startContinuousBleScan() {
    unawaited(_restartBleScan());
    _bleRescanTimer?.cancel();
    _bleRescanTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!FlutterBluePlus.isScanningNow && !_isScanningDrone && !_isBusy) {
        unawaited(_restartBleScan());
      }
    });
  }

  Future<void> _restartBleScan() async {
    if (_isScanningDrone) return;
    if (mounted) setState(() => _isScanningDrone = true);
    try {
      final adapterState = await FlutterBluePlus.adapterState.first;
      if (adapterState != BluetoothAdapterState.on) {
        _log('Bluetooth がオフです。オンにしてください。');
        return;
      }

      await FlutterBluePlus.stopScan();
      await _bleScanSubscription?.cancel();

      _bleScanSubscription = FlutterBluePlus.scanResults.listen((results) {
        for (final result in results) {
          final ad = result.advertisementData;
          final odidBytes =
              UavTelemetryPacket.extractFromServiceData(ad.serviceData) ??
              UavTelemetryPacket.extractFromManufacturerData(ad.manufacturerData);
          if (odidBytes == null) continue;

          final messages = UavTelemetryPacket.extractAllMessages(odidBytes);
          for (final msg in messages) {
            final msgType = msg.isNotEmpty ? (msg[0] >> 4) & 0x0F : -1;

            if (msgType == 0) {
              final uasId = UavTelemetryPacket.tryParseUasId(msg);
              if (uasId != null && uasId.isNotEmpty) {
                _log('[BLE BasicID] UAS_ID=$uasId rssi=${result.rssi}dBm');
              }
              continue;
            }

            if (msgType == 1) {
              final packet =
                  UavTelemetryPacket.tryParseLocation(msg, _scanSeq++);
              if (packet != null && mounted) {
                _log('[BLE Location] seq=${packet.sequence} '
                    'lat=${packet.latitude.toStringAsFixed(6)} '
                    'lon=${packet.longitude.toStringAsFixed(6)} '
                    'alt=${packet.altitudeMeters.toStringAsFixed(1)}m '
                    'airborne=${packet.statusIsAirborne} '
                    'rssi=${result.rssi}dBm');
                setState(() => _applyDroneTelemetry(packet));
              }
              continue;
            }

            if (msgType == 4) {
              final sys = UavTelemetryPacket.tryParseSystem(msg);
              if (sys != null) {
                _log('[BLE System] $sys rssi=${result.rssi}dBm');
              }
              continue;
            }

            _log('[BLE type=$msgType] ${msg.length}B (未パース) rssi=${result.rssi}dBm');
          }
        }
      });

      await FlutterBluePlus.startScan(timeout: const Duration(seconds: 20));
    } catch (e) {
      _log('BLE スキャンエラー: $e');
    } finally {
      if (mounted) setState(() => _isScanningDrone = false);
    }
  }

  Future<void> _initializeDetectionPipeline() async {
    try {
      final detector = await UavYoloDetector.tryCreateFromCandidates([
        UavYoloDetector.visdroneFinetunedConfigAsset,
        UavYoloDetector.roboflowDroneConfigAsset,
        UavYoloDetector.defaultConfigAsset,
      ]);
      if (!mounted) {
        detector?.dispose();
        return;
      }
      setState(() {
        _yoloDetector = detector;
        if (detector != null) {
          _detectionBackendLabel = 'YOLO TFLite';
          _detectionBackendStatus = detector.description
                  .contains('uav_visdrone_finetuned')
              ? 'VisDrone 事前学習後に UAV へ fine-tune したプロファイルを優先して読み込みました。'
              : detector.description.contains('uav_roboflow_drone')
                  ? 'Roboflow の UAV 専用プロファイルを優先して読み込みました。'
                  : 'YOLO モデルを読み込みました。';
        } else {
          _detectionBackendLabel = 'ML Kit fallback';
          _detectionBackendStatus = 'YOLO モデルが無効または未配置のため、軽量ラベリングを利用します。';
        }
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _yoloDetector = null;
        _detectionBackendLabel = 'ML Kit fallback';
        _detectionBackendStatus = 'YOLO 初期化に失敗したため、軽量ラベリングへフォールバックします。error=$error';
      });
    }
  }

  void _applyDefaultInputs() {
    _droneLatController.clear();
    _droneLonController.clear();
    _droneAltController.clear();
    _droneTimeController.clear();
    _targetLatController.clear();
    _targetLonController.clear();
    _targetAltController.clear();
    _targetTimeController.clear();
    _droneInputMode = DroneInputMode.manual;
    _selectedCircuitProfile = SafetyCircuitProfile.base;
    _lastDroneTelemetry = null;
    _log('ドローン側は手入力または Raspberry Pi BLE 受信、利用者側は端末の GPS と気圧センサーで取得できます。');
  }

  bool _hasDroneManualInputs() {
    final lat = _tryParseDouble(_droneLatController.text);
    final lon = _tryParseDouble(_droneLonController.text);
    final alt = _tryParseDouble(_droneAltController.text);
    final time = _tryParseInt(_droneTimeController.text);
    return lat != null &&
        lon != null &&
        alt != null &&
        time != null &&
        lat >= -90 &&
        lat <= 90 &&
        lon >= -180 &&
        lon <= 180 &&
        alt.isFinite &&
        time >= 0;
  }

  bool _hasDroneInputsReady() {
    if (_droneInputMode == DroneInputMode.ble) {
      return _lastDroneTelemetry != null;
    }
    return _hasDroneManualInputs();
  }

  double? _tryParseDouble(String value) {
    try {
      return double.parse(value);
    } catch (_) {
      return null;
    }
  }

  int? _tryParseInt(String value) {
    try {
      return int.parse(value);
    } catch (_) {
      return null;
    }
  }

  double _approxDistanceMeters() {
    final droneLat = _tryParseDouble(_droneLatController.text);
    final droneLon = _tryParseDouble(_droneLonController.text);
    final droneAlt = _tryParseDouble(_droneAltController.text);
    final targetLat = _tryParseDouble(_targetLatController.text);
    final targetLon = _tryParseDouble(_targetLonController.text);
    final targetAlt = _tryParseDouble(_targetAltController.text);

    if (droneLat == null ||
        droneLon == null ||
        droneAlt == null ||
        targetLat == null ||
        targetLon == null ||
        targetAlt == null) {
      return 0;
    }

    return approxDistanceMeters(
      droneLat: droneLat,
      droneLon: droneLon,
      droneAlt: droneAlt,
      targetLat: targetLat,
      targetLon: targetLon,
      targetAlt: targetAlt,
    );
  }

  int _approxTimeDelta() {
    final targetTime = _tryParseInt(_targetTimeController.text);
    final droneTime = _tryParseInt(_droneTimeController.text);
    if (targetTime == null || droneTime == null) return 0;
    return (targetTime - droneTime).abs();
  }

  void _applyDroneTelemetry(UavTelemetryPacket packet) {
    _droneLatController.text = packet.latitude.toStringAsFixed(7);
    _droneLonController.text = packet.longitude.toStringAsFixed(7);
    _droneAltController.text = packet.altitudeMeters.toStringAsFixed(1);
    _droneTimeController.text = packet.unixTimeSec.toString();
    _lastDroneTelemetry = packet;
    _droneHistory.add(packet);
    if (_droneHistory.length > 20) _droneHistory.removeAt(0);
  }

  double _baroToRelativeAlt(double pressureHpa) {
    final p0 = _groundPressureHpa;
    if (p0 == null || p0 <= 0) return 0.0;
    return 44330.0 * (1.0 - math.pow(pressureHpa / p0, 1.0 / 5.255));
  }

  void _startBarometerStream() {
    _barometerSubscription = barometerEventStream().listen(
      (BarometerEvent event) {
        if (!mounted) return;
        _groundPressureHpa ??= event.pressure;
        final altitude = _baroToRelativeAlt(event.pressure);
        setState(() => _currentAltitudeMeters = altitude);
      },
      onError: (_) {
        if (!mounted) return;
        setState(() => _currentAltitudeMeters = null);
      },
    );
  }

  void _startProofTimer() {
    _proofStartedAt = DateTime.now();
    _proofElapsed = Duration.zero;
    _proofTimer?.cancel();
    _proofTimer = Timer.periodic(const Duration(milliseconds: 200), (_) {
      if (_proofStartedAt != null) {
        setState(() {
          _proofElapsed = DateTime.now().difference(_proofStartedAt!);
        });
      }
    });
  }

  void _stopProofTimer() {
    _proofTimer?.cancel();
    _proofTimer = null;
    if (_proofStartedAt != null) {
      _proofElapsed = DateTime.now().difference(_proofStartedAt!);
    }
  }

  String get _elapsedLabel {
    final d = _proofElapsed;
    if (d == null) return '';
    final s = d.inMilliseconds / 1000.0;
    return s >= 60
        ? '${d.inMinutes}m ${d.inSeconds % 60}s'
        : '${s.toStringAsFixed(1)}s';
  }

  Future<void> _runProofFromVideoEvidence() async {
    if (!_hasDroneInputsReady()) {
      _log(_droneInputMode == DroneInputMode.ble
          ? '証明前に Raspberry Pi からドローン側ログを受信してください。'
          : '証明前にドローン側ログを手入力してください。');
      return;
    }
    if (_videoEvidence == null) {
      _log('先に動画を録画してください。');
      return;
    }
    await _runProofFlow();
  }

  Future<void> _runProofFlow() async {
    FocusScope.of(context).unfocus();
    _startProofTimer();
    setState(() {
      _isBusy = true;
    });
    _log('ドローン入力値と端末取得ログをもとに証明条件を準備しています...');

    try {
      final drone = _lastDroneTelemetry ??
          UavTelemetryPacket(
            latitude: _tryParseDouble(_droneLatController.text) ?? 0,
            longitude: _tryParseDouble(_droneLonController.text) ?? 0,
            altitudeMeters: _tryParseDouble(_droneAltController.text) ?? 0,
            altitudeGeoMeters: _tryParseDouble(_droneAltController.text) ?? 0,
            speedH: 0,
            speedV: 0,
            direction: 0,
            statusIsAirborne: false,
            unixTimeSec: _tryParseInt(_droneTimeController.text) ?? 0,
            sequence: 0,
          );

      final target = PositionSnapshot(
        lat: _tryParseDouble(_targetLatController.text) ?? 0,
        lon: _tryParseDouble(_targetLonController.text) ?? 0,
        alt: _tryParseDouble(_targetAltController.text) ?? 0,
        unixTimeSec: _tryParseInt(_targetTimeController.text) ?? 0,
      );

      await ref.read(zkProofProvider.notifier).run(
            profile: _selectedCircuitProfile,
            drone: drone,
            target: target,
            uavDetected: _uavDetectedInVideo,
            droneHistory: _droneHistory,
            locationHistory: _locationHistory,
            videoPath: _videoEvidence?.path,
            videoRecordedAt: _videoEvidence?.recordedAt,
            detectionBackendLabel: _detectionBackendLabel,
            videoDetectionDetails: _videoDetectionDetails
                .expand((d) => d.regions)
                .map((r) => {'score': r.confidence, 'label': r.label})
                .toList(),
          );

      final proofState = ref.read(zkProofProvider);
      _stopProofTimer();
      setState(() => _isBusy = false);
      _log(proofState.proofValid
          ? '✓ 証明・検証 完了（$_elapsedLabel）'
          : '✗ 証明は生成できましたが検証に失敗しました（$_elapsedLabel）');
    } catch (error) {
      _stopProofTimer();
      setState(() => _isBusy = false);
      _log('✗ エラー（$_elapsedLabel）: $error');
    }
  }

  Future<void> _analyzeVideoEvidence() async {
    final evidence = _videoEvidence;
    if (evidence == null) {
      _log('動画がまだありません。先に録画してください。');
      return;
    }
    setState(() => _videoDetectionSummary = '動画フレームの UAV 候補を解析しています...');

    List<_SampledVideoFrame> frames = const [];
    List<_VideoDetectionDetail> details = const [];
    try {
      frames = await _extractVideoFrames(evidence.path);
      _log('フレーム抽出: ${frames.length}枚');

      if (_yoloDetector != null) {
        details = await _analyzeFramesWithYolo(frames);
      } else {
        details = await _analyzeFramesWithMlKit(frames);
      }

      var detected = false;
      final labels = <String>{};
      for (final detail in details) {
        for (final label in detail.labels) {
          labels.add(label);
          if (_looksLikeUavLabel(label.split(':').first.toLowerCase())) {
            detected = true;
          }
        }
        for (final region in detail.regions) {
          labels.add('${region.label}:${region.confidence.toStringAsFixed(2)}');
          if (_looksLikeUavLabel(region.label.toLowerCase())) detected = true;
        }
      }

      setState(() {
        _uavDetectedInVideo = detected;
        _videoDetectionLabels = labels.toList()..sort();
        _videoDetectionDetails = details;
        _videoDetectionSummary = detected
            ? '$_detectionBackendLabel により動画内の UAV 候補を検知しました。証明に進めます。'
            : '$_detectionBackendLabel では UAV 候補を確実には検知できませんでした。別角度で再録画すると精度が上がる場合があります。';
      });
      _log(detected ? '動画解析で UAV 候補を検知しました。' : '動画解析では UAV 候補を検知できませんでした。');
    } catch (error) {
      setState(() {
        _uavDetectedInVideo = false;
        _videoDetectionDetails = const [];
        _videoDetectionSummary = '動画解析エラー: $error';
      });
      _log('動画解析エラー: $error');
    } finally {
      // サムネイル・プレビューの一時ファイルを削除
      Future<void> tryDelete(String path) async {
        try { await File(path).delete(); } catch (_) {}
      }
      for (final frame in frames) {
        await tryDelete(frame.path);
      }
      for (final detail in details) {
        if (detail.previewPath != null) await tryDelete(detail.previewPath!);
      }
    }
  }

  Future<List<_SampledVideoFrame>> _extractVideoFrames(String videoPath) async {
    final tempDir = await getTemporaryDirectory();
    final frames = <_SampledVideoFrame>[];
    for (final positionMs in [0, 1000, 2500]) {
      final thumbnailPath = await video_thumbnail.VideoThumbnail.thumbnailFile(
        video: videoPath,
        thumbnailPath: tempDir.path,
        imageFormat: video_thumbnail.ImageFormat.JPEG,
        timeMs: positionMs,
        quality: 85,
      );
      if (thumbnailPath != null) {
        frames.add(_SampledVideoFrame(path: thumbnailPath, timeMs: positionMs));
      }
    }
    return frames;
  }

  Future<List<_VideoDetectionDetail>> _analyzeFramesWithMlKit(
    List<_SampledVideoFrame> frames,
  ) async {
    final details = <_VideoDetectionDetail>[];
    final labeler = ImageLabeler(
      options: ImageLabelerOptions(confidenceThreshold: 0.45),
    );
    final objectDetector = ObjectDetector(
      options: ObjectDetectorOptions(
        mode: DetectionMode.single,
        classifyObjects: true,
        multipleObjects: true,
      ),
    );

    try {
      for (final frame in frames) {
        final inputImage = InputImage.fromFilePath(frame.path);
        final imageLabels = await labeler.processImage(inputImage);
        final objects = await objectDetector.processImage(inputImage);
        final regions = await _buildMlKitRegions(
          frame: frame,
          objects: objects,
          labeler: labeler,
        );
        final previewPath = await _buildMlKitPreview(
          frame: frame,
          regions: regions,
        );
        final labels = imageLabels
            .map((label) =>
                '${label.label}:${label.confidence.toStringAsFixed(2)}')
            .toList();
        details.add(_VideoDetectionDetail(
          timeMs: frame.timeMs,
          backend: 'ML Kit',
          labels: labels,
          previewPath: previewPath,
          regions: regions,
        ));
      }
    } finally {
      await labeler.close();
      await objectDetector.close();
    }
    return details;
  }

  Future<List<_VideoDetectedRegion>> _buildMlKitRegions({
    required _SampledVideoFrame frame,
    required List<DetectedObject> objects,
    required ImageLabeler labeler,
  }) async {
    final bytes = await File(frame.path).readAsBytes();
    final decoded = img.decodeImage(bytes);
    if (decoded == null) return const [];

    final tempDir = await getTemporaryDirectory();
    final regions = <_VideoDetectedRegion>[];

    for (var index = 0; index < objects.length; index++) {
      final rect = objects[index].boundingBox;
      final left = rect.left.clamp(0, decoded.width - 1).toInt();
      final top = rect.top.clamp(0, decoded.height - 1).toInt();
      final right = rect.right.clamp(left + 1, decoded.width.toDouble()).toInt();
      final bottom = rect.bottom.clamp(top + 1, decoded.height.toDouble()).toInt();
      final width = right - left;
      final height = bottom - top;
      if (width < 8 || height < 8) continue;

      final crop = img.copyCrop(decoded, x: left, y: top, width: width, height: height);
      final cropPath = '${tempDir.path}/mlkit_crop_${frame.timeMs}_$index.jpg';
      await File(cropPath).writeAsBytes(img.encodeJpg(crop, quality: 90));

      final cropLabels = await labeler.processImage(InputImage.fromFilePath(cropPath));
      await File(cropPath).delete().catchError((_) => File(cropPath));
      final cropTop = cropLabels.isNotEmpty ? cropLabels.first : null;
      final detectorTop =
          objects[index].labels.isNotEmpty ? objects[index].labels.first : null;
      final regionLabel = cropTop?.label ?? detectorTop?.text ?? 'object';
      final regionConfidence = cropTop?.confidence ?? detectorTop?.confidence ?? 0.0;

      regions.add(_VideoDetectedRegion(
        left: left.toDouble(),
        top: top.toDouble(),
        right: right.toDouble(),
        bottom: bottom.toDouble(),
        label: regionLabel,
        confidence: regionConfidence,
      ));
    }
    return regions;
  }

  Future<String?> _buildMlKitPreview({
    required _SampledVideoFrame frame,
    required List<_VideoDetectedRegion> regions,
  }) async {
    if (regions.isEmpty) return null;
    final bytes = await File(frame.path).readAsBytes();
    final decoded = img.decodeImage(bytes);
    if (decoded == null) return null;
    for (final region in regions) {
      img.drawRect(
        decoded,
        x1: region.left.toInt(),
        y1: region.top.toInt(),
        x2: region.right.toInt(),
        y2: region.bottom.toInt(),
        color: img.ColorRgb8(17, 142, 104),
        thickness: 4,
      );
    }
    final tempDir = await getTemporaryDirectory();
    final previewPath = '${tempDir.path}/mlkit_preview_${frame.timeMs}.jpg';
    await File(previewPath).writeAsBytes(img.encodeJpg(decoded, quality: 92));
    return previewPath;
  }

  Future<List<_VideoDetectionDetail>> _analyzeFramesWithYolo(
    List<_SampledVideoFrame> frames,
  ) async {
    final detector = _yoloDetector;
    if (detector == null) return const [];
    final tempDir = await getTemporaryDirectory();
    final details = <_VideoDetectionDetail>[];

    for (final frame in frames) {
      final detections = await detector.detectImageFile(frame.path);
      final regions = detections
          .map((d) => _VideoDetectedRegion(
                left: d.left,
                top: d.top,
                right: d.right,
                bottom: d.bottom,
                label: d.label,
                confidence: d.score,
              ))
          .toList();

      String? previewPath;
      if (regions.isNotEmpty) {
        try {
          final bytes = await File(frame.path).readAsBytes();
          final decoded = img.decodeImage(bytes);
          if (decoded != null) {
            for (final r in regions) {
              img.drawRect(decoded,
                  x1: r.left.toInt(),
                  y1: r.top.toInt(),
                  x2: r.right.toInt(),
                  y2: r.bottom.toInt(),
                  color: img.ColorRgb8(48, 209, 88),
                  thickness: 4);
              img.fillRect(decoded,
                  x1: r.left.toInt(),
                  y1: (r.top - 22).toInt().clamp(0, decoded.height),
                  x2: (r.left + 140).toInt().clamp(0, decoded.width),
                  y2: r.top.toInt().clamp(0, decoded.height),
                  color: img.ColorRgb8(0, 0, 0));
              img.drawString(decoded,
                  '${r.label} ${(r.confidence * 100).toStringAsFixed(0)}%',
                  font: img.arial14,
                  x: r.left.toInt() + 4,
                  y: (r.top - 18).toInt().clamp(0, decoded.height),
                  color: img.ColorRgb8(48, 209, 88));
            }
            previewPath = '${tempDir.path}/yolo_preview_${frame.timeMs}.jpg';
            await File(previewPath).writeAsBytes(img.encodeJpg(decoded, quality: 92));
          }
        } catch (_) {}
      }

      details.add(_VideoDetectionDetail(
        timeMs: frame.timeMs,
        backend: 'YOLO TFLite',
        labels: detections
            .map((d) => '${d.label}:${d.score.toStringAsFixed(2)}')
            .toList(),
        previewPath: previewPath,
        regions: regions,
      ));
    }
    return details;
  }

  bool _looksLikeUavLabel(String label) {
    const keywords = <String>[
      'drone',
      'quadcopter',
      'multirotor',
      'uav',
      'unmanned aerial vehicle',
      'airplane',
      'helicopter',
    ];
    return keywords.any(label.contains);
  }

  // ── UI ───────────────────────────────────────────────────────────────────

  BoxDecoration _surfaceDecoration({
    Color color = Colors.white,
    double radius = 22,
    Color borderColor = const Color(0xFFE4E0D3),
  }) {
    return BoxDecoration(
      color: color,
      borderRadius: BorderRadius.circular(radius),
      border: Border.all(color: borderColor),
      boxShadow: const [
        BoxShadow(
          color: Color(0x140E201D),
          blurRadius: 24,
          offset: Offset(0, 10),
        ),
      ],
    );
  }

  Widget _buildResultPanel({required String title, required String body}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: _surfaceDecoration(radius: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontWeight: FontWeight.w700,
              color: Color(0xFF2E3F3C),
            ),
          ),
          const SizedBox(height: 8),
          SelectableText(
            body.isEmpty ? '$title は証明実行後に表示されます。' : body,
            style: const TextStyle(
              fontFamily: 'monospace',
              fontSize: 12,
              color: Color(0xFF334643),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStepDot(
      bool done, bool active, IconData icon, String label) {
    final color = done
        ? const Color(0xFF30D158)
        : (active ? Colors.white : Colors.white30);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: done
                ? const Color(0xFF30D158).withValues(alpha: 0.25)
                : (active
                    ? Colors.white.withValues(alpha: 0.15)
                    : Colors.transparent),
            border: Border.all(color: color, width: done ? 0 : 1.5),
          ),
          child: Icon(
            done ? Icons.check_rounded : icon,
            size: 14,
            color: color,
          ),
        ),
        const SizedBox(height: 3),
        Text(label,
            style: TextStyle(
                color: color, fontSize: 10, fontWeight: FontWeight.w600)),
      ],
    );
  }

  Widget _buildStepLine(bool filled) {
    return Expanded(
      child: Container(
        height: 1.5,
        margin: const EdgeInsets.only(bottom: 14),
        color: filled
            ? const Color(0xFF30D158).withValues(alpha: 0.6)
            : Colors.white12,
      ),
    );
  }

  Widget _buildOverlayDataCard({
    required IconData icon,
    required String label,
    required bool ready,
    required String line1,
    required String line2,
    required int count,
  }) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: ready
              ? const Color(0xFF30D158).withValues(alpha: 0.6)
              : Colors.white24,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon,
                  size: 14,
                  color: ready ? const Color(0xFF30D158) : Colors.white54),
              const SizedBox(width: 4),
              Text(
                label,
                style: TextStyle(
                  color: ready ? const Color(0xFF30D158) : Colors.white54,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (count > 0) ...[
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                  decoration: BoxDecoration(
                    color: Colors.white12,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '$count件',
                    style: const TextStyle(color: Colors.white54, fontSize: 10),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 4),
          Text(line1,
              style: const TextStyle(
                color: Colors.white,
                fontFamily: 'monospace',
                fontSize: 13,
                fontWeight: FontWeight.w700,
              )),
          Text(line2,
              style: const TextStyle(
                color: Colors.white70,
                fontFamily: 'monospace',
                fontSize: 11,
              )),
        ],
      ),
    );
  }

  Widget _buildMetricChip(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label,
              style: TextStyle(
                  color: color, fontSize: 11, fontWeight: FontWeight.w600)),
          const SizedBox(width: 6),
          Text(value,
              style: TextStyle(
                  color: color, fontSize: 14, fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }

  Widget _buildMainTab(double approxDistance, int approxTimeDelta) {
    final droneReady = _hasDroneInputsReady();
    final locationReady = _hasTargetInputsReady;
    final videoReady = _videoEvidence != null;
    final zkState = ref.watch(zkProofProvider);
    final provenOnce = zkState.verdictTitle != '未実行';
    final canProve = droneReady && locationReady && !_isBusy;

    final drone = _lastDroneTelemetry;
    final topPad = MediaQuery.of(context).padding.top;
    final bottomPad = MediaQuery.of(context).padding.bottom;

    // 各ドットは独立したboolで制御する（GPS取得済みなら即緑に）
    final bleActive  = !droneReady;
    final gpsActive  = droneReady && !locationReady;
    final recActive  = droneReady && locationReady && !videoReady && !provenOnce;
    final zkActive   = videoReady && !provenOnce;

    final String nextHint;
    if (_isBusy) {
      nextHint = 'ZK 証明を生成しています... $_elapsedLabel';
    } else if (_isCapturing) {
      nextHint = 'YOLO でフレームを解析しています...';
    } else if (_isRecording) {
      final secs = _recordingElapsed.inSeconds;
      nextHint = '録画中 ${secs}s — ドローンを画角に捉えたら停止してください';
    } else if (!droneReady) {
      nextHint = _droneInputMode == DroneInputMode.ble
          ? '① BLE でドローンの Remote ID を受信してください'
          : '① 詳細タブでドローンの座標を手入力してください';
    } else if (!locationReady) {
      nextHint = '② GPS で自分の位置を取得しています...';
    } else if (!videoReady) {
      nextHint = '③ 録画ボタンでドローンを動画に収めてください';
    } else if (provenOnce) {
      nextHint = '証明完了。再録画または再証明できます。';
    } else {
      nextHint = '④ ZK 証明を実行して接近を証明します';
    }

    return Stack(
      children: [
        Positioned.fill(
          child: _cameraReady && _cameraController != null
              ? LayoutBuilder(builder: (context, constraints) {
                  return CustomPaint(
                    foregroundPainter: _liveDetections.isNotEmpty && _previewSize != null
                        ? _BboxPainter(
                            detections: _liveDetections,
                            previewSize: _previewSize!,
                            screenSize: Size(
                                constraints.maxWidth, constraints.maxHeight),
                          )
                        : null,
                    child: CameraPreview(_cameraController!),
                  );
                })
              : const ColoredBox(
                  color: Color(0xFF0A0F0D),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.camera_alt_rounded,
                            color: Color(0xFF4E6762), size: 52),
                        SizedBox(height: 12),
                        Text('カメラを初期化中...',
                            style: TextStyle(color: Color(0xFF4E6762))),
                      ],
                    ),
                  ),
                ),
        ),

        // 上部: ステップバー
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          child: Container(
            padding: EdgeInsets.fromLTRB(16, topPad + 10, 16, 14),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.7),
                  Colors.transparent,
                ],
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'UAV Safety ZK',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 17,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.3,
                  ),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    _buildStepDot(droneReady, bleActive, Icons.bluetooth_rounded, 'BLE'),
                    _buildStepLine(droneReady),
                    _buildStepDot(locationReady, gpsActive, Icons.gps_fixed_rounded, 'GPS'),
                    _buildStepLine(droneReady && locationReady),
                    _buildStepDot(videoReady || provenOnce, recActive, Icons.videocam_rounded, '録画'),
                    _buildStepLine(videoReady || provenOnce),
                    _buildStepDot(provenOnce, zkActive, Icons.verified_rounded, '証明'),
                  ],
                ),
              ],
            ),
          ),
        ),

        if (_isRecording || _isCapturing)
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: LinearProgressIndicator(
              value: null,
              backgroundColor: Colors.white24,
              color: _isRecording ? const Color(0xFFFF3B30) : const Color(0xFFFF9500),
              minHeight: 3,
            ),
          ),

        // 下部オーバーレイ
        Positioned(
          bottom: 0,
          left: 0,
          right: 0,
          child: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.bottomCenter,
                end: Alignment.topCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.9),
                  Colors.black.withValues(alpha: 0.55),
                  Colors.transparent,
                ],
              ),
            ),
            padding: EdgeInsets.fromLTRB(16, 20, 16, bottomPad + 82),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // データカード行
                Row(
                  children: [
                    Expanded(
                      child: _buildOverlayDataCard(
                        icon: Icons.airplanemode_active_rounded,
                        label: 'ドローン',
                        ready: droneReady,
                        line1: drone != null
                            ? '${drone.latitude.toStringAsFixed(4)}°'
                            : '未受信',
                        line2: drone != null
                            ? '${drone.longitude.toStringAsFixed(4)}°  ${drone.altitudeMeters.toStringAsFixed(0)}m'
                            : 'BLE スキャン中...',
                        count: _droneHistory.length,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _buildOverlayDataCard(
                        icon: Icons.person_pin_circle_rounded,
                        label: 'あなた',
                        ready: locationReady,
                        line1: locationReady
                            ? '${double.tryParse(_targetLatController.text)?.toStringAsFixed(4) ?? '--'}°'
                            : '取得中...',
                        line2: locationReady
                            ? '${double.tryParse(_targetLonController.text)?.toStringAsFixed(4) ?? '--'}°  ${_targetAltController.text}m'
                            : 'GPS 待機中...',
                        count: _locationHistory.length,
                      ),
                    ),
                  ],
                ),

                if (droneReady && locationReady) ...[
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _buildMetricChip(
                        '推定距離',
                        '${approxDistance.toStringAsFixed(1)}m',
                        approxDistance <= _distanceLimitMeters
                            ? const Color(0xFF30D158)
                            : const Color(0xFFFF9500),
                      ),
                      const SizedBox(width: 10),
                      _buildMetricChip(
                        '時刻差',
                        '${approxTimeDelta}s',
                        approxTimeDelta <= _timeLimitSeconds
                            ? const Color(0xFF30D158)
                            : const Color(0xFFFF9500),
                      ),
                    ],
                  ),
                ],

                const SizedBox(height: 12),

                Container(
                  width: double.infinity,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    nextHint,
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                    textAlign: TextAlign.center,
                  ),
                ),

                const SizedBox(height: 12),

                // デモ用スキップボタン
                if (!droneReady && !_isBusy) ...[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      OutlinedButton.icon(
                        onPressed: () {
                          final nowSeconds =
                              DateTime.now().millisecondsSinceEpoch ~/ 1000;
                          setState(() {
                            double baseLat =
                                _tryParseDouble(_targetLatController.text) ??
                                    35.6895;
                            double baseLon =
                                _tryParseDouble(_targetLonController.text) ??
                                    139.6917;
                            double baseAlt =
                                _tryParseDouble(_targetAltController.text) ??
                                    0.0;

                            if (_targetLatController.text.isEmpty) {
                              _targetLatController.text =
                                  baseLat.toStringAsFixed(6);
                              _targetLonController.text =
                                  baseLon.toStringAsFixed(6);
                              _targetAltController.text =
                                  baseAlt.toStringAsFixed(1);
                              _targetTimeController.text =
                                  nowSeconds.toString();
                              _locationHistory.add(PositionSnapshot(
                                lat: baseLat,
                                lon: baseLon,
                                alt: baseAlt,
                                unixTimeSec: nowSeconds,
                              ));
                            }

                            _lastDroneTelemetry = UavTelemetryPacket(
                              sequence: 999,
                              latitude: baseLat + 0.0001,
                              longitude: baseLon + 0.0001,
                              altitudeMeters: baseAlt + 20.0,
                              altitudeGeoMeters: baseAlt + 20.0,
                              speedH: 0.0,
                              speedV: 0.0,
                              direction: 0.0,
                              statusIsAirborne: true,
                              unixTimeSec: nowSeconds,
                              uasId: 'DEMO-DRONE-001',
                            );
                            _droneLatController.text =
                                (baseLat + 0.0001).toStringAsFixed(6);
                            _droneLonController.text =
                                (baseLon + 0.0001).toStringAsFixed(6);
                            _droneAltController.text =
                                (baseAlt + 20.0).toStringAsFixed(1);
                            _droneTimeController.text = nowSeconds.toString();
                            _droneHistory.add(_lastDroneTelemetry!);
                          });
                        },
                        icon: const Icon(Icons.fast_forward_rounded, size: 16),
                        label: const Text('デモ用：BLEスキップ'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.amberAccent,
                          side: const BorderSide(color: Colors.amberAccent),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 8),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(16)),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                ],

                // ライブ検知バッジ
                if (_liveDetections.isNotEmpty &&
                    !_isRecording &&
                    !_isCapturing) ...[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0xFF30D158).withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                              color: const Color(0xFF30D158)
                                  .withValues(alpha: 0.6)),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.airplanemode_active_rounded,
                                color: Color(0xFF30D158), size: 13),
                            SizedBox(width: 4),
                            Text(
                              'UAV をプレビューで検知中',
                              style: TextStyle(
                                color: Color(0xFF30D158),
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                ],

                // 録画コントロール
                if (_isCapturing) ...[
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    decoration: BoxDecoration(
                      color: Colors.black54,
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Color(0xFFFF9500)),
                        ),
                        SizedBox(width: 10),
                        Text('フレームを解析しています...',
                            style: TextStyle(
                                color: Color(0xFFFF9500),
                                fontWeight: FontWeight.w700,
                                fontSize: 15)),
                      ],
                    ),
                  ),
                ] else if (_isRecording) ...[
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 10),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFF3B30).withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                              color: const Color(0xFFFF3B30)
                                  .withValues(alpha: 0.5)),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              decoration: const BoxDecoration(
                                shape: BoxShape.circle,
                                color: Color(0xFFFF3B30),
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              '${_recordingElapsed.inMinutes.toString().padLeft(2, '0')}:'
                              '${(_recordingElapsed.inSeconds % 60).toString().padLeft(2, '0')}',
                              style: const TextStyle(
                                color: Color(0xFFFF3B30),
                                fontSize: 16,
                                fontWeight: FontWeight.w800,
                                fontFamily: 'monospace',
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: _stopVideoRecordingAndAnalyze,
                          icon: const Icon(Icons.stop_rounded, size: 20),
                          label: const Text('録画停止',
                              style: TextStyle(
                                  fontWeight: FontWeight.w800, fontSize: 15)),
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFFFF3B30),
                            padding: const EdgeInsets.symmetric(vertical: 14),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(18)),
                          ),
                        ),
                      ),
                    ],
                  ),
                ] else if (videoReady) ...[
                  Row(
                    children: [
                      Expanded(
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 12),
                          decoration: BoxDecoration(
                            color: _uavDetectedInVideo
                                ? const Color(0xFF30D158).withValues(alpha: 0.15)
                                : Colors.white10,
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(
                              color: _uavDetectedInVideo
                                  ? const Color(0xFF30D158).withValues(alpha: 0.5)
                                  : Colors.white24,
                            ),
                          ),
                          child: Row(
                            children: [
                              Icon(
                                _uavDetectedInVideo
                                    ? Icons.airplanemode_active_rounded
                                    : Icons.airplanemode_inactive_rounded,
                                color: _uavDetectedInVideo
                                    ? const Color(0xFF30D158)
                                    : Colors.white38,
                                size: 18,
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  _uavDetectedInVideo ? 'UAV 検知済み' : '未検知',
                                  style: TextStyle(
                                    color: _uavDetectedInVideo
                                        ? const Color(0xFF30D158)
                                        : Colors.white54,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 14,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      OutlinedButton.icon(
                        onPressed: !_isBusy ? _startVideoRecording : null,
                        icon: const Icon(Icons.videocam_rounded, size: 16),
                        label: const Text('再録画'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.white70,
                          side: const BorderSide(color: Colors.white30),
                          padding: const EdgeInsets.symmetric(
                              vertical: 14, horizontal: 14),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(18)),
                        ),
                      ),
                    ],
                  ),
                ] else if (_cameraError != null) ...[
                  // カメラエラー時: 理由とリトライボタンを表示
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    decoration: BoxDecoration(
                      color: Colors.red.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: Colors.red.withValues(alpha: 0.4)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.videocam_off_rounded, color: Colors.redAccent, size: 20),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            _cameraError!,
                            style: const TextStyle(color: Colors.white70, fontSize: 13),
                          ),
                        ),
                        TextButton(
                          onPressed: _initCameraAndRecord,
                          child: const Text('再試行', style: TextStyle(color: Colors.redAccent)),
                        ),
                      ],
                    ),
                  ),
                ] else ...[
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: (_cameraReady && !_isBusy)
                          ? _startVideoRecording
                          : null,
                      icon: const Icon(Icons.videocam_rounded, size: 22),
                      label: Text(
                        _cameraReady ? '録画開始' : 'カメラ準備中...',
                        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                      ),
                      style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFFFF3B30),
                        disabledBackgroundColor: Colors.white12,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(18)),
                      ),
                    ),
                  ),
                ],

                const SizedBox(height: 12),

                // ZK 証明ボタン
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: canProve ? _runProofFromVideoEvidence : null,
                    style: FilledButton.styleFrom(
                      backgroundColor: canProve
                          ? const Color(0xFF30D158)
                          : Colors.white12,
                      disabledBackgroundColor: Colors.white12,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(18)),
                    ),
                    child: _isBusy
                        ? Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: Colors.white),
                              ),
                              const SizedBox(width: 10),
                              Text(
                                '証明生成中... $_elapsedLabel',
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 15),
                              ),
                            ],
                          )
                        : Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                Icons.verified_rounded,
                                size: 18,
                                color:
                                    canProve ? Colors.black87 : Colors.white24,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                canProve ? 'ZK 証明を実行' : '準備中...',
                                style: TextStyle(
                                  color: canProve
                                      ? Colors.black87
                                      : Colors.white24,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 16,
                                ),
                              ),
                            ],
                          ),
                  ),
                ),

                // 証明結果カード
                if (provenOnce) ...[
                  const SizedBox(height: 10),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 11),
                    decoration: BoxDecoration(
                      color: zkState.proofValid
                          ? const Color(0xFF30D158).withValues(alpha: 0.15)
                          : Colors.red.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: zkState.proofValid
                            ? const Color(0xFF30D158)
                            : Colors.red,
                      ),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          zkState.proofValid
                              ? Icons.verified_rounded
                              : Icons.cancel_rounded,
                          color: zkState.proofValid
                              ? const Color(0xFF30D158)
                              : Colors.red,
                          size: 20,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            zkState.verdictTitle,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                            ),
                          ),
                        ),
                        if (zkState.elapsed != null)
                          Text(
                            _formatElapsed(zkState.elapsed!),
                            style: const TextStyle(
                                color: Colors.white54, fontSize: 11),
                          ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }

  String _formatElapsed(Duration d) {
    final s = d.inMilliseconds / 1000.0;
    return s >= 60
        ? '${d.inMinutes}m ${d.inSeconds % 60}s'
        : '${s.toStringAsFixed(1)}s';
  }

  Widget _buildDetailsTab() {
    final zkState = ref.watch(zkProofProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(4, 4, 4, 12),
          child: Text(
            '詳細',
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1D2C2A),
            ),
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            child: Column(
              children: [
                // 回路セレクター
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: _surfaceDecoration(color: const Color(0xFFF8F6EE)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '証明回路',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 15,
                          color: Color(0xFF1D2C2A),
                        ),
                      ),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: SafetyCircuitConfig.all.map((config) {
                          final selected =
                              config.profile == _selectedCircuitProfile;
                          return ChoiceChip(
                            selected: selected,
                            label: Text(config.label),
                            onSelected: _isBusy
                                ? null
                                : (_) => setState(() =>
                                    _selectedCircuitProfile = config.profile),
                          );
                        }).toList(),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        _selectedCircuitConfig.description,
                        style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF5C6765),
                            height: 1.4),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 12),

                // ステータスログ
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: _isBusy
                        ? Colors.blue.shade50
                        : zkState.proofValid
                            ? Colors.green.shade50
                            : Colors.grey.shade100,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: _isBusy
                          ? Colors.blue.shade200
                          : zkState.proofValid
                              ? Colors.green.shade300
                              : Colors.grey.shade300,
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          if (_isBusy) ...[
                            const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            ),
                            const SizedBox(width: 8),
                          ],
                          Expanded(
                            child: Text(
                              _status,
                              style: TextStyle(
                                fontSize: 12,
                                color: _isBusy
                                    ? Colors.blue.shade800
                                    : Colors.black87,
                              ),
                            ),
                          ),
                        ],
                      ),
                      if (zkState.elapsed != null &&
                          zkState.elapsed!.inMilliseconds > 0) ...[
                        const SizedBox(height: 4),
                        Text(
                          _isBusy
                              ? '経過: $_elapsedLabel'
                              : '処理時間: ${_formatElapsed(zkState.elapsed!)}',
                          style: TextStyle(
                            fontSize: 11,
                            color: _isBusy
                                ? Colors.blue.shade600
                                : Colors.grey.shade600,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),

                // 検知結果
                if (_videoEvidence != null) ...[
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(14),
                    decoration:
                        _surfaceDecoration(color: const Color(0xFFF5F7F5)),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              _uavDetectedInVideo
                                  ? Icons.airplanemode_active_rounded
                                  : Icons.airplanemode_inactive_rounded,
                              size: 15,
                              color: _uavDetectedInVideo
                                  ? const Color(0xFF1A7F4B)
                                  : const Color(0xFF8A9A98),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              'UAV 検知結果',
                              style: TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 14,
                                color: _uavDetectedInVideo
                                    ? const Color(0xFF1A7F4B)
                                    : const Color(0xFF3A4A47),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(_videoDetectionSummary,
                            style: const TextStyle(
                                fontSize: 12,
                                color: Color(0xFF3A4A47),
                                height: 1.5)),
                        const SizedBox(height: 4),
                        Text(_detectionBackendStatus,
                            style: const TextStyle(
                                fontSize: 11,
                                color: Color(0xFF8A9A98),
                                height: 1.4)),
                        ..._videoDetectionDetails
                            .where((d) => d.previewPath != null)
                            .map((d) {
                          final file = File(d.previewPath!);
                          return Padding(
                            padding: const EdgeInsets.only(top: 10),
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(10),
                              child: file.existsSync()
                                  ? Image.file(file, fit: BoxFit.contain)
                                  : const SizedBox.shrink(),
                            ),
                          );
                        }),
                        if (_videoDetectionLabels.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Wrap(
                            spacing: 6,
                            runSpacing: 4,
                            children: _videoDetectionLabels
                                .map((label) => Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 8, vertical: 3),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFF0B6E69)
                                            .withValues(alpha: 0.1),
                                        borderRadius: BorderRadius.circular(8),
                                        border: Border.all(
                                            color: const Color(0xFF0B6E69)
                                                .withValues(alpha: 0.3)),
                                      ),
                                      child: Text(
                                        label,
                                        style: const TextStyle(
                                          fontSize: 11,
                                          color: Color(0xFF0B6E69),
                                          fontFamily: 'monospace',
                                        ),
                                      ),
                                    ))
                                .toList(),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],

                // 判定要約
                if (zkState.verdictTitle != '未実行') ...[
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(14),
                    decoration: _surfaceDecoration(
                      color: zkState.proofValid
                          ? const Color(0xFFEEFBF3)
                          : const Color(0xFFFFF0EE),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              zkState.proofValid
                                  ? Icons.verified_rounded
                                  : Icons.cancel_rounded,
                              size: 16,
                              color: zkState.proofValid
                                  ? const Color(0xFF1A7F4B)
                                  : Colors.red.shade700,
                            ),
                            const SizedBox(width: 6),
                            Text(
                              zkState.verdictTitle,
                              style: TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 14,
                                color: zkState.proofValid
                                    ? const Color(0xFF1A7F4B)
                                    : Colors.red.shade700,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(zkState.verdictSummary,
                            style: const TextStyle(
                                fontSize: 12,
                                color: Color(0xFF3A4A47),
                                height: 1.5)),
                        const SizedBox(height: 10),
                        const Divider(height: 1, color: Color(0xFFDDD9CC)),
                        const SizedBox(height: 10),
                        const Row(
                          children: [
                            Icon(Icons.lock_outline_rounded,
                                size: 13, color: Color(0xFF5C6765)),
                            SizedBox(width: 5),
                            Text(
                              'プライバシー',
                              style: TextStyle(
                                  fontWeight: FontWeight.w700,
                                  fontSize: 12,
                                  color: Color(0xFF5C6765)),
                            ),
                          ],
                        ),
                        const SizedBox(height: 5),
                        Text(zkState.privacySummary,
                            style: const TextStyle(
                                fontSize: 12,
                                color: Color(0xFF5C6765),
                                height: 1.5)),
                      ],
                    ),
                  ),
                ],

                const SizedBox(height: 12),
                _buildResultPanel(
                    title: 'Witness Inputs',
                    body: zkState.inputJson ?? ''),
                const SizedBox(height: 10),
                _buildResultPanel(
                    title: 'Public Signals',
                    body: zkState.publicSignals ?? ''),
                const SizedBox(height: 10),
                _buildResultPanel(
                    title: 'Proof JSON', body: zkState.proof ?? ''),
                const SizedBox(height: 20),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildLogTab() {
    return Container(
      color: const Color(0xFF0D1117),
      child: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Row(
                children: [
                  const Icon(Icons.terminal_rounded,
                      color: Color(0xFF58A6FF), size: 18),
                  const SizedBox(width: 8),
                  const Text(
                    'コンソールログ',
                    style: TextStyle(
                      color: Color(0xFF58A6FF),
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.5,
                    ),
                  ),
                  const Spacer(),
                  Text('${_logs.length} 件',
                      style: const TextStyle(
                          color: Color(0xFF8B949E), fontSize: 12)),
                  const SizedBox(width: 12),
                  GestureDetector(
                    onTap: () => setState(() => _logs.clear()),
                    child: const Icon(Icons.delete_outline_rounded,
                        color: Color(0xFF8B949E), size: 18),
                  ),
                ],
              ),
            ),
            const Divider(color: Color(0xFF21262D), height: 1),
            Expanded(
              child: _logs.isEmpty
                  ? const Center(
                      child: Text(
                        'ログがまだありません',
                        style: TextStyle(
                            color: Color(0xFF484F58), fontSize: 13),
                      ),
                    )
                  : ListView.builder(
                      controller: _logScrollController,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 8),
                      itemCount: _logs.length,
                      itemBuilder: (context, i) {
                        final line = _logs[i];
                        final isError =
                            line.contains('エラー') || line.contains('✗');
                        final isSuccess =
                            line.contains('✓') || line.contains('完了');
                        final isBle = line.contains('[BLE');
                        Color textColor = const Color(0xFFC9D1D9);
                        if (isError) textColor = const Color(0xFFF85149);
                        if (isSuccess) textColor = const Color(0xFF3FB950);
                        if (isBle) textColor = const Color(0xFF79C0FF);
                        return Padding(
                          padding: const EdgeInsets.symmetric(vertical: 2),
                          child: Text(
                            line,
                            style: TextStyle(
                              color: textColor,
                              fontSize: 11,
                              fontFamily: 'monospace',
                              height: 1.5,
                            ),
                          ),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _proofTimer?.cancel();
    _recordingTimer?.cancel();
    _liveDetectionTimer?.cancel();
    _bleRescanTimer?.cancel();
    _locationStream?.cancel();
    _bleScanSubscription?.cancel();
    FlutterBluePlus.stopScan();
    _barometerSubscription?.cancel();
    _yoloDetector?.dispose();
    _cameraController?.dispose();
    _droneLatController.dispose();
    _droneLonController.dispose();
    _droneAltController.dispose();
    _droneTimeController.dispose();
    _targetLatController.dispose();
    _targetLonController.dispose();
    _targetAltController.dispose();
    _targetTimeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final approxDistance = _approxDistanceMeters();
    final approxTimeDelta = _approxTimeDelta();
    return Scaffold(
      extendBody: true,
      backgroundColor: Colors.black,
      body: _selectedTabIndex == 0
          ? _buildMainTab(approxDistance, approxTimeDelta)
          : _selectedTabIndex == 1
              ? Container(
                  decoration: const BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Color(0xFFE8F3EE),
                        Color(0xFFF3F2EA),
                        Color(0xFFF8F5EC),
                      ],
                    ),
                  ),
                  child: SafeArea(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
                      child: _buildDetailsTab(),
                    ),
                  ),
                )
              : _selectedTabIndex == 2
                  ? _buildLogTab()
                  : const BleRawScanPage(),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedTabIndex,
        onDestinationSelected: (index) {
          setState(() => _selectedTabIndex = index);
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home_rounded),
            label: 'メイン',
          ),
          NavigationDestination(
            icon: Icon(Icons.data_object_outlined),
            selectedIcon: Icon(Icons.data_object_rounded),
            label: '詳細',
          ),
          NavigationDestination(
            icon: Icon(Icons.terminal_outlined),
            selectedIcon: Icon(Icons.terminal_rounded),
            label: 'ログ',
          ),
          NavigationDestination(
            icon: Icon(Icons.bluetooth_searching_outlined),
            selectedIcon: Icon(Icons.bluetooth_searching_rounded),
            label: 'BLE Raw',
          ),
        ],
      ),
    );
  }
}

// ── ライブ YOLO 検知バウンディングボックス描画 ───────────────────────────────

class _BboxPainter extends CustomPainter {
  const _BboxPainter({
    required this.detections,
    required this.previewSize,
    required this.screenSize,
  });

  final List<UavYoloDetection> detections;
  final Size previewSize;
  final Size screenSize;

  @override
  void paint(Canvas canvas, Size size) {
    final scaleX = screenSize.width / previewSize.height;
    final scaleY = screenSize.height / previewSize.width;
    final scale = scaleX < scaleY ? scaleX : scaleY;
    final offsetX = (screenSize.width - previewSize.height * scale) / 2;
    final offsetY = (screenSize.height - previewSize.width * scale) / 2;

    final boxPaint = Paint()
      ..color = const Color(0xFF30D158)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5;

    final bgPaint = Paint()..color = const Color(0xBB000000);

    for (final det in detections) {
      final left = det.left * scale + offsetX;
      final top = det.top * scale + offsetY;
      final right = det.right * scale + offsetX;
      final bottom = det.bottom * scale + offsetY;

      canvas.drawRect(Rect.fromLTRB(left, top, right, bottom), boxPaint);

      final label =
          '${det.label} ${(det.score * 100).toStringAsFixed(0)}%';
      final tp = TextPainter(
        text: TextSpan(
          text: label,
          style: const TextStyle(
            color: Color(0xFF30D158),
            fontSize: 11,
            fontWeight: FontWeight.w700,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();

      final labelRect = Rect.fromLTWH(left, top - 18, tp.width + 8, 18);
      canvas.drawRect(labelRect, bgPaint);
      tp.paint(canvas, Offset(left + 4, top - 16));
    }
  }

  @override
  bool shouldRepaint(_BboxPainter old) => old.detections != detections;
}
