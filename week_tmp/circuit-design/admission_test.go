package draft

import (
	"crypto/rand"
	nativeed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	"math/big"
	"testing"
)

func TestAdmission(t *testing.T) {
	key, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	other, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	e := ExpectedContext{Session: big.NewInt(7), FrameID: big.NewInt(8), ClaimToken: big.NewInt(9), PolicyDigest: big.NewInt(10), Observer: key.PublicKey, SessionStartMS: 90000, SessionEndMS: 200000}
	base := PublicReceipt{Session: big.NewInt(7), FrameID: big.NewInt(8), ClaimToken: big.NewInt(9), PolicyDigest: big.NewInt(10), Commitment: big.NewInt(11), RecordID: big.NewInt(12), Key: key.PublicKey, ClaimTimeMS: 100000, ExpiresMS: 180000}
	cases := []struct {
		name  string
		valid bool
		fn    func(*PublicReceipt, *ExpectedContext, *uint64, map[string]bool)
	}{
		{"expected_context", true, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) {}},
		{"unknown_session", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { r.Session = big.NewInt(99) }},
		{"unknown_frame", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { r.FrameID = big.NewInt(99) }},
		{"different_claim", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) {
			r.ClaimToken = big.NewInt(99)
		}},
		{"unapproved_model", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) {
			r.PolicyDigest = big.NewInt(99)
		}},
		{"unknown_observer", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { r.Key = other.PublicKey }},
		{"identity_key", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) {
			r.Key.A.X.SetZero()
			r.Key.A.Y.SetOne()
		}},
		{"expired", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { *n = 180001 }},
		{"future_session", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { *n = 89999 }},
		{"session_ended", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { *n = 200001 }},
		{"expiry_outside_session", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { r.ExpiresMS = 200001 }},
		{"claim_before_session", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { r.ClaimTimeMS = 89999 }},
		{"claim_after_expiry", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { r.ClaimTimeMS = 180001 }},
		{"duplicate_receipt", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) {
			s[ReceiptReplayKey(*r)] = true
		}},
		{"new_commitment_not_replay_escape", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) {
			s[ReceiptReplayKey(*r)] = true
			r.Commitment = big.NewInt(999)
		}},
		{"nil_record_id", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { r.RecordID = nil }},
		{"oversized_record_id", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) {
			r.RecordID = new(big.Int).Lsh(big.NewInt(1), 128)
		}},
		{"nil_commitment", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { r.Commitment = nil }},
		{"nil_context", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { e.Session = nil }},
		{"session_interval_reversed", false, func(r *PublicReceipt, e *ExpectedContext, n *uint64, s map[string]bool) { e.SessionEndMS = 1 }},
	}
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			r, e2, n, seen := base, e, uint64(150000), map[string]bool{}
			tt.fn(&r, &e2, &n, seen)
			count := len(seen)
			err := CheckAdmission(r, e2, n, seen)
			if (err == nil) != tt.valid {
				t.Fatalf("want valid=%v err=%v", tt.valid, err)
			}
			if len(seen) != count {
				t.Fatal("preflight mutated replay state before proof verification")
			}
		})
	}
}
func TestSignatureMessageCanonical(t *testing.T) {
	k, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := SignatureMessage(nil, k.PublicKey, big.NewInt(1), 100); err == nil {
		t.Fatal("nil accepted")
	}
	if _, err := SignatureMessage(big.NewInt(-1), k.PublicKey, big.NewInt(1), 100); err == nil {
		t.Fatal("negative accepted")
	}
}
