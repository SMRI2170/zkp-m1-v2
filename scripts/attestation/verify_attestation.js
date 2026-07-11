// Android Key Attestation の検証ゲート（★2 入力真正性 / Sybil対策）。
//
// 目的: 回路の device_pubkey（BabyJub EdDSA鍵）が「改ざんされていない実機の
// ハードウェア鍵に裏書きされている」ことを確認し、正当な端末だけ登録を許す。
//
// TEE/StrongBox がアテステーションするのは P-256 の鍵。これを回路の BabyJub 鍵に
// 束縛するため、アテステーションの challenge = device_pubkey の束縛値 とする
// （＝このハード端末がこの BabyJub 鍵を裏書きした、を証明）。
//
// 検証内容:
//   1. 証明書チェーンの署名連結（leaf ← … ← root）
//   2. root が信頼ルート（本番は Google Hardware Attestation Root）に一致
//   3. leaf に Key Attestation 拡張（OID 1.3.6.1.4.1.11129.2.1.17）が存在
//   4. attestationChallenge == 期待束縛値（device_pubkey に紐付く）
//   5. keymasterSecurityLevel が TEE/StrongBox（＝ハードウェア鍵）
//   6. teeEnforced.origin == GENERATED（＝実機内で生成、インポートでない）
const x509 = require("@peculiar/x509");
const { AsnConvert } = require("@peculiar/asn1-schema");
const androidAsn = require("@peculiar/asn1-android");
const { webcrypto } = require("crypto");

x509.cryptoProvider.set(webcrypto);

const HARDWARE_LEVELS = new Set([
  androidAsn.SecurityLevel.trustedEnvironment,
  androidAsn.SecurityLevel.strongBox,
]);
const ORIGIN_GENERATED = 0;

function fail(reason) {
  return { ok: false, reason };
}

async function verifyAttestation({ chainPem, expectedChallenge, trustedRootPem }) {
  const certs = chainPem.map((pem) => new x509.X509Certificate(pem));
  if (certs.length < 2) return fail("chain too short");

  // 1. チェーン署名連結
  for (let i = 0; i < certs.length - 1; i++) {
    const ok = await certs[i].verify({ publicKey: certs[i + 1].publicKey, signatureOnly: true });
    if (!ok) return fail(`bad signature at cert ${i}`);
  }

  // 2. ルートピン留め（本番は Google のハードウェアアテステーション根）
  const root = certs[certs.length - 1];
  if (trustedRootPem) {
    const trusted = new x509.X509Certificate(trustedRootPem);
    const a = Buffer.from(root.rawData);
    const b = Buffer.from(trusted.rawData);
    if (Buffer.compare(a, b) !== 0) return fail("root not trusted");
  }

  // 3. Key Attestation 拡張
  const leaf = certs[0];
  const ext = leaf.getExtension(androidAsn.id_ce_keyDescription);
  if (!ext) return fail("no key attestation extension");
  let kd;
  try {
    kd = AsnConvert.parse(ext.value, androidAsn.KeyDescription);
  } catch (e) {
    return fail("cannot parse key attestation extension");
  }

  // 4. challenge が期待束縛値（device_pubkey に紐付く）
  const challenge = Buffer.from(kd.attestationChallenge.buffer).toString("utf8");
  if (expectedChallenge !== undefined && challenge !== expectedChallenge) {
    return fail(`challenge mismatch (got ${JSON.stringify(challenge)})`);
  }

  // 5. ハードウェア由来か
  if (!HARDWARE_LEVELS.has(kd.keymasterSecurityLevel)) {
    return fail(`not hardware-backed (level=${kd.keymasterSecurityLevel})`);
  }

  // 6. 実機内生成（origin=GENERATED）
  const origin = kd.teeEnforced ? kd.teeEnforced.origin : undefined;
  if (origin !== ORIGIN_GENERATED) {
    return fail(`origin not GENERATED (origin=${origin})`);
  }

  const publicKeyJwk = await webcrypto.subtle.exportKey("jwk", await leaf.publicKey.export());
  return {
    ok: true,
    securityLevel: androidAsn.SecurityLevel[kd.keymasterSecurityLevel],
    challenge,
    publicKeyJwk,
  };
}

module.exports = { verifyAttestation };
