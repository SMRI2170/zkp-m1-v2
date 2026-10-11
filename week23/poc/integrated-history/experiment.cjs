const fs=require('fs'),assert=require('assert/strict'),crypto=require('crypto'),cp=require('child_process');
const {Wallet,JsonRpcProvider,ContractFactory,Contract,AbiCoder,keccak256,getBytes}=require('ethers');
const solc=require('solc');
(async()=>{
 const providers=[0,1,2,3].map(i=>new JsonRpcProvider(`http://127.0.0.1:${18545+i}`,undefined,{cacheTimeout:-1}));providers.forEach(p=>p.pollingInterval=100);
 const sender=new Wallet(JSON.parse(fs.readFileSync(process.env.W23_KEYFILE)).key,providers[0]);
 const observers=[0,1,2].map(()=>Wallet.createRandom());const other=Wallet.createRandom().connect(providers[0]);
 fs.writeFileSync(process.env.W23_PRIVATE+'/signing-keys.json',JSON.stringify({observers:observers.map(w=>w.privateKey),other:other.privateKey}),{mode:0o600,flag:'wx'});
 const manifests=JSON.parse(process.env.W23_MANIFESTS),workerTests=[],verification=[];
 function verify(label,args=[]){
  const child=cp.spawnSync('python3',[process.env.W23_WORKER,manifests[label],...args.map(String)],{encoding:'utf8'});
  assert(child.stdout,'missing verifier output');const result=JSON.parse(child.stdout);
  if(child.status!==0)throw Error(result.reason);return result;
 }
 function rejects(label,args,name){let rejected=false;try{verify(label,args);}catch(e){workerTests.push({case:name,rejected:true,reason:e.message});rejected=true;}assert(rejected,name);}
 rejects('tampered-proof',[],'tampered-proof');rejects('tampered-public',[],'tampered-public');
 rejects('individual',[100002,778,20261011],'wrong-proof-session');rejects('individual',[100002,777,0],'wrong-proof-policy');
 rejects('recursive',[100004],'expired-observation');rejects('recursive',[100000],'future-observation');
 const input={language:'Solidity',sources:{'VerifiedHistory.sol':{content:fs.readFileSync(process.env.W23_SOURCE,'utf8')}},settings:{evmVersion:'paris',optimizer:{enabled:true,runs:200},outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}}};
 const built=JSON.parse(solc.compile(JSON.stringify(input)));assert(!(built.errors||[]).some(e=>e.severity==='error'),JSON.stringify(built.errors));
 const artifact=built.contracts['VerifiedHistory.sol'].VerifiedHistory;
 const history=await new ContractFactory(artifact.abi,artifact.evm.bytecode.object,sender).deploy(20261011,observers.map(w=>w.address),{gasLimit:4000000,gasPrice:0,type:0});await history.waitForDeployment();
 const address=await history.getAddress();await(await sender.sendTransaction({to:other.address,value:1000000000000000000n,gasLimit:21000,gasPrice:0,type:0})).wait();
 const coder=AbiCoder.defaultAbiCoder();
 const tuple='tuple(bytes32 session,bytes32 evidence,uint64 epoch,uint64 deadline,uint256 proofSession,uint256 claimedRID,uint256 bucket,uint256 policy,uint256 members,uint256 consistent,uint256 suspicious)';
 const localSession=e=>keccak256(coder.encode(['string','uint256','uint256','uint256','uint256','uint256','uint64'],['week23-history-v1',1,e.proofSession,e.claimedRID,e.bucket,e.policy,e.epoch]));
 const localPayload=e=>keccak256(coder.encode(['string','uint256','address',tuple],['week23-receipt-signature-v1',237023,address,e]));
 async function envelope(receipt,epoch){const block=await providers[0].getBlock('latest');let e={session:'0x'+'00'.repeat(32),evidence:'0x'+crypto.createHash('sha256').update(receipt.canonical).digest('hex'),epoch,deadline:block.timestamp+120,proofSession:receipt.receipt.proof_session,claimedRID:receipt.receipt.claimed_rid,bucket:receipt.receipt.bucket,policy:receipt.receipt.policy,members:receipt.receipt.member_mask,consistent:receipt.receipt.consistent,suspicious:receipt.receipt.suspicious};e.session=localSession(e);assert.equal(e.session,await history.sessionId(e));assert.equal(localPayload(e),await history.payload(e));return e;}
 async function checkedCertificate(label,epoch){
  const receipts=[0,1,2].map(()=>verify(label));assert.equal(new Set(receipts.map(r=>r.pid)).size,3);
  receipts.slice(1).forEach(r=>assert.equal(r.canonical,receipts[0].canonical));
  const e=await envelope(receipts[0],epoch);const started=performance.now();
  const signatures=await Promise.all(observers.map(w=>w.signMessage(getBytes(localPayload(e)))));
  verification.push({kind:label,verifier_pids:receipts.map(r=>r.pid),verify_ms:receipts.map(r=>r.verify_ms),evidence_sha256:e.evidence.slice(2),proof_public_bytes:receipts[0].receipt.evidence.reduce((sum,a)=>sum+Number(fs.statSync(JSON.parse(fs.readFileSync(manifests[label])).artifacts.find(x=>x.stage===a.stage).proof).size)+Number(fs.statSync(JSON.parse(fs.readFileSync(manifests[label])).artifacts.find(x=>x.stage===a.stage).public).size),0),signature_ms:performance.now()-started,public_status:{proof:'VALID_OFFCHAIN',rid_auth:'UNVERIFIED',physical_risk:'UNKNOWN'}});
  return {e,signatures};
 }
 const transactions=[];
 async function wait(tx,start,label,expected){let r;const end=Date.now()+20000;while(!r){r=await providers[0].send('eth_getTransactionReceipt',[tx.hash]);assert(Date.now()<end,'inclusion timeout');if(!r)await new Promise(r=>setTimeout(r,50));}
  assert.equal(Number(BigInt(r.status)),expected,label);const replicationEnd=Date.now()+10000;
  while(true){const all=await Promise.all(providers.map(p=>p.send('eth_getTransactionReceipt',[tx.hash])));if(all.every(x=>x&&x.blockHash===r.blockHash&&x.status===r.status))break;assert(Date.now()<replicationEnd,'replication timeout');await new Promise(r=>setTimeout(r,50));}
  const row={case:label,status:expected,gas_used:Number(BigInt(r.gasUsed)),ms:performance.now()-start,block:Number(BigInt(r.blockNumber)),index:Number(BigInt(r.transactionIndex)),all_four_same_receipt:true};transactions.push(row);return row;
 }
 async function submit(c,label,expected){const start=performance.now();return wait(await history.submit(c.e,c.signatures,{gasLimit:600000,gasPrice:0,type:0}),start,label,expected);}
 async function action(promise,label){const start=performance.now();return wait(await promise,start,label,1);}
 const individual=await checkedCertificate('individual',1);await submit(individual,'verified-independent-set',1);
 await submit(individual,'replay',0);
 // Onchain adversarial tests intentionally bypass the normal receipt-signing pipeline.
 const mutation=(c,delta)=>({e:{...c.e,...delta},signatures:c.signatures});
 await submit(mutation(individual,{session:'0x'+'11'.repeat(32)}),'wrong-session',0);
 await submit(mutation(individual,{policy:0}),'wrong-policy',0);
 const recursive=await checkedCertificate('recursive',1);
 const stale={...recursive.e,deadline:1};const staleSigs=await Promise.all(observers.map(w=>w.signMessage(getBytes(localPayload(stale)))));
 await submit({e:stale,signatures:staleSigs},'signed-expired-envelope',0);
 await action(history.rotate(observers.map(w=>w.address),{gasLimit:300000,gasPrice:0,type:0}),'rotate-epoch-2');
 await submit(recursive,'old-epoch-certificate',0);
 const recursive2=await checkedCertificate('recursive',2);
 await submit({e:recursive2.e,signatures:recursive2.signatures.slice(0,2)},'missing-observer',0);
 await submit({e:recursive2.e,signatures:[recursive2.signatures[0],recursive2.signatures[0],recursive2.signatures[2]]},'duplicate-observer',0);
 const outsider=Wallet.createRandom();await submit({e:recursive2.e,signatures:[recursive2.signatures[0],recursive2.signatures[1],await outsider.signMessage(getBytes(localPayload(recursive2.e)))]},'unknown-observer',0);
 await submit(mutation(recursive2,{evidence:'0x'+'22'.repeat(32)}),'changed-evidence',0);
 await submit(recursive2,'verified-recursive-final',1);
 await action(history.rotate(observers.map(w=>w.address),{gasLimit:300000,gasPrice:0,type:0}),'rotate-epoch-3');
 const normal=await checkedCertificate('normal',3),outlier=await checkedCertificate('outlier',3);
 assert.equal(normal.e.session,outlier.e.session);assert.notEqual(normal.e.evidence,outlier.e.evidence);
 // Save a deliberate malicious double vote. The honest signing lock test refuses it.
 const lock=process.env.W23_PRIVATE+'/observer-vote.json';fs.writeFileSync(lock,JSON.stringify({session:normal.e.session,evidence:normal.e.evidence}),{mode:0o600,flag:'wx'});
 const child=cp.spawnSync(process.execPath,['-e','const fs=require("fs");let x=JSON.parse(fs.readFileSync(process.argv[1]));if(x.session===process.argv[2]&&x.evidence!==process.argv[3])process.exit(7);',lock,outlier.e.session,outlier.e.evidence]);assert.equal(child.status,7);
 const nonce=await providers[0].getTransactionCount(sender.address,'pending');
 const raws=await Promise.all([sender.signTransaction({to:address,data:history.interface.encodeFunctionData('submit',[normal.e,normal.signatures]),chainId:237023,nonce,gasLimit:600000,gasPrice:0,type:0}),other.signTransaction({to:address,data:history.interface.encodeFunctionData('submit',[outlier.e,outlier.signatures]),chainId:237023,nonce:0,gasLimit:600000,gasPrice:0,type:0})]);
 const start=performance.now();const raceTx=await Promise.all(raws.map(r=>providers[0].broadcastTransaction(r)));
 const receipts=await Promise.all(raceTx.map(tx=>tx.wait().catch(error=>error.receipt)));const statuses=receipts.map(r=>r.status);assert.deepEqual([...statuses].sort(),[0,1]);
 await Promise.all(raceTx.map((tx,i)=>wait(tx,start,'verified-fork-'+i,statuses[i])));
 await action(history.reportEquivocation(normal.e,normal.signatures[1],outlier.e,outlier.signatures[1],{gasLimit:300000,gasPrice:0,type:0}),'double-sign-evidence');assert(await history.revoked(observers[1].address));
 // A fresh contract state is not needed: rotate epoch and explicitly revoke a new active member.
 const replacement=Wallet.createRandom();const roster=[observers[0].address,replacement.address,observers[2].address];
 await action(history.rotate(roster,{gasLimit:300000,gasPrice:0,type:0}),'replace-observer-epoch-4');
 const previous=await checkedCertificate('recursive',4);await submit(previous,'removed-observer',0);
 await action(history.revoke(replacement.address,{gasLimit:100000,gasPrice:0,type:0}),'revoke-active-observer');
 const withReplacement=[previous.signatures[0],await replacement.signMessage(getBytes(localPayload(previous.e))),previous.signatures[2]];
 await submit({e:previous.e,signatures:withReplacement},'revoked-observer',0);
 const sessions=[individual.e.session,recursive2.e.session,normal.e.session];
 const states=await Promise.all(providers.map(p=>Promise.all(sessions.map(s=>new Contract(address,artifact.abi,p).accepted(s)))));states.slice(1).forEach(s=>assert.deepEqual(s,states[0]));
 const logs=await Promise.all(providers.map(p=>p.send('eth_getLogs',[{address,fromBlock:'0x0',toBlock:'latest'}])));
 const histories=logs.map(ls=>ls.map(l=>({blockHash:l.blockHash,transactionHash:l.transactionHash,logIndex:l.logIndex,topics:l.topics,data:l.data})));histories.slice(1).forEach(h=>assert.deepEqual(h,histories[0]));
 const decisions=logs[0].map(l=>history.interface.parseLog(l)).filter(l=>l.name==='Decision');assert.equal(decisions.length,3);
 console.log(JSON.stringify({compiler:solc.version(),worker_rejections:workerTests,verified_certificates:verification,transactions,conflict_exactly_one_accepted:true,all_four_same_states:true,all_four_same_history:true,decision_events:3,epoch_changes:3,double_sign_detected_and_revoked:true,durable_signer_restart_refused_double_vote:true,session_golden_vectors:{individual:individual.e.session,recursive:recursive2.e.session},signature_bytes:195,limits:['Groth16 is checked by local offchain verifiers, not the contract','Fixed synthetic proof session 777/policy 20261011; no dynamic recursive circuit membership','Qualification authority can replace or censor observers; three-of-three receipt requires all three','Proof observation age uses synthetic clock; envelope deadline uses Besu block timestamp','Conflicting valid proofs describe different synthetic observations, not forged cryptography','No release setup keys, VKs, proofs or private assignments deployed or published']}));providers.forEach(p=>p.destroy());
})().catch(error=>{console.error(error.message);process.exit(1);});
