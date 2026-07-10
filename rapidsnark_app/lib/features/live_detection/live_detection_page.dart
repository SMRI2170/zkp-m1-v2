import 'dart:async';
import 'dart:ui' as ui;
import 'dart:ui' show ImageFilter;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../detection/detection_state.dart';
import '../../providers/detector_provider.dart';

/// カメラプレビューにリアルタイム YOLO 検出オーバーレイを重ねるページ。
/// DroneCameraPage を整理・リネームしたもの。
/// アプリ全体が ProviderScope で包まれているため DroneCameraPageEntry は不要。
class LiveDetectionPage extends ConsumerStatefulWidget {
  const LiveDetectionPage({super.key});

  @override
  ConsumerState<LiveDetectionPage> createState() => _LiveDetectionPageState();
}

class _LiveDetectionPageState extends ConsumerState<LiveDetectionPage>
    with WidgetsBindingObserver {
  CameraController? _cameraController;
  bool _cameraReady = false;
  String _cameraError = '';

  bool _streamStarted = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_initCamera());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    final ctrl = _cameraController;
    if (ctrl != null) {
      if (ctrl.value.isStreamingImages) ctrl.stopImageStream();
      ctrl.dispose();
    }
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final ctrl = _cameraController;
    if (ctrl == null || !ctrl.value.isInitialized) return;
    if (state == AppLifecycleState.inactive) {
      if (ctrl.value.isStreamingImages) ctrl.stopImageStream();
    } else if (state == AppLifecycleState.resumed) {
      _restartStream();
    }
  }

  Future<void> _initCamera() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        if (!mounted) return;
        setState(() => _cameraError = 'カメラが見つかりません。');
        return;
      }

      final camera = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );

      final ctrl = CameraController(
        camera,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.yuv420,
      );

      await ctrl.initialize();
      if (!mounted) {
        await ctrl.dispose();
        return;
      }

      setState(() {
        _cameraController = ctrl;
        _cameraReady = true;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _cameraError = 'カメラ初期化エラー: $e');
    }
  }

  void _startStreamIfReady(DroneDetectionState detectorState) {
    final ctrl = _cameraController;
    if (!_cameraReady || ctrl == null) return;
    if (!detectorState.isReady) return;
    if (_streamStarted || ctrl.value.isStreamingImages) return;

    _streamStarted = true;
    ctrl.startImageStream((frame) {
      // 共有 detectorProvider にフレームを渡す（推論中はスキップされる）
      ref
          .read(detectorProvider.notifier)
          .processFrame(frame, ctrl.description.sensorOrientation);
    });
  }

  void _restartStream() {
    _streamStarted = false;
    _startStreamIfReady(ref.read(detectorProvider));
  }

  @override
  Widget build(BuildContext context) {
    final detectorState = ref.watch(detectorProvider);

    _startStreamIfReady(detectorState);

    final isLandscape =
        MediaQuery.of(context).orientation == Orientation.landscape;

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('ドローン リアルタイム検出'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        actions: [
          _ModelSelector(state: detectorState),
          if (detectorState.latencyMs != null)
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Center(
                child: Text(
                  '${detectorState.latencyMs!.toStringAsFixed(0)} ms',
                  style: const TextStyle(
                    color: Colors.greenAccent,
                    fontSize: 13,
                    fontFeatures: [ui.FontFeature.tabularFigures()],
                  ),
                ),
              ),
            ),
        ],
      ),
      body: Stack(
        fit: StackFit.expand,
        children: [
          if (_cameraError.isNotEmpty)
            Center(
              child: Text(
                _cameraError,
                style: const TextStyle(color: Colors.red),
                textAlign: TextAlign.center,
              ),
            )
          else if (!_cameraReady || _cameraController == null)
            const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircularProgressIndicator(color: Colors.white),
                  SizedBox(height: 12),
                  Text(
                    'カメラを初期化しています...',
                    style: TextStyle(color: Colors.white70),
                  ),
                ],
              ),
            )
          else
            Center(
              child: AspectRatio(
                aspectRatio: isLandscape
                    ? _cameraController!.value.aspectRatio
                    : (1 / _cameraController!.value.aspectRatio),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    CameraPreview(_cameraController!),
                    if (detectorState.isReady)
                      _BoundingBoxOverlay(
                          detections: detectorState.detections),
                    if (detectorState.isReady)
                      _DetectionListOverlay(
                          detections: detectorState.detections),
                  ],
                ),
              ),
            ),
          Align(
            alignment: Alignment.bottomCenter,
            child: _StatusBar(state: detectorState),
          ),
        ],
      ),
    );
  }
}

// ── クラス別カラー / アイコン ────────────────────────────────────────────────

Color _classColor(String label) {
  final l = label.toLowerCase();
  if (l.contains('drone')) return const Color(0xFFFF5252);
  if (l.contains('helicopter')) return const Color(0xFFFFD740);
  if (l.contains('airplane') || l.contains('plane')) return const Color(0xFF40C4FF);
  if (l.contains('bird')) return const Color(0xFF69F0AE);
  return const Color(0xFFB0BEC5);
}

IconData _classIcon(String label) {
  final l = label.toLowerCase();
  if (l.contains('drone')) return Icons.radio_button_checked;
  if (l.contains('helicopter')) return Icons.flight;
  if (l.contains('airplane') || l.contains('plane')) return Icons.airplanemode_active;
  if (l.contains('bird')) return Icons.air;
  return Icons.category;
}

// ── バウンディングボックスオーバーレイ ────────────────────────────────────────

class _BoundingBoxOverlay extends StatelessWidget {
  const _BoundingBoxOverlay({required this.detections});

  final List<DroneDetection> detections;

  @override
  Widget build(BuildContext context) {
    if (detections.isEmpty) return const SizedBox.shrink();
    return CustomPaint(painter: _BoxPainter(detections: detections));
  }
}

class _BoxPainter extends CustomPainter {
  const _BoxPainter({required this.detections});

  final List<DroneDetection> detections;

  @override
  void paint(Canvas canvas, Size size) {
    for (final d in detections) {
      final color = _classColor(d.label);

      final boxPaint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5
        ..color = color;

      final fillPaint = Paint()
        ..style = PaintingStyle.fill
        ..color = color.withValues(alpha: 0.12);

      final rect = Rect.fromLTRB(
        d.box.left * size.width,
        d.box.top * size.height,
        d.box.right * size.width,
        d.box.bottom * size.height,
      );

      final rrect = RRect.fromRectAndRadius(rect, const Radius.circular(10.0));
      canvas.drawRRect(rrect, fillPaint);
      canvas.drawRRect(rrect, boxPaint);

      final labelBgPaint = Paint()
        ..style = PaintingStyle.fill
        ..color = color.withValues(alpha: 0.85);

      final labelStyle = TextStyle(
        color: Colors.black.withValues(alpha: 0.85),
        fontSize: 12,
        fontWeight: FontWeight.w700,
      );

      final label = '${d.label}  ${(d.score * 100).toStringAsFixed(0)}%';
      final tp = TextPainter(
        text: TextSpan(text: label, style: labelStyle),
        textDirection: ui.TextDirection.ltr,
      )..layout(maxWidth: size.width);

      final labelY = rect.top - tp.height - 6 < 0 ? rect.top + 2 : rect.top - tp.height - 6;
      final labelRect = Rect.fromLTWH(rect.left, labelY, tp.width + 12, tp.height + 6);
      canvas.drawRRect(
        RRect.fromRectAndRadius(labelRect, const Radius.circular(6.0)),
        labelBgPaint,
      );
      tp.paint(canvas, Offset(rect.left + 6, labelY + 3));
    }
  }

  @override
  bool shouldRepaint(_BoxPainter old) => old.detections != detections;
}

// ── 左上 検出結果パネル ────────────────────────────────────────────────────────

class _DetectionListOverlay extends StatelessWidget {
  const _DetectionListOverlay({required this.detections});

  final List<DroneDetection> detections;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      top: 12,
      left: 12,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Container(
            constraints: const BoxConstraints(maxWidth: 200),
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.55),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
            ),
            padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
            child: detections.isEmpty
                ? const _EmptyDetectionHint()
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '検出  ${detections.length}件',
                        style: const TextStyle(
                          color: Colors.white54,
                          fontSize: 10,
                          letterSpacing: 0.8,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 8),
                      ...detections.map((d) => _DetectionRow(d)),
                    ],
                  ),
          ),
        ),
      ),
    );
  }
}

class _EmptyDetectionHint extends StatelessWidget {
  const _EmptyDetectionHint();

  @override
  Widget build(BuildContext context) {
    return const Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.search, color: Colors.white38, size: 14),
        SizedBox(width: 6),
        Text(
          'スキャン中...',
          style: TextStyle(color: Colors.white38, fontSize: 12),
        ),
      ],
    );
  }
}

class _DetectionRow extends StatelessWidget {
  const _DetectionRow(this.d);

  final DroneDetection d;

  @override
  Widget build(BuildContext context) {
    final color = _classColor(d.label);
    final icon = _classIcon(d.label);
    final pct = (d.score * 100).round();

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Container(
            width: 26,
            height: 26,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.18),
              borderRadius: BorderRadius.circular(7),
              border: Border.all(color: color.withValues(alpha: 0.5), width: 1),
            ),
            child: Icon(icon, color: color, size: 14),
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                d.label,
                style: TextStyle(
                  color: color,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  height: 1.1,
                ),
              ),
              const SizedBox(height: 3),
              Row(
                children: [
                  SizedBox(
                    width: 72,
                    height: 4,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(2),
                      child: LinearProgressIndicator(
                        value: d.score.clamp(0.0, 1.0),
                        backgroundColor: Colors.white12,
                        valueColor: AlwaysStoppedAnimation<Color>(color),
                      ),
                    ),
                  ),
                  const SizedBox(width: 5),
                  Text(
                    '$pct%',
                    style: const TextStyle(
                      color: Colors.white60,
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ── ステータスバー ────────────────────────────────────────────────────────────

class _StatusBar extends StatelessWidget {
  const _StatusBar({required this.state});

  final DroneDetectionState state;

  @override
  Widget build(BuildContext context) {
    final String message;
    final Color color;

    switch (state.status) {
      case DetectorStatus.loading:
        message = 'モデルを読み込んでいます...';
        color = Colors.amber;
      case DetectorStatus.error:
        message = state.errorMessage ?? 'エラー';
        color = Colors.red;
      case DetectorStatus.ready:
        final n = state.detections.length;
        message = n == 0 ? 'ドローンは検出されていません' : 'ドローン $n 機を検出しました';
        color = n > 0 ? Colors.greenAccent : Colors.white70;
    }

    return Container(
      width: double.infinity,
      color: Colors.black54,
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            if (state.status == DetectorStatus.loading)
              const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(
                  color: Colors.amber,
                  strokeWidth: 2,
                ),
              )
            else if (state.detections.isNotEmpty)
              const Icon(Icons.location_on, color: Colors.greenAccent, size: 16)
            else
              const Icon(Icons.search, color: Colors.white54, size: 16),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                message,
                style: TextStyle(color: color, fontSize: 13),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── モデル選択セレクタ ─────────────────────────────────────────────────────────

class _ModelSelector extends ConsumerWidget {
  const _ModelSelector({required this.state});

  final DroneDetectionState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return PopupMenuButton<String>(
      icon: const Icon(Icons.model_training, color: Colors.white),
      tooltip: 'モデルを選択',
      initialValue: state.selectedModelPath,
      onSelected: (path) {
        ref.read(detectorProvider.notifier).changeModel(path);
      },
      itemBuilder: (context) => const [
        PopupMenuItem(
          value: 'assets/models/new-models/best_float16.tflite',
          child: Text('New Float16'),
        ),
        PopupMenuItem(
          value: 'assets/models/new-models/best_float32.tflite',
          child: Text('New Float32'),
        ),
        PopupMenuItem(
          value: 'assets/models/uav_yolo11n_uav.tflite',
          child: Text('Old YOLO11n'),
        ),
      ],
    );
  }
}
