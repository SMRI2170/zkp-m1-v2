"""Prepare an isolated PR5 project build; preserve the original PR4 binary."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from setup import ROOT,REPO,memory_evidence


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=REPO/'.cache/issue70')
    p.add_argument('--workspace',type=Path,default=REPO/'.cache/issue75');p.add_argument('--out',type=Path,required=True);p.add_argument('--build',action='store_true')
    a=p.parse_args();source=a.source.resolve();workspace=a.workspace.resolve()
    if source==workspace or not workspace.is_relative_to((REPO/'.cache').resolve()):p.error('Use a DIFFERENT project directory inside .cache/')
    if a.out.exists():p.error('Use a new receipt path; preserve previous failures')
    workspace.mkdir(parents=True,exist_ok=True,mode=0o700)
    memory=memory_evidence()
    if shutil.disk_usage(workspace).free<8*1024**3:raise ValueError('Need 8GiB disk headroom')
    if memory.get('free_percentage') is not None and memory['total_bytes']*memory['free_percentage']/100<4*1024**3:raise ValueError('Need 4GiB estimated memory headroom')
    if 'MemAvailable' in memory and memory['MemAvailable']<4*1024**3:raise ValueError('Need 4GiB available memory')
    if memory.get('unsupported_platform'):raise ValueError('Memory preflight unsupported on this host')
    baseline=source/'project-build/out/clang-release/rid_smoke';original=hashlib.sha256(baseline.read_bytes()).hexdigest()
    for name in ['omnetpp-6.2.0','inet4.5','eigen-5.0.0','python','uli-net-sim']:
        target=source/name;link=workspace/name
        if not target.exists():raise ValueError('Build PR1 dependencies first: '+name)
        if link.exists():
            if not link.is_symlink() or link.resolve()!=target.resolve():raise ValueError('Existing workspace dependency differs; preserved')
        else:link.symlink_to(target.resolve(),target_is_directory=True)
    (workspace/'project-build').mkdir(exist_ok=True)
    result=dict(status='PREPARED',source_binary_sha256=original,memory=memory,build_requested=a.build)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    if a.build:
        log=a.out.with_suffix('.build.log')
        with log.open('w') as stream:
            command=['bash',str(ROOT/'scripts/build_power_extension.sh'),str(workspace)]
            code=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT).returncode
        result.update(status='BUILT' if code==0 else 'BUILD_FAILED',exit_code=code,build_log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
        if code==0:result['new_binary_sha256']=hashlib.sha256((workspace/'project-build/out/clang-release/rid_smoke').read_bytes()).hexdigest()
    result['source_binary_unchanged']=hashlib.sha256(baseline.read_bytes()).hexdigest()==original
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    if not result['source_binary_unchanged']:raise ValueError('Original binary changed')
    print(json.dumps(result,indent=2));return 2 if result['status']=='BUILD_FAILED' else 0


if __name__=='__main__':raise SystemExit(main())
