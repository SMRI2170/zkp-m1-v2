package com.example.rapidsnark_app

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.cert.Certificate
import java.security.spec.ECGenParameterSpec

/**
 * Android Key Attestation の試験用実装。
 *
 * AndroidKeyStore に TEE/StrongBox 由来の P-256 鍵を生成し、証明書chainと
 * 呼び出し元提供challengeを返す。challengeの一致だけでは、V2回路のBabyJubJub
 * observer鍵をこのP-256鍵へ結び付けたり、観測statementへの署名を証明したりしない。
 * 現状は呼び出しごとに既存aliasを削除して鍵を作り直すため、安定したobserver
 * credentialとしても使えない。統合には鍵の対応を検証するproof-of-possessionと
 * 固定trust-rootを使う登録処理が別途必要。
 */
object DeviceAttestation {
    private const val ALIAS = "uav_device_attest_key"

    /** 呼び出し元challengeを含むP-256 Key AttestationとPEM chainを返す。 */
    fun attest(nonce: ByteArray): Map<String, Any> {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (ks.containsAlias(ALIAS)) ks.deleteEntry(ALIAS)

        val builder = KeyGenParameterSpec.Builder(
            ALIAS,
            KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY,
        )
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setAttestationChallenge(nonce)

        // StrongBox 優先。無ければ TEE にフォールバック。
        try {
            generate(builder.setIsStrongBoxBacked(true).build())
        } catch (e: Exception) {
            generate(builder.setIsStrongBoxBacked(false).build())
        }

        val chain = ks.getCertificateChain(ALIAS)
            ?: throw IllegalStateException("no attestation chain")
        val pem = chain.map { toPem(it) }
        val pub = Base64.encodeToString(
            ks.getCertificate(ALIAS).publicKey.encoded, Base64.NO_WRAP,
        )
        return mapOf(
            "publicKey" to pub,
            "certChain" to pem,
            "nonce" to Base64.encodeToString(nonce, Base64.NO_WRAP),
        )
    }

    private fun generate(spec: KeyGenParameterSpec) {
        val kpg = KeyPairGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore",
        )
        kpg.initialize(spec)
        kpg.generateKeyPair()
    }

    private fun toPem(cert: Certificate): String {
        val b64 = Base64.encodeToString(cert.encoded, Base64.NO_WRAP)
        val body = b64.chunked(64).joinToString("\n")
        return "-----BEGIN CERTIFICATE-----\n$body\n-----END CERTIFICATE-----"
    }
}
