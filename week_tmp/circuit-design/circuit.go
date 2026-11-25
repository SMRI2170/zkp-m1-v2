// Package draft implements an isolated research constraint system, not a release verifier.
package draft

import (
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"
)

const (
	Bins               = 4
	CoordinateBits     = 20 // centimetres in a public, fixed local ENU origin + offset
	MaxCoordinate      = (1 << CoordinateBits) - 1
	MaxDistanceSquared = 3 * MaxCoordinate * MaxCoordinate
	RSSIMax            = 16000 // rssi_cdbm + 16000; [-160,0] dBm inclusive
	PolicyDomain       = 3201001
	ObservationDomain  = 3201002
)

// Circuit exposes only a claimed point, context, public policy and result.
// Bounds are half-open squared-distance bins in cm²; RSSI endpoints inclusive.
// Status: 0=model-consistent, 1=model-inconsistent, 2=quality hold.
// Commitment must be bound externally to an admitted observer's signed record.
// A self-chosen commitment alone provides no observation authenticity.
type Circuit struct {
	Session      frontend.Variable           `gnark:",public"`
	FrameID      frontend.Variable           `gnark:",public"` // public identifier of local coordinate frame; registry external
	ClaimToken   frontend.Variable           `gnark:",public"` // opaque claimed-RID/run token; not authentication
	Claim        [3]frontend.Variable        `gnark:",public"`
	ClaimTime    frontend.Variable           `gnark:",public"` // seconds since session epoch; never a wrapped RID hour value
	Bounds       [Bins + 1]frontend.Variable `gnark:",public"`
	Low          [Bins]frontend.Variable     `gnark:",public"`
	High         [Bins]frontend.Variable     `gnark:",public"`
	MaxAge       frontend.Variable           `gnark:",public"`
	MaxAccuracy  frontend.Variable           `gnark:",public"` // cm; external metadata, not sensor truth
	PolicyDigest frontend.Variable           `gnark:",public"`
	Status       frontend.Variable           `gnark:",public"`
	Commitment   frontend.Variable           `gnark:",public"`

	Observer     [3]frontend.Variable
	RSSI         frontend.Variable
	ObservedTime frontend.Variable
	Accuracy     frontend.Variable
	Nonce        frontend.Variable // 128-bit nonzero; random generation is external
}

func bounded(api frontend.API, v frontend.Variable, bits int) { api.ToBinary(v, bits) }

func (c *Circuit) Define(api frontend.API) error {
	// Bounded ordinary integers prevent finite-field wraparound and sign ambiguity.
	bounded(api, c.ClaimTime, 32)
	bounded(api, c.ObservedTime, 32)
	bounded(api, c.MaxAge, 16)
	bounded(api, c.MaxAccuracy, 16)
	bounded(api, c.Accuracy, 16)
	bounded(api, c.RSSI, 14)
	api.AssertIsLessOrEqual(c.RSSI, RSSIMax)
	bounded(api, c.Nonce, 128)
	api.AssertIsDifferent(c.Nonce, 0)
	distance := frontend.Variable(0)
	for i := 0; i < 3; i++ {
		bounded(api, c.Claim[i], CoordinateBits)
		bounded(api, c.Observer[i], CoordinateBits)
		delta := api.Sub(c.Claim[i], c.Observer[i])
		distance = api.Add(distance, api.Mul(delta, delta))
	}
	// Max squared distance < 2^42 << BN254 scalar modulus.
	api.AssertIsEqual(c.Bounds[0], 0)
	api.AssertIsEqual(c.Bounds[Bins], MaxDistanceSquared+1)
	for i := 0; i <= Bins; i++ {
		bounded(api, c.Bounds[i], 42)
	}
	h, err := mimc.NewMiMC(api)
	if err != nil {
		return err
	}
	h.Write(PolicyDomain, c.MaxAge, c.MaxAccuracy)
	for i := 0; i <= Bins; i++ {
		h.Write(c.Bounds[i])
	}
	count := frontend.Variable(0)
	inside := frontend.Variable(0)
	for i := 0; i < Bins; i++ {
		api.AssertIsLessOrEqual(api.Add(c.Bounds[i], 1), c.Bounds[i+1])
		bounded(api, c.Low[i], 14)
		bounded(api, c.High[i], 14)
		api.AssertIsLessOrEqual(c.Low[i], c.High[i])
		api.AssertIsLessOrEqual(c.High[i], RSSIMax)
		h.Write(c.Low[i], c.High[i])
		belowLower := api.IsZero(api.Sub(api.Cmp(distance, c.Bounds[i]), -1))
		belowUpper := api.IsZero(api.Sub(api.Cmp(distance, c.Bounds[i+1]), -1))
		selected := api.Mul(api.Sub(1, belowLower), belowUpper)
		count = api.Add(count, selected)
		rssiLow := api.Sub(1, api.IsZero(api.Add(api.Cmp(c.RSSI, c.Low[i]), 1)))
		rssiHigh := api.Sub(1, api.IsZero(api.Sub(api.Cmp(c.RSSI, c.High[i]), 1)))
		inside = api.Add(inside, api.Mul(selected, rssiLow, rssiHigh))
	}
	api.AssertIsEqual(count, 1)
	api.AssertIsEqual(c.PolicyDigest, h.Sum())
	deltaT := api.Sub(c.ObservedTime, c.ClaimTime)
	earlier := api.IsZero(api.Add(api.Cmp(c.ObservedTime, c.ClaimTime), 1))
	age := api.Select(earlier, api.Neg(deltaT), deltaT)
	fresh := api.Sub(1, api.IsZero(api.Sub(api.Cmp(age, c.MaxAge), 1)))
	accurate := api.Sub(1, api.IsZero(api.Sub(api.Cmp(c.Accuracy, c.MaxAccuracy), 1)))
	eligible := api.Mul(fresh, accurate)
	expected := api.Select(eligible, api.Sub(1, inside), 2)
	api.AssertIsEqual(c.Status, expected)
	h.Reset()
	h.Write(ObservationDomain, c.Session, c.FrameID, c.ClaimToken, c.PolicyDigest)
	for i := 0; i < 3; i++ {
		h.Write(c.Claim[i])
	}
	h.Write(c.ClaimTime)
	for i := 0; i < 3; i++ {
		h.Write(c.Observer[i])
	}
	h.Write(c.RSSI, c.ObservedTime, c.Accuracy, c.Nonce, c.Status)
	api.AssertIsEqual(c.Commitment, h.Sum())
	return nil
}
