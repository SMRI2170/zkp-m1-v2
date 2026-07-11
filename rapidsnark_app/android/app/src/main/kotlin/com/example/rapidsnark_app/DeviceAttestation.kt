package com.example.rapidsnark_app

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.cert.Certificate
import java.security.spec.ECGenParameterSpec

/**
 * 端末アテステーション（M3 / ★2 入力真正性・Sybil対策）。
 *
 * AndroidKeyStore に TEE/StrongBox 由来の EC 鍵を生成し、Key Attestation の
 * 証明書チェーンを取得する。challenge に device_pubkey の束縛値（nonce）を入れることで、
 * 「このハード端末がこの device_pubkey を裏書きした」ことを検証側（verify_attestation.js）で
 * 確認でき、正当な実機だけが端末登録を通る。
 */
object DeviceAttestation {
    private const val ALIAS = "uav_device_attest_key"

    /** nonce(=device_pubkey束縛値)に対するアテステーションを生成し、公開鍵とPEMチェーンを返す。 */
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
