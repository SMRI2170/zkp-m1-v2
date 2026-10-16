// Native RapidSnark prover+verifier. Transient witnesses/proofs only in /dev/shm.
const fs=require('fs'),path=require('path'),os=require('os'),crypto=require('crypto');
const {execFileSync,spawnSync}=require('child_process');
const [fixture,prover,verifier]=process.argv.slice(2);
const manifest=JSON.parse(fs.readFileSync(path.join(fixture,'manifest.json')));
if(!manifest.phase1_contributed||!manifest.phase2_contributed||!manifest.zkey_verified)throw Error('uncontributed test setup refused');
for(const [name,h] of Object.entries(manifest.files)) {
 const p=path.join(fixture,name); if((fs.statSync(p).mode&0o777)!==0o600)throw Error('private artifact permissions');
 if(crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')!==h)throw Error('fixture hash mismatch');
}
if((fs.statSync(fixture).mode&0o777)!==0o700)throw Error('fixture directory permissions');
const builder=require(path.join(fixture,'euclidean_js/witness_calculator.js'));
const cases=[[0,0,0,0],[0,0,3,4],[3,4,0,0],[0,0,1,1],[0,0,65535,65535],[65535,0,0,65535],[100,100,101,100]];
function isqrt(d){let lo=0,hi=92682,r=0;while(lo<=hi){let m=Math.floor((lo+hi)/2);if(m*m<=d){r=m;lo=m+1;}else{hi=m-1;}}return r;}
function input(a){let [x1,y1,x2,y2]=a,d2=(x1-x2)**2+(y1-y2)**2,r=isqrt(d2);return {x1,y1,x2,y2,d2,r};}
function emit(v){console.log(JSON.stringify(v));}
function clock(){return process.hrtime.bigint();}
function ms(t){return Number(clock()-t)/1e6;}
function reject(bin,args){const r=spawnSync(bin,args,{timeout:120000});if(r.error||r.signal||r.status!==1)throw Error('negative verifier did not return an ordinary invalid-proof exit');return r;}
function command(bin,args){return execFileSync(bin,args,{encoding:'utf8',stdio:['ignore','pipe','pipe'],timeout:120000});}
(async()=>{
 process.umask(0o077);
 const tmp=fs.mkdtempSync('/dev/shm/week24-euclid-');fs.chmodSync(tmp,0o700);
 try{
  const wc=await builder(fs.readFileSync(path.join(fixture,'euclidean_js/euclidean.wasm')));
  emit({phase:'start',os:process.platform,arch:process.arch,framework:'Circom/RapidSnark',setup_host:'Mac',source_sha256:manifest.source_sha256});
  for(let sample_id=0;sample_id<28;sample_id++){
   const i=sample_id%7;
   const a=input(cases[i]);let t=clock();const w=await wc.calculateWTNSBin(a,true);const wms=ms(t);fs.writeFileSync(path.join(tmp,'w.wtns'),w,{mode:0o600});
   t=clock();command(prover,[path.join(fixture,'local.zkey'),path.join(tmp,'w.wtns'),path.join(tmp,'proof.json'),path.join(tmp,'public.json')]);const pms=ms(t);
   const pub=JSON.parse(fs.readFileSync(path.join(tmp,'public.json')));if(JSON.stringify(pub)!==JSON.stringify([String(a.d2),String(a.r)]))throw Error('public output mismatch');
   t=clock();command(verifier,[path.join(fixture,'vk.json'),path.join(tmp,'public.json'),path.join(tmp,'proof.json')]);const vms=ms(t);
   fs.writeFileSync(path.join(tmp,'badpublic.json'),JSON.stringify([String(a.d2+1),String(a.r)]),{mode:0o600});
   reject(verifier,[path.join(fixture,'vk.json'),path.join(tmp,'badpublic.json'),path.join(tmp,'proof.json')]);
   let proof=JSON.parse(fs.readFileSync(path.join(tmp,'proof.json')));proof.pi_a[0]='0';proof.pi_a[1]='0';fs.writeFileSync(path.join(tmp,'badproof.json'),JSON.stringify(proof),{mode:0o600});
   reject(verifier,[path.join(fixture,'vk.json'),path.join(tmp,'public.json'),path.join(tmp,'badproof.json')]);
   emit({phase:'sample',case_id:i,sample_id,warmup:sample_id<7,repetition:sample_id<7?null:Math.floor((sample_id-7)/7),witness_ms:wms,prove_ms:pms,verify_ms:vms,verified:true,changed_public_rejected:true,tampered_proof_rejected:true,proof_json_bytes:fs.statSync(path.join(tmp,'proof.json')).size,proof_bytes:fs.statSync(path.join(tmp,'proof.json')).size,public_bytes:fs.statSync(path.join(tmp,'public.json')).size,proof_encoding:'JSON'});
  }
  // Bypass witness generation to test native proof verification against an
  // inconsistent assignment, not merely the generator's sanity assertions.
  const forged=Buffer.from(await wc.calculateWTNSBin(input(cases[0]),true));
  let offset=12,dataOffset=null,fieldBytes=null;
  for(let j=0;j<forged.readUInt32LE(8);j++){
   const kind=forged.readUInt32LE(offset),length=Number(forged.readBigUInt64LE(offset+4));
   if(kind===1)fieldBytes=forged.readUInt32LE(offset+12);
   if(kind===2)dataOffset=offset+12;
   offset+=12+length;
  }
  if(fieldBytes!==32||dataOffset===null)throw Error('unexpected WTNS layout');
  forged[dataOffset+fieldBytes]=1; // wire 1 = public d2, inconsistent with zero coordinates.
  fs.writeFileSync(path.join(tmp,'forged.wtns'),forged,{mode:0o600});
  const attempt=spawnSync(prover,[path.join(fixture,'local.zkey'),path.join(tmp,'forged.wtns'),path.join(tmp,'forged-proof.json'),path.join(tmp,'forged-public.json')],{timeout:120000});
  if(attempt.error||attempt.signal||![0,1].includes(attempt.status))throw Error('forged-witness prover execution failure');
  let forgedRejected=attempt.status===1;
  if(!forgedRejected){reject(verifier,[path.join(fixture,'vk.json'),path.join(tmp,'forged-public.json'),path.join(tmp,'forged-proof.json')]);forgedRejected=true;}
  if(!forgedRejected)throw Error('forged assignment produced verified proof');
  emit({phase:'native-invalid-witness',rejected:true,prover_rejected:attempt.status!==0});
  const bad=[{...input([0,0,3,4]),r:4},{...input([0,0,3,4]),r:6},{...input([0,0,3,4]),d2:26},input([65536,0,0,0]),input([-1,0,0,0]),{...input([0,0,0,0]),r:131072}];
  for(const a of bad){let rejected=false;try{await wc.calculateWTNSBin(a,true);}catch(e){rejected=true;}if(!rejected)throw Error('invalid witness accepted');}
  emit({phase:'summary',samples:21,warmups:7,protocol:'distance-u16-balanced-v1',invalid_cases_rejected:6,all_verified:true,negative_verifier_exit_code:1,transient_files:'owner-only tmpfs removed on exit',proofs_persisted:false});
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
