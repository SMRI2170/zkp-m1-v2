import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:rapidsnark_app/app.dart';

void main() {
  testWidgets('renders safety proof screen', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: RapidsnarkApp()),
    );

    expect(find.text('UAV Safety ZK'), findsWidgets);
  });
}
