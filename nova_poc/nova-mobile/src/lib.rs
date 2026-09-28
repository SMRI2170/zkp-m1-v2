// Nova(Sonobe)チェーンステップのUniFFIラッパー。week20/09 §2.3.1の設計。
//
// 回路(ChainStepCircuit)・RSSI整合ロジック(rssi_consistency_ok/abs_diff)は
// ../examples/uav_chain_step.rs（week20/08で実装・検証済み）と同一。
// ここではそれをスマホ(Swift/Kotlin)から呼べる薄いオブジェクトAPIとして再公開する。
//
// 公開API（週20/09の設計通り）:
//   ChainState::new(drone_id, time_bucket)  … preprocess(1回だけ, 遅延キャッシュ) + init
//   ChainState::prove_step(obs)             … 1ステップ進める(消費的、内部でmutexロック)
//   ChainState::verify() -> bool            … 現在までのIVC証明を検証
//   ChainState::state() -> Vec<u64>         … z = (drone_id, time_bucket, consistent, suspicious, step)

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
use std::sync::{Mutex, OnceLock};

use folding_schemes::commitment::{kzg::KZG, pedersen::Pedersen};
use folding_schemes::folding::nova::{Nova, PreprocessorParam};
use folding_schemes::frontend::FCircuit;
use folding_schemes::transcript::poseidon::poseidon_canonical_config;
use folding_schemes::{Error as FsError, FoldingScheme};

uniffi::setup_scaffolding!();

// ── circuits/remoteid_consistency_rel.circom と同じ係数（week20/06 §1.4） ──────────
const LAT_CM_NUM: u64 = 11_132_000;
const LON_CM_NUM: u64 = 9_128_800;
const GEO_DEN: u64 = 10_000_000;
const TOL_NUM: u64 = 90;
const TOL_DEN: u64 = 100;

fn abs_diff<F: PrimeField>(a: &FpVar<F>, b: &FpVar<F>) -> Result<FpVar<F>, SynthesisError> {
    let a_lt_b = a.is_cmp(b, Ordering::Less, false)?;
    FpVar::conditionally_select(&a_lt_b, &(b - a), &(a - b))
}

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

    let lower = TOL_DEN - TOL_NUM;
    let upper = TOL_DEN + TOL_NUM;

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

#[derive(Clone, Debug)]
struct ChainStepCircuit<F: PrimeField>
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

    fn new(_params: Self::Params) -> Result<Self, FsError> {
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

        let drone_id = z_i[0].clone();
        let time_bucket = z_i[1].clone();
        let consistent_count = &z_i[2] + &ok;
        let suspicious_count = &z_i[3] + (FpVar::constant(F::one()) - &ok);
        let step_count = &z_i[4] + FpVar::constant(F::one());

        Ok(vec![drone_id, time_bucket, consistent_count, suspicious_count, step_count])
    }
}

type N = Nova<
    Projective,
    Projective2,
    ChainStepCircuit<Fr>,
    KZG<'static, Bn254>,
    Pedersen<Projective2>,
    false,
>;

type NovaParams = (
    <N as FoldingScheme<Projective, Projective2, ChainStepCircuit<Fr>>>::ProverParam,
    <N as FoldingScheme<Projective, Projective2, ChainStepCircuit<Fr>>>::VerifierParam,
);

// preprocess は回路にのみ依存し高コストなので、アプリのプロセス内で1回だけ実行して使い回す
// （実機では初回起動時にここで数百ms〜数秒かかる想定。week20/08のM2 Mac実測は625ms）。
static NOVA_PARAMS: OnceLock<NovaParams> = OnceLock::new();

fn get_params() -> Result<&'static NovaParams, NovaMobileError> {
    if let Some(p) = NOVA_PARAMS.get() {
        return Ok(p);
    }
    let f_circuit = ChainStepCircuit::<Fr>::new(()).map_err(to_err)?;
    let poseidon_config = poseidon_canonical_config::<Fr>();
    let preprocess_params = PreprocessorParam::new(poseidon_config, f_circuit.clone());
    let mut rng = rand::rngs::OsRng;
    let params = N::preprocess(&mut rng, &preprocess_params).map_err(to_err)?;
    Ok(NOVA_PARAMS.get_or_init(|| params))
}

fn to_err(e: FsError) -> NovaMobileError {
    NovaMobileError::Folding(e.to_string())
}

#[derive(Debug, thiserror::Error, uniffi::Error)]
pub enum NovaMobileError {
    #[error("folding-schemes error: {0}")]
    Folding(String),
}

/// 1参加者ぶんの秘匿観測（回路の外に出ない）。week20/06 §1.4と同じ7項目。
#[derive(uniffi::Record)]
pub struct ObservationInput {
    pub drone_lat: u64,
    pub drone_lon: u64,
    pub drone_alt: u64,
    pub target_lat: u64,
    pub target_lon: u64,
    pub target_alt: u64,
    pub measured_range_cm: u64,
}

/// チェーンの状態(z)を保持するオブジェクト。Swift/Kotlinからはハンドルとして扱う。
#[derive(uniffi::Object)]
pub struct ChainState {
    inner: Mutex<N>,
}

#[uniffi::export]
impl ChainState {
    /// z_0 = (drone_id, time_bucket, consistent=0, suspicious=0, step=0) で初期化。
    /// 初回呼び出し時のみ preprocess の重いコストがかかる（以降はキャッシュを再利用）。
    #[uniffi::constructor]
    pub fn new(drone_id: u64, time_bucket: u64) -> Result<std::sync::Arc<Self>, NovaMobileError> {
        let params = get_params()?;
        let f_circuit = ChainStepCircuit::<Fr>::new(()).map_err(to_err)?;
        let initial_state = vec![
            Fr::from(drone_id),
            Fr::from(time_bucket),
            Fr::from(0u64),
            Fr::from(0u64),
            Fr::from(0u64),
        ];
        let folding_scheme = N::init(params, f_circuit, initial_state).map_err(to_err)?;
        Ok(std::sync::Arc::new(Self { inner: Mutex::new(folding_scheme) }))
    }

    /// 1ステップ進める（前の証明を内包して観測を足す）。
    pub fn prove_step(&self, obs: ObservationInput) -> Result<(), NovaMobileError> {
        let ext: [Fr; 7] = [
            Fr::from(obs.drone_lat),
            Fr::from(obs.drone_lon),
            Fr::from(obs.drone_alt),
            Fr::from(obs.target_lat),
            Fr::from(obs.target_lon),
            Fr::from(obs.target_alt),
            Fr::from(obs.measured_range_cm),
        ];
        let mut fs = self.inner.lock().unwrap();
        let rng = rand::rngs::OsRng;
        fs.prove_step(rng, ext, None).map_err(to_err)
    }

    /// 現在までのIVC証明を検証する。
    pub fn verify(&self) -> Result<bool, NovaMobileError> {
        let params = get_params()?;
        let fs = self.inner.lock().unwrap();
        let ivc_proof = fs.ivc_proof();
        match N::verify(params.1.clone(), ivc_proof) {
            Ok(()) => Ok(true),
            Err(_) => Ok(false),
        }
    }

    /// z = (drone_id, time_bucket, consistent_count, suspicious_count, step_count)。
    /// BN254のFrをそのままu64に収まる想定の範囲でしか使わないため、小さい値は文字列表現で返す。
    pub fn state(&self) -> Vec<String> {
        let fs = self.inner.lock().unwrap();
        fs.state().iter().map(|f| f.to_string()).collect()
    }
}
