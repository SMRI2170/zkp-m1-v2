"""Explicit observation regimes; detector projections never contain truth."""
from collections import defaultdict
import hashlib
import math

OBSERVABLE_FIELDS=('tx_event_id','rx_event_id','rx_node_id','rx_time','rx_xyz',
                   'claimed_xyz','claimed_timestamp','serial','rssi_dbm','delivered')


def detector_projection(rows,source_run,regime='asynchronous_one_rssi'):
    if not source_run:
        raise ValueError('A run namespace is required for packet IDs')
    namespace=hashlib.sha256(source_run.encode()).hexdigest()[:24]
    if regime not in ['asynchronous_one_rssi','same_physical_packet_comparison']:
        raise ValueError('Explicit observation regime required')
    projected=[]
    for row in rows:
        record={k:row[k] for k in OBSERVABLE_FIELDS if k!='claimed_xyz'}
        if row['delivered']:
            record['claimed_xyz']=row['rx_claimed_xyz'] # Only the received payload, not TX truth.
        else:
            if row['rssi_dbm'] is not None or row['rx_time'] is not None:
                raise ValueError('Unreceived packet contains measured RX data')
            record.update(claimed_xyz=None,serial=None,claimed_timestamp=None)
        projected.append(dict(dataset_source='simulation',source_run_id=namespace,
                              observer_regime=regime,**record))
    return projected


def asynchronous_view(rows,receiver_ids,count):
    groups=defaultdict(list)
    for row in rows:groups[row['tx_event_id']].append(row)
    ordered=sorted(groups.values(),key=lambda values:values[0]['tx_time'])[:count]
    output=[]
    for index,values in enumerate(ordered):
        selected=receiver_ids[index%len(receiver_ids)]
        match=[r for r in values if r['rx_node_id']==selected]
        if len(match)!=1:
            raise ValueError('Missing/duplicate configured receiver opportunity')
        output.append(match[0]) # Do not fall back to another RX if this one missed.
    if len(output)!=count:
        raise ValueError('Not enough distinct transmissions')
    return output


def same_packet_group(observations):
    keys={(r['source_run_id'],r['tx_event_id']) for r in observations}
    if len(keys)!=1:
        raise ValueError('DRSS requires one physical transmission in one run')
    if len({r['rx_node_id'] for r in observations})!=len(observations):
        raise ValueError('Duplicate receiver')
    return [r for r in observations if r['delivered'] and r['rssi_dbm'] is not None]


def unrestricted_single_rssi(view):
    keys=[(r['source_run_id'],r['tx_event_id']) for r in view]
    if len(set(keys))!=len(keys):
        raise ValueError('Expected one opportunity per distinct transmission')
    return [dict(source_run_id=r['source_run_id'],tx_event_id=r['tx_event_id'],
                 decision='UNDETERMINED',score=None,
                 reason='one unrestricted unknown power per observation' if r['rssi_dbm'] is not None else 'no RSSI received') for r in view]


def nonidentifiability_counterexample(count,ratio=4,n=2):
    if count<1 or ratio<=0 or n<=0:
        raise ValueError('Positive count, distance ratio and exponent required')
    error=0.
    for k in range(count):
        d=10+(k%300);p=-10+(k%41);noise=.7*math.sin(k)
        other_distance=d*ratio
        other_power=p+10*n*math.log10(other_distance/d)
        first=p-10*n*math.log10(d)+noise
        other=other_power-10*n*math.log10(other_distance)+noise
        error=max(error,abs(first-other))
    return dict(count=count,distance_ratio=ratio,path_loss_exponent=n,
                power_compensation_db=10*n*math.log10(ratio),max_rssi_difference_db=error,
                scope='Mathematical log-distance counterexample, not a second RF execution; common claim and residual, unrestricted independent power',
                does_not_establish=['same delivery/interference under physical output limits','identity authentication','safety distance'])


def translated_trajectory_counterexample(count,gap_s=3600):
    receivers=[(100,100,2),(300,100,2),(100,300,2),(300,300,2),(200,100,8)]
    errors=[];changes=[]
    for i in range(count):
        t=.1+i*gap_s;angle=3/80*t
        p=(200+80*math.cos(angle),200+80*math.sin(angle),40)
        other=(p[0]+100,p[1],p[2]);receiver=receivers[i%len(receivers)]
        d=math.dist(p,receiver);other_d=math.dist(other,receiver)
        change=20*math.log10(other_d/d);noise=.7*math.sin(i)
        first=13-20*math.log10(d)+noise
        second=13+change-20*math.log10(other_d)+noise
        errors.append(abs(first-second));changes.append(change)
    return dict(count=count,gap_s=gap_s,trajectory_translation_m=100,
                both_instantaneous_speeds_mps=3,common_claim_in_both_worlds=True,
                max_rssi_difference_db=max(errors),power_change_min_db=min(changes),power_change_max_db=max(changes),
                scope='Mathematical pair of smooth translated trajectories with per-observation unrestricted power; not a second RF run')


def symmetric_multisite_counterexample():
    receivers=[(100,0,0),(0,100,0),(-100,0,0),(0,-100,0)]
    first=(0,0,80);other=(0,0,20);n=2.2
    change=10*n*math.log10(math.dist(other,receivers[0])/math.dist(first,receivers[0]))
    errors=[abs((13-10*n*math.log10(math.dist(first,r)))-(13+change-10*n*math.log10(math.dist(other,r)))) for r in receivers]
    return dict(receivers=4,heights_m=[80,20],power_change_db=change,max_rssi_difference_db=max(errors),
                scope='Mathematical symmetric log-distance counterexample; not the five-node INET scene or an RF execution')
