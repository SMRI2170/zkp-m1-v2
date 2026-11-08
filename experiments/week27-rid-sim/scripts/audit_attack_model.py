"""Posthoc physical-model decomposition; truth is audit-only, no detector changes."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from evaluation import signal_dbm,prediction
from normalize import write_csv
from observations import asynchronous_view
from observer_attack import SCHEDULE
from run_observer_attack import load_verified,bootstrap


def dipole_pair_gain(actual,receiver):
    distance=math.dist(actual,receiver);horizontal=math.hypot(actual[0]-receiver[0],actual[1]-receiver[1])
    if not math.isfinite(distance) or not math.isfinite(horizontal) or distance<=1e-3 or horizontal<=1e-6:raise ValueError('Dipole axis/null singularity, not a finite received-power prediction')
    return 20*math.log10(1.5)+40*math.log10(horizontal/distance)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--results',type=Path,required=True)
    a=p.parse_args();analysis=a.raw_dir/'analyses'/hashlib.sha256(str(a.results.resolve()).encode()).hexdigest()[:16]
    receipts=[json.loads(line) for line in (a.results/'case-receipts.jsonl').read_text().splitlines()]
    fspl_constant=20*math.log10(4*math.pi*2.442e9/299792458)
    # INET 4.5.4 band centers are zero-indexed: configured channelNumber=6
    # selects 2.442GHz. Both default vertical dipoles have gain 1.5*sin²(theta).
    output=[];maximum_error=0.;maximum_identity=0.;count=0
    for receipt in receipts:
        rid=receipt['run_id'];spec=receipt['spec'];phy=rid.split('-eval-')[0]
        if '-eval-strong-' not in rid or phy not in ['default','upper40'] or spec['attack_case']!='schedule_aware':continue
        geometry={int(k):tuple(v) for k,v in json.loads((analysis/f'{phy}-geometry.json').read_text()).items()}
        rows,tx,audit,ledger=load_verified(a.raw_dir/rid,spec)
        view=asynchronous_view(rows,SCHEDULE,len(tx));components=[]
        for row,truth in zip(view,ledger):
            if not row['delivered']:continue
            gain_true=dipole_pair_gain(row['true_tx_xyz'],row['rx_xyz']);gain_claim=dipole_pair_gain(row['rx_claimed_xyz'],row['rx_xyz'])
            distance_true=math.dist(row['true_tx_xyz'],row['rx_xyz']);distance_claim=math.dist(row['rx_claimed_xyz'],row['rx_xyz'])
            isolated=signal_dbm(row)
            reconstructed=truth['effective_phy_tx_dbm']-fspl_constant-20*math.log10(distance_true)+gain_true
            error=isolated-reconstructed;maximum_error=max(maximum_error,abs(error))
            ideal_claim=spec['nominal_dbm']-fspl_constant-20*math.log10(distance_claim)+gain_claim
            surrogate=ideal_claim-prediction(row,geometry)
            antenna=gain_true-gain_claim;clipping=truth['compensation_error_db'];observed=isolated-prediction(row,geometry)
            identity=observed-surrogate-antenna-clipping-error
            maximum_identity=max(maximum_identity,abs(identity));count+=1
            components.append(dict(surrogate=surrogate,antenna=antenna,clipping=clipping,observed=observed))
        if not components:continue
        result=dict(phy=phy,seed=spec['seed'],offset_m=spec['offset_x_m'],bound_db=spec['attack_bound_db'],received=len(components))
        for field in ['surrogate','antenna','clipping','observed']:
            values=[r[field] for r in components];center=statistics.median(values)
            result[f'{field}_mean_abs_db']=statistics.mean(abs(v) for v in values)
            result[f'{field}_centered_mean_abs_db']=statistics.mean(abs(v-center) for v in values)
        output.append(result)
    if maximum_error>1e-6 or maximum_identity>1e-6:raise ValueError('Declared physical-model decomposition did not reconcile with actual measured RF')
    write_csv(a.results/'model-decomposition.csv',output)
    source_root=Path(__file__).resolve().parents[3]/'.cache/issue75/inet4.5/src/inet/physicallayer/wireless'
    sources=['common/antenna/DipoleAntenna.cc','ieee80211/mode/Ieee80211Band.cc','common/pathloss/FreeSpacePathLoss.cc']
    result=dict(status='PASSED',new_rf_runs=0,reused_selected_receptions=count,per_seed_rows=len(output),
                actual_carrier_hz=2.442e9,configured_channel_index=6,fspl_constant_db=fspl_constant,
                max_signal_reconstruction_error_db=maximum_error,max_signed_residual_identity_error_db=maximum_identity,
                source_sha256={path:hashlib.sha256((source_root/path).read_bytes()).hexdigest() for path in sources},
                formula='observed residual = surrogate normal-model residual at claim + G(true)-G(claim) + power-clipping error + reconstruction error',
                scope='Posthoc truth-only diagnosis for declared vertical dipoles and FreeSpace. No added detector inputs, no threshold tuning, no gain-aware attack RF run, no field multipath attribution.')
    (a.results/'model-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
