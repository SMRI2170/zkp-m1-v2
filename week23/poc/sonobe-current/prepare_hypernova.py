"""Preserve original failed tree, patch a fresh tree to one released arkworks family."""
from pathlib import Path
import shutil
import re

ROOT=Path(__file__).resolve().parents[3]
source=ROOT/'.cache/week23/sources/sonobe-hypernova-9c4e61f8'
target=ROOT/'.cache/week23/sources/sonobe-hypernova-fixed-v1'
shutil.copytree(source,target,ignore=shutil.ignore_patterns('target','.git'))
p=target/'Cargo.toml';text=p.read_text().split('[patch.crates-io]')[0]
text=re.sub(r'(ark-[\w-]+ = )\{ git = "[^"]+", default-features = false \}',r'\1{ version = "=0.6.0", default-features = false }',text)
p.write_text(text)
if (target/'Cargo.lock').exists():(target/'Cargo.lock').rename(target/'Cargo.lock.failed-original')
print(target)

# Port only the removed fork-specific MSM API to the exact arithmetic loop
# used by current Sonobe main. No relation checks or commitment openings removed.
p=target/'crates/primitives/src/commitments/pedersen.rs'
text=p.read_text();start=text.index('        let n = v.len();',text.index('fn msm('));end=text.index('        Ok(res)',start)
text=text[:start]+"""        // Arkworks 0.6 removed the fork-only joint multiplication API.
        // Same MSM relation as current Sonobe main; retain every scalar term.
        if g.len() < v.len() {
            return Err(SynthesisError::Unsatisfiable);
        }
        for (g_i, v_i) in g.iter().zip(v) {
            res += g_i.scalar_mul_le(v_i.to_bits_le()?.iter())?;
        }
"""+text[end:]
p.write_text(text)
