//! Experimental yoloproofs R1CS, same bounded integer distance, no committed capture input.
use bulletproofs::{
    r1cs::{ConstraintSystem, LinearCombination as L, Prover, R1CSError, R1CSProof, Verifier},
    BulletproofGens, PedersenGens,
};
use curve25519_dalek::scalar::Scalar;
use merlin::Transcript;
use std::time::Instant;
fn range<CS: ConstraintSystem>(
    cs: &mut CS,
    v: L,
    assignment: Option<Scalar>,
    n: usize,
) -> Result<(), R1CSError> {
    let mut sum = L::default();
    for i in 0..n {
        let a = assignment.map(|s| Scalar::from(((s.to_bytes()[i / 8] >> (i % 8)) & 1) as u64));
        let b = cs.allocate(a)?;
        let (_, _, o) = cs.multiply(b.into(), b - Scalar::ONE);
        cs.constrain(o.into());
        sum = sum + b * Scalar::from(1u64 << i);
    }
    cs.constrain(v - sum);
    Ok(())
}
fn circuit<CS: ConstraintSystem>(
    cs: &mut CS,
    a: Option<[Scalar; 4]>,
    d: Scalar,
    r: Scalar,
) -> Result<(), R1CSError> {
    let v = (0..4)
        .map(|i| cs.allocate(a.map(|x| x[i])))
        .collect::<Result<Vec<_>, _>>()?;
    for i in 0..4 {
        range(cs, v[i].into(), a.map(|x| x[i]), 16)?;
    }
    range(cs, d.into(), Some(d), 33)?;
    range(cs, r.into(), Some(r), 17)?;
    let dx: L = v[0] - v[2];
    let dy: L = v[1] - v[3];
    let (_, _, dx2) = cs.multiply(dx.clone(), dx);
    let (_, _, dy2) = cs.multiply(dy.clone(), dy);
    cs.constrain(dx2 + dy2 - d);
    let (_, _, rs) = cs.multiply(r.into(), r.into());
    range(cs, d - rs, Some(d - r * r), 18)?;
    let rp = r + Scalar::ONE;
    let (_, _, rps) = cs.multiply(rp.into(), rp.into());
    range(
        cs,
        rps - d - Scalar::ONE,
        Some(rp * rp - d - Scalar::ONE),
        18,
    )?;
    Ok(())
}
fn transcript(d: Scalar, r: Scalar) -> Transcript {
    let mut t = Transcript::new(b"week24-euclidean-bulletproofs-v1");
    t.append_message(b"d2", &d.to_bytes());
    t.append_message(b"floor_sqrt", &r.to_bytes());
    t
}
fn verify(
    proof: &R1CSProof,
    d: Scalar,
    r: Scalar,
    pc: &PedersenGens,
    bp: &BulletproofGens,
) -> Result<(), R1CSError> {
    let mut t = transcript(d, r);
    let mut v = Verifier::new(&mut t);
    circuit(&mut v, None, d, r)?;
    v.verify(proof, pc, bp)
}
fn prove(a: [Scalar; 6], pc: &PedersenGens, bp: &BulletproofGens) -> Result<R1CSProof, R1CSError> {
    let mut t = transcript(a[4], a[5]);
    let mut p = Prover::new(pc, &mut t);
    circuit(&mut p, Some([a[0], a[1], a[2], a[3]]), a[4], a[5])?;
    p.prove(bp)
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
fn main() -> Result<(), Box<dyn std::error::Error>> {
    emit(
        serde_json::json!({"phase":"start","framework":"Bulletproofs 5.0.1 pinned git experimental R1CS/Ristretto","os":std::env::consts::OS,"arch":std::env::consts::ARCH,"unstable_r1cs_api":true}),
    );
    let t = Instant::now();
    let pc = PedersenGens::default();
    let bp = BulletproofGens::new(512, 1);
    emit(
        serde_json::json!({"phase":"keys","setup_ms":t.elapsed().as_secs_f64()*1000.0,"trusted_setup":false}),
    );
    for (i, a) in CASES.iter().enumerate() {
        let a = a.map(Scalar::from);
        let t = Instant::now();
        let proof = prove(a, &pc, &bp)?;
        let pms = t.elapsed().as_secs_f64() * 1000.0;
        let t = Instant::now();
        verify(&proof, a[4], a[5], &pc, &bp)?;
        let vms = t.elapsed().as_secs_f64() * 1000.0;
        assert!(verify(&proof, a[4] + Scalar::ONE, a[5], &pc, &bp).is_err());
        assert!(verify(&proof, a[4], a[5] + Scalar::ONE, &pc, &bp).is_err());
        let mut data = proof.to_bytes();
        let size = data.len();
        data[1] ^= 1;
        let bad = R1CSProof::from_bytes(&data);
        let decode = bad.is_err();
        assert!(match bad {
            Err(_) => true,
            Ok(p) => verify(&p, a[4], a[5], &pc, &bp).is_err(),
        });
        emit(
            serde_json::json!({"phase":"sample","case_id":i,"prove_ms":pms,"verify_ms":vms,"proof_bytes":size,"public_scalar_bytes":64,"verified":true,"changed_public_rejected":true,"changed_root_rejected":true,"tampered_proof_rejected":true,"tampered_proof_decode_rejected":decode}),
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
        let a = a.map(Scalar::from);
        if let Ok(p) = prove(a, &pc, &bp) {
            assert!(verify(&p, a[4], a[5], &pc, &bp).is_err());
        }
    }
    let a = [
        -Scalar::ONE,
        Scalar::ZERO,
        Scalar::ZERO,
        Scalar::ZERO,
        Scalar::ONE,
        Scalar::ONE,
    ];
    if let Ok(p) = prove(a, &pc, &bp) {
        assert!(verify(&p, a[4], a[5], &pc, &bp).is_err());
    }
    emit(
        serde_json::json!({"phase":"summary","samples":7,"invalid_cases_rejected":6,"all_verified":true,"proofs_saved":false}),
    );
    Ok(())
}
