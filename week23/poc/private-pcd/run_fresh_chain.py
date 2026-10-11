"""Inspect unchanged synthetic setup fixtures, then prove fresh A/B/C in separate processes."""
from pathlib import Path
import hashlib,json,os,re,subprocess,time
ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'.cache/week23/private/pcd'
OUT=ROOT/'.cache/week23/private/zk-carry-fresh-v1'
os.umask(0o077)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def observation(stage):
 lat,lon,alt=812345000+stage*600,914567800+stage*800,345123+stage*41
 return [lat,lon,alt,lat+1,lon+3,alt-300,5317 if stage==3 else 312+stage]
def main():
 OUT.mkdir(mode=0o700)
 original=json.loads((ROOT/'week23/manifests/sources.json').read_text())['research_sources_sha256']
 sources={}
 for name in ['main.go','relations.go','go.mod','go.sum']:
  path='week23/poc/private-pcd/'+name;h=sha(ROOT/path)
  if h!=original['poc/private-pcd/'+name]:raise ValueError('source metadata mismatch; fixtures preserved')
  sources[path]=h
 old=next(json.loads(line)['fixture_artifact_sha256'] for line in (ROOT/'week23/logs/private-pcd-fork-normal.log').read_text().splitlines() if line.startswith('{') and 'fixture_artifact_sha256' in line)
 artifacts={}
 for stage in (1,2,3):
  for name in ['ccs','pk','vk','proof','public']:
   key=str(stage)+'/'+name+'.bin';h=sha(BASE/key);artifacts[key]=h
   if stage>1 and h!=old[str(stage)+'/'+name]:raise ValueError('previous artifact mismatch; preserve and inspect')
  subprocess.run([str(ROOT/'.cache/week23/private-pcd-fresh'),'verify',str(BASE),str(stage)],check=True,capture_output=True)
 inventory={'sources':sources,'artifacts':artifacts,'inspection':'stage2/3 match previous published artifact hashes; stage1 source + native proof checked, fresh source compilation must match CCS before reuse'}
 (OUT/'inspected-fixtures.json').write_text(json.dumps(inventory,indent=2))
 (ROOT/'week23/manifests/fresh-chain-fixtures.json').write_text(json.dumps(inventory,indent=2)+'\n')
 resources=[]
 for stage in (1,2,3):
  start=time.monotonic();peak=0;log=ROOT/f'week23/logs/fresh-chain-stage{stage}.log'
  if log.exists():raise FileExistsError('preserve existing experiment logs')
  with log.open('w') as f:
   p=subprocess.Popen([str(ROOT/'.cache/week23/private-pcd-fresh'),'fresh-chain',str(BASE),str(OUT),str(stage)],cwd=ROOT,env={**os.environ,'GOMAXPROCS':'2'},stdout=f,stderr=subprocess.STDOUT)
   try:
    while p.poll() is None:
     raw=subprocess.check_output(['ps','-o','rss=','-p',str(p.pid)],text=True).strip();rss=int(raw or '0')*1024;peak=max(peak,rss)
     swap=subprocess.check_output(['sysctl','vm.swapusage'],text=True);used=float(re.search(r'used = ([\d.]+)M',swap)[1])
     if rss>4.5*1024**3 or used>7500:raise RuntimeError('resource ceiling; preserve private fixtures for resume')
     time.sleep(1)
   finally:
    if p.poll() is None:p.terminate();p.wait(timeout=30)
  if p.returncode:raise RuntimeError('stage failed; inspect public phase log')
  resources.append({'stage':stage,'pid':p.pid,'peak_rss_bytes':peak,'elapsed_s':time.monotonic()-start,'exit_code':p.returncode})
  print(json.dumps(resources[-1]),flush=True)
 tests=[]
 for stage in (1,2,3):
  result=subprocess.run([str(ROOT/'.cache/week23/private-pcd-fresh'),'inspect-verified',str(OUT),str(stage)],capture_output=True,text=True,check=True)
  row=next(json.loads(s) for s in result.stdout.splitlines() if s.startswith('{'))
  payload=b''.join((OUT/str(stage)/(name+'.bin')).read_bytes() for name in ['proof','public'])
  for owner in range(1,stage):
   matches=sum(payload.count(value.to_bytes(32,order)) for value in observation(owner) for order in ('little','big'))
   assert matches==0;tests.append({'receiver_stage':stage,'prior_owner':owner,'exact_canary_matches_both_endians':matches})
  tests.append({'case':'final-native-verification-'+str(stage),'public':row['public'],'verified':True,'transfer_bytes':len(payload)})
 result={'fresh_independent_provers':resources,'tests':tests,'private_assignment_cached':False,'transfer':'proof + public only; VK is trusted receiver-local metadata','scope':'fixed three-stage gnark general recursion fallback, not HyperNova/NovaBlindFold; no field/hardware/DRIP truth; exact canary check is not a ZK security proof'}
 (ROOT/'week23/logs/fresh-secret-chain.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
