# #41：秘密Witnessを共有しないA→B→C

状態: IN_PROGRESS（旧版の生状態と最終ZK層を確認し、一般再帰fallbackを実行）。

最終ZK proofと継続用proofは別物。生IVCProofの転送だけでこのタスクを完了としない。
第一候補の型/API調査後、一般再帰による独立SNARKの固定VK検証をfallbackとして評価する。
実在する署名付きログや3個別proofの相互検証は比較対象Aであり、再帰PCD成功とは呼ばない。

## 共通statement案（実装前の仕様）

version、session識別子、claimed RID、timeBucket、policyHash、memberBinding、
used-member集合、consistentCount、suspiciousCount、stepCountを拘束する。
原観測は各参加者のprivate入力。時刻/replayの拒否は外部の現在時刻・使用済みsession状態にも依存する。
公開count/参加集合はリンク可能性を持ち、元Witness非共有から匿名性までは導けない。

否定テストは前段proof改竄・別session/RID/policy・期限切れ・replay・重複member・虚偽count。
途中離脱・並列追加・分岐は、証明の妥当性と全体の唯一の確定履歴を分けて評価する。
端末移植とEVM最終検証は独立したゲート。

## 実行前の資源確認

このホストは16GiB物理RAM、swap約4.89GiB使用・空き約0.61GiB（開始時）。
既存一般再帰実験は大きなsetupでswap増大が記録されている。
現在の実行は小規模旧Novaの1jobビルドまで。一般再帰setupは安全なheadroomを確認してから実行する。
`pcd3 --stage=plan` はhost preflightであり、秘密非共有3段proofやFinalBNV2 EVM成功の証拠ではない。

## 実装と現在の実行範囲

一般再帰fallbackを [poc/private-pcd](poc/private-pcd) に新規実装した。
元のchainpocと同じ相対許容帯関係を使い、前段のGroth16 proofと公開入力を回路内で検証する。
前段VKは回路定数。fixtureのversion/session/RID/bucket/policy、3人の固定member順と累積countを拘束する。
転送物は前段のproof/public、trusted setup由来のVK。元private assignmentは保存・転送しない。
このPoCは固定3段・固定sessionであり、任意参加/任意深さのPCDや実機入力認証ではない。

Aのproof生成・verifyは成功。Bのcompileは1,253,359制約で成功。
B初回はsetup後のWitness作成で共有オブジェクト由来のエラーになった（約307秒、peak RSS約1.89GiB）。
これは今回のコードの不具合であり、メモリ不足や方式の不可能性ではない。
placeholderテンプレートと実assignmentを分離して修正し、再実行中。
preflightではWitness作成まで確認する。再帰回路のBSB22 commitment hintは実proverが提供するため、
未setupのraw `IsSolved` での成功を要求したり、dummy hintで代用したりしない。
実proverの成功と最終verifyを最終判定に使う。

旧版の最終ZK proofは生成/verifyに成功した。一方、[API probe](logs/zk-resume-api-probe.log) は
`from_ivc_proof` の入力型不一致（E0308）を再現した。
これはそのAPIへ直接渡せないという限定的結果であり、追加実装や他方式の不可能性ではない。

初回時点の残件: 外部資格レジストリ、永続expiry/replayストア、別観測の分岐proof、端末移植。追加結果は後節。
未実証: FinalBNV2/EVM。この一般再帰PoCは既存V2実装と同一構成ではない。

## Bの再実行結果

[Bログ](logs/private-pcd-2.log) と [資源測定](logs/private-pcd-2-resource.json) はexit 0。
setup 286,897ms、prove 16,050ms、verify 1,972µs、peak RSS 2,820,210,688 bytes。
公開状態はversion=1 / session=777 / RID=424242 / bucket=100001 / policy=20261011 /
member mask=3 / consistent=2 / suspicious=0 / steps=2。元A assignmentを読み戻す処理はない。
session・RID・policy・duplicate member・countの不正assignmentは実Groth16 proverで拒否した。
この結果は回路内の前段proof検証を含む、有限2段の一般再帰の成功。
旧Nova生IVCProofのWitness共有とは異なる経路である。

Cは実行途中に1,706,641制約でcompileとWitness作成を確認した。最終結果は次節に記載する。
expiry/future/replayは [host policyログ](logs/private-pcd-host-policy.log) の合成時計で拒否を確認した。
これらは外部状態に依存するhost gateであり、proofだけでグローバルreplayを防止したとは主張しない。

## Cの結果と限定的な成立判定

[Cログ](logs/private-pcd-3.log)、[資源測定](logs/private-pcd-3-resource.json)、
[独立した最終verify](logs/private-pcd-final-verify.log) は成功。
setup 371,187ms、prove 19,791ms、verify 1,943µs、peak RSS 3,368,435,712 bytes。
最終状態はmember mask=7 / consistent=2 / suspicious=1 / steps=3。session等の5項目はA/Bと一致。
三つのGo prover processで有限3段の一般再帰を実行し、CのproofでBのproof、さらにAのproofを回路内検証した。
**この固定fixture・固定3段構成では、先行者の元assignmentを転送せず証明を継続できた。**

[転送検査](logs/private-pcd-transport.json): Aのproof+publicは464 bytes、B/Cは各496 bytes。
前段の合成private scalarに対するexact-byte canary一致は0件。private assignmentのキャッシュは作成しない。
各段のproofの1byte改竄はnative Groth16 verifyで拒否された。
canary検査は漏洩検査であり、暗号学的ZK安全性の証明と区別する。

[署名付き転送検査](logs/private-pcd-signed-transport.json) は既生成proofを使う別harness。
3個の独立Python workerが元assignmentを読み込まず、先行者の署名とproofを検証して自段のpacketを署名した。
暗号学的proof生成のGo processと、転送検査のPython processを同一実行と呼ばない。
payload/session/policyの改竄、合成時計の期限切れ、hostのseen状態によるreplayを拒否。
テスト署名鍵はignored owner-onlyディレクトリに保存し、公開・Git追加しない。
同じproofの署名付きenvelopeを二重発行すると両方有効だった。これは別観測の分岐proof生成を実験した結果ではない。

判定は「有限3段Go一般再帰のローカルPoCとして成立」。
旧SonobeのZK folding引継ぎAPI、動的member登録・匿名性、実機RF入力の真正性、任意深さPCD、
端末移植、FinalBNV2/EVMの成立まで拡大しない。Issue #41全条件をDONEにしたという意味ではない。


## 別観測の分岐proof・永続受信ポリシー：追加実行

同じB証明を入力に、別Go processのCでnormal（range=300）とoutlier（range=5000）の2本を生成し、
両方のnative最終verifyに成功した。公開結果はそれぞれ member=7 / consistent=3,suspicious=0 と 2,1。
[normal](logs/private-pcd-fork-normal.log)、[outlier](logs/private-pcd-fork-outlier.log)。
元assignmentの保存・転送は行わず、前段proof/publicと当段の合成観測だけを入力にした。

既存の使い捨てlocal setup fixtureは明示的に検査して使用した。
元main/relations/go.mod/go.sumのsource/dependency hash一致、現在ソースから再compileしたCCSと保存CCSの**byte完全一致**、
前段proofの検証、使用artifact全hashの記録、生成proofの元VKによる最終verifyを確認。
setup/proof/private fixtureはignored owner-only領域で保存し、release keysとして使用しない。
これは `pcd3` のsetup-cache実装ではなく、この固定3段fixtureの追加実験である。
normal/outlier proveは約24.775/19.506秒、setupを含まない（loaded PKの検査/読み込み時間も別）。
実行が一部重なった共有Mac測定なので、専用ホストでの性能分位値ではない。

`persistent_gate.py` は固定ローカルrosterのEd25519署名とtrusted stage VKによる実proof検証を行い、
SQLiteの主キー(session/policy/RID/bucket/stage)とtransactionで受理を永続化する。
合成clockで期限/futureを拒否し、受信process再起動後のreplayを拒否した。
A受信後Bが提出しない場合、Cのcryptographic proofが正しくてもhostの前packet受付がないため停止する。
既存B証明が手元にあれば別C proverへ引継ぎ可能であるが、B段そのものを飛ばす方式ではない。

異なるC観測で生成した2本のproofを同じB parentへ署名し、**2つの同時受信process**で同じDBへ提出。
両者のproof/署名は正しいが、transactionで1件のみ受理、他方は競合/replayとして拒否した。
独立した2個のDBには別々のC分岐を受理できることも実行で確認した。
[受信テスト全結果](logs/private-pcd-persistent-gate.json)。

この検査は固定ordinal Cからの2つの競合提出であり、任意の異なる2観測者の動的参加を実装したものではない。
SQLiteは単一受信者内の競合制御を与え、複数独立主体の合意・グローバルreplay/fork拒否を与えない。
外部資格registry、任意参加者/離脱時の順序再構成、Rust ZK-folding、Pi/Pixel移植、FinalBNV2/EVMは残る。

## 2026-10-12：新しい観測・証明で秘密非共有チェーンを再実行

[10](10_HyperNova実行と最新Sonobe安全性と秘密引継ぎ.md)で、同じ固定回路/検査済みsetupのもと、新しい合成観測でA/B/Cを独立processからproveした。
全source/artifact hash照合と現在ソースからのCCS再構築一致を必須とした。前段からproof/publicのみ読み、private assignmentは保存/転送しない。
B prove 18.449秒、C 24.106秒（単回）、C最終native verify成功、転送464/496/496 bytes。
Cの公開9入力改変は実verifierで全件拒否。exact canary照合はBへのA、CへのA/Bが0件。
HyperNova/NovaBlindFoldの秘密継続は別の未成立課題であり、この成功で代替名を付けない。
