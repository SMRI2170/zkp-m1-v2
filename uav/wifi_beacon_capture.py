#!/usr/bin/env python3
"""Owner-private Wi-Fi Beacon ODID capture/replay; no hardware authentication.

Reuses observer_capture's ASTM decoder. Live input requires an already configured
Linux monitor interface; this tool never changes the control network interface.
Only classic PCAP with radiotap (DLT 127) is supported, not PCAPNG/Ethernet.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import threading

from observer_capture import parse_rid_payload, message_fields_for_log

ROOT = Path(__file__).resolve().parents[1]
ODID_PREFIX = bytes.fromhex('fa0bbc0d')


def decode_beacon(packet):
    """Return one frame's ODID IEs, or [] for a non-Beacon/non-ODID frame.

    Radiotap fields 0..5 are sufficient for flags, channel and signed dBm signal.
    Later fields are skipped via it_len, never mistaken for an antenna signal.
    """
    if len(packet) < 8 or packet[0] != 0:
        raise ValueError('invalid radiotap header')
    length, present = struct.unpack_from('<HI', packet, 2)
    if length < 8 or length > len(packet):
        raise ValueError('invalid radiotap length')
    offset, bitmap = 8, present
    while bitmap & (1 << 31):
        if offset + 4 > length:
            raise ValueError('truncated radiotap presence words')
        bitmap = struct.unpack_from('<I', packet, offset)[0]
        offset += 4
    fields = {}
    for bit, (alignment, size) in enumerate([(8, 8), (1, 1), (1, 1), (2, 4), (2, 2), (1, 1)]):
        if present & (1 << bit):
            offset = (offset + alignment - 1) // alignment * alignment
            if offset + size > length:
                raise ValueError('truncated radiotap field')
            fields[bit] = packet[offset:offset + size]
            offset += size
    flags = fields.get(1, b'\0')[0]
    if flags & 0x40:
        raise ValueError('driver reported bad FCS')
    frame = packet[length:]
    if flags & 0x10:
        if len(frame) < 4:
            raise ValueError('truncated FCS')
        frame = frame[:-4]
    if len(frame) < 2:
        raise ValueError('truncated frame control')
    control = int.from_bytes(frame[:2], 'little')
    if control & 0x00ff != 0x0080:
        return []
    if control & 0x4300:  # DS/protected frames are not this Beacon format.
        raise ValueError('unsupported Beacon flags')
    if len(frame) < 36:
        raise ValueError('truncated Beacon fixed fields')
    ies, pos = [], 36
    while pos < len(frame):
        if pos + 2 > len(frame):
            raise ValueError('truncated IE header')
        kind, size = frame[pos:pos + 2]
        pos += 2
        if pos + size > len(frame):
            raise ValueError('truncated IE body')
        body = frame[pos:pos + size]
        pos += size
        if kind == 221 and body.startswith(ODID_PREFIX):
            if len(body) <= 5:
                raise ValueError('ODID IE has no message')
            ies.append(body)
    records = []
    for body in ies:
        try:
            messages = [message_fields_for_log(m) for _, m in parse_rid_payload(body[5:])]
            status, reason = 'decoded', None
        except ValueError as exc:
            messages, status, reason = [], 'invalid', str(exc)
        records.append(dict(
            frame_type='wifi_beacon_remote_id', rx_phy='wifi_beacon',
            rssi_dbm=struct.unpack('b', fields[5])[0] if 5 in fields else None,
            frequency_mhz=struct.unpack_from('<H', fields[3])[0] if 3 in fields else None,
            rssi_missing_reason=None if 5 in fields else 'RADIOTAP_DBM_SIGNAL_ABSENT',
            transmitter_identifier_if_observed=':'.join(f'{b:02x}' for b in frame[10:16]),
            bssid=':'.join(f'{b:02x}' for b in frame[16:22]),
            sequence_control=int.from_bytes(frame[22:24], 'little'),
            beacon_tsf_us=int.from_bytes(frame[24:32], 'little'),
            frame_digest=hashlib.sha256(frame).hexdigest(),
            frame_digest_scope='80211_frame_without_radiotap_or_fcs',
            vendor_content_digest=hashlib.sha256(body).hexdigest(),
            odid_counter=body[4], rid_parse_status=status, rid_parse_reason=reason,
            odid_payload_hex=body[5:].hex(),
            messages=messages, physical_packet_match='unconfirmed',
        ))
    return records


def read_exact(stream, size, eof_ok=False):
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(size - len(result))
        if not chunk:
            if not result and eof_ok:
                return None
            raise ValueError('truncated PCAP')
        result.extend(chunk)
    return bytes(result)


def pcap_packets(stream):
    header = read_exact(stream, 24)
    formats = {b'\xd4\xc3\xb2\xa1': ('<', 1000000), b'\xa1\xb2\xc3\xd4': ('>', 1000000),
               b'\x4d\x3c\xb2\xa1': ('<', 1000000000), b'\xa1\xb2\x3c\x4d': ('>', 1000000000)}
    if header[:4] not in formats:
        raise ValueError('classic PCAP required (PCAPNG is not supported)')
    endian, scale = formats[header[:4]]
    major, minor, _, _, snaplen, linktype = struct.unpack(endian + 'HHIIII', header[4:])
    if (major, minor) != (2, 4) or linktype != 127 or not 0 < snaplen <= 1048576:
        raise ValueError('PCAP v2.4 with radiotap linktype 127 required')
    while True:
        row = read_exact(stream, 16, eof_ok=True)
        if row is None:
            return
        seconds, fraction, included, original = struct.unpack(endian + 'IIII', row)
        if included > snaplen or included > original or fraction >= scale:
            raise ValueError('invalid PCAP record')
        data = read_exact(stream, included)
        yield seconds + fraction / scale, data, included != original


def normalize(record, timestamp, node_id, source_type):
    return dict(record, schema_version='wifi_observation_v1', node_id=node_id,
                source_type=source_type, observation_kind='raw_management_frame',
                received_at_utc=datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                monotonic_time_us=None, clock_sync_method='unknown',
                clock_offset_estimate_ms=None, time_uncertainty_ms=None,
                receiver_position=None, receiver_position_missing_reason='NOT_CONFIGURED',
                absolute_power_calibrated=False)


def private_output(path):
    """New files only, inside ignored captures/, no symlink components."""
    path = Path(os.path.abspath(path))
    if not any(path.is_relative_to(base) for base in [ROOT / 'captures', ROOT / 'uav/captures']):
        raise ValueError('output must be inside repository captures/ or uav/captures/')
    current = ROOT
    for name in path.relative_to(ROOT).parts[:-1]:
        current /= name
        if current.is_symlink():
            raise ValueError('symlink output directory rejected')
        if not current.exists():
            current.mkdir(mode=0o700)
        if current.stat().st_uid != os.getuid() or current.stat().st_mode & 0o077:
            raise ValueError('capture directories must be current-owner-only (0700)')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    return os.fdopen(fd, 'w', encoding='utf-8', buffering=1)


def consume(stream, output, node_id, source_type):
    counts = Counter()
    for timestamp, packet, truncated in pcap_packets(stream):
        counts['pcap_records'] += 1
        if truncated:
            counts['truncated_frames'] += 1
            continue
        try:
            records = decode_beacon(packet)
        except ValueError:
            counts['malformed_or_bad_fcs_frames'] += 1
            continue
        counts['odid_ies'] += len(records)
        for record in records:
            counts['decoded_ies' if record['rid_parse_status'] == 'decoded' else 'invalid_ies'] += 1
            output.write(json.dumps(normalize(record, timestamp, node_id, source_type)) + '\n')
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--pcap', type=Path, help='existing classic PCAP; always labelled replay')
    source.add_argument('--live-interface', help='already configured Linux monitor interface')
    parser.add_argument('--duration', type=int, default=60)
    parser.add_argument('--node-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.duration <= 3600:
        parser.error('duration must be 1..3600 seconds')
    process, timer = None, None
    try:
        with private_output(args.output) as output:
            if args.pcap:
                with args.pcap.open('rb') as stream:
                    counts = consume(stream, output, args.node_id, 'replay')
            else:
                if not sys.platform.startswith('linux'):
                    raise ValueError('live capture requires Linux; use --pcap for host tests')
                process = subprocess.Popen(['tcpdump', '-i', args.live_interface, '-U', '-s', '4096',
                                            '-w', '-', 'type', 'mgt', 'subtype', 'beacon'], stdout=subprocess.PIPE)
                timer = threading.Timer(args.duration, lambda: process.poll() is None and process.send_signal(signal.SIGINT))
                timer.start()
                counts = consume(process.stdout, output, args.node_id, 'real_capture')
                code = process.wait(timeout=5)
                if code != 0:
                    raise ValueError('tcpdump failed; check interface, permissions and stderr')
        print(json.dumps(dict(counts=counts, source_type='replay' if args.pcap else 'real_capture',
                              physical_packet_match='unconfirmed', new_zkp_proofs=0)))
        return 0 if counts.get('decoded_ies', 0) else 3
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if timer:
            timer.cancel()
        if process and process.poll() is None:
            process.kill()
            process.wait()


if __name__ == '__main__':
    raise SystemExit(main())
