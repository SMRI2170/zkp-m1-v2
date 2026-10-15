# coding: utf-8
"""Check recorded Pi evidence, separate from executing a new hardware proof in CI."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def read(path):return json.loads((ROOT/path).read_text())
def rows(path):
    path=ROOT/path
    text=gzip.decompress(path.read_bytes()).decode() if path.suffix=='.gz' else path.read_text()
    return [json.loads(line) for line in text.splitlines() if line.startswith('{')]

def main():
    manifest=read('week24/manifests/pi-stability.json')
    for name,digest in manifest['file_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    pre=rows('week24/logs/pi-stability/preflight-n4-v2/health.jsonl')
    summary=read('week24/logs/pi-stability/preflight-n4-v2/summary.json')
    assert len(pre)==3 and all(s['ready'] and all(s['checks'].values()) for s in pre)
    assert summary['all_ready'] and summary['no_observed_uptime_reset'] and summary['observed_uptime_span_s']>=60
    assert manifest['readiness_scope']=='before and during initialization; not three idle samples before load'
    run='week24/logs/pi-stability/eval-workload-n4-v2/'
    resource=read(run+'resource.json')
    stream=rows(run+'benchmark.jsonl')
    normal=[x for x in stream if x['phase']=='sample']
    assert resource['exit_code']==0 and resource['stop_reason'] is None
    assert len(normal)==4 and all(x['verified'] for x in normal)
    assert all(all(x[k] for k in ['changed_public_rejected','changed_root_rejected','tampered_proof_rejected']) for x in normal)
    assert sum(bool(x['warmup']) for x in normal)==1
    assert stream[-1]['phase']=='summary' and stream[-1]['all_verified']
    assert stream[-1]['invalid_cases_rejected']==5
    assert resource['cpu_quota_percent']==25 and resource['sampled_swap_peak_bytes']==0
    assert resource['memory_events_after'].get('oom_kill',0)==resource['memory_events_before'].get('oom_kill',0)
    assert resource['limits_bytes']=={'memory.max':512*1024**2,'memory.high':384*1024**2,'memory.swap.max':0}
    assert all(int(x,16)&0xF==0 for x in resource['throttle_samples'])
    assert not read(run+'filesystem-audit.json')['created_files']
    meta=read(run+'metadata.json')
    assert meta['observation_count']==4 and meta['timeout_s']==1500
    assert meta['binary_sha256']=='a238c11d1196ea9bc3197ac5a7756f4d76307595ec9b9656623d49c1f25f1c0b'
    memory=rows(run+'memory.jsonl.gz')
    assert min(x['system_available_bytes'] for x in memory)>=1024**3
    assert all(x['system_swap_used_bytes']==0 and x['cgroup_swap_bytes']==0 for x in memory)
    after=rows('week24/logs/pi-stability/after-n4-v2/health.jsonl')
    assert len(after)==1 and after[0]['ready'] and after[0]['uptime_s']>pre[-1]['uptime_s']
    data='week24/data/pi-observation-scaling-v2/'
    trials=rows(data+'trials.jsonl')
    assert len(trials)==4
    assert sorted(x['observation_count'] for x in trials if x['status']=='completed')==[1,2,4]
    failed=[x for x in trials if x['status']!='completed']
    assert len(failed)==1 and failed[0]['observation_count']==4 and failed[0]['whole_unit_peak_bytes'] is None
    measured=[x for x in rows(data+'samples.jsonl') if not x['warmup']]
    assert len(measured)==9 and all(x['verified'] for x in measured)
    log=(ROOT/'week24/logs/pi-stability/binding-tests-mac.log').read_text()
    assert log.count('    --- PASS: TestFreshSignedIntegerBoundaries/')==11
    assert log.count('    --- PASS: TestAdditionalBatchBindings/')==5
    assert manifest['launcher_pi_e2e_verified'] is False
    print('Pi n4: warmup1+repeat3 verified, guards/no OOM/swap; historic partial retained; extra 16 solver cases passed. CI validates recorded evidence, not a new Pi trial.')

if __name__=='__main__':main()
