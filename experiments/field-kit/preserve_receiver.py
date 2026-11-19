#!/usr/bin/env python3
"""Bounded-memory, verified preservation of receiver captures and configuration.

Offline-copy mode is archive validation, never evidence of a live-node backup.
No extraction, service mutation, activation or old-data deletion is performed.
"""
import argparse
import hashlib
import gzip
import io
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import time

LIMIT=16*1024**3
MAX_FILES=100000
CHUNK=1024**2


def check_deadline(deadline):
    if time.monotonic()>deadline:raise TimeoutError('Preservation deadline reached')


def signature(s):return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def digest(path,deadline):
    check_deadline(deadline)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode):raise ValueError('Regular source files required')
        h=hashlib.sha256()
        while True:
            check_deadline(deadline);data=f.read(CHUNK)
            if not data:break
            h.update(data)
        if signature(before)!=signature(os.fstat(f.fileno())):raise ValueError('Source changed during read')
    return h.hexdigest(),signature(before)


def collect(base,deadline):
    base=Path(base)
    for p in [base,base/'releases',base/'config']:
        if p.is_symlink():raise ValueError('Source root symlink rejected')
    releases=base/'releases'
    if not releases.is_dir():raise ValueError('Release directory required')
    roots=[]
    for release in sorted(releases.iterdir()):
        if release.is_symlink():raise ValueError('Release symlink rejected')
        if not release.is_dir():continue
        capture=release/'captures'
        if capture.is_symlink():raise ValueError('Capture root symlink rejected')
        if capture.exists():roots.append(capture)
    if (base/'config').exists():roots.append(base/'config')
    files={};total=0
    for root in roots:
        for folder,dirs,names in os.walk(root,followlinks=False):
            check_deadline(deadline)
            for name in dirs+names:
                if (Path(folder)/name).is_symlink():raise ValueError('Source symlink rejected')
            for name in sorted(names):
                p=Path(folder)/name;s=p.stat()
                if not stat.S_ISREG(s.st_mode):raise ValueError('Nonregular source rejected')
                total+=s.st_size
                if total>LIMIT or len(files)>=MAX_FILES:raise ValueError('Preservation size/file limit')
                h,sig=digest(p,deadline)
                files[str(p.relative_to(base))]=dict(bytes=sig[2],sha256=h,signature=list(sig))
    if not any('/captures/' in p for p in files):raise ValueError('No capture files; refuse empty preservation')
    return files


def service_evidence():
    show=subprocess.run(['systemctl','show','zkp-rid-observer.service','-p','ActiveState','-p','MainPID'],capture_output=True,text=True,timeout=10,check=True)
    props=dict(line.split('=',1) for line in show.stdout.splitlines() if '=' in line)
    if props.get('ActiveState') not in ['inactive','failed'] or props.get('MainPID')!='0':raise ValueError('Receiver must be quiescent before live preservation')
    unit=subprocess.run(['systemctl','cat','zkp-rid-observer.service'],capture_output=True,text=True,timeout=10,check=True)
    return dict(service_properties=props,unit_text=unit.stdout)


def member_name(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or str(p)!=name:raise ValueError('Noncanonical archive path')
    if len(p.parts)>=2 and p.parts[0]=='config':return name
    if len(p.parts)>=4 and p.parts[0]=='releases' and p.parts[2]=='captures':return name
    raise ValueError('Archive path outside config/capture allowlist')


def verify_archive(path,deadline):
    with tarfile.open(path,'r|gz') as tar:
        members=iter(tar);first=next(members,None)
        if first is None or first.name!='snapshot-manifest.json' or not first.isfile() or first.size>32*1024**2:raise ValueError('Bounded first manifest required')
        manifest=json.loads(tar.extractfile(first).read())
        if manifest.get('format')!='rid_receiver_snapshot_v1':raise ValueError('Unknown snapshot format')
        expected=manifest['files']
        if not isinstance(expected,dict) or not 1<=len(expected)<=MAX_FILES:raise ValueError('Invalid manifest count')
        total=0
        for name,value in expected.items():
            member_name(name);size=value['bytes']
            if isinstance(size,bool) or not isinstance(size,int) or size<0:raise ValueError('Invalid manifest size')
            total+=size
        if total>LIMIT:raise ValueError('Manifest size limit')
        seen=set()
        for item in members:
            check_deadline(deadline);member_name(item.name)
            if not item.isfile() or item.name in seen or item.name not in expected:raise ValueError('Unexpected/duplicate/nonregular member')
            if item.size!=expected[item.name]['bytes']:raise ValueError('Member size mismatch')
            seen.add(item.name);h=hashlib.sha256();stream=tar.extractfile(item)
            while True:
                check_deadline(deadline);data=stream.read(CHUNK)
                if not data:break
                h.update(data)
            if h.hexdigest()!=expected[item.name]['sha256']:raise ValueError('Member SHA-256 mismatch')
        if seen!=set(expected):raise ValueError('Missing archive members')
    return manifest


def preserve(base,archive,*,offline_copy=False,node_id=None,timeout_s=1800,probe=service_evidence):
    base=Path(base).absolute();archive=Path(archive).absolute()
    if not 1<=timeout_s<=3600:raise ValueError('Bounded timeout 1..3600 seconds required')
    # Reject every existing output ancestor symlink; never overwrite a previous receipt/archive.
    for p in [archive,*archive.parents]:
        if p.is_symlink():raise ValueError('Output symlink rejected')
    if archive.is_relative_to(base):raise ValueError('Keep backup outside source tree')
    if archive.exists():raise ValueError('Archive already exists')
    if not archive.parent.is_dir() or archive.parent.stat().st_uid!=os.getuid() or archive.parent.stat().st_mode&0o077:raise ValueError('Owner-private output directory required')
    os.umask(0o077);deadline=time.monotonic()+timeout_s
    evidence={'service_state':'NOT_CHECKED_OFFLINE_COPY'}
    if not offline_copy:
        if node_id not in ['observer-'+x for x in 'bcdef']:raise ValueError('Explicit receiver identity required')
        config=base/'config/node.json'
        if config.is_symlink() or not config.exists():raise ValueError('Existing node config required')
        if json.loads(config.read_text()).get('node_id')!=node_id:raise ValueError('Receiver identity mismatch')
        evidence=probe()
    files=collect(base,deadline)
    if shutil.disk_usage(archive.parent).free<1024**3+sum(x['bytes'] for x in files.values())+32*1024**2:raise ValueError('Insufficient backup disk headroom')
    manifest=dict(format='rid_receiver_snapshot_v1',mode='OFFLINE_PRESERVED_COPY' if offline_copy else 'QUIESCENT_LIVE_NODE',
        files=files,service_evidence=evidence,source_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    partial=archive.with_name(archive.name+'.partial')
    # Failed partials deliberately remain; a different run name is required to retry.
    with partial.open('xb') as output:
        # An explicit gzip wrapper avoids requiring the newer tarfile stream compresslevel API.
        with gzip.GzipFile(fileobj=output,mode='wb',compresslevel=1) as compressed,tarfile.open(fileobj=compressed,mode='w|') as tar:
            data=json.dumps(manifest,sort_keys=True).encode();header=tarfile.TarInfo('snapshot-manifest.json');header.size=len(data);header.mode=0o600
            tar.addfile(header,io.BytesIO(data))
            for name,record in sorted(files.items()):
                check_deadline(deadline)
                fd=os.open(base/name,os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,'rb') as source:
                    if list(signature(os.fstat(source.fileno())))!=record['signature']:raise ValueError('Source changed before archive write')
                    header=tarfile.TarInfo(name);header.size=record['bytes'];header.mode=0o600
                    tar.addfile(header,source)
                    if list(signature(os.fstat(source.fileno())))!=record['signature']:raise ValueError('Source changed while archiving')
        output.flush();os.fsync(output.fileno())
    verify_archive(partial,deadline)
    archive_sha=digest(partial,deadline)[0]
    if collect(base,deadline)!=files:raise ValueError('Source membership/content changed; partial retained')
    os.link(partial,archive);partial.unlink()
    return dict(mode=manifest['mode'],files=len(files),source_bytes=sum(x['bytes'] for x in files.values()),
        archive_bytes=archive.stat().st_size,sha256=archive_sha,source_unchanged_at_final_check=True,
        archive_verified=True,live_preservation_verified=not offline_copy,
        configuration_present=any(x.startswith('config/') for x in files),deployment_executed=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--node-id');p.add_argument('--offline-copy',action='store_true');p.add_argument('--timeout',type=int,default=1800)
    a=p.parse_args()
    from audit_receivers import private_path
    archive=private_path(a.archive);receipt=private_path(a.receipt)
    if receipt in [archive,archive.with_name(archive.name+'.partial')]:p.error('Distinct archive and receipt paths required')
    if receipt.exists():p.error('New receipt required')
    os.umask(0o077)
    for path in [archive.parent,receipt.parent]:
        path.mkdir(parents=True,exist_ok=True,mode=0o700)
        if path.stat().st_uid!=os.getuid() or path.stat().st_mode&0o077:p.error('Owner-private output directories required')
    try:
        result=preserve(a.base.resolve(),archive,offline_copy=a.offline_copy,node_id=a.node_id,timeout_s=a.timeout)
    except Exception as e:
        with receipt.open('x') as f:json.dump(dict(status='FAILED',error_type=type(e).__name__,partial_preserved=archive.with_name(archive.name+'.partial').exists()),f,indent=2)
        raise
    with receipt.open('x') as f:json.dump(dict(status='VERIFIED',**result),f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
