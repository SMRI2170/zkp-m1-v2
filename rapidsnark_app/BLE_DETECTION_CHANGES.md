# BLE リモートID 検知強化 — 変更詳細

## 概要

Remote ID の検知カバレッジ拡大、未解析データの可視化、BLE スキャン安定化を目的とした一連の変更。

---

## 1. 検知パターン拡張

### 変更ファイル
- `lib/domain/uav_telemetry.dart`
- `lib/main.dart`（`UavTelemetryPacket` クラスのコピー）

### 変更前の対応パターン

| パターン | 識別方法 |
|---|---|
| OpenDroneID 標準 | Service UUID `0xFFFA` |
| DJI 旧機種 | Manufacturer Data Company ID `0x2005` のみ |

### 変更後の対応パターン

| パターン | 識別方法 | 追加理由 |
|---|---|---|
| OpenDroneID 標準 | Service UUID `0xFFFA` | 既存 |
| **App Code プレフィックス付き** | `0xFFFA` Service Data 先頭の `0x0D` を除去 | opendroneid-core-c の実装が先頭に App Code を付与する場合がある |
| DJI 旧機種 | Manufacturer Data `0x2005` | 既存 |
| **DJI 新ファーム** | Manufacturer Data `0x2006` | 新世代ファームウェアで Company ID が変更された |
| **Parrot** | Manufacturer Data `0x0043` | Parrot ANAFI 等の対応 |
| **Autel Robotics** | Manufacturer Data `0x0417` | Autel EVO 等の対応 |
| **Skydio** | Manufacturer Data `0x06D6` | Skydio 2 / X10 等の対応 |

### 主な実装変更点

#### App Code (0x0D) プレフィックス除去

```dart
// 変更前
static List<int>? extractFromServiceData(Map<dynamic, List<int>> serviceData) {
  for (final entry in serviceData.entries) {
    final key = entry.key.toString().toLowerCase();
    if (key.contains('fffa')) return entry.value;  // 先頭が 0x0D でも返していた
  }
  return null;
}

// 変更後
static List<int>? extractFromServiceData(Map<dynamic, List<int>> serviceData) {
  for (final entry in serviceData.entries) {
    final key = entry.key.toString().toLowerCase();
    if (!key.contains('fffa')) continue;
    final raw = entry.value;
    if (raw.isEmpty) continue;
    if (raw[0] == _odidAppCode && raw.length > 1) return raw.sublist(1); // 0x0D を除去
    return raw;
  }
  return null;
}
```

#### Manufacturer Data の複数メーカー対応

```dart
// 変更前: DJI 旧機種 1社のみ
static const _djiLegacyCompanyId = 0x2005;

static List<int>? extractFromManufacturerData(Map<int, List<int>> manufacturerData) {
  final payload = manufacturerData[_djiLegacyCompanyId];
  if (payload != null && payload.isNotEmpty) return payload;
  return null;
}

// 変更後: 既知メーカーをマップで管理し全てを試行
static const _knownManufacturerIds = <int, String>{
  0x2005: 'DJI (legacy)',
  0x2006: 'DJI',
  0x0043: 'Parrot',
  0x0417: 'Autel Robotics',
  0x06D6: 'Skydio',
};

static List<int>? extractFromManufacturerData(Map<int, List<int>> manufacturerData) {
  for (final id in _knownManufacturerIds.keys) {
    final raw = manufacturerData[id];
    if (raw == null || raw.isEmpty) continue;
    if (raw[0] == _odidAppCode && raw.length > 1) return raw.sublist(1);
    return raw;
  }
  return null;
}
```

---

## 2. BLE Raw スキャナー機能の追加

未解析・未対応のデータを含む全 BLE 広告データをリアルタイムで確認できる画面。

### 追加ファイル

#### `lib/domain/raw_ble_device.dart`

全 BLE デバイスの広告データを保持するデータモデル。

```
RawBleDevice
├─ deviceId        : MAC アドレス / iOS UUID
├─ deviceName      : 広告名
├─ rssi            : 電波強度 (dBm)
├─ serviceUuids    : 広告している UUID リスト
├─ serviceData     : UUID → bytes マップ
├─ manufacturerData: Company ID → bytes マップ
├─ receivedAt      : 受信タイムスタンプ
└─ odidPayload     : OpenDroneID として解析できたペイロード (null = 未解析)
```

#### `lib/providers/raw_ble_provider.dart`

全スキャン結果を最新50件・RSSI 降順で保持する Riverpod Notifier。

#### `lib/features/ble_raw_scan/ble_raw_scan_page.dart`

BLE Raw タブの UI 実装。

### 表示内容

**デバイス一覧（RSSI 強度順）**

```
📡 DJI-XXXX          [Remote ID]  -45 dBm  AA:BB:CC:DD:EE:FF
🔵 Unknown Device    [Unknown]    -72 dBm  11:22:33:44:55:66
```

**タップで展開される詳細**

| セクション | 内容 |
|---|---|
| Service UUIDs | 広告している全 UUID |
| Service Data | UUID + 16バイト区切り hex dump + ASCII列 |
| Manufacturer Data | Company ID（ブランド名付き）+ hex dump |
| 診断ボックス | 解析結果または失敗理由 |

**hex dump 表示形式（Wireshark 形式）**

```
0000  FA FF 10 00 6F 21 43 01  B4 7E 53 08 92 54 7A 01  ....o!C..~S..Tz.
0010  64 01 00 00 FF FF FF FF  00 00 00 00 00            d............
```
長押しでクリップボードにコピー可能。

**診断ボックス（解析成功の場合）**

```
✓ App Code (0x0D) 検出 → 除去して解析
✓ [Type 1 Proto 0 25B] Location
    35.689500, 139.691700
    Alt(baro)=42.0m  Alt(geo)=43.5m
    SpeedH=2.5m/s  SpeedV=0.0m/s
    Dir=180°  AIRBORNE
```

**診断ボックス（解析失敗の場合）**

```
✗ [Type 1 Proto 0 20B] Location: バイト数不足 (20/25)
✗ [Type 1 Proto 0 25B] Location: 座標がゼロ（未設定）
? [Type 6 Proto 2 25B] 未知タイプ
⚠ OpenDroneID 形式の可能性あり（UUID が 0xFFFA 以外）
ASCII: "DJI..."
```

**未知 Manufacturer Data の診断**

既知ドローンメーカー以外のデータに対しても ASCII・バイト数・type nibble を表示し、OpenDroneID 形式の可能性があれば警告する。

### ナビゲーション

`SafetyUseCasePage`（`main.dart`）のボトムナビゲーションバーに4番目のタブとして追加。

```
[メイン] [詳細] [ログ] [BLE Raw]  ← 追加
```

---

## 3. BLE スキャン アーキテクチャ修正

### 問題

`BleService` と `RawBleNotifier` が独立してスキャンを開始・停止していたため、Android の BLE レート制限（30秒以内に5回まで）に抵触。

```
エラー: App is scanning too frequently
```

### 修正前の構造

```
BleService      → FlutterBluePlus.startScan() ─┐
                                                 ├─ 2本のスキャンが競合
RawBleNotifier  → FlutterBluePlus.startScan() ─┘
```

### 修正後の構造

```
BleService（スキャン管理 1本のみ）
  ├─ packets ストリーム    → bleHistoryProvider / bleServiceProvider
  └─ rawResults ストリーム → RawBleNotifier（BLE Raw タブ）
```

### 変更ファイル: `lib/services/ble_service.dart`

```dart
// 追加: 生 ScanResult ストリーム
final _rawController = StreamController<List<ScanResult>>.broadcast();
Stream<List<ScanResult>> get rawResults => _rawController.stream;

// 変更: スキャン再起動前に 2秒のインターバル
_isScanningSubscription = FlutterBluePlus.isScanning.listen((scanning) async {
  if (!scanning) {
    await Future<void>.delayed(const Duration(seconds: 2)); // 追加
    ...
  }
});

// 変更: タイムアウトを 20秒 → 30秒 に延長
await FlutterBluePlus.startScan(timeout: const Duration(seconds: 30));

// 追加: rawResults にも配信
void _onScanResults(List<ScanResult> results) {
  if (_rawController.hasListener) _rawController.add(results); // 追加
  // 既存の ODID パース処理...
}
```

### 変更ファイル: `lib/providers/raw_ble_provider.dart`

自前スキャンを完全に削除し、`bleServiceProvider` から `rawResults` を購読する形に変更。

```dart
// 変更前: 独立してスキャンを管理
class RawBleNotifier extends AutoDisposeNotifier<...> {
  void _start() {
    FlutterBluePlus.startScan(...); // 独自スキャン
  }
}

// 変更後: BleService の rawResults を共有
class RawBleNotifier extends Notifier<List<RawBleDevice>> {
  @override
  List<RawBleDevice> build() {
    final service = ref.watch(bleServiceProvider); // BleService を共有
    _sub = service.rawResults.listen(_onResults);  // rawResults を購読
    ...
  }
}
```

### レート制限対策のまとめ

| 対策 | 内容 |
|---|---|
| スキャン一本化 | `BleService` のみがスキャンを管理 |
| 再起動インターバル | スキャン終了後 2秒待ってから再開 |
| タイムアウト延長 | 20秒 → 30秒（start/stop 頻度を約33%削減） |

---

## 4. ビルド修正

### `main.dart` 削除済みファイルの import 修正

リファクタリングで削除されたファイルへの import が残っていたため修正。

```dart
// 削除
import 'drone_detection/drone_camera_page.dart'; // 削除済みファイル
import 'uav_yolo_detector.dart';                 // パス変更

// 追加
import 'detection/uav_yolo_detector.dart';       // 新しいパス
```

### `ProviderScope` の追加

`BleRawScanPage` が Riverpod (`ConsumerWidget`) を使用するため、アプリ全体を `ProviderScope` で囲む。

```dart
// 変更前
runApp(const RapidsnarkApp());

// 変更後
runApp(const ProviderScope(child: RapidsnarkApp()));
```

### Gradle kotlin-dsl キャッシュ破損への対処

```bash
# 破損したキャッシュを削除
rm -rf ~/.gradle/caches/8.12/kotlin-dsl
rm -rf android/.gradle
flutter clean
flutter pub get
```

---

## ファイル一覧

### 新規作成

| ファイル | 内容 |
|---|---|
| `lib/domain/raw_ble_device.dart` | 生 BLE 広告データモデル |
| `lib/providers/raw_ble_provider.dart` | BLE Raw スキャン Notifier |
| `lib/features/ble_raw_scan/ble_raw_scan_page.dart` | BLE Raw スキャン UI |

### 変更

| ファイル | 主な変更内容 |
|---|---|
| `lib/domain/uav_telemetry.dart` | App Code 対応・メーカー ID 拡張 |
| `lib/main.dart` | import 修正・ProviderScope 追加・BLE Raw タブ追加・メーカー ID 拡張 |
| `lib/services/ble_service.dart` | rawResults ストリーム追加・再起動インターバル・タイムアウト延長 |
| `lib/providers/raw_ble_provider.dart` | BleService 共有に変更（自前スキャン廃止） |
| `lib/features/safety_proof/safety_proof_page.dart` | BLE Raw タブ追加（※ main.dart 側が実際に使われるため実質未使用） |
