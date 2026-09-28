// UniFFIラッパー(ChainState)が examples/uav_chain_step.rs と同じ結果を出すことを確認する。
use nova_mobile::{ChainState, ObservationInput};

fn obs_consistent() -> ObservationInput {
    ObservationInput {
        drone_lat: 1_256_891_390,
        drone_lon: 3_196_917_000,
        drone_alt: 1_200,
        target_lat: 1_256_891_590,
        target_lon: 3_196_917_180,
        target_alt: 1_000,
        measured_range_cm: 341,
    }
}

fn obs_spoofed() -> ObservationInput {
    ObservationInput {
        drone_lat: 1_256_891_390,
        drone_lon: 3_196_917_000,
        drone_alt: 1_200,
        target_lat: 1_256_891_590,
        target_lon: 3_196_917_180,
        target_alt: 1_000,
        measured_range_cm: 5_000,
    }
}

#[test]
fn three_steps_match_week20_08() {
    let state = ChainState::new(424242, 100001).expect("init failed");

    state.prove_step(obs_consistent()).expect("step1 failed");
    println!("z_1 = {:?}", state.state());

    state.prove_step(obs_consistent()).expect("step2 failed");
    println!("z_2 = {:?}", state.state());

    state.prove_step(obs_spoofed()).expect("step3 failed");
    let z3 = state.state();
    println!("z_3 = {:?}", z3);

    // z = (drone_id, time_bucket, consistent_count, suspicious_count, step_count)
    assert_eq!(z3[0], "424242");
    assert_eq!(z3[1], "100001");
    assert_eq!(z3[2], "2", "consistent_count should be 2 (week20/08と同じ)");
    assert_eq!(z3[3], "1", "suspicious_count should be 1 (week20/08と同じ)");
    assert_eq!(z3[4], "3");

    let ok = state.verify().expect("verify call failed");
    assert!(ok, "IVC proof should verify successfully");
}
