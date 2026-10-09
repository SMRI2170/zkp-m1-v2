import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

/// Owner-private metadata for one phone observation run.
///
/// The session key is held in memory only. The caller must provision the same
/// fresh key to the other observers through a separate secure channel.
class V2ObserverCaptureConfig {
  factory V2ObserverCaptureConfig({
    required String runId,
    required String observerId,
    required int calibrationProfileId,
    required List<int> sessionKey,
    required double latitude,
    required double longitude,
    required double altitudeMeters,
    required double locationAccuracyMeters,
  }) {
    if (!_opaqueId.hasMatch(runId) || !_opaqueId.hasMatch(observerId)) {
      throw ArgumentError(
        'runId and observerId must be bounded opaque ASCII IDs',
      );
    }
    if (calibrationProfileId < 0 || calibrationProfileId > 0xffffffff) {
      throw ArgumentError.value(calibrationProfileId, 'calibrationProfileId');
    }
    if (sessionKey.length != 32) {
      throw ArgumentError('session key must contain exactly 32 bytes');
    }
    if (!latitude.isFinite ||
        latitude < -90 ||
        latitude > 90 ||
        !longitude.isFinite ||
        longitude < -180 ||
        longitude > 180 ||
        !altitudeMeters.isFinite ||
        !locationAccuracyMeters.isFinite ||
        locationAccuracyMeters < 0) {
      throw ArgumentError('observer location or accuracy is invalid');
    }
    return V2ObserverCaptureConfig._(
      runId,
      observerId,
      calibrationProfileId,
      latitude,
      longitude,
      altitudeMeters,
      locationAccuracyMeters,
      Uint8List.fromList(sessionKey),
    );
  }

  V2ObserverCaptureConfig._(
    this.runId,
    this.observerId,
    this.calibrationProfileId,
    this.latitude,
    this.longitude,
    this.altitudeMeters,
    this.locationAccuracyMeters,
    this._sessionKey,
  );

  static final RegExp _opaqueId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$');

  final String runId;
  final String observerId;
  final int calibrationProfileId;
  final double latitude;
  final double longitude;
  final double altitudeMeters;
  final double locationAccuracyMeters;
  final Uint8List _sessionKey;

  Map<String, Object?> get observerLocation => {
    'latitude_deg': latitude,
    'longitude_deg': longitude,
    'altitude_m': altitudeMeters,
    'accuracy_m': locationAccuracyMeters,
    'source': 'phone_gps_asserted_unverified',
  };

  void clearSecrets() => _sessionKey.fillRange(0, _sessionKey.length, 0);
}

/// Platform-neutral BLE event adapter, allowing the capture format to be
/// tested without a radio or FlutterBluePlus platform channel.
class V2ObserverAdvertisement {
  const V2ObserverAdvertisement({
    required this.advertiserId,
    required this.eventIdentity,
    required this.receivedAt,
    required this.rssiDbm,
    required this.payload,
  });

  /// Used only in memory for per-advertiser tag carry-forward and deduplication.
  final String advertiserId;

  /// Must change for each radio callback, but remain stable when a buffered
  /// ScanResult is re-emitted by the plugin.
  final String eventIdentity;

  final DateTime receivedAt;
  final int rssiDbm;
  final List<int> payload;
}

/// Writes the same private JSONL contract as `uav/observer_capture.py`.
/// Raw RID bytes and asserted phone coordinates stay in app-private storage;
/// this class does not authenticate RID or attest GPS/RSSI hardware.
class V2ObserverCaptureRecorder {
  V2ObserverCaptureRecorder._({
    required this.file,
    required V2ObserverCaptureConfig config,
  }) : _config = config,
       _sink = file.openWrite(mode: FileMode.append);

  static const schema = 'signal.observer-capture.v1';
  static const serviceUuid = '0000fffa-0000-1000-8000-00805f9b34fb';

  final File file;
  final V2ObserverCaptureConfig _config;
  final IOSink _sink;
  final Uint8List _addressPseudonymKey = _randomBytes(32);
  final Map<String, String> _uasTagsByAdvertiser = {};
  final Set<String> _seenEvents = {};
  final Queue<String> _seenEventOrder = Queue<String>();
  late final StreamSubscription<V2ObserverAdvertisement> _subscription;
  Future<void> _writeTail = Future<void>.value();
  Object? _writeError;
  int _captureEventSequence = 0;
  int _capturedMessages = 0;
  int _authenticationPageRecords = 0;
  int _unsupportedOrMalformed = 0;
  bool _stopped = false;

  String get path => file.path;

  /// Mark a radio acquisition failure so the host witness adapter rejects this
  /// capture instead of treating a partial scan as complete. The exception
  /// message is deliberately omitted because platform errors may contain local
  /// paths or other device details.
  void recordAcquisitionFailure({
    required String source,
    required Object error,
  }) {
    const supportedSources = {
      'ble_adapter_unavailable',
      'ble_scan_start',
      'ble_scan_results',
    };
    if (!supportedSources.contains(source)) {
      throw ArgumentError.value(source, 'source');
    }
    _recordFailure(source: source, error: error);
  }

  static Future<V2ObserverCaptureRecorder> start({
    required Stream<V2ObserverAdvertisement> advertisements,
    required Directory privateDirectory,
    required V2ObserverCaptureConfig config,
  }) async {
    await privateDirectory.create(recursive: true);
    final now = DateTime.now().toUtc().millisecondsSinceEpoch;
    final random = Random.secure();
    File? output;
    for (var attempt = 0; attempt < 8; attempt++) {
      final suffix = List.generate(
        8,
        (_) => random.nextInt(16).toRadixString(16),
      ).join();
      final candidate = File(
        '${privateDirectory.path}/observer-${config.observerId}-$now-$suffix.jsonl',
      );
      try {
        await candidate.create(exclusive: true);
        output = candidate;
        break;
      } on FileSystemException {
        if (!await candidate.exists()) rethrow;
      }
    }
    if (output == null) {
      throw StateError('could not allocate a unique capture file');
    }

    final recorder = V2ObserverCaptureRecorder._(file: output, config: config);
    try {
      recorder._queueRecord({
        'schema': schema,
        'record_type': 'capture_start',
        ...recorder._identity,
        'captured_at_utc': _utcNow(),
        'transport': 'BLE',
        'service_uuid': serviceUuid,
        'authentication_status': 'not_evaluated',
        'observer_location': config.observerLocation,
        'raw_payload_included': true,
        'notes': [
          'Phone GPS is self-reported and not hardware-attested.',
          'RID authentication is not evaluated by this capture.',
        ],
      });
      await recorder._writeTail;
      recorder._throwIfWriteFailed();
    } catch (_) {
      config.clearSecrets();
      await recorder._sink.close();
      rethrow;
    }
    recorder._subscription = advertisements.listen(
      recorder._recordAdvertisement,
      onError: recorder._recordStreamError,
    );
    return recorder;
  }

  Map<String, Object?> get _identity => {
    'run_id': _config.runId,
    'observer_id': _config.observerId,
    'calibration_profile_id': _config.calibrationProfileId,
    'uas_id_tag_scope': 'shared_session_key_and_run_id',
  };

  void _recordAdvertisement(V2ObserverAdvertisement event) {
    if (_stopped || _writeError != null) return;
    final fingerprint = '${event.advertiserId}|${event.eventIdentity}';
    if (!_seenEvents.add(fingerprint)) return;
    // Bound in-memory deduplication state for long field sessions.
    _seenEventOrder.addLast(fingerprint);
    if (_seenEventOrder.length > 20000) {
      _seenEvents.remove(_seenEventOrder.removeFirst());
    }

    final messages = _decodePayload(event.payload);
    if (messages == null) {
      _unsupportedOrMalformed++;
      return;
    }

    _captureEventSequence++;
    final unixMs = event.receivedAt.millisecondsSinceEpoch;
    final receivedAtUtc = DateTime.fromMillisecondsSinceEpoch(
      unixMs,
      isUtc: true,
    );
    for (final item in messages) {
      final parsed = item.message;
      if (parsed['message_type'] == 'basic_id') {
        final uasId = parsed.remove('_uas_id') as String;
        _uasTagsByAdvertiser[event.advertiserId] = _sharedUasTag(uasId, parsed);
      }
      final type = parsed['message_type'];
      if (type == 'authentication') _authenticationPageRecords++;
      final record = <String, Object?>{
        'schema': schema,
        'record_type': 'observation',
        ..._identity,
        'captured_at_utc': receivedAtUtc.toIso8601String(),
        'captured_at_unix_ms': unixMs,
        'capture_event_seq': _captureEventSequence,
        'transport': 'BLE',
        'service_uuid': serviceUuid,
        'rssi_dbm': event.rssiDbm,
        'advertiser_tag': _ephemeralTag(
          _addressPseudonymKey,
          'ble-address',
          event.advertiserId,
          _config.runId,
        ),
        'uas_id_tag': _uasTagsByAdvertiser[event.advertiserId],
        'authentication_status': 'not_evaluated',
        'capture_scope': 'single_observer_local_test',
        'observer_location': _config.observerLocation,
        ...parsed,
        'raw_message_hex': _hex(item.bytes),
      };
      if (event.payload.length != 25) {
        record['raw_message_pack_hex'] = _hex(event.payload);
      }
      _queueRecord(record);
      _capturedMessages++;
    }
  }

  String _sharedUasTag(String uasId, Map<String, Object?> parsed) {
    final typedId = '${parsed['id_type']}:${parsed['ua_type']}:$uasId';
    return _ephemeralTag(_config._sessionKey, 'uas-id', typedId, _config.runId);
  }

  String _ephemeralTag(
    List<int> key,
    String domain,
    String value,
    String context,
  ) {
    final parts = [
      domain,
      context,
      value,
    ].map(utf8.encode).toList(growable: false);
    final bytes = BytesBuilder(copy: false)
      ..add(utf8.encode('signal.observer-tag.v1'));
    for (final part in parts) {
      bytes.add(_u32be(part.length));
      bytes.add(part);
    }
    return Hmac(
      sha256,
      key,
    ).convert(bytes.takeBytes()).toString().substring(0, 24);
  }

  void _recordStreamError(Object error, StackTrace stack) {
    _recordFailure(source: 'advertisement_stream', error: error);
  }

  void _recordFailure({required String source, required Object error}) {
    if (_stopped) return;
    _queueRecord({
      'schema': schema,
      'record_type': 'capture_error',
      ..._identity,
      'captured_at_utc': _utcNow(),
      'failure_source': source,
      'error_type': error.runtimeType.toString(),
      'message': 'BLE acquisition failed; this capture must not be used.',
    });
  }

  void _queueRecord(Map<String, Object?> record) {
    _writeTail = _writeTail
        .then((_) async {
          if (_writeError != null) return;
          _sink.write('${jsonEncode(record)}\n');
          await _sink.flush();
        })
        .catchError((Object error, StackTrace stack) {
          _writeError = error;
        });
  }

  void _throwIfWriteFailed() {
    if (_writeError != null) {
      throw StateError('capture file write failed: $_writeError');
    }
  }

  Future<String> stop() async {
    if (_stopped) return path;
    _stopped = true;
    await _subscription.cancel();
    await _writeTail;
    if (_writeError == null) {
      _queueRecord({
        'schema': schema,
        'record_type': 'capture_end',
        ..._identity,
        'captured_at_utc': _utcNow(),
        'captured': _capturedMessages,
        'capture_event_count': _captureEventSequence,
        'authentication_page_records': _authenticationPageRecords,
        'unsupported_or_malformed': _unsupportedOrMalformed,
        'notes': [
          'RSSI is receiver-reported and environment-dependent.',
          'Capture does not establish Remote ID authenticity or observer attestation.',
        ],
      });
      await _writeTail;
    }
    await _sink.flush();
    await _sink.close();
    _config.clearSecrets();
    _addressPseudonymKey.fillRange(0, _addressPseudonymKey.length, 0);
    _uasTagsByAdvertiser.clear();
    _seenEvents.clear();
    _seenEventOrder.clear();
    _throwIfWriteFailed();
    return path;
  }

  static const _typeNames = {
    0: 'basic_id',
    1: 'location',
    2: 'authentication',
    3: 'self_id',
    4: 'system',
    5: 'operator_id',
  };

  static List<_DecodedMessage>? _decodePayload(List<int> input) {
    final payload = List<int>.unmodifiable(input);
    List<List<int>> messages;
    if (payload.length == 25) {
      messages = [payload];
    } else {
      if (payload.length < 3 ||
          (payload[0] >> 4) != 0x0f ||
          (payload[0] & 0x0f) != 2 ||
          payload[1] != 25 ||
          payload[2] < 1 ||
          payload[2] > 9 ||
          payload.length != 3 + 25 * payload[2]) {
        return null;
      }
      messages = List.generate(
        payload[2],
        (index) => payload.sublist(3 + 25 * index, 3 + 25 * (index + 1)),
      );
    }
    final result = <_DecodedMessage>[];
    for (var index = 0; index < messages.length; index++) {
      final bytes = messages[index];
      final parsed = _decodeMessage(bytes);
      if (parsed == null) return null;
      if (payload.length != 25) {
        parsed['message_pack_index'] = index;
        parsed['message_pack_size'] = messages.length;
      }
      result.add(_DecodedMessage(bytes, parsed));
    }
    return result;
  }

  static Map<String, Object?>? _decodeMessage(List<int> bytes) {
    if (bytes.length != 25 || (bytes[0] & 0x0f) != 2) return null;
    final type = bytes[0] >> 4;
    final name = _typeNames[type];
    if (name == null) return null;
    final result = <String, Object?>{
      'message_type': name,
      'protocol_version': 2,
      'message_type_id': type,
    };
    if (type == 0) {
      final rawId = bytes.sublist(2, 22);
      final nul = rawId.indexOf(0);
      final idBytes = nul < 0 ? rawId : rawId.sublist(0, nul);
      if (nul >= 0 && rawId.sublist(nul).any((byte) => byte != 0)) return null;
      if (idBytes.isEmpty ||
          idBytes.any((byte) => byte < 0x20 || byte > 0x7e)) {
        return null;
      }
      final uasId = String.fromCharCodes(idBytes);
      if (uasId.trim() != uasId) return null;
      result['id_type'] = bytes[1] >> 4;
      result['ua_type'] = bytes[1] & 0x0f;
      result['_uas_id'] = uasId;
    } else if (type == 1) {
      final latitudeE7 = _i32le(bytes, 5);
      final longitudeE7 = _i32le(bytes, 9);
      final altitude = _u16le(bytes, 15);
      final timestamp = _u16le(bytes, 21);
      if (latitudeE7 < -900000000 ||
          latitudeE7 > 900000000 ||
          longitudeE7 < -1800000000 ||
          longitudeE7 > 1800000000 ||
          (timestamp != 0xffff && timestamp >= 36000)) {
        return null;
      }
      result['latitude_deg'] = latitudeE7 / 1e7;
      result['longitude_deg'] = longitudeE7 / 1e7;
      result['altitude_geo_m'] = altitude == 0xffff
          ? null
          : altitude * 0.5 - 1000;
      result['rid_timestamp_raw'] = timestamp == 0xffff ? null : timestamp;
      result['rid_seconds_within_hour'] = timestamp == 0xffff
          ? null
          : timestamp / 10;
    } else if (type == 2) {
      final page = bytes[1] & 0x0f;
      result['auth_type'] = bytes[1] >> 4;
      result['auth_data_page'] = page;
      if (page == 0) {
        final lastPage = bytes[2];
        final length = bytes[3];
        if (lastPage >= 16 || length > 17 + lastPage * 23) return null;
        result['auth_last_page_index'] = lastPage;
        result['auth_length'] = length;
        result['auth_timestamp_2019'] = _u32le(bytes, 4);
        result['auth_data_hex'] = _hex(bytes.sublist(8, 25));
      } else {
        result['auth_last_page_index'] = null;
        result['auth_length'] = null;
        result['auth_timestamp_2019'] = null;
        result['auth_data_hex'] = _hex(bytes.sublist(2, 25));
      }
    }
    return result;
  }

  static String _utcNow() => DateTime.now().toUtc().toIso8601String();

  static Uint8List _randomBytes(int length) {
    final random = Random.secure();
    return Uint8List.fromList(
      List.generate(length, (_) => random.nextInt(256)),
    );
  }

  static List<int> _u32be(int value) => [
    (value >> 24) & 0xff,
    (value >> 16) & 0xff,
    (value >> 8) & 0xff,
    value & 0xff,
  ];

  static int _u16le(List<int> bytes, int offset) =>
      bytes[offset] | (bytes[offset + 1] << 8);

  static int _u32le(List<int> bytes, int offset) =>
      _u16le(bytes, offset) | (_u16le(bytes, offset + 2) << 16);

  static int _i32le(List<int> bytes, int offset) {
    final value = _u32le(bytes, offset);
    return value >= 0x80000000 ? value - 0x100000000 : value;
  }

  static String _hex(List<int> bytes) =>
      bytes.map((value) => value.toRadixString(16).padLeft(2, '0')).join();
}

class _DecodedMessage {
  const _DecodedMessage(this.bytes, this.message);

  final List<int> bytes;
  final Map<String, Object?> message;
}
