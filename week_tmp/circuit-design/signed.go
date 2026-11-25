package draft

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark-crypto/ecc"
	native "github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
	nativeed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	ted "github.com/consensys/gnark-crypto/ecc/twistededwards"
	"github.com/consensys/gnark/frontend"
	edcurve "github.com/consensys/gnark/std/algebra/native/twistededwards"
	"github.com/consensys/gnark/std/hash/mimc"
	"github.com/consensys/gnark/std/signature/eddsa"
)

const SignedDomain = 3203001

// SignedCircuit adds an observation-author signature to the uncertain statement.
// This does NOT register the key or establish sensor truth. Admission checks for
// key, policy, session, expiry, replay must accompany actual proof verification.
type SignedCircuit struct {
	Observation UncertaintyCircuit
	ObserverKey eddsa.PublicKey   `gnark:",public"`
	RecordID    frontend.Variable `gnark:",public"` // per-observer session-scoped receipt ID, not a physical RF packet ID
	ExpiresMS   frontend.Variable `gnark:",public"`
	Signature   eddsa.Signature
}

// Generic constant-order multiplication deliberately uses only Add/Double:
// optimized ScalarMul assumes subgroup membership and cannot prove its own precondition.
func assertPrimeNonIdentity(curve edcurve.Curve, p edcurve.Point) {
	api := curve.API()
	curve.AssertIsOnCurve(p)
	identity := api.Mul(api.IsZero(p.X), api.IsZero(api.Sub(p.Y, 1)))
	api.AssertIsEqual(identity, 0)
	q := edcurve.Point{X: 0, Y: 1}
	order := curve.Params().Order
	for i := order.BitLen() - 1; i >= 0; i-- {
		q = curve.Double(q)
		if order.Bit(i) == 1 {
			q = curve.Add(q, p)
		}
	}
	api.AssertIsEqual(q.X, 0)
	api.AssertIsEqual(q.Y, 1)
}

func (c *SignedCircuit) Define(api frontend.API) error {
	if err := c.Observation.Define(api); err != nil {
		return err
	}
	bounded(api, c.RecordID, 128)
	api.AssertIsDifferent(c.RecordID, 0)
	bounded(api, c.ExpiresMS, 48)
	api.AssertIsLessOrEqual(c.Observation.ClaimTimeMS, c.ExpiresMS)
	api.AssertIsLessOrEqual(c.Observation.ObservedTimeMS, c.ExpiresMS)
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
	h.Write(SignedDomain, c.Observation.Commitment, c.ObserverKey.A.X, c.ObserverKey.A.Y, c.RecordID, c.ExpiresMS)
	message := h.Sum()
	h.Reset()
	return eddsa.Verify(curve, c.Signature, message, c.ObserverKey, &h)
}

// SignatureMessage is canonical field-element hashing, not arbitrary JSON.
// All fields must already be normalized and bound by Observation.Commitment.
func SignatureMessage(commitment *big.Int, key nativeed.PublicKey, recordID *big.Int, expiresMS uint64) ([]byte, error) {
	x := new(big.Int)
	y := new(big.Int)
	key.A.X.BigInt(x)
	key.A.Y.BigInt(y)
	values := []*big.Int{big.NewInt(SignedDomain), commitment, x, y, recordID, new(big.Int).SetUint64(expiresMS)}
	h := native.NewMiMC()
	for _, v := range values {
		if v == nil || v.Sign() < 0 || v.Cmp(ecc.BN254.ScalarField()) >= 0 {
			return nil, fmt.Errorf("noncanonical field input")
		}
		b := v.FillBytes(make([]byte, 32))
		if _, err := h.Write(b); err != nil {
			return nil, err
		}
	}
	return h.Sum(nil), nil
}

// PublicReceipt is the public statement supplied alongside proof verification.
// These preflight checks never verify a proof or append to a replay ledger.
type PublicReceipt struct {
	Session, FrameID, ClaimToken, PolicyDigest, Commitment, RecordID *big.Int
	Key                                                              nativeed.PublicKey
	ClaimTimeMS, ExpiresMS                                           uint64
}
type ExpectedContext struct {
	Session, FrameID, ClaimToken, PolicyDigest *big.Int
	Observer                                   nativeed.PublicKey
	SessionStartMS, SessionEndMS               uint64
	MaxFutureSkewMS                            uint64
}

func canonical(v *big.Int) bool {
	return v != nil && v.Sign() >= 0 && v.Cmp(ecc.BN254.ScalarField()) < 0
}
func equal(a, b *big.Int) bool { return canonical(a) && canonical(b) && a.Cmp(b) == 0 }

// ReceiptReplayKey excludes policy/claim/commitment: changing those must not
// allow reusing the same observer's receipt ID within the same session.
func ReceiptReplayKey(r PublicReceipt) string {
	return fmt.Sprintf("%x/%s/%s", r.Key.Bytes(), r.Session.String(), r.RecordID.String())
}
func CheckAdmission(r PublicReceipt, e ExpectedContext, nowMS uint64, alreadyAccepted map[string]bool) error {
	if !equal(r.Session, e.Session) || !equal(r.FrameID, e.FrameID) || !equal(r.ClaimToken, e.ClaimToken) || !equal(r.PolicyDigest, e.PolicyDigest) {
		return fmt.Errorf("unexpected context or unapproved policy")
	}
	if !canonical(r.Commitment) || r.RecordID == nil || r.RecordID.Sign() <= 0 || r.RecordID.BitLen() > 128 {
		return fmt.Errorf("invalid receipt identity")
	}
	if !r.Key.A.IsOnCurve() || r.Key.A.IsZero() || !r.Key.A.IsInSubGroup() || !e.Observer.A.IsOnCurve() || e.Observer.A.IsZero() || !e.Observer.A.IsInSubGroup() {
		return fmt.Errorf("invalid observer key")
	}
	if !r.Key.Equal(&e.Observer) {
		return fmt.Errorf("observer not admitted")
	}
	if e.SessionStartMS > e.SessionEndMS || e.SessionEndMS >= 1<<48 || nowMS < e.SessionStartMS || nowMS > e.SessionEndMS || nowMS > r.ExpiresMS || r.ExpiresMS > e.SessionEndMS || r.ClaimTimeMS < e.SessionStartMS || r.ClaimTimeMS > r.ExpiresMS {
		return fmt.Errorf("outside session or expired")
	}
	if e.MaxFutureSkewMS >= 1<<32 || (r.ClaimTimeMS > nowMS && r.ClaimTimeMS-nowMS > e.MaxFutureSkewMS) {
		return fmt.Errorf("claim too far in future or invalid future-skew policy")
	}
	if alreadyAccepted[ReceiptReplayKey(r)] {
		return fmt.Errorf("receipt already accepted")
	}
	return nil
}
