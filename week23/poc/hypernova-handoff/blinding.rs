//! Probe valid random folding versus full IVC binding; no privacy claim.
use ark_bn254::{Fr,G1Projective};
use ark_grumpkin::Projective;
use ark_ff::PrimeField;
use ark_r1cs_std::{GR1CSVar,alloc::AllocVar,boolean::Boolean,eq::EqGadget,fields::fp::FpVar};
use ark_relations::gr1cs::SynthesisError;
use ark_std::{error::Error,rand::thread_rng,sync::Arc};
use sonobe_fs::{DeciderKey,FoldingSchemeDef,FoldingSchemeDecider,FoldingSchemeProver,FoldingSchemeVerifier,hypernova::HyperNova};
use sonobe_ivc::{IVC,compilers::cyclefold::{Proof,adapters::hypernova::HyperNovaNovaIVC}};
use sonobe_primitives::{circuits::FCircuit,commitments::pedersen::Pedersen,traits::Dummy,relations::WitnessInstanceSampler,transcripts::{Transcript,griffin::{GriffinParams,sponge::GriffinSponge}}};
use std::time::Instant;

type CM=Pedersen<G1Projective,true>;
type H=HyperNova<CM>;
type T=GriffinSponge<Fr>;
type I=HyperNovaNovaIVC<CM,Pedersen<Projective,true>,T>;
type P=<I as IVC>::Proof<Circuit>;
struct Circuit;
impl FCircuit for Circuit {
 type Field=Fr;type State=[Fr;5];type StateVar=[FpVar<Fr>;5];type ExternalInputs=[Fr;7];type ExternalOutputs=();
 fn dummy_state(&self)->Self::State{[Fr::from(0);5]}
 fn dummy_external_inputs(&self)->Self::ExternalInputs{[Fr::from(1);7]}
 fn generate_step_constraints(&self,_i:FpVar<Fr>,state:Self::StateVar,external:[Fr;7])->Result<(Self::StateVar,()),SynthesisError>{
  let inputs=external.map(|v|FpVar::new_witness(state[0].cs(),||Ok(v))).into_iter().collect::<Result<Vec<_>,_>>()?;
  let flags=inputs.iter().map(|v|v.is_eq(&FpVar::Constant(Fr::from(0))).map(|b|!b)).collect::<Result<Vec<_>,_>>()?;
  let [session,rid,bucket,policy,count]=state;
  Ok(([session,rid,bucket,policy,count+FpVar::from(Boolean::kary_and(&flags)?)],()))
 }
}
fn canaries(stage:usize)->[Fr;7]{std::array::from_fn(|i|Fr::from_le_bytes_mod_order(&[0x71,0x59,0x23,stage as u8,i as u8,0xa7,0x9e,0x31,0xb3,0xd5,0x6f,0x81,0x92,0x23,0x45,0x71]))}
fn copy(p:&P)->P {Proof(p.0.clone(),p.1.clone(),p.2.clone(),p.3.clone(),p.4.clone(),p.5.clone())}
fn main()->Result<(),Box<dyn Error>>{
 let mut rng=thread_rng();let config=Arc::new(GriffinParams::new(16,5,9));let circuit=Circuit;
 let start=Instant::now();let pp=I::preprocess((65536,2048,config),&mut rng)?;let(pk,vk)=I::generate_keys(pp,&circuit)?;
 println!("{{\"phase\":\"keys\",\"ms\":{}}}",start.elapsed().as_millis());
 let z0=[Fr::from(777),Fr::from(424242),Fr::from(100001),Fr::from(20261011),Fr::from(0)];let mut state=z0;let mut proof:P=Dummy::dummy(&pk);
 for stage in 1..=3 {
  let start=Instant::now();let(next,_,new)=I::prove(&pk,&circuit,stage-1,&z0,&state,canaries(stage),&proof,&mut rng)?;
  state=next;proof=new;I::verify::<Circuit>(&vk,stage,&z0,&state,&proof)?;assert_eq!(state[4],Fr::from(stage as u64));
  let visible=canaries(stage).iter().filter(|c|proof.2.w.contains(c)).count();assert_eq!(visible,7);
  println!("{{\"phase\":\"ivc-step\",\"stage\":{stage},\"verified\":true,\"incoming_canaries\":{visible},\"ms\":{}}}",start.elapsed().as_millis());
 }
 let (random_w,random_u):(<H as FoldingSchemeDef>::RW,<H as FoldingSchemeDef>::RU)=pk.0.sample((),&mut rng)?;
 H::decide_running(&pk.0,&random_w,&random_u)?;
 let mut tp=T::new_with_pp_hash(&pk.2.0,pk.2.1).separate_domain(b"week23-random-fold-probe");
 let mut tv=T::new_with_pp_hash(&pk.2.0,pk.2.1).separate_domain(b"week23-random-fold-probe");
 let empty_w:[<H as FoldingSchemeDef>::IW;0]=[];let empty_u:[<H as FoldingSchemeDef>::IU;0]=[];
 let start=Instant::now();let (blind_w,blind_u,pi,_) = <H as FoldingSchemeProver<2,0>>::prove(pk.0.to_pk(),&mut tp,&[&proof.0,&random_w],&[&proof.1,&random_u],&empty_w,&empty_u,&mut rng)?;
 H::decide_running(&pk.0,&blind_w,&blind_u)?;
 let verified_u=<H as FoldingSchemeVerifier<2,0>>::verify(pk.0.to_vk(),&mut tv,&[&proof.1,&random_u],&empty_u,&pi)?;assert_eq!(verified_u,blind_u);
 let matches=(1..=3).flat_map(canaries).filter(|c|blind_w.w.contains(c)).count();assert_eq!(matches,0);
 println!("{{\"phase\":\"random-fold\",\"fold_relation_verified\":true,\"nimfs_verified\":true,\"running_canary_matches\":{matches},\"ms\":{}}}",start.elapsed().as_millis());
 let mut altered=copy(&proof);altered.0=blind_w;altered.1=blind_u;
 let direct=I::verify::<Circuit>(&vk,3,&z0,&state,&altered).unwrap_err();
 assert!(matches!(direct,sonobe_ivc::Error::IVCVerificationFail));
 println!("{{\"phase\":\"direct-error\",\"error\":{:?}}}",format!("{direct:?}"));
 println!("{{\"phase\":\"replace-running-state\",\"full_ivc_rejected\":true,\"reason\":\"incoming public hash still binds original accumulator\"}}");
 // Do not equate a successful prove() call with a valid resumed proof.
 match I::prove(&pk,&circuit,3,&z0,&state,canaries(4),&altered,&mut rng) {
  Ok((next,_,resumed)) => {
   let valid=I::verify::<Circuit>(&vk,4,&z0,&next,&resumed).is_ok();
   println!("{{\"phase\":\"resume-direct-blind\",\"prover_returned_proof\":true,\"final_verified\":{valid}}}");
   assert!(!valid,"invalid blinded state resumed to a verified proof");
  },
  Err(_) => println!("{{\"phase\":\"resume-direct-blind\",\"prover_returned_proof\":false,\"final_verified\":false}}"),
 }
 // Recomputing the public hash alone cannot repair the augmented-circuit relation.
 let mut sponge=T::new_with_pp_hash(&pk.2.0,pk.2.1).separate_domain(b"sponge");
 let hash=sponge.add(&3usize).add(&z0).add(&state).add(&altered.1).add(&altered.5).get_field_element();
 altered.3.x[0]=hash;
 let rebound=I::verify::<Circuit>(&vk,3,&z0,&state,&altered).unwrap_err();
 assert!(!matches!(rebound,sonobe_ivc::Error::IVCVerificationFail));
 println!("{{\"phase\":\"rebound-error\",\"error\":{:?}}}",format!("{rebound:?}"));
 println!("{{\"phase\":\"rebind-public-hash-only\",\"full_ivc_rejected\":true,\"reason\":\"incoming witness is not a valid assignment for the re-bound statement\"}}");
 let mut removed=copy(&proof);removed.2.w.fill(Fr::from(0));assert!(I::verify::<Circuit>(&vk,3,&z0,&state,&removed).is_err());
 println!("{{\"phase\":\"erase-incoming-witness\",\"full_ivc_rejected\":true}}");
 // Claim mutation is rejected by the full IVC boundary, independently of masking.
 for index in 0..5 {let mut fake=state;fake[index]+=Fr::from(1);assert!(I::verify::<Circuit>(&vk,3,&z0,&fake,&proof).is_err());}
 println!("{{\"phase\":\"claimed-state-tamper\",\"rejected_fields\":5}}");
 Ok(())
}
