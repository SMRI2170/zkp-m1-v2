# 次の実装で満たすbinding relation（設計案、未実装）

random foldの成功だけでは、同じsessionのIVC継続にならない。
既存native verifierを無視せず、blinded accumulatorが元の検証済み履歴に由来することを追加で証明する必要がある。
以下は要件の切り分けであり、NovaBlindFoldの実装や安全性証明ではない。

## 公開statement

`protocolVersion / verifierConfigHash / circuitHash / session / policy / memberEpoch /
i / z0 / zi / blindedPrimaryInstance / blindedCycleFoldInstance / transcriptDomain`。
bytes32やcurve fieldのencodingを明示し、異なるfieldへの暗黙変換をしない。
ゼロ知識binderのVKは受信側の信頼設定に固定し、送信者のVKは受理しない。

## 証明すべき関係

- 元のfull IVC proofが、そのversion/config/session/i/z0/ziでverifyされる。
- 最新incoming witnessを含む証拠を正しくfoldし、引継ぎに生の元incoming witnessを残さない。
- primaryとCycleFold側のblindingを区別し、両者の新instance/commitment/関係が正しい。
- random foldのtranscriptとcommitment openingがstatementに拘束され、元/新の関係を取り違えない。
- next Proverが受け取るmasked witnessが、証明された新instanceのopeningと一致する。
- 追加binderの証明がゼロ知識で、元witness/私的maskをその証明に露出させない。
- 次段のaugmented circuitがbinderを検証してから継続する。hostだけで検証し、その結果を回路へ拘束しない方式は同じ暗号的保証にならない。

## 否定・privacyゲート

wrong session/policy/version/config/step/count、primary/CycleFoldのmix、target instance変更、
binder改竄、sender-owned VK、mask再利用、古いproofの付け替え、無検証でのresumeを検査する。
元canaryのfield/byte一致だけでなく、public transcript＋transferからの逆算も検査する。
randomnessのuniformityや全体ZK性は、canary検査だけでは証明できない。

既存のhash/relation/opening検査を省略する変更は採用しない。
旧setupを新しいbinding circuitへ流用しない。新しい回路・依存・全artifact hashを固定し、
必要なsetup/proofはowner-only ignored領域で保持してnativeで検証する。
使い捨てGroth16 VK/proofはGit/チェーンへpublish/deployしない。
