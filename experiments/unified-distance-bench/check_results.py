"""CI checks saved evidence; does not execute new proofs or measure Pi performance."""
import hashlib
import json
from pathlib import Path
import build
from protocol import VERSION, schedule, validate_samples
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=json.loads((ROOT/'week24/manifests/unified-distance.json').read_text())
    for name,expected in manifest['file_sha256'].items():assert sha(ROOT/name)==expected,name
    plan=json.loads((ROOT/'week24/data/unified-distance-plan/protocol.json').read_text())
    assert plan['schedule']==schedule() and plan['measured_samples']==21 and plan['warmups']==7
    assert len(plan['coverage'])==18 and sum(r['balanced_driver_ready'] for r in plan['coverage'])==8
    assert all(r['balanced_pi_run']=='not_executed' for r in plan['coverage'])
    evidence=ROOT/'week24/logs/unified-native-v2'
    confirmations=json.loads((evidence/'confirmation.json').read_text())
    expected={'gnark-groth16','gnark-plonk',*build.RUST}
    assert {r['framework'] for r in confirmations}==expected
    for r in confirmations:
        assert r['normal_proofs_verified']==28 and r['measured_proofs']==21 and r['warmup_proofs']==7
        assert r['case_counts']=={str(i):3 for i in range(7)}
        assert r['pi_executed'] is False and r['performance_comparison'] is False
        log=evidence/(r['framework']+'.jsonl');assert sha(log)==r['raw_log_sha256']
        rows=[json.loads(s) for s in log.read_text().splitlines() if s.startswith('{')]
        validate_samples([x for x in rows if x.get('phase')=='sample'],require_complete=True)
        assert rows[-1]['all_verified'] and rows[-1]['samples']==21 and rows[-1]['protocol']==VERSION
        for name,expected_hash in r['build_metadata']['source_sha256'].items():assert sha(ROOT/name)==expected_hash
        assert r['build_metadata']['build_script_sha256']==sha(Path(build.__file__))
    cross=json.loads((evidence/'arm64-builds.json').read_text())
    assert {r['framework'] for r in cross}==set(build.FRAMEWORKS)
    for r in cross:
        assert r['target']=='aarch64-unknown-linux-musl' and not r['pi_executed']
        assert r['protocol']==VERSION and r['build_script_sha256']==sha(Path(build.__file__))
    print('Balanced drivers verified: 8 configurations, 224 recorded host proofs (7 warmup + 21 measured each); ARM64 build only, no new Pi run.')
if __name__=='__main__':main()
