use sp1_sdk::{prelude::*, ProverClient};
use std::time::Instant;
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let path = std::env::args().nth(1).expect("synthetic guest ELF path required");
    let bytes = std::fs::read(path)?;
    let elf = Elf::from(bytes);
    // Explicit local CPU backend: no from_env/network/mock fallback.
    println!("{}",serde_json::json!({"phase":"start","backend":"explicit local CPU","os":std::env::consts::OS,"arch":std::env::consts::ARCH}));
    let client = ProverClient::builder().cpu().build().await;
    let pk = client.setup(elf).await?;
    let mut stdin = SP1Stdin::new();
    stdin.write(&[0u64, 0, 3, 4, 25, 5]);
    let t = Instant::now();
    let proof = client.prove(&pk, stdin).core().await?;
    let prove_ms = t.elapsed().as_secs_f64()*1000.;
    let t = Instant::now();
    client.verify(&proof, &pk.verifying_key(), None)?;
    let verify_ms = t.elapsed().as_secs_f64()*1000.;
    let mut public = proof.public_values.clone();
    assert_eq!(public.read::<[u64;2]>(), [25,5]);
    let mut altered = proof.clone();
    let mut changed_public = sp1_sdk::SP1PublicValues::new();
    changed_public.write(&[26u64,5]);
    altered.public_values = changed_public;
    assert!(client.verify(&altered, &pk.verifying_key(), None).is_err());
    println!("{}",serde_json::json!({"phase":"summary","framework":"SP1 6.9.0 local CPU Core","os":std::env::consts::OS,"arch":std::env::consts::ARCH,"all_verified":true,"samples":1,"prove_ms":prove_ms,"verify_ms":verify_ms,"core_serialized_bytes":bincode::serialize(&proof)?.len(),"proofs_saved":false,"changed_public_rejected":true,"scope":"Core proof, not compressed or final ZK wrapper"}));
    Ok(())
}
