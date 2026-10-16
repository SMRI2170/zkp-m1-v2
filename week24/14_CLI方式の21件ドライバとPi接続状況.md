# Week24：CLI方式の21件ドライバとPi接続状況

Issue #60/#61の続きを開始した。今回のコード追加は #61 のCircom/RapidSnarkとNoir/Barretenbergの測定driver。
**実ZKP生成・新条件でのPi性能評価は、今回まだ実施していない。**

## Piで観測したこと（#60）

SSH認証が成立し、最初の確認ではuptime約20分、利用可能メモリ約3.3GiB、swap使用0だった。
再起動で消えるwatchdog等のruntime保護がinactiveだったため、hash一致の既存installerによる復旧を試みた。
そのSSHコマンドは終了コード255／server応答timeoutとなり、復旧完了は確認できなかった。
その後のread-only確認ではuptimeが0分台、watchdogはinactive、利用可能メモリ約3.4GiB、swap使用0だった。

重負荷・proof生成・新binary配置は開始していない。手動の電源操作か予期しない再起動かを確認中で、OOM・電源・installerが原因と断定しない。
SSHの接続再利用を避ける独立接続でも応答失敗があり、その後のpreflightコマンドも接続終了255で、readyな事前検査を取得できていない。
接続先・password・host key・boot ID・journal本文は公開しない。#48 の安定性確認と接続復旧後に、guard状態を再点検してから #60 の8構成測定を再開する。

## 実装したもの（#61）

|方式|新driver|今回の検証範囲|未完了|
|---|---|---|---|
|Circom/RapidSnark|7入力warmup＋7入力×3回、JSON proof/publicサイズ|元sourceのhashと安全性チェックの保持、JS構文|実prover/verifier、Pi測定|
|Noir/Barretenberg|同じ28件、21件集計、sample別tmpfs出力|元source保持、Python構文、偽CLIによるdispatchとcleanup|実nargo/bb proof、Pi測定|

両方式ともsource snapshotを新directoryへ生成する。旧回路・ソース・測定結果・manifestは書き換えない。
Circomの貢献済みsetup確認と不正assignment検査、NoirのZK設定・公開入力／proof改竄拒否の呼出しを維持した。
Noirのfake CLI試験は実暗号処理をしないため、28件の実proof成功には数えない。

NoirはcompileとVK生成を含む既存フローを維持し、具体的な時間fieldを残したうえで共通fieldも追加する。
CircomのCLI起動やJSON encodingも区別する。反復数の統一だけで、完全に同じ工程・security・通信形式とは主張しない。

## 次に進めること

- Pi再起動の背景・接続・runtime保護・ready preflightを確認し、#60 の8構成21件測定を行う。
- この2つのCLI driverを実prover/verifierで検査し、資源予算と工程を固定してPiへ適用する。
- #61 の残る8構成（Kimchi、Binius64、Jolt、Nova、HyperNova、Plonky2、RISC Zero、SP1）を順次対応する。IVCは別系列protocol、資源／sysroot制約は #55 を参照する。
- 実測が揃ってからCSV/JSONL・統計・PNG/SVGを生成する。旧測定値で新結果を埋めない。

[実装・再現手順](../experiments/balanced-cli/README.md)。回帰テスト3件と既存Python61件・aggregator Go・契約テストを確認する。
研究PoCの合成距離計算であり、DRIP trust chain、sensor honesty、observer hardware／航空機認証は保証しない。
