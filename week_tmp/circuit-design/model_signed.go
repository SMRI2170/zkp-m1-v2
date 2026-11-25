package draft

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math/big"
	"reflect"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	nativeed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	ted "github.com/consensys/gnark-crypto/ecc/twistededwards"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/schema"
	edcurve "github.com/consensys/gnark/std/algebra/native/twistededwards"
	"github.com/consensys/gnark/std/hash/mimc"
	"github.com/consensys/gnark/std/signature/eddsa"
)

const ModelStatementID = "frozen-log-2d-signed-v1-research-only"

// New statement: never use the old SignedCircuit VK for this structure.
type SignedModelCircuit struct {
	Core            CalibratedCircuit
	ObserverKey     eddsa.PublicKey   `gnark:",public"`
	RecordID        frontend.Variable `gnark:",public"`
	ClaimTimeMS     frontend.Variable `gnark:",public"`
	ExpiresMS       frontend.Variable `gnark:",public"`
	MaxAgeMS        frontend.Variable `gnark:",public"`
	StatementPolicy frontend.Variable `gnark:",public"`
	Nullifier       frontend.Variable `gnark:",public"`
	ObservedTimeMS  frontend.Variable
	ClockErrorMS    frontend.Variable
	TimeKnown       frontend.Variable
	HorizontalKnown frontend.Variable
	SourceDigest    [2]frontend.Variable
	Signature       eddsa.Signature
}

func (c *SignedModelCircuit) Define(api frontend.API) error {
	if err := c.Core.Define(api); err != nil {
		return err
	}
	bounded(api, c.RecordID, 128)
	api.AssertIsDifferent(c.RecordID, 0)
	for _, v := range []frontend.Variable{c.ClaimTimeMS, c.ObservedTimeMS, c.ExpiresMS} {
		bounded(api, v, 48)
	}
	bounded(api, c.ClockErrorMS, 32)
	bounded(api, c.MaxAgeMS, 32)
	api.AssertIsBoolean(c.TimeKnown)
	api.AssertIsBoolean(c.HorizontalKnown)
	for _, v := range c.SourceDigest {
		bounded(api, v, 128)
	}
	api.AssertIsDifferent(api.Add(c.SourceDigest[0], c.SourceDigest[1]), 0)
	age := api.Add(absDifference(api, c.ClaimTimeMS, c.ObservedTimeMS), c.ClockErrorMS)
	api.AssertIsEqual(c.Core.Eligible, api.Mul(c.TimeKnown, c.HorizontalKnown, api.Sub(1, less(api, c.MaxAgeMS, age))))
	api.AssertIsLessOrEqual(c.ClaimTimeMS, c.ExpiresMS)
	api.AssertIsLessOrEqual(c.ObservedTimeMS, c.ExpiresMS)
	curve, err := edcurve.NewEdCurve(api, ted.BN254)
	if err != nil {
		return err
	}
	assertPrimeNonIdentity(curve, c.ObserverKey.A)
	assertPrimeNonIdentity(curve, c.Signature.R)
	h, err := mimc.NewMiMC(api)
	if err != nil {
		return err
	}
	h.Write(3207001, c.Core.PolicyDigest, c.MaxAgeMS)
	api.AssertIsEqual(c.StatementPolicy, h.Sum())
	h.Reset()
	h.Write(3207002, c.ObserverKey.A.X, c.ObserverKey.A.Y, c.Core.Session, c.SourceDigest[0], c.SourceDigest[1])
	api.AssertIsEqual(c.Nullifier, h.Sum())
	h.Reset()
	h.Write(3207003, c.Core.Commitment, c.ObserverKey.A.X, c.ObserverKey.A.Y, c.RecordID, c.ClaimTimeMS, c.ExpiresMS, c.StatementPolicy, c.ObservedTimeMS, c.ClockErrorMS, c.TimeKnown, c.HorizontalKnown, c.SourceDigest[0], c.SourceDigest[1], c.Nullifier)
	message := h.Sum()
	h.Reset()
	return eddsa.Verify(curve, c.Signature, message, c.ObserverKey, &h)
}

// CanonicalSource identifies a recorded API observation, NOT a physical RF frame.
// Source declarations remain an observer trust boundary; changing the source
// declaration can evade deduplication if the authorized observer is dishonest.
func CanonicalSource(run, boot string, observedUS uint64, rawIE []byte) ([2]*big.Int, error) {
	var out [2]*big.Int
	if run == "" || boot == "" || observedUS == 0 || len(rawIE) == 0 || len(rawIE) > 4096 {
		return out, fmt.Errorf("source identity incomplete")
	}
	rawHash := sha256.Sum256(rawIE)
	b, _ := json.Marshal([]any{"recorded-api-observation-v1", run, boot, observedUS, fmt.Sprintf("%x", rawHash)})
	sum := sha256.Sum256(b)
	out[0] = new(big.Int).SetBytes(sum[:16])
	out[1] = new(big.Int).SetBytes(sum[16:])
	return out, nil
}
func ModelSignatureMessage(c *SignedModelCircuit, key nativeed.PublicKey, record, claim, expiry, maxAge, observed, clock uint64, timeKnown, horizontalKnown bool, source [2]*big.Int) ([]byte, error) {
	if source[0] == nil || source[1] == nil || source[0].Sign() < 0 || source[1].Sign() < 0 || source[0].BitLen() > 128 || source[1].BitLen() > 128 {
		return nil, fmt.Errorf("source digest invalid")
	}
	commitment, ok := c.Core.Commitment.(*big.Int)
	if !ok || !canonical(commitment) {
		return nil, fmt.Errorf("canonical commitment required")
	}
	corePolicy, ok := c.Core.PolicyDigest.(*big.Int)
	if !ok || !canonical(corePolicy) {
		return nil, fmt.Errorf("canonical profile required")
	}
	x, y := new(big.Int), new(big.Int)
	key.A.X.BigInt(x)
	key.A.Y.BigInt(y)
	policy, err := FieldHash(big.NewInt(3207001), corePolicy, new(big.Int).SetUint64(maxAge))
	if err != nil {
		return nil, err
	}
	session, ok := c.Core.Session.(*big.Int)
	if !ok {
		return nil, fmt.Errorf("canonical context required")
	}
	nullifier, err := FieldHash(big.NewInt(3207002), x, y, session, source[0], source[1])
	if err != nil {
		return nil, err
	}
	c.ObserverKey.Assign(ted.BN254, key.Bytes())
	c.RecordID = record
	c.ClaimTimeMS = claim
	c.ExpiresMS = expiry
	c.MaxAgeMS = maxAge
	c.StatementPolicy = policy
	c.Nullifier = nullifier
	c.ObservedTimeMS = observed
	c.ClockErrorMS = clock
	c.TimeKnown = flag(timeKnown)
	c.HorizontalKnown = flag(horizontalKnown)
	c.SourceDigest = [2]frontend.Variable{source[0], source[1]}
	values := []*big.Int{big.NewInt(3207003), commitment, x, y, new(big.Int).SetUint64(record), new(big.Int).SetUint64(claim), new(big.Int).SetUint64(expiry), policy, new(big.Int).SetUint64(observed), new(big.Int).SetUint64(clock), new(big.Int).SetUint64(flag(timeKnown)), new(big.Int).SetUint64(flag(horizontalKnown)), source[0], source[1], nullifier}
	digest, err := FieldHash(values...)
	if err != nil {
		return nil, err
	}
	return digest.FillBytes(make([]byte, 32)), nil
}

type ModelContext struct {
	ExpectedContext
	AllowResearchProfile bool
}
type verifiedModelReceipt struct {
	receipt   PublicReceipt
	nullifier string
	verified  bool
}

func decodeModel(public witness.Witness) (SignedModelCircuit, witness.Witness, error) {
	var c SignedModelCircuit
	if public == nil {
		return c, nil, fmt.Errorf("public witness missing")
	}
	src, ok := public.Vector().(fr.Vector)
	if !ok {
		return c, nil, fmt.Errorf("BN254 public witness required")
	}
	p, err := public.Public()
	if err != nil {
		return c, nil, err
	}
	pv, ok := p.Vector().(fr.Vector)
	if !ok || len(pv) != len(src) {
		return c, nil, fmt.Errorf("private elements supplied")
	}
	vec := append(fr.Vector(nil), src...)
	leaf := reflect.TypeOf((*frontend.Variable)(nil)).Elem()
	count, err := schema.Walk(ecc.BN254.ScalarField(), &c, leaf, nil)
	if err != nil || count.Public != len(vec) {
		return c, nil, fmt.Errorf("statement/schema mismatch")
	}
	i := 0
	_, err = schema.Walk(ecc.BN254.ScalarField(), &c, leaf, func(l schema.LeafInfo, v reflect.Value) error {
		if l.Visibility == schema.Public {
			z := new(big.Int)
			vec[i].BigInt(z)
			v.Set(reflect.ValueOf(z))
			i++
		}
		return nil
	})
	if err != nil {
		return c, nil, err
	}
	snapshot, err := frontend.NewWitness(&c, ecc.BN254.ScalarField(), frontend.PublicOnly())
	return c, snapshot, err
}

// VerifyModelProof returns an opaque internal verification token, never an
// unverified caller receipt. It is research-only until model adoption exists.
func VerifyModelProof(proof groth16.Proof, vk groth16.VerifyingKey, public witness.Witness, e ModelContext, now uint64) (verifiedModelReceipt, error) {
	var zero verifiedModelReceipt
	if !e.AllowResearchProfile {
		return zero, fmt.Errorf("unadopted model: explicit research-only opt-in required")
	}
	if proof == nil || vk == nil || proof.CurveID() != ecc.BN254 || vk.CurveID() != ecc.BN254 {
		return zero, fmt.Errorf("proof/key unavailable or wrong curve")
	}
	c, snapshot, err := decodeModel(public)
	if err != nil {
		return zero, err
	}
	if vk.NbPublicWitness() != len(snapshot.Vector().(fr.Vector)) {
		return zero, fmt.Errorf("VK schema mismatch")
	}
	profile, err := FrozenEnvelope()
	if err != nil {
		return zero, err
	}
	digest, err := profile.Digest()
	if err != nil {
		return zero, err
	}
	if c.Core.PolicyDigest.(*big.Int).Cmp(digest) != 0 {
		return zero, fmt.Errorf("unrecognized model profile")
	}
	scalar := func(v frontend.Variable) *big.Int { return new(big.Int).Set(v.(*big.Int)) }
	var r PublicReceipt
	r.Session = scalar(c.Core.Session)
	r.FrameID = scalar(c.Core.FrameID)
	r.ClaimToken = scalar(c.Core.ClaimToken)
	r.PolicyDigest = scalar(c.StatementPolicy)
	r.Commitment = scalar(c.Core.Commitment)
	r.RecordID = scalar(c.RecordID)
	ct, ex := scalar(c.ClaimTimeMS), scalar(c.ExpiresMS)
	if ct.BitLen() > 48 || ex.BitLen() > 48 {
		return zero, fmt.Errorf("time range")
	}
	r.ClaimTimeMS = ct.Uint64()
	r.ExpiresMS = ex.Uint64()
	r.Key.A.X.SetBigInt(scalar(c.ObserverKey.A.X))
	r.Key.A.Y.SetBigInt(scalar(c.ObserverKey.A.Y))
	if err = CheckAdmission(r, e.ExpectedContext, now, nil); err != nil {
		return zero, err
	}
	if err = groth16.Verify(proof, vk, snapshot); err != nil {
		return zero, fmt.Errorf("proof verification failed")
	}
	return verifiedModelReceipt{r, scalar(c.Nullifier).String(), true}, nil
}
