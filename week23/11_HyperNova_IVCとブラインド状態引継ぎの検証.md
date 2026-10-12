# HyperNova IVC実行とblinded stateの継続ゲート

2026-10-12。[10](10_HyperNova実行と最新Sonobe安全性と秘密引継ぎ.md)で残ったHyperNova固有の秘密継続を追加検証した。
固定branch `9c4e61f8`＋10の依存/MSM互換patchを使用し、今回library/verifierは変更していない。
[結果](logs/hypernova-handoff-probe.json)、[コード/再現](poc/hypernova-handoff/README.md)、[固定hash](manifests/hypernova-handoff.json)。

## 実行できたもの

compile確認だけだったHyperNova IVCを実行した。
上流のHyperNovaNovaIVC/HyperNovaOvaIVCテストは各20step、両方成功、失敗/ignoreなし。
[上流IVCテストログ](logs/hypernova-ivc-tests.log)。これは40stepの単一processテストで、独立観測者の実証ではない。

追加toy回路は7非zero秘密入力からcount+1し、公開stateはsession/RID/bucket/policy/count。
同じIVC engineで3stepをprove/verifyし、count=3を確認した。
各stepのincoming witnessには当該入力7canaryが残る。上流main/一般再帰の結果とは別に、HyperNova branchでも確認した。

## random foldの成功とIVC継続の失敗を分離

現在のrunning LCCCS stateと、`HyperNovaKey::sample`で生成してdecide_runningを通したrandom LCCCS stateを
`FoldingSchemeProver<2,0>`でfoldした。
新しいrunning witness/instanceはdecide_runningとNIMFS verifierの両方が成功し、出力instanceが一致した。
新running witness中の元canary完全一致は0件。**これだけではゼロ知識性を示さない**。

| ケース | 実際の結果 |
|---|---|
| 元の3段IVC | verify成功 |
| random foldされたLCCCS | decide_running/NIMFS verify成功 |
| random-fold出力をIVC Proofのrunning pairへ差替え | `IVCVerificationFail` |
| その無効状態から次のproveを呼ぶ | proveはproofを返したが、**最終verify失敗** |
| incomingの公開hashだけ、新running stateに合わせて更新 | `FoldingError(ArithError(UnsatisfiedAssignments(...)))` |
| 元incoming witnessを全zeroへ置換 | full IVC verify失敗 |
| session/RID/bucket/policy/countを各々改変 | 全5項目でfull IVC verify失敗 |

prove()の戻り成功を検証済み継続とは扱わない。受信時の明示的verifyと、最終verifyが必要である。
この未検証resumeの失敗を隠したり、hash/relation/opening checkを無視してgreenにする変更はしていない。

## なぜそのまま引き継げないか

既存IVCではincoming public inputが
`H(ppHash, i, z0, zi, primaryRunningInstance, cycleFoldRunningInstance)` に拘束される。
random foldでprimaryRunningInstanceを変更すると、元incoming inputは別のstateを指すためhash gateで拒否される。
公開hashだけを更新すると、incoming witnessが元のaugmented circuitのassignmentなので、今度はrelation検査が拒否する。

またprimary running pairだけをmaskしても、最新incoming witnessを同梱したままならその秘密入力は読める。
「canaryが新running witnessから消えた」「valid CCS foldができた」「同じIVC履歴として秘密非共有で継続できた」は3つの別の判定である。

## 次の実装箇所を具体化

[追加binding relation案](poc/hypernova-handoff/handoff-relation.md)に、必要なstatement、relation、否定テストを記した。
**元の検証済みIVC→blinding処理→新しいmasked state**を結び付けるゼロ知識binderと、
それを次のaugmented circuitで検証する経路が必要である。
単に受信hostが検証したことにして、回路ではそのbindingを無視する変更は同じ保証にならない。
primaryとCycleFold両側、最新incoming、session/step/transcript、trusted VKを同時に拘束する必要がある。

このrelation案は未実装・未証明。NovaBlindFoldの完成実装やA→B→C秘密非共有の成立例とはしない。
今回確定したのは「通常HyperNova IVCは実行できる」「random foldは検証できる」
「既存Proofへの単純差替え/公開hash変更では、検証済み秘密継続にならない」という具体的な境界である。

秘密非共有の成立例は10の一般再帰方式を維持する。
HyperNova固有の秘密継続を不可能とは結論せず、追加binder/継続回路の課題として#39/#41へ記録する。

後続：[12のFolding binder実装](12_HyperNova_Folding_binderの回路実装と検証.md)で、
SumCheckと非ネイティブ群演算を回路化し、正常充足と6件の改竄拒否を確認した。
Groth16はsetupまで成功し、prove中にswap上限で停止。元IVC履歴binderと秘密継続は引き続き未完了。

## 測定範囲

追加probeは単一process。key生成1,288 ms、3stepのprove＋verifyは226/443/464 ms、random fold＋検証350 msの単回。
一般再帰のGPS/RSSI回路とはrelation/測定区間が違うため、性能倍率を出さない。
事前に16 GiB/free 56%/swap used約5.20 GiBを確認。cargo -j 2、上流test-threads=1。
key/proof/witnessはRAM内、Gitには値を入れずphase/件数/公開可能なerrorだけを保存した。
実キャプチャ・実位置・秘密観測者鍵・使い捨てGroth16 VK/proofのpublish/deployはない。

既存Python 61件、Go、contracts 48件も成功。研究PoCであり、DRIP、RF真値、実UAV同一性、hardware認証は保証しない。
