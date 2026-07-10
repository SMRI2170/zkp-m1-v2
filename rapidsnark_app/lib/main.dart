import 'dart:convert';
import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:circom_witnesscalc/circom_witnesscalc.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter/services.dart';
import 'package:flutter_rapidsnark/flutter_rapidsnark.dart';
import 'package:geolocator/geolocator.dart';
import 'package:google_mlkit_image_labeling/google_mlkit_image_labeling.dart';
import 'package:google_mlkit_object_detection/google_mlkit_object_detection.dart';
import 'package:image/image.dart' as img;
import 'package:path_provider/path_provider.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:video_thumbnail/video_thumbnail.dart' as video_thumbnail;

import 'core/rssi_ranging.dart';
import 'core/rssi_logger.dart';
import 'detection/uav_yolo_detector.dart';
import 'features/ble_raw_scan/ble_raw_scan_page.dart';
import 'features/wifi_raw_scan/wifi_raw_scan_page.dart';

List<CameraDescription> _availableCameras = [];

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // カメラリスト取得は initState 側で行うため、ここでは空リストのまま起動する
  // （パーミッション未付与時に availableCameras() が例外を起こしても問題なし）
  try {
    _availableCameras = await availableCameras();
  } catch (_) {}
  runApp(const ProviderScope(child: RapidsnarkApp()));
}

class RapidsnarkApp extends StatelessWidget {
  const RapidsnarkApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'UAV Safety Proof Demo',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0B6E69),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF3F2EA),
        useMaterial3: true,
      ),
      home: const SafetyUseCasePage(),
    );
  }
}

class PositionSnapshot {
  const PositionSnapshot({
    required this.lat,
    required this.lon,
    required this.alt,
    required this.unixTimeSec,
  });
  final double lat;
  final double lon;
  final double alt;
  final int unixTimeSec;
}

// 動画録画時に Remote ID・GPS と同時にスナップショットした証拠データ
class VideoEvidence {
  const VideoEvidence({
    required this.path,
    required this.recordedAt,
  });

  final String path;         // 録画した動画のファイルパス
  final DateTime recordedAt; // 録画完了時刻（Remote ID スナップショットと紐付け）
}

class SampledVideoFrame {
  const SampledVideoFrame({required this.path, required this.timeMs});

  final String path;
  final int timeMs;
}

class VideoDetectionDetail {
  const VideoDetectionDetail({
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
  final List<VideoDetectedRegion> regions;
}

class VideoDetectedRegion {
  const VideoDetectedRegion({
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

enum DroneInputMode { manual, ble }

enum SafetyCircuitProfile {
  base,
  detectionFlag,
  detectionCommitment,
  featureClassifier,
  timeSeries,
}

class SafetyCircuitConfig {
  const SafetyCircuitConfig({
    required this.profile,
    required this.label,
    required this.assetPrefix,
    required this.description,
    this.requiresVideo = false,
  });

  final SafetyCircuitProfile profile;
  final String label;
  final String assetPrefix;
  final String description;
  final bool requiresVideo;
}

// ── OpenDroneID パケット (ASTM F3411-22a / opendroneid-core-c 準拠) ───────────
//
// BLE Service UUID 0xFFFA の Service Data AD から解析する。
// remote_id.py が BasicID (偶数 seq) と Location (奇数 seq) を交互に送信するため、
// スキャナーは Location メッセージを見つけ次第フォームに反映する。
//
// Location メッセージ (25 bytes) — opendroneid-core-c ODID_Location_encoded_t:
//   Byte 0    : (MessageType=1 << 4) | ProtoVersion
//   Byte 1    : Status[7:4] | Reserved[3] | HeightType[2] | EWDirection[1] | SpeedMult[0]
//                 Status high nibble: UNDECLARED=0, GROUND=1, AIRBORNE=2, EMERGENCY=3, RC_LOST=4
//                 EWDirection=1 → direction = raw + 180 (West half)
//                 SpeedMult=1  → speed_h = raw * 0.75 m/s (high domain)
//                 SpeedMult=0  → speed_h = raw * 0.25 m/s (low domain)
//   Byte 2    : Direction (uint8, 0-179 or 0-179+EWDir)
//   Byte 3    : SpeedHorizontal (uint8, ÷0.25 or ÷0.75 per SpeedMult)
//   Byte 4    : SpeedVertical (int8, ÷0.5 m/s, positive=up)
//   Bytes 5-8 : Latitude  (int32 LE, × 1e-7 degrees)
//   Bytes 9-12: Longitude (int32 LE, × 1e-7 degrees)
//   Bytes 13-14: AltitudeBaro (uint16 LE, raw=(alt+1000)/0.5, step=0.5m)
//   Bytes 15-16: AltitudeGeo  (uint16 LE, same encoding)
//   Bytes 17-18: Height      (uint16 LE, same encoding)
//   Byte 19   : HorizAcc[3:0] | VertAcc[7:4]
//   Byte 20   : BaroAcc[3:0]  | SpeedAcc[7:4]
//   Bytes 21-22: Timestamp (uint16 LE, 1/10 sec since UTC hour start)
//   Byte 23   : TSAcc[3:0] | Reserved[7:4]
//   Byte 24   : Reserved
//
// BasicID メッセージ (25 bytes) — opendroneid-core-c ODID_BasicID_encoded_t:
//   Byte 0    : (MessageType=0 << 4) | ProtoVersion
//   Byte 1    : (IDType << 4) | UAType  — IDType high nibble, UAType low nibble
//   Bytes 2-21: UAS_ID (20 bytes, null-padded ASCII or binary)
//   Bytes 22-24: Reserved
// System メッセージ (type=4, ASTM F3411-22a §6.4) のデコード結果
// ZK 証明には使用しないが、規格準拠受信の記録として保持する。
//
// System メッセージ 25 バイト構成:
//   Byte 0    : (MessageType=4 << 4) | ProtoVersion
//   Byte 1    : OperatorLocationType[1:0] | ClassificationType[4:2] | Reserved[7:5]
//   Bytes 2-5 : OperatorLatitude  (int32 LE, × 1e-7 degrees)
//   Bytes 6-9 : OperatorLongitude (int32 LE, × 1e-7 degrees)
//   Bytes 10-11: AreaCount        (uint16 LE)
//   Byte 12   : AreaRadius        (uint8, × 10 m)
//   Bytes 13-14: AreaCeiling      (uint16 LE, 高度エンコード: (alt+1000)/0.5)
//   Bytes 15-16: AreaFloor        (uint16 LE, 同上)
//   Byte 17   : (ClassEU << 4) | CategoryEU
//   Bytes 18-21: OperatorAltitudeGeo (float32 LE, m)
//   Bytes 22-24: Timestamp 下位 24bit (uint32 LE の低 3 バイト;
//                           epoch = 2019-01-01 00:00:00 UTC = Unix 1546300800)
class UavSystemPacket {
  const UavSystemPacket({
    required this.operatorLatitude,
    required this.operatorLongitude,
    required this.operatorAltitudeGeo,
    required this.areaCount,
    required this.areaRadiusMeters,
    required this.areaCeilingMeters,
    required this.areaFloorMeters,
    required this.operatorLocationType,
    required this.classificationType,
  });

  final double operatorLatitude;
  final double operatorLongitude;
  final double operatorAltitudeGeo; // m, float32 から読み出し
  final int areaCount;
  final int areaRadiusMeters;       // AreaRadius × 10
  final double areaCeilingMeters;
  final double areaFloorMeters;
  final int operatorLocationType;   // 0=TakeOff, 1=LiveGNSS, 2=Fixed, 3=Dynamic
  final int classificationType;

  @override
  String toString() =>
      'System(opLat=${operatorLatitude.toStringAsFixed(6)} '
      'opLon=${operatorLongitude.toStringAsFixed(6)} '
      'opAlt=${operatorAltitudeGeo.toStringAsFixed(1)}m '
      'area=$areaCount×r${areaRadiusMeters}m '
      '[${areaFloorMeters.toStringAsFixed(0)}m-${areaCeilingMeters.toStringAsFixed(0)}m])';
}

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
  static const _msgTypeSystem   = 4; // オペレーター位置
  static const _msgTypeMsgPack  = 0xF; // Message Pack (複数メッセージ束)

  // opendroneid-core-c BLE App Code (0x0D) — Service Data の先頭に付くことがある
  static const _odidAppCode = 0x0D;

  // BLE Manufacturer Data Company IDs
  static const _knownManufacturerIds = <int, String>{
    0x2005: 'DJI (legacy)',
    0x2006: 'DJI',
    0x0043: 'Parrot',
    0x0417: 'Autel Robotics',
    0x06D6: 'Skydio',
  };

  // opendroneid-core-c ODID_Status_t (UNDECLARED=0, GROUND=1, AIRBORNE=2, EMERGENCY=3, RC_LOST=4)
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

  // opendroneid-core-c 高度エンコード: raw = (alt_m + 1000) / 0.5
  // デコード: alt_m = raw * 0.5 - 1000
  static double _decodeAltitude(int raw) {
    if (raw == 0xFFFF) return 0.0;
    return raw * 0.5 - 1000.0;
  }

  // opendroneid-core-c 方向デコード: EWDirection フラグで西半球補正
  static double _decodeDirection(int raw, int ewDir) {
    return ewDir == 1 ? raw + 180.0 : raw.toDouble();
  }

  // opendroneid-core-c 水平速度デコード: SpeedMult フラグで高域スケール切替
  static double _decodeSpeedH(int raw, int speedMult) {
    return speedMult == 1 ? raw * 0.75 : raw * 0.25;
  }

  // opendroneid-core-c 垂直速度デコード: int8 × 0.5 m/s
  static double _decodeSpeedV(int raw) {
    final signed = raw >= 128 ? raw - 256 : raw;
    return signed * 0.5;
  }

  // タイムスタンプ再構築: 1/10 秒単位の時間内秒数 → Unix 秒
  static int _reconstructUnixTime(int tsRaw) {
    if (tsRaw == 0xFFFF) return DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final secondsWithinHour = tsRaw ~/ 10;
    final nowSec = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final hourStart = nowSec - (nowSec % 3600);
    return hourStart + secondsWithinHour;
  }

  /// Location メッセージ (type=1) をパースしてパケットを返す。
  /// Service Data の値部分（UUID を除く 25 バイト）を受け取る。
  static UavTelemetryPacket? tryParseLocation(List<int>? rawBytes, int seq) {
    if (rawBytes == null || rawBytes.length < 25) return null;
    final msgType = (rawBytes[0] >> 4) & 0x0F;
    if (msgType != _msgTypeLocation) return null;

    // Byte 1: Status[7:4] | Reserved[3] | HeightType[2] | EWDirection[1] | SpeedMult[0]
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

    if (latI32 == 0 && lonI32 == 0) return null; // 無効座標

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

  /// BasicID メッセージ (type=0) から UAS_ID 文字列と IDType/UAType を取り出す。
  static String? tryParseUasId(List<int>? rawBytes) {
    if (rawBytes == null || rawBytes.length < 25) return null;
    final msgType = (rawBytes[0] >> 4) & 0x0F;
    if (msgType != _msgTypeBasicId) return null;

    // Byte 1: (IDType << 4) | UAType — high nibble=IDType, low nibble=UAType

    final idBytes = rawBytes.sublist(2, 22);
    final nullIdx = idBytes.indexOf(0);
    return String.fromCharCodes(nullIdx >= 0 ? idBytes.sublist(0, nullIdx) : idBytes)
        .trim()
        .replaceAll('\x00', '');
  }

  /// System メッセージ (type=4) をパースしてオペレーター位置等を返す。
  /// ZK 証明の入力には使用しないが、規格準拠受信の完全性のために実装。
  static UavSystemPacket? tryParseSystem(List<int>? rawBytes) {
    if (rawBytes == null || rawBytes.length < 25) return null;
    final msgType = (rawBytes[0] >> 4) & 0x0F;
    if (msgType != _msgTypeSystem) return null;

    final byte1 = rawBytes[1] & 0xFF;
    final data  = ByteData.sublistView(Uint8List.fromList(rawBytes));
    final latI32 = data.getInt32(2, Endian.little);
    final lonI32 = data.getInt32(6, Endian.little);

    if (latI32 == 0 && lonI32 == 0) return null;

    // OperatorAltitudeGeo: bytes 18-21 を float32 LE として読む
    // (ASTM F3411-22a の packed struct に基づく。一部実装では uint16 の場合あり)
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
  /// App Code (0x0D) プレフィックスを除去してから返す。
  static List<int>? extractFromServiceData(Map<dynamic, List<int>> serviceData) {
    for (final entry in serviceData.entries) {
      final key = entry.key.toString().toLowerCase();
      if (!key.contains('fffa')) continue;
      final raw = entry.value;
      if (raw.isEmpty) continue;
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

  // ASTM Remote ID WiFi Beacon ベンダ固有 IE の OUI (FA 0B BC) と OUI type (0x0D)
  static const _wifiOdidOui = [0xFA, 0x0B, 0xBC];
  static const _wifiOdidOuiType = 0x0D;

  /// WiFi Beacon のベンダ固有 IE から OpenDroneID message pack を取り出す。
  /// ネイティブ側で OUI+type+counter を除去済みのことが多いが、
  /// 念のため OUI ヘッダーが残っていれば（OUI 3 + type 1 + counter 1 = 5B）除去し、
  /// 先頭に App Code (0x0D) が付く場合もスキップする。失敗時は null。
  static List<int>? extractFromWifiBeacon(List<int> ieContent) {
    if (ieContent.isEmpty) return null;
    var data = ieContent;
    // OUI (FA 0B BC) + type (0x0D) が残っている場合は OUI+type+counter の 5B を除去
    if (data.length > 5 &&
        data[0] == _wifiOdidOui[0] &&
        data[1] == _wifiOdidOui[1] &&
        data[2] == _wifiOdidOui[2] &&
        data[3] == _wifiOdidOuiType) {
      data = data.sublist(5);
    }
    if (data.isEmpty) return null;
    // BLE 同様、App Code (0x0D) が先頭に付くケースを吸収
    if (data[0] == _odidAppCode && data.length > 1) return data.sublist(1);
    return data;
  }

  /// Service Data ペイロードに含まれる全 25B OpenDroneID メッセージを返す。
  /// 単一メッセージ (type 0-14) はそのままリストに包む。
  /// Message Pack (type=0xF, ASTM F3411-22a §7.9) はヘッダーを解析して
  /// 各 25B メッセージを取り出す。
  ///   Byte 0 : (0xF << 4) | ProtoVersion
  ///   Byte 1 : SingleMessageSize (常に 25)
  ///   Byte 2 : MsgPackSize (1-9)
  ///   Byte 3+: 25B × MsgPackSize のメッセージ列
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

class SafetyUseCasePage extends StatefulWidget {
  const SafetyUseCasePage({super.key});

  @override
  State<SafetyUseCasePage> createState() => _SafetyUseCasePageState();
}

class _SafetyUseCasePageState extends State<SafetyUseCasePage> {
  static const _latCmNum = 11132000.0;
  static const _lonCmNum = 9128800.0;
  static const _geoDen = 10000000.0;
  static const _distanceLimitMeters = 30.0;
  static const _timeLimitSeconds = 5;
  static const _circuitConfigs = <SafetyCircuitConfig>[
    SafetyCircuitConfig(
      profile: SafetyCircuitProfile.base,
      label: 'Base',
      assetPrefix: 'distance30',
      description: '距離と時刻だけを証明する最小構成です。',
    ),
    SafetyCircuitConfig(
      profile: SafetyCircuitProfile.detectionFlag,
      label: 'Detection Flag',
      assetPrefix: 'distance30_detection_flag',
      description: 'UAV 検知フラグとスコア・クラスを追加する軽量案です。',
      requiresVideo: true,
    ),
    SafetyCircuitConfig(
      profile: SafetyCircuitProfile.detectionCommitment,
      label: 'Commitment',
      assetPrefix: 'distance30_detection_commitment',
      description: '座標を Poseidon ハッシュでコミットメント化し、プライバシーを保ちながら接近と検知を証明します。',
      requiresVideo: false,
    ),
    SafetyCircuitConfig(
      profile: SafetyCircuitProfile.featureClassifier,
      label: 'Feature Classifier',
      assetPrefix: 'distance30_feature_classifier',
      description: '外部抽出した特徴量を小さな分類器で評価する拡張案です。',
      requiresVideo: true,
    ),
    SafetyCircuitConfig(
      profile: SafetyCircuitProfile.timeSeries,
      label: 'Time Series (20点)',
      assetPrefix: 'distance30_time_series',
      description: '録画中に収集した最大 20 ペアの時系列データを使い、いずれか 1 点でも接近していれば接近を証明します。',
      requiresVideo: false,
    ),
  ];
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

  final _rapidsnark = Rapidsnark();
  final _witnesscalc = CircomWitnesscalc();

  String _status = 'ドローン側は手入力 / BLE 受信 / WiFi 受信、利用者側は端末センサー取得で進められます。';
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
  String _inputJson = '';
  String _publicSignals = '';
  String _proof = '';
  String _verdictTitle = '未実行';
  String _verdictSummary = 'まだ証明は生成されていません。';
  String _privacySummary = '座標そのものは公開せず、真偽だけを共有します。';
  bool _proofValid = false;
  bool _isBusy = false;
  bool _isScanningDrone = false;
  DateTime? _proofStartedAt;
  Duration? _proofElapsed;
  Timer? _proofTimer;
  bool _uavDetectedInVideo = false;
  double? _groundPressureHpa;     // アプリ起動時に記録した地上気圧 (QFE 基準)
  double? _currentAltitudeMeters;
  Timer? _autoLocationTimer;
  Timer? _bleRescanTimer;
  // カメラ
  CameraController? _cameraController;
  bool _cameraReady = false;
  bool _isCapturing = false; // 録画停止後の YOLO 解析中フラグ
  bool _isRecording = false;
  DateTime? _recordingStartedAt;
  Duration _recordingElapsed = Duration.zero;
  Timer? _recordingTimer;
  // ライブ検知（Plan B）
  List<UavYoloDetection> _liveDetections = const [];
  Size? _previewSize;
  bool _isLiveDetecting = false;
  Timer? _liveDetectionTimer;
  // データ履歴（常時蓄積、最大20件）
  final List<PositionSnapshot> _locationHistory = [];
  final List<UavTelemetryPacket> _droneHistory = [];
  StreamSubscription<Position>? _locationStream;
  StreamSubscription<List<ScanResult>>? _bleScanSubscription;
  // WiFi Beacon (OpenDroneID) 受信ストリーム — ネイティブの EventChannel を購読
  static const _wifiOdidChannel = EventChannel('uav/wifi_odid');
  StreamSubscription<dynamic>? _wifiScanSubscription;
  int _scanSeq = 0;
  VideoEvidence? _videoEvidence; // 録画した動画（Remote ID と同時スナップショット）
  List<String> _videoDetectionLabels = const [];
  List<VideoDetectionDetail> _videoDetectionDetails = const [];
  String _videoDetectionSummary = '「撮影して検知」でドローンを撮影すると YOLO で自動解析します。';
  UavYoloDetector? _yoloDetector;
  String _detectionBackendLabel = 'ML Kit fallback';
  String _detectionBackendStatus = 'YOLO モデルがまだ入っていないため、軽量ラベリングで解析します。';
  StreamSubscription<BarometerEvent>? _barometerSubscription;
  UavTelemetryPacket? _lastDroneTelemetry;
  // 最後にドローン位置を受信した経路（'BLE' / 'WiFi'）。UI 表示用。
  String? _lastDroneSource;
  // WiFi Beacon を 1 件以上受信したか（UI のスキャン状態表示用）
  bool _wifiOdidSeen = false;
  // 最後に WiFi Beacon で OpenDroneID を受信した時刻。
  // Beacon で取れている間は NAN を処理しない（重複検知の抑止 / Beacon 優先）。
  DateTime? _lastBeaconOdidAt;
  static const _beaconPreferWindow = Duration(seconds: 15);

  bool get _hasTargetInputsReady =>
      _targetLatController.text.isNotEmpty &&
      _targetLonController.text.isNotEmpty &&
      _targetAltController.text.isNotEmpty &&
      _targetTimeController.text.isNotEmpty;

  String get _droneModeLabel =>
      _droneInputMode == DroneInputMode.ble ? 'Raspberry Pi BLE 受信' : '手入力';

  SafetyCircuitConfig get _selectedCircuitConfig => _circuitConfigs.firstWhere(
    (config) => config.profile == _selectedCircuitProfile,
  );

  String get _collectionNextAction {
    if (_droneInputMode == DroneInputMode.ble && _lastDroneTelemetry == null) {
      return 'まず Raspberry Pi から受信します';
    }
    if (!_hasTargetInputsReady) {
      return '次に端末情報を取得します';
    }
    if (_videoEvidence == null) {
      return '録画ボタンでドローンを動画に収めてください';
    }
    if (!_uavDetectedInVideo) {
      return '動画解析結果を確認して再録画もできます';
    }
    return '証明実行まで進めます';
  }

  @override
  void initState() {
    super.initState();
    _applyDefaultInputs();
    _startBarometerStream();
    unawaited(_initializeDetectionPipeline());
    // GPS ストリーム開始（1秒ごと）
    _startLocationStream();
    // カメラ初期化
    unawaited(_initCameraAndRecord());
    // BLE モードなら起動時からスキャン開始、25秒ごとに再スキャン
    _startContinuousBleScan();
    // WiFi Beacon (DJI 等) 経由の Remote ID は、NEARBY_WIFI_DEVICES 許可後に開始する。
    // （許可前に開始すると WiFi Aware subscribe が SecurityException でクラッシュするため）
    unawaited(_requestWifiScanPermission());
  }

  /// WiFi スキャンに必要な権限を要求し、許可されてから受信を開始する。
  /// Android 13+ では NEARBY_WIFI_DEVICES が別権限。12 以下は ACCESS_FINE_LOCATION
  /// （GPS 取得時に要求済み）で代替される。
  Future<void> _requestWifiScanPermission() async {
    if (!Platform.isAndroid) {
      _startContinuousWifiScan();
      return;
    }
    try {
      final status = await Permission.nearbyWifiDevices.request();
      if (status.isGranted) {
        _startContinuousWifiScan();
      } else {
        _log('WiFi スキャン権限が未許可です。WiFi 経由の Remote ID 受信は無効です（BLE は継続）。');
      }
    } catch (_) {
      // 古い端末（12以下）では nearbyWifiDevices が無く例外 → FINE_LOCATION で代替、開始してよい
      _startContinuousWifiScan();
    }
  }

  Future<void> _initCameraAndRecord() async {
    // パーミッション取得後にカメラリストが空の場合は再取得
    if (_availableCameras.isEmpty) {
      try {
        _availableCameras = await availableCameras();
      } catch (e) {
        _log('カメラ取得エラー: $e');
        return;
      }
    }
    if (_availableCameras.isEmpty) {
      _log('カメラが見つかりません。カメラ権限を確認してください。');
      return;
    }
    final camera = _availableCameras.first;
    final controller = CameraController(
      camera,
      ResolutionPreset.medium,
      enableAudio: false,
    );
    try {
      await controller.initialize();
      if (!mounted) { await controller.dispose(); return; }
      setState(() {
        _cameraController = controller;
        _cameraReady = true;
        _previewSize = controller.value.previewSize;
      });
      _startLiveDetection();
    } catch (e) {
      _log('カメラ初期化エラー: $e');
    }
  }

  // ── ライブ検知 (Plan B) ─────────────────────────────────────────
  void _startLiveDetection() {
    if (_yoloDetector == null || _isLiveDetecting) return;
    _isLiveDetecting = true;
    _liveDetectionTimer = Timer.periodic(const Duration(milliseconds: 800), (_) async {
      if (!mounted || _isRecording || _isCapturing) return;
      final ctrl = _cameraController;
      if (ctrl == null || !ctrl.value.isInitialized) return;
      try {
        final photo = await ctrl.takePicture();
        final detections = await _yoloDetector!.detectImageFile(photo.path);
        await File(photo.path).delete();
        if (mounted) setState(() => _liveDetections = detections);
      } catch (_) {}
    });
  }

  void _stopLiveDetection() {
    _liveDetectionTimer?.cancel();
    _liveDetectionTimer = null;
    _isLiveDetecting = false;
    if (mounted) setState(() => _liveDetections = const []);
  }

  // ── 動画録画 (Plan A) ─────────────────────────────────────────
  Future<void> _startVideoRecording() async {
    final ctrl = _cameraController;
    if (ctrl == null || !_cameraReady || _isRecording || _isCapturing || _isBusy) return;
    _stopLiveDetection();
    try {
      await ctrl.startVideoRecording();
      if (!mounted) return;
      setState(() {
        _isRecording = true;
        _recordingStartedAt = DateTime.now();
        _recordingElapsed = Duration.zero;
      });
      _recordingTimer = Timer.periodic(const Duration(milliseconds: 100), (_) {
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
    setState(() { _isRecording = false; _isCapturing = true; });
    try {
      final videoFile = await ctrl.stopVideoRecording();
      final recordedAt = DateTime.now();
      _selectBestDataPair();
      setState(() {
        _videoEvidence = VideoEvidence(path: videoFile.path, recordedAt: recordedAt);
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
    // 時刻差が最小のドローン・ユーザーペアを選ぶ
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

  void _startLocationStream() {
    _locationStream?.cancel();
    _autoLocationTimer?.cancel();
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
    ).listen((position) async {
      double alt = _currentAltitudeMeters ?? 0.0;
      final unixSec = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final snapshot = PositionSnapshot(
        lat: position.latitude,
        lon: position.longitude,
        alt: alt,
        unixTimeSec: unixSec,
      );
      if (!mounted) return;
      setState(() {
        // 常時蓄積（最大20件）
        _locationHistory.add(snapshot);
        if (_locationHistory.length > 20) _locationHistory.removeAt(0);
        // 現在値を常時更新
        _targetLatController.text = position.latitude.toStringAsFixed(7);
        _targetLonController.text = position.longitude.toStringAsFixed(7);
        _targetAltController.text = alt.toStringAsFixed(1);
        _targetTimeController.text = unixSec.toString();
      });
    }, onError: (_) {});
  }

  void _startContinuousBleScan() {
    unawaited(_restartBleScan());
    // スキャン終了を検知して即座に再スキャン（空白を最小化）
    // isScanningNow が false に変わったタイミングで _restartBleScan を呼ぶ
    _bleRescanTimer?.cancel();
    _bleRescanTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!FlutterBluePlus.isScanningNow && !_isScanningDrone && !_isBusy) {
        unawaited(_restartBleScan());
      }
    });
  }

  /// 直近の RSSI サンプル（中央値集約でマルチパス外れ値に強くする）。
  final List<int> _recentDroneRssi = [];
  static const int _rssiWindow = 10;

  /// RSSI 較正データを CSV 蓄積するロガー（実機 DJI セッションの記録用）。
  final RssiLogger _rssiLogger = RssiLogger();

  /// RemoteID 放送位置と、RSSI から推定した実測レンジの整合をログに出す。
  /// 自端末 GPS（_target*Controller）と rssi が揃ったときのみ判定する。
  /// 直近 _rssiWindow 件の RSSI を中央値集約してから判定（単発は粗いため）。
  /// ドローンを一切改造せず、地上側の受信強度だけで放送値の矛盾を検出する土台。
  void _logRssiConsistency(
      double droneLat, double droneLon, double droneAltM, int rssi, String source) {
    final pLat = _tryParseDouble(_targetLatController.text);
    final pLon = _tryParseDouble(_targetLonController.text);
    if (pLat == null || pLon == null || rssi == 0) return;

    _recentDroneRssi.add(rssi);
    if (_recentDroneRssi.length > _rssiWindow) _recentDroneRssi.removeAt(0);

    final pAlt = _tryParseDouble(_targetAltController.text) ?? 0.0;
    final horiz = Geolocator.distanceBetween(pLat, pLon, droneLat, droneLon);
    final dAlt = droneAltM - pAlt;
    final claimed = math.sqrt(horiz * horiz + dAlt * dAlt);
    final r = checkRssiConsistencyFromSamples(
        claimedDistanceM: claimed, rssiSamples: _recentDroneRssi);
    if (r.verdict == RssiVerdict.unknown) return;
    _log('[$source RSSI-check] ${r.label} '
        'n=${_recentDroneRssi.length} '
        'claimed=${claimed.toStringAsFixed(1)}m '
        'est=${r.estimatedRangeM.toStringAsFixed(1)}m '
        'band[${r.lowerM.toStringAsFixed(1)},${r.upperM.toStringAsFixed(1)}]m');

    // 実機較正用に CSV へ蓄積（UI は止めない）
    unawaited(_rssiLogger.append(RssiLogRow(
      t: DateTime.now(),
      source: source,
      rssi: rssi,
      claimedM: claimed,
      estM: r.estimatedRangeM,
      verdict: r.label,
      phoneLat: pLat,
      phoneLon: pLon,
      droneLat: droneLat,
      droneLon: droneLon,
      droneAltM: droneAltM,
    )));
  }

  Future<void> _restartBleScan() async {
    if (_isScanningDrone) return;
    if (mounted) setState(() { _isScanningDrone = true; });
    try {
      // Bluetooth ON 確認
      final adapterState = await FlutterBluePlus.adapterState.first;
      if (adapterState != BluetoothAdapterState.on) {
        _log('Bluetooth がオフです。オンにしてください。');
        return;
      }

      await FlutterBluePlus.stopScan();
      await _bleScanSubscription?.cancel();

      _bleScanSubscription = FlutterBluePlus.scanResults.listen((results) {
        for (final result in results) {
          // ① serviceData から標準 OpenDroneID UUID 0xFFFA を探す
          // ② 見つからなければ manufacturerData から DJI 旧機種 (0x2005) を探す
          final ad = result.advertisementData;
          final odidBytes =
              UavTelemetryPacket.extractFromServiceData(ad.serviceData) ??
              UavTelemetryPacket.extractFromManufacturerData(ad.manufacturerData);
          if (odidBytes == null) continue;

          // 単一メッセージ / Message Pack を統一処理
          final messages = UavTelemetryPacket.extractAllMessages(odidBytes);
          for (final msg in messages) {
            final msgType = msg.isNotEmpty ? (msg[0] >> 4) & 0x0F : -1;

            // BasicID (type=0) → UAS_ID を保持
            if (msgType == 0) {
              final uasId = UavTelemetryPacket.tryParseUasId(msg);
              if (uasId != null && uasId.isNotEmpty) {
                _log('[BLE BasicID] UAS_ID=$uasId rssi=${result.rssi}dBm');
              }
              continue;
            }

            // Location (type=1) → 即座に UI へ反映
            if (msgType == 1) {
              final packet = UavTelemetryPacket.tryParseLocation(msg, _scanSeq++);
              if (packet != null && mounted) {
                _log('[BLE Location] seq=${packet.sequence} '
                    'lat=${packet.latitude.toStringAsFixed(6)} '
                    'lon=${packet.longitude.toStringAsFixed(6)} '
                    'alt=${packet.altitudeMeters.toStringAsFixed(1)}m '
                    'airborne=${packet.statusIsAirborne} '
                    'rssi=${result.rssi}dBm');
                _logRssiConsistency(packet.latitude, packet.longitude,
                    packet.altitudeMeters, result.rssi, 'BLE');
                setState(() => _applyDroneTelemetry(packet, source: 'BLE'));
              }
              continue;
            }

            // System (type=4) → オペレーター位置をログに記録（ZK 証明では未使用）
            if (msgType == 4) {
              final sys = UavTelemetryPacket.tryParseSystem(msg);
              if (sys != null) {
                _log('[BLE System] $sys rssi=${result.rssi}dBm');
              }
              continue;
            }

            // その他 (SelfID=3, OperatorID=5, Auth=2 等) → 型番だけログ
            _log('[BLE type=$msgType] ${msg.length}B (未パース) rssi=${result.rssi}dBm');
          }
        }
      });

      // withServices フィルターを使わない:
      // remote_id.py は Service Data (0x16) のみ送信し UUID リスト (0x03) を含まないため
      // Android の withServices フィルターに引っかからずパケットが捨てられてしまう
      await FlutterBluePlus.startScan(timeout: const Duration(seconds: 20));
    } catch (e) {
      _log('BLE スキャンエラー: $e');
    } finally {
      if (mounted) setState(() { _isScanningDrone = false; });
    }
  }

  /// WiFi Beacon 経由の OpenDroneID を常時受信する（Android 11+ / DJI 等対応）。
  /// ネイティブ (WifiOdidScanner) が EventChannel でベンダ固有 IE の
  /// message pack を流してくるので、BLE と同じパースで証明フローへ合流させる。
  void _startContinuousWifiScan() {
    _wifiScanSubscription?.cancel();
    _wifiScanSubscription = _wifiOdidChannel.receiveBroadcastStream().listen(
      _onWifiOdidEvent,
      onError: (Object e) => _log('WiFi スキャンエラー: $e'),
    );
  }

  void _onWifiOdidEvent(dynamic event) {
    if (event is! Map) return;
    final rawPayload = event['payload'];
    if (rawPayload == null) return;
    final payload = List<int>.from(rawPayload as List);
    final rssi = (event['rssi'] as num?)?.toInt() ?? 0;
    final ssid = (event['ssid'] as String?) ?? '';
    // 'Beacon' or 'NAN'（DJI 等は機種により搬送方式が異なる）
    final transport = (event['transport'] as String?) ?? 'Beacon';
    final tag = 'WiFi/$transport';

    final odidBytes = UavTelemetryPacket.extractFromWifiBeacon(payload);
    if (odidBytes == null) return;

    // Beacon 優先: Beacon で受信できている間は NAN を処理しない（重複検知の抑止）。
    final now = DateTime.now();
    if (transport == 'Beacon') {
      _lastBeaconOdidAt = now;
    } else if (_lastBeaconOdidAt != null &&
        now.difference(_lastBeaconOdidAt!) < _beaconPreferWindow) {
      return; // Beacon が生きているので NAN はスキップ
    }

    if (!_wifiOdidSeen && mounted) setState(() => _wifiOdidSeen = true);

    // 単一メッセージ / Message Pack を BLE と同じ分岐で処理
    for (final msg in UavTelemetryPacket.extractAllMessages(odidBytes)) {
      final msgType = msg.isNotEmpty ? (msg[0] >> 4) & 0x0F : -1;

      // BasicID (type=0) → UAS_ID をログ
      if (msgType == 0) {
        final uasId = UavTelemetryPacket.tryParseUasId(msg);
        if (uasId != null && uasId.isNotEmpty) {
          _log('[$tag BasicID] UAS_ID=$uasId ssid=$ssid rssi=${rssi}dBm');
        }
        continue;
      }

      // Location (type=1) → 即座に UI へ反映
      if (msgType == 1) {
        final packet = UavTelemetryPacket.tryParseLocation(msg, _scanSeq++);
        if (packet != null && mounted) {
          _log('[$tag Location] seq=${packet.sequence} '
              'lat=${packet.latitude.toStringAsFixed(6)} '
              'lon=${packet.longitude.toStringAsFixed(6)} '
              'alt=${packet.altitudeMeters.toStringAsFixed(1)}m '
              'airborne=${packet.statusIsAirborne} '
              'ssid=$ssid rssi=${rssi}dBm');
          _logRssiConsistency(packet.latitude, packet.longitude,
              packet.altitudeMeters, rssi, 'WiFi/$transport');
          setState(() => _applyDroneTelemetry(packet, source: 'WiFi'));
        }
        continue;
      }

      // System (type=4) → オペレーター位置をログに記録（ZK 証明では未使用）
      if (msgType == 4) {
        final sys = UavTelemetryPacket.tryParseSystem(msg);
        if (sys != null) {
          _log('[$tag System] $sys rssi=${rssi}dBm');
        }
        continue;
      }

      _log('[$tag type=$msgType] ${msg.length}B (未パース) rssi=${rssi}dBm');
    }
  }

  Future<void> _initializeDetectionPipeline() async {
    try {
      final detector = await UavYoloDetector.tryCreateFromCandidates([
        UavYoloDetector.newModelConfigAsset,
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
          _detectionBackendStatus =
              detector.description.contains('uav_visdrone_finetuned')
              ? 'VisDrone 事前学習後に UAV へ fine-tune したプロファイルを優先して読み込みました。動画解析とライブ検知の両方でこのモデルを使います。'
              : detector.description.contains('uav_roboflow_drone')
              ? 'Roboflow の UAV 専用プロファイルを優先して読み込みました。動画解析とライブ検知の両方でこのモデルを使います。'
              : 'YOLO モデルを読み込みました。動画フレーム解析では YOLO を優先利用します。';
        } else {
          _detectionBackendLabel = 'ML Kit fallback';
          _detectionBackendStatus =
              'YOLO モデルが無効または未配置のため、軽量ラベリングを利用します。Roboflow 用またはサンプル YOLO 用の config を有効化すると切り替わります。';
        }
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _yoloDetector = null;
        _detectionBackendLabel = 'ML Kit fallback';
        _detectionBackendStatus =
            'YOLO 初期化に失敗したため、軽量ラベリングへフォールバックします。error=$error';
      });
    }
  }

  Future<String> _copyAssetToTemp({
    required String assetPath,
    required String fileName,
  }) async {
    final directory = await getTemporaryDirectory();
    final outputFile = File('${directory.path}/$fileName');
    final bytes = (await rootBundle.load(assetPath)).buffer.asUint8List();
    await outputFile.writeAsBytes(bytes, flush: true);
    return outputFile.path;
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
    _log('ドローン側は手入力 / BLE 受信 / WiFi 受信、利用者側は端末の GPS と気圧センサーで取得できます。');
    _inputJson = '';
    _publicSignals = '';
    _proof = '';
    _verdictTitle = '未実行';
    _verdictSummary = 'まだ証明は生成されていません。';
    _privacySummary = '端末内で証明を生成し、公開するのは安全判定だけです。';
    _proofValid = false;
  }

  int _normalizeLatitude(String value) {
    final latitude = double.parse(value);
    return ((latitude + 90.0) * 10000000).round();
  }

  int _normalizeLongitude(String value) {
    final longitude = double.parse(value);
    return ((longitude + 180.0) * 10000000).round();
  }

  int _metersToCentimeters(String value) {
    return (double.parse(value) * 100).round();
  }

  int _seconds(String value) {
    return int.parse(value);
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

  Map<String, dynamic> _buildBaseInputPayload() {
    return <String, String>{
      'drone_lat_e7_norm': _normalizeLatitude(
        _droneLatController.text,
      ).toString(),
      'drone_lon_e7_norm': _normalizeLongitude(
        _droneLonController.text,
      ).toString(),
      'drone_alt_cm': _metersToCentimeters(_droneAltController.text).toString(),
      'drone_time_sec': _seconds(_droneTimeController.text).toString(),
      'target_lat_e7_norm': _normalizeLatitude(
        _targetLatController.text,
      ).toString(),
      'target_lon_e7_norm': _normalizeLongitude(
        _targetLonController.text,
      ).toString(),
      'target_alt_cm': _metersToCentimeters(
        _targetAltController.text,
      ).toString(),
      'target_time_sec': _seconds(_targetTimeController.text).toString(),
    };
  }

  int _estimateDetectionScoreBps() {
    if (!_uavDetectedInVideo) {
      return 0;
    }

    double bestScore = 0.85;
    for (final detail in _videoDetectionDetails) {
      for (final region in detail.regions) {
        if (_looksLikeUavLabel(region.label.toLowerCase())) {
          bestScore = math.max(bestScore, region.confidence);
        }
      }
      for (final label in detail.labels) {
        final parts = label.split(':');
        if (parts.length != 2) {
          continue;
        }
        final rawLabel = parts.first.toLowerCase();
        final confidence = double.tryParse(parts.last) ?? 0.0;
        if (_looksLikeUavLabel(rawLabel)) {
          bestScore = math.max(bestScore, confidence);
        }
      }
    }
    return (bestScore * 10000).round();
  }

  int _deriveStableHash(String input, int seed) {
    var hash = seed;
    for (final byte in utf8.encode(input)) {
      hash = ((hash * 131) + byte) & 0x7fffffff;
    }
    return hash;
  }

  Map<String, dynamic> _buildTimeSeriesInputPayload() {
    const n = 20;

    final droneEntries = _droneHistory.take(n).toList();
    final UavTelemetryPacket? lastDrone =
        droneEntries.isNotEmpty ? droneEntries.last : null;
    while (droneEntries.length < n) {
      droneEntries.add(
        lastDrone ??
            const UavTelemetryPacket(
              latitude: 0,
              longitude: 0,
              altitudeMeters: 0,
              altitudeGeoMeters: 0,
              speedH: 0,
              speedV: 0,
              direction: 0,
              statusIsAirborne: false,
              unixTimeSec: 0,
              sequence: 0,
            ),
      );
    }

    final locationEntries = _locationHistory.take(n).toList();
    final PositionSnapshot? lastLoc =
        locationEntries.isNotEmpty ? locationEntries.last : null;
    while (locationEntries.length < n) {
      locationEntries.add(
        lastLoc ??
            const PositionSnapshot(lat: 0, lon: 0, alt: 0, unixTimeSec: 0),
      );
    }

    String normLat(double lat) => ((lat + 90) * 1e7).round().toString();
    String normLon(double lon) => ((lon + 180) * 1e7).round().toString();
    String altCm(double alt) => (alt * 100).round().toString();

    return {
      'drone_lat_e7_norm':
          droneEntries.map((d) => normLat(d.latitude)).toList(),
      'drone_lon_e7_norm':
          droneEntries.map((d) => normLon(d.longitude)).toList(),
      'drone_alt_cm': droneEntries.map((d) => altCm(d.altitudeMeters)).toList(),
      'drone_time_sec':
          droneEntries.map((d) => d.unixTimeSec.toString()).toList(),
      'target_lat_e7_norm':
          locationEntries.map((l) => normLat(l.lat)).toList(),
      'target_lon_e7_norm':
          locationEntries.map((l) => normLon(l.lon)).toList(),
      'target_alt_cm': locationEntries.map((l) => altCm(l.alt)).toList(),
      'target_time_sec':
          locationEntries.map((l) => l.unixTimeSec.toString()).toList(),
    };
  }

  Map<String, dynamic> _buildInputsPayload() {
    if (_selectedCircuitProfile == SafetyCircuitProfile.timeSeries) {
      return _buildTimeSeriesInputPayload();
    }
    final payload = _buildBaseInputPayload();
    final targetTime = _seconds(_targetTimeController.text);

    switch (_selectedCircuitProfile) {
      case SafetyCircuitProfile.base:
        break;
      case SafetyCircuitProfile.detectionFlag:
        payload.addAll({
          'uav_detected': _uavDetectedInVideo ? '1' : '0',
          'detection_score_bps': _estimateDetectionScoreBps().toString(),
          'detection_class_id': '1',
        });
        break;
      case SafetyCircuitProfile.detectionCommitment:
        final evidence = _videoEvidence;
        // 録画完了時刻を frame_time_sec に使う。未録画の場合は target_time を代入
        final frameTimeSec = evidence != null
            ? (evidence.recordedAt.millisecondsSinceEpoch ~/ 1000)
            : targetTime;
        final commitmentSeed = evidence == null
            ? 'no-evidence'
            : '${evidence.path}|${evidence.recordedAt.toIso8601String()}';
        payload.addAll({
          'uav_detected': _uavDetectedInVideo ? '1' : '0',
          'detection_score_bps': _estimateDetectionScoreBps().toString(),
          'detection_class_id': '1',
          'frame_time_sec': frameTimeSec.toString(),
          // 動画フレームの外部ハッシュ（254-bit を hi/lo に分割）
          // 回路内で Poseidon(hi, lo) として frame_binding にバインドされる
          'frame_commitment_hi': _deriveStableHash(commitmentSeed, 17).toString(),
          'frame_commitment_lo': _deriveStableHash(commitmentSeed, 97).toString(),
        });
        break;
      case SafetyCircuitProfile.featureClassifier:
        final detailCount = _videoDetectionDetails.length;
        final regionCount = _videoDetectionDetails.fold<int>(
          0,
          (sum, detail) => sum + detail.regions.length,
        );
        final feature0 = _uavDetectedInVideo ? 60 : 0;
        final feature1 = math.max(detailCount, 1) * 20;
        final feature2 = math.max(regionCount, 1) * 10;
        final feature3 = _detectionBackendLabel.contains('YOLO') ? 30 : 12;
        payload.addAll({
          'frame_time_sec': targetTime.toString(),
          'features': [
            feature0.toString(),
            feature1.toString(),
            feature2.toString(),
            feature3.toString(),
          ],
        });
        break;
      case SafetyCircuitProfile.timeSeries:
        // handled by early return above
        break;
    }

    return payload;
  }

  String _buildInputsJson() {
    return const JsonEncoder.withIndent('  ').convert(_buildInputsPayload());
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

    final latDiffE7 = ((targetLat - droneLat).abs() * 10000000);
    final lonDiffE7 = ((targetLon - droneLon).abs() * 10000000);
    final altDiffCm = ((targetAlt - droneAlt).abs() * 100);

    final latMeters = (latDiffE7 * _latCmNum / _geoDen) / 100;
    final lonMeters = (lonDiffE7 * _lonCmNum / _geoDen) / 100;
    final altMeters = altDiffCm / 100;

    return math.sqrt(
      latMeters * latMeters + lonMeters * lonMeters + altMeters * altMeters,
    );
  }

  int _approxTimeDelta() {
    final targetTime = _tryParseInt(_targetTimeController.text);
    final droneTime = _tryParseInt(_droneTimeController.text);
    if (targetTime == null || droneTime == null) {
      return 0;
    }
    return (targetTime - droneTime).abs();
  }

  void _applyDroneTelemetry(UavTelemetryPacket packet, {String? source}) {
    _droneLatController.text = packet.latitude.toStringAsFixed(7);
    _droneLonController.text = packet.longitude.toStringAsFixed(7);
    _droneAltController.text = packet.altitudeMeters.toStringAsFixed(1);
    _droneTimeController.text = packet.unixTimeSec.toString();
    _lastDroneTelemetry = packet;
    if (source != null) _lastDroneSource = source;
    // 常時蓄積（最大20件）
    _droneHistory.add(packet);
    if (_droneHistory.length > 20) _droneHistory.removeAt(0);
  }

  void _applySemanticResult(List<dynamic> publicSignals) {
    final within30 =
        publicSignals.isNotEmpty && publicSignals[0].toString() == '1';
    final distanceOk =
        publicSignals.length > 1 && publicSignals[1].toString() == '1';
    final timeOk =
        publicSignals.length > 2 && publicSignals[2].toString() == '1';
    final approxDistance = _approxDistanceMeters();
    final approxTimeDelta = _approxTimeDelta();

    _verdictTitle = within30 ? '接近あり: 要注意' : '安全距離を維持';

    if (within30) {
      _verdictSummary =
          'この証明では、対象者とドローンが30m以内に入り、かつ時刻差も$_timeLimitSeconds秒以内でした。苦情対応や事故検証に使える結果です。';
    } else if (!distanceOk && timeOk) {
      _verdictSummary =
          '時刻は揃っていますが、推定距離は ${approxDistance.toStringAsFixed(1)}m で30mを超えています。住民・観客側にとって安全側の結果です。';
    } else if (distanceOk && !timeOk) {
      _verdictSummary =
          '空間的には近くても、検知時刻との差が ${approxTimeDelta}s あり、同一瞬間の接近とは見なされません。';
    } else {
      _verdictSummary =
          '距離も時刻も閾値外でした。第三者の位置や飛行ルートを公開せず、安全側の判定だけを共有できます。';
    }

    // Commitment 回路（public outputs 10 個）の追加解釈
    // 出力順: [0]within30 [1]distance_ok [2]time_ok [3]detection_ok
    //         [4]frame_time_ok [5]detection_bundle_ok [6]within30_and_detected
    //         [7]drone_commitment [8]target_commitment [9]frame_binding
    if (_selectedCircuitProfile == SafetyCircuitProfile.detectionCommitment &&
        publicSignals.length >= 10) {
      final detectionOk = publicSignals[3].toString() == '1';
      final withinAndDetected = publicSignals[6].toString() == '1';
      final droneCommit = publicSignals[7].toString();
      final targetCommit = publicSignals[8].toString();
      final frameBinding = publicSignals[9].toString();

      if (withinAndDetected) {
        _verdictTitle = '接近あり + UAV 検知: 要注意';
        _verdictSummary =
            '30m 以内の接近と UAV 検知の両方が成立しています。'
            'Poseidon コミットメント付きの証明として記録できます。';
      } else if (within30 && !detectionOk) {
        _verdictSummary +=
            '\n(距離は 30m 以内ですが、UAV 検知スコアが基準を下回っています)';
      }

      final droneShort =
          droneCommit.length > 8 ? '${droneCommit.substring(0, 8)}...' : droneCommit;
      final targetShort =
          targetCommit.length > 8 ? '${targetCommit.substring(0, 8)}...' : targetCommit;
      final frameShort =
          frameBinding.length > 8 ? '${frameBinding.substring(0, 8)}...' : frameBinding;

      _privacySummary =
          'Poseidon ハッシュにより、座標の実値は非公開のまま証明に結びついています。\n'
          'drone:   $droneShort\n'
          'target:  $targetShort\n'
          'frame:   $frameShort\n'
          '(完全な値は Public Signals パネルに表示されます)';
    } else if (_selectedCircuitProfile == SafetyCircuitProfile.timeSeries &&
        publicSignals.length >= 21) {
      // Time Series 回路: outputs = within30[0..19] (indices 0-19) + any_within30 (index 20)
      final anyWithin30 = publicSignals[20].toString() == '1';
      final hitCount = List.generate(20, (i) => publicSignals[i].toString() == '1' ? 1 : 0)
          .fold(0, (a, b) => a + b);
      _verdictTitle = anyWithin30 ? '接近あり: 要注意 (時系列)' : '安全距離を維持 (時系列)';
      _verdictSummary = anyWithin30
          ? '$hitCount / 20 ペアで 30m 以内への接近が確認されました。録画中のデータが証拠として記録されます。'
          : '20 ペアすべてで 30m 以内への接近はありませんでした。録画期間中は安全距離を維持しています。';
      _privacySummary =
          'any_within30=$anyWithin30 のみが公開されます。生の GPS 座標・飛行ルートは外へ出しません。';
      _proofValid = anyWithin30;
    } else {
      _privacySummary =
          '公開信号は within30=$within30, distance_ok=$distanceOk, time_ok=$timeOk のみで、生の位置座標や飛行ルートは外へ出しません。';
    }
  }

  String _assetPathFor(String suffix) {
    final config = _selectedCircuitConfig;
    if (config.profile == SafetyCircuitProfile.base) {
      return 'assets/distance30$suffix';
    }
    return 'assets/circuits/${config.assetPrefix}/${config.assetPrefix}$suffix';
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

  Future<void> _runProofFlow() async {
    FocusScope.of(context).unfocus();

    _startProofTimer();
    setState(() {
      _isBusy = true;
      _inputJson = '';
      _publicSignals = '';
      _proof = '';
      _proofValid = false;
      _proofElapsed = Duration.zero;
    });
    _log('ドローン入力値と端末取得ログをもとに証明条件を準備しています...');

    try {
      final inputsJson = _buildInputsJson();
      final circuitConfig = _selectedCircuitConfig;
      final graphData = (await rootBundle.load(
        _assetPathFor('.wcd'),
      )).buffer.asUint8List();
      if (graphData.length < 32) {
        throw Exception(
          '${circuitConfig.assetPrefix}.wcd が不足しています。対応する build スクリプトで assets を再生成してください。',
        );
      }

      final verificationKey = await rootBundle.loadString(
        _assetPathFor('_verification_key.json'),
      );

      setState(() { _inputJson = inputsJson; });
      _log('① Witness を計算しています...');

      final zkeyPath = await _copyAssetToTemp(
        assetPath: _assetPathFor('_groth16.zkey'),
        fileName: '${circuitConfig.assetPrefix}_groth16.zkey',
      );

      final witness = await _witnesscalc.calculateWitness(
        inputs: inputsJson,
        graphData: graphData,
      );
      if (witness == null) {
        throw Exception('Witness generation returned null.');
      }

      _log('② Groth16 証明を生成しています...');

      final publicBufferSize = await _rapidsnark.groth16PublicBufferSize(
        zkeyPath: zkeyPath,
      );
      final proveResult = await _rapidsnark.groth16Prove(
        zkeyPath: zkeyPath,
        witness: witness,
        publicBufferSize: publicBufferSize,
      );

      _log('③ 検証キーで確認しています...');

      final proofValid = await _rapidsnark.groth16Verify(
        proof: proveResult.proof,
        inputs: proveResult.publicSignals,
        verificationKey: verificationKey,
      );

      _stopProofTimer();
      final elapsed = _elapsedLabel;

      final decodedPublic =
          jsonDecode(proveResult.publicSignals) as List<dynamic>;

      setState(() {
        _proofValid = proofValid;
        _publicSignals = const JsonEncoder.withIndent('  ').convert(decodedPublic);
        _proof = const JsonEncoder.withIndent('  ').convert(jsonDecode(proveResult.proof));
        _applySemanticResult(decodedPublic);
      });
      _log(proofValid
          ? '✓ 証明・検証 完了（$elapsed）'
          : '✗ 証明は生成できましたが検証に失敗しました（$elapsed）');
    } catch (error) {
      _stopProofTimer();
      final elapsed = _elapsedLabel;
      setState(() {
        _verdictTitle = '実行失敗';
        _verdictSummary = '証明生成フローの途中で停止しました。端末内の witness / zkey / verification key を確認してください。';
        _privacySummary = '失敗時も座標の生データは外部送信していません。';
      });
      _log('✗ エラー（$elapsed）: $error');
    } finally {
      setState(() {
        _isBusy = false;
      });
    }
  }

  /// QFE 方式: 地上気圧 P0 からの相対高度を返す。
  /// P0 未設定時は 0.0 を返す（地上扱い）。
  double _baroToRelativeAlt(double pressureHpa) {
    final p0 = _groundPressureHpa;
    if (p0 == null || p0 <= 0) return 0.0;
    return 44330.0 * (1.0 - math.pow(pressureHpa / p0, 1.0 / 5.255));
  }

  void _startBarometerStream() {
    _barometerSubscription = barometerEventStream().listen(
      (BarometerEvent event) {
        if (!mounted) return;
        // 初回読み取り時に地上気圧を記録（QFE 基準点）
        _groundPressureHpa ??= event.pressure;
        final altitude = _baroToRelativeAlt(event.pressure);
        setState(() {
          _currentAltitudeMeters = altitude;
        });
      },
      onError: (_) {
        if (!mounted) return;
        setState(() {
          _currentAltitudeMeters = null;
        });
      },
    );
  }

  Future<void> _fillTargetFromDeviceSensors({bool silent = false}) async {
    if (!silent) {
      setState(() {
        _status = '端末のGPSと気圧センサーを読み取っています...';
      });
    }

    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        throw Exception('位置情報サービスが無効です。端末の位置情報を有効にしてください。');
      }

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }

      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        throw Exception('位置情報権限がありません。権限を許可してください。');
      }

      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.best,
        ),
      );

      double? altitudeMeters = _currentAltitudeMeters;
      if (altitudeMeters == null) {
        final event = await barometerEventStream().first.timeout(
          const Duration(seconds: 3),
        );
        _groundPressureHpa ??= event.pressure;
        altitudeMeters = _baroToRelativeAlt(event.pressure);
        _currentAltitudeMeters = altitudeMeters;
      }

      final altitudeMetersValue = altitudeMeters;
      if (!mounted) return;

      setState(() {
        _targetLatController.text = position.latitude.toStringAsFixed(7);
        _targetLonController.text = position.longitude.toStringAsFixed(7);
        _targetAltController.text = altitudeMetersValue.toStringAsFixed(1);
        _targetTimeController.text =
            (DateTime.now().millisecondsSinceEpoch ~/ 1000).toString();
      });
      if (!silent) _log('第三者側検知ログを端末実測で更新しました。GPS と気圧センサーを使用しています。');
    } catch (error) {
      if (!mounted) return;
      if (!silent) _log('端末センサー取得エラー: $error');
    }
  }


  Future<void> _analyzeVideoEvidence() async {
    final evidence = _videoEvidence;
    if (evidence == null) {
      _log('動画がまだありません。先に録画してください。');
      return;
    }
    setState(() { _videoDetectionSummary = '動画フレームの UAV 候補を解析しています...'; });

    try {
      final frames = await _extractVideoFrames(evidence.path);
      _log('フレーム抽出: ${frames.length}枚');

      final List<VideoDetectionDetail> details;
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
          if (_looksLikeUavLabel(label.split(':').first.toLowerCase())) detected = true;
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
    }
  }

  Future<List<SampledVideoFrame>> _extractVideoFrames(String videoPath) async {
    final tempDir = await getTemporaryDirectory();
    final frames = <SampledVideoFrame>[];
    for (final positionMs in [0, 1000, 2500]) {
      final thumbnailPath = await video_thumbnail.VideoThumbnail.thumbnailFile(
        video: videoPath,
        thumbnailPath: tempDir.path,
        imageFormat: video_thumbnail.ImageFormat.JPEG,
        timeMs: positionMs,
        quality: 85,
      );
      if (thumbnailPath != null) {
        frames.add(SampledVideoFrame(path: thumbnailPath, timeMs: positionMs));
      }
    }
    return frames;
  }

  Future<List<VideoDetectionDetail>> _analyzeFramesWithMlKit(
    List<SampledVideoFrame> frames,
  ) async {
    final details = <VideoDetectionDetail>[];
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
            .map(
              (label) =>
                  '${label.label}:${label.confidence.toStringAsFixed(2)}',
            )
            .toList();
        details.add(
          VideoDetectionDetail(
            timeMs: frame.timeMs,
            backend: 'ML Kit',
            labels: labels,
            previewPath: previewPath,
            regions: regions,
          ),
        );
      }
    } finally {
      await labeler.close();
      await objectDetector.close();
    }

    return details;
  }

  Future<List<VideoDetectedRegion>> _buildMlKitRegions({
    required SampledVideoFrame frame,
    required List<DetectedObject> objects,
    required ImageLabeler labeler,
  }) async {
    final bytes = await File(frame.path).readAsBytes();
    final decoded = img.decodeImage(bytes);
    if (decoded == null) {
      return const [];
    }

    final tempDir = await getTemporaryDirectory();
    final regions = <VideoDetectedRegion>[];

    for (var index = 0; index < objects.length; index++) {
      final rect = objects[index].boundingBox;
      final left = rect.left.clamp(0, decoded.width - 1).toInt();
      final top = rect.top.clamp(0, decoded.height - 1).toInt();
      final right = rect.right
          .clamp(left + 1, decoded.width.toDouble())
          .toInt();
      final bottom = rect.bottom
          .clamp(top + 1, decoded.height.toDouble())
          .toInt();
      final width = right - left;
      final height = bottom - top;
      if (width < 8 || height < 8) {
        continue;
      }

      final crop = img.copyCrop(
        decoded,
        x: left,
        y: top,
        width: width,
        height: height,
      );
      final cropPath = '${tempDir.path}/mlkit_crop_${frame.timeMs}_$index.jpg';
      await File(cropPath).writeAsBytes(img.encodeJpg(crop, quality: 90));

      final cropLabels = await labeler.processImage(
        InputImage.fromFilePath(cropPath),
      );
      final cropTop = cropLabels.isNotEmpty ? cropLabels.first : null;
      final detectorTop = objects[index].labels.isNotEmpty
          ? objects[index].labels.first
          : null;
      final regionLabel = cropTop?.label ?? detectorTop?.text ?? 'object';
      final regionConfidence =
          cropTop?.confidence ?? detectorTop?.confidence ?? 0.0;

      regions.add(
        VideoDetectedRegion(
          left: left.toDouble(),
          top: top.toDouble(),
          right: right.toDouble(),
          bottom: bottom.toDouble(),
          label: regionLabel,
          confidence: regionConfidence,
        ),
      );
    }

    return regions;
  }

  Future<String?> _buildMlKitPreview({
    required SampledVideoFrame frame,
    required List<VideoDetectedRegion> regions,
  }) async {
    if (regions.isEmpty) {
      return null;
    }

    final bytes = await File(frame.path).readAsBytes();
    final decoded = img.decodeImage(bytes);
    if (decoded == null) {
      return null;
    }

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

  Future<List<VideoDetectionDetail>> _analyzeFramesWithYolo(
    List<SampledVideoFrame> frames,
  ) async {
    final detector = _yoloDetector;
    if (detector == null) return const [];

    final tempDir = await getTemporaryDirectory();
    final details = <VideoDetectionDetail>[];

    for (final frame in frames) {
      final detections = await detector.detectImageFile(frame.path);
      final regions = detections.map((d) => VideoDetectedRegion(
        left: d.left, top: d.top, right: d.right, bottom: d.bottom,
        label: d.label, confidence: d.score,
      )).toList();

      // bbox を描いたプレビュー画像を生成
      String? previewPath;
      if (regions.isNotEmpty) {
        try {
          final bytes = await File(frame.path).readAsBytes();
          final decoded = img.decodeImage(bytes);
          if (decoded != null) {
            for (final r in regions) {
              // バウンディングボックス
              img.drawRect(decoded,
                x1: r.left.toInt(), y1: r.top.toInt(),
                x2: r.right.toInt(), y2: r.bottom.toInt(),
                color: img.ColorRgb8(48, 209, 88), thickness: 4);
              // ラベル背景
              img.fillRect(decoded,
                x1: r.left.toInt(), y1: (r.top - 22).toInt().clamp(0, decoded.height),
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

      details.add(VideoDetectionDetail(
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
    ];
    return keywords.any(label.contains);
  }

  Future<void> _fillDroneFromBle() async {
    await _restartBleScan();
  }

  Future<void> _receiveDroneAndCaptureVideo() async {
    if (_droneInputMode == DroneInputMode.ble && _lastDroneTelemetry == null) {
      await _fillDroneFromBle();
      if (!mounted || _lastDroneTelemetry == null) {
        return;
      }
    }

    if (!_hasDroneInputsReady()) {
      setState(() {
        _status =
            'ドローン側ログの Latitude / Longitude / Altitude / Unix Time を入力してください。';
      });
      return;
    }

    await _fillTargetFromDeviceSensors();
    if (!mounted || _status.startsWith('端末センサー取得エラー:')) {
      return;
    }
    await _startVideoRecording();
  }

  Future<void> _runProofFromVideoEvidence() async {
    if (!_hasDroneInputsReady()) {
      _log(_droneInputMode == DroneInputMode.ble
          ? '証明前に BLE または WiFi からドローン側ログを受信してください。'
          : '証明前にドローン側ログを手入力してください。');
      return;
    }
    if (_videoEvidence == null) {
      _log('先に動画を録画してください。');
      return;
    }
    // 検知成否に関わらず証明を実行する（データは常に収集済み）
    await _runProofFlow();
  }

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

  ButtonStyle _primaryActionStyle([Color color = const Color(0xFF0B6E69)]) {
    return FilledButton.styleFrom(
      backgroundColor: color,
      foregroundColor: Colors.white,
      padding: const EdgeInsets.symmetric(vertical: 15, horizontal: 18),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    );
  }

  Widget _buildNumberField(String label, TextEditingController controller) {
    return TextField(
      controller: controller,
      keyboardType: const TextInputType.numberWithOptions(
        decimal: true,
        signed: true,
      ),
      decoration: InputDecoration(
        labelText: label,
        filled: true,
        fillColor: const Color(0xFFF8F7F1),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: Color(0xFFD9D6C8)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: Color(0xFFD9D6C8)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: Color(0xFF0B6E69), width: 1.5),
        ),
      ),
    );
  }

  Widget _buildMetricTile(String label, String value, String helper) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFFF5F8F4),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0xFFE0E7DF)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: Color(0xFF4E6762),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              value,
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: Color(0xFF12312E),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              helper,
              style: const TextStyle(fontSize: 11, color: Color(0xFF4E6762)),
            ),
          ],
        ),
      ),
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

  // ── 新UI: 2タブ設計 ──────────────────────────────────────────

  Widget _buildStatusRow(String label, bool ready, {String value = ''}) {
    return Row(
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: ready ? const Color(0xFF1BAA6A) : const Color(0xFFCCC9BE),
          ),
        ),
        const SizedBox(width: 8),
        Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: ready ? const Color(0xFF12312E) : const Color(0xFF8B8B82),
          ),
        ),
        if (value.isNotEmpty) ...[
          const Spacer(),
          Text(
            value,
            style: const TextStyle(
              fontSize: 12,
              fontFamily: 'monospace',
              color: Color(0xFF4E6762),
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildSection({
    required IconData icon,
    required String title,
    required Color accent,
    required List<Widget> children,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: _surfaceDecoration(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: accent, size: 20),
              ),
              const SizedBox(width: 10),
              Text(
                title,
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 16,
                  color: Color(0xFF1D2C2A),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          ...children,
        ],
      ),
    );
  }

  Widget _buildMainTab(double approxDistance, int approxTimeDelta) {
    final droneReady = _hasDroneInputsReady();
    final locationReady = _hasTargetInputsReady;
    final videoReady = _videoEvidence != null;
    final provenOnce = _verdictTitle != '未実行';
    final canProve = droneReady && locationReady && !_isBusy;

    final drone = _lastDroneTelemetry;
    final topPad = MediaQuery.of(context).padding.top;
    final bottomPad = MediaQuery.of(context).padding.bottom;

    // 現在のステップ (0-3)
    final step = provenOnce ? 3 : (videoReady ? 2 : (droneReady && locationReady ? 1 : 0));

    // 次のアクションヒント
    final String nextHint;
    if (_isBusy) {
      nextHint = 'ZK 証明を生成しています... $_elapsedLabel';
    } else if (_isCapturing) {
      nextHint = 'YOLO でフレームを解析しています...';
    } else if (_isRecording) {
      final secs = _recordingElapsed.inSeconds;
      nextHint = '録画中 ${secs}s — ドローンを画角に捉えたら停止してください';
    } else if (!droneReady) {
      nextHint = '① BLE / WiFi でドローンの Remote ID を受信してください';
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
        // ── カメラプレビュー（全画面）+ ライブ bbox オーバーレイ ──
        Positioned.fill(
          child: _cameraReady && _cameraController != null
              ? LayoutBuilder(builder: (context, constraints) {
                  return CustomPaint(
                    foregroundPainter: _liveDetections.isNotEmpty && _previewSize != null
                        ? _BboxPainter(
                            detections: _liveDetections,
                            previewSize: _previewSize!,
                            screenSize: Size(constraints.maxWidth, constraints.maxHeight),
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

        // ── 上部: アプリ名 + ステップインジケーター ──
        Positioned(
          top: 0, left: 0, right: 0,
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
                // ── ステップバー ──
                Row(
                  children: [
                    _buildStepDot(0, step, Icons.sensors_rounded, 'BLE/WiFi'),
                    _buildStepLine(step >= 1),
                    _buildStepDot(1, step, Icons.gps_fixed_rounded, 'GPS'),
                    _buildStepLine(step >= 2),
                    _buildStepDot(2, step, Icons.videocam_rounded, '録画'),
                    _buildStepLine(step >= 3),
                    _buildStepDot(3, step, Icons.verified_rounded, '証明'),
                  ],
                ),
              ],
            ),
          ),
        ),

        // ── 録画中 / 解析中: 上端バー ──
        if (_isRecording || _isCapturing)
          Positioned(
            top: 0, left: 0, right: 0,
            child: LinearProgressIndicator(
              value: null,
              backgroundColor: Colors.white24,
              color: _isRecording ? const Color(0xFFFF3B30) : const Color(0xFFFF9500),
              minHeight: 3,
            ),
          ),

        // ── 下部オーバーレイ ──
        Positioned(
          bottom: 0, left: 0, right: 0,
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
                // ── データカード行 ──
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
                            : (_wifiOdidSeen
                                ? 'BLE / WiFi 受信中...'
                                : 'BLE / WiFi スキャン中...'),
                        count: _droneHistory.length,
                        sourceBadge: drone != null ? _lastDroneSource : null,
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

                // ── 距離・時刻チップ ──
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

                // ── 次のアクションヒント ──
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    nextHint,
                    style: const TextStyle(
                      color: Colors.white70,
                      fontSize: 12,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),

                const SizedBox(height: 12),

                // ── ライブ検知バッジ（録画前のみ）──
                if (_liveDetections.isNotEmpty && !_isRecording && !_isCapturing) ...[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0xFF30D158).withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: const Color(0xFF30D158).withValues(alpha: 0.6)),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.airplanemode_active_rounded,
                                color: Color(0xFF30D158), size: 13),
                            const SizedBox(width: 4),
                            Text(
                              'UAV をプレビューで検知中',
                              style: const TextStyle(
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

                // ── 録画コントロール ──
                if (_isCapturing) ...[
                  // 解析中
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
                          width: 18, height: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Color(0xFFFF9500)),
                        ),
                        SizedBox(width: 10),
                        Text('フレームを解析しています...',
                            style: TextStyle(color: Color(0xFFFF9500),
                                fontWeight: FontWeight.w700, fontSize: 15)),
                      ],
                    ),
                  ),
                ] else if (_isRecording) ...[
                  // 録画中: タイマー + 停止ボタン
                  Row(
                    children: [
                      // タイマー表示
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFF3B30).withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: const Color(0xFFFF3B30).withValues(alpha: 0.5)),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 8, height: 8,
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
                      // 録画停止ボタン
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: _stopVideoRecordingAndAnalyze,
                          icon: const Icon(Icons.stop_rounded, size: 20),
                          label: const Text('録画停止',
                              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
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
                  // 録画済み: 結果表示 + 再録画
                  Row(
                    children: [
                      Expanded(
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
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
                          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 14),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(18)),
                        ),
                      ),
                    ],
                  ),
                ] else ...[
                  // 録画前: 録画開始ボタン（全幅）
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: (_cameraReady && !_isBusy) ? _startVideoRecording : null,
                      icon: const Icon(Icons.videocam_rounded, size: 22),
                      label: const Text('録画開始',
                          style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
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

                // ── ZK 証明ボタン（全幅）──
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
                                width: 18, height: 18,
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
                                color: canProve ? Colors.black87 : Colors.white24,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                canProve ? 'ZK 証明を実行' : '準備中...',
                                style: TextStyle(
                                  color: canProve ? Colors.black87 : Colors.white24,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 16,
                                ),
                              ),
                            ],
                          ),
                  ),
                ),

                // ── 証明結果カード ──
                if (provenOnce) ...[
                  const SizedBox(height: 10),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
                    decoration: BoxDecoration(
                      color: _proofValid
                          ? const Color(0xFF30D158).withValues(alpha: 0.15)
                          : Colors.red.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: _proofValid
                            ? const Color(0xFF30D158)
                            : Colors.red,
                      ),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          _proofValid
                              ? Icons.verified_rounded
                              : Icons.cancel_rounded,
                          color: _proofValid
                              ? const Color(0xFF30D158)
                              : Colors.red,
                          size: 20,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            _verdictTitle,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                            ),
                          ),
                        ),
                        if (_proofElapsed != null)
                          Text(
                            _elapsedLabel,
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

  Widget _buildStepDot(int index, int currentStep, IconData icon, String label) {
    final done = currentStep > index;
    final active = currentStep == index;
    final color = done
        ? const Color(0xFF30D158)
        : (active ? Colors.white : Colors.white30);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 28, height: 28,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: done
                ? const Color(0xFF30D158).withValues(alpha: 0.25)
                : (active ? Colors.white.withValues(alpha: 0.15) : Colors.transparent),
            border: Border.all(color: color, width: done ? 0 : 1.5),
          ),
          child: Icon(
            done ? Icons.check_rounded : icon,
            size: 14, color: color,
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
    String? sourceBadge,
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
              Icon(icon, size: 14,
                  color: ready ? const Color(0xFF30D158) : Colors.white54),
              const SizedBox(width: 4),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  softWrap: false,
                  style: TextStyle(
                    color: ready ? const Color(0xFF30D158) : Colors.white54,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              if (sourceBadge != null) ...[
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                  decoration: BoxDecoration(
                    color: (sourceBadge == 'WiFi'
                            ? const Color(0xFF0A84FF)
                            : const Color(0xFF5E5CE6))
                        .withValues(alpha: 0.25),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: (sourceBadge == 'WiFi'
                              ? const Color(0xFF0A84FF)
                              : const Color(0xFF5E5CE6))
                          .withValues(alpha: 0.8),
                      width: 0.8,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        sourceBadge == 'WiFi'
                            ? Icons.wifi_rounded
                            : Icons.bluetooth_rounded,
                        size: 10,
                        color: sourceBadge == 'WiFi'
                            ? const Color(0xFF6AB7FF)
                            : const Color(0xFF9D9BFF),
                      ),
                      const SizedBox(width: 3),
                      Text(
                        sourceBadge,
                        style: TextStyle(
                          color: sourceBadge == 'WiFi'
                              ? const Color(0xFF6AB7FF)
                              : const Color(0xFF9D9BFF),
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              if (count > 0) ...[
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 5, vertical: 1),
                  decoration: BoxDecoration(
                    color: Colors.white12,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '$count件',
                    style: const TextStyle(
                        color: Colors.white54, fontSize: 10),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 4),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              line1,
              maxLines: 1,
              softWrap: false,
              style: const TextStyle(
                color: Colors.white,
                fontFamily: 'monospace',
                fontSize: 13,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              line2,
              maxLines: 1,
              softWrap: false,
              style: const TextStyle(
                color: Colors.white70,
                fontFamily: 'monospace',
                fontSize: 11,
              ),
            ),
          ),
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
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(width: 6),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 14,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDetailsTab() {
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
                // 回路セレクター（コンパクト版）
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
                        children: _circuitConfigs.map((config) {
                          final selected =
                              config.profile == _selectedCircuitProfile;
                          return ChoiceChip(
                            selected: selected,
                            label: Text(config.label),
                            onSelected: _isBusy
                                ? null
                                : (_) => setState(
                                      () => _selectedCircuitProfile =
                                          config.profile,
                                    ),
                          );
                        }).toList(),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        _selectedCircuitConfig.description,
                        style: const TextStyle(
                          fontSize: 12,
                          color: Color(0xFF5C6765),
                          height: 1.4,
                        ),
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
                        : _proofValid
                        ? Colors.green.shade50
                        : Colors.grey.shade100,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: _isBusy
                          ? Colors.blue.shade200
                          : _proofValid
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
                      if (_proofElapsed != null &&
                          _proofElapsed!.inMilliseconds > 0) ...[
                        const SizedBox(height: 4),
                        Text(
                          _isBusy
                              ? '経過: $_elapsedLabel'
                              : '処理時間: $_elapsedLabel',
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

                // 検知結果（動画録画後に表示）
                if (_videoEvidence != null) ...[
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(14),
                    decoration: _surfaceDecoration(color: const Color(0xFFF5F7F5)),
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
                        Text(
                          _videoDetectionSummary,
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF3A4A47),
                            height: 1.5,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          _detectionBackendStatus,
                          style: const TextStyle(
                            fontSize: 11,
                            color: Color(0xFF8A9A98),
                            height: 1.4,
                          ),
                        ),
                        // 検知フレーム画像（bbox 付き）
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
                            children: _videoDetectionLabels.map((label) => Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: const Color(0xFF0B6E69).withValues(alpha: 0.1),
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(
                                    color: const Color(0xFF0B6E69).withValues(alpha: 0.3)),
                              ),
                              child: Text(
                                label,
                                style: const TextStyle(
                                  fontSize: 11,
                                  color: Color(0xFF0B6E69),
                                  fontFamily: 'monospace',
                                ),
                              ),
                            )).toList(),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],

                // 判定要約・プライバシー説明（証明後のみ表示）
                if (_verdictTitle != '未実行') ...[
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(14),
                    decoration: _surfaceDecoration(
                      color: _proofValid
                          ? const Color(0xFFEEFBF3)
                          : const Color(0xFFFFF0EE),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              _proofValid ? Icons.verified_rounded : Icons.cancel_rounded,
                              size: 16,
                              color: _proofValid ? const Color(0xFF1A7F4B) : Colors.red.shade700,
                            ),
                            const SizedBox(width: 6),
                            Text(
                              _verdictTitle,
                              style: TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 14,
                                color: _proofValid ? const Color(0xFF1A7F4B) : Colors.red.shade700,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          _verdictSummary,
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF3A4A47),
                            height: 1.5,
                          ),
                        ),
                        const SizedBox(height: 10),
                        const Divider(height: 1, color: Color(0xFFDDD9CC)),
                        const SizedBox(height: 10),
                        Row(
                          children: const [
                            Icon(Icons.lock_outline_rounded, size: 13, color: Color(0xFF5C6765)),
                            SizedBox(width: 5),
                            Text(
                              'プライバシー',
                              style: TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 12,
                                color: Color(0xFF5C6765),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 5),
                        Text(
                          _privacySummary,
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF5C6765),
                            height: 1.5,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],

                const SizedBox(height: 12),
                _buildResultPanel(title: 'Witness Inputs', body: _inputJson),
                const SizedBox(height: 10),
                _buildResultPanel(
                    title: 'Public Signals', body: _publicSignals),
                const SizedBox(height: 10),
                _buildResultPanel(title: 'Proof JSON', body: _proof),
                const SizedBox(height: 20),
              ],
            ),
          ),
        ),
      ],
    );
  }

  // ── _BboxPainter は State クラスの外で定義（下記参照）──

  @override
  void dispose() {
    _proofTimer?.cancel();
    _recordingTimer?.cancel();
    _liveDetectionTimer?.cancel();
    _autoLocationTimer?.cancel();
    _bleRescanTimer?.cancel();
    _locationStream?.cancel();
    _bleScanSubscription?.cancel();
    _wifiScanSubscription?.cancel();
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
                      colors: [Color(0xFFE8F3EE), Color(0xFFF3F2EA), Color(0xFFF8F5EC)],
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
                  : _selectedTabIndex == 3
                      ? const BleRawScanPage()
                      : const WifiRawScanPage(),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedTabIndex,
        onDestinationSelected: (index) {
          setState(() {
            _selectedTabIndex = index;
          });
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
          NavigationDestination(
            icon: Icon(Icons.wifi_find_outlined),
            selectedIcon: Icon(Icons.wifi_find_rounded),
            label: 'WiFi Raw',
          ),
        ],
      ),
    );
  }

  Widget _buildLogTab() {
    return Container(
      color: const Color(0xFF0D1117),
      child: SafeArea(
        child: Column(
          children: [
            // ヘッダー
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Row(
                children: [
                  const Icon(Icons.terminal_rounded, color: Color(0xFF58A6FF), size: 18),
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
                  Text(
                    '${_logs.length} 件',
                    style: const TextStyle(color: Color(0xFF8B949E), fontSize: 12),
                  ),
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
            // ログリスト
            Expanded(
              child: _logs.isEmpty
                  ? const Center(
                      child: Text(
                        'ログがまだありません',
                        style: TextStyle(color: Color(0xFF484F58), fontSize: 13),
                      ),
                    )
                  : ListView.builder(
                      controller: _logScrollController,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      itemCount: _logs.length,
                      itemBuilder: (context, i) {
                        final line = _logs[i];
                        final isError = line.contains('エラー') || line.contains('✗');
                        final isSuccess = line.contains('✓') || line.contains('完了');
                        final isBle = line.contains('[BLE');
                        final isWifi = line.contains('[WiFi');
                        Color textColor = const Color(0xFFC9D1D9);
                        if (isError) textColor = const Color(0xFFF85149);
                        if (isSuccess) textColor = const Color(0xFF3FB950);
                        if (isBle) textColor = const Color(0xFF79C0FF);
                        if (isWifi) textColor = const Color(0xFF56D4DD);
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
}

// ── ライブ YOLO 検知バウンディングボックス描画 ──────────────────────────────
class _BboxPainter extends CustomPainter {
  const _BboxPainter({
    required this.detections,
    required this.previewSize,
    required this.screenSize,
  });

  final List<UavYoloDetection> detections;
  final Size previewSize;   // カメラ解像度（width × height、横向きでは縦横が入れ替わる）
  final Size screenSize;    // 描画領域サイズ

  @override
  void paint(Canvas canvas, Size size) {
    // プレビューをスクリーンにフィットさせる際の拡縮比
    final scaleX = screenSize.width  / previewSize.height;
    final scaleY = screenSize.height / previewSize.width;
    final scale  = scaleX < scaleY ? scaleX : scaleY;
    final offsetX = (screenSize.width  - previewSize.height * scale) / 2;
    final offsetY = (screenSize.height - previewSize.width  * scale) / 2;

    final boxPaint = Paint()
      ..color = const Color(0xFF30D158)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5;

    final bgPaint = Paint()..color = const Color(0xBB000000);

    for (final det in detections) {
      final left   = det.left   * scale + offsetX;
      final top    = det.top    * scale + offsetY;
      final right  = det.right  * scale + offsetX;
      final bottom = det.bottom * scale + offsetY;

      canvas.drawRect(Rect.fromLTRB(left, top, right, bottom), boxPaint);

      final label = '${det.label} ${(det.score * 100).toStringAsFixed(0)}%';
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
