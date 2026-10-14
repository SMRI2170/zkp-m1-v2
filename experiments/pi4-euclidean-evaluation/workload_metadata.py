"""Metadata for signed-workload counts, no keys or host addresses."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--count',type=int,choices=[1,2,4],required=True);p.add_argument('--run-id',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--timeout-s',type=int,default=600);a=p.parse_args()
b=ROOT/'.cache/week24/week24-observation-workload';source=HERE/'workload';h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m={'run_id':a.run_id,'framework':'gnark_groth16_workload','variant':f'BN254 MiMC EdDSA signed observations n={a.count}','host_class':'Pi4B4GB Debian12 ARM64','cpu_quota_percent':25,'threads':1,'binary_sha256':h(b),'binary_bytes':b.stat().st_size,'source_revision':'gnark v0.16.3; gnark-crypto v0.21.0','source_sha256':{str(p.relative_to(source)):h(p) for p in source.glob('*') if p.is_file() and p.suffix in ['.go','.mod','.sum']},'observation_count':a.count,'repeat_count':3,'warmup_count':1,'arrival_interval_ms':1000,'arrival_unit':'synthetic batch','queue_capacity':3,'controller_goroutine':1,'timeout_s':a.timeout_s,'order':'after Kimchi/Binius64/Jolt; sequential n1 then n2 then n4'}
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(m,indent=2)+'\n')
