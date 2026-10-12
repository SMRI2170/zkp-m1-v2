//! Intermediate full NIMFS fold binder. NOT full IVC-history/private handoff.
mod curve;
use ark_bn254::{Fr, G1Projective};
use ark_ec::PrimeGroup;
use ark_ff::Zero;
use ark_groth16::Groth16;
use ark_r1cs_std::{
    GR1CSVar, alloc::AllocVar, boolean::Boolean, convert::ToBitsGadget, eq::EqGadget,
    fields::fp::FpVar,
};
use ark_relations::gr1cs::{
    ConstraintSynthesizer, ConstraintSystem, ConstraintSystemRef, SynthesisError,
};
use ark_serialize::CanonicalSerialize;
use ark_snark::SNARK;
use ark_std::{error::Error, rand::thread_rng, sync::Arc};
use sonobe_fs::{
    DeciderKey, FoldingSchemeDecider, FoldingSchemeDef, FoldingSchemeDefGadget,
    FoldingSchemeKeyGenerator, FoldingSchemePartialVerifierGadget, FoldingSchemePreprocessor,
    FoldingSchemeProver, FoldingSchemeVerifier,
    hypernova::{HyperNova, HyperNovaGadget, NIMFSProof},
};
use sonobe_primitives::{
    circuits::{ArithExtractor, utils::CircuitForTest},
    commitments::pedersen::Pedersen,
    relations::WitnessInstanceSampler,
    transcripts::{
        Transcript, TranscriptGadget,
        griffin::{GriffinParams, sponge::GriffinSponge},
    },
};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::Path,
    time::Instant,
};
type CM = Pedersen<G1Projective, true>;
type H = HyperNova<CM>;
type HG = HyperNovaGadget<CM>;
type U = <H as FoldingSchemeDef>::RU;
type W = <H as FoldingSchemeDef>::RW;
type UV = <HG as FoldingSchemeDefGadget>::RU;
type T = GriffinSponge<Fr>;
type TV = <T as Transcript<Fr>>::Gadget;
#[derive(Clone)]
struct Binder {
    inputs: [U; 2],
    target: U,
    pi: NIMFSProof<Fr, 2, 0>,
    config: Arc<GriffinParams<Fr>>,
    meta: [Fr; 5],
    digest: Fr,
}
impl Binder {
    fn hash(&self) -> Fr {
        let mut h = T::new(&self.config).separate_domain(b"week23-fold-binder-v1");
        h.add(&self.meta)
            .add(&self.inputs[..])
            .add(&self.target)
            .get_field_element()
    }
}
fn same_bits(mut a: Vec<Boolean<Fr>>, mut b: Vec<Boolean<Fr>>) -> Result<(), SynthesisError> {
    let n = a.len().max(b.len());
    a.resize(n, Boolean::FALSE);
    b.resize(n, Boolean::FALSE);
    a.enforce_equal(&b)
}
fn bridge(p: &curve::Point, u: &UV) -> Result<(), SynthesisError> {
    let (x, y) = p.affine_xy()?;
    same_bits(x.to_bits_le()?, u.cm.x.to_bits_le()?)?;
    same_bits(y.to_bits_le()?, u.cm.y.to_bits_le()?)
}
impl ConstraintSynthesizer<Fr> for Binder {
    fn generate_constraints(self, cs: ConstraintSystemRef<Fr>) -> Result<(), SynthesisError> {
        // Fixed shape for this circuit/key; malformed proof arrays never redefine it.
        if self.pi.sc_proof.len() != 2
            || self.pi.sc_proof.iter().any(|r| r.len() != 4)
            || self.pi.sigmas.len() != 6
            || !self.pi.thetas.is_empty()
        {
            return Err(SynthesisError::Unsatisfiable);
        }
        for u in self.inputs.iter().chain(std::iter::once(&self.target)) {
            if u.x.len() != 1 || u.r_x.len() != 2 || u.v.len() != 3 {
                return Err(SynthesisError::Unsatisfiable);
            }
        }
        let meta = Vec::<FpVar<Fr>>::new_input(cs.clone(), || Ok(&self.meta[..]))?;
        meta[0].enforce_equal(&FpVar::Constant(Fr::from(1)))?;
        let digest = FpVar::new_input(cs.clone(), || Ok(self.digest))?;
        let us = [
            UV::new_witness(cs.clone(), || Ok(&self.inputs[0]))?,
            UV::new_witness(cs.clone(), || Ok(&self.inputs[1]))?,
        ];
        let target = UV::new_witness(cs.clone(), || Ok(&self.target))?;
        let pi =
            <HG as FoldingSchemeDefGadget>::Proof::<2, 0>::new_witness(
                cs.clone(),
                || Ok(&self.pi),
            )?;
        let mut transcript = TV::new(&self.config).separate_domain(b"week23-fold-transcript-v1")?;
        let (result, bits) = <HG as FoldingSchemePartialVerifierGadget<2, 0>>::verify_hinted(
            &(),
            &mut transcript,
            [&us[0], &us[1]],
            [],
            &pi,
        )?;
        result.u.enforce_equal(&target.u)?;
        result.x.enforce_equal(&target.x)?;
        result.r_x.enforce_equal(&target.r_x)?;
        result.v.enforce_equal(&target.v)?;
        // The upstream partial gadget does NOT constrain the cm hint group arithmetic.
        // Constrain actual BN254 group arithmetic and bridge all point coordinates.
        let p0 = curve::Point::alloc(cs.clone(), self.inputs[0].cm)?;
        bridge(&p0, &us[0])?;
        let p1 = curve::Point::alloc(cs.clone(), self.inputs[1].cm)?;
        bridge(&p1, &us[1])?;
        let pout = curve::Point::alloc(cs.clone(), self.target.cm)?;
        bridge(&pout, &target)?;
        p0.add(&p1.mul_bits(&bits)?).enforce_equal(&pout)?;
        // Bind the partial output hint to the independently constrained group result too.
        result.cm.enforce_equal(&target.cm)?;
        let mut h = TV::new(&self.config).separate_domain(b"week23-fold-binder-v1")?;
        h.add(&meta)?
            .add(&us[..])?
            .add(&target)?
            .get_field_element()?
            .enforce_equal(&digest)
    }
}
fn satisfied(c: Binder) -> Result<(bool, usize), SynthesisError> {
    let cs = ConstraintSystem::<Fr>::new_ref();
    c.generate_constraints(cs.clone())?;
    Ok((cs.is_satisfied()?, cs.num_constraints()))
}
fn save<T: CanonicalSerialize>(path: &Path, value: &T) -> Result<(), Box<dyn Error>> {
    let mut f = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)?;
    value.serialize_compressed(&mut f)?;
    f.flush()?;
    Ok(())
}
fn main() -> Result<(), Box<dyn Error>> {
    let mode = std::env::args().nth(1).unwrap_or("plan".into());
    let mut rng = thread_rng();
    let config = Arc::new(GriffinParams::new(16, 5, 9));
    let pp = H::preprocess(8, &mut rng)?;
    let arith = ArithExtractor::new();
    arith.execute_synthesizer(CircuitForTest { x: Fr::from(2) })?;
    let dk = H::generate_keys(pp, arith.arith()?)?;
    let (w0, u0): (W, U) = dk.sample((), &mut rng)?;
    let (w1, u1): (W, U) = dk.sample((), &mut rng)?;
    H::decide_running(&dk, &w0, &u0)?;
    H::decide_running(&dk, &w1, &u1)?;
    let mut tp = T::new(&config).separate_domain(b"week23-fold-transcript-v1");
    let mut tv = T::new(&config).separate_domain(b"week23-fold-transcript-v1");
    let empty_w: [<H as FoldingSchemeDef>::IW; 0] = [];
    let empty_u: [<H as FoldingSchemeDef>::IU; 0] = [];
    let (wout, target, pi, _) = <H as FoldingSchemeProver<2, 0>>::prove(
        dk.to_pk(),
        &mut tp,
        &[w0, w1],
        &[u0.clone(), u1.clone()],
        &empty_w,
        &empty_u,
        &mut rng,
    )?;
    H::decide_running(&dk, &wout, &target)?;
    assert_eq!(
        target,
        <H as FoldingSchemeVerifier<2, 0>>::verify(
            dk.to_vk(),
            &mut tv,
            &[u0.clone(), u1.clone()],
            &empty_u,
            &pi
        )?
    );
    let mut c = Binder {
        inputs: [u0, u1],
        target,
        pi,
        config,
        meta: [
            Fr::from(1),
            Fr::from(777),
            Fr::from(20261011),
            Fr::from(1),
            Fr::from(3),
        ],
        digest: Fr::zero(),
    };
    c.digest = c.hash();
    let start = Instant::now();
    let (ok, n) = satisfied(c.clone())?;
    assert!(ok);
    println!(
        "{}",
        serde_json::json!({"phase":"plan","constraints":n,"satisfied":true,"ms":start.elapsed().as_millis(),"full_group_equation":true,"full_ivc_history_verified":false})
    );
    if mode == "plan" {
        return Ok(());
    }
    for case in [
        "target-cm",
        "target-scalar",
        "input-cm",
        "sumcheck",
        "sigma",
        "session-digest",
    ] {
        let mut bad = c.clone();
        match case {
            "target-cm" => bad.target.cm += G1Projective::generator(),
            "target-scalar" => bad.target.u += Fr::from(1),
            "input-cm" => bad.inputs[0].cm += G1Projective::generator(),
            "sumcheck" => bad.pi.sc_proof[0][0] += Fr::from(1),
            "sigma" => bad.pi.sigmas[0] += Fr::from(1),
            "session-digest" => bad.meta[1] += Fr::from(1),
            _ => unreachable!(),
        }
        if case != "session-digest" {
            bad.digest = bad.hash();
        }
        let rejected = match satisfied(bad) {
            Ok((ok, _)) => !ok,
            Err(_) => true,
        };
        assert!(rejected, "accepted {case}");
        println!(
            "{}",
            serde_json::json!({"phase":"negative","case":case,"rejected":rejected})
        );
    }
    if mode == "check" {
        return Ok(());
    }
    if mode != "prove" {
        return Err("use plan|check|prove".into());
    }
    let path = Path::new(".cache/week23/private/hypernova-fold-binder-v1");
    fs::create_dir(path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    let start = Instant::now();
    let (pk, vk) = Groth16::<ark_bn254::Bn254>::circuit_specific_setup(c.clone(), &mut rng)?;
    let setup_ms = start.elapsed().as_millis();
    save(&path.join("pk.bin"), &pk)?;
    save(&path.join("vk.bin"), &vk)?;
    println!("{}", serde_json::json!({"phase":"setup","ms":setup_ms}));
    let start = Instant::now();
    let proof = Groth16::<ark_bn254::Bn254>::prove(&pk, c.clone(), &mut rng)?;
    let ms = start.elapsed().as_millis();
    let mut public = c.meta.to_vec();
    public.push(c.digest);
    assert!(Groth16::<ark_bn254::Bn254>::verify(&vk, &public, &proof)?);
    save(&path.join("proof.bin"), &proof)?;
    save(&path.join("public.bin"), &public)?;
    let mut bad_public = public.clone();
    bad_public[1] += Fr::from(1);
    assert!(!Groth16::<ark_bn254::Bn254>::verify(
        &vk,
        &bad_public,
        &proof
    )?);
    println!(
        "{}",
        serde_json::json!({"phase":"proof","verified":true,"prove_ms":ms,"bytes":proof.compressed_size(),"changed_session_rejected":true,"private_assignment_cached":false,"scope":"NIMFS fold binding only; NOT full IVC-history binding or cross-prover secret handoff"})
    );
    Ok(())
}
