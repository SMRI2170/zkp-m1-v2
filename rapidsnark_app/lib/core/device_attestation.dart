import 'package:flutter/services.dart';

/// Android Key Attestation のアプリ側呼び出し口。
///
/// 返る公開鍵は Android 側で作る P-256 鍵で、V2 leaf 回路の
/// BabyJubJub EdDSA observer key とは別物。このAPIは観測statementへの署名も、
/// 2つの鍵の対応関係も証明しない。証明書chainのtrust-root検証と明示的な
/// proof-of-possession付き登録が接続されるまでは、observer credentialや
/// Sybil対策が実装済みとは扱わない。
class AttestationStatement {
  const AttestationStatement({
    required this.publicKey,
    required this.certChain,
    required this.nonce,
  });

  /// Android Key Attestation が証明する P-256 公開鍵（base64 encoded key）。
  /// V2回路の BabyJubJub 公開鍵ではない。
  final String publicKey;

  /// ハードウェア由来の証明書チェーン（検証側が信頼ルートまで辿る）。
  final List<String> certChain;

  /// Android attestation certificate に含める呼び出し元提供challenge。
  /// それ自体は観測署名でも、回路freshnessの証明でもない。
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
