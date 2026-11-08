"""Native negative test: reject an invalid near-zero attack-catalog distance."""
import argparse
import json
import math
import os
from pathlib import Path

from observer_attack import attack_spec,run_attack_scene
from scene import RX_POSITIONS
from setup import REPO


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--workspace',type=Path,default=REPO/'.cache/issue75');a=p.parse_args();os.umask(0o077)
    if not a.raw_dir.resolve().is_relative_to((REPO/'captures').resolve()):p.error('Use ignored captures/')
    if a.raw_dir.exists() or a.out.exists():p.error('Preserve evidence; choose new paths')
    a.raw_dir.mkdir(parents=True,mode=0o700);a.out.parent.mkdir(parents=True,exist_ok=True)
    spec=attack_spec(799,'schedule_aware',100,'strong',count=1)
    angle=math.radians(spec['angle_deg'])+3/80*.1
    spec['catalog_override']=dict(RX_POSITIONS)
    spec['catalog_override'][0]=[200+80*math.cos(angle),200+80*math.sin(angle),40]
    try:
        run_attack_scene(spec,a.workspace.resolve(),a.raw_dir.resolve()/'zero-distance')
    except ValueError:
        receipt=json.loads((a.raw_dir/'zero-distance/execution.json').read_text())
        log=(a.raw_dir/'zero-distance/simulation.log').read_text()
        if receipt['exit_code']==0 or 'near-zero compensation distance' not in log:raise ValueError('Failure was not the intended native distance rejection')
        result=dict(status='EXPECTED_REJECTION_PASSED',exit_code=receipt['exit_code'],reason='Invalid synthetic attack-catalog distance rejected in native code before TX',log_sha256=receipt['log_sha256'])
        a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return 0
    raise ValueError('Invalid synthetic geometry was not rejected')


if __name__=='__main__':raise SystemExit(main())
