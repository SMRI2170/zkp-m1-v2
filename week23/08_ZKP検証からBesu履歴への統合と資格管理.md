# ① ZKP→Besu接続・④セッション/資格管理：ローカル統合

2026-10-12。実機を使わず、既存の合成Groth16 fixtureを**現在のコードで再検証**して接続した。
今回setup/proveを再実行していない。以前のA/B/C独立プロセス生成の成果を意図的に保持・検査している。
[結果](logs/integrated-history.json)、[受信側の信頼設定検査](logs/receipt-trust-anchor-check.json)、
[実装・手順](poc/integrated-history/README.md)。#42の統合部分をローカル完了、#29全体はIN_PROGRESS。

## 同じデータフローとして成立した範囲

1. 個別Groth16 3本（A/B/C）、または一般再帰Cの最終proofを検証対象にする。
2. **3つの別Pythonプロセス**がそれぞれ同一証拠集合を検証する。各プロセスはGoのnative Groth16 verifierを呼ぶ。
   個別集合の場合は各検証者が3本すべてを検証する。最終再帰の場合はCの1本を検証する。
3. proof/public/VKのSHA-256、実際にverifyした公開入力、session/policy/member/count/statusをcanonical JSONへ拘束する。
   受信側が固定したVKを使い、送信者が別ディレクトリに置いたVK pinは使用しない。
4. 3検証者のcanonical receipt一致後に、ローカルfixtureの3観測者鍵で同じenvelopeへ署名する。
   署名と検証プロセスは同一ホストのharness管理下であり、独立組織や実端末の鍵保護ではない。
5. Besuへ渡すのはreceiptのSHA-256、公開メタデータ、3署名。**VK/proof bytes/assignmentは渡さない**。
6. 4validatorのaccepted値・receipt blockHash/status・全イベント履歴の一致をassertする。

受け渡しsandboxに入るのはproofとpublicだけ。VKは受信側のローカル信頼設定を参照する。
setupのPKや他者の元assignmentを読み込まない。
この実験は旧Sonobeの生Witness転送やFinalBNV2 EVM再帰検証の実証ではない。

## session・署名の型

実験専用session ID：

```
keccak256(abi.encode("week23-history-v1", uint256(1),
                    proofSession, claimedRID, bucket, policy, uint64(epoch)))
```

署名payload：

```
keccak256(abi.encode("week23-receipt-signature-v1", chainId, contractAddress, Envelope))
```

Keccak bytes32をBN254 scalarへ変換しない。
Envelopeはsession/evidence/epoch/deadline/proofSession/claimedRID/bucket/policy/members/consistent/suspicious。
JavaScriptとSolidityのsessionId/payloadが一致することを実行時にassertした。
このschemaはWeek23の実験専用で、#29のMode C-v1や公開ABI正本を置き換えていない。
Go/Rust/端末のクロス言語golden vectorは残る。

回路の固定値：version=1、proofSession=777、claimedRID=424242、bucket=100001、policy=20261011。
動的に変えたのは外側の資格epochであり、回路の動的参加を実装したわけではない。
観測の鮮度は合成clock=100002で検査し、提出envelope期限はBesuのblock timestampで検査する。
古い合成bucketを現実の観測時刻として扱わない。

## 実行結果

| 正常経路 | proof＋public | offchain検証者ごとの時間 | submit→4-node receipt一致 | Gas |
|---|---|---|---|---|
| 個別proof 3本 | 1,392 bytes | 87.9–102.4 ms | 2,026.95 ms | 86,906 |
| 再帰C最終proof | 496 bytes | 33.1–33.8 ms（epoch 2提出） | 2,128.19 ms | 86,947 |

各行は単回、p50/p95ではない。offchain時間はPython→Go子プロセス起動/読込みを含み、prove/setupを含まない。
共同署名は3×65=195 bytes。以前のEd25519 baselineの192 bytesとは方式が異なる。
Gasは署名/資格/期限/初回書込みの値であり、Groth16検証Gasではない。
各段階の数値を分離し、全工程のp50や通信量・RAM比較を推定して埋めない。

受信側で拒否した6ケース：proof改竄、public改竄、別proof session、別proof policy、期限切れ/未来の合成観測。
オンチェーンで拒否したケース：再提出、別session、別policy、期限切れenvelope、旧epoch、署名者不足、
重複署名者、未登録署名者、署名後のevidence変更、資格から削除された署名者、失効済み署名者。

epochを1→2→3→4と更新し、観測者1名を置換した。
同じBから生成したnormal/outlierの**両方のC proofをnative verifyしたうえで**競合提出し、1件だけが成功した。
二重署名の2つのenvelope/signatureを提出すると、同一署名者のequivocationを検証し、資格を失効させた。
正常・不正常を含む20トランザクションのreceipt一致、成功3件のDecisionと資格イベントの全履歴一致を確認した。
永続投票ファイルを読む別プロセスは競合への再投票を拒否した。故意の二重署名は別の攻撃fixtureとして作った。

## 保証と残件

チェーンが検証するのは署名・ドメイン・資格・期限・スロット唯一性である。
**Groth16の有効性はオフチェーン検証者の証言に依存する**。鍵を持つ3者が検証せず虚偽へ署名すれば、契約はその虚偽を検知できない。
資格authorityはローカルの単一管理者であり、資格変更や提出排除が可能。3/3署名は1人の不参加で停止する。

proofStatus=VALID_OFFCHAIN、ridAuthStatus=UNVERIFIED、physicalRisk=UNKNOWNを区別した。
RFの真実性、DRIP trust chain、実UAV同一性、観測者ハードウェア認証は証明していない。
ローカル資格試験の完了を#29全体の完了としない。資格authorityの悪意、状態機械の全遷移、
動的回路membership、クロス言語ABI、匿名性/推論耐性、実運営主体の独立性は残る。
