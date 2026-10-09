import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rapidsnark_app/domain/chain_session.dart';
import 'package:rapidsnark_app/features/chain_session/chain_session_page.dart';

void main() {
  Widget createPage(ChainSession session) {
    return MaterialApp(
      home: Scaffold(body: ChainSessionPage(session: session)),
    );
  }

  testWidgets('labels the current app state as a disconnected local demo', (
    tester,
  ) async {
    await tester.pumpWidget(
      createPage(
        ChainSession(
          status: ChainSessionStatus.localDemoOnly,
          inputCapturedAt: DateTime.utc(2026, 10, 5, 3, 0),
          inputSource: 'BLE',
          localDemoProofValid: true,
        ),
      ),
    );

    expect(find.text('単体デモproof — V2/チェーン未接続'), findsOneWidget);
    expect(
      find.textContaining('V2 Remote ID leaf proofではありません'),
      findsOneWidget,
    );
    expect(find.textContaining('Remote IDの真正性・観測者登録・複数端末の集約'), findsOneWidget);
    expect(find.textContaining('registryへ送信・照会していません'), findsOneWidget);
    expect(find.textContaining('位置不整合の疑い —'), findsNothing);
  });

  testWidgets('uses non-conclusive position-inconsistency wording', (
    tester,
  ) async {
    await tester.pumpWidget(
      createPage(
        ChainSession(
          status: ChainSessionStatus.finalized,
          inputCapturedAt: DateTime.utc(2026, 10, 5, 3, 0),
          inputSource: 'BLE',
          localDemoProofValid: true,
          consistentCount: 1,
          suspiciousCount: 2,
          verdict: ChainVerdict.positionInconsistencySuspected,
          blockNumber: 42,
        ),
      ),
    );

    expect(find.text('位置不整合の疑い — 機体認証ではありません'), findsOneWidget);
    expect(find.text('Block #42 のFinalized record'), findsOneWidget);
    expect(find.textContaining('物理位置を証明しません'), findsOneWidget);
    expect(find.textContaining('詐称確定'), findsNothing);
    expect(find.textContaining('Trusted'), findsNothing);
  });

  testWidgets('does not call a no-mismatch result trusted or safe', (
    tester,
  ) async {
    await tester.pumpWidget(
      createPage(
        ChainSession(
          status: ChainSessionStatus.finalized,
          inputCapturedAt: DateTime.utc(2026, 10, 5, 3, 0),
          inputSource: 'BLE',
          localDemoProofValid: true,
          consistentCount: 2,
          suspiciousCount: 0,
          verdict: ChainVerdict.noInconsistencyObserved,
          blockNumber: 43,
        ),
      ),
    );

    expect(find.text('位置不整合はこのpolicyでは観測されず'), findsOneWidget);
    expect(find.textContaining('安全'), findsNothing);
    expect(find.textContaining('Trusted'), findsNothing);
  });
}
