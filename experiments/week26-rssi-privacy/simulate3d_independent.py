"""Sequential, bounded-size independent 3D RSSI experiment. All geometry synthetic.

The original simulator ZIP is unavailable. This code defines its own explicit
model, not recovered parameters. No real RF, secrets, Pi or ZKP is involved.
"""
import os
for _name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[_name] = '1'
import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import resource
import sys
import time
import warnings

import numpy as np
from scipy.stats import truncnorm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

SCENARIOS = ['normal', 'constant', 'shift8', 'random9', 'drift', 'step8',
             'position_only', 'joint', 'joint_bounded8', 'whitebox']
MODELS = ['PathLoss', 'Bayesian', 'GP', 'MLP', 'Oracle']


def ar1(rng, count, rho, sd):
    values = np.empty(count)
    values[0] = rng.normal(0, sd)
    for i in range(1, count):
        values[i] = rho * values[i - 1] + rng.normal(0, sd * math.sqrt(1 - rho ** 2))
    return values


def generate(config, seed, split, variant='mixed'):
    """Split-specific RNGs prevent train/test sharing of flight realizations."""
    c = config
    split_index = {'train': 0, 'calibration': 1, 'test': 2}[split]
    rng = np.random.default_rng(np.random.SeedSequence([seed, split_index, 113]))
    # Shared receiver biases, with a fixed noisy estimate, not recalibrated on test.
    device_rng = np.random.default_rng(np.random.SeedSequence([seed, 919]))
    bias = device_rng.normal(0, c['receiver_bias_sd_db'], c['receivers'])
    estimate = bias + device_rng.normal(0, c['receiver_calibration_error_sd_db'], c['receivers'])
    if variant == 'ideal':
        bias = np.zeros_like(bias); estimate = np.zeros_like(estimate)
    records = []
    m = c['events_per_flight']
    for flight in range(c['flights'][split]):
        receiver = flight % c['receivers']
        t = np.arange(m) * c['event_spacing_s']
        angle = rng.uniform(0, 2 * np.pi)
        radius = rng.uniform(*c['horizontal_radius_m'])
        height = rng.uniform(*c['altitude_m'])
        phase = angle + t * rng.uniform(-.004, .004)
        # Coordinates are local fictional offsets about the assigned receiver.
        xyz = np.column_stack([radius * np.cos(phase) + .08 * t,
                               radius * np.sin(phase), height + 2 * np.sin(t / 25)])
        d_true = np.maximum(np.linalg.norm(xyz, axis=1), 1)
        gps_error = rng.normal(0, c['gps_error_sd_m'], xyz.shape)
        if variant == 'ideal':gps_error *= 0
        d_claim = np.maximum(np.linalg.norm(xyz + gps_error, axis=1), 1)
        power = c['reference_received_dbm'] + rng.normal(0, c['flight_power_sd_db'])
        power = power + ar1(rng, m, c['power_ar1'], c['packet_power_sd_db'])
        nlos = np.empty(m, bool); nlos[0] = rng.random() < c['nlos_initial_probability']
        for i in range(1, m):
            nlos[i] = (rng.random() >= c['nlos_to_los_probability']) if nlos[i-1] else (rng.random() < c['los_to_nlos_probability'])
        if variant in ['los_only', 'ideal']:nlos[:] = False
        shadow = ar1(rng, m, c['shadow_ar1'], c['shadow_sd_db'])
        if variant == 'ideal':shadow *= 0
        fading = rng.standard_t(c['fading_t_df'], m) * c['fading_t_scale_db']
        antenna = -3 * np.cos(phase) ** 2
        # Ideal variant removes channel/bias/GPS/censoring, retaining TX randomness,
        # fast fading, antenna variation and quantization (declared explicitly).
        channel = -c['nlos_loss_db'] * nlos + shadow + fading + antenna
        raw = power + bias[receiver] - 10*c['path_loss_exponent'] * np.log10(d_true) + channel
        keep = rng.random(m) >= c['independent_packet_drop_probability']
        if variant == 'ideal':keep[:] = True
        records.append({'flight': np.full(m, flight + split_index * 10000),
                        'receiver': np.full(m, receiver),
                        'time': (flight + split_index * 10000) * c['flight_start_spacing_s'] + t,
                        'd_true': d_true, 'd_claim': d_claim, 'power': power,
                        'raw': raw, 'bias_est': np.full(m, estimate[receiver]),
                        'nlos': nlos, 'keep': keep})
    return {k: np.concatenate([r[k] for r in records]) for k in records[0]}


def receive(data, c, variant):
    rssi = np.round(data['raw'] / c['rssi_quantization_db']) * c['rssi_quantization_db']
    mask = data['keep'] & ((rssi >= c['sensitivity_dbm']) if variant != 'ideal' else True)
    return mask, rssi - data['bias_est']


def scenario(base, c, name, seed, residual_pool):
    data = {k: v.copy() for k, v in base.items()}
    rng = np.random.default_rng(np.random.SeedSequence([seed, SCENARIOS.index(name), 775]))
    normal_power = base['power']
    n = c['path_loss_exponent']
    if name == 'constant':
        for f in np.unique(data['flight']):
            mask = data['flight'] == f
            data['power'][mask] = np.mean(normal_power[mask])
    elif name == 'shift8':data['power'] += 8
    elif name == 'random9':data['power'] = c['reference_received_dbm'] + rng.normal(0, 9, len(normal_power))
    elif name in ['drift', 'step8']:
        for f in np.unique(data['flight']):
            ix = np.where(data['flight'] == f)[0]
            data['power'][ix] += np.linspace(-8, 8, len(ix)) if name == 'drift' else 8 * (np.arange(len(ix)) >= len(ix)//2)
    if name in ['position_only', 'joint', 'joint_bounded8', 'whitebox']:
        # Flip which side of 30m the claimed distance lies on.
        data['d_claim'] = np.where(data['d_true'] < c['distance_threshold_m'], 90., 15.)
    if name in ['joint', 'joint_bounded8']:
        delta = 10*n * np.log10(data['d_true'] / data['d_claim'])
        if name == 'joint_bounded8':delta = np.clip(delta, -c['attack_bound_db'], c['attack_bound_db'])
        data['power'] += delta
    data['raw'] += data['power'] - normal_power
    if name == 'whitebox':
        # Strong adversary knows the instantaneous channel and receiver estimate.
        # Target corrected required-power residual sampled from normal calibration.
        target = rng.choice(residual_pool, len(normal_power)) - 10*n*np.log10(data['d_claim'])
        target_raw = target + data['bias_est']
        data['power'] += target_raw - data['raw']
        data['raw'] = target_raw
    return data


def conformal_radius(residual, flight_ids, coverage):
    # One max score per calibration flight; no packet-iid coverage claim.
    scores = np.array([np.max(np.abs(residual[flight_ids == f])) for f in np.unique(flight_ids)])
    rank = math.ceil((len(scores) + 1) * coverage)
    return float(np.sort(scores)[rank - 1]) if rank <= len(scores) else float('inf')


def fit_models(train, cal, c, variant, seed):
    started = time.monotonic()
    train_mask, r_train = receive(train, c, variant)
    cal_mask, r_cal = receive(cal, c, variant)
    z = np.log10(train['d_true'][train_mask])
    x = r_train[train_mask, None]
    n = c['path_loss_exponent']
    # Only independent synthetic true-distance labels from training are used.
    required = r_train[train_mask] + 10*n*z
    a0 = float(np.median(required)); sigma = max(float(np.std(required)), .1)
    rng = np.random.default_rng(seed)
    subset = rng.choice(len(x), min(c['gp_max_train_points'], len(x)), replace=False)
    gp = make_pipeline(StandardScaler(), GaussianProcessRegressor(
        kernel=RBF(c['gp_rbf_length_scale'], length_scale_bounds='fixed') +
               WhiteKernel(c['gp_white_noise_variance'], noise_level_bounds='fixed'),
        optimizer=None, normalize_y=True))
    mlp = make_pipeline(StandardScaler(), MLPRegressor(
        hidden_layer_sizes=tuple(c['mlp_hidden_layers']), activation='tanh',
        solver='lbfgs', max_iter=c['mlp_max_iter'], random_state=seed, tol=1e-5))
    notices = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        gp.fit(x[subset], z[subset]);mlp.fit(x, z)
        notices = [f'{type(w.message).__name__}: {w.message}' for w in caught]
    cal_x = r_cal[cal_mask, None]; cal_z = np.log10(cal['d_true'][cal_mask])
    radii = {name: conformal_radius(model.predict(cal_x) - cal_z,
                                  cal['flight'][cal_mask], c['nominal_interval_coverage'])
             for name, model in [('GP', gp), ('MLP', mlp)]}
    residual_pool = r_cal[cal_mask] + 10*n*np.log10(cal['d_claim'][cal_mask])
    center = float(np.median(residual_pool))
    alarm_threshold = float(np.quantile(np.abs(residual_pool-center), .95))
    info = {'seed': seed, 'channel': variant, 'a0_db': a0, 'sigma_db': sigma,
            'train_received': int(train_mask.sum()), 'gp_train_points': len(subset),
            'calibration_received': int(cal_mask.sum()), 'calibration_flights_received': len(np.unique(cal['flight'][cal_mask])),
            'conformal_log10_radii': radii, 'alarm_center_db': center,
            'alarm_threshold_db': alarm_threshold, 'fit_wall_seconds': time.monotonic()-started,
            'warnings': notices, 'mlp_iterations': int(mlp[-1].n_iter_)}
    return (a0, sigma, gp, mlp, radii, center, alarm_threshold), info, residual_pool


def predict(models, data, r, c):
    a0, sigma, gp, mlp, radii, _, _ = models
    n = c['path_loss_exponent']; mu = (a0-r)/(10*n); sd = sigma/(10*n)
    lower, upper = c['bayes_log10_distance_support']
    a = (lower-mu)/sd; b = (upper-mu)/sd
    alpha = (1-c['nominal_interval_coverage'])/2
    result = {'PathLoss': (10**np.clip(mu, -3, 6), None, None)}
    result['Bayesian'] = tuple(10**truncnorm.ppf(q, a, b, loc=mu, scale=sd) for q in [.5, alpha, 1-alpha])
    for name, model in [('GP',gp),('MLP',mlp)]:
        z = model.predict(r[:, None]); radius = radii[name]
        result[name] = tuple(10**np.clip(v, -3, 6) for v in [z, z-radius, z+radius])
    # Non-deployable reference, uses true power and true NLOS status.
    result['Oracle'] = (10**np.clip((data['power']-c['nlos_loss_db']*data['nlos']-r)/(10*n), -3, 6), None, None)
    return result


def score(data, models, c, variant, seed, name):
    mask, r = receive(data, c, variant)
    pred = predict(models, data, r, c)
    residual = r + 10*c['path_loss_exponent']*np.log10(data['d_claim'])
    alarm = np.abs(residual-models[5]) > models[6]
    rows = []
    for f in np.unique(data['flight']):
        flight = data['flight'] == f
        ix = flight & mask; count = int(ix.sum())
        for model, (point, lo, hi) in pred.items():
            true = data['d_true'][ix]; err = point[ix]-true
            row = {'seed':seed, 'channel':variant, 'scenario':name, 'model':model,
                   'flight_id':int(f), 'emitted':int(flight.sum()), 'received':count,
                   'abs_error_sum_m':float(np.abs(err).sum()), 'squared_error_sum_m2':float((err**2).sum()),
                   'alarm_count':int(alarm[ix].sum()),
                   'interval_count':count if lo is not None else 0,
                   'covered_count':None, 'interval_width_sum_m':None, 'decided_count':None, 'wrong_decision_count':None}
            if lo is not None:
                left, right = lo[ix], hi[ix]; threshold = c['distance_threshold_m']
                below = right < threshold;above = left > threshold
                row.update(covered_count=int(((left<=true)&(true<=right)).sum()),
                           interval_width_sum_m=float((right-left).sum()),
                           decided_count=int((below|above).sum()),
                           wrong_decision_count=int(((below&(true>=threshold))|(above&(true<=threshold))).sum()))
            rows.append(row)
    return rows, {'emitted':len(mask), 'received':int(mask.sum()),
                  'power_min_db':float(data['power'].min()), 'power_max_db':float(data['power'].max())}


def summarize(rows):
    keys = ['channel','scenario','model']
    groups = {}
    for r in rows:groups.setdefault(tuple(r[k] for k in keys), []).append(r)
    result = []
    for key, group in groups.items():
        received = sum(r['received'] for r in group); emitted = sum(r['emitted'] for r in group)
        intervals = sum(r['interval_count'] for r in group)
        out = dict(zip(keys,key));out.update(seeds=len({r['seed'] for r in group}),
            emitted=emitted,received=received,reception_rate=received/emitted,
            mae_m=sum(r['abs_error_sum_m'] for r in group)/received if received else None,
            rmse_m=math.sqrt(sum(r['squared_error_sum_m2'] for r in group)/received) if received else None,
            alarm_rate=sum(r['alarm_count'] for r in group)/received if received else None,
            interval_coverage=None,mean_interval_width_m=None,undetermined_rate=None,
            wrong_decision_rate_all_received=None,wrong_rate_among_decided=None)
        if intervals:
            decided=sum(r['decided_count'] for r in group);wrong=sum(r['wrong_decision_count'] for r in group)
            out.update(interval_coverage=sum(r['covered_count'] for r in group)/intervals,
                       mean_interval_width_m=sum(r['interval_width_sum_m'] for r in group)/intervals,
                       undetermined_rate=1-decided/intervals,
                       wrong_decision_rate_all_received=wrong/intervals,
                       wrong_rate_among_decided=wrong/decided if decided else None)
        result.append(out)
    return result


def write_csv(path, rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('synthetic3d_config.json'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();c=json.loads(args.config.read_text())
    if args.out.exists():parser.error('use a new output directory; prior runs are preserved')
    args.out.mkdir(parents=True);(args.out/'config.json').write_text(json.dumps(c,indent=2)+'\n')
    started=time.monotonic();all_rows=[];fits=[];checks=[];scenario_resources=[]
    status={'status':'running','scope':__doc__,'completed_jobs':0}
    def checkpoint():
        (args.out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    checkpoint()
    try:
        with threadpool_limits(limits=1):
            for variant in c['channel_variants']:
                for seed in c['seeds']:
                    train=generate(c,seed,'train',variant);cal=generate(c,seed,'calibration',variant);base=generate(c,seed,'test',variant)
                    assert not set(train['flight']) & set(cal['flight'])
                    assert not set(train['flight']) & set(base['flight'])
                    models, info, residual_pool=fit_models(train,cal,c,variant,seed);fits.append(info)
                    scenarios=SCENARIOS if variant=='mixed' else ['normal']
                    for name in scenarios:
                        data=scenario(base,c,name,seed,residual_pool)
                        rows, extra=score(data,models,c,variant,seed,name);all_rows.extend(rows)
                        scenario_resources.append(dict(seed=seed,channel=variant,scenario=name,**extra))
                        if name=='position_only':
                            checks.append({'seed':seed,'channel':variant,'check':'position_only_keeps_raw_and_receive_mask',
                                           'passed':bool(np.array_equal(data['raw'],base['raw']) and np.array_equal(receive(data,c,variant)[0],receive(base,c,variant)[0]))})
                        if name=='joint_bounded8':
                            assert np.max(np.abs(data['power']-base['power'])) <= c['attack_bound_db']+1e-10
                        status['completed_jobs']+=1;checkpoint()
                        with (args.out/'progress.jsonl').open('a') as f:f.write(json.dumps(dict(seed=seed,channel=variant,scenario=name,**extra))+'\n')
                    print(json.dumps({'channel':variant,'seed':seed,'completed_jobs':status['completed_jobs'],'fit_seconds':info['fit_wall_seconds'],'warnings':len(info['warnings'])}),flush=True)
        assert all(row['passed'] for row in checks)
        summary=summarize(all_rows)
        write_csv(args.out/'flight-metrics.csv',all_rows);write_csv(args.out/'summary.csv',summary)
        write_csv(args.out/'scenario-ranges.csv',scenario_resources)
        peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result={'scope':'Independent illustrative synthetic model; not document04 numerical reproduction',
                'status':'complete','config':c,'summary':summary,'fits':fits,'checks':checks,
                'runtime':{'wall_seconds':time.monotonic()-started,'platform':platform.platform(),
                           'python':sys.version,'process_peak_rss_bytes':peak if sys.platform=='darwin' else peak*1024,
                           'compute_threads':1},
                'limitations':['Parameters not RF calibrated; no 3GPP compliance',
                               'Independent synthetic true distance is available for training/calibration only',
                               'Flight-max log-distance conformal; correlated packets are not calibration units',
                               'GP fixed kernel and at most512 training points; not hyperparameter optimized',
                               'Oracle uses hidden simulator variables; not a deployable bound',
                               'Whitebox attacker knows instantaneous channel, receiver estimate and calibration scores',
                               'No real UAV/Pi/Pixel acquisition or ZKP proof'],
                'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        (args.out/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        status.update(status='complete',wall_seconds=result['runtime']['wall_seconds']);checkpoint()
    except BaseException as exc:
        status.update(status='failed',error=f'{type(exc).__name__}: {exc}');checkpoint();raise


if __name__=='__main__':main()
