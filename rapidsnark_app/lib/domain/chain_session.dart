enum ChainSessionStatus { localDemoOnly, awaitingAggregation, finalized }

enum ChainVerdict {
  undetermined,
  noInconsistencyObserved,
  positionInconsistencySuspected,
}

/// PoC画面が表示する入力・proof・集約・チェーンの状態。
///
/// 現在のアプリからは単体デモproofしか渡していない。V2 observer proof、
/// 複数端末集約、FinalAttestationRegistry eventはまだ接続されていない。
/// verdict名は「信頼済み」「詐称確定」と誤読しないV2意味に揃える。
class ChainSession {
  const ChainSession({
    required this.status,
    required this.inputCapturedAt,
    required this.inputSource,
    required this.localDemoProofValid,
    this.consistentCount,
    this.suspiciousCount,
    this.threshold = 2,
    this.verdict = ChainVerdict.undetermined,
    this.blockNumber,
  });

  final ChainSessionStatus status;
  final DateTime? inputCapturedAt;
  final String? inputSource;
  final bool localDemoProofValid;
  final int? consistentCount;
  final int? suspiciousCount;
  final int threshold;
  final ChainVerdict verdict;
  final int? blockNumber;

  bool get hasAggregate => consistentCount != null && suspiciousCount != null;
}
