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
              'チェーン記録',
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: _ink,
              ),
            ),
            const SizedBox(height: 4),
            const Text(
              'ハッシュではなく、観測がどの判定になったかを確認します。',
              style: TextStyle(color: _muted, fontSize: 13),
            ),
            const SizedBox(height: 16),
            _statusCard(status, statusColor),
            const SizedBox(height: 20),
            const Text(
              'このセッションの流れ',
              style: TextStyle(fontWeight: FontWeight.w800, color: _ink),
            ),
            const SizedBox(height: 10),
            _flowStep(
              icon: Icons.sensors_rounded,
              title: '観測',
              detail: session.observedAt == null
                  ? 'まだ観測されていません'
                  : '${_formatTime(session.observedAt!)}${session.remoteIdSource == null ? '' : ' ・ ${session.remoteIdSource} Remote ID'}',
              complete: session.observedAt != null,
              last: false,
            ),
            _flowStep(
              icon: Icons.verified_user_rounded,
              title: '端末内 ZK 証明',
              detail: session.leafProofValid
                  ? '位置・生 RSSI を公開せず、端末内で検証済み'
                  : '証明の生成・検証を待っています',
              complete: session.leafProofValid,
              last: false,
            ),
            _flowStep(
              icon: Icons.account_tree_rounded,
              title: '複数端末の集約',
              detail: session.hasAggregate
                  ? '整合 ${session.consistentCount} 件 / 矛盾 ${session.suspiciousCount} 件'
                  : 'ほかの登録端末の証明を集約待ち',
              complete: session.hasAggregate,
              last: false,
            ),
            _flowStep(
              icon: Icons.link_rounded,
              title: 'チェーンへの最終記録',
              detail: session.blockNumber == null
                  ? '集約 proof を確定後、1 セッション 1 件だけ登録します'
                  : 'Block #${session.blockNumber} に Finalized として確定',
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
            const Text(
              'この画面では、正確な位置・生 RSSI・proof 本文・端末名は表示しません。最終確定後は、判定、件数、登録端末集合の検証結果だけをチェーンから読みます。',
              style: TextStyle(color: _muted, height: 1.5, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statusCard(String status, Color statusColor) {
    final title = switch (session.verdict) {
      ChainVerdict.trusted => 'Trusted — 裏取り成立',
      ChainVerdict.spoofSuspected => 'Spoof suspected — 矛盾を検知',
      ChainVerdict.undetermined =>
        session.status == ChainSessionStatus.localOnly
            ? 'ローカル証明を確認済み'
            : '最終判定を待機中',
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
          Icon(Icons.verified_rounded, color: statusColor, size: 30),
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
          '最終判定には、別々の登録端末から集めた複数の証明が必要です。現在はこの端末の証明だけを確認済みです。',
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
                        '整合 ${session.consistentCount}',
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
                          '矛盾 ${session.suspiciousCount}',
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
            '閾値 K=${session.threshold}。件数だけを公開し、各端末の位置・RSSI は公開しません。',
            style: const TextStyle(color: _muted, fontSize: 12),
          ),
        ],
      ),
    );
  }

  String _statusText() {
    return switch (session.status) {
      ChainSessionStatus.localOnly => 'この端末の ZK 証明は検証済みですが、まだチェーンには登録されていません。',
      ChainSessionStatus.awaitingAggregation =>
        '複数端末の proof を集約し、最終 proof を生成しています。',
      ChainSessionStatus.finalized => '集約 proof がオンチェーンで検証され、最終判定として確定しました。',
    };
  }

  Color _statusColor() {
    return switch (session.verdict) {
      ChainVerdict.trusted => _green,
      ChainVerdict.spoofSuspected => _amber,
      ChainVerdict.undetermined =>
        session.leafProofValid ? const Color(0xFF2B63C0) : _muted,
    };
  }

  String _formatTime(DateTime value) {
    return '${value.month}/${value.day} ${value.hour.toString().padLeft(2, '0')}:${value.minute.toString().padLeft(2, '0')}';
  }
}
