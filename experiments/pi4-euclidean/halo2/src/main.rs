//! Synthetic u16 integer Euclidean distance, Halo2 IPA/Pasta; no persisted proof.
use halo2_proofs::{
    arithmetic::Field,
    circuit::{AssignedCell, Layouter, SimpleFloorPlanner, Value},
    dev::MockProver,
    pasta::{EqAffine, Fp},
    plonk::{
        create_proof, keygen_pk, keygen_vk, verify_proof, Advice, Circuit, Column,
        ConstraintSystem, Error, Instance, Selector, SingleVerifier,
    },
    poly::{commitment::Params, Rotation},
    transcript::{Blake2bRead, Blake2bWrite, Challenge255},
};
use rand_core::OsRng;
use std::time::Instant;
#[derive(Clone, Debug)]
struct Config {
    a: [Column<Advice>; 3],
    inst: Column<Instance>,
    mul: Selector,
    add: Selector,
    bit: Selector,
}
#[derive(Clone, Default)]
struct Euclidean {
    values: Option<[u64; 6]>,
}
fn reference(a: [u64; 4]) -> [u64; 6] {
    let dx = a[0] as i64 - a[2] as i64;
    let dy = a[1] as i64 - a[3] as i64;
    let d = (dx * dx + dy * dy) as u64;
    let (mut lo, mut hi, mut r) = (0u64, 92682u64, 0u64);
    while lo <= hi {
        let m = (lo + hi) / 2;
        if m * m <= d {
            r = m;
            lo = m + 1
        } else {
            hi = m - 1
        }
    }
    [a[0], a[1], a[2], a[3], d, r]
}
fn val(e: &Euclidean, i: usize) -> Value<Fp> {
    match e.values {
        Some(v) => Value::known(Fp::from(v[i])),
        None => Value::unknown(),
    }
}
fn alloc(
    l: &mut impl Layouter<Fp>,
    c: &Config,
    v: Value<Fp>,
) -> Result<AssignedCell<Fp, Fp>, Error> {
    l.assign_region(
        || "private value",
        |mut r| r.assign_advice(|| "value", c.a[0], 0, || v),
    )
}
fn op(
    l: &mut impl Layouter<Fp>,
    c: &Config,
    a: &AssignedCell<Fp, Fp>,
    b: &AssignedCell<Fp, Fp>,
    mul: bool,
) -> Result<AssignedCell<Fp, Fp>, Error> {
    l.assign_region(
        || "arithmetic",
        |mut r| {
            if mul {
                c.mul.enable(&mut r, 0)?
            } else {
                c.add.enable(&mut r, 0)?
            };
            a.copy_advice(|| "a", &mut r, c.a[0], 0)?;
            b.copy_advice(|| "b", &mut r, c.a[1], 0)?;
            let v = a
                .value()
                .copied()
                .zip(b.value().copied())
                .map(|(x, y)| if mul { x * y } else { x + y });
            r.assign_advice(|| "result", c.a[2], 0, || v)
        },
    )
}
fn range(
    l: &mut impl Layouter<Fp>,
    c: &Config,
    v: &AssignedCell<Fp, Fp>,
    n: usize,
) -> Result<(), Error> {
    l.assign_region(
        || "range",
        |mut region| {
            let mut acc = Value::known(Fp::ZERO);
            let zero = region.assign_advice_from_constant(|| "zero", c.a[0], 0, Fp::ZERO)?;
            let _ = zero;
            for i in 0..n {
                c.bit.enable(&mut region, i)?;
                let b = v.value().copied().map(|f| {
                    let bytes = f.to_repr();
                    Fp::from(((bytes.as_ref()[(n - 1 - i) / 8] >> ((n - 1 - i) % 8)) & 1) as u64)
                });
                region.assign_advice(|| "bit", c.a[1], i, || b)?;
                acc = acc.zip(b).map(|(a, b)| a + a + b);
                let cell = region.assign_advice(|| "acc", c.a[0], i + 1, || acc)?;
                if i == n - 1 {
                    region.constrain_equal(cell.cell(), v.cell())?;
                }
            }
            Ok(())
        },
    )
}
use ff::PrimeField;
impl Circuit<Fp> for Euclidean {
    type Config = Config;
    type FloorPlanner = SimpleFloorPlanner;
    fn without_witnesses(&self) -> Self {
        Self::default()
    }
    fn configure(cs: &mut ConstraintSystem<Fp>) -> Config {
        let a = [cs.advice_column(), cs.advice_column(), cs.advice_column()];
        for x in a {
            cs.enable_equality(x)
        }
        let inst = cs.instance_column();
        cs.enable_equality(inst);
        let constants = cs.fixed_column();
        cs.enable_constant(constants);
        let (mul, add, bit) = (cs.selector(), cs.selector(), cs.selector());
        cs.create_gate("multiply", |m| {
            vec![
                m.query_selector(mul)
                    * (m.query_advice(a[0], Rotation::cur())
                        * m.query_advice(a[1], Rotation::cur())
                        - m.query_advice(a[2], Rotation::cur())),
            ]
        });
        cs.create_gate("add", |m| {
            vec![
                m.query_selector(add)
                    * (m.query_advice(a[0], Rotation::cur())
                        + m.query_advice(a[1], Rotation::cur())
                        - m.query_advice(a[2], Rotation::cur())),
            ]
        });
        cs.create_gate("range bit", |m| {
            let q = m.query_selector(bit);
            let b = m.query_advice(a[1], Rotation::cur());
            let old = m.query_advice(a[0], Rotation::cur());
            let next = m.query_advice(a[0], Rotation::next());
            vec![
                q.clone()
                    * b.clone()
                    * (b.clone() - halo2_proofs::plonk::Expression::Constant(Fp::ONE)),
                q * (next - old.clone() - old - b),
            ]
        });
        Config {
            a,
            inst,
            mul,
            add,
            bit,
        }
    }
    fn synthesize(&self, c: Config, mut l: impl Layouter<Fp>) -> Result<(), Error> {
        let v = (0..6)
            .map(|i| alloc(&mut l, &c, val(self, i)))
            .collect::<Result<Vec<_>, _>>()?;
        for x in &v[..4] {
            range(&mut l, &c, x, 16)?;
        }
        range(&mut l, &c, &v[4], 33)?;
        range(&mut l, &c, &v[5], 17)?;
        let negone = l.assign_region(
            || "minus one",
            |mut r| r.assign_advice_from_constant(|| "minus one", c.a[0], 0, -Fp::ONE),
        )?;
        let one = l.assign_region(
            || "one",
            |mut r| r.assign_advice_from_constant(|| "one", c.a[0], 0, Fp::ONE),
        )?;
        let nx2 = op(&mut l, &c, &v[2], &negone, true)?;
        let ny2 = op(&mut l, &c, &v[3], &negone, true)?;
        let dx = op(&mut l, &c, &v[0], &nx2, false)?;
        let dy = op(&mut l, &c, &v[1], &ny2, false)?;
        let dx2 = op(&mut l, &c, &dx, &dx, true)?;
        let dy2 = op(&mut l, &c, &dy, &dy, true)?;
        let sum = op(&mut l, &c, &dx2, &dy2, false)?;
        l.assign_region(
            || "bind d2",
            |mut r| r.constrain_equal(sum.cell(), v[4].cell()),
        )?;
        let rs = op(&mut l, &c, &v[5], &v[5], true)?;
        let nrs = op(&mut l, &c, &rs, &negone, true)?;
        let low = op(&mut l, &c, &v[4], &nrs, false)?;
        range(&mut l, &c, &low, 18)?;
        let rp = op(&mut l, &c, &v[5], &one, false)?;
        let rps = op(&mut l, &c, &rp, &rp, true)?;
        let nd = op(&mut l, &c, &v[4], &negone, true)?;
        let upper = op(&mut l, &c, &rps, &nd, false)?;
        let upper = op(&mut l, &c, &upper, &negone, false)?;
        range(&mut l, &c, &upper, 18)?;
        l.constrain_instance(v[4].cell(), c.inst, 0)?;
        l.constrain_instance(v[5].cell(), c.inst, 1)?;
        Ok(())
    }
}
const CASES: [[u64; 4]; 7] = [
    [0, 0, 0, 0],
    [0, 0, 3, 4],
    [3, 4, 0, 0],
    [0, 0, 1, 1],
    [0, 0, 65535, 65535],
    [65535, 0, 0, 65535],
    [100, 100, 101, 100],
];
fn public(v: [u64; 6]) -> Vec<Fp> {
    vec![Fp::from(v[4]), Fp::from(v[5])]
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!(
        "{}",
        serde_json::json!({"phase":"start","os":std::env::consts::OS,"arch":std::env::consts::ARCH,"backend":"Halo2 IPA/Pasta","k":9})
    );
    for a in CASES {
        let v = reference(a);
        MockProver::run(9, &Euclidean { values: Some(v) }, vec![public(v)])?.assert_satisfied();
    }
    let bad = [
        [0, 0, 3, 4, 25, 4],
        [0, 0, 3, 4, 25, 6],
        [0, 0, 3, 4, 26, 5],
        [65536, 0, 0, 0, 4294967296, 65536],
        [0, 0, 0, 0, 0, 131072],
        [u64::MAX, 0, 0, 0, 1, 1],
    ];
    for v in bad {
        assert!(
            MockProver::run(9, &Euclidean { values: Some(v) }, vec![public(v)])?
                .verify()
                .is_err()
        );
    }
    println!(
        "{}",
        serde_json::json!({"phase":"relation","valid_cases":7,"invalid_cases_rejected":6})
    );
    let t = Instant::now();
    let params: Params<EqAffine> = Params::new(9);
    let vk = keygen_vk(&params, &Euclidean::default())?;
    let pk = keygen_pk(&params, vk, &Euclidean::default())?;
    println!(
        "{}",
        serde_json::json!({"phase":"keys","setup_ms":t.elapsed().as_secs_f64()*1000.0})
    );
    for (i, a) in CASES.iter().enumerate() {
        let v = reference(*a);
        let inputs = public(v);
        let c = Euclidean { values: Some(v) };
        let t = Instant::now();
        let mut tr = Blake2bWrite::<_, EqAffine, Challenge255<_>>::init(vec![]);
        create_proof(&params, &pk, &[c], &[&[&inputs]], OsRng, &mut tr)?;
        let proof = tr.finalize();
        let pms = t.elapsed().as_secs_f64() * 1000.0;
        let t = Instant::now();
        verify_proof(
            &params,
            pk.get_vk(),
            SingleVerifier::new(&params),
            &[&[&inputs]],
            &mut Blake2bRead::<_, EqAffine, Challenge255<_>>::init(&proof[..]),
        )?;
        let vms = t.elapsed().as_secs_f64() * 1000.0;
        let mut fake = inputs.clone();
        fake[0] += Fp::ONE;
        assert!(verify_proof(
            &params,
            pk.get_vk(),
            SingleVerifier::new(&params),
            &[&[&fake]],
            &mut Blake2bRead::<_, EqAffine, Challenge255<_>>::init(&proof[..])
        )
        .is_err());
        let mut altered = proof.clone();
        altered[0] ^= 1;
        assert!(verify_proof(
            &params,
            pk.get_vk(),
            SingleVerifier::new(&params),
            &[&[&inputs]],
            &mut Blake2bRead::<_, EqAffine, Challenge255<_>>::init(&altered[..])
        )
        .is_err());
        println!(
            "{}",
            serde_json::json!({"phase":"sample","case_id":i,"prove_ms":pms,"verify_ms":vms,"verified":true,"proof_bytes":proof.len(),"changed_public_rejected":true,"tampered_proof_rejected":true})
        );
    }
    println!(
        "{}",
        serde_json::json!({"phase":"summary","all_verified":true,"samples":7,"proofs_saved":false})
    );
    Ok(())
}
