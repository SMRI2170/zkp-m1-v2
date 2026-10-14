use binius_utils::SerializeBytes;
use binius_core::Word;
use binius_frontend::{CircuitBuilder,Wire};
use binius_hash::sha256::Sha256HashSuite;
use binius_prover::{OptimalPackedB128,zk_config::ZKProver};
use binius_verifier::{config::StdChallenger,transcript::{ProverTranscript,VerifierTranscript},zk_config::ZKVerifier};
use std::time::Instant;
include!("../../cases.rs");
fn range(b:&CircuitBuilder,x:Wire,n:u32){b.assert_zero("range upper bits",b.shr(x,n));}
fn mul(b:&CircuitBuilder,x:Wire,y:Wire)->Wire{let (hi,lo)=b.imul(x,y);b.assert_zero("mul overflow",hi);lo}
fn add(b:&CircuitBuilder,x:Wire,y:Wire)->Wire{let (v,c)=b.iadd(x,y);b.assert_zero("add overflow",b.shr(c,63));v}
fn sub(b:&CircuitBuilder,x:Wire,y:Wire)->Wire{let (v,c)=b.isub_bin_bout(x,y,b.add_constant_64(0));b.assert_zero("negative subtraction",b.shr(c,63));v}
fn sqdiff(b:&CircuitBuilder,x:Wire,y:Wire)->Wire{let sum=add(b,mul(b,x,x),mul(b,y,y));sub(b,sum,b.shl(mul(b,x,y),1))}
fn verify(v:&ZKVerifier<Sha256HashSuite>,public:&[Word],bytes:Vec<u8>)->anyhow::Result<()>{let mut tr=VerifierTranscript::new(StdChallenger::default(),bytes);v.verify(public,&mut tr)?;tr.finalize()?;Ok(())}
fn main()->anyhow::Result<()>{eval_us();
 println!("{}",serde_json::json!({"phase":"start","framework":"Binius64 ZK SHA256","os":std::env::consts::OS,"arch":std::env::consts::ARCH}));
 let t=Instant::now();let b=CircuitBuilder::new();let a:[Wire;4]=std::array::from_fn(|_|b.add_witness());let d=b.add_inout();let r=b.add_inout();for x in a{range(&b,x,16);}range(&b,d,33);range(&b,r,17);
 let sum=add(&b,sqdiff(&b,a[0],a[2]),sqdiff(&b,a[1],a[3]));b.assert_eq("distance",d,sum);
 let low=sub(&b,d,mul(&b,r,r));range(&b,low,18);let rp=add(&b,r,b.add_constant_64(1));let high=sub(&b,sub(&b,mul(&b,rp,rp),d),b.add_constant_64(1));range(&b,high,18);
 let circuit=b.build();let verifier=ZKVerifier::<Sha256HashSuite>::setup(circuit.constraint_system().clone(),1)?;let prover=ZKProver::<OptimalPackedB128,Sha256HashSuite>::setup(&verifier)?;
 let mut vk=Vec::new();verifier.serialize(&mut vk)?;println!("{}",serde_json::json!({"vk_bytes":vk.len(),"phase":"keys","setup_ms":t.elapsed().as_secs_f64()*1000.,"zk":true,"log_inv_rate":1}));
 let inputs=eval_inputs();for (i,input) in inputs.iter().enumerate(){eval_mark("witness_start",i);let t=Instant::now();let mut filler=circuit.new_witness_filler();for j in 0..4{filler[a[j]]=Word(input[j]);}filler[d]=Word(input[4]);filler[r]=Word(input[5]);circuit.populate_wire_witness(&mut filler)?;let witness=filler.into_value_vec();let wms=t.elapsed().as_secs_f64()*1000.;
 eval_mark("prove_start",i);let t=Instant::now();let mut tr=ProverTranscript::new(StdChallenger::default());prover.prove(&witness,&mut rand::rng(),&mut tr)?;let proof=tr.finalize();let pms=t.elapsed().as_secs_f64()*1000.;eval_mark("verify_start",i);let t=Instant::now();verify(&verifier,witness.inout(),proof.clone())?;let vms=t.elapsed().as_secs_f64()*1000.;eval_mark("verify_end",i);
 // Frontend inout order is d2 then r; only public words reach verifier.
 assert_eq!(witness.inout()[0],Word(input[4]));assert_eq!(witness.inout()[1],Word(input[5]));
 for j in 0..2{let mut fake=witness.inout().to_vec();fake[j].0^=1;assert!(verify(&verifier,&fake,proof.clone()).is_err());}let mut fake=proof.clone();fake[0]^=1;assert!(verify(&verifier,witness.inout(),fake).is_err());
 println!("{}",serde_json::json!({"phase":"sample","case_id":eval_case(),"sample_id":i,"warmup":i<eval_warmup(),"repetition":if i<eval_warmup(){None}else{Some(i-eval_warmup())},"verified":true,"witness_ms":wms,"prove_ms":pms,"verify_ms":vms,"public_input_bytes":witness.inout().len()*8,"proof_randomness_new":eval_seen(&proof),"proof_bytes":proof.len(),"changed_public_rejected":true,"changed_root_rejected":true,"tampered_proof_rejected":true}));}
 let input=CASES[eval_case()];let mut raw=circuit.new_witness_filler();for j in 0..4{raw[a[j]]=Word(input[j]);}raw[d]=Word(input[4]);raw[r]=Word(input[5]);circuit.populate_wire_witness(&mut raw)?;raw[a[0]]=Word(input[0]^1);let raw=raw.into_value_vec();
 let attempt=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||{let mut tr=ProverTranscript::new(StdChallenger::default());prover.prove(&raw,&mut rand::rng(),&mut tr).map(|_|tr.finalize())}));
 let outcome=match attempt{Ok(Ok(p))=>{assert!(verify(&verifier,raw.inout(),p).is_err());"verifier_rejected"},Ok(Err(_))=>"prover_error",Err(_)=>"prover_panic"};
 println!("{}",serde_json::json!({"phase":"raw_witness_test","mutation":"private coordinate xor1 after population, without repopulation","outcome":outcome,"accepted":false}));
 for input in BAD{let mut filler=circuit.new_witness_filler();for j in 0..4{filler[a[j]]=Word(input[j]);}filler[d]=Word(input[4]);filler[r]=Word(input[5]);assert!(circuit.populate_wire_witness(&mut filler).is_err());}
 println!("{}",serde_json::json!({"phase":"summary","samples":inputs.len(),"all_verified":true,"invalid_cases_rejected":6,"proofs_saved":false}));Ok(())
}
