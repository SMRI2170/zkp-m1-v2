// Package completeness は「集約が提出集合を全部含めた（間引いていない）」ことを証明する
// 網羅性(包含性)の核（#3b 検閲対策）。
//
// 提出者/DA 層が集約前に「提出集合」を SubmissionRoot（含める全 device_pubkey の
// Merkle ルート）としてコミットしておく。集約は自分が含めた葉から同じ Root を再現できる
// ことを証明し、契約は SubmissionRoot == DA コミット値 を確認する。
// 集約者が1件でも間引くと Root が変わり一致しない → 間引き(検閲)を検知・拒否できる。
package completeness

import (
	"math/big"

	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"

	"uav/aggregator/membership"
)

const (
	N    = 3 // 集約する（＝提出集合の）端末数
	PadN = 4 // N 以上の最小の 2 冪
)

// Circuit: 含めた N 台の device_pubkey から作る Merkle ルートが SubmissionRoot に一致する。
type Circuit struct {
	SubmissionRoot frontend.Variable `gnark:",public"`
	Ax             [N]frontend.Variable
	Ay             [N]frontend.Variable
}

func (c *Circuit) Define(api frontend.API) error {
	leaves := make([]frontend.Variable, PadN)
	for i := 0; i < N; i++ {
		l, err := membership.Leaf(api, c.Ax[i], c.Ay[i])
		if err != nil {
			return err
		}
		leaves[i] = l
	}
	for i := N; i < PadN; i++ {
		leaves[i] = 0 // 0 パディング（回路外と一致）
	}
	cur := leaves
	for len(cur) > 1 {
		next := make([]frontend.Variable, len(cur)/2)
		for j := range next {
			h, err := mimc.NewMiMC(api)
			if err != nil {
				return err
			}
			h.Write(cur[2*j], cur[2*j+1])
			next[j] = h.Sum()
		}
		cur = next
	}
	api.AssertIsEqual(cur[0], c.SubmissionRoot)
	return nil
}

// Root は回路外で提出集合ルートを計算する（DA へコミットする値・回路と一致）。
func Root(axs, ays []*big.Int) *big.Int {
	leaves := make([]*big.Int, PadN)
	for i := 0; i < N; i++ {
		leaves[i] = membership.MimcHash(axs[i], ays[i])
	}
	for i := N; i < PadN; i++ {
		leaves[i] = big.NewInt(0)
	}
	cur := leaves
	for len(cur) > 1 {
		next := make([]*big.Int, len(cur)/2)
		for j := range next {
			next[j] = membership.MimcHash(cur[2*j], cur[2*j+1])
		}
		cur = next
	}
	return cur[0]
}
