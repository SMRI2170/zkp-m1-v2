#!/usr/bin/env python3
"""Explicit, bounded fast acquisition using existing sudo authorization only."""
import argparse
import math
import os
from pathlib import Path
import pwd
import uuid


def command(base, duration, interval, frequency, user):
    if not 1 <= duration <= 3600 or not math.isfinite(interval) or not .25 <= interval <= 60:
        raise ValueError('duration 1..3600, scan interval 0.25..60 seconds required')
    if frequency is not None and not 2400 <= frequency <= 7125:
        raise ValueError('frequency must be 2400..7125 MHz')
    cmd = ['sudo', 'systemd-run', '--wait', '--pipe', '--collect',
           '--unit=zkp-scan-' + uuid.uuid4().hex[:12], '--uid=' + user,
           '--property=RuntimeMaxSec=' + str(duration + 25), '--property=MemoryMax=128M',
           '--property=AmbientCapabilities=CAP_NET_ADMIN', '--property=CapabilityBoundingSet=CAP_NET_ADMIN',
           str(base / 'run'), '--duration', str(duration), '--interval', '0.1',
           '--active-scan', '--scan-interval', str(interval)]
    if frequency is not None:
        cmd += ['--frequency', str(frequency)]
    return cmd


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--duration', type=int, default=60)
    p.add_argument('--scan-interval', type=float, default=.25)
    p.add_argument('--frequency', type=int, help='confirmed target MHz; absent means all supported channels')
    args = p.parse_args()
    if os.getuid() == 0:
        p.error('launch as the observer user; sudo is scoped to the bounded service')
    release = Path(__file__).resolve().parents[2]
    base = release.parent.parent
    if release.parent.name != 'releases' or base.name != 'zkp-beacon-observer':
        p.error('install into the versioned release layout first')
    try:
        cmd = command(base, args.duration, args.scan_interval, args.frequency, pwd.getpwuid(os.getuid()).pw_name)
    except ValueError as e:
        p.error(str(e))
    os.execvp(cmd[0], cmd)


if __name__ == '__main__':
    main()
