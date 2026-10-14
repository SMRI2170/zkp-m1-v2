fn eval_us() -> u64 { use std::sync::OnceLock; static START:OnceLock<std::time::Instant>=OnceLock::new(); START.get_or_init(std::time::Instant::now).elapsed().as_micros() as u64 }
fn eval_number(name:&str,default:usize,max:usize)->usize { let x=std::env::var(name).map(|s|s.parse::<usize>().expect("invalid collection parameter")).unwrap_or(default);assert!(x<=max);x }
fn eval_case()->usize { eval_number("EVAL_CASE",1,6) }
fn eval_warmup()->usize { eval_number("EVAL_WARMUP",1,3) }
fn eval_inputs()->Vec<[u64;6]> { let n=eval_number("EVAL_REPEAT",3,20);assert!(n>0);println!("{}",serde_json::json!({"phase":"collection_protocol","wall_time_ns":eval_wall_ns(),"clock_us":eval_us(),"case_id":eval_case(),"warmup_count":eval_warmup(),"repeat_count":n,"mode":"same-input within-process repetition"}));vec![CASES[eval_case()];n+eval_warmup()] }
fn eval_mark(stage:&str,i:usize) {println!("{}",serde_json::json!({"phase":"phase_marker","stage":stage,"sample_id":i,"wall_time_ns":eval_wall_ns(),"clock_us":eval_us()}));}
fn eval_fingerprint(bytes:&[u8])->[u64;2] { // Non-cryptographic diagnostic only; never a security commitment.
 let mut a=0xcbf29ce484222325u64;let mut b=0x9e3779b97f4a7c15u64;for x in bytes {a=(a^(*x as u64)).wrapping_mul(0x100000001b3);b=b.rotate_left(7)^(*x as u64);}[a,b]
}

fn eval_wall_ns()->u64 { std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).expect("clock before epoch").as_nanos() as u64 }
fn eval_seen(bytes:&[u8])->bool { use std::sync::{Mutex,OnceLock};static SEEN:OnceLock<Mutex<std::collections::HashSet<[u64;2]>>>=OnceLock::new();SEEN.get_or_init(||Mutex::new(std::collections::HashSet::new())).lock().unwrap().insert(eval_fingerprint(bytes)) }
