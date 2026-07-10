import 'package:flutter/services.dart';

/// 端末アテステーション（M3・Sybil/端末真正性）。
///
/// 目的: 回路が検証する device_pubkey が「改ざんされていない実機・実アプリの
/// ハードウェア鍵」であることを、プラットフォームの証明で裏取りする。
///   - Android: Key Attestation（StrongBox/TEE 由来の証明書チェーン）
///   - iOS: App Attest / DeviceCheck
/// これにより「1人が大量の偽端末を作る」Sybil を、鍵の出所レベルで抑止する。
///
/// 本ファイルはアプリ側の統合点（インターフェース＋MethodChannel骨組み）。
/// 実際の証明生成・検証はネイティブ実装と、証明書チェーンの検証（オンチェーン/
/// バックエンド）が必要。ここではその差し込み口を定義する。
class AttestationStatement {
  const AttestationStatement({
    required this.publicKey,
    required this.certChain,
    required this.nonce,
  });

  /// 端末鍵（回路の device_pubkey に対応）。
  final String publicKey;

  /// ハードウェア由来の証明書チェーン（検証側が信頼ルートまで辿る）。
  final List<String> certChain;

  /// リプレイ防止のチャレンジ（回路 freshness と同期させる）。
  final String nonce;

  bool get isEmpty => certChain.isEmpty;
}

abstract class DeviceAttestationProvider {
  /// nonce（＝freshness ビーコン）に対する端末アテステーションを取得する。
  Future<AttestationStatement> attest(String nonce);
}

/// ネイティブ実装の骨組み。MethodChannel 経由で Android/iOS の
/// アテステーション API を呼ぶ想定（ネイティブ側の実装が別途必要）。
class PlatformDeviceAttestation implements DeviceAttestationProvider {
  static const MethodChannel _channel =
      MethodChannel('com.example.rapidsnark_app/attestation');

  @override
  Future<AttestationStatement> attest(String nonce) async {
    final res = await _channel.invokeMapMethod<String, dynamic>(
      'attest',
      {'nonce': nonce},
    );
    if (res == null) {
      return AttestationStatement(publicKey: '', certChain: const [], nonce: nonce);
    }
    return AttestationStatement(
      publicKey: (res['publicKey'] as String?) ?? '',
      certChain: (res['certChain'] as List?)?.cast<String>() ?? const [],
      nonce: (res['nonce'] as String?) ?? nonce,
    );
  }
}

/// テスト/未対応端末向けのスタブ（アテステーション無し）。
class MockDeviceAttestation implements DeviceAttestationProvider {
  const MockDeviceAttestation();

  @override
  Future<AttestationStatement> attest(String nonce) async =>
      AttestationStatement(publicKey: 'mock', certChain: const ['mock-cert'], nonce: nonce);
}
