"""Descriptive summaries only; no p95/CI claims from three autocorrelated repeats."""
import argparse,csv,json,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);a=p.parse_args()
rows=[json.loads(s) for s in (a.data/'samples.jsonl').read_text().splitlines()];trials=[json.loads(s) for s in (a.data/'trials.jsonl').read_text().splitlines()];summary=[]
for t in trials:
 xs=[s for s in rows if s['run_id']==t['run_id'] and not s['warmup']];verified=[s for s in xs if s.get('verified')]
 r={**t,'measured_samples':len(xs),'verified_samples':len(verified),'verified_fraction_of_recorded_samples':len(verified)/len(xs) if xs else None,'completed_fraction_of_planned_samples':len(xs)/t['repeat_count'] if t.get('repeat_count') else None,'repeat_scope':'within process; preliminary repeats; no population failure-rate inference','proof_nonidentical_diagnostic':all(s.get('proof_randomness_new') for s in xs) if xs else None}
 for key in ['flow_ms','witness_ms','prove_ms','verify_ms','proof_bytes','public_input_bytes','prove_memory_sampled_peak_bytes','prove_memory_time_weighted_mean_bytes']:
  vs=[s[key] for s in xs if s.get(key) is not None]
  for suffix,value in [('mean',statistics.mean(vs) if vs else None),('median',statistics.median(vs) if vs else None),('min',min(vs) if vs else None),('max',max(vs) if vs else None),('sd',statistics.stdev(vs) if len(vs)>1 else None)]:r[key+'_'+suffix]=value
 summary.append(r)
(a.data/'summary.json').write_text(json.dumps({'scope':'descriptive preliminary same-input repetitions, excluding warmup; no cross-security universal ranking','results':summary},indent=2)+'\n')
with (a.data/'summary.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=sorted(set().union(*(s.keys() for s in summary))),lineterminator='\n');w.writeheader();w.writerows(summary)
print(json.dumps([{k:r[k] for k in ['framework','measured_samples','flow_ms_mean','prove_memory_sampled_peak_bytes_max','vk_bytes']} for r in summary]))
