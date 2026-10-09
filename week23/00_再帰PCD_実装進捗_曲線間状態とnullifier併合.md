# Week 23：再帰PCD実装進捗 — 曲線間状態とnullifier併合

開始日: 2026-10-02

## 今回の結論

Week 22で計画した「BN254 leaf proofから再帰PCDへ入る境界」と「端末の二重計上防止」について、
次の基礎実装を追加した。

```text
BN254 leaf proof
  → BridgeBW
      - 固定VKでleaf proofを回路内検証
      - memberRoot membershipを検証
      - session nullifierを0→使用済みへ遷移
  → 再帰ノード（次段で接続）
      - NodeBLSの固定鍵検証部品
      - nullifier treeの安全な二分併合部品
      - BN254状態を曲線間で失わず渡すlimb形式
```

まだ最終proofやオンチェーン検証まで通してはいない。特に、二分併合回路を
`NodeBLS` / `NodeBW` の**再帰proof内部**へ接続する作業と、相互再帰の鍵bootstrapが残っている。

## 実装したもの

### 1. `NodeBLS` の固定鍵再帰検証部品

`aggregator/pcd/node_bls.go` を追加した。

- BW6-761の子proofを2件、BLS12-377側で回路内検証する。
- 子のverification keyはprover入力ではなく、回路作成時に固定する。
- ドローンID・時刻・policy・member rootの一致、nullifier状態の引き継ぎ、
  consistent / suspicious countの合算を制約として表現する。
- これは小さい値を使う既存PoC向けの部品である。v1のBN254値をそのまま
  BLS公開入力に置く本番用途には使わない（後述）。

### 2. `BridgeBW`：端末leaf proofをPCDへ接続する境界

`aggregator/pcd/bridge_bw.go` を追加した。

- BN254 Groth16 leaf proofのverification keyを固定して、BW6-761回路内で検証する。
- leaf公開信号18項目の形式を固定し、`within30_and_detected == 1` と
  legacy `drone_auth_ok == 1` を必須化する。ただしこれはprover提供鍵の署名検証bitで、Remote IDと登録鍵の対応・DRIP trust chainは証明しない。
- leafの `drone_id_commitment`、`time_bucket`、`consistency_ok` を再帰状態へ束縛する。
- leafの端末公開鍵（index 11–12）について、`memberRoot` のMerkle membershipを検証する。
- セッションに対するnullifierを計算し、当該スロットが未使用の0であること、
  更新後rootが正しいことを検証する。

BW6-761の標準MiMCはBN254版と異なるため、そのまま使うことはできない。
Bridge内では `MiMC_BN254` を有限体エミュレーションとして再計算し、既存の
登録端末treeと同じrootになるようにした。

### 3. 二分nullifier tree併合

`aggregator/nullifier/merge.go` を追加した。

単に `hash(leftRoot, rightRoot)` とすると、同じ端末が両方の子treeにいる場合を検出できない。
そこで固定深さ4（16端末）のtreeについて、次を回路内で検証する。

1. 左右の非公開leaf列から、それぞれの子rootを再計算する。
2. 同じインデックスで左右がともに非0なら拒否する。
3. 非重複のleafを併合し、統合rootを再計算する。

これにより、端末IDを公開せずに重複参加と統合root改ざんを拒否できる。

### 4. 曲線間stateエンコード

BN254 scalarは254bitである一方、BLS12-377 scalarは253bitである。したがって
BN254のroot・commitment・IDをBLS側の公開入力へ1値で渡すと、値が丸められる可能性がある。

`aggregator/pcd/state_encoding.go` と `state_limb_circuit.go` で、v1の9値を
それぞれ4個のlittle-endian 64bit limbに分解する形式を実装した。

```text
9項目 × 4 limb = 36個のBLS公開入力
```

- BN254の最大正規値は往復しても変わらない。
- 64bitを超えるlimb、BN254法以上の非正規値を拒否する。
- `state_cycle_adapter.go` はBW6状態をBN254値として復元する際にも同じ正規性検査を行う。
- とくに「BN254の法を入力して0へ丸める」入力を拒否するテストを追加した。

## 検証結果

2026-10-02時点で、次を実行して成功している。

```bash
cd aggregator
go test ./...
```

確認した否定系:

- 固定していないverification keyで作ったproofの拒否
- nullifier treeで同じ端末インデックスが左右に重なる場合の拒否
- 統合nullifier rootの改ざん拒否
- BN254の範囲外値・65bit limbの拒否
- BN254法を曲線境界で0に丸める入力の拒否

## 追加実装：Issue #5 `FinalBN` とv1 policy（2026-10-03）

`aggregator/pcd/final_bn.go` にBN254上の `FinalBN` 回路を追加した。

- BW6-761のroot proofを、コンパイル時に固定したverification keyで検証する。
- BW6のstate値をBN254 scalarへ移す際、4×64bit limbと正準範囲を検証する。
- 内部ordered stateを `final-attestation-v1` の9公開入力順に変換する。
- session開始時のnullifier rootが空tree rootであること、観測数が0でないこと、時刻と件数の範囲を制約する。
- 最小quorumを `policyCommitment` に含め、countからverdictを算出する。

v1のpolicy commitmentを次のCircomlib Poseidon preimageに固定した。

```text
Poseidon_BN254_Circomlib([
  ASCII("UAV_FINAL_POLICY_V1"),
  protocolVersion = 1,
  minimumQuorum: uint32 > 0
])
```

`minimumQuorum=2` のcommitmentは
`1791950082637333959260344209857081584058079814184145123235554669090060789867`。
test vectorのpolicy commitmentとsession IDもこの値に合わせて更新した。

実行した検証:

```bash
cd aggregator
go test ./...
RUN_FINAL_BN_COMPILE=1 go test ./pcd -run '^TestFinalBNCompilesToNinePublicInputs$'
cd ../contracts
npm test
```

Go全packageとHardhat 36テストが成功し、FinalBNのBN254回路compileでも公開入力が9個であることを確認した。
小さなBW6 test proofを使った成功・statement改ざん・初期root改ざんの否定テストも追加した。

これはFinalBN回路とstatement制約の実装までであり、本番release完了ではない。実際の `NodeBW` root key、
NodeBLS/NodeBW全段への36-limb状態とnullifier unionの接続、信頼できる鍵setup、Solidity verifier生成、
実PCDからのBN254最終proof生成は残っている。test用setup keyを本番利用しない。

## 次の実装区切り

次のまとまりは、以下を完了した時点で `week24/` として記録する。

1. 36-limb形式を本番用 `NodeBLS` / `NodeBW` の公開状態へ組み込む。
2. `MergeCircuit` のnullifier併合を、その再帰ノード内で強制する。
3. `BridgeBW → NodeBLS → NodeBW` を少なくとも3段、実proofで連結する。
4. 相互再帰の鍵artifactを固定し、違う鍵・違うsession・違うrootを混ぜる否定系を追加する。

この区切りが終わるまでは、最終EVM proofや本番稼働を主張しない。

## 追加進捗：複数観測RSSI評価を現行3ノード証明形状に整合（2026-10-05）

複数観測者の独立truth評価に、opaqueな`decision_window_id`を導入した。
`(run_id, decision_window_id)`で同一target・同一truth時刻窓の観測を集約し、
同一観測者の重複票と、独立truthのmismatchラベル不一致を拒否する。

ここで重要な実装境界が見つかった。hostのobserver-batch preflightは2人以上を
受け付ける一方、現行`aggregator/cmd/pcd3`の再帰proof runnerは厳密に3 leaf
observer固定である。この違いを評価レポートで隠さないよう、現行形状での最終
分類対象をちょうど3観測者に限定した。

- 3人未満は、票が数学上quorumに届いていても`INSUFFICIENT_EVIDENCE`。
- 3人を超える群は、今のproof topologyでは扱えないためunsupportedと報告。
- ちょうど3人についてのみ、事前登録quorumによる最終分類を行う。
- insufficient / unsupported / conflicting群はFP・FN率の分母分子に含めず、
  件数を並記してcoverageの欠落が見えるようにする。

`uav/OBSERVER_CAPTURE.md`とfield-study templateにも固定3観測者の制約を追記した。
加えてtruth ledger正規化時に、同じdecision window内の同一run/tag、観測者1行、
全窓の共通時間overlapを検査し、誤ったjoinを早期拒否する。
検証は`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s uav -p 'test_*.py' -v`で
54 tests成功。これは合成/fixtureデータによる評価ロジックの確認であり、実RF測定、
truthソースの精度、observerの物理的独立性や現行V2の最終proofを確認した結果ではない。

## 追加進捗：10〜11月 複数観測PoCの鮮度・実測評価ゲート（2026-10-04）

中期目標を2026-11-30期限で設定し、全体設計と段階別完了条件を
[`docs/protocol/multi-observer-risk-v1-design.md`](../docs/protocol/multi-observer-risk-v1-design.md)
に整理した。今回、鮮度の拘束に加えて、実RSSI評価の校正・評価データ混入を
防ぐ検査を追加した。

### 現在確認できたこと

- 当初のunsalted V2 leafではfreshnessを`target_time_sec`へ拘束し、60秒
  `time_bucket`を同時に導出した（12,006 nonlinear constraints）。後続のrun-scope
  privacy更新でrelationとそのVK/proofが置き換わった。現在の証拠は後述の追加進捗を参照。
- FinalAttestationRegistryV2はbucket startに対する粗いfuture/age window、
  approved policy/member root、最終session/proofの再利用拒否を持つ。
  mock verifierのHardhatテストは成功したが、実recursive proofによる
  コントラクト接続を証明するものではない。
- `uav/evaluate_rssi.py` は校正run IDを記録し、profileごとに複数の校正runを
  要求する。校正と評価の`run_id`または`sample_id`が重複すれば拒否する。
  `python3 -m unittest discover -s uav -p 'test_*.py'` は今回のcapture metadata検査を加えて20件成功。

### まだ通していないゲート

鮮度制約追加前に作られたV2 leaf proof/VKはその後の回路に無効。2026-10-04には
当時の12,087-constraint session-salted leaf relationに対して
`RUN_BRIDGE_BW6_SOLVE=1 bash scripts/test_v2_observer_batch.sh`を実行し、
そのrelationから使い捨てproof/VKを再生成、実leaf proof/VK/pathをBridgeBWV2の
gnark test engineでsolveし、path tamper拒否まで確認した。その後leafをBLE/RSSI-onlyの
6,201-constraint relationへ変更しており、Bridge gateは現行leafでは未再実行である。
旧setupはsingle-contributor test-onlyで、外側BW6 Groth16 proof、recursive
Node/FinalBNV2、生成verifierによるEVM検証も未完了。外側setup/proveはこのMacの
メモリ・swap余裕が限られるため、小段階で資源を監視して判断する。

実機RSSI、複数ノードの同時観測、independent ground truthも未取得であり、
合成データのテスト結果を精度の証拠にしない。現行V2 leafの正確な観測時刻は
leaf proof受取側（通常は集約者）には公開されるが、最終10公開入力とregistryには
60秒bucketだけが出る。観測端末・送信機・ground truthの準備可否を確認中。

## 追加進捗：異種校正profileの同一batch対応（2026-10-04）

この節の検証は、後続のBLE/RSSI-only変更前に使っていた12,087-constraint
session-salted leaf relationに対する歴史的結果である。単一profile IDを全observerへ要求する設計では、端末・antenna・設置条件ごとに
校正値が異なるスマホとRaspberry Piを同じsessionで検証できない。このためV2を、
profile IDの集合rootをpolicyへ束縛し、各leafがBridge内で自分のIDのMerkle membership
を示す形へ変更した。allowlistは最大16 ID、tree depth 4、入力順に依存しないよう
profile IDを昇順に正規化する。Quorumも同じpolicy commitmentへ束縛する。

FinalBNV2の10公開入力順は維持し、input[4]の意味を単一profile IDからBN254の
profile-set rootへ変更した。FinalAttestationProtocolV2はinput[4]をuint32に制限せず
正準scalarとして検査し、registry record/eventは`calibrationProfileSetRoot`を保存する。
単一profile semanticsの実験proof/VK/registry ABIとは互換でなく、再生成が必要。

### 検証

- `RUN_BRIDGE_BW6_SOLVE=1 bash scripts/test_v2_observer_batch.sh` 成功。使い捨てkeyで
  当時のV2 leaf proof 3件を生成し、profile ID 1/2混在batchを共通`{1,2}` rootで受理。
  実profile-2 leaf proofをBridgeBWV2のtest engineで解き、member pathとprofile pathを
  個別に改ざんした場合は拒否。未許可profile、重複observer、異session、改ざんpublic
  signal、V1 key流用も拒否する。outer Groth16 proofではない。
- `GOMAXPROCS=1 go test -p 1 ./pcd ./cmd/pcd3 -count=1` 成功。
- 最終入力rootがuint32を超えてもBN254正準範囲なら受理・保存するhost/registry否定・正常系を追加。V2 registryはmock verifierでこの境界をテストする。
- `cd contracts && npm test` 成功（45 tests）。
- `git diff --check` 成功。

### 限界と残り

profile membershipはIDがpolicyの許可集合に属することだけを証明する。`measured_range_cm`
は回路外でRSSIから算出され、leafはrange・profile ID・判定をobserver署名へ束縛するが、
受信機が本物であることや承認係数どおりに換算したことは証明しない。V2 input[4]の
ABI意味変更後のFinalBNV2実proof、生成verifierによるEVM検証、outer recursive proof、
実機RSSI評価は未完了のまま。詳細は
[`v2-observer-batch.md`](../docs/protocol/v2-observer-batch.md)を参照。

## 追加進捗：実測ログのsession metadata結合（2026-10-04）

`uav/observer_capture.py`のJSONLに必須の`run_id`、安定したローカル
`observer_id`、`calibration_profile_id`を加え、capture start・各observation・end/error
すべてに同じ値を付けるようにした。複数ノードには同じ不透明run IDを渡し、各受信機は
calibration/evaluation間で同じローカルobserver pseudonym/profile IDを使う。IDはASCIIの
限定文字集合と64文字以内に制約し、profile IDはuint32範囲かつcanonical decimalで読む。
BLE capture自体や実機測定を行ったわけではない。

古い`uav/OBSERVER_CAPTURE.md`には「同一batchで全leafが同一profile IDを要求」と書かれて
いたため訂正し、許可集合rootとleaf membershipがあれば異なるprofile IDのbatchを扱えること、
ただし係数適用・センサー真実性は証明されないことを明記した。更新後
`python3 -m unittest discover -s uav -p 'test_*.py'` は20件成功。

## 追加進捗：run限定の複数観測者IDタグ照合（2026-10-04）

既定ではcapture processごとに別の一時鍵を使い、観測ノード間でUAS IDを
照合しない。明示的に`--session-key-file`へ32-byte鍵を渡した場合に限り、同じ鍵・
`run_id`・Basic ID type/UA type/IDから複数ノードで一致する`uas_id_tag`を生成する。
run IDとdomainをlength-prefix付きでHMAC-SHA256へ束縛し、BLE advertiser addressのtagは
常にノードローカル鍵に分離した。鍵ファイルはsymlink不可、regular file、所有者一致、
mode 0600以下、サイズ32-byteを要求し、内容やパスはJSONLへ出さない。

このtagは同一放送IDの候補をグループ化するだけで、物理機体の同一性・Remote IDの
認証・観測ノードの独立性は示さず、leaf proofやon-chain statementにもまだ束縛されない。
共有鍵の保持者は既知ID候補を照合できるため、runごとに新しい鍵を安全に配布し、
field capture終了後の保持・廃棄を管理する。タグ実装と鍵境界のunit testを追加し、
`python3 -m unittest discover -s uav -p 'test_*.py'`は24件成功、CLI helpも表示成功。
今回の対象4ファイルをuntracked状態も含めてwhitespace scanし、違反なし。実機BLE capture
および複数node実測は未実施。

## 追加進捗：session-salted Remote ID commitment（2026-10-04）

privacyレビューで旧`Poseidon(remote_id)`が公開leaf上に固定の値を出し、低entropy RIDの
候補照合およびbucket間trackingを許すと確認した。未releaseのV2 leafを更新し、同じ
run keyと`run_id`を共有するobserverが`time_bucket`ごとに同じcommitmentを作れる一方、
別runまたは別bucketでは異なる値になるようにした。

```text
session_salt = big_endian(HMAC-SHA256(run_key,
  "signal.observer-circuit-salt.v2\0" || run_id)[:31])
drone_id_commitment = Poseidon("SIGNAL_RID_V2", remote_id,
                               session_salt, time_bucket)
```

saltはprivate witness、run-scoped commitmentと60秒bucketだけがleaf public output。
回路はsaltのentropyや乱数性を証明しないため、新しい32-byte keyの生成・安全な全node配布・
runごとの非再利用が信頼前提。key保持者は既知RIDを候補照合できる。これは同一放送IDの
候補を結合するだけで、DRIP/RID認証・物理機体の同一性・observer独立性は証明しない。

検証結果:

- Circom 2.2.3 compile: 12,087 nonlinear constraints、8 public outputs、12,077 wires。
- Python/JavaScript KDFは固定key/run vectorで同じ248-bit saltを生成。key fileはmode・owner・
  symlink・32-byte長を検査し、synthetic witness JSONは0600でexclusive作成する。
- `python3 -m unittest discover -s uav -p 'test_*.py'` は26件成功。共有key fileから
  JavaScript witness generatorが出すsaltとPython KDF結果の一致、およびCircuit witness生成を確認。
- WASM witnessで同じrun/bucketの2 observer commitment一致、別run（同じbucket）と
  別bucketのcommitment相違を確認。
- `bash scripts/test_v2_observer_batch.sh` 成功。fresh Groth16 leaf proofを検証し、host batchで
  same-bucket別runと別bucketを拒否。
- `RUN_BRIDGE_BW6_SOLVE=1 bash scripts/test_v2_observer_batch.sh` 成功。profile-set変更時のleaf VK/proofで
  BridgeBWV2 test engine solveおよびmember/profile path改ざん拒否を確認。
- 同じ統合runでtemporary Solidity verifierをfresh zkeyからexportし、Hardhat local EVMへ
  deploy。leaf proofを受理し、RID commitment/time bucket/consistency/freshness/profileの
  public signal改ざんを5件すべて拒否。
- 同じ生成物を使って`pcd3 --protocol=v2 --stage=plan`を実行し、3 leaf proof/VK・synthetic
  rosterからmember/nullifier root、profile-set/policy、2+1 count/verdict、V2 recursive topologyを
  CLI経由で出力できることを確認。これはplan/preflightのみでrecursive circuit compile/setup/proveなし。
- `RUN_PCD3_V2=1` opt-in gateを統合scriptへ追加。recursive setup/proof後、FinalBNV2 generated
  verifierとregistryをHardhat EVMで検証する設計。2026-10-04にsetup attemptを行ったが、
  BridgeBWV2 setup中のswap限界で中断し、最終proof/EVMは未完了（追加進捗を参照）。

旧V2 leaf relationのVK/proofおよび旧Bridge actual-proof結果はstaleで使用しない。Generated
leaf verifierのEVM検証までは完了したが、FinalBNV2 verifier/registry EVM、outer recursive/final
proof、実BLE capture/RSSI評価は未完了。

## 追加進捗：FinalBNV2までの実行ゲートと資源限界（2026-10-04）

古い（2024年）checked-in synthetic inputがFinal registry freshness gateに必ず失敗する
ため、統合scriptは元fixtureを変更せず、test用コピーのdrone/target/frame時刻だけを
実行時の現在分のbucket startへ一括shiftするようにした。合成データでは旧drone
self-signatureを無効化し、RID認証と誤認しない。最終Registry EVM確認用のHardhatだけは
`PCD3_V2_EVM_INITIAL_DATE`でsynthetic bucket start +30秒に固定し、contract側のfreshness
上限を広げずにその時刻で判定する。Hardhat runtimeが指定Unix時刻で起動することは
確認した（2026-10-04T14:00:30Z）。Goのtemporary build先を`GOTMPDIR=/tmp`へ分離したのは、
作業用SSDがexFAT/noexecであり、そこでGo test binaryを起動すると`exec format error`に
なったため。分離後、保持済みのcurrent leaf proofで`TestV2ObserverBatchProofIntegration`
は成功し、V2 `pcd3 --stage=plan`も3観測者・2+1判定を出力した。

`pcd3 --stage=run`を外部SSDのfixture/artifact directoryで実際に開始した。現行
BridgeBWV2は2,285,785 constraintsでcompileしたが、Groth16 setup開始約1分43秒後の観測で
`vm.swapusage`がtotal 8,192 MiB中7,841.69 MiB使用・334.31 MiB freeとなった。ホスト保護の
ためinterruptし、recursive proof、Node/Final proof、FinalBNV2 EVM結果は生成していない。
ローカルplan/leaf/Bridge test-engine結果をrecursive proof成功と取り違えない。残りは、
利用可能な高メモリrunner、または測定で安全性を確認できるより低いparallelismで全stageを
完走し、FinalBNV2 verifier/registry EVMまで確認すること。実機RSSI評価とRemote IDの
外部DRIP信頼根検証も別途未完了。

## 追加進捗：Remote ID `Verified` / `Trusted`の再送耐性要件を明確化（2026-10-04）

RFC 9575 §3.1.2 / §6.4.2を再確認し、DRIPの署名鍵chainが示す「鍵が登録済み」と、
現在観測した送信者がその秘密鍵を保持することを分けた。`VALID`には、事前固定した
trust rootからUA DET/公開鍵までのBroadcast Endorsement検証だけでなく、UA-Signed
Evidence内の動的で先読み困難なmessage、署名内容の受信データとのbinding、session内での
独立／物理観測による内容validationを要求する。静的Basic ID、Endorsement署名、または
timestamp一致だけではreplay耐性を満たさない。RFC 9575では署名/content検証成功の`Verified`と、
さらにObserver所有者policyがDIMEを信頼する`Trusted`は別状態である。未完のchain/pageは
`Partial`として保留し、timeout後の`Unverifiable`と区別する。現行V2 leafにはまだDRIP chain・
dynamic evidence verificationがなく、RID `Verified`/`Trusted`を出せない点は変わらない。

併せてFinal registryのsingle-finalization設計を脅威表へ反映した。最終proofは受け取った
leaf集合に対する正しい計算を示すだけで、集約者が全観測を含めたことは示さない。quorumを
満たすsubsetを先に確定すると後からの完全な報告を拒否するため、現PoCでは結果の完全性・
可用性を保証しないと明記した。

## 追加進捗：V2 nullifier unionとprivacy境界のコード照合（2026-10-04）

V2 sourceを追い、以前の設計ノートにあった「bridgeは空rootで、session unionが未実装」
という記述が古いと判明した。`BridgeBWV2`はempty rootからsession nullifierを一件追加し、
`NodeBLSV2`/`NodeBWV2`はchild rootに束縛した固定16-slot private leaf vectorを照合し、
重複slotのないunion rootを作る。`FinalBNV2`はそのrootを公開statementへ束縛する。
`PrepareObserverBatchV2`/host merge、union circuit、Bridge assignmentのテストはあるが、
outer Node/Final proofはsetup資源上限のため未生成で、一続きの再帰proofとしては未検証。

また現行V2 nullifierはobserver secretではなく、登録公開鍵から作る`deviceLeaf`とsessionの
MiMCであることを確認した。ordered roster/index mapが漏れると、16 slotのsubset候補を
列挙して公開nullifier rootから参加者を推定できる。したがってon-chain anonymityはrosterを
知らない相手までの境界であり、roster-aware anonymityを主張しない。必要なら次protocolで
observer-held secret commitmentを登録credentialへ結合する必要がある。

追加テスト: `GOTMPDIR=/tmp GOMAXPROCS=1 go test -p 1 ./pcd -run
'^TestEmulatedNullifierSetUnion(AcceptsDisjointObserverSlots|RejectsDuplicateAndForgedUnion)$'`
は2件pass。`GOTMPDIR=/tmp GOMAXPROCS=1 go test -p 1 ./nullifier -run
'^TestMergeCircuit'`は3件pass（disjoint setを受理し、同じindexと偽造union rootを拒否）。
いずれもcircuit satisfiability/test harnessであり、実setup済みrecursive Groth16 proofや
FinalBNV2 EVM検証ではない。

## 追加進捗：実測RSSIデータの正規化経路（2026-10-04）

実機評価の入力作成が手作業CSVに依存していたため、`uav/prepare_rssi_dataset.py`を追加。
保護された`observer_capture.py` JSONLと、別管理するsurvey/GNSS truth-window CSVを
run・observer・session-scoped `uas_id_tag`・Unix ms区間で結合し、校正用またはholdout評価用
CSVを生成する。窓ごとにtagged受信RSSIのmedian、Location packet位置のmedianを算出し、
校正時の独立真値距離も同じ投影関数から求める。入力にcapture/ground-truth間の最大時刻誤差を
必須化して出力へ保持し、窓長以上の誤差は拒否する。入力のcapture完了marker/count、
observer/profile一致、非重複区間、RSSI/座標/altitudeを検査し、必要データ欠落時は失敗する。
生capture/truth inputはcurrent-user owner-only regular fileを要求し、tagを除く正確な位置を含む
outputも0600 exclusive createとした。

`uav/OBSERVER_CAPTURE.md`にtruth-window列定義、field captureから校正・評価CSVへのCLI例、
保管要件とデータ境界を追記。`python3 -m unittest discover -s uav -p 'test_*.py' -v`は
35件成功。synthetic capture JSONLから両modeの行が生成されること、profile/count/重複窓/
時刻不確かさ/欠落packet拒否、0600/no-overwrite、既存evaluator schemaへのCLI出力を確認。
さらに校正capture 2 run→校正CSV→holdout capture 4 run→評価CSV→既存`evaluate_rssi.py`を
一続きで実行し、既知のTP/FP/TN/FN各1件を再現できることを確認した。これはpipelineの
synthetic integration testであり、RSSI classifier性能または現場の正確性を示すものではない。
evaluation reportへ、実際にparseした校正/評価CSVのbyte lengthとSHA-256を追加。pathを含めず、
データcontentの同一性を再確認できるようにした（source/authenticityの証明ではない）。report
JSONのoutputも0600 exclusive-createにし、権限/上書き拒否をtestした。既存
`.github/workflows/verify.yml`はpush/PRでUAV unittest discoveryを実行しており、この統合test
もCI対象に含まれる。

この検証は正規化コードのテストに限る。repository内に実BLE captureまたは独立truth-window
datasetはなく、実機RSSI精度・false positive/negative評価は依然未実施。正常なデータ経路を
整えたが、目的(3)の証拠には数台の観測端末、制御した機体/送信器、独立した位置真値と
現場試験が必要。Synthetic test resultをfield resultとして扱わない。

## 追加監査：実captureからV2 leaf proofへの意味接続（2026-10-04）

注: 以下は修正前の状態を記録した履歴。camera入力と30m拒否ゲートは、本ファイル末尾の
「BLE/RSSI-only leafで遠距離不整合を集約可能にする」で解消方針・変更内容を記録した。

現行`uav/observer_capture.py`はBLE/RSSI、Basic ID/LocationとOpenDroneID Authentication pageの
framing/dataをJSONL化するが、ページ再構成・DRIP署名/endorsement/content検証はしていない。当時はstatusを
`unverified`と記録していたが、暗号検証未実行の意味なので現在は`not_evaluated`に修正した。V2 leafはcamera/video由来の
`uav_detected`・score/class・frame commitment/timeを要求する。V2 public signal 0は
`within30 * detection_bundle_ok`で、`VerifyV2ObserverBatch`と`BridgeBWV2`はいずれも0をrejectする。
`target_*`をobserver位置として使う場合、申告位置がobserverから30mを超える大きな不整合は
`consistency_ok=0`という危険側証拠があってもquorum集約前に落ちる。現行の
`scripts/gen_witness_sample_v2.js`もchecked-in synthetic inputと固定テスト観測者鍵を使い、実capture
を読まない。このため既存multi-proof testは、実Pi/phoneからleafを生成するE2Eを証明しない。

このgapを映像スコア/フレームを作り物で埋めてはならない。個別proofにcamera detectionを必要と
するか（BLE/RSSIだけか）を確認中。選択後、受信観測の有効性と不整合riskを別signalとして扱い、
距離ゲートがsuspect reportをdropしないleaf semanticsを決め、V2 VK以降を全て再生成・再検証する。
旧V2回路・合成witnessの現E2E状態から、capture-backed leaf proofへは未接続。

## 追加進捗：RSSI dataset source hash chain（2026-10-04）

正規化CSVがどのraw入力から生成されたかを照合できるよう、`prepare_rssi_dataset.py`は
capture set（各JSONLの内容hashをsortしdomain-separated hash）とtruth-window CSVのSHA-256を
CSV列として保持する。ファイル名/pathや`uas_id_tag`はCSVに出さない。`evaluate_rssi.py`は実際に
parseした校正/holdout CSV bytesのhashとlengthをreportへ記録するため、evaluation report→normalized
CSV→raw capture/truth contentのidentity chainを再確認できる。これは改変検出/再現用で、署名や
trusted clock/source provenanceではない。Normalizerの合成CLIテストでraw hashが期待値と一致し、
既存holdout evaluationが同一schemaを受理することを確認した。

## 追加監査：スマホ／Pi観測者credentialの実装境界（2026-10-04）

Flutter・Android・Pi・V2 witness generatorの鍵経路をコード照合した。V2 leaf回路が検証するのはBabyJubJub EdDSA-Poseidon署名。当時は実captureから観測者鍵で署名する経路がなかったが、その後、owner-private JSONLと別途provisionした鍵を受けるオフラインadapterを追加した（次の追加進捗）。これはcapture daemon/Flutterへの統合や実credential enrollmentではない。

- `scripts/gen_witness_sample_v2.js`は固定秘密鍵`01…`/`02…`/`03…`を使う合成fixture専用。観測credential登録や実端末鍵ではない。
- `uav/observer_capture.py`のHMACはRID pseudonymとrun saltの導出用で、観測者署名やJSONLの真正性を与えない。`observer_id`はcaller指定のローカルラベル。
- `scripts/capture_to_witness_v2.js`は後続追加のowner-private capture adapter。anchor eventのBasic IDを起点に同一bucket内のdecision windowを集計し、per-event RSSI medianとwindow内のLocation messagesから別鍵署名witnessを作るが、synthetic JSONLだけで検証済み。registry enrollmentや実センサーの保護とは接続していない。
- Flutter `ZkInputBuilder`にはV2観測者EdDSA鍵の生成・保管・署名がなく、`DeviceAttestationProvider`もproof生成経路から参照されていない。
- Android `DeviceAttestation`はP-256 Key Attestationを返すが、各呼び出しでaliasを削除して再生成し、BabyJubJub鍵へのproof-of-possession bindingや観測statement署名を行わない。iOS相当経路は現コードから確認できない。
- `scripts/attestation`は合成X.509 chain fixture用で、実機root/production enrollmentではない。従来は`trustedRootPem`または`expectedChallenge`を省略できたため、検証器をfail-closedに変更して両方必須とし、それぞれ未指定の拒否testを追加した。challenge一致だけでP-256鍵とBabyJubJub秘密鍵の同一所有を示すわけではない。

設計書`docs/protocol/multi-observer-risk-v1-design.md`に各経路の実装状態と、登録credentialによるcanonical V2 statement署名・未登録鍵/差し替え/RSSI・profile・time・session改ざん拒否・重複登録/失効拒否を次の受け入れ条件として記録した。端末hardware attestationによるSybil耐性は鍵pairingとenrollmentが通るまで主張しない。

検証: `cd scripts/attestation && npm ci --ignore-scripts` 成功、`npm test` は10件pass。これは合成証明書の検証器testであり、Android実機、Google hardware attestation root、Flutter/Piからの観測署名、登録済みcredentialのE2Eを証明しない。

## 追加進捗：capture decision windowからcurrent V2 witness/proof（2026-10-04）

`uav/observer_capture.py`の`--include-raw` JSONLから、anchor eventのBasic IDと同じrun-scoped tagを持つdecision windowを集計し、現行V2 leaf witnessを作る`scripts/capture_to_witness_v2.js`を追加した。per-event RSSIを一度ずつ使ってmedianを計算し、同windowのLocation timestamp/coordinatesもmedian化する。Basic IDは`id_type || ua_type || 20-byte ID`をbig-endian field scalarにencodeし、session key/run IDから計算したHMAC tagとcapture記録を照合する。Locationのseconds-within-hourは各capture receive時刻に最も近いhourへunwrapし、5秒を超えるものは拒否する。RSSI rangeはreportのreceiver/profile calibration modelから算出し、report toleranceが回路の0.9と一致すること、同一observer/profile・独立校正runが2件以上あることを要求する。出力witness/provenanceは0600・exclusive createで、provenanceにはRID auth `not_evaluated`、observer location `cli_asserted_unverified`、sensor not hardware-attestedを明記する。

検証: `node --check scripts/capture_to_witness_v2.js`と`node --test scripts/capture_to_witness_v2.test.js`が成功（9/9、通常約7.5秒）。3-event windowのmedian署名、current Circom WASM witness、CLI出力permission/overwrite refusal、未知option、別session key、stale timestamp、profile mismatch、separate-event Basic ID/Location join、Locationなし、bucket越境、対象緯度外、負座標丸めを確認。さらに`RUN_CAPTURE_WITNESS_GROTH16=1 node --test scripts/capture_to_witness_v2.test.js`も9/9成功（約258秒）。median-refactor後の現行leafから使い捨てsingle-contributor Powers of Tau/zkeyを作成し、zkey consistency check、proof生成・verificationを通した。これはtrusted ceremony、release VK、実機BLE captureの証拠ではない。外部SSDは0600 modeを保持しないため、CLI private-file testを含む全gateは通常のprivate tmp領域で実行した。

## 追加進捗：BLE captureでAuthentication pageを保持（2026-10-04）

DRIP署名検証に必要なAuthentication Message bytesが既存Pi captureで`unsupported`として破棄されていたため、`observer_capture.py`でtype 0x2をpage単位にdecodeし、type/page番号・page 0のlast index/length/timestamp・17/23-byte dataをJSONLへ保存するよう変更。ASTM単体25-byte frameに加え、公式OpenDroneID C layoutに従う3-byte header + 1–9個の25-byte message packを検証して展開する。各inner messageのraw bytes、MessagePack index/countを保持し、outer pack bytesは`--include-raw`時に保存する。type 0x3〜0x5はmessage typeを保持する。`authentication_status`は`not_evaluated`であり、page assembler、FEC、DRIP SAM署名、信頼chain、session content validationは未実装。これはRFC 9575の`Unverified`（検証失敗）とは異なり、まだ検証を試みていない状態である。したがってこれは認証成功ではなく、後続検証で入力を失わないためのcapture改善。

page長・last index・pack header/count/total length・nested/unsupported childの拒否testを追加。Message Pack内で複数messageを同一radio eventとして記録し、RSSI normalizerは`capture_event_seq`ごと一度だけ中央値へ含める。pack siblings間のreceive time/RSSI/advertiser不整合とevent count不一致も拒否する。`python3 -m unittest discover -s uav -p 'test_*.py' -v` は44件成功。これは合成parser/normalizer testで、実Bluetooth受信やDRIP verificationを証明しない。field recordsの`auth_data_hex`にもDETやsignatureが含まれ得るため、既存どおりcapture JSONLはowner-only 0600で保護する。OpenDroneID C referenceとRFC 9575の範囲を照合したが、現行repoにはDRIP cryptographic verifier依存はない。

## 再帰setup再実行の資源preflight（2026-10-04）

高制約BridgeBWV2/Node/Final setupを再開する前に現在のhost状態を読み取り確認した。`vm.swapusage`は7,168 MiB中5,734.06 MiB使用・1,433.94 MiB空き、`vm_stat`のfree pageは4,319（16 KiB/page）、Data volumeの空きは2.9 GiBでcapacity表示100%。別mountの`/Volumes/SSD`は1.6 TiB空きだが、これはhost memory/swap圧迫を解消しない。この状態ではsetupを開始せず、既存artifactも削除しない。setupとFinal EVMの未完了状態は維持する。

## 追加進捗：BLE/RSSI-only leafで遠距離不整合を集約可能にする（2026-10-04）

10〜11月の目標範囲を複数スマホ／PiのBLE Remote ID + RSSIによる位置不整合判定に固定した。現行V2のoutput 0は以前、`within30 * detection_bundle_ok`で、host/Bridgeが1だけを受理していた。このためobserver位置から30mを超える申告位置は、RSSIとの矛盾を`suspicious`へ数える前にleaf/batch入口で除外され得た。また、Pi captureには存在しないcamera/frame入力をfixtureから要求していた。

未releaseのV2 leaf relationを次のように修正した。

- camera/detection/frame入力を削除し、RSSI-only leafにした。
- 旧prover-supplied drone self-signature placeholderも削除した。これは登録RID鍵やDRIP rootに束縛されず、信頼性を与えない余分な回路だった。現V2はRID commitmentで同じ申告値をグループ化するだけで、機体認証はしない。
- output 0を`observation_eligible`へ変更。`abs(drone_time_sec-target_time_sec) <= 5`かつ`measured_range_cm > 0`だけで判定し、位置整合の結果とは分離した。
- V2 observer署名preimageを`Poseidon(domain, RID commitment, target commitment, observation_eligible, freshness, measured_range_cm, profile_id, consistency_ok)`へ変更し、入力と結果を引き続き同じobserver署名へ束縛。
- host batchとBridgeBWV2はsignal 0を`observation_eligible == 1`として検証し、`consistency_ok == 0`も正常な分類結果として集約する。
- synthetic generator/test gateに、別observer key/profileを持つ二つのfar-mismatch leafを追加。意図したbatch outcomeはconsistent 1 / suspicious 2 / `VerdictSpoofSuspected`。実地データではない。

検証: 旧RID自己署名placeholderも削除した最終leaf relationをCircom 2.2.3でcompile（6,201 nonlinear constraints、8 outputs）。`bash scripts/test_leaf_v2_binding.sh`成功。signed range/profile/freshness tamperを拒否し、far-mismatch WASM witnessのsignal 0=`1`・signal 5=`0`を確認した。`GOMAXPROCS=1 go test -p 1 ./pcd -count=1`も42秒で成功。ただしこの時点ではslow integration用proof fixtureがなく、実Groth16 proof経由のintegration testはskip扱いだった。その後の現行relationに対するfresh leaf proof・host batch・leaf EVM・`pcd3 --stage=plan`の検証結果は本ファイル末尾の「追加検証」節を参照。すべての旧V2 proof/VK/verifierは新relation・新署名preimageには使えない。

この後のread-only preflightはData volume空き2.7 GiB、7,168 MiB swapの6,311.38 MiB使用/856.62 MiB空きだった。ここではGroth16 disposable proof scriptを実行せず、host資源が回復した段階で現行relationのfresh proof→host integration→Bridge solve→leaf EVMを再確認する。ローカル試験で作った一時Circom/witness artifactsはTrashへ移動した（復元可能）。

本修正は既知の「検出すべき疑い報告を入口で捨てる」仕様不整合を直す一方、capture-to-proof/実端末observer署名・登録、センサー真実性、独立実機観測、実RSSIの誤検知/見逃しは閉じない。再帰・最終EVM setupは依然host資源が厳しいため開始していない。

## 追加調査：DRIP認証verify実装候補（2026-10-04）

公開候補を絞って一次資料を確認した。OpenDroneIDの[`authentication-verifier-api`](https://github.com/opendroneid/authentication-verifier-api)は「validation serviceがhostする」Remote ID認証のOpenAPI仕様で、ローカル署名/endorsement verifier実装そのものではない。Linköping Universityが公開する[DRIP code page](https://www.ida.liu.se/~andgu38/drip/)は実験実装を案内するが、取得した`drip-core-c` READMEはencoding/decoding libraryとして説明し、公開headerの関数も`encodeDripLink/Manifest/Wrapper/Frame`が中心だった。今回確認した候補だけでは、受信側でAuth pages + FEC + DRIP SAM + endorsement chain + signed session contentを一続きに`VALID`判定できる、すぐ導入可能なローカルverifierは確認できなかった（全公開実装を網羅調査した、という意味ではない）。

したがって現実装ではAuthentication pageを保存し、statusを`not_evaluated`に留める。外部validation serviceを使うなら、serviceの信頼・可用性・データ送信/プライバシーと「どの検証結果をどのrootに結び付けるか」を設計判断として別途決める必要がある。未確認コードをcrypto verifierとして導入したり、署名成功だけでRIDを認証済み表示するのは避ける。

## 追加検証：現行RSSI-only V2の実leaf proof → batch / plan（2026-10-04）

前節のleaf semantics変更後、更新後初の`bash scripts/test_v2_observer_batch.sh`を、`GOMAXPROCS=1 TMPDIR=/Volumes/SSD GOTMPDIR=/tmp UAV_V2_BATCH_GO_TEST_TIMEOUT=10m`で実行した。runは6,201 constraint current leaf relationから使い捨てsingle-contributor VKで複数Groth16 proofを生成し、fixture/test temp directoryはscript trapで除去した。

- fresh V2 leaf proofを生成し、同relationからexportしたlocal Solidity verifierが正常proofを受理、RID commitment/time bucket/consistency/freshness/profileの5 signal改ざんを拒否。
- `TestV2ObserverBatchProofIntegration`が実proofを検証してPASS。正常・同一observer重複・profile allowlist・別run/session・改ざんpublic outputを確認。far mismatchの2 observer（別登録key、profile 1/2）は`observation_eligible=1`かつ`suspicious`として受理され、正常1+不整合2からcount `1/2`、`VerdictSpoofSuspected`を導出。far observerのBridge assignmentもhost側で作成。
- `pcd3 --stage=plan`に同じ正常1+far2 proofを渡し、3件/3 distinct registered keys、profile set `{1,2}`、count `1/2`、verdict `2`（`VerdictSpoofSuspected`）を出力。
- `GOMAXPROCS=1 go test -p 1 ./cmd/pcd3 -count=1` PASS。CLIのV2 security noteを「claimed RIDをgroupするだけで、aircraft/DRIP認証はしない」に修正した。

境界: 今回のscript実行は`RUN_BRIDGE_BW6_SOLVE=1`なしのため、fresh leaf proofを実BridgeBWV2 circuit内でsolveする確認ではない（host Bridge assignmentまで）。`pcd3 --stage=plan`なのでrecursive proof、FinalBNV2 verifierのEVM検証も未実施。local proof/VKはtest-only single-contributorであり、release trust rootではない。run中swapは約6.2/7.2 GiB使用・約0.94 GiB空き、Data volumeは2.9 GiB空きだった。次はresource preflight後にBridgeBWV2 solve gate、次段のrecursive proof、FinalBNV2 EVMを順に実施する。

## 中期目標：複数Remote ID観測証明PoC（2026-10-04〜2026-11-30）

期限は2026-11-30。目標は、異なるスマホ／Raspberry Pi観測ノードのBLE Remote ID + RSSI報告を同じRID/time bucketで個別証明し、集約結果から位置不整合の危険判定を作り、最終ZK proofをEVMで検証する再現可能な研究PoC。RID broadcastの真正性やRSSI/observer位置の物理的真実性は別々の信頼問題として扱い、RID verifier未実装の間は結果をclaimed RIDに対する位置不整合と説明し、認証statusは`not_evaluated`と明記する。本番運用保証やFlutter→KMP移行は完了条件に含めない。

| 期間 | 主な成果 | 完了ゲート |
|---|---|---|
| 10/04–10/11 | 脅威モデル・信頼境界・データ/プライバシー境界を固定。RID auth、観測者登録、session/nullifier、quorum、RSSI校正の前提を文書化。 | 正常系と改ざん・重複・異session混入・未登録observerの拒否条件をテスト項目として列挙し、未認証入力の扱いを決める。 |
| 10/12–10/31 | 現行capture→leafを堅牢化。少なくとも2つの独立observerで実データを取り、校正/holdout評価を開始。Bridge proof gateを現行leafへ接続。 | 複数observerの独立captureで同じRID/time bucketの個別proof・集約前判定を再現し、誤検知/見逃しを実データで報告。ハードウェアやデータを用意できない場合は依存関係として期限前に明記し、syntheticを実測扱いしない。 |
| 11/01–11/15 | leaf→Bridge/recursive aggregation→FinalBNV2 proofの実経路を完成。 | duplicate、誤ったprofile/policy、改ざんpublic input等の拒否を含む自動testを通し、proof/public input/VKの対応を固定する。 |
| 11/16–11/30 | Final proofをEVM registry/verifierで検証し、1コマンドの再現手順と限界・残存リスクを整理。 | clean runでcapture fixture/field record→leaf proofs→aggregate/final proof→EVM verifyが連続成功。Sybil、relay、sensor spoofing、clock/provenance、RID authenticationの残課題を明示する。 |

このスケジュールは中期PoCの受入ゲートであり、現時点で達成済みを示さない。各期のゲートが実機・計算資源・未実装の信頼根に阻まれた場合、CIや暗号検査を緩めて通すのではなく、阻害要因と残作業を記録する。

## 追加監査：Remote ID状態名とDET trust rootの正規化（2026-10-04）

RFC 9575の状態を`VALID/INVALID`へ単純化すると、署名/content検証に成功した`Verified`と、Observer owner policyがDIMEも信頼した`Trusted`を混同する。またcapture utilityはDRIP検証を試みていないのに`unverified`と出力しており、RFCの「検証失敗」と誤読され得た。capture JSONL、capture-to-witness provenance/CLIは未実行を表す`not_evaluated`に変更した。これは`Unverified`や`None`と同義ではない。現在のV2 leaf/PCDはauth statusをproofへ含めないため、位置判定はclaimed RIDに対する結果として表示する。

信頼根設計へRFC 9886を追加。DETのHHIT RRにはCanonical Registration Certificate、UAS RIDのBRID RRにはBroadcast Endorsementsを使用し、apex DNSSEC必須・他階層DNSSEC推奨、DNSSECを使わない場合は証明書階層をrootまでwalkする。IANAのRAA assignmentだけではDIME/機体の登録者を信頼したことにならない。synthetic verifier fixtureはprivate-use RAA `15360..16383` / private DNSに閉じ、root bundle digest/version、expiry、失効確認時点をpolicyへ固定する。実装・auth proof bindingは未完了で、RFC用語に沿ったstate contractとtrust-root境界の設計更新である。

一次資料: [RFC 9575](https://www.rfc-editor.org/rfc/rfc9575.html) §§3.1.2, 6.4.2, Appendix A、[RFC 9886](https://www.rfc-editor.org/rfc/rfc9886.html) §§3, 5.1, 5.2, 7.1。

## 追加検証：現行leaf proofからBridgeBWV2 test-engine solve（2026-10-04）

現行relationの未確認だったBridge回路関係を、以下で再実行した。

```sh
TMPDIR=/Volumes/SSD GOTMPDIR=/tmp GOMAXPROCS=1 \
UAV_V2_BATCH_GO_TEST_TIMEOUT=15m RUN_BRIDGE_BW6_SOLVE=1 \
bash scripts/test_v2_observer_batch.sh
```

現行6,201-constraint / 8-output leafをcompileし、test-only single-contributor setupから正常・far-mismatch・profile 1/2・別run/session leaf proofを生成。fresh generated Solidity leaf verifierはproofを受理し、RID commitment/time bucket/consistency/freshness/profileの5 public signal改ざんを拒否した。`TestV2ObserverBatchProofIntegration`は14.46秒でPASSし、3 registered observersのhost batchでconsistent=1 / suspicious=2 / `VerdictSpoofSuspected`を再現。さらに実far-mismatch・profile-2 leaf proofのBridgeBWV2 assignmentをgnark test engineでsolveし、member pathとprofile pathの改ざんをそれぞれ拒否。`pcd3 --stage=plan`も同じ3件、profile set `{1,2}`、count `1/2`、verdict `2`を出力した。

fixtureは`/Volumes/SSD`の専用mktemp directoryに置かれ、script終了後にdirectoryが削除されたことを確認した。境界: Bridge回路の**test-engine solve**は現行leaf proofを含むが、Bridgeのouter BW6 Groth16 setup/proveではない。recursive Node/FinalBNV2 proof、FinalBNV2 verifier/registry EVM、実機capture/RSSIも未実施。leaf VKは使い捨てsetupで、release trust rootではない。実行後のhostはswap 9,216 MiB中8,634 MiB使用（582 MiB free）、Data volume 467 MiB freeだったため、outer setupは行わない。

artifact recoveryもコード照合した。`pcd3`は各stageでsource/dependency/artifact hashが揃う`stage.json`付き完了stageだけを再利用する。`groth16.Setup`がartifact書き出し前に中断した場合はstageができず、serializing中に中断してmetadata未完となったstageはfail-closedで手動調査/別artifact pathが必要、自動resumeではない。docsの「preserves for inspection/resume」を「completed manifest-matched stage may be reused; incomplete stage is not guaranteed to resume」に修正した。partial key directoryを自動削除/上書きする処理は追加せず、今回の使い捨てfixtureのみscript trap cleanupを確認した。

## 追加実装：観測者roster rootの明示的trust anchor化（2026-10-04）

`pcd3`は`--active-member-root`を省略すると、roster manifest内の`memberRoot`をそのままactive rootとして使っていた。これではローカルJSONの自己申告値とregistryから独立取得したrootの区別がCLI上で曖昧だったため、loaderをfail-closedに変更した。

- offline synthetic fixture以外では`--active-member-root`を必須にし、値を省略した`pcd3 --stage=plan`が明示エラーで停止することを確認。
- roster JSONからmember key列を読み、canonical BN254 decimal field値・最大16件・重複公開鍵なしを検査し、Merkle rootを再計算してmanifest宣言rootと照合する。
- explicit active rootがある場合は再計算rootとの一致を必須化。plan outputにrootの出所を表示し、operatorがauthoritative registryから取得すべき値であることを出力する。
- `--allow-manifest-root-for-test`はsynthetic offline test/demo専用の明示的opt-inとし、scriptとsample commandに反映。これはregistry authenticityを証明しない。
- `GOMAXPROCS=1 go test -p 1 ./cmd/pcd3 -count=1` PASS。欠落root、明示root、wrong active root、宣言root改ざん、重複鍵、非canonical decimalを単体testで確認。v1 checked-in leaf 3件の`pcd3 --stage=plan`はtest-only modeと明示root modeの双方で成功し、結果にroot sourceが表示された。

境界: CLIはroot入力の構造的一貫性を検査するが、RPCやオンチェーン照合を自動実行しない。explicit argumentをoperatorが本当に正しいcontractから取得したことまでは証明しない。registry contract/event/root retrieval、登録・失効の権限手順、実機observer key enrollmentは別途必要。既存の複数observer PoC要件・期限は変えていない。

## 追加修正：FinalBNV2 EVM harnessのroot/policy自己承認を解消（2026-10-04）

`FinalAttestationRegistryV2`自体は`activeMemberRoot`とapproved policyをproof public inputと比較するが、artifact-backed EVM harnessはsubmit直前に `activeMemberRoot = publicInputs[5]` と `approve(publicInputs[3])` を実行していた。したがってそのrunner単独では、proofが自分のroot/policyをregistryに承認させる自己整合性しか検査しないことを確認した。

- `verify_pcd3_final_v2_evm.js` にartifact外の `PCD3_V2_ACTIVE_MEMBER_ROOT` と `PCD3_V2_APPROVED_POLICY_COMMITMENT` を必須化。両者をcanonical BN254 decimalとして読み、proof public inputsと一致しない場合はregistryを構成する前に停止する。
- ローカルregistryへ設定する値もproof artifactからでなく、それぞれの独立期待値から設定する。
- disposable batch scriptはsynthetic roster fixtureからtest rootを読み、`pcd3 --stage=plan`が選択profile/quorumから出したpolicy commitmentをrunnerへ渡す。これはfixture内のbinding testであり、本番registryの信頼根・governanceを認証するものではない。
- `node --check scripts/verify_pcd3_final_v2_evm.js`、`bash -n scripts/test_v2_observer_batch.sh`、`npx hardhat test test/FinalAttestationRegistryV2.test.js`が成功（6 tests）。既存contract testはroot mismatch、未承認policy、重複session/proof拒否も含む。

境界: FinalBNV2の実proof artifactは未生成なので、artifact-backed EVM runnerをこの変更後にend-to-end実行したわけではない。recursive proof/setupのresource gate、実chainからroot/policyを読むRPC integration、管理者権限／変更履歴は未完了。

## 追加再検証：V2 batch scriptと期待policy配線（2026-10-04）

`TMPDIR=/Volumes/SSD GOTMPDIR=/tmp GOMAXPROCS=1 UAV_V2_BATCH_GO_TEST_TIMEOUT=15m bash scripts/test_v2_observer_batch.sh`を再実行しexit 0。現行6,201-constraint leafのcompile、synthetic V2 witnessとdisposable Groth16 setup、複数proof生成、generated leaf EVM proof/tamper check、`TestV2ObserverBatchProofIntegration`、`pcd3 --protocol=v2 --stage=plan`が成功した。planは3 distinct registered observer、同じsession/profile set `{1,2}`、consistent 1 / suspicious 2 / `VerdictSpoofSuspected`を出力した。

今回追加したshell wiringも実行された。plan outputからV2 policy commitmentを抽出し、synthetic roster JSONからmember rootを取得し、空値を拒否するguardまで通過した。これは次段のartifact-backed EVM runnerへproof外の期待値を渡すfixture試験であり、`RUN_PCD3_V2=1`を指定していないためrecursive proof/FinalBNV2 EVMは実行していない。使い捨てfixtureはscript終了後に`/Volumes/SSD/uav-v2-observer-batch.PrTl6A`が存在しないことを確認した。

## 追加統計修正：RSSI run-cluster bootstrapの未定義標本を可視化（2026-10-04）

`uav/evaluate_rssi.py`はFPR/FNRのrun-cluster bootstrapで、陽性または陰性classを含まない再標本を除外していたが、出力は要求回数1,000のみで有効再標本数を示していなかった。class構成の偏りが強いholdoutでも条件付きCIが通常の95%区間に見える可能性があるため、次を追加した。

- FPR/FNRごとにvalid/undefined bootstrap replicate数をreportする。
- evaluation reportへ、ground-truth mismatch/consistent label別のsample数と独立run数を追加し、class coverageの偏りを見えるようにする。
- `prepare_rssi_dataset.py`由来のtime uncertainty、window duration、RSSI event count、Location packet countを入力すれば、min/median/maxを品質要約に出す。metadataが一部だけある場合や不正な値は拒否し、全て無いlegacy入力なら欠落としてlimitationsへ明記する。
- 各rateに必要なtruth classを含む再標本が要求回数の95%未満の場合、percentile CIを出力しない。
- 方法・limitations・capture手順書にこの区間省略規則を説明。
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s uav -p 'test_*.py' -v` PASS、46 tests。balanced clusterのcoverageは各truth class 2 sample/2 run、class-segregated testは1 sample/1 runを出し、有効率不足の両CIが省略されることを確認。capture quality metadataの分布出力、部分欠落・時刻不確かさ不正の拒否、およびJSONL+truth CSV→normalized evaluation CSV→evaluation JSONのcapture-quality end-to-end出力を確認。

境界: これはsynthetic testによる統計実装の検証で、RSSIモデルの妥当性、実機false positive/negative、実験runの十分性を示すものではない。実機captureと独立RTK/GNSS truthを用いた完全held-out評価は未着手。

workspace内のignored/hidden fileも含む`*.jsonl`/`*.csv`のread-only inventoryを実施。UAV capture logやtruth-window datasetはなく、検出されたCSVはzk-distance内のconstraint比較summary 2件だけで、本RSSI評価には使えない。次の実測gateには複数観測端末、RID送信対象、独立truth source、分離したcalibration/evaluation runが必要。

## 追加検証：full V2 proof再試行と回帰テスト（2026-10-04）

`TMPDIR=/Volumes/SSD GOTMPDIR=/tmp GOMAXPROCS=1 RUN_BRIDGE_BW6_SOLVE=1 RUN_PCD3_V2=1 PCD3_GOMAXPROCS=1 UAV_V2_BATCH_GO_TEST_TIMEOUT=15m bash scripts/test_v2_observer_batch.sh`を開始。現行leaf回路のcompile・使い捨てleaf Groth16 proof生成・generated leaf EVM tamper検査・`TestV2ObserverBatchProofIntegration`・`pcd3 --stage=plan`までは通過し、3 distinct synthetic observersからconsistent=1 / suspicious=2 / `VerdictSpoofSuspected`を確認した。その後BridgeBWV2（2,285,785 constraints）のGroth16 setup開始を確認した。

setup中のread-only資源観測で空きメモリ34%、swap 2,918.62/4,096 MiB使用を見たためSIGINTで停止した。同時点に別のJava/Android emulator等も稼働していたため、swap増加をこのsetup単独の消費とは断定しない。停止後の空きメモリは61%。test scriptのtrapにより`/Volumes/SSD/uav-v2-observer-batch.99xNO7`は削除済み。回路拒否や証明検証のエラーではなく、Bridge setup以降のartifact・proof・FinalBNV2 EVM検証は未生成である。

中断後に低parallelismで再検証した結果：`cd aggregator && GOMAXPROCS=1 go test -p 1 ./...` PASS（pcd packageを含む、約64秒）、Python RSSI/capture/dataset suite 46 tests PASS、`cd contracts && ./node_modules/.bin/hardhat test test/FinalAttestationRegistryV2.test.js` 6 tests PASS。最後のregistry testはmock/local registry unit coverageであり、FinalBNV2実proof artifactを使うEVM E2Eの代わりではない。

再試行時の設定判断のため、現在pinされている`gnark v0.15.0` / `gnark-crypto v0.20.1`のBW6-761 Groth16 setupと`BatchScalarMultiplicationG1`をread-onlyで調査した。setupはconstraint/FFT domain規模のscalarをまとめ、scalar digit変換とJacobian結果の配列を全scalar数に比例して確保する。したがって`GOMAXPROCS=1`は実行並列度を下げても、支配的な配列長・ピーク保持量を下げる設定ではない。これは現行Macで外側proofが絶対に不可能という測定ではないが、同じ条件で低parallelismだけに期待して再試行する根拠はない。次回は十分なmemory headroomを確保した専用runnerで同じ回路・同じ信頼境界のまま実行するか、証明関係を変えずにpeak-memoryを抑えるsetup方式を検証する。

現時点の最優先未完了ゲートは、資源に余裕のある専用runnerで同一leaf VK・入力からBridge setup/proofを最後まで実行し、manifest-matched stage artifactを保持したうえでNode/FinalBNV2・実生成verifierによるEVM検証まで連続させること。実機RSSI captureと独立truthデータも未取得で、合成データの評価を実測精度として扱わない。

## 追加修正：V2結果ラベルが機体真正性を含意しないよう限定（2026-10-04）

現行設計の結果語彙は`NO_INCONSISTENCY_OBSERVED`（位置不整合を確認できなかった）と定義している一方、Go/registryのenum名は同じ数値`1`を`Trusted`として公開していた。これはDRIP認証状態`Trusted`や「機体が安全・実在する」と読み違える余地があり、仕様と実装表示を合わせた。

- V2の数値意味は`0=INSUFFICIENT_EVIDENCE`、`1=NO_INCONSISTENCY_OBSERVED`、`2=POSITION_INCONSISTENCY_SUSPECTED`と明記し、CLI plan出力にラベルと既存数値を併記。
- Solidity V2 registryのenum識別子も同じ意味へ変更。enumの数値順、10入力ABI、public signal値、registry storage/eventの数値は変更していない。V1の`Trusted`名・ABIは維持し、Goにはlegacy source-compatibility aliasを残した。
- `GOMAXPROCS=1 go test -p 1 ./pcd ./cmd/pcd3` PASS。V2 label全値、invalid値、numeric alias不変、CLI plan文言を検査。
- `cd contracts && ./node_modules/.bin/hardhat test test/FinalAttestationRegistryV2.test.js` PASS（6 tests、Solidity 1 file compile）。recordの数値`1`を`NoInconsistencyObserved`として確認。

これはV2結果の表示意味とV1互換性の明確化であり、位置判定の信頼を強める変更ではない。DRIP identity proof、独立センサー測定、FinalBNV2実proofのEVM E2Eは引き続き未完了。

## 追加運用補助：再帰V2 gateの保存fixtureからの再開（2026-10-04）

高メモリrunnerへ移す際、再帰proof gateのためだけにleaf用test setupと複数proofを作り直さなくてよいよう、`scripts/resume_v2_observer_batch.sh`を追加した。保存したnamed disposable fixture directory内のVK・leaf proof・public signalを必須確認し、同じartifact directoryで`pcd3 --stage=plan`を再計算してから`--stage=run`を起動する。stage manifestと入力hashが一致する完了済みstageだけを再利用し、最終proof artifactが一意にできた場合に限ってartifact-backed FinalBNV2 EVM harnessを呼ぶ。

検証: `bash -n scripts/resume_v2_observer_batch.sh`成功。作成した空の専用一時directoryを渡し、期待どおり最初の欠落leaf VKでexit 2・副作用なしになることを確認し、その空directoryだけを`rmdir`で削除した。shellcheckは環境に存在しない。完全fixtureを使った再帰run/EVMは未検証であり、現在のhost resource状態では再実行しない。

境界: これは再実行準備の改善で、setupの中断地点から未完stage自体を復元する機能ではない。fixtureが残っていない今回のrunにも遡及適用できない。stage未保存・metadata不整合時の再計算または別artifact directoryによる再試行、2,285,785-constraint BridgeBWV2のouter setup、Node/FinalBNV2 proofとEVM、実機BLE/RSSI＋独立truthデータは依然として未完了。実proof artifactを生成したとは扱わない。

## 追加実装：Flutter phone captureを共通V2 JSONLへ接続（2026-10-04）

以前のinventoryではFlutter側にBLE receive/parserはあるものの、V2 `capture_to_witness_v2.js` が読むshared-session-tagged JSONLはPi capture経路しかなかった。複数observer目標のうちphone nodeが欠けているため、既存`BleService.rawResults`へ次を追加した。

- BLE Raw Scan画面から明示的にstart/stopする`V2ObserverCaptureRecorder`を実装。Service Dataだけを読み、25-byte message / OpenDroneID Message Packを検査して`signal.observer-capture.v1`へ出力する。Wi-Fi manufacturer/NANはまだ対象外。
- Piと同じ`uas-id` HMAC input encodingでrun-scoped tagを作る。raw Basic IDはprivate logのraw hex内だけに保持し、advertiser addressはprocess-scoped HMACへ置き換え、shared session key自体はfileへ書かない。buffered ScanResult再emitをdeduplicateし、Message Pack内部messagesに一つのcapture event sequence/time/RSSIを保つ。
- phone GPS fix latitude/longitude/altitude/accuracyを`phone_gps_asserted_unverified`として記録。V2 adapterはそのsourceを受け、accuracy値をprivate provenanceに残し、不正値を拒否する。accuracyは現行leaf判定へ拘束されず、位置・RSSIの真実性を証明しない。
- JSONLはapp-private documentsへ専用random filenameでexclusive create。通常停止で`capture_end`を書く。app kill/stream error時はadapterがrejectするincomplete/error logになる。debug build向けADB copy commandを停止後に提示し、field raw dataの持ち出し注意を表示する。

検証: `rapidsnark_app`で`flutter test --no-pub` 10 tests PASS。recorder testsはPythonと照合した固定UAS-tag vector、raw ID/address非記録、buffered event dedup、malformed pack拒否、pack sequence/tag groupingを確認。`flutter build apk --debug --no-pub`成功。`node --test scripts/capture_to_witness_v2.test.js`は12 tests PASS（phone GPS status/accuracyのprovenance、負accuracy拒否、protocol version 2 acceptance/version 0 rejectionを含む）。`flutter analyze --no-pub`はexit 1で既存`lib/main.dart`のunused element/curly-braces 12 diagnosticsのみを報告し、今回変更したDart filesにdiagnosticはなかった。`crypto`は既lockfileのpackageをdirect dependencyとして宣言。

境界: read-only `adb devices -l`では`emulator-5554`だけが見え、実phone radio/GPSを使ったcapture、Android端末からのADB搬送、**その実出力**をNode adapterへ通してleaf proof化するE2Eは未実施。GPSはcapture全体で固定した一時点snapshotであり、移動する場合は別runが必要。実端末observer EdDSA鍵の生成・保管・登録も未実装で、このcaptureは共有session keyによるRID groupingだけで観測者を認証しない。BLE Service Data以外、Remote ID DRIP認証、phone GPS uncertaintyを回路へ含める扱い、receiver RSSI source/係数の証明も未解決。実RSSIと独立truth、recursive final proof/EVMも引き続き未完了。

## 追加検証：Flutter capture → Node adapter → Circom相互運用（2026-10-04）

Pi parser (`uav/observer_capture.py`)とFlutter recorderはASTM/OpenDroneID protocol version 2を正しく出していたが、Node `capture_to_witness_v2.js`だけがversion 0を期待し、これまでのJS synthetic fixtureもinvalid version 0だった。Dartから生成したcaptureをNodeへ渡すtestを追加して、この経路不通を検出した。Node parserとJS fixtureをversion 2へ修正し、version 0をrejectするtestを足した。

`node --test scripts/test_flutter_capture_interop.test.js` PASS。test専用Dart toolがrecorder本体からBasic ID+Location入りMessage Pack JSONLを生成し、shared key/provenance/同一capture-event sequenceを確認する。captureをmode 0644にした状態はNode private-file guardが拒否し、0600へ保護後はCLIがwitnessとprovenanceを作成。phone GPS source/accuracy、3 event RSSI median、3 Location messageを検査し、その実witnessを現行`uav_witness_attestation_v2.circom`のWASMでcalculateして非空witnessを得た。`node --test scripts/capture_to_witness_v2.test.js`も12 tests PASS。ADB copy commandへ`umask 077`を加え、手動transferでもNodeのmode gateを満たすようにした。

これは合成固定ID/keyによるDart recorder実装のcross-runtime testで、実radio/phone GPS、field record、Groth16 leaf proof、複数observer aggregate、final proof/EVMではない。使い捨てテストcapture/keyはtemp directory内で作り、test終了後にcleanupする。実capture→conversionの再現性、observer鍵enrollment、実機RSSI＋truth、recursive FinalBNV2→EVMは未達のまま。

## 追加回帰確認：現行の軽量suite一式（2026-10-04）

今回の変更内容を含む現行worktreeで、proof setupを起動しない検証を再実行した。

- `cd aggregator && go test ./...` PASS。全Go packageを確認。
- `node --test scripts/capture_to_witness_v2.test.js scripts/test_flutter_capture_interop.test.js` PASS（13 tests）。Dart recorder JSONLから現行Circom leafの非空witnessを計算する相互運用を含む。
- `python3 -m unittest discover -s uav -p 'test_*.py'` PASS（46 tests）。RSSI evaluator、capture normalizer、privacy/file validationのunit tests。
- `cd contracts && npm test` PASS（45 tests）。V2 registryのpolicy/root/freshness/replay拒否を含むが、V2 registry caseはmock verifierによるunit testであり、実FinalBNV2 proofを使うEVM E2Eではない。
- 最初に試した`python3 -m pytest`はこのsystem Pythonにpytest moduleがなく起動しなかった。repositoryの既存unittest runnerで同じ対象suiteを実行している。

proof setupを避けた理由を再確認するため`sysctl vm.swapusage`をread-onlyで取得したところ、6,144 MiB中4,747 MiBを使用、空きは1,396 MiBだった。既往のBridgeBWV2 setupがこのMacでswap逼迫のため停止しており、今回はsetupを再起動していない。integration testsの成功は単体leaf witness、host preflight、mock verifier coverageを越える外側proofの証拠ではない。

実測gateの入力有無もread-onlyで再確認した。`adb devices -l`は`emulator-5554`のみで、repository内にcapture JSONL、RSSI calibration CSV、独立truth CSVは見つからなかった。従って今回のPython 46 testsはcapture/evaluation logicの合成テストであり、field observationの代わりにはならない。

この再確認でコード側の軽量suiteに新しい失敗は見つからなかった。次の完了gateは、前回のleaf proofsを保持したfixtureと十分なmemory headroomのあるrunnerでBridgeBWV2からNode/FinalBNV2を生成し、independently supplied member root/policyを用いてartifact-backed V2 EVM harnessへ通すこと。実機radio/GPS/RSSIと独立ground truthによる評価も別途必要であり、synthetic suiteの件数を実測結果へ読み替えない。

## 追加実装：Flutter／Pi captureからV2 leaf proof・複数observer preflight（2026-10-04）

これまではFlutter recorder→Node adapter→CircomとPi parser unit testが別々に存在し、異なるcapture実装が同一の複数observer batchへ入る証拠がなかった。Piの実`observer_capture.capture` BLE callbackをfake scannerで駆動するfixtureを2件生成し、Flutter Dart recorder fixtureと共通run key・claimed Basic ID・time bucketを使って共通adapterへ渡すintegrationを追加した。

- 3つのJSONLを`capture_to_witness_v2.js`で変換し、RID commitment/session salt/time bucketの一致を確認。Phone 1台＋Pi 2台は異なるobserver ID、BabyJubJub鍵、asserted location、校正profileを使う（profile 7/2/1）。
- 各witnessを現行`uav_witness_attestation_v2.circom`で計算し、`snarkjs wtns check`で充足を確認。
- 一時的なsingle-contributor test ceremonyから同一VKを作り、3つのGroth16 leaf proofを生成してそれぞれ`groth16 verify`で確認。固定テストobserver rosterは秘密鍵1/2/3の公開鍵に一致する。
- その**同じ3 proof artifact**と生成VKをGo `pcd3 --protocol=v2 --stage=plan`へ渡し、active test rosterの異なる3 memberとして検証されることを確認。profile set `{1,2,7}`と `consistent=1 / suspicious=2 / POSITION_INCONSISTENCY_SUSPECTED` がplanに出た。
- leaf proofが正しい状態からpublic `consistency_ok` signalだけを反転した場合はGroth16 verificationで拒否。同じobserver proof/publicを2 slotへコピーした場合は重複registry indexで拒否。別run/sessionで作ったが同じVKで個別には有効なleaf proofを3件目へ混ぜた場合は、同一RID commitment/session不一致で拒否。
- `uav/test_pi_capture_interop.py`はPi capture callbackのMessage Pack/event/time/RSSI grouping、shared pseudonym scope、private file modeをunittestで検査し、既存CI用Python suiteにも入る。開発者向けコマンドと限界は`uav/OBSERVER_CAPTURE.md`に記録。

検証: `python3 -m unittest discover -s uav -p 'test_*.py'` PASS（47 tests）、`node --test scripts/capture_to_witness_v2.test.js scripts/test_flutter_capture_interop.test.js scripts/test_cross_platform_capture_interop.test.js` PASS（14 tests）。負例を含むcross-platform end-to-end testは約226秒。全fixture、ceremony、zkey、proofはprivate temp directory内で生成しcleanupした。

境界: BLE callbackは合成Message Packを返すfake scannerで、1 contributorのsetup/VKはtest専用でありrelease trust rootではない。実Android/Pi radio/GPS、実DRIP署名、production enrollment root、再帰Bridge/Node/FinalBNV2 proof、FinalBNV2 EVM検証はまだない。複数proofの`pcd3 --stage=plan`成功を再帰proofや最終on-chain attestationの成功とみなさない。実RSSI＋独立truth評価も未達。Flutter/Circomを必要とするcross-platform integrationはCI環境には追加しておらず、CIはPi callbackのPython unittest境界までを確認する。

## 実測準備：RSSI field-study preregistrationとtruth-window template（2026-10-04）

現行capture inventoryでは実機JSONL、校正CSV、独立truth CSVがなく、ADBにもemulatorしか見えていない。データができてから閾値やrun分割を事後変更する事故を避けるため、field studyを始める前に埋める`uav/field-study-template/study-preregistration.md`と、calibration/evaluationを分けたheader-only truth-window CSV templateを追加した。

- position-error threshold、RSSI tolerance、校正距離/profile、held-out run IDs、truth source/vertical datum/time uncertainty、environment、privacy/custodyを測定前に記入する。
- 1行/観測者×対象×decision windowのtruth ledgerは既存`prepare_rssi_dataset.py`と同じ14-column schemaを使い、`uav/test_field_study_template.py`で両テンプレートのheader-only内容を`WINDOW_FIELDS`と照合する。
- 完了したtruth ledger/raw capture/keyをGitへ入れないよう、既存`.gitignore`のroot `captures/`と`uav/captures/`を確認し、copy先として明示した。
- `python3 -m unittest discover -s uav -p 'test_*.py'` PASS（48 tests）。`git check-ignore -v uav/captures/heldout-truth.csv`が`.gitignore:53:uav/captures/`で無視されることを確認。

これは測定手順・schema準備であり、入力データやRSSI性能結果を作ったものではない。実機Android/Pi、送信機、独立survey/RTK truth、分離された複数calibration/evaluation runがないため、false positive/negativeのfield評価は未実施。recursive FinalBNV2 proof/EVMも引き続き未完了。

## AI実装規約を追加（2026-10-04）

repositoryに既存のroot `AGENTS.md`がなかったため、PoC固有の信頼境界、個人/field data保護、使い捨てsingle-contributor鍵の扱い、`pcd3 --stage=plan`とrecursive EVM proofの証拠差、重いsetup前のmemory確認、既存のGo/Python/Hardhat check、および実装→local check→publish→CI log/root-cause repairの手順を簡潔に記した。

検証: `git diff --check`と追加ファイルのtrailing-whitespace確認は成功。規約は認証実装やproof pipelineの動作証拠を増やすものではない。実機RSSI評価、recursive FinalBNV2 proof/EVMの未達状態は変わらない。

## 再帰setup cacheの中断復旧を安全化（2026-10-04）

`pcd3 --stage=run`のGroth16 setup cache保存を、公開先stage directoryへ直接書く方式から、同じfilesystem上の一時directoryへ全artifactとhash metadataを書き終えてからdirectory renameで公開する方式に変更した。metadataとCCS/proving key/verifying keyのhash検査に通る完了済み一時cacheがあれば、再実行時に公開済みstageへ復旧する。途中・破損・source/dependency不一致の一時cacheは採用も削除もせず保持し、新しいsetupを行う。既存の不完全な公開済みstageも自動修復・上書きしない。

検証: `cd aggregator && go test ./...` PASS。復旧helperのunit testに加え、小さいBN254 circuitの実際のGroth16 CCS/PK/VKを保存・hash照合し、tamperされたproving keyはreject、同時に完全なcacheは復旧することを確認した。

境界: これは完了済みsetup serializationの途中公開によるcache破損を防ぎ、rename前に停止した完全artifactを再利用する改善であり、Groth16 setup自体が中断した地点から演算を続けるものではない。証明stageの中間proofもまだ永続化していない。BridgeBWV2 outer setup（2,285,785 constraints）を現hostのメモリ制約下で再起動しておらず、Node/FinalBNV2 proof、実生成verifierによるEVM検証、実機RSSI＋独立truth測定の未達状態に変更はない。

## V1/V2の機体認証境界を設計書で分離（2026-10-04）

現行`uav_witness_attestation_v2.circom`と`VerifyV2ObserverBatch`を確認したところ、RIDはclaimed broadcast IDとしてgroupされ、V2 circuitにはDRIP認証出力・UA signature verifier・endorsement chain/root verifierがない。一方、設計書の「現在の回路」節にはlegacy V1の`drone_auth_ok`説明が現行回路の状態と読める形で残っていたため、V1 legacyと現行V2を分け、V2 proofの意味を「同じ申告RIDに対する観測者証明・位置不整合判定」に限定した。将来のDRIP信頼状態は署名とsigned-contentの検証、登録連鎖のtrust bundle/version、有効性policyをproof/statementへ束縛するまで最終判定に含めない。

一次資料としてRFC EditorのRFC 9575を照合。RFCは、Broadcast EndorsementでDET→公開鍵の登録chainを検証するだけでは観測されたUAの鍵保有や新しい送信者を示せず、unique/unpredictableなUA-signed evidenceと内容検証が別途必要と定める。従って現行の`not_evaluated`境界と「位置不整合の疑い」表示は保持し、機体真正性の主張へ拡張しない。変更後の設計書はV2 source/batch contractに照合したが、これはDRIP実装やfield proofではない。

追加回帰: `pcd3 --stage=plan`のV2出力testも更新し、bounded verdictに加えて「claimed RIDのgroupingだけであり、aircraft/DRIP認証ではない」という注意書きが将来のCLI変更で消えた場合に失敗するようにした。

検証: `GOMAXPROCS=1 go test -p 1 -count=1 ./cmd/pcd3` PASS。read-only host checkでは搭載RAM 16 GiB。最初の確認では`vm_stat`上のfree pagesが約0.72 GiB、作業volume空き7.2 GiBだった。workspaceからcapture JSONL・calibration/truth CSV・`final-proof`命名のartifactは見つからず、見つかった`summary.csv` 2件は別のzk-distance比較結果だったため、その時点ではBridgeBWV2 outer setupを起動していない。

同日後刻の再確認では`vm_stat` free pagesが約0.19 GiB、作業volume空き4.9 GiBまで減少していた。`adb devices -l`では`emulator-5554`のみ。GitHub APIのread-only queryではrepositoryに登録済みself-hosted runnerは0件、`gh run list`には2026-09-28の既存Verify成功runが1件だけだった。これらはfield testや巨大Groth16 setupを動かせるrunnerが存在する証拠ではない。

## BridgeBWV2 setupのallocation見積り（旧計算・後日訂正）

`gnark v0.15.0` / `gnark-crypto v0.20.1`の固定module cacheにある実装を再確認した。BridgeBWV2の既測定R1CSは2,285,785 constraints。BW6-761 `fft.NewDomain`は次の2冪へ丸めるためdomain `D=4,194,304`。setupは`Z[D]`をG1 scalar入力へappendするのでscalar数`N`は少なくともD。

当時はBW6-761 `fr.Element=48B`, `fp.Element=96B`、G1 Jacobian 288B、affine 192Bとして、scalar input・`uint16` digits・Jacobian・affineのobject sizeを合計し2.25 GiBと記録した。これは各配列サイズの合計であり、全配列が同時liveであることを証明しない。後続の現行source reviewでdigitsの最後のreadとaffine output allocationが別phaseと確認したため、2.25 GiBを同時allocation floorとして使用しない。訂正した保守的なoverlap boundとcurrent dependency/R1CSは下記2026-10-05 entryを参照。いずれの算出もpeak RAMやrunner容量の推奨値ではなく、`GOMAXPROCS`を下げてもslice lengthは減らない。

このsource-derived boundから、容量未知の標準runnerや空きのない現hostを安全と判断する根拠は得られなかった。現hostではsetupを起動せず、次回はピークRSS/swapを計測可能で十分なheadroomとdiskを持つ隔離runnerで段階別に測るか、証明関係を変えないsetup memory最適化を検討する。

## V2 recursive中間proofを完全witnessに束縛してcache（2026-10-04）

`runProofPipelineV2`は中断後の再実行でBridgeBWV2 observer proof 3件、NodeBLSV2、PromoteBLSV2、NodeBWV2を毎回作り直していた。`proof-cache-v1`を追加し、cache key/metadataを完全serialized witness hash、stage source/constraint/VK hash、outer/inner curve、Solidity target、labelへ束縛。再利用時はcache metadataとproof/public-witness file hashを照合し、現stage VKでGroth16 proofを再検証してから返す。ディスクにはproof・public witness・metadataだけを0600で保存し、directoryは0700、private/full assignmentはhash計算だけに使い保存しない。各cacheは同じfilesystem内の一時directoryに完成後renameして公開する。FinalBNV2自体とfinal outputは未cacheで、final proof段で止まるとそのproofは再生成する。

検証: 小さな実BN254 circuitのsetup/proofで同一assignmentのcache hitが同一proof bytesを返すこと、private assignmentをcache filesに含めないこと、違うunsatisfied assignmentがcache hitしないこと、tampered proof bytesがhash検査でrejectされることを確認。`GOMAXPROCS=1 go test -p 1 -count=1 ./cmd/pcd3` PASS、`GOMAXPROCS=1 go test -p 1 ./...` PASS。`bash -n scripts/resume_v2_observer_batch.sh`成功し、カスタムartifact path配下の`proof-cache-v1/`と`proofs-v2/`が`.gitignore`対象になることを`git check-ignore -v`で確認した。

境界: cache unit testは小型BN254 circuitによるもので、実BridgeBWV2/Node/FinalBNV2のproof cache hitやfull recursive E2Eの証拠ではない。cache未完成でrename前に中断したproofは再proofとなる場合があり、FinalBNV2/final-artifact出力もcacheされない。resource headroomのない現hostではouter setupを再起動していない。実proof→FinalBNV2 EVM、実機RSSI＋独立truthは未達のまま。

## FinalBNV2 proof cacheとfinal artifactの原子的公開（2026-10-05）

前日のcache実装で残っていた最終BN proofを`proveAndVerifyCached`へ接続。FinalBNV2も完全serialized witness、stage source/constraint/VK、BN254/BW6-761、Solidity targetに束縛され、再開時にはcached public witnessとproofを現VKで検証してから使う。secret/full witnessは引き続き保存しない。最終出力directory名はRID/time等をそのまま露出せず、domain-separated identityのSHA-256（quorum、public statement、verifier hash、proof hashを含む）とする。新たなproof bytesは別directoryになり、既存artifactを上書きしない。

最終JSONとproof hashはowner-only一時directoryへ先にすべて書き、fsync後、同じparent内のrenameでdirectory一括公開する。同じ完全なfile集合・byte列が既にある場合のみ再実行を成功扱いし、欠落・追加・改変ファイルやsymlink/権限不適合は上書きせずfail-closedにする。一時directory作成中にkillされた場合、完成先は公開されずtempを残す。

検証: `GOMAXPROCS=1 go test -p 1 -count=1 ./cmd/pcd3` PASS。filesystem helper testでcomplete directory publish、完全同一成果物のidempotent resume、改変済みproofの保持と拒否、partial directoryの保持と拒否を確認。巨大recursive setup/E2Eはこのhostのresource headroom不足により起動しない。

## 受け入れ条件の再確認と現host資源（2026-10-05）

現行worktreeのcomponent verificationを再実行: `GOMAXPROCS=1 go test -p 1 -count=1 ./...` PASS、`python3 -m unittest discover -s uav -p 'test_*.py'`で48件PASS、`cd contracts && npm test`で45件PASS。Hardhat結果にはV1のactual Groth16→実verifier→registry testとV2 registry/compiler testがあるが、V2 registry側はmock verifier。したがってこれはV2 recursive FinalBNV2 proof→EVM実証の代替ではない。

追加で`node --test scripts/capture_to_witness_v2.test.js scripts/test_cross_platform_capture_interop.test.js scripts/test_flutter_capture_interop.test.js`を実行し14件PASS。Flutter形式＋Pi形式のsynthetic capture 3件からleaf witness/proofを生成し、同一claimed RID/session bucketの`pcd3 --stage=plan`が受理、observer重複・改ざんpublic signal・別run/session混入proofが拒否されることを実行確認した。これはfixture生成プログラム同士の相互運用であり、独立した実端末/実機RF観測の証拠ではない。

V2 full integration entrypointは`scripts/test_v2_observer_batch.sh`にあり、`RUN_PCD3_V2=1`で有効化される。ただし現在の再測定では物理RAM 16 GiB、free pages 3,534（16 KiB/pageで約55 MiB）、workspace volume空き3.2 GiB。`adb devices -l`はAndroid emulatorのみを示し、`gh api repos/SMRI2170/zkp-m1-v2/actions/runners`のself-hosted runner数は0。workspace内にもreal capture/truth datasetはなく、field-studyの`.example` templateのみ。従ってfull setupをこのhostで再実行したり、synthetic fixtureを実機評価として扱わない。

次の現実的な実行条件は十分なRAM・scratch diskを確保した隔離hostで同じfixture directoryを保持してfull V2 entrypointを通し、FinalBNV2 EVM結果とresource計測を保存すること。その後、少なくとも複数observer deviceと独立した位置ground truthを用意して評価する必要がある。Oct–Novのgoalはactiveのままで、受入条件(3)(4)は未達。

## 中期目標の進捗：gnark更新とcurrent leaf→batch再検証（2026-10-05）

中期目標（2026-10-04〜2026-11-30）の実装基盤を点検し、`aggregator`がgnark v0.15.0 / gnark-crypto v0.20.1を固定していることを確認した。gnark公式release notesはv0.16.0で一部回路に関するsoundness修正を案内し更新を強く推奨している。現repoのどの回路が影響対象かはrelease noteだけでは特定できないため、既存artifactとの互換性・性能差を検証しながらv0.16.3 / gnark-crypto v0.21.0へ更新した。これは特定の脆弱性悪用や現repo回路への影響を確認したという意味ではない。公式情報: [gnark releases](https://github.com/Consensys/gnark/releases)、[v0.16.3 go.mod](https://raw.githubusercontent.com/Consensys/gnark/v0.16.3/go.mod)。

- `GOMAXPROCS=1 go test -p 1 -run '^$' ./...`で全package compile PASS、`GOMAXPROCS=1 go test -p 1 -count=1 -timeout 10m ./...`で全Go test PASS（`pcd`は約69秒）。
- `RUN_BRIDGE_BW6_COMPILE=1 GOMAXPROCS=1 go test -p 1 -count=1 ./pcd -run '^TestBridgeBWV2CompileOnly$' -v` PASS。current BridgeBWV2は3,295,111 constraints / 9 public inputs。旧v0.15.0で記録した2,285,785 constraintsより約44%増えた。ライブラリ更新間の観測差であり、特定修正が増加の原因だとは切り分けていない。
- 同scriptをCircom 2.2.3 / snarkjs 0.7.6 / circomlib 2.0.5 / circomlibjs 0.1.7のtoolchain preflight付きにし、実行時の版ずれを拒否するようにした。`TMPDIR=/tmp GOTMPDIR=/tmp GOMAXPROCS=1 UAV_V2_BATCH_GO_TEST_TIMEOUT=10m bash scripts/test_v2_observer_batch.sh`を再実行してPASS。Go 1.26.5上でcurrent 6,201-constraint leaf circuitのtest-only setup/proofsを新規生成し、生成EVM verifierは正常proofを受理、RID commitment・time bucket・consistency・freshness・profile改ざんを拒否。Goのproof-backed batch testは3 distinct registered test observersでPASSし、1 consistent + 2 suspiciousから`POSITION_INCONSISTENCY_SUSPECTED`を出力。`pcd3 --stage=plan`も3件を再検証し、profile set `{1,2}`と同じ判定を導出した。fixtureはscriptが作成・終了時にcleanupした。

境界: `RUN_PCD3_V2`は有効化していないため、この結果はBridgeBWV2 outer setup/proof、recursive Node/FinalBNV2、FinalBNV2 artifact-backed EVMのE2Eではない。rosterとleaf setupはtest-onlyであり、RID/機体真正性やDRIP認証も検証しない。実機captureおよび独立truth ledgerもない。したがって11月の完了条件(3)(4)は引き続き未達で、今回のdependency更新だけで中期目標を達成扱いにはしない。

## DRIP認証stateと検証順序を一次仕様に照合（2026-10-05）

`docs/protocol/multi-observer-risk-v1-design.md`の認証state表をRFC Editorの一次資料へ再照合した。RFC 9575 Appendix Aは`None / Partial / Unsupported / Unverifiable / Verified / Trusted / Unverified / Questionable / Conflicting`を定義し、`Verified`にはその時点までに同じclaimed senderから受け取った全Authentication messageの署名検証と§6.4.2のcontent validationが必要。§3.1.2/§6.4.2ではBroadcast Endorsement chainによる登録key検証と、sessionごとに少なくとも一度、UAS RID elementを含むAuthenticationの署名検証後に別ソースで内容相関する要件を分けている。許容閾値外のcontentはsignature failure同様に拒否する。仕様書の文言をこのstate/順序に合わせて明確化した。

RFC 9886 §7.1/§6.2.1.5とも照合し、self-signed HHIT certificateのDNSSEC要求、DNSSECなしでの証明書chain walk、private-use RAAのprivate DNS/test-only境界に既存設計との矛盾はない。対応箇所は`docs/protocol/multi-observer-risk-v1-design.md` §4。これは要件(1)のdesign evidenceを精密化したものに限り、capture側のDRIP parser、trust bundle verifier、proof bindingは未実装。現行V2状態は`not_evaluated`のまま。

## RSSI評価の時刻品質ゲートを強制（2026-10-05）

評価監査で、事前登録票に最大時刻ずれの欄がある一方、評価CLIは上限を受け取らず、時刻品質metadataなしでも偽陽性・偽陰性を算出できることを確認した。これでは独立truthとの時間整合が弱いwindowを、測定結果として誤って数える可能性があった。

- `evaluate_rssi.py`に必須引数`--max-time-uncertainty-ms`を追加。各評価windowの時刻不確かさ、window幅、capture observation件数、Location packet件数を必須化し、欠落・不正値・時刻不確かさがwindow幅以上・事前登録上限超過を拒否する。
- 合成unit testに必須metadata、missing、window境界、preregister上限超過の拒否を追加。prepare→evaluateのテストCLIとcapture手順も新しい引数・列に合わせた。
- 検証: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s uav -p 'test_*.py'` PASS（48 tests）。

境界: CLIに渡した上限とCSV metadataが事前登録後に変更されていないことを、このツール単体は認証しない。試験票・元capture・独立truthの保管と変更履歴を別途管理する必要がある。今回は合成テストのみで、実RSSI性能・現地の時刻精度は検証していない。実機Android/Piと独立truthデータ、FinalBNV2 recursive proof/EVMの未達状態に変更はない。

## FinalBNV2 EVM runnerのartifact信頼境界・公開入力検査を強化（2026-10-05）

実FinalBNV2 artifactをローカルEVM verifierへ渡す`contracts/scripts/verify_pcd3_final_v2_evm.js`を確認し、artifact内のverifier source path/hashだけを互いに照合していた自己参照的な検査を修正した。runnerはartifact外で独立に承認した`PCD3_V2_EXPECTED_VERIFIER_SHA256`との一致を必須にする。`test_v2_observer_batch.sh`とresume scriptはFinalBNV2のstage VKからexport・照合されたverifier sourceを独立値としてhashしrunnerへ渡す。別途artifact内`minimumQuorum`も、外部承認値と一致しuint32内であることを要求する。`pcd3 --quorum`の値を同じ承認値としてrunnerへ伝える。生成verifierのnegative testは、従来の一部3入力ではなく10個すべてのpublic inputを1ずつ改変して拒否を確認する。

検証: metadata照合の成功・不一致・zero・uint32 overflow、および独立verifier hash一致・不一致・不正形式のunit testを追加。`cd contracts && npm test` PASS（47 tests）、`bash -n scripts/test_v2_observer_batch.sh`、`node --check contracts/scripts/verify_pcd3_final_v2_evm.js`、`git diff --check`も成功。

追加監査で、registryは10個すべての公開入力をBN254 scalar範囲に制限する一方、artifact-backed runnerはprofile-set rootしかEVM call前に個別確認していないと分かった。artifact parserを10入力すべてのcanonical decimal / BN254 field element検査へ統一し、入力数不一致・先頭zero・各indexのfield境界をtestした。`GOMAXPROCS=1 go test -p 1 -timeout 2m ./cmd/pcd3`も成功。Hardhat全体は再実行後48 tests passing。

境界: 現worktreeには現行FinalBNV2 proof artifactがなく、10入力すべてのnegative EVM callを含むartifact-backed runner自体は実行していない。現host確認ではworkspace volume空き3.8 GiB、free pages約0.57 GiBで、resource-intensiveなrecursive proofを起動しない判断は変わらない。これはEVM harnessの検査強化であり、recursive proof/EVM E2Eの完了とは扱わない。

## current V2 leafのphone/Pi複数観測proof再検証（2026-10-05）

SSD上に保持されていたOct 4の合成fixtureを調べたところ、leaf WASMが現行circuitの入力数と合わず（旧WASM側30 input slots、current witness 18）、current relationのfixtureとして再利用できないことが分かった。そのfixtureからは`pcd3 --stage=plan`が通るものの、旧VKに対する検証なのでcurrent-source evidenceに数えない。不足分として追加生成したfar-mismatch用synthetic inputは旧WASMで生成不能と確認し、その追加分と空の出力directoryだけを削除した（fixture生成scriptから再作成可能）。それ以外の古いfixtureは変更せず保管し、下記を現行sourceから作り直した。

- `TMPDIR=/Volumes/SSD UAV_V2_BATCH_KEEP_FIXTURES=1 bash scripts/test_v2_observer_batch.sh`を実行。current V2 Circomを6,201 constraints / 8 public outputsでcompileし、使い捨てtest-only setupからcurrent leaf proofを生成した。generated leaf EVM verifierは正常proofを受理し、RID commitment・time bucket・consistency・freshness・profileのpublic signal改ざんを拒否。proof-backed Go `TestV2ObserverBatchProofIntegration`はPASSし、distinct registered observer 3件、正常/quorumおよびfar-mismatch verdict、duplicate observer、許可外profile、異session/別run混入、member/profile/nullifier path改ざん拒否まで確認した。
- 同scriptの`pcd3 --stage=plan`はcurrent proof 3件を再検証し、1 consistent + 2 suspiciousから`POSITION_INCONSISTENCY_SUSPECTED`、許可profile集合`{1,2}`、3 distinct observersを導出した。`RUN_PCD3_V2`は指定せず、再帰setup/proofは起動していない。test-only rosterと単一contributor setupはrelease用鍵・observer enrollment根ではない。
- `node --test --test-concurrency=1 scripts/capture_to_witness_v2.test.js scripts/test_flutter_capture_interop.test.js scripts/test_cross_platform_capture_interop.test.js`をlocal POSIX temp (`TMPDIR=/tmp`)で実行し14/14 PASS。Dart phone recorder + 2つのPi callback fixtureから各leaf witness/proofを作り、current leafとmulti-observer preflightで検証する。別run/session・重複・改ざん等の負例も含む。すべて合成capture/fake radioで、実機観測ではない。
- stale fixtureの誤再開を避けるため`resume_v2_observer_batch.sh`はcurrent Circomを再compileし、saved disposable zkeyをcurrent R1CS + Powers of Tauに対してverifyしてからVKをexport比較するようにした。古いOct 4 fixtureへresume scriptを試し、`snarkjs zkey verify`が`INVALID: Different circuit parameters`で停止し、recursive stageへ進まず、一時compile directoryもtrapで削除された。
- `--validate-only` optionを追加し、再帰setupなしでfixture互換性だけ確認できるようにした。current fixtureは`ZKey Ok!`後にsaved VKとの一致が取れてPASS。旧fixtureは同じコマンドで`Different circuit parameters`となりFAIL-CLOSED。両方ともtemporary compile directoryは削除済み。

環境上の注意: 外付けSSDはExFATでPOSIX owner/modeを保持しないため、0600/0700を要求するcapture adapter testは`TMPDIR=/Volumes/SSD`だと意図どおり拒否した。規則を弱めず、当該privacy testはmode semanticsを持つlocal `/tmp`で再実行しPASS。SSDに残したfixtureは固定test keyの合成データであり、秘密captureやfield keyを置く用途には使わない。最終recursive proof artifactは依然存在せず、16 GiB hostのswapは約2.87/4 GiB使用・local volume空き約3.3 GiBのため、BridgeBWV2/Node/FinalBNV2のsetup/proofとartifact-backed FinalBNV2 EVMは未実施。`adb devices`はemulatorのみ、self-hosted runnerは0、独立truth/capture dataも未確認。

## BridgeBWV2 current-relation test-engine再実行のresource preflight（2026-10-05）

`RUN_BRIDGE_BW6_SOLVE=1`はouter Groth16 setupではなく、current 6,201-constraint leaf proofを含むBridgeBWV2 relationのcompile/solve gateである。同一current relationは10月4日のログ（上記「追加検証：現行leaf proofからBridgeBWV2 test-engine solve」）でsolveおよびpath改ざん拒否まで確認済み。ただしその実行後に記録されたswapは8.634/9.0 GiB使用・582 MiB空きだった。

現時点の再読取ではこのhostのswap totalは4 GiB、2.851 GiB使用・1.245 GiB空き、local volume空き3.3 GiB、接続実機はなくAndroid emulatorのみ、registered self-hosted runnerは0。以前のsolveで観測したswap使用量に対するheadroomがないため、gateを再起動せず既存current-relation evidenceを採用する判断とした。これはresource判断であり回路失敗ではない。新しいgateは実行していない。外部high-memory hostまたは十分なmemory/swap headroomを確保後、同じ保存fixture・`--validate-only`通過後に再開する。

## Flutter実BLE captureの既知scan failureをfail-closed化（2026-10-05）

BLE Raw Scan画面からV2 recorderが実サービスストリームを購読し、app-private Documents配下へ保存する経路を再確認した。以前は`FlutterBluePlus.startScan`例外を握り潰し、scan result streamの異常もcapture記録に反映しなかったため、既知の受信失敗があっても閉じレコードだけを持つ部分captureになり得た。

- adapter off、scan start例外、scan result stream error、予期しないstream closeを`capture_error`としてprivate JSONLへ記録する。例外本文は端末path等が混入し得るため保存せず、sourceとerror typeだけを残す。
- `capture_to_witness_v2.js`は`capture_error`を持つfileを、capture_endがあっても拒否する回帰テストを追加。RSSI dataset normalizerも同じくrejectする既存gateをregression testで確認した。radioが黙って落とす広告までは検知できないため、RF callback coverageの限界は別途記録する。
- 検証: Flutter recorder test 4件PASS、対象Dart 3ファイルの`flutter analyze` PASS、Node capture parser negative test PASS、`uav`全50 tests PASS、Flutter recorder→Node→Circom WASM synthetic interop PASS、`git diff --check` PASS。

境界: BLE platform channelをmockしたunit/instrumentation testではなく、物理phoneでのscan failure injectionもfield captureも未実施。RSSIの実測評価およびFinalBNV2 recursive proof/EVMの未達状態は変わらない。

## proof/field作業の環境再確認（2026-10-05）

Flutter・RSSI回帰後にread-only確認: local work volume空き3.5 GiB、swap 4 GiB中2.763 GiB使用（1.333 GiB free）、16 KiB/pageの`vm_stat` free pages 12,198（約0.19 GiB）。`adb devices -l`はemulatorのみ、GitHub self-hosted runnerは0。workspace内の通常検索ではphysical capture、独立truth ledger、FinalBNV2 final proof artifactは見つからなかった。従ってBridgeBWV2 outer setup/FinalBNV2 recursive provingもfield evaluationも起動していない。Flutter部分検証の成功は物理無線・RSSI性能や最終EVM proofの証拠ではない。

## RSSI evaluatorの座標CSVをowner-only入力に制限（2026-10-05）

`prepare_rssi_dataset.py`はexact-position CSVとtruth/capture入力にsymlink拒否・current-user ownership・regular file・0600以下を要求する一方、`evaluate_rssi.py`は通常の`Path.read_bytes()`で読み、保護条件を迂回できた。評価CSVにもexact observer/aircraft coordinatesが含まれるため、evaluator側にも`O_NOFOLLOW`、`fstat`のregular/current-user検査とowner-read/no group-other access条件を適用した。0600を超える権限とsymlinkを拒否するCLI回帰testを追加し、入力CSVとreportのowner-only境界を文書化。

検証: evaluator tests 14件PASS（広いpermissionとsymlinkの拒否を含む）、`uav`全50 tests PASS、`git diff --check` PASS。実capture・ground truthを処理した評価結果はない。

## RSSI評価の事前登録run数をレポートのadequacy gateへ接続（2026-10-05）

Held-out性能値を出せても、3観測者や同一flight内の多数windowを独立標本として誤読すると評価の信頼性を過大に見せる。既存evaluatorは`run_id` cluster bootstrapと各truth labelのrun coverageを出すが、事前登録した最低run数との比較はなかった。

- Preregistrationにtruth classごとの最低independent `run_id`数、期待する95% false-rate interval precision、target未達時のexploratory扱い、incomplete/conflicting/unsupported groupの報告方法を追加。
- `evaluate_rssi.py`へ必須CLI option `--minimum-independent-runs-per-class`を追加。`multi_observer.finalized_truth_class_coverage`はFPR/FNRへ実際に入る3-distinct-observerの最終二値decisionだけを数え、`preregistered_run_count_adequacy`はそのrun数を宣言値と比較する。未finalized groupのrun coverageでadequacyを満たしたように扱わない。
- `--maximum-95-false-rate-ci-width`も必須化し、aggregate FPR/FNR bootstrap intervalの各幅を事前登録targetと照合。interval unavailableはprecision target missとして示し、run floorとprecision gateを分離した。reportはcaller値を用いるため、private preregistrationとの一致は現地作業前後に確認する必要があり、統計上のbias/representativenessは保証しない。
- 6 consistent + 6 mismatch独立runで正しい3-observer decisionが出る合成testはrun-count/interval-width両targetを満たすことを確認。conflicting-only runはraw label coverageに見えてもfinalized coverage 0、unavailable intervalで両gateが未達となる。必須CLI option負例、範囲検査、`--help`の回帰を含め`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s uav -p 'test_*.py'` PASS（57 tests）。`python3 uav/evaluate_rssi.py --help`も実行成功。

境界: preregistered valueはCLI caller入力で、試験者がheld-outを見たあと値を引き下げないことの外部監査は別途必要。ここで追加したtest dataは合成のみで、実機RSSI、独立truth、実performance intervalは得ていない。

再帰proofを実行するhost preflightの再確認: 物理RAM 16 GiB、system volume空きは前回107 MiBと読んだ後にread-only再読取で2.0 GiBへ戻った。`~/Library/Caches/go-build`は2.5 GiB、swapは3 GiB中2.77 GiB使用（約305 MiB free）。cache/tempは削除していない。`adb devices -l`はAndroid emulatorのみ、GitHub self-hosted runnersは0。環境値が変動しheadroomがないためBridgeBWV2 outer setup/FinalBNV2 provingは起動しなかった。

## RSSI評価条件を単一machine-readable preregistrationへ集約（2026-10-05）

以前のCLIは閾値・quorum・sample floor・interval precisionを個別に受け取り、別途記録したprivate preregistrationとの不一致を検知できなかった。評価者が設定を転記するときの手違いを防ぐため、owner-private JSONを評価器の唯一のpolicy/run-plan入力とした。

- `uav/evaluate_rssi.py`は`--preregistration`を必須化。schemaを厳密検査し、duplicate key・非標準数値・未定義/追加field・symlink・非owner-only fileを拒否する。policy値と期待calibration/evaluation run IDはJSONから取得。
- calibration/evaluation CSVのrun ID集合を宣言済みsetと完全一致させる。欠落または余分なrunがあればmetrics算出前に停止する。reportにはpreregistrationとCSVのSHA-256/byte lengthを保存。
- `uav/field-study-template/study-preregistration.json.example`を追加。Markdownは実験方法メモ専用にし、evaluator設定の二重管理を避ける。report hashはJSONの作成時期、truth/data provenance、sensor honestyを証明しない点を明記。
- capture-normalizerからevaluatorへのend-to-end synthetic regressionをJSON経由へ更新。duplicate-key、calibration/evaluation run mismatch、owner permission/symlink拒否をtest。

検証: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s uav -p 'test_*.py'` 61 tests PASS、`evaluate_rssi.py --help`は新CLI表示を確認、`git diff --check` PASS。実機capture/ground truthはなく、RSSI性能の評価結果は出ていない。以前のCLI引数に関する履歴は当時の仕様として残すが、以後はJSON interfaceを使う。

## 現行worktreeのGo/Hardhat regression再確認（2026-10-05）

- `cd aggregator && GOMAXPROCS=1 go test -p 1 ./...` PASS。pcd packageは67.308秒。`RUN_PCD3_V2`、Bridge Groth16/solve、recursive compile等のopt-in gateは有効化していない。
- `cd contracts && npm test` PASS、48 tests。FinalAttestationRegistryV2 mock-verifier suiteとgenerated verifier ABI/compiler testsを含むが、現行FinalBNV2実proof artifactのEVM検証ではない。
- GitHub APIのread-only照会で、このrepositoryに登録されたself-hosted runnerは0台。

この確認はcurrent-sourceの回帰とmock/ABI境界の証拠であり、Bridge/Node/FinalBNV2実setup・proof・EVMを一続きにした検証や実機RSSI性能評価を代替しない。直近hostは16 GiB RAM、3 GiB swap中約2.59 GiB使用、volume空き3.7 GiBであるため、高制約recursive setupは実行していない。

## 高コストrecursive gateのfixture誤削除を防止（2026-10-05）

`scripts/test_v2_observer_batch.sh`は`RUN_PCD3_V2=1`でBridge/Node/FinalBNV2のsetup/proofを開始する一方、`UAV_V2_BATCH_KEEP_FIXTURES=1`がなければ終了時trapがfixture/cache一式を削除する。長時間setupの中断・失敗後に同一artifactから調査/再開する要件と衝突するため、`RUN_PCD3_V2=1`時は保持optionなしで一時directoryを作る前にexit 2でfail-closedにした。通常のleaf→batch preflightでは従来どおりcleanupされる。

検証: `bash -n scripts/test_v2_observer_batch.sh` PASS。`RUN_PCD3_V2=1`のみで起動するnegative checkは保持option不足の明示文言とexit 2を確認し、fixture作成まで進まなかった。再帰gate自体はこのhostのRAM/swap/空き容量不足により起動していない。

## BW6 Groth16のsource-derived live-array下限を現行依存に合わせ訂正（2026-10-05）

以前の2.25 GiB計算では、scalar input・`uint16` digit array・Jacobian result・affine outputを同時liveとして加算していた。現行依存の実source (`gnark v0.16.3`, `gnark-crypto v0.21.0`)を読み直すと、`BatchScalarMultiplicationG1`はdigit loopの後に`BatchJacobianToAffineG1`を呼び、affine resultをそこで新たにallocateする。`digits`の参照はloop後に不要となるため、sourceだけからscalar/digitsとaffine outputの同時liveを保証できない。2.25 GiBはphase中のobject allocation sumであり、確定したoverlap lower boundとして扱わない。

現在のBridgeBWV2は3,295,111 constraints。`fft.NewDomain`はこれをD=4,194,304へ丸め、Groth16 BW6-761 setupのscalar vectorはZ[D]を含むためN≥D。`G1Jac`は288B、`G1Affine`は192B。affine conversion中は入力point sliceと新規出力sliceが同時に必要なので、これだけで`D × (288+192) = 2,013,265,920 bytes = 1.875 GiB`以上のbacking arraysがliveになる。conversionのN-byte zero mask、setupABC/FFT/G2/他key配列、runtime等は除外した部分下限で、peak/RAM recommendationではない。`GOMAXPROCS`を下げても各slice lengthは変わらない。

根拠source: `$GOMODCACHE/github.com/consensys/gnark@v0.16.3/backend/groth16/bw6-761/setup.go` (Z[D]をscalar vectorへ追加)、`gnark-crypto@v0.21.0/ecc/bw6-761/fr/fft/domain.go` (`NextPowerOfTwo`)、`ecc/bw6-761/g1.go` (G1Jac/G1Affineサイズ・affine output allocation)、`ecc/bw6-761/multiexp.go` (377-bit scalar chunksとdigits allocation)。これは前回見積りの精度を訂正するsource auditであり、新しいsetup peak測定ではない。

## FlutterのPoC状態画面でdemo proofとV2/chainを分離（2026-10-05）

既存の「チェーン」tabは汎用single-circuit proofのvalid flagだけを受け取り、登録observer leaf proof・複数端末集約待ちのように表示していた。verdict enumも`Trusted`/`Spoof suspected`とし、現在未接続のV2/registry stateを実在する結果に誤読させる作りだった。

- tabを「PoC状況」に変更。現在の状態を「単体デモproof」とし、Remote ID認証・観測者登録・V2複数observer aggregation・Final proof・EVM registryが画面と未接続であることを明記。
- 結果語彙を「位置不整合はこのpolicyでは観測されず」「位置不整合の疑い」へ変更し、機体真正性・物理位置の保証ではないことを併記。no-mismatchをTrusted/Safeと表現しないwidget regression testsを追加。
- generic proof verifierの真偽を`_lastProofCryptographicallyVerified`で別保持し、時系列demoのsemantic risk値とPoC状態画面のproof-verification表示を混同しない。

検証: `flutter test`全体14 tests PASS。変更したmodel/page/widget testに対する`flutter analyze` PASS（No issues found）。`main.dart`を含めた限定analyzeは既存の未使用要素等12 diagnosticsを報告したが、今回の変更対象ファイルだけのanalyzeはclean。これはUIの意味を正確にしたもので、アプリからV2 leaf/aggregation/chainへの実接続を作ったわけではない。

## FinalBNV2再帰経路の実setupを再開しresource stop（2026-10-05）

外付けSSDに残っていた現行leaf fixtureへ`PCD3_GOMAXPROCS=1 bash scripts/resume_v2_observer_batch.sh <fixture> --validate-only`を実行。current Circomは6,201 constraints / 8 outputsで再compileされ、saved zkeyはcurrent R1CSとPowers of Tauに対して`ZKey Ok!`、export VKもfixtureのVKと一致した。続けてresumeを開始し、3件のcurrent synthetic leaf proofが再検証され、`pcd3 --stage=plan`は1 consistent + 2 suspicious、`POSITION_INCONSISTENCY_SUSPECTED`を再導出した。

`pcd3 --stage=run`では`BridgeBWV2`が2,520,507 constraintsでcompileし、ローカルGroth16 setupへ入った。約8分、CPU 1コアで計算した時点でswap使用量が約2.31 GiBから3.94 GiBへ増加し（swap totalも5 GiBへ拡張）、内蔵volume空きが約3.9 GiBから1.6 GiBへ減ったためSIGINTで安全停止した。終了後にpcd3プロセスはなく、`pcd3-artifacts`には空のroot directoryのみ。current leaf fixture/proofは保持され、setup stage key/manifest・Bridge proof・Node/FinalBNV2 proof・生成verifierによるEVM検証は未生成。

これは再帰回路の正否ではなく、この16 GiB Macと現在のswap/disk headroomでouter setupを完了できなかったという実測である。同一hostで直ちに再試行せず、より大きいRAMと十分なswap/作業volumeを持つ環境で保存fixtureをresumeする。合成fixtureの互換性検査・plan成功は、実機RSSI評価や再帰proof/EVM E2E達成とは区別する。

同時に`adb devices -l`と`uav/`配下のcapture形式（CSV/JSONL/PCAP）をread-only確認したが、接続はAndroid emulatorのみで、実測captureは存在しなかった。従って実RSSIのfalse-positive/false-negative評価も開始できない。実機複数ノード、Remote ID送信源、独立した位置truthデータの準備が必要。

## Capture event内の異なるRID tag混入を拒否（2026-10-05）

capture-to-witness adapterは、event内の1レコードに対象UAS tagがあればその`capture_event_seq`全体をdecision windowへ入れていた。そのため同じBLE callbackの別Location rowに別のrun-scoped UAS tagがあっても、現行実装ではその位置値を混ぜて署名witnessを作れてしまう。

`parseCaptureBytes`で各非null UAS tagの形式（24桁lowercase hex）を検査し、同じcapture eventに異なるtagが複数あればfail-closedで拒否する回帰testを追加。`node --test scripts/capture_to_witness_v2.test.js`は14 tests PASS。さらに使い捨てleaf ceremonyのPowers-of-Tau powerを14から13へ下げた。current R1CS 6,201 constraintsを`2^13 = 8,192` capacityで満たすため、今後relation変更時は必要powerを再確認する。

`TMPDIR=/tmp node --test --test-concurrency=1 scripts/test_cross_platform_capture_interop.test.js`も1 test PASS。Phone recorder + 2 Pi-format synthetic captureから現行V2 leaf proofを各1件生成・verifyし、Goの3-observer `pcd3 --stage=plan`とduplicate・tamper・別session拒否まで通した。実機ではなくfixtureであり、operational enrollment・独立した物理sensor truth・recursive proof/EVMの証拠ではない。内蔵disk空きが約944 MiBまで減っているため、このturnでは追加の高コストtestを起動していない。

## Powers-of-Tau容量をceremony開始前にfail-closed検査（2026-10-05）

power 14から13への最適化後、回路変更で制約が8,192を超えても「ceremonyを始めてからGroth16 setupで失敗」する可能性が残っていた。cross-runtime testと`scripts/test_v2_observer_batch.sh`に、Circomのlinear/non-linear countを読むcapacity preflightを追加し、compiler output形式が読めない場合、制約数が不正な場合、またはpower 13の`2^13 = 8,192`を超える場合はPowers-of-Tau ceremonyを始める前に停止する。

検証: 現行Circom 2.2.3の実出力と`snarkjs r1cs info`はともに6,201 constraintsを報告し、capacity gateは`6,201 <= 8,192`でPASS。unit testは6,201受理、8,193拒否、output形式不明の拒否を確認。`node --check scripts/test_cross_platform_capture_interop.test.js`、capacity unit test 1/1 PASS、`bash -n scripts/test_v2_observer_batch.sh` PASS。高コストceremonyは起動していない。

## 現行フィールド評価・capture adapter回帰再確認（2026-10-05）

goalの中期化確認後、外部機材や大きなsetupを使わずに再検証できる評価コードとleaf witness adapterをcurrent worktreeで再実行した。

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s uav -p 'test_*.py' -v`: 61 tests PASS。preregistration、校正/evaluationのrun分離、独立truth join、複数観測quorumのFPR/FNR集計、private input/output、capture parserの回帰を含む。
- `node --test scripts/capture_to_witness_v2.test.js`: 14 tests PASS。合成BLE captureから現行V2 Circom witnessが計算でき、RID tag混入・別session key・不正な時刻/校正等を拒否することを確認。
- `cd contracts && npm test`: 48 tests PASS。V2 registry policy/member root/freshness/replay拒否と生成verifier ABI検査を含む。ただしV2 registry suiteはmock verifierを使い、生成verifier compiler testもABI幅・入力形式の検査である。current FinalBNV2 proof artifactをEVMで検証した結果ではない。

いずれもfixture/合成入力の検証であり、実RSSIの誤検知・見逃しや独立したground truthの証拠ではない。`adb devices -l`で見えるのはAndroid emulatorのみで、現在のworkspaceに実測captureもない。内蔵volume空きは約946 MiBのため、今回もrecursive Groth16 setup/FinalBNV2 EVM gateは起動していない。したがって達成条件(3)(4)は未達のまま。次に必要なのは実機複数ノードと独立truth datasetの用意、およびより大きいRAM/scratch diskを持つ隔離runnerでのcurrent recursive proof再開である。
