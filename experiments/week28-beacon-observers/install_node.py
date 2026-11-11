#!/usr/bin/env python3
"""Install a local on-demand launcher for an already transferred release.

Run as the ordinary observer user, never sudo. No package/network/SSH changes.
Existing configuration and capture releases are preserved.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import secrets


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--node-id', required=True, choices=['observer-a', 'observer-b', 'observer-c'])
    args = p.parse_args()
    os.umask(0o077)
    if os.getuid() == 0:
        p.error('install as the observer user, not root')
    release = Path(__file__).resolve().parents[2]
    base = release.parent.parent
    if release.parent.name != 'releases' or base.name != 'zkp-beacon-observer':
        p.error('expected ~/zkp-beacon-observer/releases/<version>/ layout')
    config_dir = base / 'config'
    config_dir.mkdir(mode=0o700, exist_ok=True)
    config_file = config_dir / 'node.json'
    config = dict(node_id=args.node_id, interface='wlan0', receiver_position=None,
                  clock_sync_method='unknown', time_uncertainty_ms=None)
    if config_file.exists():
        if json.loads(config_file.read_text()) != config:
            p.error('existing config differs; inspect it rather than overwrite')
    else:
        with config_file.open('x') as f:
            f.write(json.dumps(config, indent=2) + '\n')
    current = base / 'current'
    if current.exists() and not current.is_symlink():
        p.error('current is not a symlink; inspect it manually')
    temporary = base / 'current.new'
    temporary.symlink_to(release.relative_to(base))
    temporary.replace(current)
    run = base / 'run'
    script = '#!/bin/sh\nset -eu\nexec python3 ' + shlex.quote(str(current / 'experiments/week28-beacon-observers/run_observer.py'))
    script += ' --config ' + shlex.quote(str(config_file)) + ' "$@"\n'
    if run.is_symlink():
        p.error('launcher symlink rejected')
    run.write_text(script)
    run.chmod(0o700)
    fast = base / 'fast'
    if fast.is_symlink():
        p.error('fast launcher symlink rejected')
    fast.write_text('#!/bin/sh\nset -eu\nexec python3 ' + shlex.quote(str(current / 'experiments/week28-beacon-observers/start_fast.py')) + ' "$@"\n')
    fast.chmod(0o700)
    marker=config_dir/'marker.json'
    if not marker.exists():
        config=dict(uas_id='PI-RID-'+args.node_id[-1].upper()+'-'+secrets.token_hex(4).upper(),
                    tx_mac='02:'+':'.join(f'{b:02x}' for b in secrets.token_bytes(5)))
        fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(json.dumps(config,indent=2)+'\n')
    transmitter=base/'transmit-marker'
    if transmitter.is_symlink():p.error('transmitter launcher symlink rejected')
    transmitter.write_text('#!/bin/sh\nset -eu\nexec python3 '+shlex.quote(str(current/'experiments/week28-beacon-observers/start_marker.py'))+' "$@"\n')
    transmitter.chmod(0o700)
    print(json.dumps(dict(status='INSTALLED_ON_DEMAND', node_id=args.node_id,
                          automatic_start=False, packages_changed=False)))


if __name__ == '__main__':
    main()
