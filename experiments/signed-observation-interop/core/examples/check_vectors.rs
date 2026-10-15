use serde::Deserialize;
use std::io::{self, BufRead};
use week24_signed_observation_core::{verify, Batch};
#[derive(Deserialize)]
struct Vector {
    case: String,
    batch: Batch,
    expected: bool,
}
fn main() {
    let mut results = Vec::new();
    for line in io::stdin().lock().lines() {
        let line = line.expect("input pipe");
        if !line.starts_with('{') {
            continue;
        }
        let vector: Vector = serde_json::from_str(&line).expect("canonical synthetic vector");
        let got = verify(&vector.batch);
        // Do not log the vector or panic-debug its private assignment.
        assert_eq!(
            got, vector.expected,
            "reference mismatch: {} n={}",
            vector.case, vector.batch.public.count
        );
        results.push(serde_json::json!({"case":vector.case,"observation_count":vector.batch.public.count,"accepted":got,"expected":vector.expected,"scope":"native reference and Go solver/envelope; no ZKP"}));
    }
    assert_eq!(results.len(), 40, "incomplete vector stream");
    println!(
        "{}",
        serde_json::json!({"phase":"interop_summary","cases":results,"all_matched":true,"private_vectors_saved":false,"proof_generated":false})
    );
}
