"""Run one recursive stage with an explicit local resource ceiling."""
import subprocess,sys,time,json,re
from pathlib import Path
root=Path(__file__).resolve().parents[3]
stage=int(sys.argv[1]);log=root/f'week23/logs/private-pcd-{stage}.log'
if log.exists():
    attempt=1
    while log.with_name(f'private-pcd-{stage}-attempt-{attempt}.log').exists(): attempt+=1
    log=log.with_name(f'private-pcd-{stage}-attempt-{attempt}.log')
start=time.monotonic();peak=0
with log.open('w') as f:
    p=subprocess.Popen([str(root/'.cache/week23/private-pcd'),'prove',str(root/'.cache/week23/private/pcd'),str(stage)],stdout=f,stderr=subprocess.STDOUT,env={**__import__('os').environ,'GOMAXPROCS':'2'})
    reason=None
    while p.poll() is None:
        raw=subprocess.check_output(['ps','-o','rss=','-p',str(p.pid)],text=True).strip()
        rss=int(raw or '0')*1024;peak=max(peak,rss)
        swap=subprocess.check_output(['sysctl','vm.swapusage'],text=True)
        used=float(re.search(r'used = ([\d.]+)M',swap)[1])
        if rss>4.5*1024**3 or used>7500:
            reason={'reason':'resource_ceiling','rss_bytes':rss,'swap_used_MiB':used}
            p.terminate();p.wait(timeout=30);break
        time.sleep(1)
summary={'stage':stage,'exit_code':p.returncode,'peak_rss_bytes':peak,'elapsed_s':time.monotonic()-start,'ceiling':reason,'rss_ceiling_GiB':4.5,'swap_ceiling_MiB':7500}
log.with_name(log.stem+'-resource.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary));sys.exit(0 if p.returncode==0 else 1)
