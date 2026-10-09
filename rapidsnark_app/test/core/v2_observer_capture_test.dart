import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:rapidsnark_app/core/v2_observer_capture.dart';

void main() {
  late Directory directory;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('v2-observer-capture-');
  });

  tearDown(() async {
    if (await directory.exists()) await directory.delete(recursive: true);
  });

  test(
    'writes private cross-node JSONL with Python-compatible tag and dedup',
    () async {
      final advertisements =
          StreamController<V2ObserverAdvertisement>.broadcast(sync: true);
      addTearDown(advertisements.close);
      final sessionKey = List<int>.generate(32, (index) => index);
      final config = V2ObserverCaptureConfig(
        runId: 'run-01',
        observerId: 'phone-01',
        calibrationProfileId: 7,
        sessionKey: sessionKey,
        latitude: 35.0,
        longitude: 139.0,
        altitudeMeters: 10,
        locationAccuracyMeters: 4.5,
      );
      final recorder = await V2ObserverCaptureRecorder.start(
        advertisements: advertisements.stream,
        privateDirectory: directory,
        config: config,
      );

      final basic = List<int>.filled(25, 0)..[0] = 0x02;
      basic[1] = 0x21; // ID type 2, UA type 1
      final uasId = 'UAV-123'.codeUnits;
      basic.setRange(2, 2 + uasId.length, uasId);
      final first = V2ObserverAdvertisement(
        advertiserId: 'rotating-radio-address',
        eventIdentity: 'radio-event-1',
        receivedAt: DateTime.utc(2026, 10, 4, 12, 1),
        rssiDbm: -42,
        payload: basic,
      );
      advertisements.add(first);
      advertisements.add(first); // Buffered scan results may be re-emitted.

      final location = List<int>.filled(25, 0)..[0] = 0x12;
      location.setRange(5, 9, _i32le(350000000));
      location.setRange(9, 13, _i32le(1390000100));
      location[15] = 0xe8;
      location[16] = 0x03; // 1000 * 0.5 - 1000 = -500m
      location[21] = 100;
      final second = V2ObserverAdvertisement(
        advertiserId: 'rotating-radio-address',
        eventIdentity: 'radio-event-2',
        receivedAt: DateTime.utc(2026, 10, 4, 12, 1, 1),
        rssiDbm: -45,
        payload: location,
      );
      advertisements.add(second);

      final path = await recorder.stop();
      final lines = await File(path).readAsLines();
      final records = lines
          .map((line) => jsonDecode(line) as Map<String, dynamic>)
          .toList();
      final observations = records
          .where((record) => record['record_type'] == 'observation')
          .toList();
      expect(records.first['record_type'], 'capture_start');
      expect(records.last['record_type'], 'capture_end');
      expect(
        records.every(
          (record) => record['schema'] == 'signal.observer-capture.v1',
        ),
        isTrue,
      );
      expect(observations, hasLength(2));
      expect(records.last['captured'], 2);
      expect(records.last['capture_event_count'], 2);
      expect(
        records.first['uas_id_tag_scope'],
        'shared_session_key_and_run_id',
      );
      expect(
        records.first['observer_location']['source'],
        'phone_gps_asserted_unverified',
      );
      expect(observations.first['raw_message_hex'], _hex(basic));
      expect(observations.first['uas_id_tag'], 'ed6b94f9a9dbc54b1acbd7fc');
      expect(observations.last['uas_id_tag'], observations.first['uas_id_tag']);
      expect(observations.last['rssi_dbm'], -45);
      expect(observations.last['latitude_deg'], closeTo(35, 0.0000001));
      expect(lines.join('\n'), isNot(contains('UAV-123')));
      expect(lines.join('\n'), isNot(contains('rotating-radio-address')));
      expect(lines.join('\n'), isNot(contains(_hex(sessionKey))));
      expect(await File(path).exists(), isTrue);
    },
  );

  test(
    'rejects malformed message packs without counting them as observations',
    () async {
      final advertisements =
          StreamController<V2ObserverAdvertisement>.broadcast(sync: true);
      addTearDown(advertisements.close);
      final recorder = await V2ObserverCaptureRecorder.start(
        advertisements: advertisements.stream,
        privateDirectory: directory,
        config: V2ObserverCaptureConfig(
          runId: 'run-02',
          observerId: 'pi-01',
          calibrationProfileId: 1,
          sessionKey: List<int>.filled(32, 7),
          latitude: 35,
          longitude: 139,
          altitudeMeters: 0,
          locationAccuracyMeters: 8,
        ),
      );
      advertisements.add(
        V2ObserverAdvertisement(
          advertiserId: 'address',
          eventIdentity: 'invalid-pack',
          receivedAt: DateTime.utc(2026, 10, 4),
          rssiDbm: -70,
          payload: [0xf2, 25, 2, 0x02],
        ),
      );

      final path = await recorder.stop();
      final records = (await File(path).readAsLines())
          .map((line) => jsonDecode(line) as Map<String, dynamic>)
          .toList();
      expect(
        records.where((record) => record['record_type'] == 'observation'),
        isEmpty,
      );
      expect(records.last['captured'], 0);
      expect(records.last['capture_event_count'], 0);
      expect(records.last['unsupported_or_malformed'], 1);
    },
  );

  test(
    'records BLE acquisition failures without leaking platform messages',
    () async {
      final advertisements =
          StreamController<V2ObserverAdvertisement>.broadcast(sync: true);
      addTearDown(advertisements.close);
      final recorder = await V2ObserverCaptureRecorder.start(
        advertisements: advertisements.stream,
        privateDirectory: directory,
        config: V2ObserverCaptureConfig(
          runId: 'run-failure',
          observerId: 'phone-failure',
          calibrationProfileId: 1,
          sessionKey: List<int>.filled(32, 4),
          latitude: 35,
          longitude: 139,
          altitudeMeters: 0,
          locationAccuracyMeters: 5,
        ),
      );

      recorder.recordAcquisitionFailure(
        source: 'ble_scan_start',
        error: StateError('private-device-path/secret detail'),
      );
      recorder.recordAcquisitionFailure(
        source: 'ble_adapter_unavailable',
        error: StateError('radio switched off'),
      );
      final path = await recorder.stop();
      final text = await File(path).readAsString();
      final records = text
          .trim()
          .split('\n')
          .map((line) => jsonDecode(line) as Map<String, dynamic>)
          .toList();
      final failures = records
          .where((record) => record['record_type'] == 'capture_error')
          .toList();

      expect(failures, hasLength(2));
      expect(
        failures.map((record) => record['failure_source']),
        containsAll(['ble_scan_start', 'ble_adapter_unavailable']),
      );
      expect(
        failures.every((record) => record['error_type'] == 'StateError'),
        isTrue,
      );
      expect(text, isNot(contains('private-device-path')));
      expect(records.last['record_type'], 'capture_end');
    },
  );

  test(
    'retains message-pack grouping and tags Location after its Basic ID',
    () async {
      final advertisements =
          StreamController<V2ObserverAdvertisement>.broadcast(sync: true);
      addTearDown(advertisements.close);
      final recorder = await V2ObserverCaptureRecorder.start(
        advertisements: advertisements.stream,
        privateDirectory: directory,
        config: V2ObserverCaptureConfig(
          runId: 'run-pack',
          observerId: 'phone-pack',
          calibrationProfileId: 3,
          sessionKey: List<int>.filled(32, 9),
          latitude: 35,
          longitude: 139,
          altitudeMeters: 0,
          locationAccuracyMeters: 5,
        ),
      );
      final basic = List<int>.filled(25, 0)..[0] = 0x02;
      basic.setRange(2, 9, 'UAV-123'.codeUnits);
      final location = List<int>.filled(25, 0)..[0] = 0x12;
      location.setRange(5, 9, _i32le(350000000));
      location.setRange(9, 13, _i32le(1390000100));
      location[15] = 0xe8;
      location[16] = 0x03;
      location[21] = 100;
      final pack = [0xf2, 25, 2, ...basic, ...location];
      advertisements.add(
        V2ObserverAdvertisement(
          advertiserId: 'pack-address',
          eventIdentity: 'pack-event-1',
          receivedAt: DateTime.utc(2026, 10, 4, 12, 1),
          rssiDbm: -50,
          payload: pack,
        ),
      );

      final path = await recorder.stop();
      final records = (await File(path).readAsLines())
          .map((line) => jsonDecode(line) as Map<String, dynamic>)
          .where((record) => record['record_type'] == 'observation')
          .toList();
      expect(records, hasLength(2));
      expect(records.map((record) => record['capture_event_seq']).toSet(), {1});
      expect(records.map((record) => record['message_pack_index']), [0, 1]);
      expect(
        records.map((record) => record['uas_id_tag']).toSet(),
        hasLength(1),
      );
      expect(
        records.every((record) => record['raw_message_pack_hex'] == _hex(pack)),
        isTrue,
      );
    },
  );
}

List<int> _i32le(int value) => [
  value & 0xff,
  (value >> 8) & 0xff,
  (value >> 16) & 0xff,
  (value >> 24) & 0xff,
];

String _hex(List<int> bytes) =>
    bytes.map((value) => value.toRadixString(16).padLeft(2, '0')).join();
