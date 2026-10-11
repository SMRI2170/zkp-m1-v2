// Nova(Folding, 方式B) PoC — week20/04 §0・§9 で「省メモリ代替」として温存していた方式Bを、
// Sonobe（privacy-ethereum/sonobe, folding-schemes crate, BN254/Grumpkin曲線サイクル）で実装する。
//
// ステップ関数(F)は aggregator/cmd/chainpoc（方式A/gnark PoC, week20/06）と同じ関係を強制する:
//   - RSSI整合判定(circuits/remoteid_consistency_rel.circom と同じ相対許容帯の計算, week20/06 §1.4)
//   - 累積状態 z = (drone_id, time_bucket, consistent_count, suspicious_count, step_count)
//     consistent_count += ok, suspicious_count += (1-ok), step_count += 1
//
// 方式Aとの違い（設計上の要点、詳細は week20/08 参照）:
//   - Nova(IVC)はフレームワーク自身が z_i の連続性を保証するため、gnark版のように
//     「前の証明を検証して取り出したdrone_id/time_bucketが新しい主張と一致するか」を自分で
//     assertする必要がない（z_iは"主張"ではなくIVCエンジンが管理する真の状態）。
//   - 「前の証明を検証する」ための箱のサイズ問題（week20/06 §1.2, 自己再帰のブートストラップ）も
//     Novaには存在しない。各ステップは同じ1つの回路(ChainStepCircuit)をそのまま使い回せる。
#![allow(non_snake_case)]

use ark_bn254::{Fr, G1Projective as Projective};
use ark_crypto_primitives::sponge::Absorb;
use ark_ff::PrimeField;
use ark_grumpkin::Projective as Projective2;
use ark_r1cs_std::{
    boolean::Boolean,
    fields::{fp::FpVar, FieldVar},
    select::CondSelectGadget,
};
use ark_relations::gr1cs::{ConstraintSystemRef, SynthesisError};
use core::cmp::Ordering;
use core::marker::PhantomData;
use std::time::Instant;

use folding_schemes::commitment::pedersen::Pedersen;
use folding_schemes::folding::nova::{Nova, PreprocessorParam};
use folding_schemes::frontend::FCircuit;
use folding_schemes::transcript::poseidon::poseidon_canonical_config;
use folding_schemes::{Error, FoldingScheme};

// circuits/remoteid_consistency_rel.circom と同じ係数（week20/06 §1.4 の対応表と同一）。
const LAT_CM_NUM: u64 = 11_132_000;
const LON_CM_NUM: u64 = 9_128_800;
const GEO_DEN: u64 = 10_000_000;
const TOL_NUM: u64 = 90;
const TOL_DEN: u64 = 100;

/// |a-b|。circuits/lib_uav_safety.circom の AbsDiff と同じ発想。
/// gnark版(week20/06)では cmp.IsLess + api.Select、Sonobe(arkworks)では
/// FpVar::is_cmp（ark-r1cs-std 0.6.0 の専用比較API。両辺が (p-1)/2 以下であることが前提だが、
/// 今回の値はどれも field modulus よりはるかに小さいので問題ない）+ CondSelectGadget で同じことを行う。
fn abs_diff<F: PrimeField>(a: &FpVar<F>, b: &FpVar<F>) -> Result<FpVar<F>, SynthesisError> {
    let a_lt_b = a.is_cmp(b, Ordering::Less, false)?;
    FpVar::conditionally_select(&a_lt_b, &(b - a), &(a - b))
}

/// circuits/remoteid_consistency_rel.circom(RemoteIdConsistencyRel)と同じ計算。
/// 申告位置(drone)と自位置(target)から幾何距離の二乗を求め、RSSI実測レンジ(measuredRangeCm)の
/// 相対許容帯 ±90% と整数のまま比較する（平方根・除算を避ける設計はcircom/gnark版を踏襲）。
fn rssi_consistency_ok<F: PrimeField>(
    drone_lat: &FpVar<F>,
    drone_lon: &FpVar<F>,
    drone_alt: &FpVar<F>,
    target_lat: &FpVar<F>,
    target_lon: &FpVar<F>,
    target_alt: &FpVar<F>,
    measured_range_cm: &FpVar<F>,
) -> Result<FpVar<F>, SynthesisError> {
    let d_lat = abs_diff(drone_lat, target_lat)?;
    let d_lon = abs_diff(drone_lon, target_lon)?;
    let d_alt = abs_diff(drone_alt, target_alt)?;

    let lat_scaled = &d_lat * FpVar::constant(F::from(LAT_CM_NUM));
    let lon_scaled = &d_lon * FpVar::constant(F::from(LON_CM_NUM));
    let alt_scaled = &d_alt * FpVar::constant(F::from(GEO_DEN));

    let claimed_dist_sq =
        &lat_scaled * &lat_scaled + &lon_scaled * &lon_scaled + &alt_scaled * &alt_scaled;

    let lower = TOL_DEN - TOL_NUM; // 10
    let upper = TOL_DEN + TOL_NUM; // 190

    let base = measured_range_cm * FpVar::constant(F::from(GEO_DEN));
    let lower_num = &base * FpVar::constant(F::from(lower));
    let upper_num = &base * FpVar::constant(F::from(upper));
    let lower_sq = &lower_num * &lower_num;
    let upper_sq = &upper_num * &upper_num;

    let claimed_scaled = &claimed_dist_sq * FpVar::constant(F::from(TOL_DEN * TOL_DEN));

    let ge_lower = lower_sq.is_cmp(&claimed_scaled, Ordering::Less, true)?;
    let le_upper = claimed_scaled.is_cmp(&upper_sq, Ordering::Less, true)?;
    let ok_bool: Boolean<F> = Boolean::kary_and(&[ge_lower, le_upper])?;

    FpVar::conditionally_select(
        &ok_bool,
        &FpVar::constant(F::one()),
        &FpVar::constant(F::zero()),
    )
}

/// IVCのステップ関数 F。z_i = (drone_id, time_bucket, consistent_count, suspicious_count, step_count)。
/// 外部入力(external_inputs)は各参加者の秘匿観測7つ（回路の外に出ない）。
#[derive(Clone, Debug)]
pub struct ChainStepCircuit<F: PrimeField>
where
    F: Absorb,
{
    _f: PhantomData<F>,
}

impl<F: PrimeField> FCircuit<F> for ChainStepCircuit<F>
where
    F: Absorb,
{
    type Params = ();
    type ExternalInputs = [F; 7];
    type ExternalInputsVar = [FpVar<F>; 7];

    fn new(_params: Self::Params) -> Result<Self, Error> {
        Ok(Self { _f: PhantomData })
    }

    fn state_len(&self) -> usize {
        5
    }

    fn generate_step_constraints(
        &self,
        _cs: ConstraintSystemRef<F>,
        _i: usize,
        z_i: Vec<FpVar<F>>,
        external_inputs: Self::ExternalInputsVar,
    ) -> Result<Vec<FpVar<F>>, SynthesisError> {
        let [drone_lat, drone_lon, drone_alt, target_lat, target_lon, target_alt, measured_range_cm] =
            external_inputs;

        let ok = rssi_consistency_ok(
            &drone_lat,
            &drone_lon,
            &drone_alt,
            &target_lat,
            &target_lon,
            &target_alt,
            &measured_range_cm,
        )?;

        // 同一ドローン・同一時間窓: NovaはIVCエンジン自身がz_iの連続性を保証するため、
        // gnark版のような「前の証明から取り出した値と新しい主張が一致するか」のassertは不要。
        // ここでは単に前の値を引き継ぐだけでよい。
        let drone_id = z_i[0].clone();
        let time_bucket = z_i[1].clone();
        let consistent_count = &z_i[2] + &ok;
        let suspicious_count = &z_i[3] + (FpVar::constant(F::one()) - &ok);
        let step_count = &z_i[4] + FpVar::constant(F::one());

        Ok(vec![
            drone_id,
            time_bucket,
            consistent_count,
            suspicious_count,
            step_count,
        ])
    }
}

use ark_ec::AffineRepr;
use ark_serialize::{CanonicalDeserialize, CanonicalSerialize};
use serde_json::json;
use std::io::Write;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::{fs, path::Path};

type N<const H: bool> = Nova<
    Projective,
    Projective2,
    ChainStepCircuit<Fr>,
    Pedersen<Projective, H>,
    Pedersen<Projective2, H>,
    H,
>;
// Entirely invented coordinates/range; never read capture files.
const CANARY: [u64; 7] = [71001, 82003, 93007, 71019, 82021, 94009, 10103];
fn save<T: CanonicalSerialize>(p: &Path, value: &T) -> Result<(), Box<dyn std::error::Error>> {
    let mut bytes = vec![];
    value.serialize_compressed(&mut bytes)?;
    let mut f = fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(p)?;
    f.write_all(&bytes)?;
    Ok(())
}
fn read<T: CanonicalDeserialize>(p: &Path) -> Result<T, Box<dyn std::error::Error>> {
    let bytes = fs::read(p)?;
    Ok(T::deserialize_compressed(&bytes[..])?)
}
fn experiment<const H: bool>(mode: &str, dir: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let mut rng = rand::rngs::OsRng;
    let circuit = ChainStepCircuit::<Fr>::new(())?;
    if mode == "a" {
        fs::create_dir(dir)?;
        fs::set_permissions(dir, fs::Permissions::from_mode(0o700))?;
        let t = Instant::now();
        let params = N::<H>::preprocess(
            &mut rng,
            &PreprocessorParam::new(poseidon_canonical_config::<Fr>(), circuit.clone()),
        )?;
        let setup_ms = t.elapsed().as_secs_f64() * 1000.;
        let z0 = vec![
            Fr::from(424242u64),
            Fr::from(100001u64),
            Fr::from(0u64),
            Fr::from(0u64),
            Fr::from(0u64),
        ];
        let mut prover = N::<H>::init(&params, circuit, z0)?;
        let t = Instant::now();
        prover.prove_step(&mut rng, CANARY.map(Fr::from), None)?;
        let prove_ms = t.elapsed().as_secs_f64() * 1000.;
        let proof = prover.ivc_proof();
        N::<H>::verify(params.1.clone(), proof.clone())?;
        save(&dir.join("pp.bin"), &params.0)?;
        save(&dir.join("vp.bin"), &params.1)?;
        save(&dir.join("state.bin"), &proof)?;
        println!(
            "{}",
            json!({"role":"A","pid":std::process::id(),"hiding":H,"setup_ms":setup_ms,"prove_ms":prove_ms,"bytes":fs::metadata(dir.join("state.bin"))?.len(),"verified":true})
        );
        return Ok(());
    }
    let pp: <N<H> as FoldingScheme<Projective, Projective2, ChainStepCircuit<Fr>>>::ProverParam =
        read(&dir.join("pp.bin"))?;
    let vp_bytes = fs::read(dir.join("vp.bin"))?;
    let vp = N::<H>::vp_deserialize_with_mode(
        &vp_bytes[..],
        ark_serialize::Compress::Yes,
        ark_serialize::Validate::Yes,
        (),
    )?;
    let proof: folding_schemes::folding::nova::IVCProof<Projective, Projective2> =
        read(&dir.join("state.bin"))?;
    let t = Instant::now();
    N::<H>::verify(vp.clone(), proof.clone())?;
    let verify_ms = t.elapsed().as_secs_f64() * 1000.;
    let matches: Vec<_> = CANARY.iter().enumerate().map(|(field, &value)| {
        let needle = Fr::from(value);
        json!({"field":field,"w_i_indices":proof.w_i.W.iter().enumerate().filter(|(_,v)|**v==needle).map(|(i,_)|i).collect::<Vec<_>>(),"W_i_indices":proof.W_i.W.iter().enumerate().filter(|(_,v)|**v==needle).map(|(i,_)|i).collect::<Vec<_>>()})
    }).collect();
    println!(
        "{}",
        json!({"role":"B","pid":std::process::id(),"hiding":H,"verify_ms":verify_ms,"w_i_W_len":proof.w_i.W.len(),"W_i_W_len":proof.W_i.W.len(),"cf_W_len":proof.cf_W_i.W.len(),"canary_matches":matches})
    );
    for kind in ["valid", "count", "rid", "bucket", "witness", "commitment"] {
        let mut p = proof.clone();
        match kind {
            "count" => p.z_i[2] += Fr::from(1u64),
            "rid" => p.z_i[0] += Fr::from(1u64),
            "bucket" => p.z_i[1] += Fr::from(1u64),
            "witness" => p.w_i.W[0] += Fr::from(1u64),
            "commitment" => p.u_i.cmW += Projective::from(ark_bn254::G1Affine::generator()),
            _ => (),
        }
        let incoming_matches = p
            .w_i
            .commit::<Pedersen<Projective, H>, H>(&pp.cs_pp, p.u_i.x.clone())?
            == p.u_i;
        let verify = N::<H>::verify(vp.clone(), p.clone());
        let t = Instant::now();
        let restore = N::<H>::from_ivc_proof(p, (), (pp.clone(), vp.clone()));
        let mut row = json!({"case":kind,"hiding":H,"received_verify_ok":verify.is_ok(),"restore_ok":restore.is_ok(),"incoming_commitment_matches_witness":incoming_matches});
        if let Ok(mut next) = restore {
            let step = next.prove_step(&mut rng, CANARY.map(|v| Fr::from(v + 2)), None);
            row["step_ok"] = json!(step.is_ok());
            row["step_error"] = json!(step.err().map(|e| format!("{e:?}")));
            row["final_verify_ok"] = json!(N::<H>::verify(vp.clone(), next.ivc_proof()).is_ok());
        }
        row["continue_ms"] = json!(t.elapsed().as_secs_f64() * 1000.);
        println!("{row}");
        if kind == "valid" {
            assert!(
                row["received_verify_ok"] == true
                    && row["restore_ok"] == true
                    && row["step_ok"] == true
                    && row["final_verify_ok"] == true
            );
        } else {
            assert!(row["received_verify_ok"] == false);
        }
    }
    Ok(())
}
fn zk_experiment(dir: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let pp: <N<true> as FoldingScheme<Projective, Projective2, ChainStepCircuit<Fr>>>::ProverParam =
        read(&dir.join("pp.bin"))?;
    let bytes = fs::read(dir.join("vp.bin"))?;
    let vp = N::<true>::vp_deserialize_with_mode(
        &bytes[..],
        ark_serialize::Compress::Yes,
        ark_serialize::Validate::Yes,
        (),
    )?;
    let proof: folding_schemes::folding::nova::IVCProof<Projective, Projective2> =
        read(&dir.join("state.bin"))?;
    N::<true>::verify(vp.clone(), proof.clone())?;
    let prover = N::<true>::from_ivc_proof(proof, (), (pp, vp))?;
    let t = Instant::now();
    let zk =
        folding_schemes::folding::nova::zk::RandomizedIVCProof::new(&prover, rand::rngs::OsRng)?;
    let generate_ms = t.elapsed().as_secs_f64() * 1000.;
    let result = folding_schemes::folding::nova::zk::RandomizedIVCProof::verify::<
        Pedersen<Projective, true>,
        Pedersen<Projective2, true>,
    >(
        &prover.r1cs,
        &prover.cf_r1cs,
        prover.pp_hash,
        &prover.poseidon_config,
        prover.i,
        prover.z_0.clone(),
        prover.z_i.clone(),
        &zk,
    );
    let direct_matches = CANARY
        .iter()
        .filter(|&&v| zk.W_i_prime.W.contains(&Fr::from(v)))
        .count();
    println!(
        "{}",
        json!({"probe":"RandomizedIVCProof","generate_ms":generate_ms,"verify_ok":result.is_ok(),"direct_canary_matches_W_i_prime":direct_matches,"resume_api":"from_ivc_proof requires IVCProof, not RandomizedIVCProof; no conversion located"})
    );
    result?;
    Ok(())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() == 4 && args[1] == "zk" && args[2] == "true" {
        return zk_experiment(Path::new(&args[3]));
    }
    if args.len() != 4
        || !["a", "b"].contains(&args[1].as_str())
        || !["false", "true"].contains(&args[2].as_str())
    {
        return Err("usage: week23-witness-transfer a|b false|true PRIVATE_DIRECTORY".into());
    }
    if args[2] == "true" {
        experiment::<true>(&args[1], Path::new(&args[3]))
    } else {
        experiment::<false>(&args[1], Path::new(&args[3]))
    }
}
