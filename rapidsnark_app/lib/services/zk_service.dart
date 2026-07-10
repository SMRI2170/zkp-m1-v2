import 'dart:io';

import 'package:circom_witnesscalc/circom_witnesscalc.dart';
import 'package:flutter/services.dart';
import 'package:flutter_rapidsnark/flutter_rapidsnark.dart';
import 'package:path_provider/path_provider.dart';

/// ZK 証明の結果
class ZkProofResult {
  const ZkProofResult({
    required this.proof,
    required this.publicSignals,
    required this.valid,
  });

  final String proof;
  final String publicSignals;
  final bool valid;
}

/// ZK 証明サービス。Witness 計算・Groth16 証明・検証を行う。
class ZkService {
  final _rapidsnark = Rapidsnark();
  final _witnesscalc = CircomWitnesscalc();

  Future<ZkProofResult> prove({
    required String inputsJson,
    required String wcdAssetPath,
    required String zkeyAssetPath,
    required String verificationKeyAssetPath,
  }) async {
    // .wcd グラフデータを読み込む
    final graphData =
        (await rootBundle.load(wcdAssetPath)).buffer.asUint8List();
    if (graphData.length < 32) {
      throw Exception('$wcdAssetPath が不正です。assets を再生成してください。');
    }

    // 検証キーを読み込む
    final verificationKey =
        await rootBundle.loadString(verificationKeyAssetPath);

    // zkey を一時ファイルにコピー（rapidsnark はファイルパスを要求）
    final zkeyPath = await _copyAssetToTemp(zkeyAssetPath);

    // ① Witness 計算
    final witness = await _witnesscalc.calculateWitness(
      inputs: inputsJson,
      graphData: graphData,
    );
    if (witness == null) {
      throw Exception('Witness generation returned null');
    }

    // ② Groth16 証明生成
    final publicBufferSize =
        await _rapidsnark.groth16PublicBufferSize(zkeyPath: zkeyPath);
    final proveResult = await _rapidsnark.groth16Prove(
      zkeyPath: zkeyPath,
      witness: witness,
      publicBufferSize: publicBufferSize,
    );

    // ③ 検証
    final valid = await _rapidsnark.groth16Verify(
      proof: proveResult.proof,
      inputs: proveResult.publicSignals,
      verificationKey: verificationKey,
    );

    return ZkProofResult(
      proof: proveResult.proof,
      publicSignals: proveResult.publicSignals,
      valid: valid,
    );
  }

  Future<String> _copyAssetToTemp(String assetPath) async {
    final dir = await getTemporaryDirectory();
    final fileName = assetPath.split('/').last;
    final file = File('${dir.path}/$fileName');
    final bytes = (await rootBundle.load(assetPath)).buffer.asUint8List();
    await file.writeAsBytes(bytes, flush: true);
    return file.path;
  }
}
