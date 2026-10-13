"""Cross-build pinned additional circuit backends; this is not a Pi proof run."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--framework',choices=['all','arkworks','halo2-kzg','spartan','bulletproofs','plonky2','plonky3'],default='all');args=parser.parse_args()
choices=['arkworks','halo2-kzg','spartan','bulletproofs','plonky2','plonky3'] if args.framework=='all' else [args.framework]
result={}
for name in choices:
    env={**os.environ,'CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER':'rust-lld'}
    targets={'arkworks':'target-additional','halo2-kzg':'target-additional','spartan':'target-spartan','bulletproofs':'target-spartan','plonky2':'target-plonky','plonky3':'target-plonky3'}
    env['CARGO_TARGET_DIR']=str(root/'.cache/week24'/targets[name])
    cmd=['cargo']
    if name=='plonky2':cmd+=['+nightly-2026-10-01']
    if name=='bulletproofs':
        sysroot=Path(subprocess.check_output(['rustc','--print','sysroot'],text=True).strip())
        host=next(x.split(': ',1)[1] for x in subprocess.check_output(['rustc','-vV'],text=True).splitlines() if x.startswith('host:'))
        ar=sysroot/'lib/rustlib'/host/'bin/llvm-ar'
        if not ar.exists():raise RuntimeError('Install rustup component llvm-tools; do not disable clear_on_drop')
        env.update({'CC_aarch64_unknown_linux_musl':'clang','CFLAGS_aarch64_unknown_linux_musl':'--target=aarch64-linux-musl','AR_aarch64_unknown_linux_musl':str(ar)})
    cmd+=['build','--manifest-path',str(source/name/'Cargo.toml'),'--locked','--release','--target','aarch64-unknown-linux-musl','-j','1']
    subprocess.run(cmd,env=env,check=True)
    binary=Path(env['CARGO_TARGET_DIR'])/'aarch64-unknown-linux-musl/release'/('week24-euclidean-'+name)
    result[name]={'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'pi_proof_executed_by_build':False,'source_sha256':{n:hashlib.sha256((source/name/n).read_bytes()).hexdigest() for n in ['Cargo.toml','Cargo.lock','src/main.rs']}}
output=root/'.cache/week24/logs/additional-build.json'
output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
