# #39：Nova系実装とZK引継ぎAPIの調査

調査日: 2026-10-11。状態: IN_PROGRESS。ソース固定情報: [manifest](manifests/sources.json)。

## 確認した事実

旧PoCの `nova_poc/sonobe/` は存在せず、追跡コードには依存workspaceのCargo.lockもない。
`week20/08` は shallow cloneのHEADと手作業パッチを指定するだけで、当時のcommitを保存していない。
したがって旧実行版の完全一致再現は未確認。今回の旧API再現には公開履歴の
`9b7dd34f0e0341046baeabc6f900f5ee63007f18` を採用した。これは当時の版を特定したという意味ではない。
arkworks 0.6.0移植と2回のscalar_mul_leへの置換を別パッチとして保存する。

| 機能 | 旧API再現版 | Sonobe main `7f042351` | 別ブランチ/他実装 | 実行状況 |
|---|---|---|---|---|
| Nova+CycleFold | `Nova` / `FoldingScheme` | `CycleFoldBasedIVC` / `IVC::prove` | Microsoft `RecursiveSNARK` | 旧版A/B・両Hを実行済み |
| 状態復元 | `from_ivc_proof` | stateとproofを`IVC::prove`へ渡す | Microsoft serde復元・`prove_step` | 秘密非共有とは別問題 |
| 生Witness | `IVCProof.W_i/w_i/cf_W_i` | `Proof`の6要素にrunning/incoming witness | Microsoft serialized `r_W_primary`等 | 含有をソースで確認 |
| 最終ZK層 | `RandomizedIVCProof` | mainのIVCに同名APIなし | Microsoft `CompressedSNARK::prove/verify` | 継続可能性は未実証 |
| HyperNova | 旧ツリーに実装あり | mainへ未統合 | `revamp/hypernova`のコード存在確認 | ブランチ版の動作は未確認 |
| ProtoGalaxy | 旧ツリーに実装あり | mainへ未統合 | `revamp/protogalaxy`のコード存在確認 | 同上 |
| EVM Decider | `decider_eth` | mainへ未統合 | `revamp/decider`にLegoGroth16・Solidityテンプレート | 最終証明生成/EVM検証は未実施 |

「mainへ未統合」は「公開コードがどこにもない」を意味しない。
ブランチHEADは [sonobe-branches.txt](manifests/sonobe-branches.txt) に固定した。
API構造の照合はソース解析であり、ビルド・実行成功の主張ではない。

旧版の `from_ivc_proof` は状態を展開して回路を再構築し、`verify`を呼ばずに返す。
新mainの `Proof` もWitnessを含む。公開フィールドやserdeの可視性制御はZKを与えない。
Microsoftの `CompressedSNARK::prove` はランダムinstanceをfoldして圧縮し、
`verify`がある一方、圧縮proofを`RecursiveSNARK::prove_step`へ渡すAPIは今回読んだ型にはない。
`evm` featureのシリアライズ対応だけから、今回のEVM Deciderが完成しているとは判断しない。
[Microsoft公式実装](https://github.com/microsoft/Nova) のMicroNova部品とexperimental NeutronNovaを区別する。

## 論文と実装の区別

| 構成 | 原資料/版 | 研究上の位置づけ | この調査で確認したコード |
|---|---|---|---|
| Nova | [2021/370](https://eprint.iacr.org/2021/370) | uniform IVC | Microsoft / Sonobe |
| SuperNova | [2022/1758](https://eprint.iacr.org/2022/1758) | non-uniform IVC | [Arecibo](https://github.com/lurk-lang/arecibo) は候補、未ビルド |
| HyperNova | [2023/573](https://eprint.iacr.org/2023/573)、2026-02-20の改訂説明 | CCS・multi-folding・NovaBlindFold | Sonobe旧ツリー/開発ブランチ、論文全体の実装と同一視しない |
| KiloNova | [2023/1579](https://eprint.iacr.org/2023/1579)、2026-02-17の第6版 | preprocessing SNARK / multi-predicate PCD | この取得範囲では著者が結び付けた公開実装を未特定 |

KiloNovaの現行題名は **Preprocessing Folding-based SNARKs for Machine Executions**。
旧検索結果の「Zero-Knowledge PCD from Non-Uniform Multi-Folding Schemes」と同一版として扱わない。
同名の天文・別ソフトウェア検索結果を暗号実装の証拠にしない。
HyperNovaの旧「付録D.4」という参照は現行改訂ではsection 7への移動を確認した。

## 秘密保護型引継ぎの候補とゲート

[Sonobe旧ZK文書](https://sonobe.pse.dev/usage/nova-zk.html) のUse-case-3は最後のIVC状態を
検証するZK proofであり、以降foldしない用途である。Use-case-1のアプリ層randomized instanceと、
最終ZK proofから別proverが継続することを同一視しない。

1. `H=true` の生 `IVCProof` 転送は候補から除外する前に #40 のcanary実験で可視性を確認する。
2. `RandomizedIVCProof` から`from_ivc_proof`へ直接復元できるか、型/APIを照合する。
   できない場合は失敗箇所を記録し、ライブラリ全体の不可能性とは言わない。
3. fallbackは前段の独立Groth16 proofを次段の回路で固定VK検証する有限3段再帰。
   転送はproofと公開statementだけとし、前段private assignmentを渡さない。
   これはfoldingのZK引継ぎAPIではなく一般再帰SNARKである。
4. 秘密保護・session/policy/member拘束・重複・replayをテストし、実測後に端末移植へ進む。

未完了: Arecibo/論文リンクからの著者実装追跡、原論文PDFの式と各APIの詳細対応、
新ブランチのビルド、端末要件の評価。有限3段の秘密非共有候補の実行は #41 で成功済み。

## 実行による追加確認

旧版H=trueの `RandomizedIVCProof::new` と `verify` はローカルで成功した。
`W_i_prime` に7つのcanaryの直接一致は0件。これはcanary検査でありZK安全性の証明ではない。
[実行ログ](logs/witness-zk-final.jsonl) の生成は約917ms（単回）。
生IVCProofでは両Hとも元canaryを直接受信できた。
したがって「H=trueにすれば元Witness非共有で継続できる」という候補は、この転送形式では要件未達。
最終ZK proofの生成自体はできているので、ZKを生成できないという結論でもない。


## 追加調査：APIの入力・出力と継続責務

2026-10-11に #39 を継続。以下は固定commitのソース確認である。

| 実装/API | 入力 → 出力 | 次proverへの転送 | 今回の判定 |
|---|---|---|---|
| 旧Sonobe `from_ivc_proof` / `prove_step` | 生 `IVCProof` + pp/vp → Nova状態 → 次IVCProof | running/incoming/CycleFoldのWitnessを含む | 動作確認済み、元Witness非共有要件を満たさない |
| 旧Sonobe `RandomizedIVCProof::new/verify` | 完全なNova状態 + RNG → randomized最終proof | `W_i_prime` とCycleFold witness等 | 最終verifyは成功。これを生IVC状態へ復元するAPIは未提供（調査範囲内） |
| Microsoft Nova `CompressedSNARK::prove` | pp + pk + `RecursiveSNARK` → 圧縮proof | ランダムfold後のSNARK/public state | 最終ZK用途。`prove_step(&mut RecursiveSNARK, pp, circuit)`への逆変換APIは未提供（調査範囲内） |
| Arecibo SuperNova `RecursiveSNARK::prove_step` | 複数circuit用生状態 + pp + primary/secondary circuit → 更新状態 | `r_W_primary: Vec<Option<RelaxedR1CSWitness>>`, secondary witness等 | non-uniformの実装あり。秘密非共有引継ぎとは別機能 |
| Arecibo SuperNova `CompressedSNARK::prove` | pp + pk + `RecursiveSNARK` → batched圧縮proof | SNARK/public instance/program counter | 圧縮proofから生状態へ戻すAPIは調査範囲内にない。Microsoft最新版と同じZKランダム化を持つとは仮定しない |
| Week23 Go一般再帰 | 前proof + 公開9項目 + 当段秘密観測 → 当段proof | proofとpublicのみ | 固定3段A/B/C生成・最終verify済み。任意段数foldingではない |

参照箇所:
- [旧Sonobe Nova](https://github.com/privacy-ethereum/sonobe/blob/9b7dd34f0e0341046baeabc6f900f5ee63007f18/folding-schemes/src/folding/nova/mod.rs)、[zk.rs](https://github.com/privacy-ethereum/sonobe/blob/9b7dd34f0e0341046baeabc6f900f5ee63007f18/folding-schemes/src/folding/nova/zk.rs)。Use-case-1はアプリ層で実装するという説明で、対応する完成済み分散resume APIではない。Use-case-2はDecider回路の変更を要するとの記述。
- [Microsoft Nova](https://github.com/microsoft/Nova/blob/01b1e2d662a847ed7029770ecbaf6687398899dd/src/nova/mod.rs): `RecursiveSNARK` line 321、`prove_step` line 459、`CompressedSNARK::prove` line 796。ランダムinstance生成 → 2系統のfold → commitmentのderandomize → 2つのSNARK証明という最終圧縮経路。
- [Arecibo SuperNova](https://github.com/lurk-lang/arecibo/blob/8997d733aa69c3b6db5a44e06f7c0f74ad315d6f/src/supernova/mod.rs): 生状態line 484、`prove_step` line 746。[圧縮](https://github.com/lurk-lang/arecibo/blob/8997d733aa69c3b6db5a44e06f7c0f74ad315d6f/src/supernova/snark.rs): line 95、178。公式Microsoft実装とは別fork。

### MicroNova / NeutronNova

Microsoft固定版のREADMEはMicroNovaの**部品**としてHyperKZGとMicroSpartan (`src/spartan/ppsnark.rs`) を説明する。
この部品の存在から、Week23 sessionを受け取るEVM Deciderやクロスprover継続が完成したとは判断しない。
NeutronNovaは `experimental` featureで、`src/neutron/mod.rs` line 2にチェック不足の注意書きがある。
`new/prove_step/verify` はあるが、これを安全性確認済みの代替として採用しない。研究用評価の対象にはできる。

### 元Witnessを渡さず継続するために必要な追加実装

Use-case-1のrandom-satisfying instanceを単に生成して渡すだけでは、現在の `from_ivc_proof` の型を満たさない。
foldされた引継ぎinstanceが、session/state・累積結果・前段検証状態に結び付いていることを次段のaugmented circuitで確認する必要がある。
primaryだけでなくCycleFold側の整合性、transcript domain、公開step数、Deciderが証明するrelationを同時に設計する。
これは今ある最終proofのキャストではなく、引継ぎ型・生成/受信検証/次fold・Deciderの追加実装と安全性検討である。
具体的なローカル代替は既に `poc/private-pcd/relations.go` の `Chain.Define` にあり、固定VKで前proofを検証しpublic状態を拘束する。
これは「追加実装すればfoldingが安全」とする証明ではなく、動作済み一般再帰との区別である。

公開session/RID/bucket/member/countおよび連鎖順序は秘匿対象ではなく、proofのZK性とは別にリンク可能性を持つ。
受信者は署名/送信者資格、proof、session/policy、重複・期限を確認し、秘密保護だけで状態検証を省略しない。
合成fixture/schema/toolchainは [manifest](manifests/sources.json) と [#41](04_秘密保護型A_B_C連鎖PoC.md) に固定済み。

### 開発ブランチの実ビルド

`revamp/hypernova` 固定commit `9c4e61f8` を別のignored directoryへ展開し、ソース無変更で
`cargo +stable test --release -j 2 -p sonobe-fs hypernova -- --nocapture` を実行した。
arkworks 0.5系の固定forkと最新0.6系git依存が混在し、`sonobe-primitives` の型エラーで終了101。テストは走っていない。
[要約ログ](logs/sonobe-hypernova-test.log) にfull logのhashと先頭エラーを保存した。
これは公開コード存在確認から動作確認へ進めた結果で、HyperNova自体が実装不可能という結論ではない。
依存を当該commit時点へ固定する作業は残る。

論文取得範囲: ePrintの改訂ページとKiloNova現行PDFを閲覧。HyperNova/SuperNova PDFの直接取得は403で失敗した。
KiloNova PDFの式(1)はCCS、式(2)–(4)はsum-check、section 5がmulti-predicate PCD、section 6が最終SNARKであり、
これを現在のSonobe/Nova APIの実装済み機能とは対応付けない。ePrintページと取得PDFの範囲では著者実装URLを特定できていない。
式の詳細照合と公開実装追跡が残るため、#39全体はIN_PROGRESSを維持する。


### Arecibo SuperNova：実行結果

commit `8997d733`。初回は依存 `sppark 0.1.15` のnamespace変更でC++ buildが失敗。
`sppark 0.1.6` を固定後、広い `rand = ^0` / `rand_chacha = ^0` が新APIに解決されて失敗した。
`proptest 1.2.0` と `rand_chacha 0.3.1` の固定でrand 0.8系を再現した。
さらに最新Rustがdeny(unused)で報告する不要な括弧/未使用importの2箇所を除去した。
[patch](manifests/arecibo-build.patch) は回路・検証条件・assertを変更しない。

固定lock/patch適用後、`supernova::snark::test::test_nivc_trivial_with_compression` が **1 passed**、114.18秒。
標準テスト内で6 steps、Pallas/BN256/secpの3種×2種の圧縮構成を実行する。
[成功ログ](logs/arecibo-supernova-final-test.log)、[再現手順](poc/api-survey/README.md)、[Cargo.lock](manifests/arecibo.Cargo.lock)。
最初のfilter誤指定で0 testsだった結果もbuild-onlyとして保存し、テスト成功の証拠に使わない。
SuperNova/圧縮が実行可能であることを確認したが、秘密非共有のクロスprover継続はこのテストの対象ではない。

## 2026-10-12：HyperNova実行と継続APIの追加検証

[10の実験](10_HyperNova実行と最新Sonobe安全性と秘密引継ぎ.md)で依存混在を修正し、
固定revamp/hypernova＋明示patchの240fold/関連38テストを実行した。
core arkworks 0.6.0に統一し、MSM APIだけを互換移植。旧失敗ツリー/lock/logは保存。
HyperNovaのCycleFold IVC adapterはcompile確認できた。NovaBlindFoldというAPI名は当該ツリーにない。
Folding/IVC adapterの存在と、元Witnessを共有しない継続APIを分離した。
当該mainのraw Proofは7合成canaryを露出することを両Hで実行確認した。
一般再帰の別方式は新しい観測のA/B/Cで秘密assignment非共有と最終native verifyに成功。
HyperNovaのZK継続成立や全論文照合の完了とはしない。
