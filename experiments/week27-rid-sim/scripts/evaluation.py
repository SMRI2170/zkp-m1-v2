"""Conditional detectors on an observable-only projection, not position proofs.

No method receives truth, true power, attack labels, scenario names or seeds.
The free-power single-RSSI policy deliberately always abstains. Statistical
methods below add assumptions and are not solutions to unrestricted power.
"""
from collections import defaultdict
import itertools
import math
import random
import statistics

from observations import same_packet_group


def signal_dbm(row,noise_dbm=-100.):
    """Known, fixed INET noise floor subtraction: an EXTRA model assumption."""
    if not row['delivered'] or row['rssi_dbm'] is None:return None
    power=10**(row['rssi_dbm']/10)-10**(noise_dbm/10)
    return 10*math.log10(power) if power>0 else None


def fit_geometry(normal_observations,role):
    if role!='train_normal':raise ValueError('Fit requires normal training split')
    values=defaultdict(list)
    for r in normal_observations:
        power=signal_dbm(r)
        if power is not None:
            values[r['rx_node_id']].append((math.log10(max(math.dist(r['claimed_xyz'],r['rx_xyz']),.001)),power))
    fitted={}
    for node,pairs in values.items():
        x,y=zip(*pairs);mx=statistics.mean(x);my=statistics.mean(y)
        variance=sum((v-mx)**2 for v in x)
        if len(pairs)<10 or variance<1e-8:raise ValueError('Insufficient normal geometry variation')
        slope=sum((a-mx)*(b-my) for a,b in pairs)/variance
        fitted[node]=(my-slope*mx,slope)
    return fitted


def prediction(row,geometry):
    intercept,slope=geometry[row['rx_node_id']]
    return intercept+slope*math.log10(max(math.dist(row['claimed_xyz'],row['rx_xyz']),.001))


def single_residual(view,geometry):
    # A single flight-wide nuisance offset, estimated from OBSERVABLE claims
    # and RSSI. This batch statistic does not assume true nominal TX power.
    errors=[None if signal_dbm(r) is None else signal_dbm(r)-prediction(r,geometry) for r in view]
    valid=[v for v in errors if v is not None]
    center=statistics.median(valid) if valid else 0.
    return [None if v is None else abs(v-center) for v in errors]


def kf_scores(view):
    """Replay upstream scalar KF equations ONLY on selected observations.

    Upstream Q=.01, R=4, P0=10, n=2, f=2400 MHz. Each observer/claimed RID
    has independent state. Missing RSSI does not update state. Startup is UND,
    unlike the upstream offline evaluator's nan_to_num(0) convention.
    """
    states={};scores=[]
    for r in view:
        if not r['delivered'] or r['rssi_dbm'] is None:
            scores.append(None);continue
        key=(r['rx_node_id'],r['serial'])
        distance=max(math.dist(r['claimed_xyz'],r['rx_xyz']),.001)
        z=r['rssi_dbm']+32.44+20*math.log10(2400)+20*math.log10(distance/1000)
        if key not in states:
            states[key]=(z,10.);scores.append(None);continue
        estimate,covariance=states[key];prior=covariance+.01;innovation=z-estimate
        variance=prior+4.;gain=prior/variance
        scores.append(innovation**2/variance)
        states[key]=(estimate+gain*innovation,(1-gain)*prior)
    return scores


def drss_score(frame,geometry):
    received=same_packet_group(frame)
    residuals=[signal_dbm(r)-prediction(r,geometry) for r in received if signal_dbm(r) is not None]
    if len(residuals)<2:return None
    # Maximum all-pair discrepancy; common power cancels in the assumed
    # isolated-signal, calibrated receiver model, not arbitrary interference.
    return max(residuals)-min(residuals)


def mlat_score(frame,solver):
    received=same_packet_group(frame)
    if len(received)<4:return None
    import numpy as np
    positions=np.asarray([r['rx_xyz'] for r in received],dtype=float)
    values=np.asarray([r['rssi_dbm'] for r in received],dtype=float)
    claim=np.asarray(received[0]['claimed_xyz'],dtype=float)
    if any(r['claimed_xyz']!=received[0]['claimed_xyz'] for r in received):
        raise ValueError('Received payload differs across same-frame observers')
    position,power=solver(positions,values,claim)
    if position is None or power is None or not np.isfinite(position).all() or not math.isfinite(power):return None
    # Do not silently discard unphysical estimates or large normal errors.
    return float(np.linalg.norm(position-claim))


def calibrated_threshold(scores,role,alpha=.05):
    if role!='calibrate_normal':raise ValueError('Threshold requires normal calibration split')
    valid=sorted(s for s in scores if s is not None and math.isfinite(s))
    if not valid: return None
    # Empirical upper quantile, not a finite-sample FPR guarantee under
    # within-flight dependence. Independent flights are the reporting units.
    return valid[min(len(valid)-1,math.ceil((1-alpha)*len(valid))-1)]


def decide(scores,threshold):
    return ['UNDETERMINED' if s is None or threshold is None or not math.isfinite(s)
            else 'FLAG' if s>threshold else 'BELOW_THRESHOLD' for s in scores]


def metrics(decisions,received):
    if len(decisions)!=len(received):raise ValueError('One outcome per TX required')
    if any(d not in ['FLAG','BELOW_THRESHOLD','UNDETERMINED'] for d in decisions):raise ValueError('Invalid decision')
    if any(d!='UNDETERMINED' and not rx for d,rx in zip(decisions,received)):
        raise ValueError('An unreceived packet cannot be scored')
    total=len(decisions);valid=sum(d!='UNDETERMINED' for d in decisions);flags=decisions.count('FLAG')
    return dict(tx_count=total,received_count=sum(received),scored_count=valid,flag_count=flags,
                below_count=decisions.count('BELOW_THRESHOLD'),und_count=decisions.count('UNDETERMINED'),
                received_rate=sum(received)/total if total else None,
                eligible_rate=valid/total if total else None,
                und_rate=decisions.count('UNDETERMINED')/total if total else None,
                alarm_scored=flags/valid if valid else None,
                alarm_received=flags/sum(received) if any(received) else None,
                alarm_all_tx=flags/total if total else None,
                below_scored=decisions.count('BELOW_THRESHOLD')/valid if valid else None)


def grouped_frames(rows,receiver_ids):
    frames={}
    for r in rows:
        if r['rx_node_id'] in receiver_ids:frames.setdefault(r['tx_event_id'],[]).append(r)
    return list(frames.values())


def split_check(train,calibration,evaluation):
    sets=[set(train),set(calibration),set(evaluation)]
    if any(a&b for a,b in itertools.combinations(sets,2)):raise ValueError('Seed leakage across splits')


def seed_interval(values,repeats=1000,seed=70170):
    values=[x for x in values if x is not None]
    if not values:return dict(mean=None,low=None,high=None,independent_seeds=0)
    if len(values)==1:return dict(mean=values[0],low=None,high=None,independent_seeds=1)
    rng=random.Random(seed);means=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(repeats))
    return dict(mean=statistics.mean(values),low=means[int(.025*repeats)],high=means[min(repeats-1,int(.975*repeats))],independent_seeds=len(values))


def risk_mask(tx,user_at):
    # EVALUATION ONLY. Never passed to score calculation or calibration.
    return [math.dist(t['true_tx_xyz'],user_at(t['tx_time']))<30<=math.dist(t['claimed_xyz'],user_at(t['tx_time'])) for t in tx]
