// 検証ゲートの自己テスト（実機なし）。
// 正当なハードウェアアテステーション → 登録許可 / 各種の不正 → 拒否 を確認する。
const androidAsn = require("@peculiar/asn1-android");
const { verifyAttestation } = require("./verify_attestation");
const { generateTestChain } = require("./gen_test_chain");

// 試験用challenge文字列。これだけでBabyJub秘密鍵の所持を証明するわけではない。
const BINDING = "device_pubkey:15944627324083773346390189001500210680939402028015651549526524193195473201952";

let pass = 0;
let failCount = 0;
function check(name, cond) {
  if (cond) {
    console.log(`  ok  ${name}`);
    pass++;
  } else {
    console.log(`  NG  ${name}`);
    failCount++;
  }
}

async function main() {
  // 1. 正当: StrongBox・GENERATED・challenge一致 → 許可
  {
    const { chainPem, rootPem } = await generateTestChain(BINDING);
    const r = await verifyAttestation({ chainPem, expectedChallenge: BINDING, trustedRootPem: rootPem });
    check("正当なハードウェア鍵を許可", r.ok === true);
    check("  securityLevel=strongBox", r.ok && r.securityLevel === "strongBox");
    check("  公開鍵を抽出", r.ok && r.publicKeyJwk && r.publicKeyJwk.kty === "EC");
  }

  // 信頼rootまたはchallengeが無い場合はfail closedにする。
  {
    const { chainPem, rootPem } = await generateTestChain(BINDING);
    const noRoot = await verifyAttestation({ chainPem, expectedChallenge: BINDING });
    const noChallenge = await verifyAttestation({ chainPem, trustedRootPem: rootPem });
    check("信頼root未指定を拒否", noRoot.ok === false && /trusted root/.test(noRoot.reason));
    check("期待challenge未指定を拒否", noChallenge.ok === false && /expected challenge/.test(noChallenge.reason));
  }

  // 2. challenge 不一致（別 device_pubkey へ流用）→ 拒否
  {
    const { chainPem, rootPem } = await generateTestChain("other-binding");
    const r = await verifyAttestation({ chainPem, expectedChallenge: BINDING, trustedRootPem: rootPem });
    check("challenge不一致を拒否", r.ok === false && /challenge/.test(r.reason));
  }

  // 3. ソフトウェア鍵（非ハード）→ 拒否
  {
    const { chainPem, rootPem } = await generateTestChain(BINDING, {
      securityLevel: androidAsn.SecurityLevel.software,
    });
    const r = await verifyAttestation({ chainPem, expectedChallenge: BINDING, trustedRootPem: rootPem });
    check("ソフトウェア鍵を拒否", r.ok === false && /hardware/.test(r.reason));
  }

  // 4. インポート鍵（origin != GENERATED）→ 拒否
  {
    const { chainPem, rootPem } = await generateTestChain(BINDING, { origin: 2 /* IMPORTED */ });
    const r = await verifyAttestation({ chainPem, expectedChallenge: BINDING, trustedRootPem: rootPem });
    check("インポート鍵を拒否", r.ok === false && /origin/.test(r.reason));
  }

  // 5. 拡張なし（アテステーション無し）→ 拒否
  {
    const { chainPem, rootPem } = await generateTestChain(BINDING, { withExtension: false });
    const r = await verifyAttestation({ chainPem, expectedChallenge: BINDING, trustedRootPem: rootPem });
    check("アテステーション拡張なしを拒否", r.ok === false && /extension/.test(r.reason));
  }

  // 6. 別ルート（信頼root不一致）→ 拒否
  {
    const { chainPem } = await generateTestChain(BINDING);
    const other = await generateTestChain(BINDING);
    const r = await verifyAttestation({ chainPem, expectedChallenge: BINDING, trustedRootPem: other.rootPem });
    check("信頼root不一致を拒否", r.ok === false && /root/.test(r.reason));
  }

  console.log(`\n${pass} passed, ${failCount} failed`);
  process.exit(failCount === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
