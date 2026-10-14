use jolt_sdk::PrivateInput;
use std::time::Instant;
include!("../../../cases.rs");
fn main() -> anyhow::Result<()> {
    eval_us();
    println!("{}",serde_json::json!({"phase":"start","framework":"Jolt PrivateInput + zk","os":std::env::consts::OS,"arch":std::env::consts::ARCH,"zk_feature":true}));
    let args:Vec<String>=std::env::args().skip(1).collect();
    let quick=args.iter().any(|x|x=="--quick");
    let t=Instant::now();
    let mut program=if args.first().map(String::as_str)==Some("--elf") {
        let path=std::path::PathBuf::from(args.get(1).expect("public guest ELF path required"));
        let mut p=jolt_sdk::host::Program::new("week24-euclidean-jolt-guest");
        p.set_func("distance");p.set_heap_size(32768);p.elf=Some(path);p
    } else {guest::compile_distance(args.first().expect("ignored guest build directory required"))};
    let shared=guest::preprocess_shared_distance(&mut program)?;
    let prep=guest::preprocess_prover_distance(shared);
    let verifier_prep=guest::verifier_preprocessing_from_prover_distance(&prep);
    let prove=guest::build_prover_distance(program,prep);
    let vk_bytes=jolt_sdk::serialize_verifier_object(&verifier_prep)?.len();
    let verify=guest::build_verifier_distance(verifier_prep);
    println!("{}",serde_json::json!({"phase":"keys","vk_bytes":vk_bytes,"setup_ms":t.elapsed().as_secs_f64()*1000.}));
    let selected=eval_inputs();
    for (i,a) in selected.iter().enumerate() {
        eval_mark("prove_start",i);
        let t=Instant::now();let (output,proof,io)=prove(PrivateInput::new([a[0],a[1],a[2],a[3]]),a[4],a[5]);
        let prove_ms=t.elapsed().as_secs_f64()*1000.;assert!(output && !io.panic);
        eval_mark("verify_start",i);let t=Instant::now();assert!(verify(a[4],a[5],output,io.panic,proof.clone()));
        let vms=t.elapsed().as_secs_f64()*1000.;eval_mark("verify_end",i);
        assert!(!verify(a[4]^1,a[5],output,io.panic,proof.clone()));
        assert!(!verify(a[4],a[5]^1,output,io.panic,proof.clone()));
        let size=bincode::serialize(&proof)?.len();
        let mut fake=proof.clone();fake.trace_length+=1;
        assert!(!verify(a[4],a[5],output,io.panic,fake));
        println!("{}",serde_json::json!({"phase":"sample","case_id":eval_case(),"sample_id":i,"warmup":i<eval_warmup(),"repetition":if i<eval_warmup(){None}else{Some(i-eval_warmup())},"verified":true,"prove_ms":prove_ms,"verify_ms":vms,"public_input_bytes":bincode::serialize(&(a[4],a[5],output,io.panic))?.len(),"proof_randomness_new":eval_seen(&bincode::serialize(&proof)?),"proof_bytes":size,"changed_public_rejected":true,"changed_root_rejected":true,"tampered_proof_rejected":true,"proofs_saved":false}));
    }
    let invalid:&[[u64;6]]=if quick {&BAD[..2]} else {&BAD};
    for a in invalid {
        let (output, proof, io) = prove(PrivateInput::new([a[0],a[1],a[2],a[3]]),a[4],a[5]);
        assert!(io.panic, "invalid distance assignment must panic");
        // A proof of a panic is not accepted as a successful distance computation.
        assert!(!verify(a[4],a[5],output,false,proof));
    }
    println!("{}",serde_json::json!({"phase":"summary","samples":selected.len(),"all_verified":true,"proofs_saved":false,"invalid_cases_rejected":invalid.len(),"quick_mode":quick,"negative_scope":"actual invalid execution proofs reject a false panic=false claim"}));
    Ok(())
}
