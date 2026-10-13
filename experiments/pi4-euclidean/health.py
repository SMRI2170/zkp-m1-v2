"""Public-safe Pi health snapshot: no host addresses, passwords, serials, or boot IDs."""
import hashlib,json,re,subprocess
from pathlib import Path

def run(args):return subprocess.run(args,capture_output=True,text=True,timeout=10)
mem={k:int(v.split()[0])*1024 for k,v in (x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines()) if k in ['MemAvailable','SwapTotal','SwapFree']}
ssh_pid=run(['systemctl','show','ssh.service','-p','MainPID','--value']).stdout.strip()
watch=Path('/run/week24/memory_watchdog.py')
result={'uptime_s':float(Path('/proc/uptime').read_text().split()[0]),'mem_available_bytes':mem['MemAvailable'],'system_swap_used_bytes':mem['SwapTotal']-mem['SwapFree'],
 'throttled':run(['vcgencmd','get_throttled']).stdout.strip().split('=',1)[1],
 'slice_active':run(['systemctl','is-active','--quiet','week24.slice']).returncode==0,
 'watchdog_active':run(['systemctl','is-active','--quiet','week24-memory-watchdog.service']).returncode==0,
 'ssh_oom_score_adj':int(Path(f'/proc/{ssh_pid}/oom_score_adj').read_text()),
 'watchdog_root_owned':watch.stat().st_uid==0,'watchdog_sha256':hashlib.sha256(watch.read_bytes()).hexdigest(),
 'parent_limits':{n:int(Path('/sys/fs/cgroup/week24.slice',n).read_text()) for n in ['memory.max','memory.high','memory.swap.max']},
 'week24_tmpfs_remnants':[p.name for p in Path('/dev/shm').glob('week24-*')]}
for label,boot in [('current','0'),('previous','-1')]:
 r=run(['journalctl','-k','-b',boot,'--no-pager']);result[label+'_journal_readable']=r.returncode==0
 result[label+'_kernel_oom_matches']=len(re.findall(r'oom-kill|out of memory|Killed process',r.stdout,re.I))
 result[label+'_kernel_undervoltage_matches']=len(re.findall(r'Undervoltage detected',r.stdout))
print(json.dumps(result,indent=2))
