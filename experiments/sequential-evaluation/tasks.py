"""Known implementation/build/collection steps for the sequential evaluation job."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
def call(argv):subprocess.run([str(x) for x in argv],cwd=ROOT,check=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['build','cli','collect','plot','unsupported']);p.add_argument('--framework');p.add_argument('--tag',required=True);p.add_argument('--job',type=Path,required=True);a=p.parse_args()
    if a.action=='build':
        f=a.framework
        if f=='gnark':
            call([sys.executable,'experiments/unified-distance-bench/build.py',f,'--build-id',a.tag+'-host'])
            binary=ROOT/'.cache/week24/unified-build'/(a.tag+'-host')/'gnark/unified-gnark'
            fixtures=ROOT/'.cache/week24/private'/('sequential-'+a.tag);fixtures.mkdir(mode=0o700)
            for backend in ['groth16','plonk']:call([binary,'setup',backend,fixtures/backend])
        call([sys.executable,'experiments/unified-distance-bench/build.py',f,'--build-id',a.tag,'--target','aarch64-unknown-linux-musl'])
    elif a.action=='cli':
        call([sys.executable,'experiments/balanced-cli/render.py',a.framework,'--out',ROOT/'.cache/week24/sequential-cli'/a.tag/a.framework])
    elif a.action=='collect':
        # Fetch is best effort; preserve any partial logs. Never relaunch a remote trial.
        r=subprocess.run([sys.executable,str(Path(__file__).with_name('pi.py')),'collect','--job',str(a.job),'--tag',a.tag],cwd=ROOT)
        runs=a.job/'pi-runs'
        if runs.exists() and any(p.is_dir() and (p/'metadata.json').exists() for p in runs.iterdir()):
            call([sys.executable,'experiments/unified-distance-bench/collect.py','--runs',runs,'--out',a.job/'data'])
        else:
            (a.job/'data').mkdir(exist_ok=True)
            (a.job/'data/summary.json').write_text('[]\n')
            (a.job/'data/samples.csv').write_text('run_id,case_id,repetition,flow_ms,proof_bytes\n')
            (a.job/'data/samples.jsonl').write_text('')
        rows=json.loads((a.job/'data/summary.json').read_text())
        (a.job/'measurement-status.json').write_text(json.dumps({'pi_runs_collected':len(rows),'completed_runs':sum(r['status']=='completed' for r in rows),'fetch_exit_code':r.returncode,'proof_measurements_present':bool(rows),'raw_run_directories':[{'run_id':p.name,'metadata_present':(p/'metadata.json').exists(),'resource_present':(p/'resource.json').exists()} for p in runs.iterdir() if p.is_dir()] if runs.exists() else [],'missing_values':'null / blank; no imputation'},indent=2)+'\n')
        if r.returncode:raise SystemExit(r.returncode)
    elif a.action=='plot':
        rows=json.loads((a.job/'data/summary.json').read_text())
        if not any(r.get('status')=='completed' for r in rows):
            (a.job/'plot-status.json').write_text(json.dumps({'status':'blocked','reason':'No completed Pi cohort; no performance figure generated'})+'\n');raise SystemExit(3)
        call([sys.executable,'experiments/unified-distance-bench/plot.py','--data',a.job/'data','--out',a.job/'plots'])
    else:
        notes={'nova':'Needs separate fresh-state ordered IVC series; not independent final ZK proofs','hypernova':'Needs separate fresh-state ordered IVC series; not independent final ZK proofs','kimchi':'Balanced multi-input adapter and proof validation pending','binius64':'Balanced adapter and bounded runtime protocol pending','jolt':'Balanced full-case adapter and guest proof validation pending','plonky2':'Pi stability and resource prerequisites pending (#55)','risc0':'Pi sysroot and safe proof resource prerequisites pending (#55)','sp1':'Pi sysroot and safe proof resource prerequisites pending (#55)'}
        record={'framework':a.framework,'status':'unsupported','reason':notes[a.framework],'proof_executed':False}
        (a.job/(a.framework+'-capability.json')).write_text(json.dumps(record,indent=2)+'\n');raise SystemExit(4)
if __name__=='__main__':main()
