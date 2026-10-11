// Expected compile failure in the fixed revamp/hypernova tree: this API is absent.
use sonobe_fs::hypernova::NovaBlindFold;
fn main() { let _ = core::mem::size_of::<NovaBlindFold>(); }
