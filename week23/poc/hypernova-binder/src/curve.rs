//! BN254 G1 homogeneous complete addition, over emulated Fq in Fr.
//! Formula matches ark-r1cs-std 0.6's RCB Algorithm 1 (a=0, b=3).
use ark_bn254::{Fq, Fr, G1Projective};
use ark_ec::{AffineRepr, CurveGroup};
use ark_r1cs_std::{
    alloc::AllocVar,
    boolean::Boolean,
    eq::EqGadget,
    fields::{FieldVar, emulated_fp::EmulatedFpVar},
};
use ark_relations::gr1cs::{ConstraintSystemRef, SynthesisError};
type F = EmulatedFpVar<Fq, Fr>;
#[derive(Clone)]
pub struct Point {
    pub x: F,
    pub y: F,
    pub z: F,
}
impl Point {
    pub fn alloc(cs: ConstraintSystemRef<Fr>, p: G1Projective) -> Result<Self, SynthesisError> {
        let affine = p.into_affine();
        let (x, y) = affine.xy().unwrap_or_default();
        let x = F::new_witness(cs.clone(), || Ok(x))?;
        let y = F::new_witness(cs, || Ok(y))?;
        let infinity = x.is_zero()? & y.is_zero()?;
        let z = infinity.select(&F::zero(), &F::one())?;
        let yy = infinity.select(&F::one(), &y)?;
        // y^2*z = x^3 + 3*z^3, cofactor=1 for BN254 G1.
        (&yy * &yy * &z).enforce_equal(&(&x * &x * &x + &z * &z * &z * Fq::from(3)))?;
        Ok(Self { x, y: yy, z })
    }
    pub fn zero() -> Self {
        Self {
            x: F::zero(),
            y: F::one(),
            z: F::zero(),
        }
    }
    pub fn add(&self, b: &Self) -> Self {
        let xx = &self.x * &b.x;
        let yy = &self.y * &b.y;
        let zz = &self.z * &b.z;
        let xy = (&self.x + &self.y) * (&b.x + &b.y) - (&xx + &yy);
        let xz = (&self.x + &self.z) * (&b.x + &b.z) - (&xx + &zz);
        let yz = (&self.y + &self.z) * (&b.y + &b.z) - (&yy + &zz);
        let bz = &zz * Fq::from(9);
        let minus = &yy - &bz;
        let plus = &yy + &bz;
        let xx3 = &xx + &xx + &xx;
        let bxz = &xz * Fq::from(9);
        Self {
            x: &minus * &xy - &yz * &bxz,
            y: &plus * &minus + &xx3 * &bxz,
            z: &plus * &yz + &xy * &xx3,
        }
    }
    pub fn select(c: &Boolean<Fr>, a: &Self, b: &Self) -> Result<Self, SynthesisError> {
        Ok(Self {
            x: c.select(&a.x, &b.x)?,
            y: c.select(&a.y, &b.y)?,
            z: c.select(&a.z, &b.z)?,
        })
    }
    pub fn mul_bits(&self, bits: &[Boolean<Fr>]) -> Result<Self, SynthesisError> {
        let mut q = Self::zero();
        for bit in bits.iter().rev() {
            q = q.add(&q);
            let plus = q.add(self);
            q = Self::select(bit, &plus, &q)?;
        }
        Ok(q)
    }
    pub fn enforce_equal(&self, b: &Self) -> Result<(), SynthesisError> {
        self.z.is_zero()?.enforce_equal(&b.z.is_zero()?)?;
        (&self.x * &b.z).enforce_equal(&(&b.x * &self.z))?;
        (&self.y * &b.z).enforce_equal(&(&b.y * &self.z))
    }
    pub fn affine_xy(&self) -> Result<(F, F), SynthesisError> {
        let inf = self.z.is_zero()?;
        let denom = inf.select(&F::one(), &self.z)?;
        let inverse = denom.inverse()?;
        Ok((
            inf.select(&F::zero(), &(&self.x * &inverse))?,
            inf.select(&F::zero(), &(&self.y * &inverse))?,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ark_ec::PrimeGroup;
    use ark_ff::Zero;
    use ark_relations::gr1cs::ConstraintSystem;
    #[test]
    fn complete_group_edges_match_native() -> Result<(), SynthesisError> {
        let g = G1Projective::generator();
        let zero = G1Projective::zero();
        for (a, b) in [
            (zero, zero),
            (zero, g),
            (g, zero),
            (g, g),
            (g, -g),
            (g * Fr::from(7), g * Fr::from(19)),
        ] {
            let cs = ConstraintSystem::<Fr>::new_ref();
            let pa = Point::alloc(cs.clone(), a)?;
            let pb = Point::alloc(cs.clone(), b)?;
            let expected = Point::alloc(cs.clone(), a + b)?;
            pa.add(&pb).enforce_equal(&expected)?;
            assert!(cs.is_satisfied()?);
        }
        Ok(())
    }
    #[test]
    fn scalar_edges_match_native() -> Result<(), SynthesisError> {
        let g = G1Projective::generator();
        for scalar in [0u64, 1, 2, 17, 31] {
            let cs = ConstraintSystem::<Fr>::new_ref();
            let p = Point::alloc(cs.clone(), g)?;
            let bits = (0..5)
                .map(|i| Boolean::constant((scalar >> i) & 1 == 1))
                .collect::<Vec<_>>();
            let expected = Point::alloc(cs.clone(), g * Fr::from(scalar))?;
            p.mul_bits(&bits)?.enforce_equal(&expected)?;
            assert!(cs.is_satisfied()?);
        }
        Ok(())
    }
    #[test]
    fn wrong_sum_and_off_curve_are_unsatisfied() -> Result<(), SynthesisError> {
        let g = G1Projective::generator();
        let cs = ConstraintSystem::<Fr>::new_ref();
        let p = Point::alloc(cs.clone(), g)?;
        let wrong = Point::alloc(cs.clone(), g * Fr::from(3))?;
        p.add(&p).enforce_equal(&wrong)?;
        assert!(!cs.is_satisfied()?);
        let cs = ConstraintSystem::<Fr>::new_ref();
        let bad = G1Projective::new_unchecked(Fq::from(1), Fq::from(1), Fq::from(1));
        Point::alloc(cs.clone(), bad)?;
        assert!(!cs.is_satisfied()?);
        Ok(())
    }
}
