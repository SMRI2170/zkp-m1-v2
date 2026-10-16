"""Observe only: no sudo, settings changes, service restart, or prover launch."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
PREFLIGHT_SHA='8a6ed1ef7f19066d858afa5ecda61a751a157978be5d502e6c3ec0f3d7f9096e'

def summarize(rows):
    uptimes=[r.get('uptime_s') for r in rows]
    monotonic=bool(rows) and all(type(u) in (int,float) for u in uptimes) and all(a<=b for a,b in zip(uptimes,uptimes[1:]))
    return {'scope':'read-only readiness observations; no proof execution or reboot-cause attribution',
        'samples':len(rows),'all_ready':len(rows)==3 and all(r.get('ready') is True for r in rows),
        'no_observed_uptime_reset':monotonic,
        'observed_uptime_span_s':uptimes[-1]-uptimes[0] if monotonic else None,
        'ready_for_next_preflight':len(rows)==3 and monotonic and all(r.get('ready') is True for r in rows),
        'reboot_cause':'unknown','proof_executed':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--preflight',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if hashlib.sha256(a.preflight.read_bytes()).hexdigest()!=PREFLIGHT_SHA:raise SystemExit('preflight source hash mismatch')
    spec=importlib.util.spec_from_file_location('readiness',a.preflight);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    os.umask(0o077);a.out.mkdir(parents=True,mode=0o700)
    rows=[]
    with (a.out/'health.jsonl').open('x') as f:
        for i in range(3):
            if i:time.sleep(30)
            r=module.snapshot();rows.append(r);f.write(json.dumps(r)+'\n');f.flush()
    result=summarize(rows);result['preflight_source_sha256']=PREFLIGHT_SHA
    (a.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return 0 if result['ready_for_next_preflight'] else 1
if __name__=='__main__':raise SystemExit(main())
