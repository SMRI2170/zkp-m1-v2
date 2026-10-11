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
新ブランチのビルド、最小秘密非共有候補の実行、端末要件の評価。

## 実行による追加確認

旧版H=trueの `RandomizedIVCProof::new` と `verify` はローカルで成功した。
`W_i_prime` に7つのcanaryの直接一致は0件。これはcanary検査でありZK安全性の証明ではない。
[実行ログ](logs/witness-zk-final.jsonl) の生成は約917ms（単回）。
生IVCProofでは両Hとも元canaryを直接受信できた。
したがって「H=trueにすれば元Witness非共有で継続できる」という候補は、この転送形式では要件未達。
最終ZK proofの生成自体はできているので、ZKを生成できないという結論でもない。
