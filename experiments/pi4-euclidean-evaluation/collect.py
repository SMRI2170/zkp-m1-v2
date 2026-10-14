"""Normalize raw trials into plotting-ready CSV/JSONL; unavailable metrics stay null."""
import argparse,csv,gzip,hashlib,json,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--runs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
parse_anomalies=[]
def rows(p):
 result=[]
 if not p.exists() and p.with_suffix(p.suffix+'.gz').exists():p=p.with_suffix(p.suffix+'.gz')
 if not p.exists():parse_anomalies.append({'file':str(p.relative_to(a.runs)),'reason':'missing_file'});return result
 text=gzip.decompress(p.read_bytes()).decode() if p.suffix=='.gz' else p.read_text()
 for no,line in enumerate(text.splitlines(),1):
  if not line.startswith('{'):continue
  try:result.append(json.loads(line))
  except json.JSONDecodeError:parse_anomalies.append({'file':str(p.relative_to(a.runs)),'line':no,'reason':'invalid_or_truncated_json_preserved_in_raw'})
 return result
def weighted_mean(values):
 pairs=[(y['elapsed_s']-x['elapsed_s'],x['cgroup_current_bytes']) for x,y in zip(values,values[1:]) if y['elapsed_s']>x['elapsed_s']]
 return sum(t*v for t,v in pairs)/sum(t for t,v in pairs) if pairs else None
def write(name,values):
 (a.out/(name+'.jsonl')).write_text(''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in values))
 fields=sorted(set().union(*(s.keys() for s in values))) if values else []
 with (a.out/(name+'.csv')).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(values)
samples=[];trials=[];memory=[];checks=[];observed_queue=[];hashes={}
for run in sorted(x for x in a.runs.iterdir() if x.is_dir()):
 meta=read(run/'metadata.json');stream=rows(run/'benchmark.jsonl');resource=read(run/'resource.json') if (run/'resource.json').exists() else {};mem=rows(run/'memory.jsonl');proto=next((r for r in stream if r['phase']=='collection_protocol'),{})
 for key in ['repeat_count','warmup_count']:
  if key in meta and proto:assert meta[key]==proto[key],f'{run.name}: metadata/protocol mismatch: {key}'
 base={k:meta[k] for k in ['run_id','framework','variant','host_class','cpu_quota_percent','threads','binary_sha256','source_revision']}
 if 'observation_count' in meta:base['observation_count']=meta['observation_count']
 success=resource.get('exit_code')==0 and resource.get('stop_reason') is None and any(r.get('all_verified') for r in stream)
 trials.append({**base,'status':'completed' if success else 'failed_or_partial','exit_code':resource.get('exit_code'),'stop_reason':resource.get('stop_reason'),'external_stop_reason':meta.get('external_stop_reason'),'setup_ms':next((r.get('setup_ms') for r in stream if r['phase']=='keys'),None),'compile_ms':next((r.get('compile_ms') for r in stream if r['phase']=='keys'),None),'constraints':next((r.get('constraints') for r in stream if r['phase']=='keys'),None),'vk_bytes':next((r.get('vk_bytes') for r in stream if r['phase']=='keys'),None),'binary_bytes':meta.get('binary_bytes'),'guest_elf_bytes':meta.get('guest_elf_bytes'),'whole_unit_time_weighted_mean_bytes':weighted_mean(mem),'whole_unit_peak_bytes':resource.get('cgroup_peak_bytes'),'elapsed_s':resource.get('elapsed_s'),'warmup_count':proto.get('warmup_count'),'repeat_count':proto.get('repeat_count'),'swap_peak_bytes':resource.get('sampled_swap_peak_bytes'),'oom_kill_delta':resource.get('memory_events_after',{}).get('oom_kill',0)-resource.get('memory_events_before',{}).get('oom_kill',0) if resource else None,'temperature_before_C':resource.get('temperature_before_C'),'temperature_after_C':resource.get('temperature_after_C')})
 for row in mem:memory.append({'run_id':base['run_id'],**{k:v for k,v in row.items() if k!='process'},**{'process_'+k:v for k,v in row.get('process',{}).items()}})
 markers={}
 for r in stream:
  if r['phase'] in ['input_arrival','input_dequeue']:observed_queue.append({**base,**r})
  if r['phase']=='phase_marker':markers.setdefault(r['sample_id'],{})[r['stage']]=r
  if r['phase'] in ['raw_witness_test','workload_negative','summary']:checks.append({**base,**r})
 for r in stream:
  if r['phase']!='sample':continue
  mark=markers.get(r['sample_id'],{});begin=mark.get('prove_start',{}).get('wall_time_ns');end=mark.get('verify_start',{}).get('wall_time_ns')
  during=[s for s in mem if begin is not None and end is not None and begin<=s.get('wall_time_ns',-1)<end]
  def mean_time(rows):
   pairs=[(y['wall_time_ns']-x['wall_time_ns'],x['cgroup_current_bytes']) for x,y in zip(rows,rows[1:]) if y['wall_time_ns']>x['wall_time_ns']]
   return sum(t*v for t,v in pairs)/sum(t for t,v in pairs) if pairs else None
  witness=r.get('witness_ms');flow=sum(r[k] for k in ['prove_ms','verify_ms'])+(witness or 0)
  samples.append({**base,**r,'trial_completed':success,'witness_start_wall_time_ns':mark.get('witness_start',{}).get('wall_time_ns'),'prove_start_wall_time_ns':begin,'verify_end_wall_time_ns':mark.get('verify_end',{}).get('wall_time_ns'),'witness_timing_scope':'separate' if witness is not None else 'included_in_prove','flow_ms':flow,'prove_memory_sampled_peak_bytes':max((s['cgroup_current_bytes'] for s in during),default=None),'prove_memory_time_weighted_mean_bytes':mean_time(during),'prove_memory_samples':len(during),'prove_temperature_mean_C':statistics.mean(s['temperature_C'] for s in during) if during else None})
 for f in run.rglob('*'):
  if f.is_file():hashes[str(f.relative_to(a.runs))]=hashlib.sha256(f.read_bytes()).hexdigest()
write('samples',samples);write('trials',trials);write('memory',memory);write('checks',checks)
# Serial FIFO arrival model driven by measured services. It is not a real 1Hz load test.
queues=[]
for trial in trials:
 group=[s for s in samples if s['run_id']==trial['run_id'] and not s.get('warmup')];finish=0.
 for i,s in enumerate(group):
  arrival=i*1000.;start=max(arrival,finish);finish=start+s['flow_ms'];queues.append({'run_id':s['run_id'],'framework':s['framework'],'repetition':s['repetition'],'arrival_ms':arrival,'service_ms':s['flow_ms'],'wait_ms':start-arrival,'finish_ms':finish,'response_ms':finish-arrival,'evaluation_mode':'trace_driven_serial_fifo_model','measured_load_test':False,'trial_completed':s['trial_completed']})
write('queue_model_1hz',queues);write('queue_observed_1hz',observed_queue)
(a.out/'schema.json').write_text(json.dumps({'schema_version':1,'thread_semantics':'configured compute parallelism, not measured OS thread count','units':{'time':'ms or explicit _s/_ns','memory_and_size':'bytes','temperature':'C'},'missing':'JSON null / empty CSV; never zero-fill unavailable','clock':'phase markers and memory sampling use same-host wall_time_ns; phase-local elapsed is monotonic; sampling bounds are approximate','statistics':'same-input within-process preliminary repeats; exclude warmup; not independent cold trials; current n=3 has no confidence/p95 claim','memory_mean_scope':'prove interval mean uses the observed span between in-interval samples; no interpolation across missing boundaries','privacy':'only sizes and diagnostic distinctness; proof/VK/private assignments remain RAM-only','queue_model':'model only; queue_observed_1hz holds actual synthetic batch arrival/dequeue events when present','parse_anomalies':parse_anomalies,'raw_file_sha256':hashes},indent=2)+'\n')
print(json.dumps({'trials':len(trials),'samples':len(samples),'memory_samples':len(memory)}))
