"""Offline stage receipts; never claim Actions performs native RF runs."""
import argparse
import hashlib
import json
from pathlib import Path

from setup import ROOT


def validate_geometry(root,plan_path):
    result=json.loads((root/'summary.json').read_text());plan=json.loads(plan_path.read_text())
    if result['status']!='PR6A_GEOMETRY_SMOKE_PASSED' or result['completed_cases']!=17:raise ValueError('Geometry smoke incomplete')
    if plan['configuration_sha256']!=hashlib.sha256((ROOT/'config/external-validity.json').read_bytes()).hexdigest():raise ValueError('Frozen design changed')
    if sum(r['tx'] for r in result['receipts'])!=result['total_new_phy_tx'] or sum(r['rx'] for r in result['receipts'])!=result['total_rx']:raise ValueError('RF receipt count mismatch')
    if {r['layout'] for r in result['receipts']}!={'baseline','biased','irregular'}:raise ValueError('Missing declared layout')
    if {r['direction'] for r in result['receipts']}!={'x','toward','away','tangent','vertical','equidistant'}:raise ValueError('Missing native claim direction')
    for r in result['receipts']:
        if r['exit_code'] or r['claim_max_error_m']>1e-8 or r['displacement_norm_max_error_m']>1e-8:raise ValueError('Native geometry mismatch')
        if r['rx']>r['tx']*5:raise ValueError('RX count exceeds opportunities')
    return dict(status='PASSED',stage='PR6a',native_rf_cases=17,layouts=3,directions=6,scope='Offline receipt audit, not RF execution in CI')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('geometry_results',type=Path);p.add_argument('plan',type=Path);a=p.parse_args()
    print(json.dumps(validate_geometry(a.geometry_results,a.plan),indent=2))
