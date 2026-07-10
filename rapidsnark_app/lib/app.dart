import 'package:flutter/material.dart';

import 'features/safety_proof/safety_proof_page.dart';

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
      home: const SafetyProofPage(),
    );
  }
}
