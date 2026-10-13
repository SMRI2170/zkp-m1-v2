"""Sampled macOS process-tree RSS/swap guard, not a hard cgroup limit.
Only synthetic local proof trials. No network/backend fallback.
"""
import argparse,json,os,signal,subprocess,time,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--timeout-s',type=int,default=600);p.add_argument('--rss-max-mib',type=int,default=4096);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
assert a.timeout_s<=1800 and 0<a.rss_max_mib<=4096
cmd=a.command[1:] if a.command[0]=='--' else a.command
os.umask(0o077);a.out.mkdir(mode=0o700)
def swap():
 s=subprocess.check_output(['sysctl','vm.swapusage'],text=True,timeout=2)
 return float(re.search(r'used = ([\d.]+)M',s).group(1))*2**20
def rss_tree(pid):
 rows=[list(map(int,s.split())) for s in subprocess.check_output(['ps','-axo','pid=,ppid=,rss='],text=True,timeout=2).splitlines()]
 descendants={pid}
 while True:
  expanded=descendants|{x for x,parent,_ in rows if parent in descendants}
  if expanded==descendants:break
  descendants=expanded
 return sum(rss*1024 for x,_,rss in rows if x in descendants)
before=swap();start=time.monotonic();peak=0;reason=None;samples=0
with (a.out/'benchmark.jsonl').open('x') as out,(a.out/'stderr.log').open('x') as err,(a.out/'memory.jsonl').open('x') as memory:
 child=subprocess.Popen(cmd,stdout=out,stderr=err,start_new_session=True,env={**os.environ,'RAYON_NUM_THREADS':'1','OMP_NUM_THREADS':'1','RISC0_DEV_MODE':'0'})
 try:
  while child.poll() is None:
   rss=rss_tree(child.pid);current_swap=swap();peak=max(peak,rss);samples+=1
   memory.write(json.dumps({'elapsed_s':time.monotonic()-start,'process_tree_rss_bytes':rss,'system_swap_delta_bytes':current_swap-before})+'\n');memory.flush()
   if rss>a.rss_max_mib*2**20:reason='process_tree_rss_limit';break
   if current_swap-before>512*2**20:reason='system_swap_growth_limit';break
   if time.monotonic()-start>a.timeout_s:reason='timeout';break
   time.sleep(.1)
 except Exception as exc:reason='telemetry_error:'+type(exc).__name__
 finally:
  if child.poll() is None:
   try:os.killpg(child.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:child.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
resource={'os':'macos','exit_code':child.returncode,'stop_reason':reason,'elapsed_s':time.monotonic()-start,'sampled_process_tree_peak_bytes':peak,'poll_samples':samples,'rss_limit_bytes':a.rss_max_mib*2**20,'system_swap_growth_limit_bytes':512*2**20,'scope':'100ms sampled process-tree RSS; soft monitor, not cgroup/hard limit; Mac results not Pi metrics'}
(a.out/'resource.json').write_text(json.dumps(resource,indent=2)+'\n');print(json.dumps(resource))
if child.returncode!=0 or reason is not None:raise SystemExit(1)
