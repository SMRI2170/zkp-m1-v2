"""Compile capability probes separately from normal test targets; preserve all logs."""
from pathlib import Path
import json,os,subprocess
ROOT=Path(__file__).resolve().parents[3]
TREE=ROOT/'.cache/week23/sources/sonobe-hypernova-fixed-v1'
rows=[]
for name,crate,example,expected in [('blindfold','fs','week23_blindfold_probe',101),('hypernova_ivc','ivc','week23_hypernova_ivc_probe',0)]:
 source=ROOT/'week23/poc/sonobe-current/probes'/(name+'.rs')
 target=TREE/'crates'/crate/'examples'/(example+'.rs');target.parent.mkdir(parents=True,exist_ok=True)
 target.write_text(source.read_text())
 try:
  result=subprocess.run(['cargo','+stable','check','-j','2','--manifest-path',str(TREE/'Cargo.toml'),'-p','sonobe-'+crate,'--example',example],cwd=ROOT,env={**os.environ,'CARGO_TARGET_DIR':str(ROOT/'.cache/week23/target-hypernova-fixed')},capture_output=True,text=True)
  (ROOT/'.cache/week23/logs'/('api-probe-'+name+'.log')).write_text(result.stdout+result.stderr)
  assert result.returncode==expected,(name,result.stderr)
  if name=='blindfold':assert 'no `NovaBlindFold` in `hypernova`' in result.stderr
  rows.append({'probe':name,'exit_code':result.returncode,'conclusion':'No NovaBlindFold symbol; not evidence that every ZK API is impossible' if name=='blindfold' else 'HyperNova/CycleFold IVC type bridge compiles; execution and ZK/blinded handoff are separate requirements'})
 finally:target.rename(target.with_suffix('.rs.checked'))
(ROOT/'week23/logs/hypernova-api-probes.json').write_text(json.dumps({'probes':rows},indent=2)+'\n')
print(json.dumps(rows))
