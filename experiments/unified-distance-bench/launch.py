"""Pi launch: pinned runner + binary + preflight; never start on missing guards."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
RUNNER_SHA='bb19ee59cc3ca5cbad3071d511e90e2f4abe98a659a2db665a8b2435181b340f'
PREFLIGHT_SHA='8a6ed1ef7f19066d858afa5ecda61a751a157978be5d502e6c3ec0f3d7f9096e'

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--build-metadata',type=Path,required=True);p.add_argument('--backend',choices=['groth16','plonk'])
    p.add_argument('--fixture',type=Path);p.add_argument('--cache',type=Path,default=Path.home()/'.cache/week24')
    a=p.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,50}',a.run_id):p.error('invalid run-id')
    if os.uname().machine!='aarch64' or os.geteuid()==0:p.error('run as ordinary Pi ARM64 user')
    root=a.cache.resolve();build=json.loads(a.build_metadata.read_text());binary=a.binary.resolve()
    if build.get('protocol')!='distance-u16-balanced-v1':raise SystemExit('balanced protocol build required')
    if build['target']!='aarch64-unknown-linux-musl':raise SystemExit('ARM64 build metadata required')
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=build['binary_sha256']:raise SystemExit('binary hash mismatch')
    runner=root/'run_guarded_evaluation.py';preflight=root/'preflight.py'
    for path,sha in [(runner,RUNNER_SHA),(preflight,PREFLIGHT_SHA)]:
        if sha is None or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise SystemExit('helper hash mismatch')
    framework=build['framework'];cmd=[str(binary)]
    if framework=='gnark':
        if not a.backend or a.fixture is None:p.error('gnark requires backend and fixture')
        cmd+=['bench',a.backend,str(a.fixture.resolve())];framework+='-'+a.backend
    elif a.backend or a.fixture:p.error('fixture/backend only supported for gnark')
    out=root/'runs'/a.run_id;work=Path('/dev/shm')/('week24-eval-'+a.run_id)
    if out.exists() or work.exists():raise SystemExit('preserve existing run/work and use new ID')
    # Serialize launches. Also reject other running heavy trials, including older launchers.
    with (root/'unified-launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        units=subprocess.check_output(['systemctl','list-units','--state=running','--no-legend','--plain','week24-*.service'],text=True)
        if any('watchdog' not in line for line in units.splitlines() if line.strip()):raise SystemExit('another experiment unit is active')
        subprocess.run([sys.executable,str(preflight),'--out',str(root/'preflight'/a.run_id),'--samples','3','--interval-s','30'],check=True)
        args=['sudo','-n','systemd-run','--unit=week24-eval-'+a.run_id,'--wait','--pipe']
        for prop in ['User='+str(os.getuid()),'Slice=week24.slice','MemoryAccounting=yes','MemoryHigh=192M','MemoryMax=256M','MemorySwapMax=0','OOMScoreAdjust=500','OOMPolicy=stop','CPUWeight=10','CPUQuota=25%','RuntimeMaxSec=1230']:
            args+=['-p',prop]
        args += [sys.executable,str(runner),'--out',str(out),'--work-dir',str(work),'--timeout-s','1200','--memory-high-mib','192','--memory-max-mib','256','--',*cmd]
        code=subprocess.run(args).returncode
        if out.exists():
            metadata={'protocol':'distance-u16-balanced-v1','run_id':a.run_id,'framework':framework,
                'host_class':'Pi4B4GB ARM64','cpu_quota_percent':25,'threads':1,
                'flow_scope':'logged witness if separate + prove + verify; setup/load/negative tests excluded',
                'phase_notes':{'gnark':'frontend.NewWitness timing; public witness extraction and oracle outside timer','arkworks':'field conversion outside timer; synthesis included in prover','halo2-ipa':'reference/public assignment prep outside timer; assignment included in create_proof','halo2-kzg':'reference/public assignment prep outside timer; assignment included in create_proof','spartan':'witness interval includes build + is_sat sanity check','bulletproofs':'field conversion outside timer; R1CS assignment included in prove','plonky3':'field conversion outside timer; trace construction timed separately'}[build['framework']],
                'proof_encoding':'framework-native serialized proof only','binary_sha256':build['binary_sha256'],
                'build_metadata':build,'launcher_exit_code':code}
            (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
        return code
if __name__=='__main__':raise SystemExit(main())
