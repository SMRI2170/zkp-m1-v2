#!/usr/bin/env python3
"""Verify/extract a code-only Pi kit into a NEW release. Preserve configs and old captures.

Run as pi. --activate explicitly changes launchers; --role selects the intended service.
No package installation, key copying, raw-data migration or automatic old-data deletion.
"""
import argparse
import hashlib
import json
import os
import shutil
import importlib.util
import re
from pathlib import Path,PurePosixPath
import subprocess
import sys
import tarfile
import uuid


def verified_members(archive,expected):
    if len(expected)>500:raise ValueError('source count limit')
    files={};total=0
    with tarfile.open(archive,'r:gz') as tar:
        for m in tar.getmembers():
            path=PurePosixPath(m.name)
            if not m.isfile() or path.is_absolute() or '..' in path.parts or m.name not in expected or m.name in files:
                raise ValueError('archive member rejected')
            total+=m.size
            if m.size>4*1024**2 or total>32*1024**2:raise ValueError('source size limit')
            data=tar.extractfile(m).read()
            if hashlib.sha256(data).hexdigest()!=expected[m.name]:raise ValueError('source hash mismatch')
            files[m.name]=data
    if set(files)!=set(expected):raise ValueError('source set mismatch')
    return files


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kit',type=Path,required=True)
    p.add_argument('--node-id',choices=['observer-'+c for c in 'abcdef'],required=True)
    p.add_argument('--role',choices=['receiver','transmitter'],default='receiver')
    p.add_argument('--activate',action='store_true');a=p.parse_args()
    if os.getuid()==0:p.error('run as pi; only explicit service installation uses sudo')
    if a.role=='transmitter' and a.node_id!='observer-a':p.error('only A is designated transmitter')
    kit=a.kit.resolve();manifest=json.loads((kit/'manifest.json').read_text())
    if manifest['format']!='rid_field_kit_v1':raise ValueError('unknown kit')
    archive=kit/'pi-source.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['payloads'][archive.name]['sha256']:raise ValueError('archive hash mismatch')
    files=verified_members(archive,manifest['sources']['pi'])
    if sys.platform!='linux':p.error('Pi deployment requires Linux')
    if shutil.disk_usage(Path.home()).free<1024**3:raise ValueError('at least 1GiB free disk required')
    mem=Path('/proc/meminfo').read_text()
    if int(re.search(r'^MemAvailable:\s+(\d+)',mem,re.M)[1])<192*1024:raise ValueError('RAM headroom below 192MiB')
    required=['iw']+(['hostapd','hostapd_cli','ip'] if a.role=='transmitter' else [])
    missing=[x for x in required if not shutil.which(x,path=os.environ.get('PATH','')+':/usr/sbin:/sbin')]
    if a.role=='transmitter':missing += [x for x in ['serial','smbus2','bme280'] if importlib.util.find_spec(x) is None]
    if missing:raise ValueError('dependencies missing: '+','.join(missing))
    os.umask(0o077);base=Path.home()/'zkp-beacon-observer'
    if any(x.is_symlink() for x in [base,base/'releases']):raise ValueError('base/release symlinks rejected')
    # New session only by explicit invocation; never auto-roll over an exhausted capture budget.
    release=base/'releases'/('kit-'+manifest['source_hash'][:12]+'-'+uuid.uuid4().hex[:8]);release.mkdir(mode=0o700,parents=True)
    for name,data in files.items():
        target=release/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(data)
    (release/'kit-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    scripts=release/'experiments/week28-beacon-observers'
    subprocess.run([sys.executable,'-m','unittest','discover','-s',str(release/'uav'),'-p','test_wifi*.py'],check=True)
    if not a.activate:
        print('VERIFIED_STAGED_RELEASE '+str(release));return
    subprocess.run([sys.executable,str(scripts/'install_node.py'),'--node-id',a.node_id],check=True)
    subprocess.run(['sudo',sys.executable,str(scripts/('install_flight.py' if a.role=='transmitter' else 'install_boot.py')),'--enable'],check=True)
    print('ACTIVATED_NEW_SESSION_OLD_CAPTURES_RETAINED '+str(release))


if __name__=='__main__':main()
