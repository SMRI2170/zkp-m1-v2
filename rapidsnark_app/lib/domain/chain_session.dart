enum ChainSessionStatus { localOnly, awaitingAggregation, finalized }

enum ChainVerdict { undetermined, trusted, spoofSuspected }

/// チェーンに保存する最終レコードを、人が読める画面へ変換するための状態。
///
/// 座標・RSSI・proof bytes は持たない。将来は FinalAttestationRegistry の
/// Finalized event をこの型に変換して表示する。
class ChainSession {
  const ChainSession({
    required this.status,
    required this.observedAt,
    required this.remoteIdSource,
    required this.leafProofValid,
    this.leafProofCount = 1,
    this.consistentCount,
    this.suspiciousCount,
    this.threshold = 2,
    this.verdict = ChainVerdict.undetermined,
    this.blockNumber,
  });

  final ChainSessionStatus status;
  final DateTime? observedAt;
  final String? remoteIdSource;
  final bool leafProofValid;
  final int leafProofCount;
  final int? consistentCount;
  final int? suspiciousCount;
  final int threshold;
  final ChainVerdict verdict;
  final int? blockNumber;

  bool get hasAggregate => consistentCount != null && suspiciousCount != null;
}
