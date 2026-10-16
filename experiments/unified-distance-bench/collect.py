"""Collect the balanced protocol; archived n=7/20 runs cannot pass as new n=21."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from protocol import VERSION, EXPECTED, stats, validate_samples

def read_rows(path):
    result=[];errors=[]
    if not path.exists():return [],['missing benchmark log']
    for i,line in enumerate(path.read_text().splitlines(),1):
        if not line.strip().startswith('{'):continue
        try:result.append(json.loads(line))
        except json.JSONDecodeError:errors.append('invalid JSON line '+str(i))
    return result,errors

def weighted_memory(rows):
    # Last sample has no known duration beyond its timestamp.
    pairs=list(zip(rows,rows[1:]));span=0.;area=0.
    for a,b in pairs:
        dt=b['elapsed_s']-a['elapsed_s']
        if dt<0:raise ValueError('memory clock moved backwards')
        area+=a['cgroup_current_bytes']*dt;span+=dt
    return area/span if span>0 else None

def resource_ok(r):
    before=r.get('memory_events_before',{});after=r.get('memory_events_after',{})
    return (r.get('exit_code')==0 and r.get('stop_reason') is None
        and type(before.get('oom_kill')) is int and after.get('oom_kill')==before['oom_kill']
        and r.get('sampled_swap_peak_bytes')==0
        and r.get('cpu_quota_percent')==25 and r.get('threads')==1
        and len(r.get('benchmark_cpu_affinity',[]))==1
        and r.get('throttle_samples') and all(int(v,16)&0xF==0 for v in r['throttle_samples']))

def collect_run(path):
    meta=json.loads((path/'metadata.json').read_text())
    required=['run_id','framework','host_class','cpu_quota_percent','threads','flow_scope','proof_encoding','protocol','binary_sha256','build_metadata']
    if any(k not in meta for k in required):raise ValueError('missing metadata')
    if meta['protocol']!=VERSION:raise ValueError('wrong collection protocol')
    rows,errors=read_rows(path/'benchmark.jsonl')
    samples=[r for r in rows if r.get('phase')=='sample']
    complete=validate_samples(samples)
    summary=rows[-1] if rows else {}
    valid_summary=(summary.get('phase')=='summary' and summary.get('all_verified') is True
        and summary.get('samples')==21 and summary.get('warmups')==7 and summary.get('protocol')==VERSION)
    resource=json.loads((path/'resource.json').read_text()) if (path/'resource.json').exists() else {}
    healthy=resource_ok(resource)
    same_conditions=(meta['cpu_quota_percent']==25 and meta['threads']==1)
    status='completed' if complete and valid_summary and healthy and same_conditions and not errors else 'partial'
    memory,memory_errors=read_rows(path/'memory.jsonl')
    errors+=memory_errors
    if errors or len(memory)<2:status='partial'
    if meta.get('launcher_exit_code',0)!=0:status='partial'
    # read_rows also accepts ordinary JSON telemetry without phase.
    measurement=[]
    for r in samples:
        x={k:r[k] for k in ['sample_id','case_id','warmup','repetition','prove_ms','verify_ms','verified']}
        x.update(run_id=meta['run_id'],framework=meta['framework'],witness_ms=r.get('witness_ms'),proof_bytes=r.get('proof_bytes'),public_bytes=r.get('public_bytes',r.get('public_scalar_bytes')))
        x['flow_ms']=r['prove_ms']+r['verify_ms']+r.get('witness_ms',0)
        measurement.append(x)
    measured=[r for r in measurement if not r['warmup']]
    record={**meta,'status':status,'measured_samples':len(measured),'expected_samples':EXPECTED,
        'warmup_samples':len(samples)-len(measured),'successful_summary':valid_summary,'resource_healthy':bool(healthy),
        'parse_errors':errors,'flow_ms':stats(r['flow_ms'] for r in measured),
        'phase_ms':{k:stats(r[k] for r in measured if r.get(k) is not None) for k in ['witness_ms','prove_ms','verify_ms']},
        'proof_bytes':stats(r['proof_bytes'] for r in measured if r.get('proof_bytes') is not None),
        'preparation':[{k:r[k] for k in ['phase','compile_ms','key_load_ms','setup_ms'] if k in r} for r in rows if any(k in r for k in ['compile_ms','key_load_ms','setup_ms'])],
        'by_case':[{'case_id':i,'flow_ms':stats(r['flow_ms'] for r in measured if r['case_id']==i)} for i in range(7)],
        'whole_run_memory_mean_bytes':weighted_memory(memory),
        'whole_run_kernel_peak_bytes':resource.get('cgroup_peak_bytes'),
        'whole_run_sampled_peak_bytes':max((r['cgroup_current_bytes'] for r in memory),default=None),
        'resource':resource,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir() if p.is_file()}}
    return record,measurement

def main():
    p=argparse.ArgumentParser();p.add_argument('--runs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    records=[];samples=[]
    for path in sorted(a.runs.iterdir()):
        if path.is_dir() and (path/'metadata.json').exists():
            r,s=collect_run(path);records.append(r);samples+=s
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/'summary.json').write_text(json.dumps(records,indent=2)+'\n')
    (a.out/'samples.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in samples))
    fields=list(samples[0]) if samples else ['run_id','case_id','repetition','flow_ms']
    with (a.out/'samples.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(samples)
    print(json.dumps({'runs':len(records),'completed':sum(r['status']=='completed' for r in records),'scope':'recorded measurements only; no proving during collection'}))
if __name__=='__main__':main()
