use risc0_zkvm::{compute_image_id, ExecutorEnv, LocalProver, Prover, ProverOpts};
use std::time::Instant;
fn main() -> anyhow::Result<()> {
    assert!(std::env::var("RISC0_DEV_MODE").unwrap_or_default() != "1");
    let path = std::env::args().nth(1).expect("synthetic guest ELF path required");
    let user_elf = std::fs::read(path)?;
    // Same default kernel wrapping as risc0-build 3.0.6 GuestListEntry.
    let elf = risc0_binfmt::ProgramBinary::new(&user_elf, risc0_zkos_v1compat::V1COMPAT_ELF).encode();
    let env = ExecutorEnv::builder().write(&[0u64,0,3,4,25,5])?.build()?;
    // Force local CPU proving; no Bonsai/network/default backend selection.
    println!("{}",serde_json::json!({"phase":"start","backend":"explicit LocalProver composite","os":std::env::consts::OS,"arch":std::env::consts::ARCH}));
    let prover = LocalProver::new("week24-local");
    let t = Instant::now();
    let receipt = prover.prove_with_opts(env, &elf, &ProverOpts::composite())?.receipt;
    let prove_ms = t.elapsed().as_secs_f64()*1000.;
    let t = Instant::now();
    receipt.verify(compute_image_id(&elf)?)?;
    let verify_ms = t.elapsed().as_secs_f64()*1000.;
    assert_eq!(receipt.journal.decode::<[u64;2]>()?, [25,5]);
    let mut altered = receipt.clone();
    altered.journal.bytes[0] ^= 1;
    assert!(altered.verify(compute_image_id(&elf)?).is_err());
    assert!(receipt.verify([0u32;8]).is_err());
    println!("{}",serde_json::json!({"phase":"summary","framework":"RISC Zero 3.0.6 local composite","os":std::env::consts::OS,"arch":std::env::consts::ARCH,"all_verified":true,"samples":1,"prove_ms":prove_ms,"verify_ms":verify_ms,"receipt_serialized_bytes":bincode::serialize(&receipt)?.len(),"proofs_saved":false,"changed_public_rejected":true,"wrong_image_rejected":true,"scope":"Composite receipt; no recursion/Groth16 wrapper"}));
    Ok(())
}
