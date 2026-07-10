import 'dart:convert';

import '../core/geo_math.dart';
import '../core/poseidon.dart';
import '../domain/position_snapshot.dart';
import '../domain/safety_circuit.dart';
import '../domain/uav_telemetry.dart';

/// ZK 証明の入力 JSON を構築するサービス。
/// プロファイル別の input ペイロードを組み立てる。
class ZkInputBuilder {
  /// プロファイルに応じた入力ペイロードを構築する。
  Map<String, dynamic> build({
    required SafetyCircuitProfile profile,
    required UavTelemetryPacket drone,
    required PositionSnapshot target,
    required bool uavDetected,
    required List<UavTelemetryPacket> droneHistory,
    required List<PositionSnapshot> locationHistory,
    String? videoPath,
    DateTime? videoRecordedAt,
    double detectionScore = 0.85,
    List<double> features = const [0, 0, 0, 0],
    List<dynamic> videoDetectionDetails = const [],
    String detectionBackendLabel = 'ML Kit fallback',
  }) {
    if (profile == SafetyCircuitProfile.timeSeries) {
      return _buildTimeSeriesPayload(droneHistory, locationHistory);
    }

    final payload = _buildBasePayload(drone, target);
    final targetTimeSec = target.unixTimeSec;

    switch (profile) {
      case SafetyCircuitProfile.base:
        break;

      case SafetyCircuitProfile.detectionFlag:
        final scoreBps = _estimateDetectionScoreBps(
          uavDetected: uavDetected,
          videoDetectionDetails: videoDetectionDetails,
        );
        payload.addAll({
          'uav_detected': uavDetected ? '1' : '0',
          'detection_score_bps': scoreBps.toString(),
          'detection_class_id': '1',
        });
        break;

      case SafetyCircuitProfile.detectionCommitment:
        final frameTimeSec = videoRecordedAt != null
            ? (videoRecordedAt.millisecondsSinceEpoch ~/ 1000)
            : targetTimeSec;
        final commitmentSeed = videoPath == null || videoRecordedAt == null
            ? 'no-evidence'
            : '$videoPath|${videoRecordedAt.toIso8601String()}';

        // Poseidon ハッシュで commitment を生成
        final seedBytes = utf8.encode(commitmentSeed);
        final seedBigInt = seedBytes.fold<BigInt>(
          BigInt.zero,
          (acc, b) => (acc * BigInt.from(256) + BigInt.from(b)) %
              BigInt.parse(
                '21888242871839275222246405745257275088548364400416034343698204186575808495617',
              ),
        );
        final commitment = poseidon2(
          BigInt.from(frameTimeSec),
          seedBigInt,
        );
        final (hi, lo) = splitHiLo(commitment);

        final scoreBps = _estimateDetectionScoreBps(
          uavDetected: uavDetected,
          videoDetectionDetails: videoDetectionDetails,
        );
        payload.addAll({
          'uav_detected': uavDetected ? '1' : '0',
          'detection_score_bps': scoreBps.toString(),
          'detection_class_id': '1',
          'frame_time_sec': frameTimeSec.toString(),
          'frame_commitment_hi': hi.toString(),
          'frame_commitment_lo': lo.toString(),
        });
        break;

      case SafetyCircuitProfile.featureClassifier:
        final f0 = uavDetected ? 60 : 0;
        final f1 = features.isNotEmpty ? (features[0] * 20).round() : 20;
        final f2 = features.length > 1 ? (features[1] * 10).round() : 10;
        final f3 = detectionBackendLabel.contains('YOLO') ? 30 : 12;
        payload.addAll({
          'frame_time_sec': targetTimeSec.toString(),
          'features': [
            f0.toString(),
            f1.toString(),
            f2.toString(),
            f3.toString(),
          ],
        });
        break;

      case SafetyCircuitProfile.timeSeries:
        // handled by early return
        break;
    }

    return payload;
  }

  Map<String, dynamic> _buildBasePayload(
    UavTelemetryPacket drone,
    PositionSnapshot target,
  ) {
    return <String, String>{
      'drone_lat_e7_norm': normalizeLatitude(drone.latitude).toString(),
      'drone_lon_e7_norm': normalizeLongitude(drone.longitude).toString(),
      'drone_alt_cm': metersToCentimeters(drone.altitudeMeters).toString(),
      'drone_time_sec': drone.unixTimeSec.toString(),
      'target_lat_e7_norm': normalizeLatitude(target.lat).toString(),
      'target_lon_e7_norm': normalizeLongitude(target.lon).toString(),
      'target_alt_cm': metersToCentimeters(target.alt).toString(),
      'target_time_sec': target.unixTimeSec.toString(),
    };
  }

  Map<String, dynamic> _buildTimeSeriesPayload(
    List<UavTelemetryPacket> droneHistory,
    List<PositionSnapshot> locationHistory,
  ) {
    const n = 20;

    final droneEntries = droneHistory.take(n).toList();
    final lastDrone = droneEntries.isNotEmpty ? droneEntries.last : null;
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

    final locationEntries = locationHistory.take(n).toList();
    final lastLoc = locationEntries.isNotEmpty ? locationEntries.last : null;
    while (locationEntries.length < n) {
      locationEntries.add(
        lastLoc ??
            const PositionSnapshot(lat: 0, lon: 0, alt: 0, unixTimeSec: 0),
      );
    }

    String normLat(double lat) => normalizeLatitude(lat).toString();
    String normLon(double lon) => normalizeLongitude(lon).toString();
    String altCm(double alt) => metersToCentimeters(alt).toString();

    return {
      'drone_lat_e7_norm': droneEntries.map((d) => normLat(d.latitude)).toList(),
      'drone_lon_e7_norm': droneEntries.map((d) => normLon(d.longitude)).toList(),
      'drone_alt_cm': droneEntries.map((d) => altCm(d.altitudeMeters)).toList(),
      'drone_time_sec': droneEntries.map((d) => d.unixTimeSec.toString()).toList(),
      'target_lat_e7_norm': locationEntries.map((l) => normLat(l.lat)).toList(),
      'target_lon_e7_norm': locationEntries.map((l) => normLon(l.lon)).toList(),
      'target_alt_cm': locationEntries.map((l) => altCm(l.alt)).toList(),
      'target_time_sec': locationEntries.map((l) => l.unixTimeSec.toString()).toList(),
    };
  }

  int _estimateDetectionScoreBps({
    required bool uavDetected,
    required List<dynamic> videoDetectionDetails,
  }) {
    if (!uavDetected) return 0;

    // videoDetectionDetails に Map<String, dynamic> の confidence/score があれば使う
    double bestScore = 0.0;
    for (final detail in videoDetectionDetails) {
      if (detail is Map) {
        final score = (detail['score'] ?? detail['confidence']);
        if (score is num && score.toDouble() > bestScore) {
          bestScore = score.toDouble();
        }
      }
    }

    // 実スコアが取れた場合はそれを使い、取れない場合は保守的に 50% とする
    final score = bestScore > 0.0 ? bestScore : 0.50;
    return (score * 10000).round().clamp(0, 10000);
  }
}
