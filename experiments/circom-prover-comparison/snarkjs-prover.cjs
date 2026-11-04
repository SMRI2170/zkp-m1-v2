#!/usr/bin/env node
// Same four positional arguments as native RapidSnark; no private values in diagnostics.
const fs=require('fs'),path=require('path');
process.umask(0o077);
(async()=>{
 const root=process.env.WEEK24_SNARKJS_ROOT;
 const expected=process.env.WEEK24_SNARKJS_VERSION||'0.7.6';
 if(!['0.7.5','0.7.6'].includes(expected)||!root||JSON.parse(fs.readFileSync(path.join(root,'package.json'))).version!==expected)throw Error('pinned snarkjs required');
 const [zkey,witness,proofFile,publicFile]=process.argv.slice(2);
 if(!zkey||!witness||!proofFile||!publicFile)throw Error('four paths required');
 const snarkjs=require(root);
 const {proof,publicSignals}=await snarkjs.groth16.prove(zkey,witness,undefined,{singleThread:true});
 fs.writeFileSync(proofFile,JSON.stringify(proof,null,1),{mode:0o600});
 fs.writeFileSync(publicFile,JSON.stringify(publicSignals,null,1),{mode:0o600});
})().catch(()=>{console.error('snarkjs prover failed; private diagnostic suppressed');process.exitCode=1;});
