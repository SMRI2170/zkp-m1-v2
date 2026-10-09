#!/usr/bin/env node

// Freeze Circomlib's BN254 Poseidon parameters (input arity 3, t=4) as a
// protocol artifact for the Go policy-commitment gadget. Run from the repo
// root after npm ci. The source package version is pinned by package-lock.json.
const fs = require("node:fs");
const path = require("node:path");
const circomlibDirectory = path.dirname(require.resolve("circomlibjs"));
const poseidonConstants = JSON.parse(
  fs.readFileSync(path.resolve(circomlibDirectory, "../src/poseidon_constants.json"), "utf8")
);

const WIDTH_INDEX = 2; // t=4 => C[2], M[2]
const generated = {
  source: "circomlibjs poseidon_constants.json; t=4; N_ROUNDS_F=8; N_ROUNDS_P=56",
  roundConstants: poseidonConstants.C[WIDTH_INDEX].map((x) => BigInt(x).toString()),
  mds: poseidonConstants.M[WIDTH_INDEX].map((row) => row.map((x) => BigInt(x).toString())),
};

const destination = path.resolve(
  __dirname,
  "../aggregator/pcd/circomlib_poseidon_t4_constants.json"
);
fs.writeFileSync(destination, `${JSON.stringify(generated, null, 2)}\n`);
console.log(`wrote ${path.relative(process.cwd(), destination)}`);
