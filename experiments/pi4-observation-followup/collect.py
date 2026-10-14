"""Keep native Mac workload measurements distinct from Pi cgroup/CPU quota metrics."""
import argparse,csv,json,statistics,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--runs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
def rows(p):return [json.loads(s) for s in p.read_text().splitlines() if s.startswith('{')]
def write(name,rs):
 (a.out/(name+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rs))
 with (a.out/(name+'.csv')).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=sorted(set().union(*(r.keys() for r in rs))),lineterminator='\n');w.writeheader();w.writerows(rs)
samples=[];trials=[];queue=[];hashes={}
for run in sorted(a.runs.iterdir()):
 if not run.is_dir():continue
 meta=json.loads((run/'metadata.json').read_text());resource=json.loads((run/'resource.json').read_text());stream=rows(run/'benchmark.jsonl');base={k:meta[k] for k in ['run_id','host_class','cpu_quota_percent','observation_count','compute_parallelism']}
 assert resource['os']=='macos' and stream[0]['os']=='darwin'
 success=resource['exit_code']==0 and resource['stop_reason'] is None and stream[-1].get('all_verified',False)
 if success:assert stream[-1]['samples']==4
 keys=next(r for r in stream if r['phase']=='keys')
 trials.append({**base,'compile_ms':keys['compile_ms'],'setup_ms':keys['setup_ms'],'constraints':keys['constraints'],'vk_bytes':keys['vk_bytes'],'binary_bytes':meta['binary_bytes'],'whole_run_sampled_process_tree_rss_peak_bytes':resource['sampled_process_tree_peak_bytes'],'memory_scope':meta['memory_scope'],'elapsed_s':resource['elapsed_s'],'status':'completed' if success else 'failed_or_partial','exit_code':resource['exit_code'],'stop_reason':resource['stop_reason']})
 for r in stream:
  if r['phase']=='sample':samples.append({**base,**r,'trial_completed':success,'flow_ms':r['witness_ms']+r['prove_ms']+r['verify_ms'],'prove_memory_bytes':None,'prove_memory_unavailable_reason':'host guard has no same-clock phase memory markers; no Pi cgroup surrogate'})
  if r['phase'] in ['input_arrival','input_dequeue']:queue.append({**base,**r})
 for f in run.iterdir():
  if f.is_file():hashes[str(f.relative_to(a.runs))]=hashlib.sha256(f.read_bytes()).hexdigest()
write('samples',samples);write('trials',trials);write('queue_observed_1hz',queue)
summary=[]
for t in trials:
 xs=[r for r in samples if r['run_id']==t['run_id'] and not r['warmup']];flows=[r['flow_ms'] for r in xs]
 summary.append({**t,'n':len(xs),'flow_mean_ms':statistics.mean(flows),'flow_median_ms':statistics.median(flows),'flow_sd_ms':statistics.stdev(flows),'max_wait_ms':max(r['wait_ms'] for r in queue if r['run_id']==t['run_id'] and r['phase']=='input_dequeue')})
(a.out/'summary.json').write_text(json.dumps({'scope':'Mac native CPU, quota unset; warmup1+within-process repeat3; not Pi or independent cold repetition','results':summary},indent=2)+'\n')
(a.out/'schema.json').write_text(json.dumps({'time_units':'ms/s/ns in names','size_units':'bytes','memory':'whole-run sampled process-tree RSS, soft monitor; no phase-specific or Pi cgroup claims','missing':'JSON null/CSV empty, not zero','raw_file_sha256':hashes},indent=2)+'\n')
print(json.dumps(summary))
