"""Strict SSH transport for bounded, serial Pi trials. Credentials only in environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
FRAMEWORKS=['gnark','arkworks','halo2-ipa','halo2-kzg','spartan','bulletproofs','plonky3']
TRIALS=['gnark-groth16','gnark-plonk',*FRAMEWORKS[1:]]
REMOTE='/home/pi/.cache/week24'
def transport():
    env=dict(os.environ)
    if env.get('EVAL_SSH_PASSWORD'):env.update(SSH_ASKPASS_REQUIRE='force',SSH_ASKPASS=str(HERE/'askpass.sh'),DISPLAY=env.get('DISPLAY',':0'))
    options=['-o','ControlPath=none','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+env.get('EVAL_KNOWN_HOSTS',str(ROOT/'.cache/week24/private/known_hosts'))]
    if env.get('EVAL_HOST_KEY_ALIAS'):options+=['-o','HostKeyAlias='+env['EVAL_HOST_KEY_ALIAS']]
    if env.get('EVAL_SSH_IPV6')=='1':options+=['-6']
    return options,env,env.get('EVAL_SSH_TARGET','pi@raspberrypi.local')
def ssh(cmd,timeout=30,input=None):
    opts,env,target=transport()
    return subprocess.run(['ssh',*opts,target,cmd],env=env,input=input,text=True,capture_output=True,timeout=timeout)
def upload(local,remote):
    opts,env,target=transport()
    subprocess.run(['scp',*opts,str(local),target+':'+remote],env=env,check=True,timeout=60)
def download(remote,local):
    opts,env,target=transport()
    return subprocess.run(['scp',*opts,target+':'+remote,str(local)],env=env,timeout=60).returncode

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['probe','deploy','trial','collect']);p.add_argument('--job',type=Path,required=True);p.add_argument('--tag',required=True);p.add_argument('--framework');a=p.parse_args()
    job=a.job;remote=REMOTE+'/sequential-'+a.tag
    if a.action=='probe':
        code="import hashlib,importlib.util,json;from pathlib import Path;p=Path('/home/pi/.cache/week24/preflight-v1.py');assert hashlib.sha256(p.read_bytes()).hexdigest()=='8a6ed1ef7f19066d858afa5ecda61a751a157978be5d502e6c3ec0f3d7f9096e';s=importlib.util.spec_from_file_location('p',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(json.dumps(m.snapshot()))"
        try:
            r=ssh(shlex.join(['python3','-c',code]),timeout=20)
            if r.returncode:result={'ready':False,'reason':'SSH probe failed','ssh_exit_code':r.returncode}
            else:result=json.loads(r.stdout)
        except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError):result={'ready':False,'reason':'SSH timeout, missing tool or invalid telemetry'}
        (job/'pi-readiness.json').write_text(json.dumps(result,indent=2)+'\n')
        return 0 if result.get('ready') is True else 3
    if a.action=='deploy':
        # A failed probe is never bypassed by the deployment helper.
        if json.loads((job/'pi-readiness.json').read_text()).get('ready') is not True:return 3
        r=ssh(shlex.join(['mkdir','-m','700',remote]));r.check_returncode()
        for name,local in [('launch.py',ROOT/'experiments/unified-distance-bench/launch.py'),('preflight.py',ROOT/'experiments/pi4-stability/preflight.py')]:upload(local,remote+'/'+name)
        # The old launcher expects preflight.py at the cache root; preserve any existing version.
        code="from pathlib import Path;import hashlib,os;p=Path('/home/pi/.cache/week24/preflight.py');s=Path("+repr(remote+'/preflight.py')+");assert hashlib.sha256(s.read_bytes()).hexdigest()=='8a6ed1ef7f19066d858afa5ecda61a751a157978be5d502e6c3ec0f3d7f9096e';assert not p.exists() or p.read_bytes()==s.read_bytes();f=None if p.exists() else os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);None if f is None else os.write(f,s.read_bytes());None if f is None else os.close(f)"
        ssh(shlex.join(['python3','-c',code])).check_returncode()
        for framework in FRAMEWORKS:
            local=ROOT/'.cache/week24/unified-build'/a.tag/framework
            meta=json.loads((local/'build.json').read_text());binary=local/('unified-'+framework)
            assert hashlib.sha256(binary.read_bytes()).hexdigest()==meta['binary_sha256']
            ssh(shlex.join(['mkdir','-m','700',remote+'/'+framework])).check_returncode()
            for f in [binary,local/'build.json']:upload(f,remote+'/'+framework+'/'+f.name)
            ssh(shlex.join(['chmod','700',remote+'/'+framework+'/'+binary.name])).check_returncode()
        for backend in ['groth16','plonk']:
            local=ROOT/'.cache/week24/private'/('sequential-'+a.tag)/backend
            cross=json.loads((ROOT/'.cache/week24/unified-build'/a.tag/'gnark/build.json').read_text())
            fixture=json.loads((local/'manifest.json').read_text())
            assert fixture['source_digest']==cross['fixture_source_digest']
            assert local.stat().st_mode&0o777==0o700
            ssh(shlex.join(['mkdir','-m','700',remote+'/fixture-'+backend])).check_returncode()
            for name in ['cs.bin','pk.bin','vk.bin','manifest.json']:
                assert (local/name).stat().st_mode&0o777==0o600
                upload(local/name,remote+'/fixture-'+backend+'/'+name)
                ssh(shlex.join(['chmod','600',remote+'/fixture-'+backend+'/'+name])).check_returncode()
        (job/'deployment.json').write_text(json.dumps({'status':'completed','frameworks':FRAMEWORKS,'private_fixtures_exported_to_git':False})+'\n');return 0
    if a.action=='trial':
        name=a.framework
        if name not in TRIALS:raise ValueError('unknown trial')
        framework='gnark' if name.startswith('gnark-') else name
        cmd=['python3',remote+'/launch.py','--run-id',a.tag+'-'+name,'--binary',remote+'/'+framework+'/unified-'+framework,'--build-metadata',remote+'/'+framework+'/build.json']
        if framework=='gnark':cmd+=['--backend',name.removeprefix('gnark-'),'--fixture',remote+'/fixture-'+name.removeprefix('gnark-')]
        # sudo reads the password from stdin; no password appears in argv, logs, plan or CSV.
        password=os.environ.get('EVAL_SUDO_PASSWORD',os.environ.get('EVAL_SSH_PASSWORD'))
        command=('sudo -S -p "" -v && exec ' if password else 'sudo -n -v && exec ')+shlex.join(cmd)
        r=ssh(command,timeout=1320,input=password+'\n' if password else None)
        print(r.stdout)
        if r.returncode:print('Remote trial failed or connection lost; do not retry automatically.')
        return r.returncode
    state=json.loads((job/'status.json').read_text())
    deployed=any(s['id']=='pi-deploy' and s['status']=='completed' for s in state['steps'])
    if not deployed:return 0
    runs=job/'pi-runs';runs.mkdir(exist_ok=True)
    failed=False
    for name in TRIALS:
        run=a.tag+'-'+name;remote_run=REMOTE+'/runs/'+run
        check=ssh(shlex.join(['test','-d',remote_run]))
        if check.returncode:continue
        local=runs/run;local.mkdir(exist_ok=True)
        for file in ['benchmark.jsonl','memory.jsonl','resource.json','filesystem-audit.json','metadata.json']:
            if download(remote_run+'/'+file,local/file):failed=True
    return 1 if failed else 0
if __name__=='__main__':raise SystemExit(main())
