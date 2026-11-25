package draft

import (
	"encoding/json"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/schema"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestModelPrivacySchema(t *testing.T) {
	names := map[string]schema.Visibility{}
	var public, secret []string
	count, err := schema.Walk(ecc.BN254.ScalarField(), &SignedModelCircuit{}, reflect.TypeOf((*frontend.Variable)(nil)).Elem(), func(l schema.LeafInfo, _ reflect.Value) error {
		name := l.FullName()
		names[name] = l.Visibility
		if l.Visibility == schema.Public {
			public = append(public, name)
		} else {
			secret = append(secret, name)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"Core_Observer_0", "Core_RSSI", "Core_ReceiverRadius", "Core_ClaimRadius", "Core_Nonce", "ObservedTimeMS", "ClockErrorMS", "TimeKnown", "HorizontalKnown", "SourceDigest_0", "Signature_S"} {
		if names[name] != schema.Secret {
			t.Fatalf("expected private %s", name)
		}
	}
	for _, name := range []string{"Core_Claim_0", "ObserverKey_A_X", "RecordID", "ClaimTimeMS", "Nullifier"} {
		if names[name] != schema.Public {
			t.Fatalf("expected public %s", name)
		}
	}
	if p := os.Getenv("DRAFT_SUMMARY_PATH"); p != "" {
		b, _ := json.MarshalIndent(map[string]interface{}{"statement": ModelStatementID, "public_fields": public, "private_fields": secret, "public_count": count.Public, "private_count": count.Secret, "claim": "schema secrecy only; no unlinkability or independent privacy audit"}, "", "  ")
		if err := os.WriteFile(filepath.Join(filepath.Dir(p), "model-privacy-schema.json"), append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}
