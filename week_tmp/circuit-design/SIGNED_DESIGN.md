# 観測者署名と誤差対応回路の結合

最新：[2026-11-25の改善](INTEGRATION_20261125.md)で、public witnessからの受付抽出と統合検証、未来claim方針を実装した。以下は初期署名実装時点の仕様・実行履歴。

2026-11-24。既存の実測記録には新しい方式の署名を付け直していない。ここで使う署名鍵・観測・nonceは全て合成テスト用であり、実端末や実ドローンの認証実績ではない。

## 今回追加したもの

- [`SignedCircuit`](signed.go)：`UncertaintyCircuit`の計算を維持し、そのcommitmentに対する観測者署名を回路内で検証。
- `SignatureMessage`：回路と同じfield要素列で署名対象を作るnative側の関数。任意JSONのhashではない。
- `CheckAdmission`：期待する観測者公開鍵・モデル・session・座標系・claim token、期限、既受理IDを照合する外部受付の事前検査。
- [`signed_test.go`](signed_test.go)、[`admission_test.go`](admission_test.go)：改変、未登録鍵、期限切れ、再利用、異常な曲線点等の否定テスト。
- [`signed_proof_test.go`](signed_proof_test.go)：明示的に有効化する合成1件のsetup/prove/verify試験。通常のテスト実行ではskipし、高負荷setupを自動起動しない。

既存V2、Circom回路、Android/Piアプリ、実測判定モデルは変更していない。

## 何に署名するか

誤差対応回路のcommitment Cは、session・frame・claim・policyと、privateな位置/RSSI/時刻/誤差/既知フラグ/nonce/判定結果を束縛する。

その上で署名対象を次とした。

`M = MiMC(3203001, C, ObserverKey.X, ObserverKey.Y, RecordID, ExpiresMS)`

署名はBN254上のtwisted Edwards EdDSA＋MiMC。これは今回のgnark試作用の方式であり、Androidの通常のEd25519鍵、既存V2/CircomのEdDSA-Poseidon署名と互換であるとは扱わない。端末実装や鍵移行は未実施。

| 項目 | 公開/非公開 | 意味 |
|---|---|---|
| 観測者の秘密鍵 | 署名側だけ。回路witnessにも含めない | prover/サーバーへ渡さず署名生成に使う |
| 観測者公開鍵 | public | 登録鍵との照合用。観測者の継続追跡を避ける匿名会員証明は未実装 |
| 位置・RSSI・受信時刻・位置/高度/時計誤差 | private | 元の誤差対応回路と同じ |
| 署名R/S | private | 回路内で検証。proofの利用者へ署名全体を直接公開する必要はない |
| 方針/申告位置/claim時刻/run/座標系/結果/C | public | 対象と判定方針を固定する |
| RecordID | public・run内限定128bit | 同じ鍵・sessionの受付済み記録を区別。物理RFパケットIDではない |
| ExpiresMS | public・48bit | 同じepochでの署名済み有効期限 |

署名後にRSSIや誤差を書き換え、Cを再計算しても元の署名では通らない。sessionやモデルを変えて作り直す操作も同様。一方、署名者自身が嘘の観測へ署名する問題は防げない。

## 回路内の追加検査

- RecordIDは非ゼロ128bit、期限は48bit。
- 申告時刻と観測時刻は期限以下。
- 公開鍵と署名Rは曲線上・非単位元・素数位数部分群に限定。
- 部分群検査は、部分群所属を前提とする高速ScalarMulを使わず、公開定数の群位数に対するAdd/Doubleで実行する。
- 署名scalarの標準範囲はgnark EdDSA verifierで検査。

回路は「現在の実時刻」を知れないので、期限内という署名内容だけで現在の有効性を証明しない。正しい別鍵の署名も数学的には通る。これらは否定的な隠れ仕様ではなく、外部受付が必要な境界としてテストした。

## 回路の外で確認すること

`CheckAdmission`の期待contextはverifier側の信頼済み設定から与える。proverが一緒に送った設定をそのまま「承認値」にしない。

1. public session/frame/claim token/policy digestが期待値と一致。
2. 観測者公開鍵が有効な曲線点であり、登録している鍵と一致。
3. 現在時刻・claim時刻・署名期限が承認sessionの時間範囲内。
4. `(ObserverKey, Session, RecordID)`が未受理。C・claim・policyを変えても同じreceipt IDの再利用を逃がさない。
5. 実際のproofを検証し、その後だけ受付済み記録へ追加。

実装した関数は**proofを検証せず、受付状態も更新しない事前検査**。proof公開witnessとの厳格な復号対応、永続DB、原子的な重複排除、並行受付・再起動からの復元は未実装。合成proof試験では同じ割当からpublic receiptを作り、proof検証後にfixture mapへ追加して再利用拒否を確認する。これを実運用APIの完成とは扱わない。

now/expiry/claim/observedは同一epochへ対応した時間が前提。RIDの毎時周回値とホストUTC/単調時計を直接比較しない。その変換や真の時計誤差をこの署名で作り出せるわけではない。

## まだ保証しないこと

- 元Wi-Fi IE・元GPSと正規化座標のbyte-to-field変換、元ログ全件の網羅性。
- 署名者が実受信したこと、自己位置/高度/精度申告の真実性、送信機の真位置・実電力。
- 同一物理送信の照合、DRSSの成立、機体/受信ハードの真正性、DRIP trust chain。
- 現在の単局モデルが位置偽装検出器として採用可能なこと。実測は未改変13/27警報の結果を維持。
- 署名者資格の失効、匿名会員証明、Sybil耐性、悪意ある正規観測者への耐性。
- 再帰/集約proof、EVM検証、実端末のソフト/ハード鍵保護。

## 再現

```sh
cd week_tmp/circuit-design
DRAFT_SUMMARY_PATH=results/constraint-summary.json go test -count=1 -v ./...
```

通常実行は署名付き回路の合成制約と受付テストまで。単体proof試験は別途メモリ/swapを確認してから、1件・並列度2・時間上限付きで有効化する。

```sh
GOMAXPROCS=2 GOMEMLIMIT=1GiB DRAFT_RUN_PROOF=1 \
  DRAFT_SUMMARY_PATH=results/constraint-summary.json \
  go test -count=1 -timeout 120s -run '^TestSignedProof$' -v ./...
```

GOMEMLIMITはGo GCのsoft targetであり、OSのhard memory limitではない。今回の事前確認は[preflight](results/signed-proof-preflight.json)へ記録。再実行時はその時点の資源を確認する。大規模な再帰setupを許可する結果ではない。

setup/proof/keyは単体試験のプロセスメモリ内だけで保持する。使い捨て単独setupでありrelease鍵ではない。proofのシリアライズサイズは破棄用writerで数えるだけで、proof/VK/PK/秘密鍵/witnessをファイルへ出力しない。

[署名制約集計](results/signed-constraint-summary.json)、[通常テストログ](results/circuit-tests.log)、[proof試験ログ](results/signed-proof.log)、[proof試験集計](results/signed-proof-summary.json)を参照。合成単体の成功を実データ・Pi/Android・再帰/EVMでの成功へ一般化しない。

## 今回の実行結果

署名付き制約は24ケース成功、136,526制約。正しい別観測者の署名や、期限が過去かどうかを単体回路だけでは判断できないケースも通ることを確認し、外部受付の必要性を明示した。外部受付は20ケース成功。既存の計算核44＋誤差対応25ケース、Python27件も維持。

Mac/並列度2の合成1件の実行値：compile331ms、使い捨てsetup19,357ms、prove992ms。verifyは整数ms計測で0ms（1ms未満へ切捨て）で、検証処理を省略した意味ではない。サイズ164bytesは圧縮形式を破棄用writerで数えた値のみ。1回の試験値であり、平均・Pi性能・他方式との公平比較ではない。

setup/proof検証は成功、公開status/session/commitment/observerの4変更は拒否、検証後のfixture受付mapへの追加後は同じreceiptを拒否した。署名・proofは全て合成データ用で、既存実測記録を後付けで認証したものではない。
