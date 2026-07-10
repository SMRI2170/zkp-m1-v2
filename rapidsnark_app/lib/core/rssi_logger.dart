import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// RSSI 較正・整合判定の1行分ログ。
/// 実機 DJI セッションで (rssi, 放送位置, 自GPS) を蓄積し、
/// scripts/rssi/rssi_ranging.py の fit（A/n/σ 較正）に使う。
class RssiLogRow {
  RssiLogRow({
    required this.t,
    required this.source,
    required this.rssi,
    required this.claimedM,
    required this.estM,
    required this.verdict,
    required this.phoneLat,
    required this.phoneLon,
    required this.droneLat,
    required this.droneLon,
    required this.droneAltM,
  });

  final DateTime t;
  final String source;
  final int rssi;
  final double claimedM; // 放送位置と自GPSからの幾何距離
  final double estM; // RSSI 中央値集約からの推定距離
  final String verdict; // 整合 / なりすまし疑い
  final double phoneLat;
  final double phoneLon;
  final double droneLat;
  final double droneLon;
  final double droneAltM;

  static const String header =
      'timestamp,source,rssi,claimed_m,est_m,verdict,'
      'phone_lat,phone_lon,drone_lat,drone_lon,drone_alt_m';

  String toCsv() => [
        t.toIso8601String(),
        source,
        rssi,
        claimedM.toStringAsFixed(2),
        estM.toStringAsFixed(2),
        verdict,
        phoneLat.toStringAsFixed(7),
        phoneLon.toStringAsFixed(7),
        droneLat.toStringAsFixed(7),
        droneLon.toStringAsFixed(7),
        droneAltM.toStringAsFixed(2),
      ].join(',');
}

/// CSV へ追記するロガー（アプリの documents ディレクトリに保存）。
class RssiLogger {
  File? _file;

  Future<File> _ensureFile() async {
    final cached = _file;
    if (cached != null) return cached;
    final dir = await getApplicationDocumentsDirectory();
    final f = File('${dir.path}/rssi_calibration_log.csv');
    if (!await f.exists()) {
      await f.writeAsString('${RssiLogRow.header}\n');
    }
    _file = f;
    return f;
  }

  /// 1 行追記。失敗しても UI を壊さないよう握りつぶす（呼び出し側は unawaited）。
  Future<void> append(RssiLogRow row) async {
    try {
      final f = await _ensureFile();
      await f.writeAsString('${row.toCsv()}\n', mode: FileMode.append);
    } catch (_) {
      // ログ保存の失敗は無視（本機能はデータ収集の付加機能）
    }
  }

  /// 保存先パス（UI 表示・取り出し用）。
  Future<String> filePath() async => (await _ensureFile()).path;
}
