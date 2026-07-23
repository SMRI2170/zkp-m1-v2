# Changelog — zk-UAV-Proximity-Proof

---

## 2026-05-16

### Flutter アプリ: 案A（動画録画 + YOLO フレーム解析）+ 案B（ライブ bbox プレビュー）

#### 案A — 動画録画 → フレーム抽出 → YOLO（復元）

- `VideoEvidence` クラスを新設（`path` + `recordedAt`）、`PhotoEvidence` を削除
- `_startVideoRecording()`: `CameraController.startVideoRecording()` を呼び出し、100ms ごとに経過タイマーを更新
- `_stopVideoRecordingAndAnalyze()`: 録画停止 → `_selectBestDataPair()` → `_analyzeVideoEvidence()`
- `_analyzeVideoEvidence()`: `_extractVideoFrames()` で 0ms / 1s / 2.5s のフレームを抽出 → YOLO または ML Kit で解析
- `_buildInputsPayload` detectionCommitment: `_photoEvidence.capturedAt` → `_videoEvidence.recordedAt` に変更
- `_runProofFromPhotoEvidence` → `_runProofFromVideoEvidence` に改名し `_videoEvidence` チェックに変更

#### 案B — ライブ YOLO バウンディングボックスプレビュー

- `_startLiveDetection()`: 800ms 周期タイマー → `takePicture()` → YOLO → 一時ファイル削除 → `_liveDetections` 更新
- `_stopLiveDetection()`: タイマーキャンセル・`_liveDetections` クリア
- 録画開始前に `_stopLiveDetection()`、録画停止後に `_startLiveDetection()` を呼ぶことで排他制御
- `_BboxPainter` (`CustomPainter`): プレビューサイズとスクリーンサイズの比率を計算してバウンディングボックスを描画
- カメラプレビューを `LayoutBuilder + CustomPaint` でラップし、bbox をリアルタイム表示

#### UI 変更

| 変更箇所 | 変更内容 |
|---|---|
| ステップバー `③` | 📷「撮影」→ 🎥「録画」|
| メインボタン | シャッター丸ボタン → REC（録画中は赤い停止四角）|
| 録画中 | タイマー `MM:SS` を右側に表示、上端バーが赤に変化 |
| 解析中 | 上端バーがオレンジに変化、スピナー表示 |
| ライブ検知バッジ | 録画停止中に UAV 検知中の件数を緑バッジで表示 |
| `canProve` ボタン | `_runProofFlow` → `_runProofFromVideoEvidence` を直接呼ぶよう変更 |

#### コードクリーンアップ

- `_analyzePhotoEvidence()` を削除（`_analyzeVideoEvidence()` に統合）
- `dispose()` に `_recordingTimer` + `_liveDetectionTimer` のキャンセルを追加
- `flutter analyze` エラー: **0 件**

---

## 2026-05-15

### Flutter アプリ: UI/UX 直感化

#### メインタブ全面リデザイン

- **4ステップ進捗バー**を上部に追加
  - `① BLE → ② GPS → ③ 撮影 → ④ 証明` の現在位置を常時表示
  - 完了ステップはチェックマーク＋緑に変化
- **次のアクションヒント**を下部パネルに常時表示
  - 状態に応じて「① BLE でドローンの Remote ID を受信してください」などを動的に切り替え
- **シャッターボタン**を一眼カメラ風の大型円形ボタンに変更
  - 撮影前: 白い丸ボタン
  - 撮影中: オレンジのスピナー
  - 撮影後: 左に「撮り直す」ボタン、右に UAV 検知バッジ（緑/グレー）が展開
- **ZK 証明ボタン**を全幅に変更し、シャッターボタンと明確に分離
  - 条件が揃うと緑に変化し `verified` アイコンを表示
  - 処理中はインライン spinner＋経過時間を表示
- 録画進捗バーを廃止し、撮影中のみオレンジ不定幅バーを表示
- 上部インジケーターを「解析中スピナー」「撮影完了チェックマーク」に刷新

#### 詳細タブ拡充

- **UAV 検知結果カード**を追加（写真撮影後に表示）
  - 検知サマリー文、ラベルチップ一覧、使用バックエンド情報を表示
- **判定要約・プライバシーカード**を追加（証明実行後に表示）
  - `_verdictSummary`（判定の根拠文）を表示
  - `_privacySummary`（座標非公開の説明）をロックアイコン付きで表示

---

### Flutter アプリ: コードクリーンアップ

| 問題 | 対応 |
|---|---|
| `tabs` リストが `build()` 内で二重ビルドされていた | `tabs` 変数を削除し直接呼び出しに統一 |
| `_isAnalyzingVideo` が `_isCapturing` と完全に重複 | フィールド・代入をすべて削除 |
| `_currentPressureHpa` / `_lastSensorReadAt` / `_lastDroneSeenAt` が書くだけで読まれないデッドステート | 宣言・代入をすべて削除 |
| `_verdictSummary` / `_privacySummary` が計算されるが UI に出ていなかった | 詳細タブに表示するよう修正 |
| `_videoDetectionSummary` / `_videoDetectionLabels` / `_detectionBackendStatus` が UI に出ていなかった | 検知結果カードに表示するよう修正 |
| `_selectBestDataPair` のログに「録画終了」と残っていた | 「撮影時点スナップショット」に修正 |
| `initState` コメントに「自動録画」と残っていた | 「カメラ初期化」に修正 |

- `flutter analyze` の `unused_field` 警告: **24 件 → 0 件**

---

## 2026-05-15（同日・前セッション）

### Flutter アプリ: 動画録画 → 静止画撮影へのリファクタ

**目的**: ドローン写真撮影と Remote ID 検知を同時に行い、ZK 回路へ代入する。GPS 履歴は常時蓄積。

#### GPS・BLE 履歴の常時蓄積化

- `_startLocationStream` の `if (_isRecording)` ガードを削除
  - アプリ起動直後から `_locationHistory` に常時蓄積（最大 20 件）
- `_applyDroneTelemetry` の `if (_isRecording)` ガードを削除
  - BLE 受信直後から `_droneHistory` に常時蓄積（最大 20 件）

#### 録画フローの廃止と撮影フローの新設

| 旧 | 新 |
|---|---|
| `VideoEvidence`（録画パス・開始終了時刻） | `PhotoEvidence`（写真パス・撮影時刻のみ） |
| `_captureEvidenceVideo()` | 削除 |
| `_analyzeVideoEvidence()` | `_analyzePhotoEvidence()` に置き換え |
| `_runProofFromVideoEvidence()` | `_runProofFromPhotoEvidence()` に名称変更 |
| `_startRecording()` / `_stopRecordingAndPrepare()` | 削除 |

#### `_captureAndDetect()` の新設

1 ボタン押下で以下を連続実行:

```
takePicture()                     // カメラ撮影
_selectBestDataPair()             // BLE+GPS のベストペアをスナップショット
_analyzePhotoEvidence()           // YOLO または ML Kit で単枚解析
```

#### `_analyzePhotoEvidence()` の実装

- YOLO モデルがあれば `detectImageFile(path)` で単枚推論
- モデルがなければ既存 ML Kit フォールバックを流用（`SampledVideoFrame` 1 枚として渡す）

#### UI の変更

- 「録画を開始」「録画停止」ボタン → 「撮影して検知」/「撮り直す」ボタン 1 本に統一
- 証明ボタンは全幅に変更し録画ボタンとの混在を解消
- `image_picker` import を削除（不要になったため）

#### `_buildInputsPayload` の修正

- `detectionCommitment` 回路の `frame_time_sec` を `VideoEvidence.recordRequestedAt` → `PhotoEvidence.capturedAt` に変更
- `commitmentSeed` から `recordCompletedAt` 参照を削除

---

## 2026-05-02（前コミット）

### Flutter アプリ: 実ドローン Remote ID 検出の完全対応

#### 対応した検出ギャップ

| 問題 | 対応内容 |
|---|---|
| **Message Pack (type=0xF) 未対応** | `extractAllMessages()` を実装。1 パケットに BasicID・Location・System が束ねられた Message Pack を展開して処理 |
| **System メッセージ (type=4) 破棄** | `tryParseSystem()` を実装。オペレーター位置・高度をパース・ログ出力 |
| **DJI 旧機種 (manufacturerData) 未対応** | `extractFromManufacturerData()` を実装。Company ID `0x2005` を探索 |
| **BLE スキャンギャップ** | 22 秒周期タイマー → 1 秒ポーリング＋`isScanningNow` チェックに変更 |
| **BasicID ログなし** | type=0 受信時に `UAS_ID` を `_log` に記録 |

#### `canProve` のワークフロー修正

```dart
// 修正前（録画必須で証明できなかった）
final canProve = droneReady && locationReady && _videoEvidence != null;

// 修正後（BLE + GPS が揃えば証明可能）
final canProve = droneReady && locationReady;
```

---

### スライド生成スクリプト

#### `generate_opendroneid_slides.py`（35 スライド）

- **Part 5（スライド 28–30）を追加**: Message Pack の必要性・パケット構造・実装コードを解説
- Part 6 のスライド番号を 28–32 → 31–35 に繰り下げ
- まとめスライドに Message Pack 対応項目を追記

#### `generate_ui_slides.py`（17 スライド・新規作成）

- **スライド 1–9**: Flutter アプリ UI 概要（3 タブ構成・各レイヤー・データカード・回路セレクター・証明結果・ログタブ・YOLO 検知）
- **スライド 10–13**: OpenDroneID 検出フロー・`withServices` 問題・`extractAllMessages` コード・`tryParseLocation` デコード詳細
- **スライド 14–17**: 追加が必要だった理由（Pi vs 実ドローン比較表・Message Pack・System+DJI+スキャンギャップ・残課題）
- 全スライド: 左テキスト／右スクリーンショットプレースホルダーのレイアウト
