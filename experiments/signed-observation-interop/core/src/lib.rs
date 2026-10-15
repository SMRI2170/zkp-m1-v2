//! Compatibility verifier for the pinned gnark synthetic signed batch.
//! No proof system, no secret-key generation, no claim of sensor truth.
#![no_std]
extern crate alloc;
use alloc::vec::Vec;
use ark_bn254::Fr;
use ark_ff::{AdditiveGroup, BigInt, BigInteger, Field, MontFp, PrimeField, Zero};
use serde::{Deserialize, Serialize};
use sha3::{Digest, Keccak256};

pub const DOMAIN: u64 = 0x574b3234;
const D: Fr =
    MontFp!("12181644023421730124874158521699555681764249180949974110617291017600649128846");
const GX: Fr =
    MontFp!("9671717474070082183213120605117400219616337014328744928644933853176787189663");
const GY: Fr =
    MontFp!("16950150798460657717958625567821834550301663161624707787222815936182638968203");
// Prime-order subgroup of the pinned gnark BN254 twisted Edwards curve.
const ORDER: [u8; 32] = [
    0x06, 0x0c, 0x89, 0xce, 0x5c, 0x26, 0x34, 0x05, 0x37, 0x0a, 0x08, 0xb6, 0xd0, 0x30, 0x2b, 0x0b,
    0xab, 0x3e, 0xed, 0xb8, 0x39, 0x20, 0xee, 0x0a, 0x67, 0x72, 0x97, 0xdc, 0x39, 0x21, 0x26, 0xf1,
];

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Public {
    pub count: u8,
    pub session: u64,
    pub policy: u64,
    pub rid: u64,
    pub root: [u8; 32],
    pub pk: [[u8; 32]; 2],
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Observation {
    /// X1, Y1, X2, Y2, D2, R; synthetic witness, never log these in results.
    pub values: [u64; 6],
    /// Canonical uncompressed Rx, Ry, S; each fixed-width big-endian.
    pub signature: [[u8; 32]; 3],
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Batch {
    pub public: Public,
    pub observations: Vec<Observation>,
}

pub fn decode_field(bytes: &[u8; 32]) -> Option<Fr> {
    let mut limbs = [0u64; 4];
    for (i, limb) in limbs.iter_mut().enumerate() {
        *limb = u64::from_be_bytes(bytes[24 - i * 8..32 - i * 8].try_into().ok()?);
    }
    Fr::from_bigint(BigInt(limbs)) // Reject noncanonical values; never silently reduce.
}
pub fn field_bytes(f: Fr) -> [u8; 32] {
    let bytes = f.into_bigint().to_bytes_be();
    let mut out = [0; 32];
    out[32 - bytes.len()..].copy_from_slice(&bytes);
    out
}

pub struct MiMC {
    constants: [Fr; 110],
}
impl Default for MiMC {
    fn default() -> Self {
        Self::new()
    }
}
impl MiMC {
    pub fn new() -> Self {
        // gnark-crypto v0.21.0: legacy Keccak256(seed), then one Keccak per round.
        let mut previous = Keccak256::digest(b"seed");
        let mut constants = [Fr::ZERO; 110];
        for c in &mut constants {
            previous = Keccak256::digest(previous);
            *c = Fr::from_be_bytes_mod_order(&previous);
        }
        Self { constants }
    }
    pub fn hash(&self, values: &[Fr]) -> Fr {
        let mut h = Fr::ZERO;
        for v in values {
            let mut m = *v;
            for c in self.constants {
                let t = m + h + c;
                m = t.square().square() * t;
            }
            // Miyaguchi-Preneel: encrypt(v,h) + h + v; encrypt adds h at the end.
            h = m + h + h + v;
        }
        h
    }
}

// Extended Edwards coordinates, a=-1. Complete addition formulas; no inversions.
#[derive(Clone, Copy)]
struct Point {
    x: Fr,
    y: Fr,
    z: Fr,
    t: Fr,
}
impl Point {
    fn identity() -> Self {
        Self {
            x: Fr::ZERO,
            y: Fr::ONE,
            z: Fr::ONE,
            t: Fr::ZERO,
        }
    }
    fn affine(x: Fr, y: Fr) -> Option<Self> {
        if -x.square() + y.square() != Fr::ONE + D * x.square() * y.square() {
            return None;
        }
        Some(Self {
            x,
            y,
            z: Fr::ONE,
            t: x * y,
        })
    }
    fn from_bytes(p: &[[u8; 32]; 2]) -> Option<Self> {
        Self::affine(decode_field(&p[0])?, decode_field(&p[1])?)
    }
    fn add(self, b: Self) -> Self {
        let aa = (self.y - self.x) * (b.y - b.x);
        let bb = (self.y + self.x) * (b.y + b.x);
        let cc = self.t * D.double() * b.t;
        let dd = self.z.double() * b.z;
        let e = bb - aa;
        let f = dd - cc;
        let g = dd + cc;
        let h = bb + aa;
        Self {
            x: e * f,
            y: g * h,
            z: f * g,
            t: e * h,
        }
    }
    fn mul(self, scalar: &[u8; 32]) -> Self {
        let mut acc = Self::identity();
        for byte in scalar {
            for bit in (0..8).rev() {
                acc = acc.add(acc);
                if byte & (1 << bit) != 0 {
                    acc = acc.add(self);
                }
            }
        }
        acc
    }
    fn times8(self) -> Self {
        let p = self.add(self);
        let p = p.add(p);
        p.add(p)
    }
    fn equals(self, b: Self) -> bool {
        !self.z.is_zero()
            && !b.z.is_zero()
            && self.x * b.z == b.x * self.z
            && self.y * b.z == b.y * self.z
    }
}

fn signature_ok(hash: &MiMC, public: &Public, sig: &[[u8; 32]; 3], msg: Fr) -> bool {
    let Some(pk) = Point::from_bytes(&public.pk) else {
        return false;
    };
    if pk.equals(Point::identity()) || !pk.mul(&ORDER).equals(Point::identity()) {
        return false;
    }
    let Some(r) = Point::from_bytes(&[sig[0], sig[1]]) else {
        return false;
    };
    if sig[2] >= ORDER {
        return false;
    }
    let hr = hash.hash(&[r.x, r.y, pk.x, pk.y, msg]);
    let base = Point::affine(GX, GY).expect("fixed curve generator");
    base.mul(&sig[2])
        .times8()
        .equals(r.add(pk.mul(&field_bytes(hr))).times8())
}

/// Returns true only for a canonical, valid-key, observer-signed synthetic statement.
/// The stronger key/point checks are explicit; see SPEC.md for baseline differences.
pub fn verify(batch: &Batch) -> bool {
    let p = &batch.public;
    if ![1, 2, 4].contains(&p.count)
        || batch.observations.len() != p.count as usize
        || p.session >= 1 << 32
        || p.policy >= 1 << 16
    {
        return false;
    }
    let Some(root) = decode_field(&p.root) else {
        return false;
    };
    let hash = MiMC::new();
    let mut aggregate = alloc::vec![
        Fr::from(DOMAIN),
        Fr::from(p.count as u64),
        Fr::from(p.session),
        Fr::from(p.policy),
        Fr::from(p.rid)
    ];
    for (i, o) in batch.observations.iter().enumerate() {
        let v = o.values;
        if v[..4].iter().any(|x| *x >= 1 << 16) || v[4] >= 1 << 33 || v[5] >= 1 << 17 {
            return false;
        }
        let dx = v[0].abs_diff(v[2]);
        let dy = v[1].abs_diff(v[3]);
        let square = v[5] * v[5];
        let next = (v[5] + 1) * (v[5] + 1);
        if v[4] != dx * dx + dy * dy
            || square > v[4]
            || v[4] >= next
            || v[4] - square >= 1 << 18
            || next - v[4] - 1 >= 1 << 18
        {
            return false;
        }
        let fields = [
            DOMAIN,
            p.count as u64,
            p.session,
            p.policy,
            p.rid,
            i as u64,
            v[0],
            v[1],
            v[2],
            v[3],
            v[4],
            v[5],
        ]
        .map(Fr::from);
        let msg = hash.hash(&fields);
        if !signature_ok(&hash, p, &o.signature, msg) {
            return false;
        }
        aggregate.push(msg);
    }
    root == hash.hash(&aggregate)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn canonical_field_rejects_modulus() {
        let bytes = Fr::MODULUS.to_bytes_be();
        let mut p = [0; 32];
        p.copy_from_slice(&bytes);
        assert!(decode_field(&p).is_none());
        assert!(decode_field(&[255; 32]).is_none());
        assert_eq!(
            decode_field(&field_bytes(Fr::from(42u64))),
            Some(Fr::from(42u64))
        );
    }
    #[test]
    fn generator_and_subgroup_order() {
        let base = Point::affine(GX, GY).unwrap();
        assert!(!base.equals(Point::identity()));
        assert!(base.mul(&ORDER).equals(Point::identity()));
        assert!(base
            .add(base)
            .equals(base.mul(&field_bytes(Fr::from(2u64)))));
    }
}
