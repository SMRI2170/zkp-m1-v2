// Synthetic inputs. Field arithmetic is safe after explicit u16/u33/u17 bounds.
fn main(x1: u16, y1: u16, x2: u16, y2: u16, d2: pub u64, r: pub u32) {
    assert(d2 < 8589934592);
    assert(r < 131072);
    let d2 = d2 as Field;
    let r = r as Field;
    let dx = x1 as Field - x2 as Field;
    let dy = y1 as Field - y2 as Field;
    assert(d2 == dx*dx + dy*dy);
    let low = d2-r*r;
    let high = (r+1)*(r+1)-d2-1;
    let low_int = low as u32;
    assert(low == low_int as Field);
    assert(low_int < 262144);
    let high_int = high as u32;
    assert(high == high_int as Field);
    assert(high_int < 262144);
}
#[test]
fn perfect_square() { main(0,0,3,4,25,5); }
#[test]
fn nonsquare() { main(0,0,1,1,2,1); }
#[test]
fn upper_boundary() { main(0,0,65535,65535,8589672450,92680); }
#[test(should_fail)]
fn wrong_root() { main(0,0,3,4,25,4); }
#[test(should_fail)]
fn wrong_squared_distance() { main(0,0,3,4,26,5); }

#[test]
fn zero() { main(0,0,0,0,0,0); }
#[test]
fn reversed() { main(3,4,0,0,25,5); }
#[test]
fn maximum_reversed() { main(65535,0,0,65535,8589672450,92680); }
#[test]
fn adjacent() { main(100,100,101,100,1,1); }
#[test(should_fail)]
fn root_too_high() { main(0,0,3,4,25,6); }
#[test(should_fail)]
fn root_range() { main(0,0,0,0,0,131072); }
#[test(should_fail)]
fn distance_range() { main(0,0,0,0,8589934592,0); }
