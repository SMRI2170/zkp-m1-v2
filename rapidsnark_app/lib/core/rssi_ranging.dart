import 'dart:math' as math;

/// RSSI → 距離 の推定と、RemoteID 放送位置との整合チェック。
///
/// ドローン側を一切改造せず、地上（端末）側の受信強度だけで
/// 「放送した位置」と「実測レンジ」が矛盾しないかを判定する土台。
///
/// モデル（log-distance path loss）:
///   RSSI(d) = A - 10 * n * log10(d)     ⇔   d = 10 ^ ((A - RSSI) / (10 n))
///
/// RSSI 誤差は距離では「乗法的（相対 %）」に効くため、許容は固定 m ではなく
/// 相対帯 [est/f, est*f]（f = 10^(kσ/10n)）で判定する。
///
/// パラメータ A / n / sigmaDb は暫定値。実機 DJI で (rssi, 真の距離) を収集し
/// scripts/rssi/rssi_ranging.py で fit した値に置き換えること。
class RssiRangingModel {
  final double a; // 1m での RSSI [dBm]
  final double n; // path-loss 指数（自由空間 2.0 / 市街地 2.5〜4）
  final double sigmaDb; // フィット残差の標準偏差 [dB]

  const RssiRangingModel({
    this.a = -40.0,
    this.n = 2.5,
    this.sigmaDb = 3.5,
  });

  /// RSSI[dBm] から推定距離[m]。
  double distanceMeters(int rssi) =>
      math.pow(10, (a - rssi) / (10.0 * n)).toDouble();

  /// 複数 RSSI サンプルの中央値から距離推定（マルチパス外れ値にロバスト）。
  double distanceFromSamples(List<int> rssiSamples) =>
      distanceMeters(_medianRssi(rssiSamples));

  static int _medianRssi(List<int> xs) {
    final s = List<int>.from(xs)..sort();
    final mid = s.length ~/ 2;
    return s.length.isOdd ? s[mid] : ((s[mid - 1] + s[mid]) / 2).round();
  }

  /// 距離推定の相対誤差係数（±kσ）。est を [est/f, est*f] にする f。
  double relBand({double k = 2.0}) =>
      math.pow(10, k * sigmaDb / (10.0 * n)).toDouble();
}

enum RssiVerdict { consistent, suspicious, unknown }

class RssiConsistencyResult {
  final RssiVerdict verdict;
  final double estimatedRangeM;
  final double claimedDistanceM;
  final double lowerM;
  final double upperM;

  const RssiConsistencyResult({
    required this.verdict,
    required this.estimatedRangeM,
    required this.claimedDistanceM,
    required this.lowerM,
    required this.upperM,
  });

  /// consistency 回路 (remoteid_consistency.circom) に渡す measured_range_cm。
  int get measuredRangeCm => (estimatedRangeM * 100).round();

  String get label {
    switch (verdict) {
      case RssiVerdict.consistent:
        return '整合';
      case RssiVerdict.suspicious:
        return 'なりすまし疑い';
      case RssiVerdict.unknown:
        return '判定不可';
    }
  }
}

/// 放送位置から計算した距離 [m] と RSSI 実測を突き合わせる。
RssiConsistencyResult checkRssiConsistency({
  required double claimedDistanceM,
  required int rssi,
  RssiRangingModel model = const RssiRangingModel(),
}) {
  if (rssi == 0) {
    return const RssiConsistencyResult(
      verdict: RssiVerdict.unknown,
      estimatedRangeM: 0,
      claimedDistanceM: 0,
      lowerM: 0,
      upperM: 0,
    );
  }
  return _resultFor(model.distanceMeters(rssi), claimedDistanceM, model);
}

/// 複数 RSSI サンプル（中央値集約）で整合を判定する。単発より外れ値に強い。
RssiConsistencyResult checkRssiConsistencyFromSamples({
  required double claimedDistanceM,
  required List<int> rssiSamples,
  RssiRangingModel model = const RssiRangingModel(),
}) {
  if (rssiSamples.isEmpty) {
    return const RssiConsistencyResult(
      verdict: RssiVerdict.unknown,
      estimatedRangeM: 0,
      claimedDistanceM: 0,
      lowerM: 0,
      upperM: 0,
    );
  }
  return _resultFor(model.distanceFromSamples(rssiSamples), claimedDistanceM, model);
}

RssiConsistencyResult _resultFor(
    double est, double claimedDistanceM, RssiRangingModel model) {
  final f = model.relBand();
  final lower = est / f;
  final upper = est * f;
  final ok = claimedDistanceM >= lower && claimedDistanceM <= upper;
  return RssiConsistencyResult(
    verdict: ok ? RssiVerdict.consistent : RssiVerdict.suspicious,
    estimatedRangeM: est,
    claimedDistanceM: claimedDistanceM,
    lowerM: lower,
    upperM: upper,
  );
}
