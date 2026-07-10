require("@nomicfoundation/hardhat-toolbox");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: {
    // 許可型EVM（Besu QBFT / Quorum）へのデプロイ先。
    // besu-qbft/ のネットワークを起動し、DEPLOYER_KEY を渡して使う。
    besu: {
      url: process.env.BESU_RPC || "http://127.0.0.1:8545",
      chainId: process.env.BESU_CHAIN_ID ? Number(process.env.BESU_CHAIN_ID) : 1337,
      accounts: process.env.DEPLOYER_KEY ? [process.env.DEPLOYER_KEY] : [],
    },
  },
};
