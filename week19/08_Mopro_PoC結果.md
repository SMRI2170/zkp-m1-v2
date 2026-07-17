# Mopro モバイル PoC 結果 — circom プローバを Flutter/Android に載せる

作成日: 2026-07-18 / 目的: 「現行 circom 回路をモバイルで動かせるか」を Mopro で**実機ビルドまで**検証。
関連: [03_モバイル実行の方法](03_モバイル実行の方法.md) / [05_決定ドキュメント](05_決定ドキュメント_ADR.md)。

---

## 結論（実証できたこと）

**circom(Groth16) プローバを Mopro 経由で Flutter アプリに載せ、Android(arm64) の
インストール可能な APK までビルドできた。** ＝ 決定ドキュメントのフェーズ1（Mopro でモバイル標準化）は
**技術的に成立**することを実機ビルドで確認。

生成物（実測）:
- `libmopro_uav_circom.so`（arm64 ネイティブ証明器, **3.0MB**）
- `mopro_flutter_bindings`（iOS+Android の Dart/Kotlin/Swift バインディング）
- Flutter アプリ（`generateCircomProof` / `verifyCircomProof` を呼ぶ）
- **`app-debug.apk`（53MB, arm64）** ← 端末にインストール可能

残る手動ステップ: 実機を接続して `flutter run`（オンデバイスで証明生成→検証を目視確認）。

---

## 実施フロー（再現手順）

```bash
# 1. ツール（このマシンに導入済み）
rustup update stable                 # ← mopro 依存が rustc 1.91+ 要求。1.90→1.97 に更新
cargo install mopro-cli --locked     # mopro CLI 0.3.7
rustup target add aarch64-linux-android aarch64-apple-ios aarch64-apple-ios-sim

# 2. プロジェクト生成（circom アダプタ）
mopro init --adapter circom --project-name mopro_uav_circom
cd mopro_uav_circom

# 3. Android arm64 バインディング
export ANDROID_NDK_HOME=~/Library/Android/sdk/ndk/27.1.12297006
mopro build --mode release --platforms android --architectures aarch64-linux-android --no-auto-update

# 4. Flutter 用バインディング＋アプリ雛形
mopro build --mode release --platforms flutter \
  --architectures aarch64-apple-ios aarch64-apple-ios-sim aarch64-linux-android --no-auto-update
mopro create --framework flutter

# 5. APK ビルド（arm64 のみに絞ると速い）
cd flutter
flutter build apk --debug --target-platform android-arm64
# → build/app/outputs/flutter-apk/app-debug.apk (53MB)
```

---

## つまずき（重要な記録）

| 事象 | 原因 | 回避 |
|---|---|---|
| `nargo` 導入で `tar: Unrecognized archive format` | 最新 v1.0.0-beta.23 が**リリースにバイナリ未添付** | `noirup -v 1.0.0-beta.22` |
| `cargo install mopro-cli` が失敗 | 依存が **rustc 1.91+** 要求（当環境 1.90） | `rustup update stable`（→1.97） |
| **Noir の Android ビルドが失敗** | barretenberg が **Zig の libc++** を要求（NDK と ABI 非互換） | Android は **circom アダプタ**で回避（barretenberg 不要）／Noir を使うなら Zig 導入 |
| Flutter バインディングで `cargo expand` エラー | flutter_rust_bridge が cargo-expand 依存 | `cargo install cargo-expand` |
| **APK が Dart コンパイルで失敗** | テンプレートが `mopro_example_app.dart` を import するが、生成物は `mopro_uav_circom.dart`（プロジェクト名で命名） | import 名を実ファイル名に置換（`mopro_example_app`→`mopro_uav_circom`） |
| APK ビルドが時間切れ | 4 ABI 分の Rust を毎回ビルド | `--target-platform android-arm64` で 1 ABI に限定 |

**教訓**:
- **Android で Noir を使うなら Zig が要る**。circom は arkworks 系で Zig 不要＝Android は circom が楽。
- Mopro の Flutter テンプレートは**プロジェクト名 `mopro_example_app` を前提**にした import があり、
  別名で init すると手直しが要る（既知の軽微な不整合）。

---

## 次の一手

1. **現行の本物の回路に差し替え**: 例の `multiplier2_final.zkey` を、
   `uav_witness_attestation` の `.zkey` ＋ witness 生成器に置換して同じ手順でビルド。
2. **実機で `flutter run`**: Pixel 8 を接続し、オンデバイスで証明生成→検証の時間を実測。
3. iOS もビルドするなら署名設定（開発者証明書）を Xcode で通す。

→ これで [05_決定ドキュメント](05_決定ドキュメント_ADR.md) フェーズ1（Mopro 標準化）は
「設計上の推奨」から「**実機ビルドで裏取り済み**」に格上げできる。

---

## 生成物の場所（このリポジトリ内・ビルド成果物）

- `week19/mopro_uav_circom/`（circom アダプタのプロジェクト一式）
- `week19/mopro_uav/`（Noir アダプタの雛形。Android は Zig 未導入のため未ビルド）
- `week19/noir_experiment/`（Noir 単体の回路＋proof 検証。既出）

※ いずれもビルド成果物が大きい（.so/APK/target）。リポジトリにコミットする場合は成果物を .gitignore 推奨。
