import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:geolocator/geolocator.dart';
import 'package:sensors_plus/sensors_plus.dart';

import '../domain/position_snapshot.dart';

/// GPS + 気圧センサーを組み合わせて PositionSnapshot を流すサービス。
class SensorService {
  double? _groundPressureHpa;
  double _currentAltitude = 0.0;

  final _controller = StreamController<PositionSnapshot>.broadcast();
  StreamSubscription<BarometerEvent>? _barometerSub;
  StreamSubscription<Position>? _gpsSub;

  Stream<PositionSnapshot> get snapshots => _controller.stream;
  double get currentAltitude => _currentAltitude;

  void start() {
    // 気圧センサー（初回読み取りで地上基準点を記録）
    _barometerSub = barometerEventStream().listen(
      (event) {
        _groundPressureHpa ??= event.pressure;
        _currentAltitude = _baroToRelativeAlt(event.pressure);
      },
      onError: (_) {},
    );

    // GPS: パーミッション確認後にストリーム開始
    _startGpsStream();
  }

  Future<void> _startGpsStream() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) return;

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      return;
    }

    _gpsSub = Geolocator.getPositionStream(
      locationSettings: Platform.isAndroid
          ? AndroidSettings(
              accuracy: LocationAccuracy.best,
              distanceFilter: 0,
              intervalDuration: const Duration(seconds: 1),
            )
          : const LocationSettings(
              accuracy: LocationAccuracy.best,
              distanceFilter: 0,
            ),
    ).listen(
      (position) {
        _controller.add(PositionSnapshot(
          lat: position.latitude,
          lon: position.longitude,
          alt: _currentAltitude,
          unixTimeSec: DateTime.now().millisecondsSinceEpoch ~/ 1000,
        ));
      },
      onError: (_) {},
    );
  }

  /// QFE 方式: 地上気圧 P0 からの相対高度を返す。
  double _baroToRelativeAlt(double pressureHpa) {
    final p0 = _groundPressureHpa;
    if (p0 == null || p0 <= 0) return 0.0;
    return 44330.0 * (1.0 - math.pow(pressureHpa / p0, 1.0 / 5.255));
  }

  void dispose() {
    _barometerSub?.cancel();
    _gpsSub?.cancel();
    _controller.close();
  }
}
