package draft

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"fmt"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"
	"math/big"
)

const CalibratedBins = 8

//go:embed profiles/frozen-log-envelope-2d-v1.json
var frozenEnvelopeJSON []byte

type EnvelopeProfile struct {
	Bounds     [CalibratedBins + 1]uint64 `json:"bounds"`
	OuterLow   [CalibratedBins]uint64     `json:"outer_low"`
	OuterHigh  [CalibratedBins]uint64     `json:"outer_high"`
	InnerLow   [CalibratedBins]uint64     `json:"inner_low"`
	InnerHigh  [CalibratedBins]uint64     `json:"inner_high"`
	Supported  [CalibratedBins]uint64     `json:"supported"`
	InnerValid [CalibratedBins]uint64     `json:"inner_valid"`
}
type EnvelopeInput struct {
	Claim          [2]uint64 `json:"claim"`
	Observer       [2]uint64 `json:"observer"`
	ReceiverRadius uint64    `json:"receiver_radius_cm"`
	ClaimRadius    uint64    `json:"claim_radius_cm"`
	RSSI           uint64    `json:"rssi"`
	Eligible       bool      `json:"eligible"`
	ExpectedStatus uint64    `json:"expected_status"` // diagnostics only, never trusted by evaluator
}

// Missing uncertainty is never silently converted to an exact zero radius.
func (o *EnvelopeInput) UnmarshalJSON(data []byte) error {
	var v struct {
		Claim          []uint64 `json:"claim"`
		Observer       []uint64 `json:"observer"`
		ReceiverRadius *uint64  `json:"receiver_radius_cm"`
		ClaimRadius    *uint64  `json:"claim_radius_cm"`
		RSSI           *uint64  `json:"rssi"`
		Eligible       *bool    `json:"eligible"`
		ExpectedStatus *uint64  `json:"expected_status"`
	}
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&v); err != nil {
		return fmt.Errorf("invalid envelope JSON")
	}
	if len(v.Claim) != 2 || len(v.Observer) != 2 || v.ReceiverRadius == nil || v.ClaimRadius == nil || v.RSSI == nil || v.Eligible == nil || v.ExpectedStatus == nil {
		return fmt.Errorf("missing envelope fields or wrong dimension")
	}
	*o = EnvelopeInput{Claim: [2]uint64{v.Claim[0], v.Claim[1]}, Observer: [2]uint64{v.Observer[0], v.Observer[1]}, ReceiverRadius: *v.ReceiverRadius, ClaimRadius: *v.ClaimRadius, RSSI: *v.RSSI, Eligible: *v.Eligible, ExpectedStatus: *v.ExpectedStatus}
	return nil
}
func FrozenEnvelope() (EnvelopeProfile, error) {
	var card struct {
		Profile EnvelopeProfile `json:"profile"`
	}
	err := json.Unmarshal(frozenEnvelopeJSON, &card)
	if err == nil {
		err = card.Profile.Validate()
	}
	return card.Profile, err
}
func (p EnvelopeProfile) Validate() error {
	if p.Bounds[0] != 0 || p.Bounds[CalibratedBins] != UncertainMaxSquared+1 {
		return fmt.Errorf("envelope coverage")
	}
	for i := 0; i < CalibratedBins; i++ {
		if p.Bounds[i] >= p.Bounds[i+1] || p.OuterLow[i] > p.OuterHigh[i] || p.OuterHigh[i] > RSSIMax || p.InnerValid[i] > 1 || p.Supported[i] > 1 {
			return fmt.Errorf("envelope range")
		}
		if p.InnerValid[i] == 1 {
			if p.Supported[i] != 1 || p.InnerLow[i] < p.OuterLow[i] || p.InnerLow[i] > p.InnerHigh[i] || p.InnerHigh[i] > p.OuterHigh[i] {
				return fmt.Errorf("invalid inner interval")
			}
		} else if p.InnerLow[i] != 0 || p.InnerHigh[i] != 0 {
			return fmt.Errorf("noncanonical empty interval")
		}
	}
	return nil
}
func (p EnvelopeProfile) Digest() (*big.Int, error) {
	if err := p.Validate(); err != nil {
		return nil, err
	}
	v := ints(3206001)
	v = append(v, ints(p.Bounds[:]...)...)
	for i := 0; i < CalibratedBins; i++ {
		v = append(v, ints(p.Supported[i], p.InnerValid[i], p.OuterLow[i], p.OuterHigh[i], p.InnerLow[i], p.InnerHigh[i])...)
	}
	return FieldHash(v...)
}
func EvaluateEnvelope(p EnvelopeProfile, o EnvelopeInput) (uint64, error) {
	if err := p.Validate(); err != nil {
		return 0, err
	}
	if o.ReceiverRadius > MaxCoordinate || o.ClaimRadius > MaxCoordinate || o.RSSI > RSSIMax {
		return 0, fmt.Errorf("observation range")
	}
	lo, hi := uint64(0), uint64(0)
	radius := o.ReceiverRadius + o.ClaimRadius
	for i := 0; i < 2; i++ {
		if o.Claim[i] > MaxCoordinate || o.Observer[i] > MaxCoordinate {
			return 0, fmt.Errorf("coordinate range")
		}
		d := diff(o.Claim[i], o.Observer[i])
		l := uint64(0)
		if d > radius {
			l = d - radius
		}
		lo += l * l
		hi += (d + radius) * (d + radius)
	}
	count, supported, inner, outer := 0, 0, 0, 0
	for i := 0; i < CalibratedBins; i++ {
		if hi >= p.Bounds[i] && lo < p.Bounds[i+1] {
			count++
			supported += int(p.Supported[i])
			if p.InnerValid[i] == 1 && p.InnerLow[i] <= o.RSSI && o.RSSI <= p.InnerHigh[i] {
				inner++
			}
			if p.OuterLow[i] <= o.RSSI && o.RSSI <= p.OuterHigh[i] {
				outer++
			}
		}
	}
	if count == 0 {
		return 0, fmt.Errorf("no bin")
	}
	if !o.Eligible || supported != count {
		return 2, nil
	}
	if inner == count {
		return 0, nil
	}
	if outer == 0 {
		return 1, nil
	}
	return 2, nil
}

// CalibratedCircuit is ONLY the spatial decision kernel. It is NOT the old
// SignedCircuit and does not assert clock/height eligibility or signatures.
type CalibratedCircuit struct {
	Session        frontend.Variable                     `gnark:",public"`
	FrameID        frontend.Variable                     `gnark:",public"`
	ClaimToken     frontend.Variable                     `gnark:",public"`
	Claim          [2]frontend.Variable                  `gnark:",public"`
	Bounds         [CalibratedBins + 1]frontend.Variable `gnark:",public"`
	OuterLow       [CalibratedBins]frontend.Variable     `gnark:",public"`
	OuterHigh      [CalibratedBins]frontend.Variable     `gnark:",public"`
	InnerLow       [CalibratedBins]frontend.Variable     `gnark:",public"`
	InnerHigh      [CalibratedBins]frontend.Variable     `gnark:",public"`
	Supported      [CalibratedBins]frontend.Variable     `gnark:",public"`
	InnerValid     [CalibratedBins]frontend.Variable     `gnark:",public"`
	PolicyDigest   frontend.Variable                     `gnark:",public"`
	Status         frontend.Variable                     `gnark:",public"`
	Commitment     frontend.Variable                     `gnark:",public"`
	Observer       [2]frontend.Variable
	ReceiverRadius frontend.Variable
	ClaimRadius    frontend.Variable
	RSSI           frontend.Variable
	Eligible       frontend.Variable
	Nonce          frontend.Variable
}

func (c *CalibratedCircuit) Define(api frontend.API) error {
	bounded(api, c.ReceiverRadius, 20)
	bounded(api, c.ClaimRadius, 20)
	bounded(api, c.RSSI, 14)
	api.AssertIsLessOrEqual(c.RSSI, RSSIMax)
	api.AssertIsBoolean(c.Eligible)
	bounded(api, c.Nonce, 128)
	api.AssertIsDifferent(c.Nonce, 0)
	lo, hi := frontend.Variable(0), frontend.Variable(0)
	radius := api.Add(c.ReceiverRadius, c.ClaimRadius)
	for i := 0; i < 2; i++ {
		bounded(api, c.Claim[i], 20)
		bounded(api, c.Observer[i], 20)
		d := absDifference(api, c.Claim[i], c.Observer[i])
		l := api.Select(less(api, d, radius), 0, api.Sub(d, radius))
		h := api.Add(d, radius)
		lo = api.Add(lo, api.Mul(l, l))
		hi = api.Add(hi, api.Mul(h, h))
	}
	api.AssertIsEqual(c.Bounds[0], 0)
	api.AssertIsEqual(c.Bounds[CalibratedBins], UncertainMaxSquared+1)
	h, err := mimc.NewMiMC(api)
	if err != nil {
		return err
	}
	h.Write(3206001)
	for _, v := range c.Bounds {
		bounded(api, v, 46)
		h.Write(v)
	}
	count, supported, inner, outer := frontend.Variable(0), frontend.Variable(0), frontend.Variable(0), frontend.Variable(0)
	for i := 0; i < CalibratedBins; i++ {
		api.AssertIsLessOrEqual(api.Add(c.Bounds[i], 1), c.Bounds[i+1])
		api.AssertIsBoolean(c.Supported[i])
		api.AssertIsBoolean(c.InnerValid[i])
		api.AssertIsEqual(api.Mul(c.InnerValid[i], api.Sub(1, c.Supported[i])), 0)
		for _, v := range []frontend.Variable{c.OuterLow[i], c.OuterHigh[i], c.InnerLow[i], c.InnerHigh[i]} {
			bounded(api, v, 14)
			api.AssertIsLessOrEqual(v, RSSIMax)
		}
		api.AssertIsLessOrEqual(c.OuterLow[i], c.OuterHigh[i])
		api.AssertIsEqual(api.Mul(api.Sub(1, c.InnerValid[i]), c.InnerLow[i]), 0)
		api.AssertIsEqual(api.Mul(api.Sub(1, c.InnerValid[i]), c.InnerHigh[i]), 0)
		api.AssertIsEqual(api.Mul(c.InnerValid[i], less(api, c.InnerLow[i], c.OuterLow[i])), 0)
		api.AssertIsEqual(api.Mul(c.InnerValid[i], less(api, c.InnerHigh[i], c.InnerLow[i])), 0)
		api.AssertIsEqual(api.Mul(c.InnerValid[i], less(api, c.OuterHigh[i], c.InnerHigh[i])), 0)
		h.Write(c.Supported[i], c.InnerValid[i], c.OuterLow[i], c.OuterHigh[i], c.InnerLow[i], c.InnerHigh[i])
		hit := api.Mul(api.Sub(1, less(api, hi, c.Bounds[i])), less(api, lo, c.Bounds[i+1]))
		in := api.Mul(c.InnerValid[i], api.Sub(1, less(api, c.RSSI, c.InnerLow[i])), api.Sub(1, less(api, c.InnerHigh[i], c.RSSI)))
		out := api.Mul(api.Sub(1, less(api, c.RSSI, c.OuterLow[i])), api.Sub(1, less(api, c.OuterHigh[i], c.RSSI)))
		count = api.Add(count, hit)
		supported = api.Add(supported, api.Mul(hit, c.Supported[i]))
		inner = api.Add(inner, api.Mul(hit, in))
		outer = api.Add(outer, api.Mul(hit, out))
	}
	api.AssertIsDifferent(count, 0)
	api.AssertIsEqual(c.PolicyDigest, h.Sum())
	status := api.Select(api.IsZero(api.Sub(inner, count)), 0, api.Select(api.IsZero(outer), 1, 2))
	api.AssertIsEqual(c.Status, api.Select(api.Mul(c.Eligible, api.IsZero(api.Sub(count, supported))), status, 2))
	h.Reset()
	h.Write(3206002, c.Session, c.FrameID, c.ClaimToken, c.PolicyDigest, c.Claim[0], c.Claim[1], c.Observer[0], c.Observer[1], c.ReceiverRadius, c.ClaimRadius, c.RSSI, c.Eligible, c.Nonce, c.Status)
	api.AssertIsEqual(c.Commitment, h.Sum())
	return nil
}
func EnvelopeAssignment(p EnvelopeProfile, o EnvelopeInput, ctx StatementContext) (CalibratedCircuit, error) {
	var c CalibratedCircuit
	status, err := EvaluateEnvelope(p, o)
	if err != nil {
		return c, err
	}
	if !canonical(ctx.Session) || !canonical(ctx.FrameID) || !canonical(ctx.ClaimToken) || !canonical(ctx.Nonce) || ctx.Nonce.Sign() <= 0 || ctx.Nonce.BitLen() > 128 {
		return c, fmt.Errorf("context")
	}
	c.Session = ctx.Session
	c.FrameID = ctx.FrameID
	c.ClaimToken = ctx.ClaimToken
	c.Nonce = ctx.Nonce
	for i := 0; i < 2; i++ {
		c.Claim[i] = o.Claim[i]
		c.Observer[i] = o.Observer[i]
	}
	c.ReceiverRadius = o.ReceiverRadius
	c.ClaimRadius = o.ClaimRadius
	c.RSSI = o.RSSI
	c.Eligible = flag(o.Eligible)
	c.Status = status
	for i := 0; i <= CalibratedBins; i++ {
		c.Bounds[i] = p.Bounds[i]
	}
	for i := 0; i < CalibratedBins; i++ {
		c.OuterLow[i] = p.OuterLow[i]
		c.OuterHigh[i] = p.OuterHigh[i]
		c.InnerLow[i] = p.InnerLow[i]
		c.InnerHigh[i] = p.InnerHigh[i]
		c.Supported[i] = p.Supported[i]
		c.InnerValid[i] = p.InnerValid[i]
	}
	digest, err := p.Digest()
	if err != nil {
		return c, err
	}
	c.PolicyDigest = digest
	v := append(ints(3206002), ctx.Session, ctx.FrameID, ctx.ClaimToken, digest)
	v = append(v, ints(o.Claim[0], o.Claim[1], o.Observer[0], o.Observer[1], o.ReceiverRadius, o.ClaimRadius, o.RSSI, flag(o.Eligible))...)
	v = append(v, ctx.Nonce, new(big.Int).SetUint64(status))
	c.Commitment, err = FieldHash(v...)
	return c, err
}
