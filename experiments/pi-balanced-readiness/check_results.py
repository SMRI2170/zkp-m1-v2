"""Validate read-only observations; no live device or proof execution in CI."""
import hashlib,json
from pathlib import Path
from observe import summarize,PREFLIGHT_SHA
ROOT=Path(__file__).resolve().parents[2]
def main():
    m=json.loads((ROOT/'week24/manifests/pi-readiness-issue60.json').read_text())
    for name,sha in m['file_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,name
    base=ROOT/'week24/logs/pi-readiness-issue60-v1'
    rows=[json.loads(s) for s in (base/'health.jsonl').read_text().splitlines()]
    recorded=json.loads((base/'summary.json').read_text())
    assert len(rows)==3 and all(recorded[k]==v for k,v in summarize(rows).items())
    assert recorded['health_sha256']==hashlib.sha256((base/'health.jsonl').read_bytes()).hexdigest()
    assert recorded['preflight_source_sha256']==PREFLIGHT_SHA
    assert hashlib.sha256((ROOT/'experiments/pi4-stability/preflight.py').read_bytes()).hexdigest()==PREFLIGHT_SHA
    assert all(not r['ready'] and r['system_swap_used_bytes']==0 and r['throttled']=='0x50000' for r in rows)
    assert not recorded['ready_for_next_preflight'] and recorded['reboot_cause']=='unknown' and not recorded['proof_executed']
    print('Pi read-only observations verified: 3 snapshots, guards not ready, no proof/performance claim, reboot cause unknown.')
if __name__=='__main__':main()
