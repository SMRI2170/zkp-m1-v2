#![no_main]
sp1_zkvm::entrypoint!(main);
pub fn main() {
    let a = sp1_zkvm::io::read::<[u64; 6]>();
    assert!(a[..4].iter().all(|x| *x < (1 << 16)));
    assert!(a[4] < (1 << 33) && a[5] < (1 << 17));
    let dx = a[0].abs_diff(a[2]);
    let dy = a[1].abs_diff(a[3]);
    let d2 = dx * dx + dy * dy;
    assert_eq!(d2, a[4]);
    let r = a[5];
    assert!(r * r <= d2 && d2 < (r + 1) * (r + 1));
    assert!(d2 - r * r < (1 << 18));
    assert!((r + 1) * (r + 1) - d2 - 1 < (1 << 18));
    // Coordinates remain private; only the claimed distance and root are public.
    sp1_zkvm::io::commit(&[d2, r]);
}
