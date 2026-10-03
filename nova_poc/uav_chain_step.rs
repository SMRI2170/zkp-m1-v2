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

use ark_bn254::{Bn254, Fr, G1Projective as Projective};
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

use folding_schemes::commitment::{kzg::KZG, pedersen::Pedersen};
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

    FpVar::conditionally_select(&ok_bool, &FpVar::constant(F::one()), &FpVar::constant(F::zero()))
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

        Ok(vec![drone_id, time_bucket, consistent_count, suspicious_count, step_count])
    }
}

fn main() -> Result<(), Error> {
    let drone_id = Fr::from(424242u64);
    let time_bucket = Fr::from(100001u64);

    // zk-distance/samples/sample_remoteid_{consistent,spoof}.json と同じ値（week20/06 §2.2と同一条件）。
    let obs_consistent: [Fr; 7] = [
        Fr::from(1_256_891_390u64),
        Fr::from(3_196_917_000u64),
        Fr::from(1_200u64),
        Fr::from(1_256_891_590u64),
        Fr::from(3_196_917_180u64),
        Fr::from(1_000u64),
        Fr::from(341u64),
    ];
    let obs_spoofed: [Fr; 7] = [
        Fr::from(1_256_891_390u64),
        Fr::from(3_196_917_000u64),
        Fr::from(1_200u64),
        Fr::from(1_256_891_590u64),
        Fr::from(3_196_917_180u64),
        Fr::from(1_000u64),
        Fr::from(5_000u64), // 幾何距離は≈341cmだが5000cmを主張＝なりすまし
    ];

    let initial_state = vec![drone_id, time_bucket, Fr::from(0u64), Fr::from(0u64), Fr::from(0u64)];

    let f_circuit = ChainStepCircuit::<Fr>::new(())?;

    type N = Nova<
        Projective,
        Projective2,
        ChainStepCircuit<Fr>,
        KZG<'static, Bn254>,
        Pedersen<Projective2>,
        false,
    >;

    let mut rng = rand::rngs::OsRng;

    println!("[setup] Nova::preprocess (ProverParams / VerifierParams)");
    let t0 = Instant::now();
    // poseidon_configはIVCエンジン自身がz_0/z_i/U_iのFiat-Shamirハッシュに使う
    // （自分のステップ回路の計算では未使用。external_inputs.rs と同じ手順）。
    let poseidon_config = poseidon_canonical_config::<Fr>();
    let nova_preprocess_params = PreprocessorParam::new(poseidon_config, f_circuit.clone());
    let nova_params = N::preprocess(&mut rng, &nova_preprocess_params)?;
    println!("  preprocess: {:?}", t0.elapsed());

    println!("[init] Nova::init(z_0 = (drone_id={}, time_bucket={}, consistent=0, suspicious=0, step=0))",
        drone_id, time_bucket);
    let mut folding_scheme = N::init(&nova_params, f_circuit, initial_state.clone())?;

    let steps = [obs_consistent, obs_consistent, obs_spoofed];
    let labels = ["整合な観測(ok=1想定)", "整合な観測(ok=1想定)", "なりすまし観測(ok=0想定)"];
    for (i, (ext, label)) in steps.iter().zip(labels.iter()).enumerate() {
        let t0 = Instant::now();
        folding_scheme.prove_step(rng, *ext, None)?;
        println!(
            "[step{}] {} prove_step: {:?}  state(z)={:?}",
            i + 1,
            label,
            t0.elapsed(),
            folding_scheme.state()
        );
    }

    println!("\nfinal state z_3 = {:?}", folding_scheme.state());

    println!("\n[verify] Nova IVC verifier（正しい証明）");
    let ivc_proof = folding_scheme.ivc_proof();
    let t0 = Instant::now();
    N::verify(nova_params.1.clone(), ivc_proof.clone())?;
    println!("  OK: 検証成功 ({:?})", t0.elapsed());

    println!("\n[negative] z_i(consistent_count)を改ざんしたIVC証明を検証しようとする");
    let mut forged = ivc_proof.clone();
    forged.z_i[2] += Fr::from(1u64); // consistent_countを勝手に+1偽装
    match N::verify(nova_params.1, forged) {
        Ok(()) => panic!("negative test failed: 改ざんしたz_iで検証が通ってしまった"),
        Err(e) => println!("  → 期待通り検証が失敗（拒否）: {:?}", e),
    }

    Ok(())
}
