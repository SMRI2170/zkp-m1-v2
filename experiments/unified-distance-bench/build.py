"""Generate new drivers from hash-pinned archived circuits; never edit old evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
RUST=('arkworks','halo2-ipa','halo2-kzg','spartan','bulletproofs','plonky3')
FRAMEWORKS=('gnark',)+RUST

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replace_once(s,old,new):
    if s.count(old)!=1:raise ValueError('source shape changed: '+old[:70])
    return s.replace(old,new)

def source_info(name):
    base=ROOT/'experiments/pi4-euclidean'
    manifest=json.loads((ROOT/'week24/manifests/euclidean-frameworks.json').read_text())['source_sha256']
    key='halo2' if name=='halo2-ipa' else name
    if name in RUST and name!='halo2-ipa':
        base=ROOT/'experiments/pi4-euclidean-additional'
        manifest=json.loads((ROOT/'week24/manifests/euclidean-additional.json').read_text())['source_sha256']
    names=['main.go','main_test.go','go.mod','go.sum'] if name=='gnark' else ['src/main.rs','Cargo.toml','Cargo.lock']
    paths={n:base/key/n for n in names}
    for n,p in paths.items():
        if sha(p)!=manifest[key+'/'+n]:raise ValueError('archived source hash mismatch: '+str(p))
    return paths

def render(name,dest):
    paths=source_info(name)
    dest.mkdir(parents=True)  # preserve incomplete builds; no overwrite
    for n,p in paths.items():
        out=dest/n;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out)
    if name=='gnark':
        p=dest/'main.go';s=p.read_text()
        s=replace_once(s,'for i := -1; i < 20; i++ {','for i := -7; i < 21; i++ {')
        s=s.replace('cases[(i+1)%len(cases)]','cases[(i+7)%len(cases)]')
        s=replace_once(s,'"case_id": (i + 1) % len(cases)',
            '"case_id": (i + 7) % len(cases), "sample_id": i+7, "repetition": func() any { if i<0 {return nil}; return i/7 }()')
        s=replace_once(s,'"samples": 20, "warmups": 1','"samples": 21, "warmups": 7, "protocol": "distance-u16-balanced-v1"')
        p.write_text(s)
        subprocess.run(['gofmt','-w',str(p)],check=True)
    else:
        p=dest/'src/main.rs';s=p.read_text()
        s=replace_once(s,'for (i, a) in CASES.iter().enumerate() {',
            'for sample_id in 0..28 {\n let i=sample_id%7; let a=&CASES[i];')
        s=replace_once(s,'"phase":"sample","case_id":i',
            '"phase":"sample","case_id":i,"sample_id":sample_id,"warmup":sample_id<7,"repetition":if sample_id<7{None}else{Some((sample_id-7)/7)}')
        s=replace_once(s,'"samples":7','"samples":21,"warmups":7,"protocol":"distance-u16-balanced-v1"')
        p.write_text(s)
    return {str(p.relative_to(ROOT)):sha(p) for p in paths.values()}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('framework',choices=FRAMEWORKS)
    p.add_argument('--target',choices=['host','aarch64-unknown-linux-musl'],default='host')
    p.add_argument('--build-id',required=True);a=p.parse_args()
    if not a.build_id.replace('-','').isalnum() or not a.build_id.isascii():p.error('ASCII build-id required')
    dest=ROOT/'.cache/week24/unified-build'/a.build_id/a.framework
    sources=render(a.framework,dest)
    env=dict(os.environ);build_meta={'framework':a.framework,'target':a.target,'source_sha256':sources,'protocol':'distance-u16-balanced-v1','pi_executed':False}
    if a.framework=='gnark':
        digest=hashlib.sha256(b''.join((dest/n).read_bytes() for n in ['main.go','go.mod','go.sum'])).hexdigest()
        env['CGO_ENABLED']='0'
        if a.target!='host':env.update(GOOS='linux',GOARCH='arm64')
        binary=dest/'unified-gnark'
        subprocess.run(['go','test','./...'],cwd=dest,check=True)
        subprocess.run(['go','build','-mod=readonly','-trimpath','-ldflags','-X main.sourceDigest='+digest,'-o',str(binary),'.'],cwd=dest,env=env,check=True)
        build_meta['fixture_source_digest']=digest
    else:
        target_dirs={'arkworks':'target-additional','halo2-ipa':'target-euclidean','halo2-kzg':'target-additional','spartan':'target-spartan','bulletproofs':'target-spartan','plonky3':'target-plonky3'}
        env['CARGO_TARGET_DIR']=str(ROOT/'.cache/week24'/target_dirs[a.framework])
        if a.target!='host':env['CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER']='rust-lld'
        if a.framework=='bulletproofs' and a.target!='host':
            sysroot=Path(subprocess.check_output(['rustc','--print','sysroot'],text=True).strip())
            host=next(x.split(': ',1)[1] for x in subprocess.check_output(['rustc','-vV'],text=True).splitlines() if x.startswith('host:'))
            ar=sysroot/'lib/rustlib'/host/'bin/llvm-ar'
            if not ar.exists():raise RuntimeError('llvm-tools required; clear_on_drop must remain enabled')
            env.update(CC_aarch64_unknown_linux_musl='clang',CFLAGS_aarch64_unknown_linux_musl='--target=aarch64-linux-musl',AR_aarch64_unknown_linux_musl=str(ar))
        cmd=['cargo','build','--locked','--release','-j','1','--manifest-path',str(dest/'Cargo.toml')]
        if a.target!='host':cmd+=['--target',a.target]
        subprocess.run(cmd,env=env,check=True)
        package='week24-euclidean-'+('halo2' if a.framework=='halo2-ipa' else a.framework)
        built=Path(env['CARGO_TARGET_DIR'])/('' if a.target=='host' else a.target)/'release'/package
        binary=dest/('unified-'+a.framework);shutil.copyfile(built,binary);binary.chmod(0o755)
    build_meta.update(binary_sha256=sha(binary),binary=str(binary.relative_to(ROOT)),
        rendered_sha256={str(p.relative_to(dest)):sha(p) for p in dest.rglob('*') if p.is_file() and p.name!='build.json'},
        host_build_platform=platform.system(),build_script_sha256=sha(Path(__file__)))
    build_meta['toolchain']=subprocess.check_output(['go','version'] if a.framework=='gnark' else ['rustc','-vV'],text=True).strip()
    (dest/'build.json').write_text(json.dumps(build_meta,indent=2)+'\n')
    print(json.dumps(build_meta))

if __name__=='__main__':main()
