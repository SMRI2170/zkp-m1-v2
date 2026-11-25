package draft

import (
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"
)

const UncertainMaxSquared = 3 * (4 * MaxCoordinate) * (4 * MaxCoordinate)

// UncertaintyCircuit is a separate statement from Circuit. Error radii and
// known flags MUST be bound to admitted metadata/policy before external use.
// They are assumptions, not proved physical error bounds. Mode3D=0 is 2D.
// If all possible distance bins agree: output 0/1; otherwise 2 (hold).
type UncertaintyCircuit struct {
	Session         frontend.Variable           `gnark:",public"`
	FrameID         frontend.Variable           `gnark:",public"`
	ClaimToken      frontend.Variable           `gnark:",public"`
	Mode3D          frontend.Variable           `gnark:",public"`
	Claim           [3]frontend.Variable        `gnark:",public"`
	ClaimTimeMS     frontend.Variable           `gnark:",public"`
	Bounds          [Bins + 1]frontend.Variable `gnark:",public"`
	Low             [Bins]frontend.Variable     `gnark:",public"`
	High            [Bins]frontend.Variable     `gnark:",public"`
	MaxAgeMS        frontend.Variable           `gnark:",public"`
	MaxSpeedCMS     frontend.Variable           `gnark:",public"` // assumed per-object speed upper bound, not measured truth
	PolicyDigest    frontend.Variable           `gnark:",public"`
	Status          frontend.Variable           `gnark:",public"`
	Commitment      frontend.Variable           `gnark:",public"`
	Observer        [3]frontend.Variable
	ReceiverError   [3]frontend.Variable // per-axis cm box; not a Gaussian standard deviation
	ClaimError      [3]frontend.Variable
	RSSI            frontend.Variable
	ObservedTimeMS  frontend.Variable
	FixTimeMS       frontend.Variable
	ClockErrorMS    frontend.Variable // combined uncertainty beyond measured within-device age
	MotionRadius    frontend.Variable // ceil(speed * total time budget / 1000), cm
	HorizontalKnown frontend.Variable
	TimeKnown       frontend.Variable
	AltitudeKnown   frontend.Variable // common datum + both vertical errors known
	Nonce           frontend.Variable
}

func absDifference(api frontend.API, a, b frontend.Variable) frontend.Variable {
	before := api.IsZero(api.Add(api.Cmp(a, b), 1))
	return api.Select(before, api.Sub(b, a), api.Sub(a, b))
}
func less(api frontend.API, a, b frontend.Variable) frontend.Variable {
	return api.IsZero(api.Add(api.Cmp(a, b), 1))
}

func (c *UncertaintyCircuit) Define(api frontend.API) error {
	api.AssertIsBoolean(c.Mode3D)
	for _, v := range []frontend.Variable{c.HorizontalKnown, c.TimeKnown, c.AltitudeKnown} {
		api.AssertIsBoolean(v)
	}
	for _, v := range []frontend.Variable{c.ClaimTimeMS, c.ObservedTimeMS, c.FixTimeMS} {
		bounded(api, v, 48)
	}
	bounded(api, c.MaxAgeMS, 32)
	bounded(api, c.ClockErrorMS, 32)
	bounded(api, c.MaxSpeedCMS, 16)
	bounded(api, c.MotionRadius, 20)
	bounded(api, c.RSSI, 14)
	api.AssertIsLessOrEqual(c.RSSI, RSSIMax)
	bounded(api, c.Nonce, 128)
	api.AssertIsDifferent(c.Nonce, 0)
	totalAge := api.Add(absDifference(api, c.ObservedTimeMS, c.FixTimeMS), absDifference(api, c.ObservedTimeMS, c.ClaimTimeMS), c.ClockErrorMS)
	// Exact integer ceil division: 0 <= 1000*radius - speed*age <= 999.
	remainder := api.Sub(api.Mul(c.MotionRadius, 1000), api.Mul(c.MaxSpeedCMS, totalAge))
	bounded(api, remainder, 10)
	api.AssertIsLessOrEqual(remainder, 999)
	lo := frontend.Variable(0)
	hi := frontend.Variable(0)
	for i := 0; i < 3; i++ {
		bounded(api, c.Claim[i], 20)
		bounded(api, c.Observer[i], 20)
		bounded(api, c.ReceiverError[i], 20)
		bounded(api, c.ClaimError[i], 20)
		d := absDifference(api, c.Claim[i], c.Observer[i])
		radius := api.Add(c.ReceiverError[i], c.ClaimError[i], c.MotionRadius)
		minDelta := api.Select(less(api, d, radius), 0, api.Sub(d, radius))
		maxDelta := api.Add(d, radius)
		enabled := frontend.Variable(1)
		if i == 2 {
			enabled = c.Mode3D
		}
		lo = api.Add(lo, api.Mul(enabled, minDelta, minDelta))
		hi = api.Add(hi, api.Mul(enabled, maxDelta, maxDelta))
	}
	api.AssertIsEqual(c.Bounds[0], 0)
	api.AssertIsEqual(c.Bounds[Bins], UncertainMaxSquared+1)
	for _, v := range c.Bounds {
		bounded(api, v, 46)
	}
	h, err := mimc.NewMiMC(api)
	if err != nil {
		return err
	}
	h.Write(3202001, c.Mode3D, c.MaxAgeMS, c.MaxSpeedCMS)
	for _, v := range c.Bounds {
		h.Write(v)
	}
	count := frontend.Variable(0)
	good := frontend.Variable(0)
	for i := 0; i < Bins; i++ {
		api.AssertIsLessOrEqual(api.Add(c.Bounds[i], 1), c.Bounds[i+1])
		bounded(api, c.Low[i], 14)
		bounded(api, c.High[i], 14)
		api.AssertIsLessOrEqual(c.Low[i], c.High[i])
		api.AssertIsLessOrEqual(c.High[i], RSSIMax)
		h.Write(c.Low[i], c.High[i])
		overlap := api.Mul(api.Sub(1, less(api, hi, c.Bounds[i])), less(api, lo, c.Bounds[i+1]))
		inside := api.Mul(api.Sub(1, less(api, c.RSSI, c.Low[i])), api.Sub(1, less(api, c.High[i], c.RSSI)))
		count = api.Add(count, overlap)
		good = api.Add(good, api.Mul(overlap, inside))
	}
	api.AssertIsDifferent(count, 0)
	api.AssertIsEqual(c.PolicyDigest, h.Sum())
	allInside := api.IsZero(api.Sub(count, good))
	noneInside := api.IsZero(good)
	decision := api.Select(allInside, 0, api.Select(noneInside, 1, 2))
	ageOK := api.Sub(1, less(api, c.MaxAgeMS, totalAge))
	altitudeOK := api.Select(c.Mode3D, c.AltitudeKnown, 1)
	eligible := api.Mul(c.HorizontalKnown, c.TimeKnown, altitudeOK, ageOK)
	api.AssertIsEqual(c.Status, api.Select(eligible, decision, 2))
	h.Reset()
	h.Write(3202002, c.Session, c.FrameID, c.ClaimToken, c.PolicyDigest)
	for _, v := range c.Claim {
		h.Write(v)
	}
	h.Write(c.ClaimTimeMS)
	for _, v := range c.Observer {
		h.Write(v)
	}
	for _, v := range c.ReceiverError {
		h.Write(v)
	}
	for _, v := range c.ClaimError {
		h.Write(v)
	}
	h.Write(c.RSSI, c.ObservedTimeMS, c.FixTimeMS, c.ClockErrorMS, c.MotionRadius, c.HorizontalKnown, c.TimeKnown, c.AltitudeKnown, c.Nonce, c.Status)
	api.AssertIsEqual(c.Commitment, h.Sum())
	return nil
}
