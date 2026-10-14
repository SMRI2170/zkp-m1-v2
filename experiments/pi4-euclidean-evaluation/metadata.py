"""Produce public-safe per-run metadata from local artifacts, with no host credentials."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('framework',choices=['kimchi','binius64','jolt']);p.add_argument('--run-id',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--repeat',type=int,default=3);p.add_argument('--warmup',type=int,default=1);p.add_argument('--case',type=int,default=1);a=p.parse_args()
f=a.framework;binary=ROOT/f'.cache/week24/target-{f}-next/aarch64-unknown-linux-musl/release/week24-euclidean-{f}-evaluation'
build=json.loads((ROOT/f'.cache/week24/logs/evaluation-{f}-pi-build.json').read_text());assert build['build_exit_code']==0
m={'run_id':a.run_id,'framework':f,'variant':{'kimchi':'Vesta IPA domain512','binius64':'ZK SHA256 log_inv_rate1 portable BLAKE3','jolt':'PrivateInput + zk prebuilt guest'}[f],'host_class':'Pi4B4GB Debian12 ARM64','cpu_quota_percent':25,'threads':1,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'binary_bytes':binary.stat().st_size,'source_revision':build['revision'],'repeat_count':a.repeat,'warmup_count':a.warmup,'synthetic_case_id':a.case,'order':'kimchi then binius64 then jolt; no simultaneous Pi benchmark','build_metadata':build}
if f=='jolt':
 elf=ROOT/'.cache/week24/jolt-next-guests/week24-euclidean-jolt-guest-distance/riscv64imac-unknown-none-elf/release/week24-euclidean-jolt-guest';m['guest_elf_bytes']=elf.stat().st_size;m['guest_elf_sha256']=hashlib.sha256(elf.read_bytes()).hexdigest()
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(m,indent=2)+'\n')
