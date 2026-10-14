"""Validate Mac-only evidence and the separately restored Pi guard."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines() if s.startswith('{')]
m=read(ROOT/'week24/manifests/observation-followup.json')
for name,digest in m['file_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
base=ROOT/'week24/logs/observation-followup';data=ROOT/'week24/data/observation-followup';samples=rows(data/'samples.jsonl');assert len(samples)==19
for n,v in [(1,1),(2,1),(4,1),(4,2),(4,3)]:
 p=base/f'mac-n{n}-v{v}';meta=read(p/'metadata.json');r=read(p/'resource.json');stream=rows(p/'benchmark.jsonl')
 assert meta['cpu_quota_percent'] is None and r['os']=='macos' and stream[0]['os']=='darwin'
 failed=n==4 and v==2
 assert (r['exit_code']==-15 and r['stop_reason']=='system_swap_growth_limit') if failed else (r['exit_code']==0 and r['stop_reason'] is None)
 assert r['rss_limit_bytes']==4096*2**20 and r['system_swap_growth_limit_bytes']==512*2**20
 delta=max(s['system_swap_delta_bytes'] for s in rows(p/'memory.jsonl'));assert delta>512*2**20 if failed else delta<=512*2**20
 if not failed:assert stream[-1]['all_verified'] and stream[-1]['samples']==4 and stream[-1]['invalid_cases_rejected']==(4 if n==1 else 5)
 else:assert not any(s.get('all_verified') for s in stream)
 for name,digest in meta['source_sha256'].items():assert hashlib.sha256((ROOT/'experiments/pi4-euclidean-evaluation/workload'/name).read_bytes()).hexdigest()==digest
 xs=[s for s in samples if s['run_id']==meta['run_id']];assert len(xs)==(3 if failed else 4) and sum(s['warmup'] for s in xs)==1
 for s in xs:
  assert s['observation_count']==n and s['proof_randomness_new'] and s['prove_memory_bytes'] is None
  assert all(s[k] for k in ['verified','changed_public_rejected','changed_root_rejected','tampered_proof_rejected'])
 for phase in ['input_arrival','input_dequeue']:assert len([s for s in stream if s['phase']==phase])==3
h=read(base/'pi-health-after-restore.json');assert h['watchdog_active'] and h['slice_active'] and h['ssh_oom_score_adj']==-900 and h['system_swap_used_bytes']==0
assert int(h['throttled'],16)&15==0
assert not m['pi_n4_verified']
print('Followup verified: Mac n1/n2 full; n4 complete2, swap-stopped1; Pi n4 remains unverified; runtime guards restored')
