// week20/09 §5.3の続き: ChainState(uniffiラッパー)経由の3ステップを実機上で直接実行し、
// prove_step/verifyの実時間を計測する。UniFFI/Kotlin/Flutterを経由せず、
// aarch64-linux-android向けにクロスコンパイルした素の実行ファイルとして
// `adb push` → `adb shell` で直接実行する（week20/08のuav_chain_step.rsと同じシナリオ）。
use nova_mobile::{ChainState, ObservationInput};
use std::time::Instant;

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

fn main() {
    println!("[on_device_bench] ChainState::new (includes one-time preprocess)");
    let t0 = Instant::now();
    let state = ChainState::new(424242, 100001).expect("init failed");
    println!("  new(): {:?}", t0.elapsed());

    let steps = [
        ("整合な観測1", obs_consistent()),
        ("整合な観測2", obs_consistent()),
        ("なりすまし観測", obs_spoofed()),
    ];
    for (label, obs) in steps {
        let t0 = Instant::now();
        state.prove_step(obs).expect("prove_step failed");
        println!("  prove_step({}): {:?}  z={:?}", label, t0.elapsed(), state.state());
    }

    let t0 = Instant::now();
    let ok = state.verify().expect("verify call failed");
    println!("  verify(): {:?}  ok={}", t0.elapsed(), ok);

    println!("[on_device_bench] DONE");
}
