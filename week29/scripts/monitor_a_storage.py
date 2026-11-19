#!/usr/bin/env python3
"""Bounded, read-only-to-recorders soak monitor; its own files remain owner-private."""
import argparse,csv,json,os,signal,subprocess,time,threading,shutil
from pathlib import Path

UNITS={'receiver':'zkp-rid-observer.service','sensors':'zkp-flight-sensors.service','transmitter':'zkp-flight-marker.service'}

def numeric(value):
 try:return int(value) if int(value)>=0 else None
 except (TypeError,ValueError):return None

def resources(release,roles,*,meminfo=Path('/proc/meminfo'),runner=subprocess.run):
 try:memory={line.split(':',1)[0]:int(line.split()[1])*1024 for line in meminfo.read_text().splitlines() if line.startswith(('MemAvailable:','SwapFree:'))}
 except (OSError,ValueError):memory={}
 try:free=shutil.disk_usage(release/'captures').free
 except OSError:free=None
 services={}
 for role in roles:
  try:
   r=runner(['systemctl','show',UNITS[role],'-p','ActiveState','-p','MemoryCurrent','-p','CPUUsageNSec','-p','NRestarts'],capture_output=True,text=True,timeout=5)
   props=dict(x.split('=',1) for x in r.stdout.splitlines() if '=' in x) if r.returncode==0 else {}
   services[role]=dict(active_state=props.get('ActiveState'),memory_bytes=numeric(props.get('MemoryCurrent')),cpu_ns=numeric(props.get('CPUUsageNSec')),restarts=numeric(props.get('NRestarts')))
  except (OSError,subprocess.TimeoutExpired):services[role]=dict(active_state=None,memory_bytes=None,cpu_ns=None,restarts=None)
 return dict(memory_available_bytes=memory.get('MemAvailable'),swap_free_bytes=memory.get('SwapFree'),disk_free_bytes=free,services=services)

def read_health(release,roles,*,runner=subprocess.run):
 r=runner(['/usr/bin/python3',str(release/'experiments/week28-beacon-observers/capture_health.py'),'--root',str(release/'captures'),'--roles',*roles],text=True,capture_output=True,timeout=15)
 return json.loads(r.stdout),r.returncode

def main():
 p=argparse.ArgumentParser();p.add_argument('--release',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--duration',type=int,default=21600);p.add_argument('--interval',type=int,default=30);p.add_argument('--roles',nargs='+',choices=list(UNITS),default=list(UNITS));a=p.parse_args()
 if not 30<=a.duration<=86400 or not 1<=a.interval<=300:p.error('duration 30..86400, interval 1..300')
 os.umask(0o077)
 if a.output.exists():raise ValueError('new monitor output required')
 a.output.mkdir(parents=True,mode=0o700);stop=False;wake=threading.Event()
 def request(*_):
  nonlocal stop;stop=True;wake.set()
 for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,request)
 start=time.monotonic();samples=0;failed=[];last=None
 with (a.output/'samples.jsonl').open('x') as f,(a.output/'resources.csv').open('x',newline='') as table:
  writer=csv.DictWriter(table,fieldnames=['elapsed_s','role','phase','records_written','session_bytes','heartbeat_age_s','memory_available_bytes','disk_free_bytes','service_memory_bytes','service_cpu_ns']);writer.writeheader()
  while not stop and time.monotonic()-start<a.duration:
   try:
    o,returncode=read_health(a.release,a.roles)
   except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
    o={'phase':'FAULT','error':'HEALTH_READ_FAILED_'+type(exc).__name__};returncode=2
   o['elapsed_s']=time.monotonic()-start;o['returncode']=returncode
   o['resources']=resources(a.release,a.roles)
   # Receiver WAITING is retained explicitly and never reported as RID reception.
   if o['phase']=='FAULT':failed.append({'elapsed_s':o['elapsed_s'],'roles':o.get('roles',{}),'error':o.get('error')})
   f.write(json.dumps(o)+'\n');f.flush();os.fsync(f.fileno());samples+=1;last=o
   for role in a.roles:
    detail=o.get('roles',{}).get(role,{});r=o['resources'];service=r['services'].get(role,{})
    writer.writerow(dict(elapsed_s=o['elapsed_s'],role=role,phase=detail.get('phase',o['phase']),records_written=detail.get('records_written'),session_bytes=detail.get('session_bytes'),heartbeat_age_s=detail.get('heartbeat_age_s'),memory_available_bytes=r['memory_available_bytes'],disk_free_bytes=r['disk_free_bytes'],service_memory_bytes=service.get('memory_bytes'),service_cpu_ns=service.get('cpu_ns')))
   table.flush();os.fsync(table.fileno())
   if len(failed)>=3:break
   wake.wait(min(a.interval,max(0,a.duration-(time.monotonic()-start))))
 completed=not stop and not failed and time.monotonic()-start>=a.duration
 summary={'completed_planned_duration':completed,'requested_duration_s':a.duration,'elapsed_s':time.monotonic()-start,'samples':samples,'fault_samples':len(failed),'stopped_by_signal':stop,'last_sample':last,'roles':a.roles,'real_drone_reception_verified':False,'scope':'recorder heartbeat and saved-row continuity; no independent RF truth'}
 (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k!='last_sample'}),flush=True)
 return 0 if completed else 2
if __name__=='__main__':raise SystemExit(main())
