import 'package:flutter/material.dart';

import '../../domain/chain_session.dart';

/// ハッシュや proof bytes ではなく、観測から最終判定までの意味を表示する画面。
class ChainSessionPage extends StatelessWidget {
  const ChainSessionPage({super.key, required this.session});

  final ChainSession session;

  static const _green = Color(0xFF167C5A);
  static const _amber = Color(0xFFB76E00);
  static const _ink = Color(0xFF172033);
  static const _muted = Color(0xFF5C687A);
  static const _line = Color(0xFFD9E0EA);

  @override
  Widget build(BuildContext context) {
    final status = _statusText();
    final statusColor = _statusColor();

    return Container(
      color: const Color(0xFFF6F8FC),
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 18, 16, 28),
          children: [
            const Text(
              '証明・チェーン接続の状態',
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: _ink,
              ),
            ),
            const SizedBox(height: 4),
            const Text(
              '単体デモproofと、未接続の複数端末・EVM工程を分けて表示します。',
              style: TextStyle(color: _muted, fontSize: 13),
            ),
            const SizedBox(height: 16),
            if (session.status == ChainSessionStatus.localDemoOnly) ...[
              _notConnectedBanner(),
              const SizedBox(height: 14),
            ],
            _statusCard(status, statusColor),
            const SizedBox(height: 20),
            const Text(
              'このセッションの流れ',
              style: TextStyle(fontWeight: FontWeight.w800, color: _ink),
            ),
            const SizedBox(height: 10),
            _flowStep(
              icon: Icons.input_rounded,
              title: 'デモ入力',
              detail: session.inputCapturedAt == null
                  ? '入力時刻はありません'
                  : '${_formatTime(session.inputCapturedAt!)}${session.inputSource == null ? '' : ' ・ ${session.inputSource}'}',
              complete: session.inputCapturedAt != null,
              last: false,
            ),
            _flowStep(
              icon: Icons.science_outlined,
              title: 'ローカルデモ ZK proof',
              detail: session.localDemoProofValid
                  ? '選択中のデモ回路でproofを検証済み（V2 Remote ID leaf proofではありません）'
                  : 'デモproofは未検証です',
              complete: session.localDemoProofValid,
              last: false,
            ),
            _flowStep(
              icon: Icons.account_tree_rounded,
              title: 'V2 複数観測者の集約',
              detail: session.hasAggregate
                  ? '位置整合 ${session.consistentCount} 件 / 不整合の疑い ${session.suspiciousCount} 件'
                  : '未接続 — 他の観測端末のproofは集約していません',
              complete: session.hasAggregate,
              last: false,
            ),
            _flowStep(
              icon: Icons.link_off_rounded,
              title: '最終ZK proof → EVM検証',
              detail: session.blockNumber == null
                  ? '未接続 — この画面はFinal proofをregistryへ送信・照会していません'
                  : 'Block #${session.blockNumber} のFinalized record',
              complete: session.status == ChainSessionStatus.finalized,
              last: true,
            ),
            const SizedBox(height: 20),
            _reasonCard(),
            const SizedBox(height: 14),
            const Text(
              'プライバシー',
              style: TextStyle(fontWeight: FontWeight.w800, color: _ink),
            ),
            const SizedBox(height: 8),
            Text(
              session.status == ChainSessionStatus.localDemoOnly
                  ? 'この画面はチェーンを読み書きしていません。将来接続するregistryでは、公開する判定・件数と、集約者や通信metadataに見える情報を別途監査します。'
                  : 'オンチェーン公開値だけでなく、集約者が見られるleaf情報や通信metadataもプライバシー境界として扱います。',
              style: const TextStyle(color: _muted, height: 1.5, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statusCard(String status, Color statusColor) {
    final title = session.status == ChainSessionStatus.localDemoOnly
        ? '単体デモproof — V2/チェーン未接続'
        : switch (session.verdict) {
            ChainVerdict.noInconsistencyObserved => '位置不整合はこのpolicyでは観測されず',
            ChainVerdict.positionInconsistencySuspected =>
              '位置不整合の疑い — 機体認証ではありません',
            ChainVerdict.undetermined => '最終判定を待機中',
          };

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: statusColor.withValues(alpha: 0.08),
        border: Border.all(color: statusColor.withValues(alpha: 0.35)),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Icon(
            session.status == ChainSessionStatus.finalized
                ? Icons.fact_check_outlined
                : Icons.info_outline_rounded,
            color: statusColor,
            size: 30,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: statusColor,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  status,
                  style: const TextStyle(
                    color: _muted,
                    fontSize: 12,
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _notConnectedBanner() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: _amber.withValues(alpha: 0.08),
        border: Border.all(color: _amber.withValues(alpha: 0.45)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: const Text(
        '現在表示できるのは汎用デモ回路のローカルproof状態だけです。Remote IDの真正性・観測者登録・複数端末の集約・最終proof・EVM記録は、このアプリ画面に接続されていません。',
        style: TextStyle(color: _ink, fontSize: 13, height: 1.45),
      ),
    );
  }

  Widget _flowStep({
    required IconData icon,
    required String title,
    required String detail,
    required bool complete,
    required bool last,
  }) {
    final color = complete ? _green : _muted;
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: 40,
            child: Column(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: color,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    complete ? Icons.check_rounded : icon,
                    color: Colors.white,
                    size: 18,
                  ),
                ),
                if (!last) Expanded(child: Container(width: 2, color: _line)),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: last ? 0 : 18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      color: _ink,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    detail,
                    style: const TextStyle(
                      color: _muted,
                      fontSize: 12,
                      height: 1.35,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _reasonCard() {
    if (!session.hasAggregate) {
      return Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: _line),
        ),
        child: const Text(
          '集約結果はありません。現在の単体デモproofは、登録済みRemote ID観測者の証明として数えていません。',
          style: TextStyle(color: _muted, fontSize: 13, height: 1.45),
        ),
      );
    }

    final total = session.consistentCount! + session.suspiciousCount!;
    final consistentWidth = total == 0 ? 0.0 : session.consistentCount! / total;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '最終判定の根拠',
            style: TextStyle(fontWeight: FontWeight.w800, color: _ink),
          ),
          const SizedBox(height: 10),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: SizedBox(
              height: 26,
              child: LayoutBuilder(
                builder: (context, constraints) => Row(
                  children: [
                    Container(
                      width: constraints.maxWidth * consistentWidth,
                      color: _green,
                      alignment: Alignment.center,
                      child: Text(
                        '位置整合 ${session.consistentCount}',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Container(
                        color: _amber,
                        alignment: Alignment.center,
                        child: Text(
                          '不整合の疑い ${session.suspiciousCount}',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '閾値 K=${session.threshold}。この結果は位置不整合のpolicy判定であり、Remote IDの真正性や機体の物理位置を証明しません。',
            style: const TextStyle(color: _muted, fontSize: 12),
          ),
        ],
      ),
    );
  }

  String _statusText() {
    if (session.status == ChainSessionStatus.localDemoOnly) {
      return session.localDemoProofValid
          ? 'デモ回路のproofはローカルで検証済みです。V2 observer proofやオンチェーンの最終記録とは別物です。'
          : 'ローカルデモproofは未検証です。複数端末集約やチェーン状態は確認していません。';
    }
    return switch (session.status) {
      ChainSessionStatus.localDemoOnly => 'ローカルデモproofの状態です。',
      ChainSessionStatus.awaitingAggregation =>
        'V2観測proofは確認済みで、複数端末の集約proofを待っています。',
      ChainSessionStatus.finalized =>
        '最終proofはEVMで検証されました。この結果もRemote IDの真正性や物理的真実を保証しません。',
    };
  }

  Color _statusColor() {
    if (session.status == ChainSessionStatus.localDemoOnly) {
      return session.localDemoProofValid ? const Color(0xFF2B63C0) : _muted;
    }
    return switch (session.verdict) {
      ChainVerdict.noInconsistencyObserved => const Color(0xFF2B63C0),
      ChainVerdict.positionInconsistencySuspected => _amber,
      ChainVerdict.undetermined => _muted,
    };
  }

  String _formatTime(DateTime value) {
    return '${value.month}/${value.day} ${value.hour.toString().padLeft(2, '0')}:${value.minute.toString().padLeft(2, '0')}';
  }
}
