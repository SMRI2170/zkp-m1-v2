"""Check committed evidence integrity, completion scopes, and resource guard outcomes."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text())
def records(p):
 rows=[];panic=0
 for s in (p/'benchmark.jsonl').read_text().splitlines():
  if s.startswith('{'):rows.append(json.loads(s))
  elif s.startswith('PANIC: panicked at guest/src/lib.rs:'):panic+=1
  else:assert s in ['  left: 26',' right: 25','  <no backtrace available>','note: run `trace_and_analyze` with `JOLT_BACKTRACE=1` environment variable to enable backtraces'],s
 return rows,panic

def main():
 m=read(ROOT/'week24/manifests/euclidean-next.json')
 for name,digest in m['file_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
 for group,name,n,bad in [('mac','kimchi-next-host-v2',7,6),('mac','binius-next-host-v1',7,6),('mac','jolt-next-prebuilt-host-v4',7,6),('mac','jolt-next-prebuilt-host-v3',1,2),('pi','next-kimchi-pi-v2',7,6),('pi','next-binius-pi-v1',7,6),('pi','next-jolt-pi-v2',1,2)]:
  p=ROOT/f'week24/logs/{group}-euclidean-next'/name;rows,panic=records(p);samples=[s for s in rows if s['phase']=='sample'];r=read(p/'resource.json')
  assert rows[0]['os']==('linux' if group=='pi' else 'macos') and rows[0]['arch']=='aarch64'
  assert len(samples)==n and rows[-1]['samples']==n and rows[-1]['all_verified'] and rows[-1]['invalid_cases_rejected']==bad and rows[-1]['proofs_saved'] is False
  for s in samples:
   assert all(s[k] is True for k in ['verified','changed_public_rejected','changed_root_rejected','tampered_proof_rejected'])
   assert s['proof_bytes']>0 and s['prove_ms']>0 and s['verify_ms']>0
  if 'jolt' in name:assert panic==bad and rows[0]['zk_feature'] and 'actual invalid execution proofs' in rows[-1]['negative_scope']
  else:assert panic==0
  assert r['exit_code']==0 and r['stop_reason'] is None
  if group=='pi':
   assert r['parent_limits_bytes']=={'memory.high':1200*2**20,'memory.max':1536*2**20,'memory.swap.max':0}
   assert r['ssh_oom_score_adj']==-900 and r['watchdog_verified_outside_slice']
   assert r['limits_bytes']['memory.swap.max']==0 and r['sampled_swap_peak_bytes']==0
   assert r['cgroup_peak_bytes']<=r['limits_bytes']['memory.max']
   for k in ['oom','oom_kill']:assert r['memory_events_before'][k]==r['memory_events_after'][k]
   assert all(int(s,16)&15==0 for s in r['throttle_samples'])
   mem=read(p/'memory-summary.json');assert mem['cgroup_kernel_peak_bytes']==r['cgroup_peak_bytes'] and mem['cgroup_swap_max_bytes']==0
 p=ROOT/'week24/logs/pi-euclidean-next/next-kimchi-pi-v1'
 assert read(p/'resource.json')['exit_code']==101 and 'missing SRS file' in (p/'stderr.log').read_text()
 p=ROOT/'week24/logs/pi-euclidean-next/next-jolt-pi-v1'
 assert read(p/'resource.json')['exit_code']==101 and "failed to run jolt" in (p/'stderr.log').read_text()
 assert not any(r.get('all_verified') for r in records(p)[0])
 health=read(ROOT/'week24/logs/euclidean-next-final-health.json')
 assert health['watchdog_active'] and health['slice_active'] and health['ssh_oom_score_adj']==-900
 assert health['system_swap_used_bytes']==0 and int(health['throttled'],16)&15==0
 summary=read(ROOT/'week24/logs/euclidean-next-summary.json');assert summary['cpu_quota_percent']==25 and [r['n'] for r in summary['results']]==[7,7,1]
 print('Next evidence verified: Mac 3 frameworks full7; Pi Kimchi/Binius64 full7, Jolt quick1 + negative2; failed attempts preserved')
if __name__=='__main__':main()
