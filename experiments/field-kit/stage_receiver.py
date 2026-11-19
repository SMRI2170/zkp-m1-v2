#!/usr/bin/env python3
"""Stage and test one receiver release after verified live preservation; never activate it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from install_pi import verified_members
from preserve_receiver import collect,digest,service_evidence,verify_archive


def kit_sources(kit):
    kit=Path(kit)
    for name in ['manifest.json','install_pi.py','pi-source.tar.gz']:
        if (kit/name).is_symlink():raise ValueError('Kit symlink rejected')
    m=json.loads((kit/'manifest.json').read_text())
    if m['format']!='rid_field_kit_v1':raise ValueError('Unknown kit format')
    if m['source_hash']!=hashlib.sha256(json.dumps(m['sources'],sort_keys=True).encode()).hexdigest():raise ValueError('Kit source metadata mismatch')
    for name in ['install_pi.py','pi-source.tar.gz']:
        if digest(kit/name,time.monotonic()+30)[0]!=m['payloads'][name]['sha256']:raise ValueError('Kit payload hash mismatch')
    verified_members(kit/'pi-source.tar.gz',m['sources']['pi'])
    return m


def stage(base,archive,kit,node_id,*,runner=subprocess.run,probe=service_evidence):
    base=Path(base).absolute();kit=Path(kit).absolute();deadline=time.monotonic()+1800
    if node_id not in ['observer-'+x for x in 'bcdef']:raise ValueError('Receiver B--F required')
    manifest=verify_archive(archive,deadline)
    if manifest.get('mode')!='QUIESCENT_LIVE_NODE':raise ValueError('Offline copies cannot authorize live staging')
    before=collect(base,deadline)
    if before!=manifest['files']:raise ValueError('Current source differs from preserved manifest')
    if 'config/node.json' not in before:raise ValueError('Node configuration missing from preservation')
    if json.loads((base/'config/node.json').read_text())['node_id']!=node_id:raise ValueError('Node identity mismatch')
    state=probe()
    if state!=manifest['service_evidence']:raise ValueError('Service/unit changed since preservation')
    current=base/'current'
    if not current.is_symlink() or current.resolve().parent!=base/'releases':raise ValueError('Recognized current release required')
    old_pointer=os.readlink(current);m=kit_sources(kit)
    # Existing installer rechecks Linux, memory, disk and dependencies. No sudo/activation flags.
    result=runner([sys.executable,str(kit/'install_pi.py'),'--kit',str(kit),'--node-id',node_id,'--role','receiver'],
        capture_output=True,text=True,timeout=600,check=True)
    paths=[x.removeprefix('VERIFIED_STAGED_RELEASE ') for x in result.stdout.splitlines() if x.startswith('VERIFIED_STAGED_RELEASE ')]
    if len(paths)!=1:raise ValueError('Unique staged-release receipt required')
    release=Path(paths[0])
    if not release.is_absolute() or release.is_symlink() or release.parent!=base/'releases' or release.name==Path(old_pointer).name:raise ValueError('New versioned release required')
    for name,expected in m['sources']['pi'].items():
        p=release/name
        if p.is_symlink() or digest(p,deadline)[0]!=expected:raise ValueError('Staged source mismatch')
    # Pi 3 /tmp may be a RAM filesystem smaller than the real SD-space reserve.
    # Exercise the unmodified disk guards on the target SD, not a tiny tmpfs.
    with tempfile.TemporaryDirectory(prefix='.stage-tests-',dir=release) as scratch:
        test_env=dict(os.environ,TMPDIR=scratch)
        tests=runner([sys.executable,'-m','unittest','discover','-s',str(release/'experiments/week28-beacon-observers'),'-p','test_*.py'],
            capture_output=True,text=True,timeout=600,check=True,env=test_env)
    if os.readlink(current)!=old_pointer:raise ValueError('Current pointer changed during stage')
    if collect(base,deadline)!=before:raise ValueError('Old captures/config changed during stage')
    if probe()!=state:raise ValueError('Service/unit changed during stage')
    return dict(stage_verified=True,activation_executed=False,service_restarted=False,
        old_captures_and_config_unchanged=True,new_release=str(release),source_hash=m['source_hash'],
        installer_stdout=result.stdout,installer_stderr=result.stderr,test_stdout=tests.stdout,test_stderr=tests.stderr)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--kit',type=Path,required=True)
    p.add_argument('--node-id',required=True);p.add_argument('--receipt',type=Path,required=True)
    a=p.parse_args()
    from audit_receivers import private_path
    receipt=private_path(a.receipt)
    if receipt.exists():p.error('New private receipt required')
    os.umask(0o077);receipt.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if receipt.parent.stat().st_uid!=os.getuid() or receipt.parent.stat().st_mode&0o077:p.error('Owner-private receipt directory required')
    try:result=stage(a.base.resolve(),a.archive,a.kit,a.node_id)
    except Exception as e:
        # Do not call a failed installation successful or remove staged/partial releases.
        detail=dict(status='FAILED',error_type=type(e).__name__,reason=str(e),activation_executed=False,partial_releases_retained=True)
        if isinstance(e,subprocess.CalledProcessError):detail.update(stdout=e.stdout,stderr=e.stderr,returncode=e.returncode)
        with receipt.open('x') as f:json.dump(detail,f,indent=2);f.write('\n')
        raise
    with receipt.open('x') as f:json.dump(dict(status='STAGED_NOT_ACTIVATED',**result),f,indent=2);f.write('\n')
    print(json.dumps(dict(stage_verified=True,activation_executed=False,old_captures_and_config_unchanged=True)))


if __name__=='__main__':main()
