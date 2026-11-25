package draft

import (
	"crypto/rand"
	"encoding/json"
	"math/big"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/consensys/gnark-crypto/ecc"
	nativeed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

type countOnlyWriter struct{ n int }

func (w *countOnlyWriter) Write(p []byte) (int, error) { w.n += len(p); return len(p), nil }

// Explicit opt-in; all signer/setup/proof material remains in process memory.
// This is a disposable single-contributor synthetic setup, never release keys.
func TestSignedProof(t *testing.T) {
	if os.Getenv("DRAFT_RUN_PROOF") != "1" {
		t.Skip("opt-in single-proof test; preflight resources before enabling")
	}
	key, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	assignment := SignedCircuit{Observation: uncertainFixture(), RecordID: 1, ExpiresMS: 200000}
	signFixture(t, &assignment, key)
	start := time.Now()
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &SignedCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	compileMS := time.Since(start).Milliseconds()
	receipt := PublicReceipt{Session: big.NewInt(7), FrameID: big.NewInt(8), ClaimToken: big.NewInt(9), PolicyDigest: assignment.Observation.PolicyDigest.(*big.Int), Commitment: assignment.Observation.Commitment.(*big.Int), RecordID: big.NewInt(1), Key: key.PublicKey, ClaimTimeMS: 100000, ExpiresMS: 200000}
	expected := ExpectedContext{Session: big.NewInt(7), FrameID: big.NewInt(8), ClaimToken: big.NewInt(9), PolicyDigest: receipt.PolicyDigest, Observer: key.PublicKey, SessionStartMS: 90000, SessionEndMS: 250000}
	seen := map[string]bool{}
	if err := CheckAdmission(receipt, expected, 150000, seen); err != nil {
		t.Fatal(err)
	}
	start = time.Now()
	pk, vk, err := groth16.Setup(cs)
	if err != nil {
		t.Fatal(err)
	}
	setupMS := time.Since(start).Milliseconds()
	witness, err := frontend.NewWitness(&assignment, ecc.BN254.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	public, err := witness.Public()
	if err != nil {
		t.Fatal(err)
	}
	start = time.Now()
	proof, err := groth16.Prove(cs, pk, witness)
	if err != nil {
		t.Fatal(err)
	}
	proveMS := time.Since(start).Milliseconds()
	start = time.Now()
	verifiedReceipt, err := VerifySignedProof(proof, vk, public, expected, 150000, seen)
	if err != nil {
		t.Fatal(err)
	}
	if verifiedReceipt.Commitment.Cmp(receipt.Commitment) != 0 {
		t.Fatal("proof/receipt extraction mismatch")
	}
	verifyElapsed := time.Since(start)
	verifyMS := verifyElapsed.Milliseconds()
	// Replay state changes only AFTER verification. This map is a test fixture,
	// not a durable/atomic production admission store.
	seen[ReceiptReplayKey(receipt)] = true
	if _, err := VerifySignedProof(proof, vk, public, expected, 150000, seen); err == nil {
		t.Fatal("verified receipt replay accepted")
	}
	if _, err := VerifySignedProof(proof, vk, public, expected, 99999, nil); err == nil {
		t.Fatal("future claim accepted through joint verification")
	}
	for _, field := range []string{"status", "session", "commitment", "observer"} {
		t.Run("reject_changed_public_"+field, func(t *testing.T) {
			bad := assignment
			switch field {
			case "status":
				bad.Observation.Status = 1
			case "session":
				bad.Observation.Session = 8
			case "commitment":
				bad.Observation.Commitment = big.NewInt(1)
			case "observer":
				bad.ObserverKey.A.X = 1
			}
			w, err := frontend.NewWitness(&bad, ecc.BN254.ScalarField())
			if err != nil {
				t.Fatal(err)
			}
			p, err := w.Public()
			if err != nil {
				t.Fatal(err)
			}
			if _, err := VerifySignedProof(proof, vk, p, expected, 150000, map[string]bool{}); err == nil {
				t.Fatal("changed public input verified")
			}
		})
	}
	if t.Failed() {
		t.Fatal("proof checks failed; summary not written")
	}
	counter := countOnlyWriter{}
	if _, err := proof.WriteTo(&counter); err != nil {
		t.Fatal(err)
	}
	result := map[string]interface{}{"status": "EXECUTED_SYNTHETIC_JOINT_VERIFICATION", "curve": "BN254", "scheme": "Groth16 disposable single-contributor test setup", "constraints": cs.GetNbConstraints(), "proof_generated": true, "proof_verified": true, "receipt_extracted_from_public_witness": true, "changed_public_inputs_rejected": 4, "replay_preflight_rejected_after_verify": true, "compile_ms": compileMS, "setup_ms": setupMS, "prove_ms": proveMS, "verify_ms": verifyMS, "verify_us": verifyElapsed.Microseconds(), "joint_gate_rejected_future_claim": true, "proof_serialized_bytes_count_only": counter.n, "keys_or_proof_written_to_disk": false, "field_data_used": false, "recursive_path_executed": false, "evm_verification_executed": false}
	if p := os.Getenv("DRAFT_SUMMARY_PATH"); p != "" {
		b, _ := json.MarshalIndent(result, "", "  ")
		if err := os.WriteFile(filepath.Join(filepath.Dir(p), "signed-proof-summary.json"), append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}
