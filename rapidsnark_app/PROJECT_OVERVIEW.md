# UAV Safety ZK — プロジェクト概要

## 概要

**UAV Safety ZK** は、ドローン（UAV）が自分から 30m 以内に接近したことを、GPS 座標などの個人情報を一切公開せずに暗号学的に証明できる Flutter アプリです。

ゼロ知識証明（ZKP）技術 — 具体的には **Groth16 / Circom + rapidsnark** — をモバイルデバイス上でオンデバイス実行し、「接近があったかどうか」という真偽値だけを第三者に提示します。ドローン苦情対応、事故検証、安全距離監視などのユースケースを想定しています。

---

## 技術スタック

| 分類 | 技術 |
|---|---|
| フレームワーク | Flutter (Dart SDK ^3.8.1) |
| 状態管理 | flutter_riverpod ^3.3.1 |
| ZK 証明エンジン | flutter_rapidsnark (iden3 製) + circom_witnesscalc |
| UAV 検知 | YOLO v11 TFLite (tflite_flutter) + Google ML Kit フォールバック |
| ドローン通信 | OpenDroneID (ASTM F3411-22a) BLE 受信 — flutter_blue_plus |
| センサー | GPS (geolocator) + 気圧計 (sensors_plus) |
| 画像処理 | image パッケージ (バウンディングボックス描画) |
| 動画処理 | camera + video_thumbnail |

---

## アーキテクチャ

```
lib/
├── main.dart                  # エントリポイント (Riverpod ProviderScope)
├── app.dart                   # MaterialApp + テーマ定義
│
├── features/
│   ├── safety_proof/
│   │   └── safety_proof_page.dart   # メイン画面（カメラ・BLE・ZK を統合）
│   └── live_detection/
│       └── live_detection_page.dart # ライブ YOLO 検知ページ
│
├── domain/
│   ├── uav_telemetry.dart     # OpenDroneID BLE パケットのパーサー
│   ├── uav_system_packet.dart # System メッセージ（オペレーター位置）
│   ├── position_snapshot.dart # 利用者 GPS スナップショット
│   └── safety_circuit.dart    # ZK 証明回路プロファイル定義
│
├── services/
│   ├── zk_service.dart        # Witness 計算 → Groth16 証明 → 検証
│   ├── zk_input_builder.dart  # 回路への入力 JSON 生成
│   ├── ble_service.dart       # BLE スキャン補助
│   └── sensor_service.dart    # センサー取得補助
│
├── providers/
│   ├── zk_proof_provider.dart  # ZK 証明状態 (Riverpod Notifier)
│   ├── detector_provider.dart  # YOLO 検知器プロバイダー
│   ├── ble_provider.dart       # BLE スキャン状態
│   └── sensor_provider.dart    # センサー状態
│
├── detection/
│   ├── uav_yolo_detector.dart  # TFLite YOLO 推論ラッパー
│   └── detection_state.dart    # 検知結果モデル
│
└── core/
    ├── poseidon.dart           # Poseidon ハッシュ (Dart ネイティブ実装)
    ├── geo_math.dart           # 緯度経度 → cm 変換ユーティリティ
    └── yuv_to_rgb.dart         # カメラフレーム変換
```

---

## 主要機能

### 1. ZK 証明パイプライン

`ZkService` が以下の 3 ステップを直列で実行します。

```
① Witness 計算 (circom_witnesscalc)
   入力 JSON (座標・時刻・検知フラグ) → witness バイト列

② Groth16 証明生成 (flutter_rapidsnark)
   witness + .zkey → proof JSON + public signals

③ 証明検証 (flutter_rapidsnark)
   proof + public signals + verification_key.json → valid: bool
```

全処理はデバイス内で完結し、生座標データが外部に送信されることはありません。

### 2. OpenDroneID BLE 受信

`UavTelemetryPacket` が ASTM F3411-22a 準拠の BLE パケットをパースします。

- Service UUID `0xFFFA` の Service Data AD を解析
- DJI 旧機種の Manufacturer Data (`Company ID 0x2005`) にも対応
- Message Pack (type=0xF) を分解して BasicID / Location / System を個別処理
- Location メッセージから緯度・経度・気圧高度・GPS 高度・速度・方位・飛行状態を取得

### 3. UAV 検知エンジン

`UavYoloDetector` が以下の優先順でモデルを選択します。

```
1. VisDrone fine-tuned YOLO (uav_visdrone_finetuned_config.json)
2. Roboflow UAV 専用 YOLO (uav_roboflow_drone_config.json)
3. 汎用 YOLO (uav_yolo_config.json)
4. ML Kit Image Labeler / Object Detector (フォールバック)
```

カメラプレビュー上で 800ms ごとにライブ推論を実行し、バウンディングボックスを `CustomPainter` でオーバーレイ描画します。

### 4. センサー統合

| センサー | 役割 |
|---|---|
| GPS (geolocator) | 利用者の緯度・経度を取得 |
| 気圧計 (sensors_plus) | 気圧計高度を計算し GPS 高度を補完 |
| カメラ (camera) | ライブ検知・動画録画・証拠フレーム取得 |

### 5. 証明回路プロファイル

`SafetyCircuitProfile` で 5 種類の Circom 回路を切り替えられます。

| プロファイル | 説明 |
|---|---|
| **Base** | 距離と時刻だけを証明する最小構成 |
| **Detection Flag** | UAV 検知フラグとスコア・クラスを追加 |
| **Commitment** | 座標を Poseidon ハッシュでコミットメント化（最もプライバシー保護が高い） |
| **Feature Classifier** | 外部抽出特徴量を小さな分類器で評価 |
| **Time Series (20点)** | 録画中に収集した最大 20 ペアの時系列データを評価 |

---

## 証明の入力と公開信号

### 入力 (Witness、非公開)

- ドローンの緯度・経度・高度・タイムスタンプ
- 利用者の緯度・経度・高度・タイムスタンプ
- UAV 検知フラグ・スコア (プロファイルによる)
- Poseidon コミットメント (Commitment プロファイル)

### 公開信号 (Public Signals、共有可能)

```json
[
  "1",  // within30: ドローンが 30m 以内に入ったか
  "1",  // distance_ok: 距離閾値以下か
  "1"   // time_ok: 時刻差 5 秒以内か
]
```

Commitment プロファイルではさらに Poseidon ハッシュ値が付加されます。

---

## アセット構成

```
assets/
├── distance30.wcd                          # Base 回路グラフ
├── distance30_groth16.zkey                 # Base 証明鍵
├── distance30_verification_key.json        # Base 検証鍵
├── circuits/
│   ├── distance30_detection_commitment/    # Commitment 回路一式
│   ├── distance30_detection_flag/         # Detection Flag 回路一式
│   ├── distance30_feature_classifier/     # Feature Classifier 回路一式
│   └── distance30_time_series/            # Time Series 回路一式
└── models/
    ├── uav_yolo11n_uav.tflite              # 汎用 YOLO TFLite モデル
    ├── uav_visdrone_finetuned_config.json  # VisDrone fine-tuned 設定
    ├── uav_roboflow_drone_config.json      # Roboflow UAV 専用設定
    └── new-models/                         # 最新 TFLite モデル群
```

---

## UI 構成 (3 タブ)

### タブ 1 — メイン (カメラビュー)

フルスクリーンのカメラプレビューに以下をオーバーレイします。

- **ステップバー**: BLE → GPS → 録画 → 証明 の進捗を視覚化
- **データカード**: ドローン座標 / 利用者座標をリアルタイム表示
- **距離・時刻差チップ**: 30m / 5 秒の閾値に対して色分け表示
- **録画コントロール**: 開始・停止・再録画ボタン
- **ZK 証明ボタン**: 条件が揃った時のみアクティブ化
- **デモ用スキップ**: BLE 未受信時に疑似データを注入してデモ可能

### タブ 2 — 詳細

- 証明回路プロファイルのセレクター
- ステータスログ・処理時間
- UAV 検知結果（フレームプレビュー + ラベル）
- 証明の判定要約・プライバシー説明
- Witness Inputs / Public Signals / Proof JSON の全文表示

### タブ 3 — コンソールログ

- タイムスタンプ付きログ（最大 200 件）
- BLE / 成功 / エラーで色分け
- ログクリアボタン

---

## ユースケース想定フロー

```
1. アプリ起動
   └─ BLE スキャン開始 + GPS 取得開始 + YOLO モデルロード + カメラ初期化

2. ドローン接近
   └─ BLE で Remote ID を受信 → 緯度・経度・高度・タイムスタンプを自動入力
      (BLE が取得できない場合は詳細タブで手入力)

3. 動画録画
   └─ ドローンを画角に捉えて録画 → 停止後にフレーム抽出 + YOLO 解析

4. ZK 証明実行
   └─ Witness 計算 → Groth16 証明生成 → 検証
      → Public Signals (接近の真偽値) を出力
      → 生座標は一切外部に出ない
```

---

## プライバシー設計

- 生の GPS 座標・飛行ルートはデバイス内にとどまり、外部送信しません
- 共有されるのは `within30 / distance_ok / time_ok` の boolean 値のみ
- Commitment プロファイルでは Poseidon ハッシュにより、座標を秘匿したまま証明に紐付けます
- 証明失敗時も座標の生データは外部送信しません

---

## 開発環境

- Flutter SDK: `^3.8.1`
- Dart SDK: `^3.8.1`
- iOS: Runner.xcworkspace (Swift)
- Android: Kotlin + Gradle (build.gradle.kts)
- バージョン: `1.0.0+1`
