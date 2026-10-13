//! Same integer relation over Ristretto scalars. No trusted setup or saved proof.
use curve25519_dalek::scalar::Scalar;
use libspartan::{InputsAssignment, Instance, SNARKGens, VarsAssignment, SNARK};
use merlin::Transcript;
use std::time::Instant;
type L = Vec<(isize, Scalar)>;
fn one() -> L {
    vec![(-1, Scalar::ONE)]
}
fn var(i: isize) -> L {
    vec![(i, Scalar::ONE)]
}
fn sub(mut a: L, b: L) -> L {
    a.extend(b.into_iter().map(|(i, s)| (i, -s)));
    a
}
fn add(mut a: L, b: L) -> L {
    a.extend(b);
    a
}
struct Builder {
    v: Vec<Scalar>,
    p: [Scalar; 2],
    c: Vec<(L, L, L)>,
}
impl Builder {
    fn alloc(&mut self, s: Scalar) -> L {
        let i = self.v.len();
        self.v.push(s);
        var(i as isize)
    }
    fn eval(&self, l: &L) -> Scalar {
        l.iter()
            .map(|(i, c)| {
                c * match *i {
                    -1 => Scalar::ONE,
                    -2 => self.p[0],
                    -3 => self.p[1],
                    j => self.v[j as usize],
                }
            })
            .sum()
    }
    fn mul(&mut self, a: L, b: L) -> L {
        let out = self.alloc(self.eval(&a) * self.eval(&b));
        self.c.push((a, b, out.clone()));
        out
    }
    fn zero(&mut self, a: L) {
        self.c.push((a, one(), vec![]));
    }
    fn range(&mut self, a: L, n: usize) {
        let bytes = self.eval(&a).to_bytes();
        let mut sum = vec![];
        for i in 0..n {
            let bit = self.alloc(Scalar::from(((bytes[i / 8] >> (i % 8)) & 1) as u64));
            self.c.push((bit.clone(), sub(bit.clone(), one()), vec![]));
            sum.extend(
                bit.into_iter()
                    .map(|(v, c)| (v, c * Scalar::from(1u64 << i))),
            );
        }
        self.zero(sub(a, sum));
    }
    fn finish(&self) -> (Instance, VarsAssignment, InputsAssignment, usize) {
        let nv = self.v.len().next_power_of_two();
        let nc = self.c.len().next_power_of_two();
        let mut mats = [vec![], vec![], vec![]];
        for (row, (a, b, c)) in self.c.iter().enumerate() {
            for (m, lc) in mats.iter_mut().zip([a, b, c]) {
                for (i, s) in lc {
                    let col = match *i {
                        -1 => nv,
                        -2 => nv + 1,
                        -3 => nv + 2,
                        j => j as usize,
                    };
                    m.push((row, col, s.to_bytes()));
                }
            }
        }
        let nz = mats.iter().map(Vec::len).max().unwrap();
        let inst = Instance::new(nc, nv, 2, &mats[0], &mats[1], &mats[2]).unwrap();
        let mut values = self.v.iter().map(Scalar::to_bytes).collect::<Vec<_>>();
        values.resize(nv, Scalar::ZERO.to_bytes());
        (
            inst,
            VarsAssignment::new(&values).unwrap(),
            InputsAssignment::new(&self.p.map(|s| s.to_bytes())).unwrap(),
            nz,
        )
    }
}
fn build(a: [Scalar; 6]) -> Builder {
    let mut b = Builder {
        v: vec![],
        p: [a[4], a[5]],
        c: vec![],
    };
    let coords = a[..4].iter().map(|s| b.alloc(*s)).collect::<Vec<_>>();
    for c in &coords {
        b.range(c.clone(), 16)
    }
    let (d, r) = (var(-2), var(-3));
    b.range(d.clone(), 33);
    b.range(r.clone(), 17);
    let dx = sub(coords[0].clone(), coords[2].clone());
    let dy = sub(coords[1].clone(), coords[3].clone());
    let dx2 = b.mul(dx.clone(), dx);
    let dy2 = b.mul(dy.clone(), dy);
    b.zero(sub(d.clone(), add(dx2, dy2)));
    let rs = b.mul(r.clone(), r.clone());
    b.range(sub(d.clone(), rs), 18);
    let rp = add(r, one());
    let rps = b.mul(rp.clone(), rp);
    b.range(sub(sub(rps, d), one()), 18);
    b
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
fn main() {
    emit(
        serde_json::json!({"phase":"start","framework":"Spartan SNARK/Ristretto","os":std::env::consts::OS,"arch":std::env::consts::ARCH}),
    );
    let b = build(CASES[0].map(Scalar::from));
    let (inst, _, _, nz) = b.finish();
    let (nc, nv) = (b.c.len().next_power_of_two(), b.v.len().next_power_of_two());
    let bad: [[u64; 6]; 5] = [
        [0, 0, 3, 4, 25, 4],
        [0, 0, 3, 4, 25, 6],
        [0, 0, 3, 4, 26, 5],
        [65536, 0, 0, 0, 4294967296, 65536],
        [0, 0, 0, 0, 0, 131072],
    ];
    for a in bad {
        let (_, v, p, _) = build(a.map(Scalar::from)).finish();
        assert!(!inst.is_sat(&v, &p).unwrap());
    }
    let (_, v, p, _) = build([
        -Scalar::ONE,
        Scalar::ZERO,
        Scalar::ZERO,
        Scalar::ZERO,
        Scalar::ONE,
        Scalar::ONE,
    ])
    .finish();
    assert!(!inst.is_sat(&v, &p).unwrap());
    emit(
        serde_json::json!({"phase":"relation","constraints":b.c.len(),"padded_constraints":nc,"private_variables":b.v.len(),"padded_variables":nv,"invalid_cases_rejected":6}),
    );
    let t = Instant::now();
    let gens = SNARKGens::new(nc, nv, 2, nz);
    let (comm, decomm) = SNARK::encode(&inst, &gens);
    emit(
        serde_json::json!({"phase":"keys","setup_ms":t.elapsed().as_secs_f64()*1000.0,"trusted_setup":false}),
    );
    for (i, a) in CASES.iter().enumerate() {
        let t = Instant::now();
        let (_, v, p, _) = build(a.map(Scalar::from)).finish();
        assert!(inst.is_sat(&v, &p).unwrap());
        let wms = t.elapsed().as_secs_f64() * 1000.0;
        let t = Instant::now();
        let proof = SNARK::prove(
            &inst,
            &comm,
            &decomm,
            v,
            &p,
            &gens,
            &mut Transcript::new(b"week24-euclidean-spartan-v1"),
        );
        let pms = t.elapsed().as_secs_f64() * 1000.0;
        let t = Instant::now();
        assert!(proof
            .verify(
                &comm,
                &p,
                &mut Transcript::new(b"week24-euclidean-spartan-v1"),
                &gens
            )
            .is_ok());
        let vms = t.elapsed().as_secs_f64() * 1000.0;
        for j in 0..2 {
            let mut inp = [Scalar::from(a[4]), Scalar::from(a[5])];
            inp[j] += Scalar::ONE;
            let fake = InputsAssignment::new(&inp.map(|s| s.to_bytes())).unwrap();
            assert!(proof
                .verify(
                    &comm,
                    &fake,
                    &mut Transcript::new(b"week24-euclidean-spartan-v1"),
                    &gens
                )
                .is_err());
        }
        let mut bytes = bincode::serialize(&proof).unwrap();
        let proof_bytes = bytes.len();
        bytes[0] ^= 1;
        let bad: Result<SNARK, _> = bincode::deserialize(&bytes);
        let decode = bad.is_err();
        assert!(match bad {
            Err(_) => true,
            Ok(q) => q
                .verify(
                    &comm,
                    &p,
                    &mut Transcript::new(b"week24-euclidean-spartan-v1"),
                    &gens
                )
                .is_err(),
        });
        emit(
            serde_json::json!({"phase":"sample","case_id":i,"witness_ms":wms,"prove_ms":pms,"verify_ms":vms,"proof_bytes":proof_bytes,"public_scalar_bytes":64,"verified":true,"changed_public_rejected":true,"changed_root_rejected":true,"tampered_proof_rejected":true,"tampered_proof_decode_rejected":decode}),
        );
    }
    emit(
        serde_json::json!({"phase":"summary","samples":7,"all_verified":true,"proofs_saved":false}),
    );
}
