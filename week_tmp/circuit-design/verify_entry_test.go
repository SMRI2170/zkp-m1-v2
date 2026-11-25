package draft

import (
	"bytes"
	"crypto/rand"
	"encoding/binary"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	nativeed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/frontend"
	"math/big"
	"testing"
)

func TestPublicExtraction(t *testing.T) {
	k, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	c := SignedCircuit{Observation: uncertainFixture(), RecordID: 1, ExpiresMS: 200000}
	signFixture(t, &c, k)
	public, err := frontend.NewWitness(&c, ecc.BN254.ScalarField(), frontend.PublicOnly())
	if err != nil {
		t.Fatal(err)
	}
	decoded, snapshot, err := DecodeSignedPublic(public)
	if err != nil {
		t.Fatal(err)
	}
	receipt, err := ReceiptFromSignedPublic(decoded)
	if err != nil {
		t.Fatal(err)
	}
	if receipt.Session.Cmp(big.NewInt(7)) != 0 || receipt.RecordID.Cmp(big.NewInt(1)) != 0 || !receipt.Key.Equal(&k.PublicKey) || receipt.Commitment.Cmp(c.Observation.Commitment.(*big.Int)) != 0 {
		t.Fatal("schema extraction mismatch")
	}
	public.Vector().(fr.Vector)[0].SetUint64(99)
	if decoded.Observation.Session.(*big.Int).Cmp(big.NewInt(7)) != 0 || snapshot.Vector().(fr.Vector)[0].String() != "7" {
		t.Fatal("caller mutation changed snapshot")
	}
	full, err := frontend.NewWitness(&c, ecc.BN254.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err = DecodeSignedPublic(full); err == nil {
		t.Fatal("secret/full witness accepted")
	}
	wrong, err := frontend.NewWitness(&c, ecc.BLS12_377.ScalarField(), frontend.PublicOnly())
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err = DecodeSignedPublic(wrong); err == nil {
		t.Fatal("wrong field accepted")
	}
	// Preserve vector length but relabel one field as secret in the binary header.
	goodPublic, err := frontend.NewWitness(&c, ecc.BN254.ScalarField(), frontend.PublicOnly())
	if err != nil {
		t.Fatal(err)
	}
	var encoded bytes.Buffer
	if _, err = goodPublic.WriteTo(&encoded); err != nil {
		t.Fatal(err)
	}
	payload := encoded.Bytes()
	n := binary.BigEndian.Uint32(payload[:4])
	binary.BigEndian.PutUint32(payload[:4], n-1)
	binary.BigEndian.PutUint32(payload[4:8], 1)
	mislabelled, err := witness.New(ecc.BN254.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	if _, err = mislabelled.ReadFrom(bytes.NewReader(payload)); err != nil {
		t.Fatal(err)
	}
	if _, _, err = DecodeSignedPublic(mislabelled); err == nil {
		t.Fatal("secret metadata accepted despite matching total vector length")
	}
	if _, _, err = DecodeSignedPublic(nil); err == nil {
		t.Fatal("nil accepted")
	}
}
func TestFutureSkewPolicy(t *testing.T) {
	r, e := reviewContext(t)
	r.ClaimTimeMS = 150001
	if CheckAdmission(r, e, 150000, nil) == nil {
		t.Fatal("future claim accepted with zero skew")
	}
	e.MaxFutureSkewMS = 1
	if err := CheckAdmission(r, e, 150000, nil); err != nil {
		t.Fatal("boundary rejected", err)
	}
	r.ClaimTimeMS = 150002
	if CheckAdmission(r, e, 150000, nil) == nil {
		t.Fatal("outside skew accepted")
	}
	e.MaxFutureSkewMS = 1 << 32
	if CheckAdmission(r, e, 150000, nil) == nil {
		t.Fatal("oversized skew accepted")
	}
}
