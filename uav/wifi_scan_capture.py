#!/usr/bin/env python3
"""Read Linux iw scan cache without changing channel, connection or monitor mode.

This is the Pi counterpart of Android ScanResult, NOT raw packet capture.
Active scan requests are opt-in and bounded; defaults only read the cache.
Drivers/network managers still determine cache refresh. No monitor/channel changes.
"""
import argparse
from contextlib import ExitStack
import math
import os
from pathlib import Path
import statistics
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import subprocess
import time

from observer_capture import parse_rid_payload, message_fields_for_log
from source_labels import classify,load_rules,text_line
from adaptive_scan import AdaptiveScanPlan
from wifi_beacon_capture import private_output, ODID_PREFIX


def parse_scan(text,include_unknown=False):
    """Parse iw 5.19-style output, including unknown Vendor IEs (-u).

    SSIDs and unrelated vendor data are never returned. Cache timestamps are
    retained separately from the time this process read the cache.
    """
    bss = None
    results = []
    for line in text.splitlines():
        match = re.match(r'^BSS ([0-9a-fA-F:]{17})\(', line)
        if match:
            bss = dict(bssid=match[1].lower(), rssi_dbm=None, frequency_mhz=None,
                       observed_boottime_s=None, cache_age_ms=None, vendor_bodies=[])
            results.append(bss)
            continue
        if bss is None:
            continue
        value = line.strip()
        if match := re.fullmatch(r'signal: (-?\d+(?:\.\d+)?) dBm', value):
            bss['rssi_dbm'] = float(match[1])
        elif match := re.fullmatch(r'freq: (\d+(?:\.0+)?)', value):
            bss['frequency_mhz'] = int(float(match[1]))
        elif match := re.fullmatch(r'last seen: (\d+(?:\.\d+)?)s \[boottime\]', value):
            bss['observed_boottime_s'] = float(match[1])
        elif match := re.fullmatch(r'last seen: (\d+) ms ago', value):
            bss['cache_age_ms'] = int(match[1])
        elif match := re.fullmatch(r'Vendor specific: OUI ([0-9a-fA-F:]{8}), data:((?: [0-9a-fA-F]{2})*)', value):
            body = bytes.fromhex(match[1].replace(':', '') + match[2].replace(' ', ''))
            if include_unknown or body.startswith(ODID_PREFIX):
                bss['vendor_bodies'].append(body)
    return results


def observations(bss, node_id, polled_at, rules=(),include_unknown=False):
    for body in (bss['vendor_bodies'] or ([b''] if include_unknown else [])):
        try:
            if not body.startswith(ODID_PREFIX):
                raise ValueError('VENDOR_IE_UNAVAILABLE' if not body else 'UNCLASSIFIED_VENDOR_IE')
            if len(body) <= 5:
                raise ValueError('ODID IE has no payload')
            parsed=[m for _,m in parse_rid_payload(body[5:])]
            messages = [message_fields_for_log(m) for m in parsed]
            uas_ids=[m.uas_id for m in parsed if m.uas_id]
            status, reason = 'decoded', None
        except ValueError as exc:
            messages, uas_ids, status, reason = [], [], 'invalid', str(exc)
        age = bss['cache_age_ms']
        yield dict(
            schema_version='wifi_observation_v1', node_id=node_id, source_type='real_capture',
            observation_kind='linux_scan_cache', rx_phy='wifi_beacon',
            frame_type='wifi_beacon_remote_id_candidate' if body.startswith(ODID_PREFIX) else 'wifi_vendor_candidate',
            vendor_format='opendroneid_candidate' if body.startswith(ODID_PREFIX) else 'unclassified_wifi_candidate',
            polled_at_utc=datetime.fromtimestamp(polled_at, timezone.utc).isoformat(),
            received_at_utc=None if age is None else datetime.fromtimestamp(polled_at - age / 1000, timezone.utc).isoformat(),
            monotonic_time_us=None if bss['observed_boottime_s'] is None else round(bss['observed_boottime_s'] * 1000000),
            time_basis='kernel_scan_cache_age_not_raw_packet_timestamp',
            cache_age_ms=age, cache_stale=age is None or age > 30000,
            clock_sync_method='unknown', clock_offset_estimate_ms=None, time_uncertainty_ms=None,
            rssi_dbm=bss['rssi_dbm'], frequency_mhz=bss['frequency_mhz'],
            rssi_missing_reason=None if bss['rssi_dbm'] is not None else 'IW_SIGNAL_ABSENT',
            bssid=bss['bssid'], transmitter_identifier_if_observed=None,
            sequence_control=None, beacon_tsf_us=None, frame_digest=None,
            frame_digest_scope='unavailable_linux_scan_cache',
            vendor_content_digest=hashlib.sha256(body).hexdigest(),
            odid_counter=body[4] if len(body) > 4 else None,
            odid_payload_hex=body[5:].hex(), rid_parse_status=status, rid_parse_reason=reason,
            messages=messages, claimed_uas_ids=uas_ids, raw_vendor_ie_hex=body.hex(),
            source_annotation=classify(bss['bssid'],uas_ids,rules),physical_packet_match='unconfirmed',
            receiver_position=None, receiver_position_missing_reason='NOT_CONFIGURED',
            absolute_power_calibrated=False)


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    x = (len(ordered) - 1) * fraction
    i = int(x)
    return ordered[i] + (ordered[min(i + 1, len(ordered) - 1)] - ordered[i]) * (x - i)


class UpdateMetrics:
    """Intervals of timestamped RSSI updates, never poll or packet-rate claims."""
    def __init__(self, started_boottime):
        self.started = started_boottime
        self.previous = {}
        self.intervals = []
        self.rssi_count = 0
        self.missing_rssi = 0
        self.current_run_updates = 0

    def add(self, row):
        if row['rssi_dbm'] is None:
            self.missing_rssi += 1
            return
        self.rssi_count += 1
        stamp = row['monotonic_time_us']
        if row['cache_stale'] or row['rid_parse_status'] != 'decoded' or stamp is None:
            return
        seconds = stamp / 1e6
        if seconds < self.started:
            return
        key = (row['bssid'], row['frequency_mhz'])
        old = self.previous.get(key)
        if old is not None and seconds <= old:
            return
        self.previous[key] = seconds
        self.current_run_updates += 1
        if old is not None:
            self.intervals.append(seconds - old)

    def summary(self):
        v = self.intervals
        return dict(rssi_records=self.rssi_count, missing_rssi_records=self.missing_rssi,
                    current_run_timestamped_rssi_updates=self.current_run_updates,
                    interval_count=len(v), interval_min_s=min(v) if v else None,
                    interval_median_s=statistics.median(v) if v else None,
                    interval_p95_s=percentile(v, .95), interval_max_s=max(v) if v else None,
                    interval_basis='same_bssid_frequency_kernel_cache_timestamp_not_packets')


def scan_command(iw, interface, frequency=None):
    command = [iw, 'dev', interface, 'scan', 'trigger']
    if frequency is not None:
        frequencies=frequency if isinstance(frequency,(tuple,list)) else [frequency]
        command += ['freq', *[str(f) for f in frequencies]]
    # A bounded systemd service may grant CAP_NET_ADMIN to this user only.
    try:
        status = Path('/proc/self/status').read_text()
        capabilities = int(re.search(r'^CapEff:\s*([0-9a-f]+)$', status, re.M)[1], 16)
    except (OSError, TypeError):
        capabilities = 0
    return command if os.geteuid() == 0 or capabilities & (1 << 12) else ['sudo', '-n', *command]


def capture(args, iw, run=subprocess.run, monotonic=time.monotonic, sleep=time.sleep,
            wall=time.time, boottime=None):
    if boottime is None:
        boottime = lambda: time.clock_gettime(getattr(time, 'CLOCK_BOOTTIME', time.CLOCK_MONOTONIC))
    seen = set()
    counts = dict(polls=0, cache_bss_entries=0, wifi_candidate_records=0, odid_records=0, fresh_decoded_records=0,
                  duplicate_cache_entries=0, scan_requests=0, scan_accepted=0, scan_failed=0)
    started = monotonic()
    end = started + args.duration
    started_boottime = boottime()
    metrics = UpdateMetrics(started_boottime)
    plan=AdaptiveScanPlan(getattr(args,'discovery_interval',30)) if getattr(args,'adaptive_scan',False) else None
    next_poll = next_scan = started
    consecutive_failures = 0
    stopped_reason = 'duration_complete'
    with ExitStack() as stack:
        output = stack.enter_context(private_output(args.output))
        events = stack.enter_context(private_output(args.events)) if args.events else None
        text_output=stack.enter_context(private_output(args.text_output)) if getattr(args,'text_output',None) else None
        rules=load_rules(getattr(args,'source_registry',None))

        def event(kind, **fields):
            if events:
                events.write(json.dumps(dict(event=kind, elapsed_s=monotonic() - started, **fields)) + '\n')
                events.flush()

        event('start', started_boottime_s=started_boottime, active_scan=args.active_scan, poll_interval_s=args.interval,
              scan_interval_s=args.scan_interval if args.active_scan else None,
              frequency_mhz=args.frequency,scan_strategy='adaptive' if plan else 'fixed_or_all',
              discovery_interval_s=plan.period if plan else None)
        try:
            while monotonic() < end:
                now = monotonic()
                if args.active_scan and now >= next_scan:
                    counts['scan_requests'] += 1
                    try:
                        frequencies=plan.choose(monotonic()) if plan else args.frequency
                        result = run(scan_command(iw, args.interface, frequencies),
                                     capture_output=True, text=True, timeout=min(2, max(.05, end-now)))
                        accepted = result.returncode == 0
                        reason = None if accepted else ('busy' if 'busy' in result.stderr.lower() else
                                 'permission' if any(x in result.stderr.lower() for x in
                                 ['permitted', 'permission', 'password']) else 'driver_rejected')
                    except subprocess.TimeoutExpired:
                        accepted, reason = False, 'timeout'
                    if accepted and plan:plan.accepted(frequencies,monotonic())
                    counts['scan_accepted' if accepted else 'scan_failed'] += 1
                    consecutive_failures = 0 if accepted else consecutive_failures + 1
                    delay = args.scan_interval if accepted else max(args.scan_interval, min(5, 2 ** min(consecutive_failures-1, 3)))
                    next_scan = monotonic() + delay
                    event('scan_request', accepted=accepted, failure_reason=reason, next_delay_s=delay,
                          requested_frequencies_mhz=list(frequencies) if isinstance(frequencies,tuple) else ([frequencies] if frequencies is not None else None),
                          scan_strategy='adaptive' if plan else 'fixed_or_all')
                    if reason == 'permission' or consecutive_failures >= 5:
                        stopped_reason = 'scan_permission_denied' if reason == 'permission' else 'scan_failure_limit'
                        break
                if monotonic() >= end:
                    break
                if monotonic() >= next_poll:
                    result = run([iw, 'dev', args.interface, 'scan', 'dump', '-u'],
                                 capture_output=True, text=True, timeout=min(2, max(.05, end-monotonic())), check=True)
                    entries = parse_scan(result.stdout,getattr(args,'include_unknown_wifi',False))
                    counts['polls'] += 1
                    counts['cache_bss_entries'] += len(entries)
                    for bss in entries:
                        for row in observations(bss, args.node_id, wall(),rules,getattr(args,'include_unknown_wifi',False)):
                            if plan and row['vendor_format']=='opendroneid_candidate':plan.learn(row,monotonic())
                            key = (bss['bssid'], bss['frequency_mhz'], bss['observed_boottime_s'], row['vendor_content_digest'])
                            if key in seen:
                                counts['duplicate_cache_entries'] += 1
                                continue
                            if len(seen) >= 100000:
                                raise ValueError('deduplication limit reached; start another run')
                            seen.add(key)
                            row['scan_strategy']='adaptive' if plan else 'fixed_or_all'
                            row['discovery_interval_s']=plan.period if plan else None
                            row['active_scan_requested'] = args.active_scan
                            row['poll_interval_s'] = args.interval
                            row['scan_request_interval_s'] = args.scan_interval if args.active_scan else None
                            output.write(json.dumps(row) + '\n')
                            output.flush()
                            if text_output:text_output.write(text_line(row)+'\n');text_output.flush()
                            metrics.add(row)
                            counts['wifi_candidate_records'] += 1
                            counts['odid_records'] += row['vendor_format']=='opendroneid_candidate'
                            counts['fresh_decoded_records'] += row['rid_parse_status'] == 'decoded' and not row['cache_stale']
                    next_poll = monotonic() + args.interval
                wake = min(end, next_poll, next_scan if args.active_scan else end)
                sleep(max(0, wake - monotonic()))
        except KeyboardInterrupt:
            stopped_reason = 'interrupted'
        event('end', stopped_reason=stopped_reason)
    summary = dict(counts=counts, updates=metrics.summary(), elapsed_s=monotonic()-started,
                   started_boottime_s=started_boottime,
                   stopped_reason=stopped_reason, source_type='real_capture', observation_kind='linux_scan_cache',
                   active_scan_requested=args.active_scan, poll_interval_s=args.interval,
                   scan_request_interval_s=args.scan_interval if args.active_scan else None,
                   scan_frequency_mhz=args.frequency,scan_strategy='adaptive' if plan else 'fixed_or_all',
                   discovery_interval_s=plan.period if plan else None,physical_packet_match='unconfirmed')
    code = 2 if stopped_reason != 'duration_complete' else (0 if counts['fresh_decoded_records'] else 3)
    return code, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', default='wlan0')
    parser.add_argument('--include-unknown-wifi',action='store_true',help='private diagnostic candidates; not identified Remote ID')
    parser.add_argument('--adaptive-scan',action='store_true')
    parser.add_argument('--discovery-interval',type=float,default=30)
    parser.add_argument('--duration', type=int, default=60)
    parser.add_argument('--interval', type=float, default=1, help='cache polling seconds; minimum 0.1')
    parser.add_argument('--active-scan', action='store_true', help='opt-in iw trigger using sudo -n; never prompts')
    parser.add_argument('--scan-interval', type=float, default=1, help='request spacing after command returns, not a rate guarantee')
    parser.add_argument('--frequency', type=int, help='optional confirmed target frequency MHz; absent means all supported channels')
    parser.add_argument('--events', help='private request diagnostics, no SSID/MAC/payload')
    parser.add_argument('--text-output',help='owner-private readable text alongside JSONL')
    parser.add_argument('--source-registry',help='owner-private JSON list of local source labels')
    parser.add_argument('--node-id', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not math.isfinite(args.discovery_interval) or not 5<=args.discovery_interval<=300:
        parser.error('discovery interval must be 5..300 seconds')
    if args.adaptive_scan and args.frequency is not None:parser.error('adaptive scan and fixed frequency are mutually exclusive')
    if (not 1 <= args.duration <= 3600 or not math.isfinite(args.interval) or not .1 <= args.interval <= 60
            or not math.isfinite(args.scan_interval) or not .25 <= args.scan_interval <= 60):
        parser.error('duration 1..3600s, poll interval 0.1..60s, scan interval 0.25..60s required')
    if args.frequency is not None and not 2400 <= args.frequency <= 7125:
        parser.error('frequency must be 2400..7125 MHz; only use a confirmed target frequency')
    paths=[os.path.abspath(p) for p in [args.output,args.events,args.text_output] if p]
    if len(paths)!=len(set(paths)):parser.error('observation, text and event outputs must have separate paths')
    iw = shutil.which('iw') or shutil.which('iw', path='/usr/sbin:/sbin')
    if not iw:
        parser.error('iw is required')
    try:
        code, summary = capture(args, iw)
        print(json.dumps(summary))
        return code
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status='FAILED', error_type=type(exc).__name__)))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
