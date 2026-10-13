//! Single-Prover only. Raw IVC contains witnesses; no final ZK/Decider claim.
use ark_bn254::{Fr, G1Projective};
use ark_grumpkin::Projective;
use ark_r1cs_std::{GR1CSVar, alloc::AllocVar, eq::EqGadget, fields::fp::FpVar};
use ark_relations::gr1cs::{ConstraintSystem, SynthesisError};
use ark_std::{error::Error, rand::thread_rng, sync::Arc};
use sonobe_ivc::{
    IVC,
    compilers::cyclefold::adapters::{hypernova::HyperNovaNovaIVC, nova::NovaNovaIVC},
};
use sonobe_primitives::{
    circuits::FCircuit,
    commitments::pedersen::Pedersen,
    traits::Dummy,
    transcripts::griffin::{GriffinParams, sponge::GriffinSponge},
};
use std::time::Instant;
struct Circuit;
fn bounded(v: &FpVar<Fr>, n: usize) -> Result<(), SynthesisError> {
    let _ = v.to_bits_le_with_top_bits_zero(n)?;
    Ok(())
}
impl FCircuit for Circuit {
    type Field = Fr;
    type State = [Fr; 3];
    type StateVar = [FpVar<Fr>; 3];
    type ExternalInputs = [Fr; 6];
    type ExternalOutputs = ();
    fn dummy_state(&self) -> Self::State {
        [Fr::from(0); 3]
    }
    fn dummy_external_inputs(&self) -> Self::ExternalInputs {
        [Fr::from(0); 6]
    }
    fn generate_step_constraints(
        &self,
        _i: FpVar<Fr>,
        s: Self::StateVar,
        e: [Fr; 6],
    ) -> Result<(Self::StateVar, ()), SynthesisError> {
        let v = e
            .map(|x| FpVar::new_witness(s[0].cs(), || Ok(x)))
            .into_iter()
            .collect::<Result<Vec<_>, _>>()?;
        for x in &v[..4] {
            bounded(x, 16)?;
        }
        bounded(&v[4], 33)?;
        bounded(&v[5], 17)?;
        let dx = &v[0] - &v[2];
        let dy = &v[1] - &v[3];
        v[4].enforce_equal(&(&dx * &dx + &dy * &dy))?;
        bounded(&(&v[4] - &v[5] * &v[5]), 18)?;
        let rp = &v[5] + Fr::from(1);
        bounded(&(&rp * &rp - &v[4] - Fr::from(1)), 18)?;
        Ok(([&s[0] + Fr::from(1), v[4].clone(), v[5].clone()], ()))
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
fn check_relation() -> Result<(), Box<dyn Error>> {
    let mut count = 0;
    for a in CASES {
        let cs = ConstraintSystem::<Fr>::new_ref();
        let s = [Fr::from(0); 3].map(|x| FpVar::new_witness(cs.clone(), || Ok(x)).unwrap());
        let _ =
            Circuit.generate_step_constraints(FpVar::Constant(Fr::from(0)), s, a.map(Fr::from))?;
        assert!(cs.is_satisfied()?);
        count = cs.num_constraints();
    }
    let bad: [[u64; 6]; 5] = [
        [0, 0, 3, 4, 25, 4],
        [0, 0, 3, 4, 25, 6],
        [0, 0, 3, 4, 26, 5],
        [65536, 0, 0, 0, 4294967296, 65536],
        [0, 0, 0, 0, 0, 131072],
    ];
    for a in bad {
        let cs = ConstraintSystem::<Fr>::new_ref();
        let s = [Fr::from(0); 3].map(|x| FpVar::new_witness(cs.clone(), || Ok(x)).unwrap());
        let _ =
            Circuit.generate_step_constraints(FpVar::Constant(Fr::from(0)), s, a.map(Fr::from))?;
        assert!(!cs.is_satisfied()?);
    }
    // Negative coordinate represented modulo the field must fail the u16 constraint.
    let cs = ConstraintSystem::<Fr>::new_ref();
    let s = [Fr::from(0); 3].map(|x| FpVar::new_witness(cs.clone(), || Ok(x)).unwrap());
    let _ = Circuit.generate_step_constraints(
        FpVar::Constant(Fr::from(0)),
        s,
        [
            -Fr::from(1),
            Fr::from(0),
            Fr::from(0),
            Fr::from(0),
            Fr::from(1),
            Fr::from(1),
        ],
    )?;
    assert!(!cs.is_satisfied()?);
    println!(
        "{}",
        serde_json::json!({"phase":"relation","valid_cases":7,"invalid_cases_rejected":6,"constraints":count})
    );
    Ok(())
}
fn run<I: IVC>(name: &str) -> Result<(), Box<dyn Error>>
where
    I: IVC<Field = Fr, Config = (usize, usize, Arc<GriffinParams<Fr>>)>,
{
    let mut rng = thread_rng();
    let t = Instant::now();
    let pp = I::preprocess(
        (65536, 2048, Arc::new(GriffinParams::new(16, 5, 9))),
        &mut rng,
    )?;
    let (pk, vk) = I::generate_keys(pp, &Circuit)?;
    println!(
        "{}",
        serde_json::json!({"phase":"keys","framework":name,"setup_ms":t.elapsed().as_secs_f64()*1000.0})
    );
    let z0 = [Fr::from(0); 3];
    let mut z = z0;
    let mut p = I::Proof::<Circuit>::dummy(&pk);
    for (i, a) in CASES.iter().enumerate() {
        let t = Instant::now();
        let (next, _, np) = I::prove(&pk, &Circuit, i, &z0, &z, a.map(Fr::from), &p, &mut rng)?;
        let ms = t.elapsed().as_secs_f64() * 1000.0;
        z = next;
        p = np;
        let t = Instant::now();
        I::verify::<Circuit>(&vk, i + 1, &z0, &z, &p)?;
        let vms = t.elapsed().as_secs_f64() * 1000.0;
        assert_eq!(
            z,
            [Fr::from((i + 1) as u64), Fr::from(a[4]), Fr::from(a[5])]
        );
        for j in 0..3 {
            let mut fake = z;
            fake[j] += Fr::from(1);
            assert!(I::verify::<Circuit>(&vk, i + 1, &z0, &fake, &p).is_err());
        }
        println!(
            "{}",
            serde_json::json!({"phase":"sample","case_id":i,"prove_ms":ms,"verify_ms":vms,"verified":true,"claimed_state_rejections":3})
        );
    }
    println!(
        "{}",
        serde_json::json!({"phase":"summary","framework":name,"steps":7,"all_verified":true,"final_zk":false,"raw_ivc_contains_witness":true,"proofs_saved":false})
    );
    Ok(())
}
fn main() -> Result<(), Box<dyn Error>> {
    println!(
        "{}",
        serde_json::json!({"phase":"start","os":std::env::consts::OS,"arch":std::env::consts::ARCH})
    );
    check_relation()?;
    match std::env::args().nth(1).as_deref() {
        Some("relation") => Ok(()),
        Some("nova") => run::<
            NovaNovaIVC<
                Pedersen<G1Projective, true>,
                Pedersen<Projective, true>,
                GriffinSponge<Fr>,
            >,
        >("Nova/CycleFold"),
        Some("hypernova") => run::<
            HyperNovaNovaIVC<
                Pedersen<G1Projective, true>,
                Pedersen<Projective, true>,
                GriffinSponge<Fr>,
            >,
        >("HyperNova/CycleFold"),
        _ => panic!("use relation|nova|hypernova"),
    }
}
