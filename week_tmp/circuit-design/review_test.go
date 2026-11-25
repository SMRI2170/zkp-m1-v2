package draft

// Diagnostic probes for evaluation. A reproduced limitation is not a security
// success: these tests intentionally record what current preflight permits.
import (
	"crypto/rand"
	"encoding/json"
	"github.com/consensys/gnark-crypto/ecc"
	nativeed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	"github.com/consensys/gnark/frontend"
	"math/big"
	"os"
	"path/filepath"
	"testing"
)

func reviewContext(t *testing.T) (PublicReceipt, ExpectedContext) {
	t.Helper()
	k, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	r := PublicReceipt{Session: big.NewInt(7), FrameID: big.NewInt(8), ClaimToken: big.NewInt(9), PolicyDigest: big.NewInt(10), Commitment: big.NewInt(11), RecordID: big.NewInt(1), Key: k.PublicKey, ClaimTimeMS: 100000, ExpiresMS: 180000}
	e := ExpectedContext{Session: r.Session, FrameID: r.FrameID, ClaimToken: r.ClaimToken, PolicyDigest: r.PolicyDigest, Observer: r.Key, SessionStartMS: 90000, SessionEndMS: 200000}
	return r, e
}
func TestReviewAdmissionBoundaries(t *testing.T) {
	// Regression: future claims beyond the verifier policy are now rejected.
	r, e := reviewContext(t)
	r.ClaimTimeMS = 170000
	futureAccepted := CheckAdmission(r, e, 150000, nil) == nil
	if futureAccepted {
		t.Fatal("future claim accepted despite zero future-skew policy")
	}
	// The replay namespace is receipt-based. A new ID requires a NEW signature,
	// but preflight alone cannot identify the same physical observation twice.
	r, e = reviewContext(t)
	seen := map[string]bool{ReceiptReplayKey(r): true}
	r.RecordID = big.NewInt(2)
	changedIDAccepted := CheckAdmission(r, e, 150000, seen) == nil
	if !changedIDAccepted {
		t.Fatal("diagnostic changed: update review; record identity behavior changed")
	}
	// Independent receipt objects are not cryptographically tied to a proof by
	// this preflight API; its docs require trusted extraction from public witness.
	r, e = reviewContext(t)
	r.Commitment = big.NewInt(999)
	independentReceiptAccepted := CheckAdmission(r, e, 150000, nil) == nil
	if !independentReceiptAccepted {
		t.Fatal("diagnostic changed: review commitment binding")
	}
	if p := os.Getenv("DRAFT_SUMMARY_PATH"); p != "" {
		b, _ := json.MarshalIndent(map[string]interface{}{"scope": "preflight diagnostics; no proof/signature forgery", "future_claim_relative_to_now_accepted": futureAccepted, "new_record_id_not_detected_as_same_observation": changedIDAccepted, "independent_public_receipt_requires_external_proof_binding": independentReceiptAccepted, "security_findings_resolved": false}, "", "  ")
		if err := os.WriteFile(filepath.Join(filepath.Dir(p), "review-findings.json"), append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}
func TestReviewPublicInputSize(t *testing.T) {
	key, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	c := SignedCircuit{Observation: uncertainFixture(), RecordID: 1, ExpiresMS: 200000}
	signFixture(t, &c, key)
	w, err := frontend.NewWitness(&c, ecc.BN254.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	pub, err := w.Public()
	if err != nil {
		t.Fatal(err)
	}
	count := countOnlyWriter{}
	if _, err := pub.WriteTo(&count); err != nil {
		t.Fatal(err)
	}
	if p := os.Getenv("DRAFT_SUMMARY_PATH"); p != "" {
		b, _ := json.MarshalIndent(map[string]interface{}{"public_witness_serialized_bytes_count_only": count.n, "scope": "gnark public witness encoding; excludes proof, protocol envelope and network overhead", "public_witness_persisted": false}, "", "  ")
		if err := os.WriteFile(filepath.Join(filepath.Dir(p), "review-public-input-cost.json"), append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}
