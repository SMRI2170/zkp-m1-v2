//! Current upstream IVC, explicit raw-state serialization and strict negative tests.
//! This is NOT a privacy-preserving transfer adapter.
use ark_bn254::{Fr, G1Projective};
use ark_crypto_primitives::sponge::poseidon::PoseidonSponge;
use ark_ec::PrimeGroup;
use ark_ff::PrimeField;
use ark_grumpkin::Projective as G2;
use ark_r1cs_std::{GR1CSVar, alloc::AllocVar, boolean::Boolean, eq::EqGadget, fields::fp::FpVar};
use ark_relations::gr1cs::SynthesisError;
use ark_serialize::{CanonicalDeserialize, CanonicalSerialize};
use ark_std::{error::Error, rand::thread_rng};
use sha2::{Digest, Sha256};
use sonobe_fs::nova::{
    instances::{IncomingInstance, RunningInstance},
    witnesses::{IncomingWitness, RunningWitness},
};
use sonobe_ivc::{
    IVC, IVCStatefulProver,
    compilers::cyclefold::{Key, Proof, adapters::nova::NovaNovaIVC},
};
use sonobe_primitives::{
    circuits::FCircuit, commitments::pedersen::Pedersen,
    transcripts::poseidon::poseidon_paper_config,
};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::Path,
    time::Instant,
};

fn canaries(stage: usize) -> [Fr; 7] {
    std::array::from_fn(|i| {
        Fr::from_le_bytes_mod_order(&Sha256::digest(format!(
            "week23-current-synthetic-{stage}-{i}"
        )))
    })
}
struct Circuit;
impl FCircuit for Circuit {
    type Field = Fr;
    type State = [Fr; 5];
    type StateVar = [FpVar<Fr>; 5];
    type ExternalInputs = [Fr; 7];
    type ExternalOutputs = ();
    fn same_state_shape(_: &Self::State, _: &Self::State) -> bool {
        true
    }
    fn dummy_state(&self) -> Self::State {
        [Fr::from(0); 5]
    }
    fn dummy_external_inputs(&self) -> Self::ExternalInputs {
        [Fr::from(1); 7]
    }
    fn generate_step_constraints(
        &self,
        _i: FpVar<Fr>,
        state: Self::StateVar,
        external: [Fr; 7],
    ) -> Result<(Self::StateVar, ()), SynthesisError> {
        let variables = external
            .map(|v| FpVar::new_witness(state[0].cs(), || Ok(v)))
            .into_iter()
            .collect::<Result<Vec<_>, _>>()?;
        let flags = variables
            .iter()
            .map(|v| v.is_eq(&FpVar::Constant(Fr::from(0))).map(|b| !b))
            .collect::<Result<Vec<_>, _>>()?;
        let verdict = FpVar::from(Boolean::kary_and(&flags)?);
        let [session, rid, bucket, policy, count] = state;
        Ok(([session, rid, bucket, policy, count + verdict], ()))
    }
}
fn encode<T: CanonicalSerialize>(v: &T, out: &mut Vec<u8>) {
    v.serialize_compressed(out).unwrap();
}
fn decode<T: CanonicalDeserialize>(input: &mut &[u8]) -> T {
    T::deserialize_compressed(input).unwrap()
}
// Non-hiding commitments have a zero-size Null randomness type without a
// canonical wire implementation upstream. Encode no bytes for that exact type.
trait RandomWire {
    fn put(&self, out: &mut Vec<u8>);
    fn get(input: &mut &[u8]) -> Self;
}
impl RandomWire for Fr {
    fn put(&self, out: &mut Vec<u8>) {
        encode(self, out)
    }
    fn get(input: &mut &[u8]) -> Self {
        decode(input)
    }
}
impl RandomWire for ark_grumpkin::Fr {
    fn put(&self, out: &mut Vec<u8>) {
        encode(self, out)
    }
    fn get(input: &mut &[u8]) -> Self {
        decode(input)
    }
}
impl RandomWire for sonobe_primitives::utils::null::Null {
    fn put(&self, _: &mut Vec<u8>) {}
    fn get(_: &mut &[u8]) -> Self {
        Self
    }
}
fn random_put<T: RandomWire>(v: &T, out: &mut Vec<u8>) {
    v.put(out)
}
fn random_get<T: RandomWire>(input: &mut &[u8]) -> T {
    T::get(input)
}
fn save(path: &Path, bytes: &[u8]) -> Result<(), Box<dyn Error>> {
    let mut f = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)?;
    f.write_all(bytes)?;
    f.sync_all()?;
    Ok(())
}
fn emit(v: serde_json::Value) {
    println!("{v}");
}

macro_rules! experiment {
 ($module:ident,$h:literal)=>{mod $module {use super::*;
 type I=NovaNovaIVC<Pedersen<G1Projective,$h>,Pedersen<G2,$h>,PoseidonSponge<Fr>>;
 type P=<I as IVC>::Proof<Circuit>;type K=<I as IVC>::ProverKey<Circuit>;
 fn pack(p:&P)->Vec<u8>{let mut out=Vec::new();
  encode(&p.0.e,&mut out);random_put(&p.0.r_e,&mut out);encode(&p.0.w,&mut out);random_put(&p.0.r_w,&mut out);
  encode(&p.1.cm_e,&mut out);encode(&p.1.u,&mut out);encode(&p.1.cm_w,&mut out);encode(&p.1.x,&mut out);
  encode(&p.2.w,&mut out);random_put(&p.2.r_w,&mut out);encode(&p.3.cm_w,&mut out);encode(&p.3.x,&mut out);
  encode(&p.4.e,&mut out);random_put(&p.4.r_e,&mut out);encode(&p.4.w,&mut out);random_put(&p.4.r_w,&mut out);
  encode(&p.5.cm_e,&mut out);encode(&p.5.u,&mut out);encode(&p.5.cm_w,&mut out);encode(&p.5.x,&mut out);out
 }
 fn unpack(mut s:&[u8])->P{let p=Proof(
  RunningWitness{e:decode(&mut s),r_e:random_get(&mut s),w:decode(&mut s),r_w:random_get(&mut s)},
  RunningInstance{cm_e:decode(&mut s),u:decode(&mut s),cm_w:decode(&mut s),x:decode(&mut s)},
  IncomingWitness{w:decode(&mut s),r_w:random_get(&mut s)},IncomingInstance{cm_w:decode(&mut s),x:decode(&mut s)},
  RunningWitness{e:decode(&mut s),r_e:random_get(&mut s),w:decode(&mut s),r_w:random_get(&mut s)},
  RunningInstance{cm_e:decode(&mut s),u:decode(&mut s),cm_w:decode(&mut s),x:decode(&mut s)});
  assert!(s.is_empty());p
 }
 fn pack_key(k:&K)->Vec<u8>{let mut b=Vec::new();encode(&k.0,&mut b);encode(&k.1,&mut b);encode(&k.2.0,&mut b);encode(&k.2.1,&mut b);encode(&k.2.2,&mut b);b}
 fn unpack_key(mut s:&[u8])->K{let k=Key(decode(&mut s),decode(&mut s),(decode(&mut s),decode(&mut s),decode(&mut s)));assert!(s.is_empty());k}
 fn audit(p:&P,stage:usize,bytes:&[u8]){let mut rows=Vec::new();
  for owner in 1..=stage {for (i,c) in canaries(owner).iter().enumerate(){let mut b=Vec::new();encode(c,&mut b);let locations=p.2.w.iter().enumerate().filter_map(|(j,v)|(v==c).then_some(j)).collect::<Vec<_>>();
   let running=p.0.w.iter().filter(|v|*v==c).count();let matches=bytes.windows(b.len()).filter(|w|*w==b.as_slice()).count();
   rows.push(serde_json::json!({"owner_stage":owner,"canary_index":i,"incoming_w_indices":locations,"running_w_matches":running,"serialized_matches":matches}));}}
  emit(serde_json::json!({"phase":"leak-audit","hiding":$h,"stage":stage,"pid":std::process::id(),"bytes":bytes.len(),"canaries":rows}));
 }
 fn negatives(k:&K,p:&P,stage:usize,z0:&[Fr;5],zi:&[Fr;5])->Result<(),Box<dyn Error>>{
  let bytes=pack(p);
  for kind in ["running-w","running-e","running-cm-w","running-cm-e","running-u","running-x","incoming-w","incoming-cm-w","incoming-x","cycle-w","cycle-e","cycle-cm-w","cycle-cm-e","cycle-u","cycle-x","step","initial-state","session","rid","bucket","policy","count"]{
   let mut q=unpack(&bytes);let mut claimed=*zi;let mut initial=*z0;let mut steps=stage;
   match kind {
    "running-w"=>q.0.w[0]+=Fr::from(1),"running-e"=>q.0.e[0]+=Fr::from(1),
    "running-cm-w"=>q.1.cm_w+=G1Projective::generator(),"running-cm-e"=>q.1.cm_e+=G1Projective::generator(),
    "running-u"=>q.1.u+=Fr::from(1),"running-x"=>q.1.x[0]+=Fr::from(1),
    "incoming-w"=>q.2.w[0]+=Fr::from(1),"incoming-cm-w"=>q.3.cm_w+=G1Projective::generator(),"incoming-x"=>q.3.x[0]+=Fr::from(1),
    "cycle-w"=>q.4.w[0]+=ark_grumpkin::Fr::from(1),"cycle-e"=>q.4.e[0]+=ark_grumpkin::Fr::from(1),
    "cycle-cm-w"=>q.5.cm_w+=G2::generator(),"cycle-cm-e"=>q.5.cm_e+=G2::generator(),
    "cycle-u"=>q.5.u+=ark_grumpkin::Fr::from(1),"cycle-x"=>q.5.x[0]+=ark_grumpkin::Fr::from(1),
    "step"=>steps+=1,"initial-state"=>initial[0]+=Fr::from(1),
    "session"=>claimed[0]+=Fr::from(1),"rid"=>claimed[1]+=Fr::from(1),"bucket"=>claimed[2]+=Fr::from(1),"policy"=>claimed[3]+=Fr::from(1),"count"=>claimed[4]+=Fr::from(1),_=>unreachable!()
   }
   let result=I::verify::<Circuit>(k,steps,&initial,&claimed,&q);
   emit(serde_json::json!({"phase":"tamper","hiding":$h,"stage":stage,"case":kind,"rejected":result.is_err()}));
   if result.is_ok(){return Err(format!("current verifier accepted {kind}").into());}
  }Ok(())
 }
 pub fn run(dir:&Path,stage:usize)->Result<(),Box<dyn Error>>{
  let mut rng=thread_rng();let circuit=Circuit;let z0=[Fr::from(777),Fr::from(424242),Fr::from(100001),Fr::from(20261011),Fr::from(0)];
  let key=if stage==1 {let config=poseidon_paper_config::<Fr,128>(5,4);let start=Instant::now();let pp=I::preprocess((65536,2048,config),&mut rng)?;let(k,_)=I::generate_keys(pp,&circuit)?;save(&dir.join("key.bin"),&pack_key(&k))?;emit(serde_json::json!({"phase":"keys","hiding":$h,"ms":start.elapsed().as_millis()}));k}
   else {unpack_key(&fs::read(dir.join("key.bin"))?)};
  let (current,proof)=if stage==1 {let p=IVCStatefulProver::<_,I>::new(&key,&circuit,z0)?;(z0,p.current_proof)}
   else {let bytes=fs::read(dir.join(format!("stage{}.bin",stage-1)))?;let p=unpack(&bytes);let mut state=z0;state[4]=Fr::from((stage-1)as u64);I::verify::<Circuit>(&key,stage-1,&z0,&state,&p)?;
    audit(&p,stage-1,&bytes);emit(serde_json::json!({"phase":"receive","hiding":$h,"stage":stage,"verified":true,"pid":std::process::id()}));(state,p)};
  let start=Instant::now();let (next,_,proof)=I::prove(&key,&circuit,stage-1,&z0,&current,canaries(stage),&proof,&mut rng)?;
  let prove_ms=start.elapsed().as_millis();I::verify::<Circuit>(&key,stage,&z0,&next,&proof)?;assert_eq!(next[4],Fr::from(stage as u64));
  let bytes=pack(&proof);save(&dir.join(format!("stage{stage}.bin")),&bytes)?;audit(&proof,stage,&bytes);
  emit(serde_json::json!({"phase":"prove","hiding":$h,"stage":stage,"pid":std::process::id(),"verified":true,"count":stage,"prove_ms":prove_ms,"bytes":bytes.len()}));
  negatives(&key,&proof,stage,&z0,&next)?;
  // Removing the incoming witness is an API/verification failure, not a ZK handoff.
  let mut omitted=unpack(&bytes);omitted.2.w.fill(Fr::from(0));
  let rejected=I::verify::<Circuit>(&key,stage,&z0,&next,&omitted).is_err();assert!(rejected);
  emit(serde_json::json!({"phase":"omit-incoming-witness","hiding":$h,"stage":stage,"rejected":rejected}));Ok(())
 }
 }};
}
experiment!(hiding, true);
experiment!(nonhiding, false);
fn main() -> Result<(), Box<dyn Error>> {
    let args = std::env::args().collect::<Vec<_>>();
    assert_eq!(args.len(), 4);
    let dir = Path::new(&args[2]);
    let stage = args[3].parse::<usize>()?;
    assert!((1..=3).contains(&stage));
    if stage == 1 {
        fs::create_dir(dir)?;
        fs::set_permissions(dir, fs::Permissions::from_mode(0o700))?;
    }
    match args[1].as_str() {
        "true" => hiding::run(dir, stage),
        "false" => nonhiding::run(dir, stage),
        _ => Err("use true|false DIR STAGE".into()),
    }
}
