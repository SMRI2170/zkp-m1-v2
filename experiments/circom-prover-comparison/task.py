"""Sequential comparison actions: preparation, bounded Pi runs, recovery, and datasets."""
import argparse,csv,hashlib,json,os,shlex,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'experiments/sequential-evaluation'));import pi
from prepare import render

def local_proof(job):
 fixture=ROOT/'.cache/week24/private/euclidean-circom-v2';snarkjs=Path(shutil.which('snarkjs')).resolve();root=snarkjs.parents[1]
 version=json.loads((root/'package.json').read_text())['version'];assert version=='0.7.6'
 m=json.loads((fixture/'manifest.json').read_text());assert all(m[k] for k in ['phase1_contributed','phase2_contributed','zkey_verified'])
 for name,sha in m['files'].items():assert hashlib.sha256((fixture/name).read_bytes()).hexdigest()==sha
 os.umask(0o077)
 with tempfile.TemporaryDirectory(prefix='circom-proof-',dir=ROOT/'.cache/week24/private') as td:
  td=Path(td)
  code="const fs=require('fs');(async()=>{const b=require(process.argv[1]);const w=await b(fs.readFileSync(process.argv[2]));fs.writeFileSync(process.argv[3],await w.calculateWTNSBin({x1:0,y1:0,x2:3,y2:4,d2:25,r:5},true),{mode:0o600});})().catch(()=>process.exit(1));"
  subprocess.run(['node','-e',code,str(fixture/'euclidean_js/witness_calculator.js'),str(fixture/'euclidean_js/euclidean.wasm'),str(td/'w.wtns')],check=True,timeout=30)
  subprocess.run(['node',str(HERE/'snarkjs-prover.cjs'),str(fixture/'local.zkey'),str(td/'w.wtns'),str(td/'proof.json'),str(td/'public.json')],env={**os.environ,'WEEK24_SNARKJS_ROOT':str(root),'WEEK24_SNARKJS_VERSION':version},check=True,timeout=60)
  assert json.loads((td/'public.json').read_text())==['25','5']
  base=[str(snarkjs),'groth16','verify',str(fixture/'vk.json')]
  normal=subprocess.run(['node',*base,str(td/'public.json'),str(td/'proof.json')],capture_output=True,timeout=60)
  (td/'bad.json').write_text('["26","5"]')
  bad=subprocess.run(['node',*base,str(td/'bad.json'),str(td/'proof.json')],capture_output=True,timeout=60)
  assert normal.returncode==0 and bad.returncode==1
 (job/'local-proof.json').write_text(json.dumps({'host':'local Mac','snarkjs_version':version,'actual_proof_verified':True,'changed_public_rejected':True,'proof_body_exported':False,'pi_measurement':False})+'\n')

def prepare(job,tag):
 code="""from pathlib import Path
import json,hashlib,shutil
base=Path('/home/pi/.cache/week24');fixture=base/'private/euclidean-circom-final';root=Path(shutil.which('snarkjs')).resolve().parents[1]
version=json.loads((root/'package.json').read_text())['version'];assert version in ['0.7.5','0.7.6']
s=(root/'src/groth16_prove.js').read_text();c=(root/'src/curves.js').read_text();assert 'logger, options)' in s and 'undefined, options)' in s and 'options.singleThread' in c
m=json.loads((fixture/'manifest.json').read_text());assert all(m[k] for k in ['phase1_contributed','phase2_contributed','zkey_verified']);assert fixture.stat().st_mode&511==448
for name,sha in m['files'].items():
 p=fixture/name;assert p.stat().st_mode&511==384 and hashlib.sha256(p.read_bytes()).hexdigest()==sha
p=base/'rapidsnark-81eddf1/build_week24/src/prover';v=p.with_name('verifier')
h=hashlib.sha256()
for f in sorted(root.rglob('*')):
 if f.is_file():h.update(str(f.relative_to(root)).encode()+b'\\0'+hashlib.sha256(f.read_bytes()).digest())
print(json.dumps({'fixture':str(fixture),'fixture_manifest_sha256':hashlib.sha256((fixture/'manifest.json').read_bytes()).hexdigest(),'snarkjs_root':str(root),'snarkjs_version':version,'snarkjs_source_tree_sha256':h.hexdigest(),'node':shutil.which('node'),'native_prover':str(p),'native_verifier':str(v),'native_prover_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'native_verifier_sha256':hashlib.sha256(v.read_bytes()).hexdigest()}))
"""
 r=pi.ssh(shlex.join(['python3','-c',code]),timeout=60);r.check_returncode();inventory=json.loads(r.stdout)
 artifacts=job/'drivers';artifacts.mkdir();(artifacts/'bench.cjs').write_text(render())
 for name in ['snarkjs-prover.cjs','launch.py']:shutil.copyfile(HERE/name,artifacts/name)
 inventory['deployed_sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in artifacts.iterdir()}
 (artifacts/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
 remote=pi.REMOTE+'/circom-compare-'+tag
 pi.ssh(shlex.join(['mkdir','-m','700',remote])).check_returncode()
 for f in artifacts.iterdir():pi.upload(f,remote+'/'+f.name)
 pi.ssh(shlex.join(['chmod','700',remote+'/snarkjs-prover.cjs'])).check_returncode()
 (job/'comparison-config.json').write_text(json.dumps({'remote_directory':remote,'inventory':inventory,'same_key_and_witness':True,'verifier_for_both':'RapidSnark native'},indent=2)+'\n')

def trial(job,tag,backend):
 config=json.loads((job/'comparison-config.json').read_text());remote=config['remote_directory']
 cmd=['python3',remote+'/launch.py','--backend',backend,'--run-id',tag+'-circom-'+backend,'--directory',remote]
 password=os.environ.get('EVAL_SUDO_PASSWORD',os.environ.get('EVAL_SSH_PASSWORD'))
 r=pi.ssh(('sudo -S -p "" -v && exec ' if password else 'sudo -n -v && exec ')+shlex.join(cmd),timeout=1320,input=password+'\n' if password else None)
 print(r.stdout)
 return r.returncode

def collect(job,tag):
 cmd=[sys.executable,str(ROOT/'experiments/sequential-evaluation/bundle_collect.py'),'--job',str(job),'--tag',tag,'--trial','circom-snarkjs','--trial','circom-rapidsnark']
 result=subprocess.run(cmd,cwd=ROOT).returncode
 runs=job/'pi-runs'
 if runs.exists() and any((d/'metadata.json').exists() for d in runs.iterdir() if d.is_dir()):
  subprocess.run([sys.executable,str(ROOT/'experiments/unified-distance-bench/collect.py'),'--runs',str(runs),'--out',str(job/'data')],check=True)
 else:
  (job/'data').mkdir(exist_ok=True);(job/'data/summary.json').write_text('[]\n');(job/'data/samples.jsonl').write_text('');(job/'data/samples.csv').write_text('run_id,framework,case_id,repetition,flow_ms\n')
 return result

def combine(job,baseline):
 sources=[baseline,job/'data'];out=job/'combined-data';out.mkdir()
 summaries=[];samples=[];provenance=[]
 for source in sources:
  if not (source/'summary.json').exists():continue
  summaries+=json.loads((source/'summary.json').read_text());samples += [json.loads(s) for s in (source/'samples.jsonl').read_text().splitlines() if s.strip()]
  provenance.append({'directory':str(source),'summary_sha256':hashlib.sha256((source/'summary.json').read_bytes()).hexdigest()})
 (out/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n');(out/'samples.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in samples))
 fields=list(dict.fromkeys(k for s in samples for k in s)) or ['run_id','framework','flow_ms']
 with (out/'samples.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(samples)
 (out/'sources.json').write_text(json.dumps(provenance,indent=2)+'\n')
 if any(r['status']=='completed' for r in summaries):subprocess.run([sys.executable,str(ROOT/'experiments/unified-distance-bench/plot.py'),'--data',str(out),'--out',str(job/'plots')],check=True)
 (job/'comparison-status.json').write_text(json.dumps({'completed_configurations':[r['framework'] for r in summaries if r['status']=='completed'],'circom_runs':[{'framework':r['framework'],'status':r['status'],'samples':r['measured_samples']} for r in summaries if r['framework'].startswith('circom-')],'different_flow_scopes_plotted_separately':True},indent=2)+'\n')

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['local-proof','prepare','trial','collect','combine']);p.add_argument('--job',type=Path,required=True);p.add_argument('--tag',required=True);p.add_argument('--backend',choices=['snarkjs','rapidsnark']);p.add_argument('--baseline',type=Path);a=p.parse_args();os.umask(0o077);a.job.mkdir(parents=True,mode=0o700,exist_ok=True);(a.job/'private').mkdir(mode=0o700,exist_ok=True)
 if a.action=='local-proof':local_proof(a.job)
 elif a.action=='prepare':prepare(a.job,a.tag)
 elif a.action=='trial':return trial(a.job,a.tag,a.backend)
 elif a.action=='collect':return collect(a.job,a.tag)
 else:combine(a.job,a.baseline)
 return 0
if __name__=='__main__':raise SystemExit(main())
