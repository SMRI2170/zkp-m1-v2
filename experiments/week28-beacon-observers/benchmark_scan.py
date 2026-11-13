#!/usr/bin/env python3
"""Run bounded request-spacing profiles sequentially; keep raw observations private.

A profile measures cache updates with RSSI, never physical packet reception rate.
No automatic permanent configuration or network/monitor changes.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'uav'))
from wifi_beacon_capture import private_output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True)
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--duration', type=int, default=20)
    p.add_argument('--profiles', default='2,1,0.5,0.25')
    p.add_argument('--frequency', type=int, help='confirmed target MHz; absent means all channels')
    args = p.parse_args()
    try:
        profiles = [float(x) for x in args.profiles.split(',')]
        if not 1 <= len(profiles) <= 6 or any(not math.isfinite(x) or not .25 <= x <= 60 for x in profiles):
            raise ValueError('1..6 profiles, request spacing 0.25..60s')
        if not 5 <= args.duration <= 60:
            raise ValueError('profile duration must be 5..60s')
        if args.frequency is not None and not 2400 <= args.frequency <= 7125:
            raise ValueError('invalid frequency')
    except ValueError as e:
        p.error(str(e))
    rows = []
    # Reserve outputs before any RF requests; never overwrite old experiments.
    with private_output(args.output_dir / 'profiles.jsonl') as out, private_output(args.output_dir / 'profiles.csv') as csvout:
        fields = ['scan_request_interval_s', 'exit_code', 'elapsed_s', 'scan_requests', 'scan_accepted',
                  'scan_failed', 'current_run_timestamped_rssi_updates', 'rssi_records', 'missing_rssi_records',
                  'interval_count', 'interval_median_s', 'interval_p95_s', 'interval_max_s']
        writer = csv.DictWriter(csvout, fieldnames=fields)
        writer.writeheader()
        for interval in profiles:
            cmd = [sys.executable, str(Path(__file__).with_name('run_observer.py')), '--config', args.config,
                   '--duration', str(args.duration), '--interval', '0.1', '--active-scan', '--scan-interval', str(interval)]
            if args.frequency is not None:
                cmd += ['--frequency', str(args.frequency)]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=args.duration + 30)
                detail = json.loads(result.stdout)
                capture = detail.get('capture') or {}
                row = dict(scan_request_interval_s=interval, exit_code=result.returncode,
                           elapsed_s=capture.get('elapsed_s'), **capture.get('counts', {}), **capture.get('updates', {}))
            except (subprocess.SubprocessError, json.JSONDecodeError) as e:
                detail = dict(status='FAILED', error_type=type(e).__name__)
                row = dict(scan_request_interval_s=interval, exit_code=2)
            rows.append(row)
            out.write(json.dumps(dict(profile=row, detail=detail))+'\n');out.flush()
            writer.writerow({k:row.get(k) for k in fields});csvout.flush()
            print(json.dumps(row), flush=True)
    return 2 if any(r['exit_code'] not in (0,3) for r in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
