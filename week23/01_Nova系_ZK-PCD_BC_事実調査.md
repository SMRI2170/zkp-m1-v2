# Week23 — Nova系・秘密保護型PCD・ブロックチェーンの事実調査

- 調査日：2026-10-11
- 対象：UAV Remote IDに対する複数独立観測者の位置/RSSI秘匿型証明・累積・検証
- 調査対象：研究リポジトリ **SMRI2170/zkp-m1-v2** のWeek20/21資料と実装、一次論文、Sonobe/Microsoft Nova公式実装、Besu公式資料
- 文書の性質：**調査報告。新たなPCD実装や3実機試験の成功を意味しない。**
- 判定区分：**[一次資料]** 論文/公式資料で記載、**[既存研究記録]** 本リポジトリで記録・実装、**[未検証]** 今回の構成で実験結果なし、**[技術的整理]** 資料から説明できる機能の違い

## 1. 何を実現したかったのか

同一Remote IDを観測する、互いに独立したノードA（Pi 4）、B（Pi 4）、C（Pixel 8）が、それぞれ自分の秘密の位置・RSSI・時刻等でZKPを生成する。

- Aは自身の秘密Witness **wA** から証明 **πA** を生成する。
- BはAの**元Witnessを受け取らず**、Aの有効な証明/秘密を隠した継続用状態と、自身の **wB** から **πAB** を生成したい。
- CもA・Bの元Witnessを受け取らず、**πAB** と自身の **wC** から **πABC** を生成したい。
- 第三者は最終証明から、定義された計算・セッション拘束・計上規則を検証したい。

これは単なる個別ZKPの提出より強い「前段の証明を内包/継続したい」という要求である。ただし、**前段証明の再帰検証・IVCのprover状態の引継ぎ・PCDの証明合成は同じAPI・同じデータ形式とは限らない**。[一次資料 S1, S2]

証明の有効性は、実際にRemote ID電波を受信したという事実やRSSI・GPSの物理的真実性の証明ではない。

## 2. 既存研究で確認されていること

| 項目 | 確認された内容 | 根拠 | 判定 |
|---|---|---|---|
| Nova＋CycleFold逐次PoC | 同一プロセスで3ステップのIVCを生成・検証。状態にはdrone_id/time_bucketと整合/疑い/段数の累積値を保持 | Week20/08、ソースR1 | [既存研究記録] |
| M2 Macでの比較 | Week20/08にNova側のstep生成約130–280ms、gnark自己再帰系7–9秒、Nova側ピークメモリ456MB、gnark系約4GBと記録。**異なる証明構成・環境に一般化不可** | Week20/08 | [既存研究記録] |
| Pixel 8上のNova | Week20/09でアプリUI経由の3ステップを実行（個々のstep 485–1198ms、verify約172msと記録） | Week20/09、ソースR2 | [既存研究記録] |
| Pixel 8上の単発Circom | 小規模回路のMopro/arkworksベース生成402ms・検証166msと記録。**RapidSnarkやフルRemote ID回路の計測ではない** | Week20/09 | [既存研究記録] |
| Sonobeの状態引継ぎAPI | 当時のSonobeではIVCProof出力・from_ivc_proofによる継続用APIが存在したとコード調査に記載 | Week20/12 | [既存研究記録] |
| 跨端末継続実装 | 既存uav_chain_step.rsとnova-mobileは単一のprover状態を順次更新する構成であり、A→B→Cの独立プロセス間転送成功は記録されていない | Week20/12、ソースR1/R2 | [未検証] |
| Witnessの構造 | 旧SonobeのIVCProofが、内部Witnessを保持する W_i / w_i 等のフィールドを含むとWeek20/12・13がソース解析で記録 | Week20/12・13 | [既存研究記録] |
| 非ブラインディング設定 | Week20/13は対象PoCが H=false を用いていたと記録 | Week20/13 | [既存研究記録] |
| 秘密座標の復元実験 | シリアライズ済み状態を別ノードで受け取り、Aの元GPS/RSSIを復元する独立テストの成功は今回確認していない | Week20/13、R1/R2 | [未検証] |
| 受信状態の検証 | Week21/01では、旧Sonobeのfrom_ivc_proofでの検証責務を指摘し、明示verifyを行うラッパーを**設計**。完成実装は未確認 | Week21/01 | [既存研究記録・未実装] |
| Membership/nullifier | 登録観測者のmembership・同一セッション内の二重計上防止が未実装と記録 | Week20/12・13 | [既存研究記録] |

**整理**：既存PoCの走行IVC状態をそのまま他者に渡す案には秘密保護上の問題がある。ただし、**その事実だけからNova系のすべてのZK-IVC/PCDが不可能だとはいえない**。

### 既存資料

- [Week20/08 Nova PoC実装結果](../week20/08_Nova方式B_PoC実装結果.md)
- [Week20/09 モバイル実測](../week20/09_モバイル実行_circom_Noir_Nova_設計.md)
- [Week20/12 複数ノード蓄積の設計課題](../week20/12_Nova方式B_複数ノード蓄積を可能にする設計課題.md)
- [Week20/13 Witness漏洩に関する実現性検証](../week20/13_プライバシー保護型K-of-N設計案の実現性検証.md)
- [Week21/01 受信状態の検証漏れと設計案](../week21/01_方式Bの検証漏れ問題と対処設計.md)
- [R1: Novaの逐次PoC](../nova_poc/uav_chain_step.rs)
- [R2: Android Novaラッパー](../nova_poc/nova-mobile/src/lib.rs)

## 3. Nova系論文について一次資料から確認できたこと

| 技術 | 論文に記載された機能 | 今回のA→B→C実装について確認できた範囲 | 根拠 |
|---|---|---|---|
| **Nova** | Foldingによる逐次IVC。更新時の計算をこれまでの全ステップ数に比例させずに進める | 既存PoCでは端末内逐次実行まで。秘密を保護した別主体への引継ぎは未実証 | S1、既存記録 |
| **SuperNova** | 異なるステップ回路を使うnon-uniform IVC。実行した命令回路の規模に応じたコストを狙う | **非一様IVCそのものがAのWitnessを隠した跨主体引継ぎを保証するとは論文要約に書かれていない** | S2 |
| **HyperNova** | CCS上のFolding、複数インスタンスのFolding、PCDへの一般化を容易にする構造。2026-02-20改訂では**NovaBlindFold**というゼロ知識化を記載 | 秘密を隠す構成は**論文で提案されている**。現在のPi 4/Pixel 8でのA→B→C安全継続成功は未確認 | S3 |
| **KiloNova** | 非一様計算のための前処理型再帰SNARK、multi-predicate PCD、中間インスタンスの定数サイズ化。2026-02-17改訂 | **PCDを提案する事実と、特定のUAV観測者間で秘密Witnessを渡さず安全に継続できる実装が存在することは別**。本研究への移植実験なし | S4 |
| **MicroNova / NeutronNova** | Microsoft NovaのREADMEに、MicroSpartan/MicroNova関連コンポーネントと実験的NeutronNovaを記載 | 本研究での端末間秘密継続・EVM上の実測は未実施 | S5 |

### NovaBlindFoldの範囲

HyperNova ePrint 2023/573 の2026-02-20改訂版アブストラクトは、NovaのFoldingがもつblindingの性質を使ったゼロ知識化手法**NovaBlindFold**を明示する。[S3]

**したがって、論文レベルで「Nova系ではWitnessを隠せない」とは言えない。**

ただし、これは以下を確認したこととは異なる。

1. 旧Sonobeの走行IVCProofをそのまま最新版へ渡せること。
2. Aが作った秘密保護状態をBが検証し、B自身の秘密Witnessだけで続きをproveできること。
3. Cまで異なる端末で継続でき、改竄・別Remote ID・重複登録も拒否できること。
4. Android / Raspberry Pi 上で実用性能が出ること。

これら4点は本研究に関して**未検証**である。

## 4. Sonobeの公式実装とドキュメントの差

**[公式リポジトリの現在のmainブランチ]** [S6]

- Sonobe公式READMEのサポート表は、**Nova = stable、CycleFold = stable、HyperNova = to be merged、ProtoGalaxy = to be merged** と記載している。
- **SuperNova**はそのサポート表には列挙されていない。**SuperNeo**は別の研究でありSuperNovaと同一ではない。
- ライブラリ自体は **0.1.0-alpha.1** のプレリリースとされ、公開APIの変更可能性が注意されている。
- 旧ブランチ/旧版READMEにはHyperNova・ProtoGalaxyの実装記載もある。**「mainでは未統合」と「どの版にも実装がない」は同義ではない**。

**[旧公式ZK層ドキュメント]** [S7]

旧Sonobeドキュメント「Nova's Zero-Knowledge Layer」は以下の用途を区別する。

- **Use-case 1**：元の個別インスタンスをランダムな満足インスタンスとFoldして秘匿し、別の主体に送って累積処理させる案。アプリケーション側の追加実装が必要と記載。
- **Use-case 2**：処理終了後、最終Deciderの生成を別主体に委託する案。Decider回路の変更が必要と記載。
- **Use-case 3**：最後のIVC状態について、さらにFoldingを継続せずゼロ知識証明として渡す案。旧ドキュメントはこの用途の実装例を提供。

**注**：この旧ドキュメントのAPIや「現在の実装」という表現を2026年mainブランチの実装保証に読み替えない。

Microsoftの公式Nova READMEは、IVC証明を圧縮する前にランダムインスタンスとFoldしてゼロ知識化する実装について述べる。[S5] **最終圧縮時の秘匿と、独立したBがAの秘密なしで継続する能力は別の要件**である。

## 5. BC版で確認できる事実と証明連鎖との違い

Besu公式QBFT資料は、承認済みValidatorがブロックに合意し、**2/3以上のValidator署名**を経て確定する方式を説明する。ビザンチン耐故障としては最低4 Validatorが必要と記載する。[S8]

| 論点 | Nova系IVC/PCD | Besu＋個別Groth16＋Solidity |
|---|---|---|
| Aの計算をBの証明の内部に含める | 再帰/PCD構成として研究対象 | **ブロックの検証・保存だけでは行われない**。別途再帰証明が必要 |
| 複数個別証明の共有・検証 | PCD構成/署名プロトコル等を設計 | Solidity verifierを実装すれば、個々のGroth16を独立検証できる |
| 証明の圧縮 | 再帰証明・Deciderなどを利用できる | 台帳の性質そのものには証明圧縮がない |
| 証拠の受付と確定履歴 | 別の証拠管理・合意手段が必要 | QBFTがブロック確定を、コントラクトが採否条件を扱える |
| Witnessのプライバシー | ZK化方式と公開入力の設計次第 | 個別ZKPと公開入力・メタデータの設計次第 |
| 受信RF・位置・RSSIの真実性 | 計算証明だけでは保証しない | ZKP/BCだけでは保証しない |

**区別すべきこと**：

- **[技術的整理]** BCは「証明の内包」を直接置き換えない。
- **[技術的整理]** Nova/PCDは「複数の独立運営主体が同じ提出集合・履歴に合意すること」を自動で提供しない。
- **[技術的整理]** BCなしでも署名付き共同検証、複数検証者、Merkleログは構成できる。したがってBCが**必須**とはこの時点で証明されていない。
- **[未検証]** 本研究の3観測ノードについて「BC方式の方が速い／安全／安い」という同条件の実験結果はまだない。
- **[未検証]** PCD・BC・PCD＋BCのどれが研究要件を最も満たすかは未確定。

## 6. Remote ID実機条件として現在分かっていること

- **[研究者報告]** 研究室のDJI機体から、Remote IDを**BLEではなくWi-Fi Beaconで受信した**。
- **[未確認]** 正式な機種はMatrice 300 RTKまたは350 RTKの可能性があるが、型番とファームウェアは未確定。
- **[未確認]** Pi 4 A/BとPixel 8 Cの3台が、同じ実飛行から必要な802.11 Beacon/Remote ID/RSSI/タイムスタンプをそろえて取得できること。
- **[未確認]** 機体が申告した位置と独立したRTK/飛行ログの「真値」を同期して比較した実測データ。

上記はNova・PCDの論文比較とは独立の実験上の前提である。現在の証明PoCには保存済み/模擬データを使えても、それを3台同時RF受信成功と記録してはならない。

## 7. 未検証事項と、何を確認すれば結論が出るか

この節は**実験済み結果ではなく、調査から抽出された不足事項**である。

| 未検証事項 | 必要な証拠 |
|---|---|
| 旧Sonobe走行状態による漏洩 | Aの秘密Witnessを含む状態の構造検査／受信B側での具体的な再構築テスト |
| 新版/旧版Sonobe ZK層の利用可能性 | 使用するGit commit・API・Use-case別の動作記録 |
| A→B→Cの秘密保護型継続 | **3つの独立プロセス**で他者の元Witnessを受け取らず継続・検証に成功したログ |
| 前状態の改竄への対応 | 検証前の状態の改竄、別session、別policy、別RID、replayをrejectするテスト |
| 匿名資格と二重計上 | membership・nullifierと公開情報の関連付けを確認するテスト |
| PCD/BCの速度とコスト | 同一データ/回路/端末・明示されたセキュリティ条件でprove/verify/bytes/RAM/latency/gasを計測 |
| BCの必須性 | 単一管理者、署名付き複数管理者、QBFT等の各信頼モデルで何が異なるかの比較 |

「実装できなかった」は、**ソフトウェア版・試したアルゴリズム・要件・再現可能な失敗ログ**が揃った場合にのみ、本実験の結果として記録できる。
「この研究に適さない」は、**機能要件・計算資源・遅延・プライバシー・運用者の信頼関係**を明示して初めて評価できる。

## 8. 現時点で書ける調査結論

1. **[確認済み]** 本研究の既存Nova/Sonobe PoCは単一端末/単一proverの逐次計算を実証した。複数独立観測者の秘密保護型IVC継続は未実証。
2. **[確認済み]** 当時利用したSonobeの走行IVCProofはWitnessを含むとソース解析され、AからBへのそのままの受け渡しは当初の秘密保持要求と衝突する。
3. **[確認済み]** HyperNovaの2026年改訂論文にはNovaBlindFoldによるゼロ知識化が存在する。KiloNovaはmulti-predicate PCDを提案する。**Nova系で秘密保護型継続が一般に不可能とはいえない。**
4. **[確認済み]** 現行Sonobe mainはHyperNovaを「統合待ち」と記載する。旧文書のZK層の機能が新版のアプリ向けAPIとしてそのまま利用できることは保証されていない。
5. **[確認済み]** Besu/QBFTはブロックの共同確定を提供する一方、個別証明を別の証明へ再帰的に内包する機能をそれ自体では提供しない。
6. **[未決定]** 今回のUAV研究でBC方式を選択すべきか、Nova系PCDを継続すべきか、併用すべきかは、現在の文献・旧PoC結果のみでは結論できない。

**重要：本報告はNova系不採用またはBC採用を既定の結論としない。**

## 9. 一次資料・公式実装

- **S1** Nova（研究原典と実装） — https://github.com/microsoft/Nova
- **S2** SuperNova, IACR ePrint 2022/1758 — https://eprint.iacr.org/2022/1758
- **S3** HyperNova, IACR ePrint 2023/573、2026-02-20改訂 — https://eprint.iacr.org/2023/573
- **S4** KiloNova, IACR ePrint 2023/1579、2026-02-17改訂 — https://eprint.iacr.org/2023/1579
- **S5** Microsoft Nova公式README（ゼロ知識化・圧縮・実験的NeutronNova） — https://github.com/microsoft/Nova
- **S6** Sonobe公式README・mainサポート表（Nova stable、HyperNova to be merged、0.1.0-alpha.1） — https://github.com/ethereum/sonobe/blob/main/README.md
- **S7** Sonobe旧ZK層ガイド（Use-case 1/2/3の違い） — https://sonobe.pse.dev/usage/nova-zk.html
- **S8** Besu公式QBFT・PoA資料 — https://docs.besu-eth.org/private-networks/how-to/configure/consensus/qbft / https://docs.besu-eth.org/private-networks/concepts/poa
- **関連ADR（現時点ではProposed）** — [2026-10-11 Nova→Besu移行に関する仮説](../docs/research/2026-10-11_nova-to-remoteid-besu_adr.md)

---

*調査対象の論文・mainブランチは変更され得る。将来の再評価では取得日とGit commit、実験環境を固定すること。*
