#!/usr/bin/env python3
"""Bounded on-demand Pi scan-cache observer; never starts an unattended service."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'uav'))
from wifi_beacon_capture import private_output


def read_config(path):
    cfg = json.loads(path.read_text())
    if cfg.get('node_id') not in ['observer-a', 'observer-b', 'observer-c', 'observer-d', 'observer-e', 'observer-f']:
        raise ValueError('node_id must identify observer-a through observer-f')
    if not isinstance(cfg.get('interface'), str) or not cfg['interface'] or len(cfg['interface']) > 32:
        raise ValueError('invalid interface')
    return cfg


def limits():
    if sys.platform != 'linux':
        raise ValueError('this launcher is for Linux Pi nodes')
    resource.setrlimit(resource.RLIMIT_AS, (128 * 1024**2, 128 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024**2, 20 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.nice(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--duration', type=int, default=60)
    parser.add_argument('--interval', type=float, default=1)
    parser.add_argument('--active-scan', action='store_true')
    parser.add_argument('--scan-interval', type=float, default=1)
    parser.add_argument('--frequency', type=int)
    parser.add_argument('--source-registry',type=Path)
    args = parser.parse_args()
    if (not 1 <= args.duration <= 3600 or not math.isfinite(args.interval) or not .1 <= args.interval <= 60
            or not math.isfinite(args.scan_interval) or not .25 <= args.scan_interval <= 60):
        parser.error('duration 1..3600, poll interval 0.1..60, scan interval 0.25..60 seconds')
    if args.frequency is not None and not 2400 <= args.frequency <= 7125:
        parser.error('frequency must be 2400..7125 MHz')
    try:
        cfg = read_config(args.config)
        limits()
        iw = shutil.which('iw') or shutil.which('iw', path='/usr/sbin:/sbin')
        if not iw or not (Path('/sys/class/net') / cfg['interface']).exists():
            raise ValueError('configured interface or iw missing')
        if args.check:
            print(json.dumps(dict(status='READY_FOR_SCAN_CACHE', node_id=cfg['node_id'],
                                  interface=cfg['interface'], python=sys.version.split()[0],
                                  memory_limit_mib=128, file_limit_mib=20, nice=os.nice(0),
                                  active_scan_requested=args.active_scan, poll_interval_s=args.interval,
                                  scan_request_interval_s=args.scan_interval if args.active_scan else None,
                                  automatic_start=False)))
            return 0
        if args.self_test:
            return subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'uav'),
                                   '-p', 'test_wifi*.py', '-v'], timeout=60).returncode
        run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        folder = ROOT / 'captures' / cfg['node_id'] / run
        command = [sys.executable, str(ROOT / 'uav/wifi_scan_capture.py'), '--interface', cfg['interface'],
                   '--node-id', cfg['node_id'], '--duration', str(args.duration), '--interval', str(args.interval),
                   '--output', str(folder / 'observations.jsonl'), '--events', str(folder / 'events.jsonl'),
                   '--text-output',str(folder / 'observations.txt')]
        if args.source_registry:command+=['--source-registry',str(args.source_registry)]
        if args.active_scan:
            command += ['--active-scan', '--scan-interval', str(args.scan_interval)]
        if args.frequency is not None:
            command += ['--frequency', str(args.frequency)]
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = child.communicate(timeout=args.duration + 20)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            timed_out = True
            os.killpg(child.pid, signal.SIGTERM)
            try:
                stdout, stderr = child.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                stdout, stderr = child.communicate()
        summary = dict(node_id=cfg['node_id'], run_id=run, source_type='real_capture',
                       observation_kind='linux_scan_cache', exit_code=child.returncode, timed_out=timed_out,
                       memory_limit_mib=128, file_limit_mib=20,
                       child_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                       duration_s=args.duration, interval_s=args.interval, physical_packet_match='unconfirmed')
        try:
            summary['capture'] = json.loads(stdout)
        except json.JSONDecodeError:
            summary['capture'] = None
        # stderr may contain local details; keep it owner-private, never in stdout.
        with private_output(folder / 'summary.json') as file:
            file.write(json.dumps(summary, indent=2) + '\n')
        if stderr:
            with private_output(folder / 'errors.log') as file:
                file.write(stderr)
        print(json.dumps(summary))
        return 2 if timed_out else child.returncode
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status='FAILED', error_type=type(exc).__name__)))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
