package draft

import (
	_ "embed"
	"encoding/json"
	"fmt"
	native "github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
	"github.com/consensys/gnark/frontend"
	"math/big"
)

//go:embed profiles/synthetic-four-band-v1.json
var syntheticPolicyJSON []byte

// IntegerPolicy specifies the circuit's integer arithmetic; it is not an
// approved empirical model. No float/log fitting is performed here.
type IntegerPolicy struct {
	Mode3D      bool             `json:"mode_3d"`
	Bounds      [Bins + 1]uint64 `json:"bounds_cm2"`
	Low         [Bins]uint64     `json:"rssi_low_shifted_cdbm"`
	High        [Bins]uint64     `json:"rssi_high_shifted_cdbm"`
	MaxAgeMS    uint64           `json:"max_age_ms"`
	MaxSpeedCMS uint64           `json:"max_speed_cm_s"`
}
type IntegerObservation struct {
	Claim, Observer, ReceiverError, ClaimError                 [3]uint64
	ClaimTimeMS, ObservedTimeMS, FixTimeMS, ClockErrorMS, RSSI uint64
	HorizontalKnown, TimeKnown, AltitudeKnown                  bool
}
type IntegerResult struct {
	Status                     uint64
	MotionRadiusCM             uint64
	MinSquaredCM, MaxSquaredCM uint64
}
type StatementContext struct{ Session, FrameID, ClaimToken, Nonce *big.Int }

func SyntheticPolicy() (IntegerPolicy, error) {
	var p IntegerPolicy
	err := json.Unmarshal(syntheticPolicyJSON, &p)
	if err == nil {
		err = p.Validate()
	}
	return p, err
}
func (p IntegerPolicy) Validate() error {
	if p.MaxAgeMS >= 1<<32 || p.MaxSpeedCMS >= 1<<16 || p.Bounds[0] != 0 || p.Bounds[Bins] != UncertainMaxSquared+1 {
		return fmt.Errorf("policy range or coverage")
	}
	for i := 0; i < Bins; i++ {
		if p.Bounds[i] >= p.Bounds[i+1] || p.Low[i] > p.High[i] || p.High[i] > RSSIMax {
			return fmt.Errorf("invalid policy bin")
		}
	}
	return nil
}
func flag(b bool) uint64 {
	if b {
		return 1
	}
	return 0
}
func diff(a, b uint64) uint64 {
	if a > b {
		return a - b
	}
	return b - a
}
func FieldHash(values ...*big.Int) (*big.Int, error) {
	h := native.NewMiMC()
	for _, v := range values {
		if !canonical(v) {
			return nil, fmt.Errorf("noncanonical field")
		}
		if _, err := h.Write(v.FillBytes(make([]byte, 32))); err != nil {
			return nil, err
		}
	}
	return new(big.Int).SetBytes(h.Sum(nil)), nil
}
func ints(values ...uint64) []*big.Int {
	out := make([]*big.Int, len(values))
	for i, v := range values {
		out[i] = new(big.Int).SetUint64(v)
	}
	return out
}
func (p IntegerPolicy) Digest() (*big.Int, error) {
	if err := p.Validate(); err != nil {
		return nil, err
	}
	v := ints(3202001, flag(p.Mode3D), p.MaxAgeMS, p.MaxSpeedCMS)
	v = append(v, ints(p.Bounds[:]...)...)
	for i := 0; i < Bins; i++ {
		v = append(v, ints(p.Low[i], p.High[i])...)
	}
	return FieldHash(v...)
}
func EvaluateInteger(p IntegerPolicy, o IntegerObservation) (IntegerResult, error) {
	var out IntegerResult
	if err := p.Validate(); err != nil {
		return out, err
	}
	if o.ClaimTimeMS >= 1<<48 || o.ObservedTimeMS >= 1<<48 || o.FixTimeMS >= 1<<48 || o.ClockErrorMS >= 1<<32 || o.RSSI > RSSIMax {
		return out, fmt.Errorf("observation range")
	}
	age := diff(o.ObservedTimeMS, o.FixTimeMS) + diff(o.ObservedTimeMS, o.ClaimTimeMS) + o.ClockErrorMS
	// age fits < 2^50, but age*speed may exceed uint64. Never wrap it.
	movement := new(big.Int).Mul(new(big.Int).SetUint64(age), new(big.Int).SetUint64(p.MaxSpeedCMS))
	movement.Add(movement, big.NewInt(999))
	movement.Div(movement, big.NewInt(1000))
	if movement.BitLen() > 20 {
		return out, fmt.Errorf("motion radius outside circuit range")
	}
	out.MotionRadiusCM = movement.Uint64()
	for i := 0; i < 3; i++ {
		if o.Claim[i] > MaxCoordinate || o.Observer[i] > MaxCoordinate || o.ReceiverError[i] > MaxCoordinate || o.ClaimError[i] > MaxCoordinate {
			return out, fmt.Errorf("coordinate/error range")
		}
		if i == 2 && !p.Mode3D {
			continue
		}
		d := diff(o.Claim[i], o.Observer[i])
		radius := o.ReceiverError[i] + o.ClaimError[i] + out.MotionRadiusCM
		lo := uint64(0)
		if d > radius {
			lo = d - radius
		}
		hi := d + radius
		out.MinSquaredCM += lo * lo
		out.MaxSquaredCM += hi * hi
	}
	count, good := 0, 0
	for i := 0; i < Bins; i++ {
		if out.MaxSquaredCM >= p.Bounds[i] && out.MinSquaredCM < p.Bounds[i+1] {
			count++
			if o.RSSI >= p.Low[i] && o.RSSI <= p.High[i] {
				good++
			}
		}
	}
	if count == 0 {
		return out, fmt.Errorf("no distance bin")
	}
	out.Status = 2
	if o.HorizontalKnown && o.TimeKnown && (!p.Mode3D || o.AltitudeKnown) && age <= p.MaxAgeMS {
		if good == count {
			out.Status = 0
		} else if good == 0 {
			out.Status = 1
		}
	}
	return out, nil
}

// BuildUncertaintyAssignment binds the integer reference output and the exact
// same policy fields into a circuit assignment, without real-key handling.
func BuildUncertaintyAssignment(p IntegerPolicy, o IntegerObservation, ctx StatementContext) (UncertaintyCircuit, error) {
	var c UncertaintyCircuit
	r, err := EvaluateInteger(p, o)
	if err != nil {
		return c, err
	}
	if !canonical(ctx.Session) || !canonical(ctx.FrameID) || !canonical(ctx.ClaimToken) || !canonical(ctx.Nonce) || ctx.Nonce.Sign() <= 0 || ctx.Nonce.BitLen() > 128 {
		return c, fmt.Errorf("invalid context/nonce")
	}
	c.Session = new(big.Int).Set(ctx.Session)
	c.FrameID = new(big.Int).Set(ctx.FrameID)
	c.ClaimToken = new(big.Int).Set(ctx.ClaimToken)
	c.Nonce = new(big.Int).Set(ctx.Nonce)
	c.Mode3D = flag(p.Mode3D)
	c.ClaimTimeMS = o.ClaimTimeMS
	c.ObservedTimeMS = o.ObservedTimeMS
	c.FixTimeMS = o.FixTimeMS
	c.ClockErrorMS = o.ClockErrorMS
	c.RSSI = o.RSSI
	c.MaxAgeMS = p.MaxAgeMS
	c.MaxSpeedCMS = p.MaxSpeedCMS
	c.MotionRadius = r.MotionRadiusCM
	c.Status = r.Status
	c.HorizontalKnown = flag(o.HorizontalKnown)
	c.TimeKnown = flag(o.TimeKnown)
	c.AltitudeKnown = flag(o.AltitudeKnown)
	for i := 0; i < 3; i++ {
		c.Claim[i] = o.Claim[i]
		c.Observer[i] = o.Observer[i]
		c.ReceiverError[i] = o.ReceiverError[i]
		c.ClaimError[i] = o.ClaimError[i]
	}
	for i := 0; i <= Bins; i++ {
		c.Bounds[i] = p.Bounds[i]
	}
	for i := 0; i < Bins; i++ {
		c.Low[i] = p.Low[i]
		c.High[i] = p.High[i]
	}
	c.PolicyDigest, err = p.Digest()
	if err != nil {
		return c, err
	}
	v := append(ints(3202002), ctx.Session, ctx.FrameID, ctx.ClaimToken, c.PolicyDigest.(*big.Int))
	v = append(v, ints(o.Claim[:]...)...)
	v = append(v, ints(o.ClaimTimeMS)...)
	v = append(v, ints(o.Observer[:]...)...)
	v = append(v, ints(o.ReceiverError[:]...)...)
	v = append(v, ints(o.ClaimError[:]...)...)
	v = append(v, ints(o.RSSI, o.ObservedTimeMS, o.FixTimeMS, o.ClockErrorMS, r.MotionRadiusCM, flag(o.HorizontalKnown), flag(o.TimeKnown), flag(o.AltitudeKnown))...)
	v = append(v, ctx.Nonce)
	v = append(v, new(big.Int).SetUint64(r.Status))
	c.Commitment, err = FieldHash(v...)
	return c, err
}

// Ensure the statement remains a gnark circuit when used by callers.
var _ frontend.Circuit = (*UncertaintyCircuit)(nil)
