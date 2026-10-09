import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:rapidsnark_app/core/v2_observer_capture.dart';

/// Test-only cross-language fixture writer. Never use its fixed keys or ID for
/// field captures; output files belong in a disposable temporary directory.
Future<void> main(List<String> args) async {
  if (args.length != 1) {
    stderr.writeln(
      'usage: dart run tool/generate_v2_observer_capture_fixture.dart <existing-temp-dir>',
    );
    exitCode = 2;
    return;
  }

  final directory = Directory(args.single);
  if (!await directory.exists()) {
    stderr.writeln('output directory must already exist');
    exitCode = 2;
    return;
  }

  final runId = 'phone-interop-run-01';
  final observerId = 'phone-interop-01';
  final profileId = 7;
  final nowMs = DateTime.now().millisecondsSinceEpoch;
  final bucketStartMs = ((nowMs ~/ 60000) + 1) * 60000;
  final firstReceiveMs = bucketStartMs + 5000;
  final advertisements = StreamController<V2ObserverAdvertisement>.broadcast(
    sync: true,
  );
  final recorder = await V2ObserverCaptureRecorder.start(
    advertisements: advertisements.stream,
    privateDirectory: directory,
    config: V2ObserverCaptureConfig(
      runId: runId,
      observerId: observerId,
      calibrationProfileId: profileId,
      sessionKey: List<int>.filled(32, 0x11),
      latitude: 35,
      longitude: 139,
      altitudeMeters: 10,
      locationAccuracyMeters: 3.25,
    ),
  );

  final basicId = List<int>.filled(25, 0);
  basicId[0] = 0x02;
  basicId[1] = 0x12; // ID type 1, UA type 2
  basicId.setRange(2, 2 + 'TEST-PHONE-001'.length, 'TEST-PHONE-001'.codeUnits);

  final firstPayload = [
    0xf2,
    25,
    2,
    ...basicId,
    ..._locationMessage(firstReceiveMs),
  ];
  advertisements.add(
    V2ObserverAdvertisement(
      advertiserId: 'private-test-radio-address',
      eventIdentity: 'event-1',
      receivedAt: DateTime.fromMillisecondsSinceEpoch(
        firstReceiveMs,
        isUtc: true,
      ),
      rssiDbm: -40,
      payload: firstPayload,
    ),
  );
  for (var index = 0; index < 2; index++) {
    final receivedMs = firstReceiveMs + (index + 1) * 100;
    advertisements.add(
      V2ObserverAdvertisement(
        advertiserId: 'private-test-radio-address',
        eventIdentity: 'event-${index + 2}',
        receivedAt: DateTime.fromMillisecondsSinceEpoch(
          receivedMs,
          isUtc: true,
        ),
        rssiDbm: -40,
        payload: _locationMessage(receivedMs),
      ),
    );
  }

  final capturePath = await recorder.stop();
  await advertisements.close();
  stdout.writeln(
    jsonEncode({
      'capture_path': capturePath,
      'run_id': runId,
      'observer_id': observerId,
      'calibration_profile_id': profileId,
      'window_start_unix_ms': bucketStartMs,
      'window_end_unix_ms': bucketStartMs + 60000,
      'event_seq': 1,
    }),
  );
}

List<int> _locationMessage(int receiveMs) {
  final bytes = Uint8List(25);
  final data = ByteData.sublistView(bytes);
  data.setUint8(0, 0x12); // Location, protocol version 2
  data.setInt32(5, 350000000, Endian.little); // 35 degrees latitude
  data.setInt32(9, 1390000100, Endian.little); // 139.00001 degrees longitude
  data.setUint16(15, 2020, Endian.little); // 10m geometric altitude
  data.setUint16(21, (receiveMs % 3600000) ~/ 100, Endian.little);
  return bytes;
}
