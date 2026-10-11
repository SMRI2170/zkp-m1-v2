# ADR: Nova/IVC研究からWi-Fi Beacon Remote ID・独立ZKP・Besu/QBFT研究への移行

- 作成日: 2026-10-11
- ステータス: **Proposed / 技術選定の仮説。実飛行・BC E2Eの実証前**
- 実装Epic: #28。要求・脅威: #10 #11。3観測者のBCなし比較基線: #26。BC採用対照実装: #29–#37。BC導入効果の比較: #20。
- 位置づけ: 2026年7月のNova研究成果を否定せず、**研究が解こうとしている問題が「1計算の逐次履歴」から「独立観測者の共同検証・確定」へ変わった**ことを明示する設計判断記録（ADR）。

## 0. 前段の研究成果と未解決課題

1. `week20/08_Nova方式B_PoC実装結果.md`：Sonobe Nova+CycleFoldで一つのプロセス内の3ステップIVCが動作。比較したgnark再帰PoCより軽量という結果を得た。
2. `week20/09_モバイル実行_circom_Noir_Nova_設計.md`：Pixel 8でNovaの3ステップ生成・検証を実証（UI経由の個々のステップ485–1198ms、verify約172ms）。Circom小規模回路はMopro/arkworks backendで証明402ms、検証166ms。**RapidSnarkでも402ms出るとの測定ではない**。
3. `week20/12_Nova方式B_複数ノード蓄積を可能にする設計課題.md`：Sonobeの`IVCProof`受け渡しAPIは存在するが、受信状態の検証、秘密witnessの取扱い、参加者間並列更新、membership/nullifierは未解決。
4. `week20/13_プライバシー保護型K-of-N設計案の実現性検証.md`：当該Sonobe実装の**生の走行`IVCProof`にはWitnessが含まれ、端末A→端末Bへ渡しても秘密の観測値を開示しない設計は成立しない**。安全なPCD/圧縮証明・個別独立proof等の別設計が必要。
5. `week21/01_方式Bの検証漏れ問題と対処設計.md`：`from_ivc_proof`は受け取った状態を自動検証せず、利用時に明示的な検証・受理制御が必要。署名ログによる事後責任追跡等も設計検討済み、実装未完了。
6. **過大な主張を避ける**：以上は**本プロジェクトの特定のSonobe/Nova PoCに対する結論**。「Nova全般がマルチパーティ不可」「NovaのFoldingは暗号的に不正な前段を常に受理する」「HyperNovaも絶対に不可能」とは言わない。適切な最終証明/Decider検証と、段階的なインポート時の検証責務は別。

## 1. 新しく確定した実機観測の事実と未確定事項

研究室で使用するDJIの機体について、**Remote IDをBluetooth LEではなくWi-Fi Beaconとして受信したことが実験で確認された**（研究者からの報告）。この一次観測はMVPの入力方式として優先する。

- **機種は未確定**：DJI Matrice **300 RTK / 350 RTK のいずれかの可能性**。推測で型番を固定しない。機体ラベル・機体情報/コントローラー・ファームウェア版を撮影/記録して確定する。
- Wi-Fi Beaconの取得を成功させた**受信機・ドライバ・周波数/チャネル・PHY・生802.11フレーム/IE・タイムスタンプ・RSSI採取経路**を必ず特定する。送信方式は観測で実証済みだが、Pi4×2とPixel8の全員が同じビーコン/RSSIを受信できるかはまだ未確認。
- `rapidsnark_app/README.md`にはAndroidの`WifiOdidScanner.kt`/Wi-Fi IE取得が記載されるが、そのAPIと取得可能なRSSI・受信頻度・スキャン制約を**実機で確認**。標準Android Wi-FiスキャンのRSSIは生パケット単位に対応しない場合がある。Pi側はモニターモード/USBアダプタ対応を先に検証。
- 機体の放送位置（`claimedPosition`）と真値（`groundTruth`）を分ける。M300/M350の飛行ログ/RTK等で位置真値と時間同期を確認し、RSSIによる偽装検知率・偽警報・判断不能を測定する。
- 日本国内の制度上の飛行許可・安全対策は別途確認する。誤ったRemote ID電波の空中送信は初期実験に不要。なりすまし等の異常ケースは録画済み/記録済みデータのオフライン再生で試験する。

## 2. Nova／SuperNova／HyperNovaの適合性判断

| 方式 | 得意な処理 | 現段階の採用判断 | 不採用/保留の**理由（条件付き）** |
|---|---|---|---|
| Nova / Sonobe（既存PoC） | **同一計算状態の長期・逐次IVC** | **MVPの跨端末共同確定には採用しない** | 現在の走行IVC状態を端末間にそのまま渡せばWitness漏洩の懸念。単一プロセスでの実測を3つの独立端末へ転用不可。受付/資格/独立合意を提供しない。 |
| SuperNova | ステップごとに異なる回路を使う**非一様IVC** | **保留** | 今回の主要課題は「異なる種類の命令を混在」ではなく**独立した秘密観測者による提出の資格・一意性・採否・監査**。非一様化ではこの問題は自動解消しない。 |
| HyperNova | CCS上の効率的Folding、複数インスタンス・PCDへの拡張可能性 | **代替研究候補として継続監視** | PCD/zk-IVCの研究可能性は存在。だが秘密Witnessを端末間に渡さない安全な**分散proverプロトコル**、提出順/検閲、セッション/資格、EVM着地の実装・性能の検証が別途必要。**数学的に不可とは結論しない**。 |
| 各端末の独立Circom/Groth16 | 観測者ごとの秘密入力について**自己完結の証明** | **採用候補（まず実験）** | 端末間でWitnessを転送する必要がなく、各端末が並列生成。Proofが複数になるため直接EVM検証時のガス/確定時間増を測定。 |

根拠：
- SuperNova: https://eprint.iacr.org/2022/1758
- HyperNova: https://www.microsoft.com/en-us/research/publication/hypernova-recursive-arguments-for-customizable-constraint-systems/
- Sonobe（実装バージョンに注意）: https://github.com/privacy-ethereum/sonobe
- SonobeのIVC proofはデフォルトでzero knowledgeとは限らない: https://sonobe.pse.dev/usage/nova-zk.html

**重要：BCとIVCは置換関係ではない。** IVCは計算列の証明圧縮、BCは独立主体の受付・検証済み履歴・合意・監査を扱う。BCはセンサー真値、受信した事実、すべての可能な観測が提出されたことを自動保証しない。将来は独立leaf proofsを再帰圧縮し、その最終証明をBCに提出する**併用**も比較する。

## 3. 現段階の参照設計

```text
DJI UAV (Wi-Fi Beacon Remote ID: claimed position/time/identifier)
       |                         |                         |
   Pi 4 A                     Pi 4 B                    Pixel 8 C
   Wi-Fi monitor RX           Wi-Fi monitor RX           Android Wi-Fi RX
   local RSSI/timestamp       local RSSI/timestamp       local RSSI/timestamp
   receiver location          receiver location          receiver location
       |                         |                         |
    Local preliminary risk/consistency with UNKNOWN (no BC wait)
       |                         |                         |
    private witness + fresh randomized commitment + Circom/Groth16 proof
       |                         |                         |
    signed (sessionId, commitment, proof digest, verdict, epoch/policy)
       \________________________|_________________________/
                                |
         [optional P2P cross verification/COMMIT/Root: #26 baseline]
                                |
              Untrusted relayer or direct EVM transaction
                                |
       Besu QBFT (4+ independently run validators in target design)
       Solidity: device eligibility, policy/vkey, proof verification,
        session identity, nullifier/duplicate, count and final status
                                |
                    Audit of verified submissions
```

- **同じRIDごとに独立BCを生成しない**。一つのchain内で`sessionId = H(domain, RID commitment, time bucket, policyHash, protocolVersion, membershipEpoch)`を生成する。攻撃者が偽RIDを放送した場合も「同一物理機体」とは断定しない。field/byte32変換は#29のgolden vectorsで規定。
- **BCに置くのは**公開入力、proof、観測コミットメント、資格/判定、公開可能な証拠Root/Hashのみ。位置、生RSSI、個人の秘密鍵、Witness、機密RFログは送信しない。パブリックメタデータの端末追跡リスクは残る。
- 「観測時点からの速報」は署名付き暫定情報でありBCやZKPを待たない。「計算上の検証成功」「物理的整合」「QBFTでの確定」「飛行の安全性」は別フィールド。
- **Onchain direct verificationはBCに暗号学的検証の実行責務を移せる**。ただし全Validatorが同じ提出トランザクションを実行しても、センサーの真正性や登録者の独立性は自動的に生まれない。
- #20/#36で公平比較：A 3台P2Pの署名付き共同証明書＋Merkleログ、B Besuで3独立Groth16 proof直接検証、C offchain verification＋BCへRootのみアンカー。BとCは同一のオンチェーン保証ではない。
- 次の段階で長期時系列・多数proofに対する累積負荷が支配的になったら、Nova系／HyperNova／PCDを含む証明圧縮の追加が合理的か再評価する。

## 4. PoC・実機で確認すべき問い（2026-10-11）

### G0：研究室での受信・真値・仕様の固定 — #13 #14 #17 #29
- [ ] DJIの機体モデル・ファームウェアとRemote ID送信方式の記録（現状：Wi-Fi Beaconとの実験報告、M300/M350型番未確認）
- [ ] Pi A/Pi BとPixel8でWi-Fi Beaconフレーム＋RSSI＋タイムスタンプを**同じ実飛行に対して**取得できるか確認。Android scanning APIの制約、受信チャネル/PHYを明記
- [ ] RTK/飛行ログとPi固定位置・Pixel GPSを同期し、claimed vs ground truthを分けて取得
- [ ] 生のGPS/RSSIを保存したローカルfixtureから`CONSISTENT/SUSPICIOUS/UNDETERMINED`を作る。観測精度とZKPの演算定義を#17に一致させる
- [ ] #29で回路のpublic/private ABI/session/policy/epoch/commitment/nullifierを固定

### G1：証明の独立性とonchain検証 — #30 #31 #34
- [ ] 各端末が秘密Witnessだけをローカル入力にしてGroth16 proofを生成できる（PoCはreplayでも可、実機成功と区別）
- [ ] ベースライン: signed proof（Pi/Pixel）を各自オフチェーン検証。onchain: same vkeyのSolidityで正しいproof採用／改竄proof拒否
- [ ] Besu 4-Validator機能試験でGas・Tx確定遅延を記録（同一PC4コンテナは**独立管理主体のBFT実証ではない**）

### G2：複数ノード・速報・失敗ケース — #32–#36
- [ ] 3観測者のsession内で一意性・採用集合・版整合・未受信/無効proof/判定不能を分ける
- [ ] ZKP・chain停止時も署名付き暫定警報はローカルで機能
- [ ] RFC/ISO/JIS等を標準化対象とする前に、偽入力でも数学的にvalid proofが成立し得る限界を攻撃・誤差試験で示す
- [ ] 同条件でBCなし・オンチェーン直接検証・Rootアンカーの比較結果と採用条件を記録

### 研究上の最終主張（仮）
「独立したRemote ID観測者が各自の位置とRSSIを開示せず、指定の判定規則に従った計算を証明し、オンチェーンで個別証明・資格・重複・履歴を検証する方式について、信頼保証/判定精度/端末負荷/確定遅延を定量的に評価する。」

**主張しない**：「BCによってRemote IDの位置が物理的に正しいと保証できた」「3台だけでByzantine耐故障合意が成立」「Nova/HyperNovaが一般に利用不能」「Wi-Fi Beacon受信をPiとPixel8で既に3台同時実証済み」。

## 5. 歴史的研究資料・今後の管理
- 従来の`week20/04`には「gnark再帰を主軸」の**当時の研究判断**が残る。削除・上書きせず本ADRを現時点のアーキテクチャ判断として引用する。
- `week20/08`、`week20/12`、`week20/13`、`week21/01`は**当時の測定/分析結果**として維持。
- 新しいIssueは乱立させず、#28進捗ダッシュボードにPhaseを記載し、#13/#14 Wi-Fi RX、#29 ABI、#31 Groth16互換、#30/#34 BesuとContract、#36 実験を子タスクで管理。
- GitHub **Wikiのページ自体はGitHub接続から直接読み書きできない場合がある**。本ドキュメントはGitHubリポジトリに配置する正式な研究判断記録とし、Wikiに移す場合はページ実体へのアクセス手段を別途確認する。
