package draft

import (
	"fmt"
	"math/big"
	"reflect"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/schema"
)

// DecodeSignedPublic snapshots a public-only BN254 witness, mapping fields by
// SignedCircuit schema, not caller JSON or manually maintained vector indexes.
// It does not authenticate this data until VerifySignedProof completes.
func DecodeSignedPublic(public witness.Witness) (SignedCircuit, witness.Witness, error) {
	var out SignedCircuit
	if public == nil {
		return out, nil, fmt.Errorf("public witness missing")
	}
	source, ok := public.Vector().(fr.Vector)
	if !ok {
		return out, nil, fmt.Errorf("expected BN254 public witness")
	}
	// A same-length vector can still declare secret elements in its header.
	declaredPublic, err := public.Public()
	if err != nil {
		return out, nil, fmt.Errorf("invalid public witness metadata: %w", err)
	}
	declaredVector, ok := declaredPublic.Vector().(fr.Vector)
	if !ok || len(declaredVector) != len(source) {
		return out, nil, fmt.Errorf("secret elements in public witness")
	}
	vector := append(fr.Vector(nil), source...)
	count, err := schema.Walk(ecc.BN254.ScalarField(), &out, reflect.TypeOf((*frontend.Variable)(nil)).Elem(), nil)
	if err != nil {
		return out, nil, err
	}
	if len(vector) != count.Public {
		return out, nil, fmt.Errorf("expected public-only witness with %d elements", count.Public)
	}
	i := 0
	_, err = schema.Walk(ecc.BN254.ScalarField(), &out, reflect.TypeOf((*frontend.Variable)(nil)).Elem(), func(leaf schema.LeafInfo, value reflect.Value) error {
		if leaf.Visibility == schema.Public {
			z := new(big.Int)
			vector[i].BigInt(z)
			value.Set(reflect.ValueOf(z))
			i++
		}
		return nil
	})
	if err != nil {
		return out, nil, err
	}
	snapshot, err := frontend.NewWitness(&out, ecc.BN254.ScalarField(), frontend.PublicOnly())
	return out, snapshot, err
}
func ReceiptFromSignedPublic(c SignedCircuit) (PublicReceipt, error) {
	var r PublicReceipt
	scalar := func(v frontend.Variable) (*big.Int, error) {
		n, ok := v.(*big.Int)
		if !ok || !canonical(n) {
			return nil, fmt.Errorf("decoded canonical scalar expected")
		}
		return new(big.Int).Set(n), nil
	}
	var err error
	fields := []struct {
		from frontend.Variable
		to   **big.Int
	}{{c.Observation.Session, &r.Session}, {c.Observation.FrameID, &r.FrameID}, {c.Observation.ClaimToken, &r.ClaimToken}, {c.Observation.PolicyDigest, &r.PolicyDigest}, {c.Observation.Commitment, &r.Commitment}, {c.RecordID, &r.RecordID}}
	for _, f := range fields {
		*f.to, err = scalar(f.from)
		if err != nil {
			return r, err
		}
	}
	ct, err := scalar(c.Observation.ClaimTimeMS)
	if err != nil || ct.BitLen() > 48 {
		return r, fmt.Errorf("claim time range")
	}
	r.ClaimTimeMS = ct.Uint64()
	ex, err := scalar(c.ExpiresMS)
	if err != nil || ex.BitLen() > 48 {
		return r, fmt.Errorf("expiry range")
	}
	r.ExpiresMS = ex.Uint64()
	x, err := scalar(c.ObserverKey.A.X)
	if err != nil {
		return r, err
	}
	y, err := scalar(c.ObserverKey.A.Y)
	if err != nil {
		return r, err
	}
	r.Key.A.X.SetBigInt(x)
	r.Key.A.Y.SetBigInt(y)
	return r, nil
}

// VerifySignedProof has NO caller-supplied PublicReceipt argument. vk and e must
// come from trusted, version-pinned verifier configuration, not the request.
// Returns only after both context admission and actual proof verification pass.
// Does not persist receipt or solve atomic/concurrent replay admission.
func VerifySignedProof(proof groth16.Proof, vk groth16.VerifyingKey, public witness.Witness, e ExpectedContext, nowMS uint64, alreadyAccepted map[string]bool) (PublicReceipt, error) {
	var zero PublicReceipt
	if proof == nil || vk == nil {
		return zero, fmt.Errorf("proof/key missing")
	}
	c, snapshot, err := DecodeSignedPublic(public)
	if err != nil {
		return zero, err
	}
	if vk.CurveID() != ecc.BN254 || proof.CurveID() != ecc.BN254 {
		return zero, fmt.Errorf("unexpected proof curve")
	}
	vector := snapshot.Vector().(fr.Vector)
	if vk.NbPublicWitness() != len(vector) {
		return zero, fmt.Errorf("unexpected verification key schema")
	}
	r, err := ReceiptFromSignedPublic(c)
	if err != nil {
		return zero, err
	}
	if err = CheckAdmission(r, e, nowMS, alreadyAccepted); err != nil {
		return zero, err
	}
	if err = groth16.Verify(proof, vk, snapshot); err != nil {
		return zero, fmt.Errorf("proof verification failed: %w", err)
	}
	return r, nil
}
