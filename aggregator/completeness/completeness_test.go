package completeness

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/test"
)

func TestCompleteness(t *testing.T) {
	assert := test.NewAssert(t)

	// 提出集合 = 3 台。DA へ SubmissionRoot をコミット。
	axs := []*big.Int{big.NewInt(1001), big.NewInt(1002), big.NewInt(1003)}
	ays := []*big.Int{big.NewInt(2001), big.NewInt(2002), big.NewInt(2003)}
	root := Root(axs, ays)

	// 正: 提出集合を全部含めた → Root 一致で通る
	valid := &Circuit{SubmissionRoot: root}
	for i := 0; i < N; i++ {
		valid.Ax[i] = axs[i]
		valid.Ay[i] = ays[i]
	}
	assert.SolvingSucceeded(&Circuit{}, valid, test.WithCurves(ecc.BN254))

	// 否: 1件を別の端末に差し替え（＝間引いて別を入れた）→ Root 不一致で失敗
	bad := &Circuit{SubmissionRoot: root}
	*bad = *valid
	bad.Ax[2] = big.NewInt(999999) // 提出集合に無い端末
	assert.SolvingFailed(&Circuit{}, bad, test.WithCurves(ecc.BN254))
}
