const fs = require('fs');
const assert = require('assert/strict');
const {Wallet, JsonRpcProvider, ContractFactory, Contract, AbiCoder, keccak256, toUtf8Bytes, getBytes, verifyMessage} = require('ethers');
const solc = require('solc');
(async () => {
  const providers = [0,1,2,3].map(i => new JsonRpcProvider(`http://127.0.0.1:${18545+i}`, undefined, {cacheTimeout:-1}));
  providers.forEach(p => p.pollingInterval=100);
  const sender = new Wallet(JSON.parse(fs.readFileSync(process.env.WEEK23_KEYFILE)).key, providers[0]);
  const other = Wallet.createRandom().connect(providers[0]);
  const observers = [0,1,2].map(() => Wallet.createRandom());
  fs.writeFileSync(process.env.WEEK23_PRIVATE+'/experiment-keys.json', JSON.stringify({other:other.privateKey,observers:observers.map(w=>w.privateKey)}), {mode:0o600,flag:'wx'});
  const input = {language:'Solidity',sources:{'ConflictHistory.sol':{content:fs.readFileSync(process.env.WEEK23_SOURCE,'utf8')}},settings:{evmVersion:'paris',optimizer:{enabled:true,runs:200},outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}}};
  const compiled = JSON.parse(solc.compile(JSON.stringify(input)));
  assert(!(compiled.errors||[]).some(e=>e.severity==='error'), JSON.stringify(compiled.errors));
  const artifact=compiled.contracts['ConflictHistory.sol'].ConflictHistory;
  const factory=new ContractFactory(artifact.abi, artifact.evm.bytecode.object, sender);
  const contract=await factory.deploy(observers.map(w=>w.address),{gasLimit:3000000,gasPrice:0,type:0});
  await contract.waitForDeployment();
  const address=await contract.getAddress();
  await (await sender.sendTransaction({to:other.address,value:1000000000000000000n,gasLimit:21000,gasPrice:0,type:0})).wait();
  const coder=AbiCoder.defaultAbiCoder();
  const hash=s=>keccak256(toUtf8Bytes(s));
  const payload=(slot,candidate)=>keccak256(coder.encode(['uint256','address','bytes32','bytes32'],[237023,address,slot,candidate]));
  const cert=async(slot,candidate,indices)=>Promise.all(indices.map(i=>observers[i].signMessage(getBytes(payload(slot,candidate)))));
  const verify=(slot,candidate,sigs,threshold)=>{
    const recovered=sigs.map(sig=>verifyMessage(getBytes(payload(slot,candidate)),sig));
    return new Set(recovered).size===recovered.length && recovered.every(a=>observers.some(w=>w.address===a)) && recovered.length>=threshold;
  };
  const x=hash('synthetic-candidate-X'),y=hash('synthetic-candidate-Y');
  const slot=hash('synthetic-session-42/round-1/parent-0/policy-1');
  const sx=await cert(slot,x,[0,1]),sy=await cert(slot,y,[1,2]);
  assert(verify(slot,x,sx,2) && verify(slot,y,sy,2));
  assert(!verify(slot,x,[sx[0],sx[0]],2));
  assert(!verify(slot,y,sx,2));
  // A persistent exclusive vote file is a signer lock, NOT a replicated consensus log.
  const locks=process.env.WEEK23_PRIVATE+'/signer-locks';fs.mkdirSync(locks,{mode:0o700});
  const lockSign=async(i,slot,candidate)=>{
    const file=locks+'/'+i+'-'+slot+'.json';
    try {const fd=fs.openSync(file,'wx',0o600);try{fs.writeFileSync(fd,JSON.stringify({slot,candidate}));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}}
    catch(e){if(e.code!=='EEXIST')throw e;assert.equal(JSON.parse(fs.readFileSync(file)).candidate,candidate,'persistent double-vote refusal');}
    return observers[i].signMessage(getBytes(payload(slot,candidate)));
  };
  const lockedSlot=hash('unanimous-slot');
  const locked=await Promise.all([0,1,2].map(i=>lockSign(i,lockedSlot,x)));
  assert(verify(lockedSlot,x,locked,3));
  let refused=false;try{await lockSign(1,lockedSlot,y);}catch(e){refused=true;}assert(refused);
  // Fresh child process reads the persisted lock, modeling a signer restart.
  const restart=require('child_process').execFileSync(process.execPath,['-e','const fs=require("fs");const v=JSON.parse(fs.readFileSync(process.argv[1]));if(v.candidate!==process.argv[2])process.exit(7);',locks+'/1-'+lockedSlot+'.json',x],{encoding:'utf8'});
  assert.equal(restart,'');
  assert(!verify(lockedSlot,x,locked.slice(0,2),3));
  const history=[];
  async function replicated(receipt){
    const end=Date.now()+10000;
    while(true){const rs=await Promise.all(providers.map(p=>p.send('eth_getTransactionReceipt',[receipt.hash])));
      if(rs.every(r=>r && r.blockHash===receipt.blockHash && BigInt(r.status)===BigInt(receipt.status)))return;
      assert(Date.now()<end,'receipt replication timeout');await new Promise(r=>setTimeout(r,50));}
  }
  async function receipt(tx,start,label){
    let r;const end=Date.now()+20000;
    while(!r){r=await providers[0].send('eth_getTransactionReceipt',[tx.hash]);assert(Date.now()<end,'inclusion timeout');if(!r)await new Promise(r=>setTimeout(r,50));}
    const normalized={hash:tx.hash,blockHash:r.blockHash,status:Number(BigInt(r.status))};await replicated(normalized);
    const record={label,status:normalized.status,submit_to_receipt_ms:performance.now()-start,gas_used:Number(BigInt(r.gasUsed)),block_number:Number(BigInt(r.blockNumber)),transaction_index:Number(BigInt(r.transactionIndex)),all_four_same_receipt:true};history.push(record);return record;
  }
  const dataX=contract.interface.encodeFunctionData('submit',[slot,x,sx]);
  const dataY=contract.interface.encodeFunctionData('submit',[slot,y,sy]);
  const nonce=await providers[0].getTransactionCount(sender.address,'pending');
  const raws=await Promise.all([sender.signTransaction({to:address,data:dataX,chainId:237023,nonce,gasLimit:500000,gasPrice:0,type:0}),other.signTransaction({to:address,data:dataY,chainId:237023,nonce:0,gasLimit:500000,gasPrice:0,type:0})]);
  const raceStart=performance.now();
  const txs=await Promise.all(raws.map(raw=>providers[0].broadcastTransaction(raw)));
  const race=await Promise.all(txs.map((tx,i)=>receipt(tx,raceStart,'conflict-'+['X','Y'][i])));
  assert.deepEqual(race.map(r=>r.status).sort(),[0,1]);
  const winner=await contract.accepted(slot);assert.equal(winner,race[0].status===1?x:y);
  async function submit(slot,candidate,sigs,label,expected){
    const start=performance.now();const tx=await contract.submit(slot,candidate,sigs,{gasLimit:500000,gasPrice:0,type:0});
    const r=await receipt(tx,start,label);assert.equal(r.status,expected);return r;
  }
  await submit(slot,x,sx,'replay',0);
  const badSlot=hash('negative-slot');const badCert=await cert(badSlot,x,[0,1]);
  await submit(badSlot,x,[badCert[0]],'missing-signer',0);
  await submit(badSlot,x,[badCert[0],badCert[0]],'duplicate-signer',0);
  const outsider=Wallet.createRandom();
  await submit(badSlot,x,[badCert[0],await outsider.signMessage(getBytes(payload(badSlot,x)))],'unknown-signer',0);
  await submit(badSlot,y,badCert,'candidate-tamper',0);
  await submit(hash('different-slot'),x,badCert,'slot-tamper',0);
  const samples=[],certificateMs=[];
  for(let i=0;i<11;i++){
    const s=hash('latency-slot-'+i);const t=performance.now();const signatures=await cert(s,x,[0,1]);const signingMs=performance.now()-t;
    const r=await submit(s,x,signatures,i===0?'warmup':'sample-'+i,1);
    if(i>0){samples.push(r.submit_to_receipt_ms);certificateMs.push(signingMs);}
  }
  const states=await Promise.all(providers.map(p=>new Contract(address,artifact.abi,p).accepted(slot)));
  assert(states.every(v=>v===winner));
  const logs=await Promise.all(providers.map(p=>p.send('eth_getLogs',[{address,fromBlock:'0x0',toBlock:'latest'}])));
  const normalizedLogs=logs.map(ls=>ls.map(l=>({blockHash:l.blockHash,transactionHash:l.transactionHash,logIndex:l.logIndex,topics:l.topics,data:l.data})));
  normalizedLogs.slice(1).forEach(ls=>assert.deepEqual(ls,normalizedLogs[0]));
  assert.equal(logs[0].length,12);
  const pct=(a,f)=>{a=[...a].sort((x,y)=>x-y);const p=(a.length-1)*f,l=Math.floor(p);return a[l]+(a[Math.ceil(p)]-a[l])*(p-l);};
  console.log(JSON.stringify({compiler:solc.version(),evm_version:'paris',workload:'same 2-of-3 observer certificates, synthetic digest candidates; first valid transaction wins',
    no_bc:{two_of_three_conflicting_certificates_both_verify:true,byzantine_double_signer:1,independent_verifier_X:x,independent_verifier_Y:y,unique_history:false,three_of_three_with_persistent_locks:{valid:true,conflict_refused:true,restart_lock_read:true,one_missing_signer_no_certificate:true},certificate_p50_ms:pct(certificateMs,.5),certificate_p95_ms:pct(certificateMs,.95),signature_bytes_per_certificate:130},
    besu:{conflict_exactly_one_accepted:true,winner,all_four_same_state:true,all_four_same_event_history:true,event_count:logs[0].length,history,latency_samples:10,warmup:1,submit_to_receipt_p50_ms:pct(samples,.5),submit_to_receipt_p95_ms:pct(samples,.95)},
    limitations:['2-of-3 observers tolerates no Byzantine equivocation for unique certificates; differs from 3-of-4 QBFT validator quorum','3-of-3 lock safety depends on honest durable signers; no total order for independent slots','Contract verifies signatures and a first-write slot policy, not observation completeness, ZKP validity, or physical truth','No censorship, independent operators, adversarial network partition or validator fault injection in this experiment','Signing time excludes proof generation, proof verification, network distribution and disk locks; chain latency includes RPC/receipt replication']}));
  providers.forEach(p=>p.destroy());
})().catch(e=>{console.error(e.message);process.exit(1);});
