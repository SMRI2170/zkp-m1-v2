# coding: utf-8
"""Pi-only launcher: require completed preflight and pinned artifacts before proving."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

RUNNER_SHA256='bb19ee59cc3ca5cbad3071d511e90e2f4abe98a659a2db665a8b2435181b340f'
BINARY_SHA256='a238c11d1196ea9bc3197ac5a7756f4d76307595ec9b9656623d49c1f25f1c0b'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id',required=True)
    p.add_argument('--count',type=int,choices=[1,2,4],required=True)
    p.add_argument('--cache',type=Path,default=Path.home()/'.cache/week24')
    a=p.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,59}',a.run_id):p.error('run-id must be 1..60 lowercase ASCII letters, digits or hyphens')
    if os.uname().machine!='aarch64' or os.geteuid()==0: p.error('Run on Pi as ordinary experiment user, not root')
    root=a.cache.resolve()
    runner=root/'run_guarded_evaluation.py';binary=root/'week24-observation-workload-queue-v1'
    for path,expected in [(runner,RUNNER_SHA256),(binary,BINARY_SHA256)]:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise SystemExit('Artifact hash mismatch: '+path.name)
    out=root/'runs'/a.run_id
    if out.exists():raise SystemExit('Run directory exists; preserve it and choose a new run-id')
    work=Path('/dev/shm')/('week24-eval-'+a.run_id)
    if work.exists():raise SystemExit('Working directory exists; inspect it and choose a new run-id')
    pre=root/'preflight'/a.run_id
    # check=True is deliberate: no proof starts on partial/failed readiness evidence.
    subprocess.run([sys.executable,str(Path(__file__).with_name('preflight.py')),
                    '--out',str(pre),'--samples','3','--interval-s','30'],check=True)
    # Noninteractive sudo: fail instead of leaving a long proof launch waiting for a password.
    # Authenticate with sudo -v in the terminal immediately before invoking this launcher.
    cmd=['sudo','-n','systemd-run','--unit=week24-eval-'+a.run_id,'--wait','--pipe']
    for prop in ['User='+str(os.getuid()),'Slice=week24.slice','MemoryAccounting=yes',
                 'MemoryHigh=384M','MemoryMax=512M','MemorySwapMax=0','OOMScoreAdjust=500',
                 'OOMPolicy=stop','CPUWeight=10','CPUQuota=25%','RuntimeMaxSec=1530']:
        cmd.extend(['-p',prop])
    cmd.extend([sys.executable,str(runner),'--out',str(out),'--work-dir',str(work),
                '--timeout-s','1500','--memory-high-mib','384','--memory-max-mib','512',
                '--',str(binary),'--count',str(a.count),'--arrival-ms','1000'])
    return subprocess.run(cmd).returncode

if __name__=='__main__':raise SystemExit(main())
