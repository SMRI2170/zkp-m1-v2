# Circom：snarkjsとRapidSnarkの証明生成比較

同じCircom距離回路、WASM Witness generator、貢献済みの使い捨てGroth16 fixtureを使用する。
両方とも検証器は共通のRapidSnark native verifier。snarkjsだけでprove＋verifyした性能とは区別する。

|構成|証明生成|検証|
|---|---|---|
|Circom＋snarkjs|Node API groth16.prove の singleThread:true|共通native verifier|
|Circom＋RapidSnark|既存native prover|同じnative verifier|

Piの既存snarkjsは0.7.5、Macは0.7.6。両方のsourceでoptionsとsingleThread対応を確認し、version/hashを記録する。packageを黙って更新しない。
Macでの実proof確認は別の使い捨てfixtureによる正当性検査で、Pi性能には加算しない。

## 条件

- 合成u16座標7入力各1回warmup後、7入力を3巡して測定21件。1process内のwarm反復。
- CPUQuota25%、1CPU affinity、子High192/Max256MiB、Swap0。既存親slice／watchdog／SSH保護と各run前の3 snapshot preflightを使用。
- Witness・prover process・共通verifierを分離。Node起動・API初期化・proof書込はprove時間に含む。WTNS書込はWitness timer外。
- 生のJSON proof/public bytesと、raw benchmarkのcanonical JSON proof bytesを区別する。
- 各正常proofの公開入力／proof改竄拒否、不正入力6件、WTNS直接改竄のprover/verifier試験を維持。
- proof／Witness実体はowner-only tmpfs内で終了時削除。SIGKILL／再起動後は残存確認が必要。

## バックグラウンド実行

既存のSSH環境変数を設定し、新しいtag/outで次を起動する。

    python3 experiments/sequential-evaluation/run.py start --plan experiments/circom-prover-comparison/plan.json --tag circom-1017a --out .cache/week24/sequential-jobs/circom-1017a

回帰 → Mac実proof／公開入力改竄検査 → Pi ready確認 → 配置 → snarkjs → RapidSnark → 1接続でログ回収 → CSV/JSON・既存7構成との結合・図 → CIログ保存。
測定失敗／接続断後に次の測定を自動開始しない。回収と集計は続け、partialと欠測を保持する。

新2構成はdata/、既存7構成を含む結合はcombined-data/へ保存。sources.jsonに元datasetのhashを保存し、工程範囲が異なるcohortは別図にする。
status.jsonとresults.csvは実行状態、comparison-status.jsonは実測完走構成、local-proof.jsonはMac検査を示す。
通常の全体planにも2構成を追加し、全体job内ではcircom/へ分ける。driver追加と実測完了を区別する。

設定変更や保護の緩和、鍵・setup/VK/proof実体の公開・チェーンdeployは行わない。研究PoCの合成距離計算であり、DRIP trust chain・sensor honesty・hardware／航空機認証は保証しない。
