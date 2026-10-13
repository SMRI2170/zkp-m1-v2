"""Check successful/failed evidence boundaries without proofs or hardware."""
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'experiments/pi4-euclidean-additional'
BASE = ROOT/'week24/logs/pi-euclidean-additional'

def read(p): return json.loads(p.read_text())
def lines(p): return [json.loads(s) for s in p.read_text().splitlines()]

def main():
    manifest = read(ROOT/'week24/manifests/euclidean-additional.json')
    for name, digest in manifest['source_sha256'].items():
        assert hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() == digest, name
    summary = read(ROOT/'week24/logs/euclidean-additional-summary.json')
    evaluation = read(ROOT/'week24/logs/euclidean-additional-evaluation.json')
    assert {s['run'] for s in summary['records']} == set(evaluation['hardware_proof_success_runs'])
    assert len(summary['records']) == 5
    assert set(summary['unmeasured']) == {'Plonky2','RISC Zero','SP1'}
    for record in summary['records']:
        run=BASE/record['run']; logs=lines(run/'benchmark.jsonl'); resource=read(run/'resource.json')
        assert logs[0]['arch']=='aarch64' and logs[0]['os']=='linux'
        assert logs[-1]['all_verified'] and logs[-1]['samples']==7 and not logs[-1]['proofs_saved']
        assert any(r.get('invalid_cases_rejected')==6 for r in logs)
        samples=[r for r in logs if r['phase']=='sample']
        assert {r['case_id'] for r in samples}==set(range(7))
        for row in samples:
            for key in ['verified','changed_public_rejected','tampered_proof_rejected']:
                assert row[key] is True, (record['run'],key)
        if record['run']=='additional-halo2-kzg-v1':
            # This run tests d2 modification; standalone r modification is unmeasured.
            assert all('changed_root_rejected' not in r for r in samples)
        else:
            assert all(r['changed_root_rejected'] is True for r in samples)
        assert resource['exit_code']==0 and resource['stop_reason'] is None
        assert resource['limits_bytes']=={'memory.max':256*2**20,'memory.high':192*2**20,'memory.swap.max':0}
        assert resource['parent_limits_bytes']['memory.max']==1536*2**20
        assert resource['ssh_oom_score_adj']==-900 and resource['watchdog_verified_outside_slice']
        assert resource['sampled_swap_peak_bytes']==0
        for key in ['oom','oom_kill','oom_group_kill']:
            assert resource['memory_events_before'][key]==resource['memory_events_after'][key]
        assert all(int(s,16)&0xf==0 for s in resource['throttle_samples'])
        memory=lines(run/'memory.jsonl'); durations=[b['elapsed_s']-a['elapsed_s'] for a,b in zip(memory,memory[1:])]
        assert all(d>0 for d in durations)
        mean=sum(row['cgroup_current_bytes']*dt for row,dt in zip(memory,durations))/sum(durations)
        assert math.isclose(mean,record['memory_time_weighted_mean_bytes'],rel_tol=1e-12)
        flow=statistics.mean(r.get('witness_ms',0)+r['prove_ms']+r['verify_ms'] for r in samples)
        assert math.isclose(flow,record['flow_mean_ms'],rel_tol=1e-12)
        assert record['proof_mean_bytes']==statistics.mean(r['proof_bytes'] for r in samples)
        for name,digest in record['source_log_sha256'].items():
            assert hashlib.sha256((run/name).read_bytes()).hexdigest()==digest
    for run in ['additional-plonky2-v1','additional-plonky2-v2','additional-plonky2-cpu25-v3']:
        assert not any(r.get('all_verified') for r in lines(BASE/run/'benchmark.jsonl'))
    invalid=[]
    for i,s in enumerate((BASE/'additional-plonky2-v2/memory.jsonl').read_text().splitlines(),1):
        try: json.loads(s)
        except json.JSONDecodeError: invalid.append(i)
    assert invalid == evaluation['plonky2']['v2']['invalid_or_truncated_memory_lines'] == [1366]
    terminal=read(BASE/'additional-plonky2-cpu25-v3/terminal-resource.json')
    assert 'original resource.json was not retrieved' in terminal['data_source']
    assert terminal['stop_reason']=='current_undervoltage_or_throttling' and int(terminal['throttled_after'],16)&0xf
    assert terminal['memory_events_after']['oom']==terminal['memory_events_before']['oom']==0
    original=read(BASE/'additional-plonky2-cpu25-v3/resource.json')
    assert all(original[k]==v for k,v in terminal.items() if k in original)
    health=read(ROOT/'week24/logs/euclidean-additional-final-health.json')
    assert health['watchdog_active'] and health['slice_active'] and health['ssh_oom_score_adj']==-900
    assert int(health['throttled'],16)&0xf==0
    assert not evaluation['zkvm']['sp1']['pi_proof_executed'] and not evaluation['zkvm']['risc_zero']['pi_proof_executed']
    assert read(BASE/'additional-sp1-cli-v2/resource.json')['exit_code']==0
    assert 'cargo-prove sp1' in (BASE/'additional-sp1-cli-v2/benchmark.jsonl').read_text()
    print('Additional evidence verified: 35 native proofs; failures and CLI/preflight kept separate')

if __name__=='__main__': main()
