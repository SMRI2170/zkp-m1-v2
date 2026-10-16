"""Sequential jobs with durable CSV/JSON status; start returns without chat polling."""
import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
def now():return datetime.now(timezone.utc).isoformat()
def write_state(job,state):
    tmp=job/'status.json.tmp';tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(job/'status.json')
    fields=['id','framework','kind','status','started_at','finished_at','elapsed_s','exit_code','reason']
    with (job/'results.csv.tmp').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for s in state['steps']:w.writerow({k:s.get(k) for k in fields})
    (job/'results.csv.tmp').replace(job/'results.csv')
def transition(job,state,step,status,**values):
    step.update(status=status,**values)
    with (job/'events.jsonl').open('a') as f:f.write(json.dumps({'at':now(),'step':step['id'],'status':status,**values})+'\n')
    write_state(job,state)
def validate(plan):
    ids=set()
    for s in plan['steps']:
        if not s['id'].replace('-','').isalnum() or s['id'] in ids:raise ValueError('invalid/duplicate step id')
        if not set(s.get('needs',[]))<=ids:raise ValueError('dependencies must precede their step')
        if not isinstance(s.get('argv'),list) or not s['argv'] or not all(isinstance(x,str) for x in s['argv']):raise ValueError('argv array required')
        if not 0<float(s.get('timeout_s',300))<=7200:raise ValueError('invalid timeout')
        ids.add(s['id'])

def work(job):
    os.umask(0o077)
    with (job/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=json.loads((job/'status.json').read_text());plan=json.loads((job/'plan.json').read_text());validate(plan)
        state.update(status='running',pid=os.getpid());write_state(job,state)
        stopping=[False]
        def stop(*_):stopping[0]=True
        old_handlers={sig:signal.getsignal(sig) for sig in [signal.SIGTERM,signal.SIGINT]}
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        for spec,step in zip(plan['steps'],state['steps']):
            if step['status']=='completed':continue
            if any(not Path(name).exists() or hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha for name,sha in state.get('source_sha256',{}).items()):
                transition(job,state,step,'blocked',reason='program source changed after job start; use a fresh job');continue
            if step['status']=='running':
                transition(job,state,step,'interrupted',reason='Previous worker ended during this step; execution may have occurred. No automatic retry.')
                continue
            if step['status']!='pending':continue
            deps=[s for s in state['steps'] if s['id'] in spec.get('needs',[])]
            if stopping[0] or (not spec.get('always',False) and any(s['status']!='completed' for s in deps)):
                transition(job,state,step,'blocked',reason='worker stopped' if stopping[0] else 'dependency not completed');continue
            mapping={'repo':str(ROOT),'job':str(job),'python':sys.executable,'tag':state['tag']}
            argv=list(spec['argv'])
            for key,value in mapping.items():argv=[x.replace('{'+key+'}',value) for x in argv]
            started=time.monotonic();transition(job,state,step,'running',started_at=now())
            process=None
            try:
                with (job/'private'/ (step['id']+'.log')).open('xb') as log:
                    process=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    reason=None
                    while process.poll() is None:
                        if stopping[0] or time.monotonic()-started>spec.get('timeout_s',300):
                            reason='interrupted; remote execution may still be active' if stopping[0] else 'timeout; remote execution may still be active'
                            os.killpg(process.pid,signal.SIGTERM)
                            try:process.wait(timeout=5)
                            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                            break
                        time.sleep(.2)
                    code=process.returncode
                status=('interrupted' if stopping[0] else 'timed_out') if reason else spec.get('exit_status',{}).get(str(code), 'completed' if code==0 else 'failed')
                transition(job,state,step,status,finished_at=now(),elapsed_s=round(time.monotonic()-started,3),exit_code=code,reason=reason or (None if code==0 else 'command failed; see private step log and result JSON'))
            except Exception as exc:
                transition(job,state,step,'failed',finished_at=now(),elapsed_s=round(time.monotonic()-started,3),reason=type(exc).__name__)
        state.update(status='completed' if all(s['status']=='completed' for s in state['steps']) else 'partial',finished_at=now());write_state(job,state)
        for sig,handler in old_handlers.items():signal.signal(sig,handler)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    start=sub.add_parser('start');start.add_argument('--plan',type=Path,default=Path(__file__).with_name('plan.json'));start.add_argument('--out',type=Path,required=True);start.add_argument('--tag',required=True)
    worker=sub.add_parser('_work');worker.add_argument('--job',type=Path,required=True)
    status=sub.add_parser('status');status.add_argument('--job',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if a.action=='_work':work(a.job.resolve());return
    if a.action=='status':
        print((a.job/'status.json').read_text());return
    if not a.tag.isascii() or not a.tag.replace('-','').isalnum() or not a.tag.islower() or len(a.tag)>20:p.error('tag: lowercase letters/digits/hyphens, <=20 chars')
    plan=json.loads(a.plan.read_text());validate(plan);job=a.out.resolve();job.mkdir(parents=True,mode=0o700)
    (job/'private').mkdir(mode=0o700);(job/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    state={'schema_version':1,'tag':a.tag,'status':'queued','started_at':now(),'finished_at':None,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'plan_sha256':hashlib.sha256(a.plan.read_bytes()).hexdigest(),'steps':[{k:s[k] for k in ['id','framework','kind'] if k in s}|{'status':'pending'} for s in plan['steps']]}
    state['source_sha256']={str(f.resolve()):hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(__file__).parent.iterdir() if f.is_file()}
    # Python 3.9+; only public status fields, never credentials or command arguments.
    write_state(job,state)
    with (job/'private/worker.log').open('xb') as log:
        proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'_work','--job',str(job)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,cwd=ROOT)
    (job/'worker.pid').write_text(str(proc.pid)+'\n')
    print(json.dumps({'started':True,'pid':proc.pid,'job':str(job),'status_json':str(job/'status.json'),'results_csv':str(job/'results.csv')},ensure_ascii=False))
if __name__=='__main__':main()
