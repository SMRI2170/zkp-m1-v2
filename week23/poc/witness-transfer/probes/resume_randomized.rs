// This probe must fail to compile: the final ZK proof is not the resume state type.
#[path = "../src/main.rs"]
mod fixture;
use ark_bn254::{Fr, G1Projective};
use ark_grumpkin::Projective;
use folding_schemes::{
    commitment::pedersen::Pedersen,
    folding::nova::{zk::RandomizedIVCProof, Nova},
    FoldingScheme,
};
type N = Nova<
    G1Projective,
    Projective,
    fixture::ChainStepCircuit<Fr>,
    Pedersen<G1Projective, true>,
    Pedersen<Projective, true>,
    true,
>;
fn resume(
    proof: RandomizedIVCProof<G1Projective, Projective>,
    params:(<N as FoldingScheme<G1Projective,Projective,fixture::ChainStepCircuit<Fr>>>::ProverParam,<N as FoldingScheme<G1Projective,Projective,fixture::ChainStepCircuit<Fr>>>::VerifierParam),
) {
    let _ = N::from_ivc_proof(proof, (), params);
}
fn main() {}
