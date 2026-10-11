// Compile capability probe: HyperNova has a CycleFold IVC adapter in this branch.
// Successful typing does not establish ZK or a witness-free handoff.
use ark_bn254::{Fr, G1Projective};
use ark_grumpkin::Projective;
use ark_crypto_primitives::sponge::poseidon::PoseidonSponge;
use sonobe_fs::{hypernova::HyperNova,nova::CycleFoldNova};
use sonobe_ivc::{IVC,compilers::cyclefold::CycleFoldBasedIVC};
use sonobe_primitives::commitments::pedersen::Pedersen;
type I = CycleFoldBasedIVC<HyperNova<Pedersen<G1Projective,true>>,CycleFoldNova<Pedersen<Projective,true>>,PoseidonSponge<Fr>>;
fn supports_ivc<T: IVC>() {}
fn main(){supports_ivc::<I>();}
