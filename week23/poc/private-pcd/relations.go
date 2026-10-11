package main

import (
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/math/cmp"
)

// circuits/remoteid_consistency_rel.circom と同じ係数（相対許容 ±90%）。
const (
	latCmNum = 11132000
	lonCmNum = 9128800
	geoDen   = 10000000
	tolNum   = 90
	tolDen   = 100
)

// absDiff: |a-b|（circuits/lib_uav_safety.circom の AbsDiff と同じ発想。
// gnark は体が大きい(BN254)ので a-b の符号を cmp.IsLess で判定して Select する）。
func absDiff(api frontend.API, a, b frontend.Variable) frontend.Variable {
	aLtB := cmp.IsLess(api, a, b)
	return api.Select(aLtB, api.Sub(b, a), api.Sub(a, b))
}

// rssiConsistencyOk: circuits/remoteid_consistency_rel.circom の RemoteIdConsistencyRel と
// 同じ計算。申告位置(drone)と自分の位置(target)から求めた幾何距離の二乗と、RSSIから求めた
// 実測レンジ(measuredRangeCm)の相対許容帯 [measured*(1-r), measured*(1+r)] を整数のまま
// （平方根/除算を避けて）比較する。r = tolNum/tolDen。
func rssiConsistencyOk(api frontend.API,
	droneLat, droneLon, droneAlt,
	targetLat, targetLon, targetAlt,
	measuredRangeCm frontend.Variable) frontend.Variable {

	dLat := absDiff(api, droneLat, targetLat)
	dLon := absDiff(api, droneLon, targetLon)
	dAlt := absDiff(api, droneAlt, targetAlt)

	latScaled := api.Mul(dLat, latCmNum)
	lonScaled := api.Mul(dLon, lonCmNum)
	altScaled := api.Mul(dAlt, geoDen)

	claimedDistSq := api.Add(
		api.Mul(latScaled, latScaled),
		api.Mul(lonScaled, lonScaled),
		api.Mul(altScaled, altScaled),
	)

	const lower = tolDen - tolNum
	const upper = tolDen + tolNum

	base := api.Mul(measuredRangeCm, geoDen)
	lowerSq := api.Mul(api.Mul(base, lower), api.Mul(base, lower))
	upperSq := api.Mul(api.Mul(base, upper), api.Mul(base, upper))

	claimedScaled := api.Mul(claimedDistSq, tolDen*tolDen)

	geLower := cmp.IsLessOrEqual(api, lowerSq, claimedScaled)
	leUpper := cmp.IsLessOrEqual(api, claimedScaled, upperSq)
	return api.Mul(geLower, leUpper)
}
