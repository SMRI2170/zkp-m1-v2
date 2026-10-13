"""Validate followup outcomes and keep Mac/Pi, partial/full and Core/final scopes explicit."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text())
def lines(p):return [json.loads(s) for s in p.read_text().splitlines()]
def main():
    manifest=read(ROOT/'week24/manifests/euclidean-followup.json')
    for name,digest in manifest['source_sha256'].items():
        assert hashlib.sha256((ROOT/'experiments/pi4-euclidean-followup'/name).read_bytes()).hexdigest()==digest,name
    old=read(ROOT/'week24/manifests/euclidean-additional.json')
    assert manifest['artifact_sha256']['plonky2_pi_existing']==old['binary_sha256']['plonky2']
    base=ROOT/'week24/logs/pi-euclidean-followup'
    p=base/'additional-plonky2-cpu25-v4';rows=lines(p/'benchmark.jsonl');samples=[s for s in rows if s['phase']=='sample']
    assert len(samples)==2 and {s['case_id'] for s in samples}=={0,1}
    assert not any(s.get('all_verified') for s in rows) and not (p/'resource.json').exists()
    memory=[];bad=[]
    for i,s in enumerate((p/'memory.jsonl').read_text().splitlines(),1):
        try:memory.append(json.loads(s))
        except json.JSONDecodeError:bad.append(i)
    partial=read(p/'partial-memory-summary.json')
    assert len(memory)==partial['complete_samples']==8436
    assert bad==partial['invalid_lines_preserved']==[8437]
    assert max(s['cgroup_current_bytes'] for s in memory)==partial['sampled_max_cgroup_bytes']
    assert all(s['cgroup_swap_bytes']==0 for s in memory)
    for s in samples:
        assert all(s[k] is True for k in ['verified','changed_public_rejected','changed_root_rejected','tampered_proof_rejected'])
    p=base/'additional-halo2-kzg-root-v2';rows=lines(p/'benchmark.jsonl');samples=[s for s in rows if s['phase']=='sample'];resource=read(p/'resource.json')
    assert len(samples)==7 and rows[-1]['all_verified'] and rows[-1]['proofs_saved'] is False
    assert rows[0]['os']=='linux' and rows[0]['arch']=='aarch64'
    assert any(s.get('invalid_cases_rejected')==6 for s in rows)
    for s in samples:assert all(s[k] for k in ['verified','changed_public_rejected','changed_root_rejected','tampered_proof_rejected'])
    assert resource['exit_code']==0 and resource['stop_reason'] is None
    assert resource['sampled_swap_peak_bytes']==0
    assert all(int(s,16)&0xf==0 for s in resource['throttle_samples'])
    for k in ['oom','oom_kill']:assert resource['memory_events_before'][k]==resource['memory_events_after'][k]
    mac=lines(ROOT/'week24/logs/plonky2-followup-host.jsonl');assert mac[0]['os']=='macos'
    assert mac[-1]['all_verified'] and mac[-1]['samples']==7 and mac[-1]['invalid_cases_rejected']==6
    base=ROOT/'week24/logs/zkvm-followup'
    p=base/'risc0-host-proof-v2';rows=lines(p/'benchmark.jsonl');resource=read(p/'resource.json')
    assert rows[0]['os']=='macos' and rows[-1]['all_verified'] and rows[-1]['samples']==1
    assert rows[-1]['changed_public_rejected'] and rows[-1]['wrong_image_rejected'] and not rows[-1]['proofs_saved']
    assert resource['exit_code']==0 and resource['stop_reason'] is None
    for name in ['sp1-host-proof-v1','sp1-host-proof-v2']:
        p=base/name;resource=read(p/'resource.json');rows=lines(p/'benchmark.jsonl')
        assert rows[0]['os']=='macos' and not any(s.get('all_verified') for s in rows)
        assert resource['exit_code']!=0 and resource['stop_reason']=='system_swap_growth_limit'
        assert max(s['system_swap_delta_bytes'] for s in lines(p/'memory.jsonl'))>512*2**20
    evaluation=read(ROOT/'week24/logs/euclidean-followup-evaluation.json')
    assert not evaluation['risc0']['pi_proof_executed'] and not evaluation['sp1']['pi_proof_executed']
    assert evaluation['sp1']['mac_verified_cases']==0 and not evaluation['plonky2']['full_pi_run_completed']
    health=read(ROOT/'week24/logs/euclidean-followup-final-health.json')
    assert health['watchdog_active'] and health['slice_active'] and health['ssh_oom_score_adj']==-900
    assert health['system_swap_used_bytes']==0 and int(health['throttled'],16)&0xf==0
    print('Followup evidence verified: Pi Plonky2 partial2, Halo2 full7; Mac Plonky2 full7, RISC Zero1; SP1 stopped2; scopes preserved')
if __name__=='__main__':main()
