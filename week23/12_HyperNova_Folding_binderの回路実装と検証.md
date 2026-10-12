# HyperNova Folding binderの回路実装と検証

2026-10-12。[11](11_HyperNova_IVCとブラインド状態引継ぎの検証.md)の追加binder課題について、
最初の部品として **2→1 NIMFS foldの結び付け** を回路化した。
[コード・再現手順](poc/hypernova-binder/README.md)、[実行ログ](logs/hypernova-binder-prove.log)。

## 回路が検査する関係

上流HyperNovaGadgetのSumCheck／scalar folding検証に、BN254 G1の
`cm_out = cm_0 + rho * cm_1`を追加した。
上流partial verifierのcmは計算hintで、これ単独では群演算を回路内で拘束しない。
通常IVCはCycleFold側でこの検査を担うが、今回のstandalone binderではFqをFr上にemulateした。
群演算はark-r1cs-std 0.6.0のRCB Algorithm 1を参考にした実験実装で、監査済みではない。
infinity、逆元、doubling、scalar multiplication、誤った和、off-curveを単体検証した。
実際のnative NIMFS出力と128bit challengeの群演算が一致し、正常回路は充足した。

publicはversion/session/policy/epoch/stepと、入力2個・出力1個のinstanceを含むGriffin digest。
piとinstanceはprivate witness。toy CCSは4制約で、binderは**2,498,769制約**。
shapeとprotocol versionは固定して拒否し、元の上流relation/verifierは変更していない。

## 実行結果と停止箇所

| 検査 | 結果 |
|---|---|
| native input opening検査・2→1fold・NIMFS verify | 成功（fixtureの事前検査） |
| 正常binderのR1CS充足性 | 成功、21.382秒 |
| target commitment/scalar、input commitment、SumCheck、sigmaの改竄 | digestも再計算して全5件拒否 |
| 元digestを保持したsession変更 | 拒否 |
| 非ネイティブ群演算の単体テスト | 3件成功、ignoreなし |
| Groth16 circuit-specific setup | 成功、鍵生成67.548秒（保存時間別） |
| Groth16 prove／native verify | **prove中にresource guardで停止、未検証** |

[resource記録](logs/hypernova-binder-prove-resource.json)。
Mac Apple M2／16 GiB、実行前free 41%／swap used 4,802.88 MiB。
最大RSSは3,377,053,696 bytes（約3.15 GiB）、開始から停止まで278.623秒。
swap usedが7,692.5 MiBとなり、設定上限7,500 MiBを超えたためSIGTERMで停止した。
RSSの4.5 GiB上限を引き上げたり、検査を削除して完了扱いにする対応はしていない。
終了コード-15はこの停止によるもので、relation不充足やverify拒否による終了ではない。
pk/vkは完成してprivate directoryに残るが、proof/publicは生成されていない。
この結果から、Groth16証明・ゼロ知識binder全体の動作成功は主張できない。
十分なメモリ余力のあるrunnerでprove/verifyを実行することが直近の残件である。

既存Python 61件、aggregator Go、contracts 48件は成功。
CIの通常チェックはこの重いRust証明実験を再実行するものではない。

## 保証の範囲と残件

この部品は **元のIVC履歴が成立していることを証明しない**。
synthetic入力はhostのdecide_runningで事前に検証するが、そのopening／relationの検査はbinder回路に入っていない。
session等のタグはdigestと結び付くが、元IVCのsession等と対応することは未拘束。
今回のsession否定テストは、元digest／既存証明を保持したままタグを変更するケースである。
タグとdigestを一緒に作り直す場合まで、元IVCとの対応なしに拒否できるとは主張しない。
CCSの行列や元のaugmented circuitの履歴を検証しているとはしない。

次の実装には、元のIVCのprimary/CycleFold/incomingの有効性をこの部品へ結び付け、
ブラインド後の状態へのopeningと最新incomingの秘密保護を拘束し、
そのbinderを次段のaugmented circuit内でtrusted VKに対して検証する経路が必要である。
その後、独立A→B→Cプロセスで受信検証・継続・最終検証を実行する。
単一foldの証明成功をHyperNova秘密非共有引継ぎの完成とは扱わない。

## 保存・研究境界

合成データのみ。local disposable setupのpk/vk/proof/publicはignored private directory（0700）とfiles（0600）のみ。
元assignmentは保存しない。GitやBesuへ使い捨てVK/proofを公開・deployしない。
RSS 4.5 GiB／swap used 7,500 MiBのguardで実行し、既存fixtureを上書きしない。
研究PoCであり、DRIP、RF真値、実UAVの同一性、観測者hardwareの認証は保証しない。
