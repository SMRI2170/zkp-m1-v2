"""Freeze the PR6 sparse design before RF evaluation; no simulated results."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from external_scene import claim_position
from scene import layout_positions
from setup import ROOT


def plan(cfg):
    contexts={};geometry=set();attacks=0;rows=[]
    for cell in cfg['cells']:
        seeds=cfg['baseline_evaluation_seeds'] if cell['id']=='reference' else cfg['factor_evaluation_seeds']
        context=(cell['layout'],cell['profile'],cell['schedule'])
        contexts.setdefault(context,set()).update(seeds);geometry.add(context[:2])
        count=len(seeds)*4*len(cfg['offsets_m']);attacks+=count
        rows.append(dict(cell_id=cell['id'],**cell,evaluation_seeds=len(seeds),new_attack_rf_cases=count))
    normal=sum(len(v) for v in contexts.values())
    calibration=sum(len(cfg['baseline_calibration_seeds']) if c==('baseline','free','round_robin') else len(cfg['factor_calibration_seeds']) for c in contexts)
    training=len(geometry);total=attacks+normal+calibration+training
    training_packets=cfg['reference_training_packets']+(training-1)*cfg['factor_training_packets']
    packets=(total-training)*cfg['packets']+training_packets
    minimum_receiver_distance=1e99;max_norm_error=0.;min_claim_receiver_distance=1e99
    import random
    for cell in cfg['cells']:
        positions=layout_positions(cell['layout'])
        for seed in set(cfg['baseline_evaluation_seeds']+cfg['baseline_calibration_seeds']+[cfg['training_seed']]):
            angle=math.radians(random.Random(seed).uniform(0,360))
            for i in range(cfg['packets']):
                t=.1+cfg['gap_s']*i;p=[200+80*math.cos(angle+3/80*t),200+80*math.sin(angle+3/80*t),40]
                minimum_receiver_distance=min(minimum_receiver_distance,*(math.dist(p,r) for r in positions.values()))
                for offset in cfg['offsets_m']:
                    q=claim_position(p,positions[0],cell['direction'],offset)
                    max_norm_error=max(max_norm_error,abs(math.dist(p,q)-offset))
                    min_claim_receiver_distance=min(min_claim_receiver_distance,*(math.dist(q,r) for r in positions.values()))
    if minimum_receiver_distance<1 or min_claim_receiver_distance<1e-3 or max_norm_error>1e-8:raise ValueError('Unsafe declared scene geometry')
    return dict(status='PLAN_FROZEN_NOT_RESULTS',cells=rows,geometry_training_contexts=training,calibration_contexts=len(contexts),
                planned_main_new_rf_cases=total,planned_main_transmissions=packets,training_cases=training,calibration_cases=calibration,normal_evaluation_cases=normal,attack_evaluation_cases=attacks,
                planned_phase6a_cases=17,planned_phase6b_controls=15,estimated_all_raw_mib=round((packets+17*20+15*20)*17000/1024**2,1),
                maximum_all_raw_mib=cfg['budget']['raw_total_max_mib'],minimum_true_receiver_distance_m=minimum_receiver_distance,
                minimum_claim_receiver_distance_m=min_claim_receiver_distance,max_displacement_norm_error_m=max_norm_error,
                interpretation='20 reference flight seeds; 5 per non-reference factor cell. Fixed layouts are declared fixtures, not randomly sampled independent cities. Shadow field seeds are separate from flight/schedule seeds.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('Plan already frozen; preserve it')
    cfg=json.loads((ROOT/'config/external-validity.json').read_text());result=plan(cfg)
    result['configuration_sha256']=hashlib.sha256((ROOT/'config/external-validity.json').read_bytes()).hexdigest()
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='cells'},indent=2))
