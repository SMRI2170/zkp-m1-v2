"""Instrument previous fixed circuits without altering their constraints or archived sources."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;ORIGINAL=ROOT/'experiments/pi4-euclidean-next'
p=argparse.ArgumentParser();p.add_argument('framework',choices=['kimchi','binius64','jolt']);p.add_argument('--target');p.add_argument('--portable-blake3',action='store_true');args=p.parse_args()
source=ROOT/'.cache/week24/evaluation-render';dest=source/args.framework
manifest=json.loads((ROOT/'week24/manifests/euclidean-next.json').read_text())
for name in ['build.py','cases.rs']:
 f=ORIGINAL/name;assert hashlib.sha256(f.read_bytes()).hexdigest()==manifest['file_sha256'][str(f.relative_to(ROOT))],f
for f in (ORIGINAL/args.framework).rglob('*'):
 if not f.is_file() or any(x in f.parts for x in ['target','__pycache__']):continue
 assert hashlib.sha256(f.read_bytes()).hexdigest()==manifest['file_sha256'][str(f.relative_to(ROOT))],f
 out=dest/f.relative_to(ORIGINAL/args.framework);out.parent.mkdir(parents=True,exist_ok=True)
 s=f.read_text().replace('name="week24-euclidean-'+args.framework+'"','name="week24-euclidean-'+args.framework+'-evaluation"').replace('name = "week24-euclidean-'+args.framework+'"','name = "week24-euclidean-'+args.framework+'-evaluation"')
 out.write_text(s)
(source/'cases.rs').write_text((ORIGINAL/'cases.rs').read_text()+'\n'+(HERE/'instrument.rs').read_text())
main=dest/('host/src/main.rs' if args.framework=='jolt' else 'src/main.rs');s=main.read_text()
s=s.replace('let t=Instant::now();','let t=Instant::now();',1)
s=s.replace('fn main()->anyhow::Result<()>{','fn main()->anyhow::Result<()>{eval_us();').replace('fn main() -> anyhow::Result<()> {','fn main() -> anyhow::Result<()> {\n    eval_us();')
s=s.replace('for(i,a)in CASES.iter().enumerate(){','let inputs=eval_inputs();for(i,a)in inputs.iter().enumerate(){eval_mark("witness_start",i);')
s=s.replace('for (i,input) in CASES.iter().enumerate(){','let inputs=eval_inputs();for (i,input) in inputs.iter().enumerate(){eval_mark("witness_start",i);')
s=s.replace('let selected:&[[u64;6]]=if quick {&CASES[1..2]} else {&CASES};','let selected=eval_inputs();')
s=s.replace('for (i,a) in selected.iter().enumerate() {','for (i,a) in selected.iter().enumerate() {\n        eval_mark("prove_start",i);')
s=s.replace('let t=Instant::now();let proof=Proof::create_recursive', 'eval_mark("prove_start",i);let t=Instant::now();let proof=Proof::create_recursive')
s=s.replace('let t=Instant::now();let mut tr=ProverTranscript', 'eval_mark("prove_start",i);let t=Instant::now();let mut tr=ProverTranscript')
s=s.replace('let t=Instant::now();verify::<','eval_mark("verify_start",i);let t=Instant::now();verify::<',1)
s=s.replace('let t=Instant::now();verify(&verifier,witness.inout(),proof.clone())?', 'eval_mark("verify_start",i);let t=Instant::now();verify(&verifier,witness.inout(),proof.clone())?')
s=s.replace('let t=Instant::now();assert!(verify(a[4],a[5],output,io.panic,proof.clone()));','eval_mark("verify_start",i);let t=Instant::now();assert!(verify(a[4],a[5],output,io.panic,proof.clone()));')
# Memory interval ends before tamper tests and serialization work.
s=s.replace('let vms=t.elapsed().as_secs_f64()*1000.;','let vms=t.elapsed().as_secs_f64()*1000.;eval_mark("verify_end",i);')
s=s.replace('"case_id":i','"case_id":eval_case(),"sample_id":i,"warmup":i<eval_warmup(),"repetition":if i<eval_warmup(){None}else{Some(i-eval_warmup())}')
s=s.replace('"samples":7','"samples":inputs.len()').replace('"proof_bytes":bytes.len()', '"public_input_bytes":public.iter().map(|x|x.into_bigint().to_bytes_le().len()).sum::<usize>(),"proof_randomness_new":eval_seen(&bytes),"proof_bytes":bytes.len()').replace('"proof_bytes":proof.len()', '"public_input_bytes":witness.inout().len()*8,"proof_randomness_new":eval_seen(&proof),"proof_bytes":proof.len()').replace('"proof_bytes":size','"public_input_bytes":bincode::serialize(&(a[4],a[5],output,io.panic))?.len(),"proof_randomness_new":eval_seen(&bincode::serialize(&proof)?),"proof_bytes":size')
if args.framework=='kimchi':
 s=s.replace('"public":2','"public":2,"vk_bytes":rmp_serde::to_vec(&verifier)?.len()')
 before=' for a in BAD{'
 test=''' let (_,mut raw)=circuit(CASES[eval_case()]);raw[0][3]+=Fp::from(2u64);
 let attempt=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||Proof::create_recursive::<Base,Scalar,_>(&map,raw,&[],&index,vec![],None,&mut rand::rngs::OsRng)));
 let outcome=match attempt {Ok(Ok(p))=>{assert!(verify::<FULL_ROUNDS,Vesta,Base,Scalar,OpeningProof<Vesta,FULL_ROUNDS>>(&map,&verifier,&p,&[Fp::from(CASES[eval_case()][4]),Fp::from(CASES[eval_case()][5])]).is_err());"verifier_rejected"},Ok(Err(_))=>"prover_error",Err(_)=>"prover_panic"};
 println!("{}",serde_json::json!({"phase":"raw_witness_test","mutation":"private bit assignment +2 after construction","outcome":outcome,"accepted":false}));
'''
 s=s.replace(before,test+before)
elif args.framework=='binius64':
 s='use binius_utils::SerializeBytes;\n'+s
 cm=dest/'Cargo.toml';cm.write_text(cm.read_text()+f'\n[dependencies.binius-utils]\npath={json.dumps(str(ROOT/".cache/week24/binius64/crates/utils"))}\n')
 # Existing lock includes binius-utils; add dependency to root package lock explicitly.
 lock=dest/'Cargo.lock';ls=lock.read_text();start=ls.index('name = "week24-euclidean-binius64-evaluation"');tail=ls[start:];tail=tail.replace(' "binius-verifier",',' "binius-verifier",\n "binius-utils",',1);lock.write_text(ls[:start]+tail)
 s=s.replace('println!("{}",serde_json::json!({"phase":"keys"', 'let mut vk=Vec::new();verifier.serialize(&mut vk)?;println!("{}",serde_json::json!({"vk_bytes":vk.len(),"phase":"keys"')
 before=' for input in BAD{'
 test=''' let input=CASES[eval_case()];let mut raw=circuit.new_witness_filler();for j in 0..4{raw[a[j]]=Word(input[j]);}raw[d]=Word(input[4]);raw[r]=Word(input[5]);circuit.populate_wire_witness(&mut raw)?;raw[a[0]]=Word(input[0]^1);let raw=raw.into_value_vec();
 let attempt=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||{let mut tr=ProverTranscript::new(StdChallenger::default());prover.prove(&raw,&mut rand::rng(),&mut tr).map(|_|tr.finalize())}));
 let outcome=match attempt{Ok(Ok(p))=>{assert!(verify(&verifier,raw.inout(),p).is_err());"verifier_rejected"},Ok(Err(_))=>"prover_error",Err(_)=>"prover_panic"};
 println!("{}",serde_json::json!({"phase":"raw_witness_test","mutation":"private coordinate xor1 after population, without repopulation","outcome":outcome,"accepted":false}));
'''
 s=s.replace(before,test+before)
else:
 s=s.replace('let verify=guest::build_verifier_distance(verifier_prep);','let vk_bytes=jolt_sdk::serialize_verifier_object(&verifier_prep)?.len();\n    let verify=guest::build_verifier_distance(verifier_prep);')
 s=s.replace('"phase":"keys","setup_ms"','"phase":"keys","vk_bytes":vk_bytes,"setup_ms"')
main.write_text(s)
# Reuse compiled dependencies, but use distinct binary names and source/render metadata.
code=(ORIGINAL/'build.py').read_text()
code=code.replace('ROOT=Path(__file__).resolve().parents[2];SOURCE=Path(__file__).resolve().parent',f'ROOT=Path({str(ROOT)!r});SOURCE=Path({str(source)!r})')
code=code.replace('.cache/week24/next-build-source','.cache/week24/evaluation-build-source').replace("'next-'+a.framework", "'evaluation-'+a.framework")
sys.argv=[str(HERE/'build.py'),args.framework]+(['--target',args.target] if args.target else [])+(['--portable-blake3'] if args.portable_blake3 else [])
exec(compile(code,str(HERE/'build.py'),'exec'))
