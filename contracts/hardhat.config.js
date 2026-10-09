require("@nomicfoundation/hardhat-toolbox");

const hardhatNetwork = {};
if (process.env.PCD3_V2_EVM_INITIAL_DATE) {
  hardhatNetwork.initialDate = process.env.PCD3_V2_EVM_INITIAL_DATE;
}

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: {
    // Synthetic proof tests can pin local chain time to the capture bucket;
    // production and ordinary tests retain Hardhat's default current time.
    hardhat: hardhatNetwork,
    // 許可型EVM（Besu QBFT / Quorum）へのデプロイ先。
    // besu-qbft/ のネットワークを起動し、DEPLOYER_KEY を渡して使う。
    besu: {
      url: process.env.BESU_RPC || "http://127.0.0.1:8545",
      chainId: process.env.BESU_CHAIN_ID ? Number(process.env.BESU_CHAIN_ID) : 1337,
      accounts: process.env.DEPLOYER_KEY ? [process.env.DEPLOYER_KEY] : [],
    },
  },
};
