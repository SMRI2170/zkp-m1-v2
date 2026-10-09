package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	groth16 "github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

type proofCacheTestCircuit struct {
	Public frontend.Variable `gnark:",public"`
	Secret frontend.Variable
}

func (c *proofCacheTestCircuit) Define(api frontend.API) error {
	api.AssertIsEqual(api.Mul(c.Secret, c.Secret), c.Public)
	return nil
}

func TestProofCacheBindsAssignmentAndVerifiesSerializedProof(t *testing.T) {
	ccs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &proofCacheTestCircuit{})
	if err != nil {
		t.Fatalf("compile proof-cache test circuit: %v", err)
	}
	pk, vk, err := groth16.Setup(ccs)
	if err != nil {
		t.Fatalf("setup proof-cache test circuit: %v", err)
	}
	constraintHash, err := fileHashFromWriter(ccs)
	if err != nil {
		t.Fatalf("hash proof-cache test circuit: %v", err)
	}
	vkHash, err := fileHashFromWriter(vk)
	if err != nil {
		t.Fatalf("hash proof-cache test VK: %v", err)
	}
	stage := stageArtifacts{
		CCS: ccs, PK: pk, VK: vk, Dir: t.TempDir(),
		Meta: stageMetadata{
			Stage: "proof-cache-test", Curve: curveName(ecc.BN254),
			SourceHash: "source-fixture", ConstraintHash: constraintHash, VerifyingKeyHash: vkHash,
		},
	}
	artifactDir := t.TempDir()
	assignment := &proofCacheTestCircuit{Public: 1, Secret: 1}
	proof1, public1, err := proveAndVerifyCached(artifactDir, "tiny-inner-proof", stage, assignment, ecc.BN254, ecc.BN254, false)
	if err != nil {
		t.Fatalf("create and cache proof: %v", err)
	}
	proof2, public2, err := proveAndVerifyCached(artifactDir, "tiny-inner-proof", stage, assignment, ecc.BN254, ecc.BN254, false)
	if err != nil {
		t.Fatalf("load verified proof cache: %v", err)
	}
	proof1Bytes, proof2Bytes := serializeProofForTest(t, proof1), serializeProofForTest(t, proof2)
	if !bytes.Equal(proof1Bytes, proof2Bytes) {
		t.Fatal("repeated assignment did not reuse the stored proof")
	}
	public1Hash, err := fileHashFromWriter(public1)
	if err != nil {
		t.Fatalf("hash first public witness: %v", err)
	}
	public2Hash, err := fileHashFromWriter(public2)
	if err != nil {
		t.Fatalf("hash cached public witness: %v", err)
	}
	if public1Hash != public2Hash {
		t.Fatalf("cached public witness hash %s, want %s", public2Hash, public1Hash)
	}

	fullWitness, err := frontend.NewWitness(assignment, ecc.BN254.ScalarField())
	if err != nil {
		t.Fatalf("rebuild test witness: %v", err)
	}
	assignmentHash, err := fileHashFromWriter(fullWitness)
	if err != nil {
		t.Fatalf("fingerprint test witness: %v", err)
	}
	cacheKey := proofCacheKey("tiny-inner-proof", stage, ecc.BN254, ecc.BN254, false, assignmentHash)
	cacheDir := proofCacheDirectory(artifactDir, "tiny-inner-proof", cacheKey)
	entries, err := os.ReadDir(cacheDir)
	if err != nil {
		t.Fatalf("list proof cache: %v", err)
	}
	if len(entries) != 3 {
		t.Fatalf("proof cache contains %d files, want proof, public witness, and metadata only", len(entries))
	}
	for _, entry := range entries {
		if entry.Name() != "cache.json" && entry.Name() != "proof.bin" && entry.Name() != "public.witness" {
			t.Errorf("unexpected cached file %q; full/private assignment must not be persisted", entry.Name())
		}
	}

	wrongAssignment := &proofCacheTestCircuit{Public: 1, Secret: 2}
	if _, _, err := proveAndVerifyCached(artifactDir, "tiny-inner-proof", stage, wrongAssignment, ecc.BN254, ecc.BN254, false); err == nil {
		t.Fatal("different unsatisfied assignment reused an existing valid proof")
	}

	if err := os.WriteFile(filepath.Join(cacheDir, "proof.bin"), []byte("tampered"), 0o600); err != nil {
		t.Fatalf("tamper cached proof: %v", err)
	}
	if _, _, err := proveAndVerifyCached(artifactDir, "tiny-inner-proof", stage, assignment, ecc.BN254, ecc.BN254, false); err == nil || !strings.Contains(err.Error(), "artifact hash mismatch") {
		t.Fatalf("tampered proof cache was not rejected by hash: %v", err)
	}
}

func serializeProofForTest(t *testing.T, proof groth16.Proof) []byte {
	t.Helper()
	var output bytes.Buffer
	if _, err := proof.WriteTo(&output); err != nil {
		t.Fatalf("serialize test proof: %v", err)
	}
	return output.Bytes()
}
