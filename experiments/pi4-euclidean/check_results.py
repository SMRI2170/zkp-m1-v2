"""Validate public experiment evidence and hashes; does not rerun hardware or proofs."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
logs=root/'week24/logs/pi-euclidean'
valid=['euclidean-groth16-v1','euclidean-plonk-v1','euclidean-rapid-v3','euclidean-halo2-v2','euclidean-noir-v1','euclidean-nova-v2','euclidean-hypernova-v1']
for name in valid:
    p=logs/name;r=json.loads((p/'resource.json').read_text())
    assert r['exit_code']==0 and r['stop_reason'] is None,name
    assert r['sampled_swap_peak_bytes']==0 and r['parent_limits_bytes']=={'memory.high':1200*2**20,'memory.max':1536*2**20,'memory.swap.max':0}
    assert r['ssh_oom_score_adj']==-900 and r['watchdog_verified_outside_slice']
    assert all(int(v,16)&15==0 for v in r['throttle_samples'])
    assert all(r['memory_events_after'][k]==r['memory_events_before'][k] for k in ['high','max','oom','oom_kill'])
    rows=[json.loads(l) for l in (p/'benchmark.jsonl').read_text().splitlines() if l.startswith('{')]
    assert rows[0]['os']=='linux' and rows[0]['arch'] in ['arm64','aarch64']
    assert rows[-1]['phase']=='summary' and rows[-1]['all_verified']
    samples=[v for v in rows if v['phase']=='sample']
    assert len(samples)==(21 if name.startswith(('euclidean-groth16','euclidean-plonk')) else 7)
    assert {v['case_id'] for v in samples}==set(range(7)) and all(v['verified'] for v in samples)
    if 'nova' in name:
        assert rows[-1]['final_zk'] is False and rows[-1]['raw_ivc_contains_witness'] is True
        assert all(v['claimed_state_rejections']==3 for v in samples)
    elif name.startswith(('euclidean-groth16','euclidean-plonk')):
        n=next(v for v in rows if v['phase']=='negative')
        assert all(n[k] for k in ['changed_public_rejected','tampered_proof_rejected','incorrect_output_witness_rejected','out_of_range_input_rejected'])
        assert n['euclidean_extra_invalid_witnesses_rejected']==7
    else:
        assert all(v['changed_public_rejected'] and v['tampered_proof_rejected'] for v in samples)
    if name=='euclidean-rapid-v3':assert next(v for v in rows if v['phase']=='native-invalid-witness')['rejected']
    mem=[json.loads(l) for l in (p/'memory.jsonl').read_text().splitlines()]
    assert len(mem)==r['poll_samples'] and all(v['system_available_bytes']>=2**30 and v['cgroup_swap_bytes']==0 and v['system_swap_used_bytes']==0 for v in mem)
    stats=json.loads((p/'memory-summary.json').read_text())
    assert stats['samples']==len(mem) and stats['cgroup_kernel_peak_bytes']==r['cgroup_peak_bytes']
    assert max(v['cgroup_current_bytes'] for v in mem)<=r['cgroup_peak_bytes']<=r['limits_bytes']['memory.max']
for name in ['euclidean-rapid-exit-audit','euclidean-noir-exit-audit']:
    p=logs/name;r=json.loads((p/'resource.json').read_text())
    assert r['exit_code']==0 and r['stop_reason'] is None and r['sampled_swap_peak_bytes']==0
    rows=[json.loads(l) for l in (p/'benchmark.jsonl').read_text().splitlines() if l.startswith('{')]
    assert rows[-1]['all_verified'] and rows[-1]['negative_verifier_exit_code']==1
    assert {v['case_id'] for v in rows if v['phase']=='sample'}==set(range(7))
failed=json.loads((logs/'euclidean-nova-v1/resource.json').read_text())
assert failed['stop_reason']=='current_undervoltage_or_throttling' and failed['exit_code']!=0
assert any(int(x,16)&15 for x in failed['throttle_samples'])
assert 'changed public accepted' in (logs/'euclidean-rapid-v1/stderr.log').read_text()
health=json.loads((root/'week24/logs/euclidean-final-health.json').read_text())
assert health['slice_active'] and health['watchdog_active'] and health['ssh_oom_score_adj']==-900
assert health['current_kernel_oom_matches']==health['previous_kernel_oom_matches']==0
assert health['week24_tmpfs_remnants']==[]
manifest=json.loads((root/'week24/manifests/euclidean-frameworks.json').read_text())
source=root/'experiments/pi4-euclidean'
for name,h in manifest['source_sha256'].items():assert hashlib.sha256((source/name).read_bytes()).hexdigest()==h,name
# All serialized setup/proof/private-assignment material must stay local-only.
assert not any(p.suffix in ['.ptau','.zkey','.wtns','.bin'] for p in source.rglob('*') if 'target' not in p.parts)
print(json.dumps({'valid_pi_framework_configurations':7,'failure_records_preserved':2,'source_hashes_verified':len(manifest['source_sha256']),'scope':'evidence schema/hash checks; not a new Pi/proof execution'}))
