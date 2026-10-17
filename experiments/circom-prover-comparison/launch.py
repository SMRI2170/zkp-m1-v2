"""Pi-only CLI launcher using the same bounded runner and fail-closed preflight."""
import argparse,fcntl,hashlib,json,os,re,subprocess,sys
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--backend',choices=['snarkjs','rapidsnark'],required=True);p.add_argument('--run-id',required=True);p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
 if not re.fullmatch('[a-z0-9][a-z0-9-]{0,59}',a.run_id):p.error('invalid run id')
 if os.uname().machine!='aarch64' or os.geteuid()==0:p.error('ordinary Pi ARM64 user required')
 os.umask(0o077);cache=Path.home()/'.cache/week24';directory=a.directory
 inv=json.loads((directory/'inventory.json').read_text());runner=cache/'run_guarded_evaluation.py';pre=cache/'preflight-v1.py'
 for path,expected in [(runner,'bb19ee59cc3ca5cbad3071d511e90e2f4abe98a659a2db665a8b2435181b340f'),(pre,'8a6ed1ef7f19066d858afa5ecda61a751a157978be5d502e6c3ec0f3d7f9096e')]:
  if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise SystemExit('helper hash mismatch')
 for name,expected in inv['deployed_sha256'].items():
  if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=expected:raise SystemExit('driver hash mismatch')
 for name in ['native_prover','native_verifier']:
  if hashlib.sha256(Path(inv[name]).read_bytes()).hexdigest()!=inv[name+'_sha256']:raise SystemExit('native binary hash mismatch')
 fixture=Path(inv['fixture'])
 if hashlib.sha256((fixture/'manifest.json').read_bytes()).hexdigest()!=inv['fixture_manifest_sha256']:raise SystemExit('fixture manifest changed')
 out=cache/'runs'/a.run_id;work=Path('/dev/shm')/('week24-eval-'+a.run_id)
 if out.exists() or work.exists():raise SystemExit('preserve prior run and use a new ID')
 with (cache/'unified-launch.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  units=subprocess.check_output(['systemctl','list-units','--state=running','--no-legend','--plain','week24-*.service'],text=True)
  if any('watchdog' not in s for s in units.splitlines() if s.strip()):raise SystemExit('another experiment is active')
  subprocess.run([sys.executable,str(pre),'--out',str(cache/'preflight'/a.run_id),'--samples','3','--interval-s','30'],check=True)
  command=['env','WEEK24_SNARKJS_ROOT='+inv['snarkjs_root'],'WEEK24_SNARKJS_VERSION='+inv['snarkjs_version'],inv['node'],str(directory/'bench.cjs'),str(fixture),str(directory/'snarkjs-prover.cjs') if a.backend=='snarkjs' else inv['native_prover'],inv['native_verifier'],a.backend]
  cmd=['sudo','-n','systemd-run','--unit=week24-eval-'+a.run_id,'--wait','--pipe']
  for prop in ['User='+str(os.getuid()),'Slice=week24.slice','MemoryAccounting=yes','MemoryHigh=192M','MemoryMax=256M','MemorySwapMax=0','OOMScoreAdjust=500','OOMPolicy=stop','CPUWeight=10','CPUQuota=25%','RuntimeMaxSec=1230']:cmd+=['-p',prop]
  cmd += [sys.executable,str(runner),'--out',str(out),'--work-dir',str(work),'--timeout-s','1200','--memory-high-mib','192','--memory-max-mib','256','--',*command]
  code=subprocess.run(cmd).returncode
  if out.exists():
   m={'protocol':'distance-u16-balanced-v1','run_id':a.run_id,'framework':'circom-'+a.backend,'host_class':'Pi4B4GB ARM64','cpu_quota_percent':25,'threads':1,'flow_scope':'WASM witness + prover process + common native verifier; CLI startup included; setup excluded','phase_notes':'WTNS disk write outside witness timer. snarkjs '+inv['snarkjs_version']+' singleThread API; common RapidSnark verifier for both variants. JSON raw size; canonical size also in raw samples.','proof_encoding':'JSON','binary_sha256':inv['deployed_sha256']['snarkjs-prover.cjs'] if a.backend=='snarkjs' else inv['native_prover_sha256'],'build_metadata':inv,'launcher_exit_code':code}
   (out/'metadata.json').write_text(json.dumps(m,indent=2)+'\n')
  return code
if __name__=='__main__':raise SystemExit(main())
