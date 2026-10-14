"""Build verified pinned local sources, avoiding unrelated upstream test submodules.
Effective manifests and dependency locks are retained; no proof execution/cache cleanup.
"""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];SOURCE=Path(__file__).resolve().parent
PINS={'kimchi':('https://github.com/o1-labs/proof-systems','9227444890bc56d63d95ce14b9cbe34e2cf58996'),'binius64':('https://github.com/binius-zk/binius64','4428e759dd27956bd5b9ae5025d67eb8ccc1accf'),'jolt':('https://github.com/a16z/jolt','8b6099f70bb21c8d38abd32dc295d34786c1699a')}
p=argparse.ArgumentParser();p.add_argument('framework',choices=list(PINS));p.add_argument('--target');p.add_argument('--portable-blake3',action='store_true');a=p.parse_args()
url,rev=PINS[a.framework];checkout=ROOT/'.cache/week24'/a.framework
if not checkout.exists():
 subprocess.run(['git','clone','--no-checkout',url,str(checkout)],check=True)
 subprocess.run(['git','-C',str(checkout),'checkout','--detach',rev],check=True)
head=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
assert head==rev,'Pinned source mismatch; preserve and inspect checkout'
assert not subprocess.check_output(['git','-C',str(checkout),'diff','HEAD','--name-only'],text=True).strip(),'Modified upstream tracked source'
base=ROOT/('.cache/week24/next-build-source-pi' if a.target else '.cache/week24/next-build-source');dest=base/a.framework
# Refresh mtimes: copy2 can hide changed content behind older Cargo fingerprints.
shutil.copytree(SOURCE/a.framework,dest,dirs_exist_ok=True,copy_function=shutil.copy,ignore=shutil.ignore_patterns('target','__pycache__'))
shutil.copy2(SOURCE/'cases.rs',base/'cases.rs')
packages=['kimchi','mina-curves','mina-poseidon','groupmap','poly-commitment'] if a.framework=='kimchi' else ['binius-core','binius-frontend','binius-hash','binius-prover','binius-verifier'] if a.framework=='binius64' else ['jolt-sdk','jolt-field','jolt-poly']
for manifest in dest.rglob('Cargo.toml'):
 text=manifest.read_text()
 for pkg in packages:
  sub={'mina-curves':'curves','mina-poseidon':'poseidon'}.get(pkg,pkg) if a.framework=='kimchi' else 'crates/'+pkg.removeprefix('binius-') if a.framework=='binius64' else 'jolt-sdk' if pkg=='jolt-sdk' else 'crates/'+pkg
  prefix='git="'+url+'",rev="'+rev+'"'
  if a.framework!='jolt':
   line=next((s for s in text.splitlines() if s.startswith(pkg+'={')),None)
   if line:text=text.replace(line,line.replace(prefix,'path='+json.dumps(str(checkout/sub))))
  else:
   for line in text.splitlines():
    if line.startswith(pkg+'={') or (pkg=='jolt-sdk' and line.startswith('jolt={')):
     text=text.replace(line,line.replace(prefix,'path='+json.dumps(str(checkout/sub))))
 manifest.write_text(text)
manifest=dest/('host/Cargo.toml' if a.framework=='jolt' else 'Cargo.toml')
env={**os.environ,'CARGO_TARGET_DIR':str(ROOT/'.cache/week24'/('target-'+a.framework+'-next')),'CARGO_NET_GIT_FETCH_WITH_CLI':'true','CARGO_HTTP_TIMEOUT':'60','CARGO_BUILD_JOBS':'1'}
command=['cargo']+(['+1.98.1'] if a.framework=='binius64' else [])+['build','--manifest-path',str(manifest),'--release','-j','1']
if (dest/'Cargo.lock').exists():command+=['--locked']
if a.target:command+=['--target',a.target];env['CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER']='rust-lld'
if a.portable_blake3:
 assert a.framework=='binius64'
 command+=['--features','portable-blake3']
completed=subprocess.run(command,env=env)
for lock in dest.rglob('Cargo.lock'):shutil.copy2(lock,SOURCE/a.framework/lock.relative_to(dest))
result={'framework':a.framework,'revision':head,'build_exit_code':completed.returncode,'proof_executed':False,'target':a.target or 'host native','portable_blake3':a.portable_blake3,'source_sha256':{str(f.relative_to(SOURCE)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((SOURCE/a.framework).rglob('*')) if f.is_file() and 'target' not in f.parts},'effective_manifest':manifest.read_text().replace(str(checkout),'<verified-pinned-checkout>')}
(ROOT/'.cache/week24/logs'/('next-'+a.framework+('-pi' if a.target else '-host')+'-build.json')).write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(completed.returncode)
