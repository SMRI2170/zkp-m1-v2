import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/position_snapshot.dart';
import '../domain/safety_circuit.dart';
import '../domain/uav_telemetry.dart';
import '../services/zk_input_builder.dart';
import '../services/zk_service.dart';

enum ZkPhase { idle, witness, proving, verifying, done, error }

class ZkProofState {
  const ZkProofState({
    this.phase = ZkPhase.idle,
    this.proofValid = false,
    this.publicSignals,
    this.proof,
    this.inputJson,
    this.elapsed,
    this.errorMessage,
    this.verdictTitle = '未実行',
    this.verdictSummary = 'まだ証明は生成されていません。',
    this.privacySummary = '座標そのものは公開せず、真偽だけを共有します。',
  });

  final ZkPhase phase;
  final bool proofValid;
  final String? publicSignals;
  final String? proof;
  final String? inputJson;
  final Duration? elapsed;
  final String? errorMessage;
  final String verdictTitle;
  final String verdictSummary;
  final String privacySummary;

  bool get isBusy =>
      phase != ZkPhase.idle && phase != ZkPhase.done && phase != ZkPhase.error;

  ZkProofState copyWith({
    ZkPhase? phase,
    bool? proofValid,
    String? publicSignals,
    String? proof,
    String? inputJson,
    Duration? elapsed,
    String? errorMessage,
    String? verdictTitle,
    String? verdictSummary,
    String? privacySummary,
  }) =>
      ZkProofState(
        phase: phase ?? this.phase,
        proofValid: proofValid ?? this.proofValid,
        publicSignals: publicSignals ?? this.publicSignals,
        proof: proof ?? this.proof,
        inputJson: inputJson ?? this.inputJson,
        elapsed: elapsed ?? this.elapsed,
        errorMessage: errorMessage ?? this.errorMessage,
        verdictTitle: verdictTitle ?? this.verdictTitle,
        verdictSummary: verdictSummary ?? this.verdictSummary,
        privacySummary: privacySummary ?? this.privacySummary,
      );
}

final zkProofProvider =
    NotifierProvider<ZkProofNotifier, ZkProofState>(ZkProofNotifier.new);

class ZkProofNotifier extends Notifier<ZkProofState> {
  final _service = ZkService();
  final _inputBuilder = ZkInputBuilder();

  static const _timeLimitSeconds = 5;

  @override
  ZkProofState build() => const ZkProofState();

  Future<void> run({
    required SafetyCircuitProfile profile,
    required UavTelemetryPacket drone,
    required PositionSnapshot target,
    required bool uavDetected,
    required List<UavTelemetryPacket> droneHistory,
    required List<PositionSnapshot> locationHistory,
    String? videoPath,
    DateTime? videoRecordedAt,
    double detectionScore = 0.85,
    List<dynamic> videoDetectionDetails = const [],
    String detectionBackendLabel = 'ML Kit fallback',
  }) async {
    final startedAt = DateTime.now();
    final config = SafetyCircuitConfig.all.firstWhere((c) => c.profile == profile);

    state = const ZkProofState(phase: ZkPhase.witness);

    try {
      final inputs = _inputBuilder.build(
        profile: profile,
        drone: drone,
        target: target,
        uavDetected: uavDetected,
        droneHistory: droneHistory,
        locationHistory: locationHistory,
        videoPath: videoPath,
        videoRecordedAt: videoRecordedAt,
        detectionScore: detectionScore,
        videoDetectionDetails: videoDetectionDetails,
        detectionBackendLabel: detectionBackendLabel,
      );
      final inputsJson = const JsonEncoder.withIndent('  ').convert(inputs);

      state = state.copyWith(phase: ZkPhase.proving, inputJson: inputsJson);

      final result = await _service.prove(
        inputsJson: inputsJson,
        wcdAssetPath: config.wcdAssetPath,
        zkeyAssetPath: config.zkeyAssetPath,
        verificationKeyAssetPath: config.verificationKeyAssetPath,
      );

      final elapsed = DateTime.now().difference(startedAt);
      final decodedPublic = jsonDecode(result.publicSignals) as List<dynamic>;

      // プロファイル別の意味解釈
      final verdict = _applySemanticResult(
        profile: profile,
        publicSignals: decodedPublic,
        droneLat: drone.latitude,
        droneLon: drone.longitude,
        droneAlt: drone.altitudeMeters,
        droneTime: drone.unixTimeSec,
        targetLat: target.lat,
        targetLon: target.lon,
        targetAlt: target.alt,
        targetTime: target.unixTimeSec,
        proofValid: result.valid,
      );

      state = ZkProofState(
        phase: ZkPhase.done,
        proofValid: result.valid,
        publicSignals: const JsonEncoder.withIndent('  ').convert(decodedPublic),
        proof: const JsonEncoder.withIndent('  ')
            .convert(jsonDecode(result.proof)),
        inputJson: inputsJson,
        elapsed: elapsed,
        verdictTitle: verdict.$1,
        verdictSummary: verdict.$2,
        privacySummary: verdict.$3,
      );
    } catch (e) {
      state = ZkProofState(
        phase: ZkPhase.error,
        elapsed: DateTime.now().difference(startedAt),
        errorMessage: e.toString(),
        verdictTitle: '実行失敗',
        verdictSummary:
            '証明生成フローの途中で停止しました。端末内の witness / zkey / verification key を確認してください。',
        privacySummary: '失敗時も座標の生データは外部送信していません。',
      );
    }
  }

  void reset() => state = const ZkProofState();

  /// public signals を解釈してタイトル・要約・プライバシー説明を返す。
  (String title, String summary, String privacy) _applySemanticResult({
    required SafetyCircuitProfile profile,
    required List<dynamic> publicSignals,
    required double droneLat,
    required double droneLon,
    required double droneAlt,
    required int droneTime,
    required double targetLat,
    required double targetLon,
    required double targetAlt,
    required int targetTime,
    required bool proofValid,
  }) {
    final within30 =
        publicSignals.isNotEmpty && publicSignals[0].toString() == '1';
    final distanceOk =
        publicSignals.length > 1 && publicSignals[1].toString() == '1';
    final timeOk =
        publicSignals.length > 2 && publicSignals[2].toString() == '1';

    // 近似距離・時刻差を計算
    final latDiffE7 = (targetLat - droneLat).abs() * 10000000;
    final lonDiffE7 = (targetLon - droneLon).abs() * 10000000;
    final altDiffCm = (targetAlt - droneAlt).abs() * 100;
    const latCm = 11132000.0;
    const lonCm = 9128800.0;
    const den = 10000000.0;
    final approxDistance = math.sqrt(
      ((latDiffE7 * latCm / den) / 100) * ((latDiffE7 * latCm / den) / 100) +
      ((lonDiffE7 * lonCm / den) / 100) * ((lonDiffE7 * lonCm / den) / 100) +
      (altDiffCm / 100) * (altDiffCm / 100),
    );
    final approxTimeDelta = (targetTime - droneTime).abs();

    String title = within30 ? '接近あり: 要注意' : '安全距離を維持';
    String summary;
    String privacy;

    if (within30) {
      summary =
          'この証明では、対象者とドローンが30m以内に入り、かつ時刻差も$_timeLimitSeconds秒以内でした。苦情対応や事故検証に使える結果です。';
    } else if (!distanceOk && timeOk) {
      summary =
          '時刻は揃っていますが、推定距離は ${approxDistance.toStringAsFixed(1)}m で30mを超えています。住民・観客側にとって安全側の結果です。';
    } else if (distanceOk && !timeOk) {
      summary =
          '空間的には近くても、検知時刻との差が ${approxTimeDelta}s あり、同一瞬間の接近とは見なされません。';
    } else {
      summary =
          '距離も時刻も閾値外でした。第三者の位置や飛行ルートを公開せず、安全側の判定だけを共有できます。';
    }

    privacy =
        '公開信号は within30=$within30, distance_ok=$distanceOk, time_ok=$timeOk のみで、生の位置座標や飛行ルートは外へ出しません。';

    // Commitment プロファイルの追加解釈
    if (profile == SafetyCircuitProfile.detectionCommitment &&
        publicSignals.length >= 10) {
      final detectionOk = publicSignals[3].toString() == '1';
      final withinAndDetected = publicSignals[6].toString() == '1';
      final droneCommit = publicSignals[7].toString();
      final targetCommit = publicSignals[8].toString();
      final frameBinding = publicSignals[9].toString();

      if (withinAndDetected) {
        title = '接近あり + UAV 検知: 要注意';
        summary = '30m 以内の接近と UAV 検知の両方が成立しています。'
            'Poseidon コミットメント付きの証明として記録できます。';
      } else if (within30 && !detectionOk) {
        summary += '\n(距離は 30m 以内ですが、UAV 検知スコアが基準を下回っています)';
      }

      final ds = droneCommit.length > 8 ? '${droneCommit.substring(0, 8)}...' : droneCommit;
      final ts = targetCommit.length > 8 ? '${targetCommit.substring(0, 8)}...' : targetCommit;
      final fs = frameBinding.length > 8 ? '${frameBinding.substring(0, 8)}...' : frameBinding;
      privacy =
          'Poseidon ハッシュにより、座標の実値は非公開のまま証明に結びついています。\n'
          'drone:   $ds\n'
          'target:  $ts\n'
          'frame:   $fs\n'
          '(完全な値は Public Signals パネルに表示されます)';
    }

    // TimeSeries プロファイルの解釈
    if (profile == SafetyCircuitProfile.timeSeries &&
        publicSignals.length >= 21) {
      final anyWithin30 = publicSignals[20].toString() == '1';
      final hitCount =
          List.generate(20, (i) => publicSignals[i].toString() == '1' ? 1 : 0)
              .fold(0, (a, b) => a + b);
      title = anyWithin30 ? '接近あり: 要注意 (時系列)' : '安全距離を維持 (時系列)';
      summary = anyWithin30
          ? '$hitCount / 20 ペアで 30m 以内への接近が確認されました。録画中のデータが証拠として記録されます。'
          : '20 ペアすべてで 30m 以内への接近はありませんでした。録画期間中は安全距離を維持しています。';
      privacy =
          'any_within30=$anyWithin30 のみが公開されます。生の GPS 座標・飛行ルートは外へ出しません。';
    }

    return (title, summary, privacy);
  }
}
