# 設計 — 端末アテステーション（★2 入力真正性 / Sybil対策）

作成日: 2026-07-11 / 関連: security_attack_surface.pptx（★2）

## 目的
回路は `device_pubkey`（BabyJub EdDSA鍵）で「端末が観測を署名した」ことは検証できるが、
**その鍵が改ざんされていない実機のハードウェア鍵か**は保証できなかった。
改造アプリ／エミュレータは任意の鍵で参加でき、偽のRSSI/GPS/検知を入れられた（★2の穴）。

端末アテステーションで **device_pubkey を実機ハードウェアに束縛**し、正当な実機だけが
端末登録を通るようにする（Sybil耐性・入力真正性の底上げ）。

## 鍵の型の橋渡し（重要）
- TEE/StrongBox が Key Attestation で証明するのは **P-256 鍵**。
- 回路が使うのは **BabyJub EdDSA 鍵**（device_pubkey）。
- 両者を繋ぐため、**アテステーションの challenge = device_pubkey の束縛値**
  （例: `Poseidon(device_pubkey_ax, device_pubkey_ay)` を符号化した nonce）とする。
  → 「このハード端末が、この BabyJub device_pubkey を裏書きした」を証明できる。

## フロー
```
[端末] DeviceAttestation.attest(nonce = device_pubkey束縛値)
   ・AndroidKeyStore に StrongBox/TEE の P-256 鍵を生成（setAttestationChallenge(nonce)）
   ・証明書チェーン（PEM）と公開鍵を返す
        │  chain + device_pubkey
        ▼
[検証ゲート] verify_attestation.js
   1. チェーン署名連結 / 2. root ピン留め(本番 Google 根)
   3. Key Attestation 拡張(OID …2.1.17) / 4. challenge == device_pubkey束縛値
   5. security level ∈ {TEE, StrongBox} / 6. origin == GENERATED
        │  OK なら「実機裏書き済み」
        ▼
[登録] registerDevice(device_pubkey)  ← ゲートを通った鍵だけ登録
        ▼
[以降] 端末は回路内で device_pubkey で観測を署名（既存 M3）
```

## 実装
- ネイティブ（Android）: `android/.../DeviceAttestation.kt` — StrongBox優先でP-256鍵生成、
  attestationChallenge=nonce、PEMチェーン返却。`MainActivity.kt` に MethodChannel 配線。
  アプリ側は `lib/core/device_attestation.dart`（既存インターフェース）から呼ぶ。
- 検証ゲート: `scripts/attestation/verify_attestation.js` — 上記1〜6を検証。
  自己テスト `test_verify.js` で 8/8 パス（正当許可／challenge流用・ソフト鍵・インポート鍵・
  拡張なし・不正root を拒否）。実機なしで検証ロジックを確認済み。

## 塞げる脅威
- **Sybil（偽端末量産）**: ハード鍵でない参加を弾く。攻撃者は実機×アテステーションが必要に。
- **入力真正性（一部）**: 少なくとも「正規実機・正規アプリの鍵」であることを担保。
  （センサ値そのものの真正化は、TEE内センサ署名や zkML と組み合わせて段階的に）

## 限界（正直に）
- **アプリ改ざん耐性は完全ではない**: 鍵はハード保護でも、アプリのセンサ読み取り経路を
  改ざんされれば偽値は入りうる。強化には Play Integrity / TEE内センサ署名が要る。
- **root/失効の運用**: 本番は Google のハードウェアアテステーション根をピン留めし、
  証明書失効（CRL）を確認すること。ここでは root ピンのみ実装（テストは自己生成root）。
- **P-256↔BabyJub 束縛**: challenge に device_pubkey を入れる方式。将来は登録を
  オンチェーン化（アテステーション検証済みの device_pubkey を登録レジストリへ）。

## 位置づけ
★2 の核（検証ゲート）を実装。ドローン署名RemoteID(既存M3)と合わせ、
「入力の出所（ドローン・端末とも）を暗号で裏取り」する層が揃う。
残るは Play Integrity / TEE内センサ署名 / zkML による「センサ値そのもの」の真正化。
