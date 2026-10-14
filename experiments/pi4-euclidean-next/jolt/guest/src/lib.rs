#![cfg_attr(feature="guest",no_std)]
#[jolt::provable(heap_size=32768,max_trace_length=65536)]
pub fn distance(coords: jolt::PrivateInput<[u64;4]>, d2:u64, r:u64) -> bool {
    let a=*coords;
    assert!(a.iter().all(|v|*v<(1<<16)));
    assert!(d2<(1<<33) && r<(1<<17));
    let dx=a[0].abs_diff(a[2]);let dy=a[1].abs_diff(a[3]);
    assert_eq!(d2,dx*dx+dy*dy);
    assert!(r*r<=d2 && d2<(r+1)*(r+1));
    assert!(d2-r*r<(1<<18) && (r+1)*(r+1)-d2-1<(1<<18));
    true
}
