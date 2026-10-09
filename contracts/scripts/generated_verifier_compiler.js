const solc = require("solc");

function compileVerifier(source) {
  return compileVersionedVerifier(source, 1, 9);
}

function compileVerifierV2(source) {
  return compileVersionedVerifier(source, 2, 10);
}

function compileVersionedVerifier(source, version, publicInputCount) {
  const sourceName = `FinalAttestationGroth16VerifierV${version}.sol`;
  const input = {
    language: "Solidity",
    sources: { [sourceName]: { content: source } },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((entry) => entry.severity === "error");
  if (errors.length > 0) {
    throw new Error(`generated verifier Solidity compile failed:\n${errors.map((entry) => entry.formattedMessage).join("\n")}`);
  }
  const candidates = Object.values(output.contracts?.[sourceName] || {});
  const verifier = candidates.find((contract) =>
    contract.abi.some((entry) => entry.type === "function" && entry.name === "verifyProof"),
  );
  if (!verifier) throw new Error("generated Solidity source has no verifyProof function");
  const verifyProof = verifier.abi.find((entry) => entry.type === "function" && entry.name === "verifyProof");
  if (
    verifyProof.inputs.length !== 2 ||
    verifyProof.inputs[0].type !== "bytes" ||
    verifyProof.inputs[1].type !== `uint256[${publicInputCount}]`
  ) {
    throw new Error(`generated V${version} verifier ABI is not verifyProof(bytes,uint256[${publicInputCount}]): ${JSON.stringify(verifyProof.inputs)}`);
  }
  if (verifier.evm.bytecode.object.length === 0) throw new Error("generated verifier has empty deployment bytecode");
  return verifier;
}

module.exports = { compileVerifier, compileVerifierV2 };
