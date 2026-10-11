package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

// Three disposable contributors sign exactly the same length-delimited proof/public set.
// Private signing keys are kept in memory only and never written to Git or logs.
func joint(dir string) error {
	h := sha256.New()
	h.Write([]byte("week23-synthetic-submission-set-v1"))
	bytes := 0
	for i := 1; i <= 3; i++ {
		if err := run("verify", dir, i); err != nil {
			return err
		}
		for _, name := range []string{"proof.bin", "public.bin"} {
			b, err := os.ReadFile(filepath.Join(dir, strconv.Itoa(i), name))
			if err != nil {
				return err
			}
			if err = binary.Write(h, binary.BigEndian, uint64(len(b))); err != nil {
				return err
			}
			h.Write(b)
			bytes += len(b)
		}
	}
	digest := h.Sum(nil)
	all := true
	reject := true
	for i := 0; i < 3; i++ {
		pub, priv, err := ed25519.GenerateKey(rand.Reader)
		if err != nil {
			return err
		}
		sig := ed25519.Sign(priv, digest)
		all = all && ed25519.Verify(pub, digest, sig)
		bad := append([]byte(nil), digest...)
		bad[0] ^= 1
		reject = reject && !ed25519.Verify(pub, bad, sig)
	}
	emit(map[string]any{"baseline": "three-independent-groth16-joint-signatures", "proof_public_bytes": bytes, "signature_bytes": 3 * ed25519.SignatureSize, "common_set_sha256": hex.EncodeToString(digest), "all_verified": all, "tampered_set_rejected": reject, "signing_keys": "test-only in-memory"})
	if !all || !reject {
		return fmt.Errorf("joint signature check failed")
	}
	return nil
}
