//! Private synthetic u16 coordinates; public d2 and floor sqrt. Disposable RAM-only keys.
use ark_bn254::{Bn254, Fr};
use ark_ff::Field;
use ark_groth16::{Groth16, Proof, prepare_verifying_key};
use ark_r1cs_std::{alloc::AllocVar, eq::EqGadget, fields::fp::FpVar};
use ark_relations::gr1cs::{
    ConstraintSynthesizer, ConstraintSystem, ConstraintSystemRef, SynthesisError,
};
use ark_serialize::{CanonicalDeserialize, CanonicalSerialize};
use rand::thread_rng;
use std::time::Instant;
#[derive(Clone)]
struct Circuit([Fr; 6]);
fn bound(v: &FpVar<Fr>, n: usize) -> Result<(), SynthesisError> {
    let _ = v.to_bits_le_with_top_bits_zero(n)?;
    Ok(())
}
impl ConstraintSynthesizer<Fr> for Circuit {
    fn generate_constraints(self, cs: ConstraintSystemRef<Fr>) -> Result<(), SynthesisError> {
        let v = self
            .0
            .iter()
            .enumerate()
            .map(|(i, x)| {
                if i < 4 {
                    FpVar::new_witness(cs.clone(), || Ok(*x))
                } else {
                    FpVar::new_input(cs.clone(), || Ok(*x))
                }
            })
            .collect::<Result<Vec<_>, _>>()?;
        for x in &v[..4] {
            bound(x, 16)?;
        }
        bound(&v[4], 33)?;
        bound(&v[5], 17)?;
        let dx = &v[0] - &v[2];
        let dy = &v[1] - &v[3];
        v[4].enforce_equal(&(&dx * &dx + &dy * &dy))?;
        bound(&(&v[4] - &v[5] * &v[5]), 18)?;
        let rp = &v[5] + Fr::ONE;
        bound(&(&rp * &rp - &v[4] - Fr::ONE), 18)?;
        Ok(())
    }
}
const CASES: [[u64; 6]; 7] = [
    [0, 0, 0, 0, 0, 0],
    [0, 0, 3, 4, 25, 5],
    [3, 4, 0, 0, 25, 5],
    [0, 0, 1, 1, 2, 1],
    [0, 0, 65535, 65535, 8589672450, 92680],
    [65535, 0, 0, 65535, 8589672450, 92680],
    [100, 100, 101, 100, 1, 1],
];
fn emit(v: serde_json::Value) {
    println!("{v}");
}
fn bytes<T: CanonicalSerialize>(v: &T) -> Vec<u8> {
    let mut b = vec![];
    v.serialize_compressed(&mut b).unwrap();
    b
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    emit(
        serde_json::json!({"phase":"start","framework":"arkworks Groth16 BN254","os":std::env::consts::OS,"arch":std::env::consts::ARCH,"setup_scope":"disposable single-contributor RAM-only local test; no deploy"}),
    );
    let invalid: [[u64; 6]; 5] = [
        [0, 0, 3, 4, 25, 4],
        [0, 0, 3, 4, 25, 6],
        [0, 0, 3, 4, 26, 5],
        [65536, 0, 0, 0, 4294967296, 65536],
        [0, 0, 0, 0, 0, 131072],
    ];
    for a in invalid {
        let cs = ConstraintSystem::<Fr>::new_ref();
        Circuit(a.map(Fr::from)).generate_constraints(cs.clone())?;
        assert!(!cs.is_satisfied()?);
    }
    let cs = ConstraintSystem::<Fr>::new_ref();
    Circuit([
        -Fr::ONE,
        Fr::from(0),
        Fr::from(0),
        Fr::from(0),
        Fr::ONE,
        Fr::ONE,
    ])
    .generate_constraints(cs.clone())?;
    assert!(!cs.is_satisfied()?);
    let cs = ConstraintSystem::<Fr>::new_ref();
    Circuit(CASES[0].map(Fr::from)).generate_constraints(cs.clone())?;
    assert!(cs.is_satisfied()?);
    emit(
        serde_json::json!({"phase":"relation","constraints":cs.num_constraints(),"invalid_cases_rejected":6}),
    );
    let mut rng = thread_rng();
    let t = Instant::now();
    let pk = Groth16::<Bn254>::generate_random_parameters_with_reduction(
        Circuit(CASES[0].map(Fr::from)),
        &mut rng,
    )?;
    let vk = prepare_verifying_key(&pk.vk);
    emit(
        serde_json::json!({"phase":"keys","setup_ms":t.elapsed().as_secs_f64()*1000.0,"pk_bytes":bytes(&pk).len(),"vk_bytes":bytes(&pk.vk).len()}),
    );
    for (i, a) in CASES.iter().enumerate() {
        let values = a.map(Fr::from);
        let t = Instant::now();
        let proof =
            Groth16::<Bn254>::create_random_proof_with_reduction(Circuit(values), &pk, &mut rng)?;
        let pms = t.elapsed().as_secs_f64() * 1000.0;
        let t = Instant::now();
        assert!(Groth16::<Bn254>::verify_proof(&vk, &proof, &values[4..])?);
        let vms = t.elapsed().as_secs_f64() * 1000.0;
        let mut fake = values[4..].to_vec();
        fake[0] += Fr::ONE;
        assert!(!Groth16::<Bn254>::verify_proof(&vk, &proof, &fake)?);
        fake = values[4..].to_vec();
        fake[1] += Fr::ONE;
        assert!(!Groth16::<Bn254>::verify_proof(&vk, &proof, &fake)?);
        let original = bytes(&proof);
        let mut mutated = original.clone();
        mutated[0] ^= 1;
        let bad = Proof::<Bn254>::deserialize_compressed(&mutated[..]);
        let decode_rejected = bad.is_err();
        let rejected = match bad {
            Err(_) => true,
            Ok(p) => !Groth16::<Bn254>::verify_proof(&vk, &p, &values[4..])?,
        };
        assert!(rejected);
        emit(
            serde_json::json!({"phase":"sample","case_id":i,"prove_ms":pms,"verify_ms":vms,"proof_bytes":original.len(),"public_scalar_bytes":64,"verified":true,"changed_public_rejected":true,"changed_root_rejected":true,"tampered_proof_rejected":true,"tampered_proof_decode_rejected":decode_rejected}),
        );
    }
    emit(
        serde_json::json!({"phase":"summary","samples":7,"all_verified":true,"proofs_saved":false,"private_assignment_cached":false}),
    );
    Ok(())
}
