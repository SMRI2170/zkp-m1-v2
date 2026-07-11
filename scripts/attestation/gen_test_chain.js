// テスト用の Android Key Attestation 証明書チェーンを生成する（実機なしで検証ゲートを試す）。
// 実機では TEE/StrongBox が同等の拡張を持つチェーンを発行する。本番検証は Google 根をピン留めする。
const x509 = require("@peculiar/x509");
const { AsnConvert, OctetString } = require("@peculiar/asn1-schema");
const androidAsn = require("@peculiar/asn1-android");
const { webcrypto } = require("crypto");

x509.cryptoProvider.set(webcrypto);

const ALG = { name: "ECDSA", namedCurve: "P-256", hash: "SHA-256" };

// challengeStr = device_pubkey の束縛値。opts で securityLevel/origin を変えて否定系も作れる。
async function generateTestChain(challengeStr, opts = {}) {
  const securityLevel = opts.securityLevel ?? androidAsn.SecurityLevel.strongBox;
  const origin = opts.origin ?? 0; // GENERATED
  const withExtension = opts.withExtension ?? true;

  const rootKeys = await webcrypto.subtle.generateKey(ALG, false, ["sign", "verify"]);
  const now = new Date();
  const later = new Date(now.getTime() + 3600 * 1000);

  const root = await x509.X509CertificateGenerator.createSelfSigned({
    serialNumber: "01",
    name: "CN=Test Attestation Root",
    notBefore: now,
    notAfter: later,
    signingAlgorithm: ALG,
    keys: rootKeys,
    extensions: [new x509.BasicConstraintsExtension(true, 1, true)],
  });

  const leafKeys = await webcrypto.subtle.generateKey(ALG, true, ["sign", "verify"]);

  const extensions = [];
  if (withExtension) {
    const kd = new androidAsn.KeyDescription({
      attestationVersion: 4,
      attestationSecurityLevel: securityLevel,
      keymasterVersion: 4,
      keymasterSecurityLevel: securityLevel,
      attestationChallenge: new OctetString(new TextEncoder().encode(challengeStr)),
      uniqueId: new OctetString(new ArrayBuffer(0)),
      softwareEnforced: new androidAsn.AuthorizationList({}),
      teeEnforced: new androidAsn.AuthorizationList({ origin }),
    });
    const extValue = AsnConvert.serialize(kd);
    extensions.push(new x509.Extension(androidAsn.id_ce_keyDescription, false, extValue));
  }

  const leaf = await x509.X509CertificateGenerator.create({
    serialNumber: "02",
    subject: "CN=attested device key",
    issuer: root.subject,
    notBefore: now,
    notAfter: later,
    signingAlgorithm: ALG,
    publicKey: leafKeys.publicKey,
    signingKey: rootKeys.privateKey,
    extensions,
  });

  return {
    chainPem: [leaf.toString("pem"), root.toString("pem")],
    rootPem: root.toString("pem"),
  };
}

module.exports = { generateTestChain };
