"""Real host proofs for driver correctness; not Pi performance measurements."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from build import ROOT, FRAMEWORKS
from protocol import validate_samples, VERSION

def main():
    p=argparse.ArgumentParser();p.add_argument('--build-id',required=True);p.add_argument('--run-id',required=True);a=p.parse_args()
    if any(not x.replace('-','').isalnum() or not x.isascii() for x in [a.build_id,a.run_id]):p.error('ASCII IDs required')
    os.umask(0o077)
    base=ROOT/'.cache/week24/private'/('unified-'+a.run_id);base.mkdir(mode=0o700)
    results=[]
    for framework in FRAMEWORKS:
        builddir=ROOT/'.cache/week24/unified-build'/a.build_id/framework
        build=json.loads((builddir/'build.json').read_text())
        if build['target']!='host':raise ValueError('host build required')
        binary=ROOT/build['binary']
        if hashlib.sha256(binary.read_bytes()).hexdigest()!=build['binary_sha256']:raise ValueError('binary hash mismatch')
        for backend in (['groth16','plonk'] if framework=='gnark' else [None]):
            name=framework+('-'+backend if backend else '')
            cmd=[str(binary)]
            if backend:
                fixture=base/('fixture-'+backend)
                with (base/(name+'-setup.jsonl')).open('x') as out,(base/(name+'-setup.stderr')).open('x') as err:
                    subprocess.run(cmd+['setup',backend,str(fixture)],stdout=out,stderr=err,env={**os.environ,'GOMAXPROCS':'1'},timeout=120,check=True)
                cmd+=['bench',backend,str(fixture)]
            log=base/(name+'.jsonl')
            with log.open('x') as out,(base/(name+'.stderr')).open('x') as err:
                subprocess.run(cmd,stdout=out,stderr=err,env={**os.environ,'GOMAXPROCS':'1','RAYON_NUM_THREADS':'1','OMP_NUM_THREADS':'1'},timeout=180,check=True)
            rows=[json.loads(s) for s in log.read_text().splitlines() if s.startswith('{')]
            samples=[r for r in rows if r.get('phase')=='sample']
            validate_samples(samples,require_complete=True)
            summary=rows[-1]
            assert summary['all_verified'] is True and summary['samples']==21 and summary['warmups']==7 and summary['protocol']==VERSION
            assert all(r.get('tampered_proof_rejected') is True and r.get('changed_public_rejected') is True for r in samples) if framework!='gnark' else any(r.get('phase')=='negative' and r.get('tampered_proof_rejected') is True and r.get('changed_public_rejected') is True for r in rows)
            results.append(dict(framework=name,host=build['host_build_platform'],protocol=VERSION,normal_proofs_verified=len(samples),warmup_proofs=7,measured_proofs=21,case_counts={str(i):sum(r['case_id']==i and not r['warmup'] for r in samples) for i in range(7)},negative_tests_retained=True,pi_executed=False,performance_comparison=False,build_metadata=build,raw_log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
            print(name+': 28 real proofs verified; measured 7 x 3; host only',flush=True)
    output=ROOT/'.cache/week24'/('unified-'+a.run_id+'-confirmation.json')
    with output.open('x') as out:json.dump(results,out,indent=2);out.write('\n')
if __name__=='__main__':main()
