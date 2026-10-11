const fs=require('fs'),assert=require('assert/strict');
const {Wallet,JsonRpcProvider,ContractFactory,AbiCoder,keccak256,getBytes,toUtf8Bytes}=require('ethers');const solc=require('solc');
(async()=>{
 const provider=new JsonRpcProvider('http://127.0.0.1:18545',undefined,{cacheTimeout:-1});provider.pollingInterval=100;
 const sender=new Wallet(JSON.parse(fs.readFileSync(process.env.FAULT_KEYFILE)).key,provider),observers=[0,1,2].map(()=>Wallet.createRandom());
 fs.writeFileSync(process.env.FAULT_PRIVATE+'/observer-keys.json',JSON.stringify(observers.map(w=>w.privateKey)),{mode:0o600,flag:'wx'});
 const input={language:'Solidity',sources:{'ConflictHistory.sol':{content:fs.readFileSync(process.env.FAULT_SOURCE,'utf8')}},settings:{evmVersion:'paris',optimizer:{enabled:true,runs:200},outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}}};
 const built=JSON.parse(solc.compile(JSON.stringify(input)));assert(!(built.errors||[]).some(e=>e.severity==='error'));
 const a=built.contracts['ConflictHistory.sol'].ConflictHistory;const contract=await new ContractFactory(a.abi,a.evm.bytecode.object,sender).deploy(observers.map(w=>w.address),{gasLimit:3000000,gasPrice:0,type:0});await contract.waitForDeployment();
 const address=await contract.getAddress(),coder=AbiCoder.defaultAbiCoder(),baseNonce=await provider.getTransactionCount(sender.address,'pending'),raw=[];
 for(let i=0;i<6;i++){
  const slot=keccak256(toUtf8Bytes('week23-fault-slot-'+(i===4?3:i))),candidate='0x'+(i===4?process.env.FAULT_Y:process.env.FAULT_X);
  const payload=keccak256(coder.encode(['uint256','address','bytes32','bytes32'],[237023,address,slot,candidate]));
  const signatures=await Promise.all(observers.map(w=>w.signMessage(getBytes(payload))));
  raw.push(await sender.signTransaction({to:address,data:contract.interface.encodeFunctionData('submit',[slot,candidate,signatures]),chainId:237023,nonce:baseNonce+i,gasLimit:600000,gasPrice:0,type:0}));
 }
 fs.writeFileSync(process.env.FAULT_PRIVATE+'/signed-transactions.json',JSON.stringify(raw),{mode:0o600,flag:'wx'});
 console.log(JSON.stringify({address,denied_tx_hash:keccak256(raw[5])}));provider.destroy();
})().catch(e=>{console.error(e.message);process.exit(1);});
