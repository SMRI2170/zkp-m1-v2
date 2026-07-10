# 許可型EVM（Besu QBFT）での UAV 接近証明レジストリ

各端末が **自分の Groth16 証明を1トランザクションとして直接提出（M1直接）** する構成。
検閲・データ可用性・包含性を、**合意プロトコルそのもの**で解く。

## なぜ検閲に強いか
- **BFT合意（QBFT）**: 正直なバリデータ・クォーラム（≧3/4）がある限り、提出Txは必ずブロックに入る
  → 単一主体が有効な証明を間引けない（＝検閲不可）。
- **全ノード複製 = DA内蔵**: 提出された全 proof は全バリデータが保持 → omission が即バレる。
- **メンバーシップ管理**: 検閲したノードは特定・除名・（必要なら）スラッシュ可能。

公開チェーンで DA層＋包含性証明を積む代わりに、信頼を「コンソーシアムの正直クォーラム」に置く。
UAV/RemoteID は当局・運航事業者のコンソーシアムが自然な信頼集合なので適合。

## 前提
- Docker / docker-compose
- Besu operator ツール（genesis と鍵の生成用）

## 手順
```bash
# 1. genesis と 4ノードぶんの鍵を生成
besu operator generate-blockchain-config \
  --config-file=qbftConfigFile.json \
  --to=networkFiles \
  --private-key-file-name=key
# 2. 生成された鍵を node1..node4 に配置（networkFiles/keys/<addr>/key を各 node ディレクトリの key へ）
#    ※ 生成物の配置は運用に合わせて調整（bootnode の enode を BOOTNODE に設定）
# 3. 起動
docker compose up -d
# 4. コントラクトをデプロイ（許可型チェーンへ。既存 verifier/registry を無改変で）
cd ..
DEPLOYER_KEY=<開発鍵> K=3 OPERATOR=<operator_commitment> MIN_FRESHNESS=<v> \
  npx hardhat run scripts/deploy.js --network besu
```

## 動作（M1直接提出）
- 各端末は `AttestationRegistry.submitAttestation(proof, publicSignals[18])` を直接呼ぶ。
- コントラクトが Groth16 検証 ＋ M3検査（drone_auth / operator / freshness）＋ K台集計。
- 集約(gnark)は gas 制約が無いので任意。必要なら `AggregateVerifier` も同様にデプロイ可能。

## 公開監査性（任意のハイブリッド）
`consensusReached` の Merkle ルートを定期的に公開チェーンへアンカーすれば、
コンソーシアム外からの改ざん検知（公開監査）も得られる。

## 注意
- 本ディレクトリはネットワーク構成のテンプレート。genesis はハンドクラフトせず
  `besu operator generate-blockchain-config` で生成すること（extraData のバリデータ符号化のため）。
- `alloc` の開発アカウント・`DEPLOYER_KEY` は実運用では必ず置き換える。
