"""Verify evidence scopes and its normalized tables without rerunning proofs."""
import gzip,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines() if s.startswith('{')]
def main():
 m=read(ROOT/'week24/manifests/euclidean-evaluation.json')
 for name,digest in m['file_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
 assert (ROOT/'experiments/pi4-euclidean-evaluation/rendered/cases.rs').read_text()==(ROOT/'experiments/pi4-euclidean-next/cases.rs').read_text()+'\n'+(ROOT/'experiments/pi4-euclidean-evaluation/instrument.rs').read_text()
 data=ROOT/'week24/data/euclidean-evaluation';samples=rows(data/'samples.jsonl');trials=rows(data/'trials.jsonl');assert len(trials)==3 and len(samples)==12
 for t in trials:
  assert t['status']=='completed' and t['cpu_quota_percent']==25 and t['threads']==1
  assert t['warmup_count']==1 and t['repeat_count']==3 and t['oom_kill_delta']==0 and t['swap_peak_bytes']==0
  p=ROOT/'week24/logs/pi-euclidean-evaluation'/t['run_id'];r=read(p/'resource.json');meta=read(p/'metadata.json');raw=rows(p/'benchmark.jsonl')
  assert r['exit_code']==0 and r['stop_reason'] is None and r['cpu_quota_percent']==25 and r['ssh_oom_score_adj']==-900 and r['watchdog_verified_outside_slice']
  assert r['parent_limits_bytes']=={'memory.high':1200*2**20,'memory.max':1536*2**20,'memory.swap.max':0}
  assert r['limits_bytes']['memory.swap.max']==0 and r['sampled_swap_peak_bytes']==0
  for k in ['oom','oom_kill']:assert r['memory_events_before'][k]==r['memory_events_after'][k]
  assert all(int(s,16)&15==0 for s in r['throttle_samples'])
  assert not read(p/'filesystem-audit.json')['created_files']
  local=ROOT/'experiments/pi4-euclidean-evaluation/rendered'/t['framework']/('host/src/main.rs' if t['framework']=='jolt' else 'src/main.rs')
  key=t['framework']+('/host/src/main.rs' if t['framework']=='jolt' else '/src/main.rs')
  assert hashlib.sha256(local.read_bytes()).hexdigest()==meta['build_metadata']['source_sha256'][key]
  xs=[s for s in samples if s['run_id']==t['run_id']];assert len(xs)==4 and sum(s['warmup'] for s in xs)==1
  assert [s['repetition'] for s in xs if not s['warmup']]==[0,1,2]
  for s in xs:
   assert s['case_id']==1 and s['trial_completed'] and s['proof_randomness_new']
   assert all(s[k] is True for k in ['verified','changed_public_rejected','changed_root_rejected','tampered_proof_rejected'])
   assert s['prove_memory_samples']>2 and s['prove_memory_time_weighted_mean_bytes']>0
   assert s['prove_memory_sampled_peak_bytes']<=r['cgroup_peak_bytes'] and s['proof_bytes']>0 and s['public_input_bytes']>0
   assert abs(s['flow_ms']-sum(s.get(k,0) for k in ['witness_ms','prove_ms','verify_ms']))<1e-6
  negatives=[s for s in raw if s['phase']=='raw_witness_test']
  if t['framework']!='jolt':assert len(negatives)==1 and not negatives[0]['accepted'] and negatives[0]['outcome'] in ['prover_error','prover_panic','verifier_rejected']
  else:assert raw[0]['zk_feature'] and not negatives
  assert raw[-1]['all_verified'] and raw[-1]['samples']==4 and raw[-1]['invalid_cases_rejected']==(2 if t['framework']=='jolt' else 6)
 queue=rows(data/'queue_model_1hz.jsonl');assert len(queue)==9 and all(not s['measured_load_test'] for s in queue)
 coverage=read(data/'coverage.json');pending={s['item'] for s in coverage['items'] if s['status']=='pending'}
 assert {'independent_cold_repetitions','long_term_leak_sidechannel'}<=pending
 work=ROOT/'week24/data/observation-workload';wt=rows(work/'trials.jsonl');ws=rows(work/'samples.jsonl');wq=rows(work/'queue_observed_1hz.jsonl')
 completed=[t for t in wt if t['status']=='completed'];assert {t['observation_count'] for t in completed}=={1,2}
 for t in completed:
  p=ROOT/'week24/logs/pi-observation-workload'/t['run_id'];meta=read(p/'metadata.json');r=read(p/'resource.json');raw=rows(p/'benchmark.jsonl')
  assert r['exit_code']==0 and r['stop_reason'] is None and r['cpu_quota_percent']==25 and r['sampled_swap_peak_bytes']==0
  assert r['ssh_oom_score_adj']==-900 and r['watchdog_verified_outside_slice'] and r['limits_bytes']['memory.max']==512*2**20
  assert all(int(s,16)&15==0 for s in r['throttle_samples'])
  for k in ['oom','oom_kill']:assert r['memory_events_after'][k]==r['memory_events_before'][k]
  assert not read(p/'filesystem-audit.json')['created_files']
  for name,digest in meta['source_sha256'].items():assert hashlib.sha256((ROOT/'experiments/pi4-euclidean-evaluation/workload'/name).read_bytes()).hexdigest()==digest
  xs=[s for s in ws if s['run_id']==t['run_id']];assert len(xs)==4 and sum(s['warmup'] for s in xs)==1
  assert all(s['verified'] and s['proof_randomness_new'] and s['prove_memory_samples']>2 for s in xs)
  qq=[s for s in wq if s['run_id']==t['run_id']];assert len(qq)==6 and all(s['measured_load_test'] for s in qq)
  for stage in ['input_arrival','input_dequeue']:assert [s['repetition'] for s in qq if s['phase']==stage]==[0,1,2]
  negatives=[s for s in raw if s['phase']=='workload_negative'];assert len(negatives)==(4 if t['observation_count']==1 else 5) and all(s['rejected'] for s in negatives)
  assert raw[-1]['all_verified'] and t['constraints']>0 and t['compile_ms']>0
 partial=[t for t in wt if t['status']!='completed'];assert len(partial)==1 and partial[0]['observation_count']==4 and partial[0]['exit_code'] is None
 p=ROOT/'week24/logs/pi-observation-workload'/partial[0]['run_id'];assert not (p/'resource.json').exists() and not any(r.get('all_verified') for r in rows(p/'benchmark.jsonl'))
 anomaly=read(work/'schema.json')['parse_anomalies'];assert len(anomaly)==1 and anomaly[0]['reason']=='invalid_or_truncated_json_preserved_in_raw'
 partial_stats=read(p/'partial-memory-summary.json');assert hashlib.sha256(gzip.decompress((p/'memory.jsonl.gz').read_bytes())).hexdigest()==partial_stats['raw_uncompressed_sha256']
 assert partial_stats['inference']=='resource/OOM/power outcome unknown; reboot observed; no successful proof claimed'
 health=read(ROOT/'week24/logs/euclidean-evaluation-final-health.json');assert health['watchdog_active'] and health['slice_active'] and health['ssh_oom_score_adj']==-900
 assert health['system_swap_used_bytes']==0 and int(health['throttled'],16)&15==0
 print('Evaluation evidence verified: 3 frameworks, warmup1 + repeat3 each; phase memory, raw-witness outcomes, null semantics and model/pending scopes preserved')
if __name__=='__main__':main()
