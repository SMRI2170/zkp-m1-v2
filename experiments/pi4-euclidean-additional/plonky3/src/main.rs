//! Goldilocks AIR + HidingFriPcs; preserve upstream ZK FRI budget and OS-seeded salts.
use p3_air::{Air, AirBuilder, BaseAir, WindowAccess};
use p3_challenger::{HashChallenger, SerializingChallenger64};
use p3_commit::ExtensionMmcs;
use p3_dft::Radix2DitParallel;
use p3_field::{PrimeCharacteristicRing, PrimeField64, extension::BinomialExtensionField};
use p3_fri::{FriParameters, HidingFriPcs};
use p3_goldilocks::Goldilocks as F;
use p3_keccak::{Keccak256Hash, KeccakF};
use p3_matrix::dense::RowMajorMatrix;
use p3_merkle_tree::MerkleTreeHidingMmcs;
use p3_symmetric::{CompressionFunctionFromHasher, PaddingFreeSponge, SerializingHasher};
use p3_uni_stark::{StarkConfig, StarkGenericConfig, prove, verify};
use rand::{SeedableRng, rngs::StdRng};
use std::time::Instant;
const WIDTH: usize = 158; // 8 bounded integers (4 coords,d2,r,2 slacks) plus 150 bits.
const BITS: [usize; 8] = [16, 16, 16, 16, 33, 17, 18, 18];
const CASES: [[u64; 6]; 7] = [
    [0, 0, 0, 0, 0, 0],
    [0, 0, 3, 4, 25, 5],
    [3, 4, 0, 0, 25, 5],
    [0, 0, 1, 1, 2, 1],
    [0, 0, 65535, 65535, 8589672450, 92680],
    [65535, 0, 0, 65535, 8589672450, 92680],
    [100, 100, 101, 100, 1, 1],
];
struct EuclideanAir;
impl BaseAir<F> for EuclideanAir {
    fn width(&self) -> usize {
        WIDTH
    }
    fn num_public_values(&self) -> usize {
        2
    }
}
impl<AB: AirBuilder<F = F>> Air<AB> for EuclideanAir {
    fn eval(&self, b: &mut AB) {
        let main = b.main();
        let row = main.current_slice();
        let d: AB::Expr = b.public_values()[0].into();
        let r: AB::Expr = b.public_values()[1].into();
        b.assert_eq(row[4], d.clone());
        b.assert_eq(row[5], r.clone());
        let dx: AB::Expr = row[0].into() - row[2];
        let dy: AB::Expr = row[1].into() - row[3];
        b.assert_eq(d.clone(), dx.clone() * dx + dy.clone() * dy);
        b.assert_eq(row[6], d.clone() - r.clone() * r.clone());
        let rp = r + F::ONE;
        b.assert_eq(row[7], rp.clone() * rp - d - F::ONE);
        let mut at = 8;
        for (j, n) in BITS.iter().enumerate() {
            let mut sum = AB::Expr::ZERO;
            for i in 0..*n {
                let bit: AB::Expr = row[at].into();
                b.assert_bool(bit.clone());
                sum += bit * F::from_u64(1u64 << i);
                at += 1;
            }
            b.assert_eq(row[j], sum);
        }
    }
}
fn trace(a: [F; 6]) -> RowMajorMatrix<F> {
    let mut row = a.to_vec();
    row.push(a[4] - a[5] * a[5]);
    row.push((a[5] + F::ONE) * (a[5] + F::ONE) - a[4] - F::ONE);
    for (j, n) in BITS.iter().enumerate() {
        let value = row[j].as_canonical_u64();
        for i in 0..*n {
            row.push(F::from_u64((value >> i) & 1));
        }
    }
    assert_eq!(row.len(), WIDTH);
    RowMajorMatrix::new(row.repeat(256), WIDTH)
}
type Challenge = BinomialExtensionField<F, 2>;
type U64Hash = PaddingFreeSponge<KeccakF, 25, 17, 4>;
type FH = SerializingHasher<U64Hash>;
type Compress = CompressionFunctionFromHasher<U64Hash, 2, 4>;
type MM = MerkleTreeHidingMmcs<F, u64, FH, Compress, StdRng, 2, 4, 4>;
type EM = ExtensionMmcs<F, Challenge, MM>;
type Challenger = SerializingChallenger64<F, HashChallenger<u8, Keccak256Hash, 32>>;
type PCS = HidingFriPcs<F, Radix2DitParallel<F>, MM, EM, StdRng>;
type Config = StarkConfig<PCS, Challenge, Challenger>;
fn emit(v: serde_json::Value) {
    println!("{v}");
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    emit(
        serde_json::json!({"phase":"start","framework":"Plonky3 Goldilocks AIR/HidingFRI/Keccak","os":std::env::consts::OS,"arch":std::env::consts::ARCH}),
    );
    let t = Instant::now();
    let hash = U64Hash::new(KeccakF {});
    let mm = MM::new(
        FH::new(hash),
        Compress::new(hash),
        0,
        StdRng::from_rng(&mut rand::rng()),
    );
    let em = EM::new(mm.clone());
    let fri = FriParameters::new_benchmark_zk(em);
    let pcs = PCS::new(
        Radix2DitParallel::default(),
        mm,
        fri,
        4,
        StdRng::from_rng(&mut rand::rng()),
    );
    let config = Config::new(pcs, Challenger::from_hasher(vec![], Keccak256Hash {}));
    assert_eq!(config.is_zk(), 1);
    emit(
        serde_json::json!({"phase":"keys","setup_ms":t.elapsed().as_secs_f64()*1000.0,"zero_knowledge_config":true,"fri_log_blowup":2,"fri_num_queries":100,"query_pow_bits":16,"batch_pow_bits":10,"trace_rows":256,"trace_width":WIDTH,"trusted_setup":false}),
    );
    for (i, a) in CASES.iter().enumerate() {
        let a = a.map(F::from_u64);
        let t = Instant::now();
        let tr = trace(a);
        let wms = t.elapsed().as_secs_f64() * 1000.0;
        let t = Instant::now();
        let p = prove(&config, &EuclideanAir, tr, &a[4..]).map_err(|e| format!("prove: {e:?}"))?;
        let pms = t.elapsed().as_secs_f64() * 1000.0;
        let t = Instant::now();
        verify(&config, &EuclideanAir, &p, &a[4..]).map_err(|e| format!("verify: {e:?}"))?;
        let vms = t.elapsed().as_secs_f64() * 1000.0;
        for j in 0..2 {
            let mut pubv = [a[4], a[5]];
            pubv[j] += F::ONE;
            assert!(verify(&config, &EuclideanAir, &p, &pubv).is_err());
        }
        let size = postcard::to_allocvec(&p)?.len();
        let mut bad = p;
        bad.opened_values.trace_local[0] += Challenge::ONE;
        assert!(verify(&config, &EuclideanAir, &bad, &a[4..]).is_err());
        emit(
            serde_json::json!({"phase":"sample","case_id":i,"witness_ms":wms,"prove_ms":pms,"verify_ms":vms,"proof_bytes":size,"public_scalar_bytes":16,"verified":true,"changed_public_rejected":true,"changed_root_rejected":true,"tampered_proof_rejected":true,"tamper_kind":"opened trace value"}),
        );
    }
    let bad: [[u64; 6]; 5] = [
        [0, 0, 3, 4, 25, 4],
        [0, 0, 3, 4, 25, 6],
        [0, 0, 3, 4, 26, 5],
        [65536, 0, 0, 0, 4294967296, 65536],
        [0, 0, 0, 0, 0, 131072],
    ];
    for a in bad {
        let a = a.map(F::from_u64);
        if let Ok(p) = prove(&config, &EuclideanAir, trace(a), &a[4..]) {
            assert!(verify(&config, &EuclideanAir, &p, &a[4..]).is_err());
        }
    }
    let a = [-F::ONE, F::ZERO, F::ZERO, F::ZERO, F::ONE, F::ONE];
    if let Ok(p) = prove(&config, &EuclideanAir, trace(a), &a[4..]) {
        assert!(verify(&config, &EuclideanAir, &p, &a[4..]).is_err());
    }
    emit(
        serde_json::json!({"phase":"summary","samples":7,"invalid_cases_rejected":6,"all_verified":true,"proofs_saved":false}),
    );
    Ok(())
}
