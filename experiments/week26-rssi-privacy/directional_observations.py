"""Paired M0/M1/M2 observation-design study. Synthetic RF, not a field detector.

M0-stat uses a calibrated normal-power distribution. M0-free has zero residual
degrees of freedom with one unrestricted power per event. M1 profiles out
common power at one site using simultaneous azimuthal power measurements.
M2 profiles out common power across sites receiving the same event.
"""
import os
for _k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[_k] = '1'
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import platform
import resource
import time
import numpy as np


def pattern(theta, count, amplitude=6):
    theta = np.asarray(theta)
    phi = np.arange(count) * 2 * np.pi / count
    return amplitude * (np.cos(theta[..., None] - phi) - 1)


def centered_score(raw, predicted, mask):
    residual = raw - predicted
    count = mask.sum(axis=-1)
    center = np.sum(np.where(mask, residual, 0), axis=-1) / np.maximum(count, 1)
    score = np.sqrt(np.sum(np.where(mask, (residual-center[..., None])**2, 0), axis=-1)
                    / np.maximum(count, 1))
    return np.where(count >= 2, score, np.nan)


def generate(cfg, seed, split, distance=None):
    rng = np.random.default_rng(np.random.SeedSequence([seed, split, 661]))
    nf = cfg['calibration_flights'] if split == 0 else cfg['test_flights']
    ne = cfg['events_per_flight']; shape = (nf, ne)
    sites = np.asarray(cfg['observer_xyz_m'], dtype=float)
    active = np.broadcast_to((np.arange(nf) % len(sites))[:, None], shape)
    u = np.linspace(0, 1, ne)[None, :]
    heading = rng.uniform(-np.pi, np.pi, (nf, 1)) + .6 * u
    radius = (rng.uniform(25, 310, (nf, 1)) + 8*np.sin(2*np.pi*u)
              if distance is None else np.full(shape, distance))
    local = np.stack([radius*np.cos(heading), radius*np.sin(heading),
                      np.broadcast_to(rng.uniform(20, 50, (nf, 1)), shape)], axis=-1)
    xyz = sites[active] + local
    return dict(xyz=xyz, active=active, heading=heading,
                power_z=rng.normal(size=shape),
                noise0=rng.normal(size=shape), noise1=rng.normal(size=(*shape, 6)),
                noise2=rng.normal(size=(*shape, len(sites))),
                gnss=rng.normal(size=(*shape, 3)),
                gain_z=rng.normal(size=(*shape, 6)),
                drift_z=rng.normal(size=(nf, 1, 6)),
                yaw_z=rng.normal(size=(nf, 1)),
                scatter_z=rng.normal(size=shape),
                nlos=rng.random(size=shape) < .2,
                drop1=rng.random(size=(*shape, 6)),
                drop2=rng.random(size=(*shape, len(sites))))


def claim(data, cfg, shift, direction):
    sites = np.asarray(cfg['observer_xyz_m'])
    local = data['xyz'] - sites[data['active']]
    unit = local[..., :2] / np.linalg.norm(local[..., :2], axis=-1, keepdims=True)
    if direction == 'inward': unit = -unit
    elif direction == 'tangential': unit = np.stack([-unit[..., 1], unit[..., 0]], axis=-1)
    elif direction != 'outward': raise ValueError(direction)
    delta = np.concatenate([shift*unit, np.zeros((*unit.shape[:-1], 1))], axis=-1)
    # Same independent claim GNSS perturbation in normal and attack cases.
    return data['xyz'] + delta + cfg['claim_gnss_sd_m'] * data['gnss']


def geometry(data, cfg, q):
    sites = np.asarray(cfg['observer_xyz_m'])
    local = data['xyz'] - sites[data['active']]
    query = q - sites[data['active']]
    return (np.linalg.norm(local, axis=-1), np.linalg.norm(query, axis=-1),
            np.arctan2(local[..., 1], local[..., 0]),
            np.arctan2(query[..., 1], query[..., 0]))


def observe(data, cfg, q, sd, count, power_mode, scenario='ideal', gap_s=0):
    d, dq, theta, tq = geometry(data, cfg, q)
    n = cfg['path_loss_exponent']; b = 10*n
    actual_n = n + (.3 if scenario == 'n_mismatch' else 0)
    power = np.full_like(d, cfg['reference_received_dbm'])
    if power_mode != 'constant': power += cfg['power_sd_db'] * data['power_z']
    if power_mode == 'joint_unbounded': power += b*np.log10(d/dq)
    # Hardware gain residuals are fixed across splits; test drift is explicit.
    amplitude = cfg['pattern_amplitude_db']
    scatter = np.where(data['nlos'], np.deg2rad(20)*data['scatter_z'], 0) if scenario == 'nlos' else 0
    yaw = np.deg2rad(5)*data['yaw_z'] if scenario == 'yaw5' else 0
    common_loss = 10*data['nlos'] if scenario == 'nlos' else 0
    base = power - 10*actual_n*np.log10(d) - common_loss
    gain = pattern(theta+scatter-yaw, count, amplitude)
    empirical = scenario == 'empirical_indoor'
    noise1 = data['empirical1'][..., :count] if empirical else sd*data['noise1'][..., :count]
    raw1 = base[..., None] + gain + noise1
    if scenario == 'gain_drift2': raw1 += 2*data['drift_z'][..., :count]
    if scenario == 'async_drift':
        # Each local tuple keeps its own timestamp/claim. No cross-time triangulation.
        hours = gap_s/3600 * data['active']/max(len(cfg['observer_xyz_m'])-1, 1)
        raw1 += cfg['gain_drift_db_per_sqrt_hour']*np.sqrt(hours)[..., None]*data['drift_z'][..., :count]
    if scenario == 'switched_packets':
        # Independent power between switched packets. No longer common power.
        raw1 += 8*data['gain_z'][..., :count]
    pred1 = pattern(tq, count, amplitude)
    sites = np.asarray(cfg['observer_xyz_m'])
    if scenario == 'layout_line':
        sites = np.array([[-120,0,2],[-60,0,2],[0,0,2],[60,0,2],[120,0,2]])
    elif scenario == 'layout_cluster':
        sites = np.array([[-5,-5,2],[5,-5,2],[5,5,2],[-5,5,2],[0,0,2]])
    dist2 = np.linalg.norm(data['xyz'][..., None, :]-sites, axis=-1)
    query2 = np.linalg.norm(q[..., None, :]-sites, axis=-1)
    noise2 = data['empirical2'] if empirical else sd*data['noise2']
    raw2 = power[..., None]-10*actual_n*np.log10(dist2)+noise2
    pred2 = -b*np.log10(query2)
    noise0 = data['empirical0'] if empirical else sd*data['noise0']
    raw0 = power-10*actual_n*np.log10(d)-common_loss+noise0
    pred0 = -b*np.log10(dq)
    mask1 = np.ones_like(raw1, dtype=bool); mask2 = np.ones_like(raw2, dtype=bool)
    if scenario == 'rf_missing':
        mask1 = (raw1 >= -100) & (data['drop1'][..., :count] >= .1)
        mask2 = (raw2 >= -100) & (data['drop2'] >= .1)
        raw0 = np.where((raw0 >= -100) & (data['drop1'][..., 0] >= .1), raw0, np.nan)
    if scenario == 'quantization':
        raw0, raw1, raw2 = np.rint(raw0), np.rint(raw1), np.rint(raw2)
    # Binary mask encodes which channels have calibrated threshold support.
    key1 = (mask1*(2**np.arange(count))).sum(axis=-1) + (2**count)*data['active']
    key2 = (mask2*(2**np.arange(len(sites)))).sum(axis=-1)
    return dict(M0_stat=(raw0-pred0, data['active']),
                M0_free=(np.full_like(d, np.nan), data['active']),
                M1=(centered_score(raw1, pred1, mask1), key1),
                M2=(centered_score(raw2, pred2, mask2), key2))


def calibrate(observations, cfg):
    result = {}
    for model, (score, key) in observations.items():
        table = {}
        for k in np.unique(key):
            values = score[(key == k) & np.isfinite(score)]
            if len(values) < cfg['minimum_calibration_events']: continue
            center = float(np.median(values)) if model == 'M0_stat' else 0.
            values = np.abs(values-center) if model == 'M0_stat' else values
            table[int(k)] = (center, float(np.quantile(values, 1-cfg['normal_alarm_target'])), len(values))
        result[model] = table
    return result


def decide(model, values, table):
    score, key = values
    usable = np.zeros_like(score, dtype=bool); alarm = usable.copy()
    for k, (center, threshold, _) in table.items():
        m = (key == k) & np.isfinite(score)
        usable |= m
        tested = np.abs(score-center) if model == 'M0_stat' else score
        alarm |= m & (tested > threshold)
    return usable, alarm


def metrics(usable, alarm):
    n, k, a = usable.size, int(usable.sum()), int(alarm.sum())
    return dict(events=n, decided=k, alarms=a, abstain_rate=1-k/n,
                alarm_all=a/n, alarm_conditional=a/k if k else None)


def evaluate(cfg, seed, empirical_pools=None):
    rows, threshold_rows, history = [], [], []
    cal, test = generate(cfg, seed, 0), generate(cfg, seed, 1)
    def run(study, sd, count, pm, scenario='ideal', distance=None, gap=0):
        evaluation = test if distance is None else generate(cfg, seed, 1, distance)
        # Stress scenarios represent test-time shift relative to ideal calibration,
        # except reception/quantization, which are enabled in both splits.
        cal_scenario = scenario if scenario in ('rf_missing', 'quantization','empirical_indoor','layout_line','layout_cluster') else 'ideal'
        cq = claim(cal, cfg, 0, 'outward')
        tables = calibrate(observe(cal, cfg, cq, sd, count,
                                  'constant' if pm == 'constant' else 'random', cal_scenario), cfg)
        tag = dict(seed=seed, study=study, noise_sd_db=sd, antennas=count, power_mode=pm,
                   scenario=scenario, distance_m=distance or 0, gap_s=gap)
        for model, table in tables.items():
            for key, (center, threshold, samples) in table.items():
                threshold_rows.append(dict(**tag, model=model, mask_key=key, center_db=center,
                                           threshold_db=threshold, samples=samples))
        cases = [('normal', 0, 'outward')] + [(f'{di}{s}', s, di) for di in cfg['directions'] for s in cfg['shifts_m']]
        if study in ('stress', 'async'): cases = [('normal',0,'outward'), ('outward100',100,'outward'), ('tangential100',100,'tangential')]
        for case, shift, direction in cases:
            q = claim(evaluation, cfg, shift, direction)
            # Truthful normal control does not use an attack power offset.
            mode = 'random' if pm == 'joint_unbounded' and shift == 0 else pm
            obs = observe(evaluation, cfg, q, sd, count, mode, scenario, gap)
            for model, values in obs.items():
                if study == 'layout' and model != 'M2': continue
                usable, alarm = decide(model, values, tables[model])
                d, dq, theta, tq = geometry(evaluation, cfg, q)
                bearing_delta = np.abs(np.angle(np.exp(1j*(tq-theta)))) * 180/np.pi
                power_change = 10*cfg['path_loss_exponent']*np.log10(d/dq) if mode=='joint_unbounded' else np.zeros_like(d)
                rows.append(dict(**tag, model=model, case=case, shift_m=shift, direction=direction,
                                 mean_bearing_change_deg=float(bearing_delta.mean()),
                                 attack_power_shift_min_db=float(power_change.min()),
                                 attack_power_shift_max_db=float(power_change.max()), **metrics(usable, alarm)))
                if study == 'async' and model == 'M1':
                    # A 3-encounter bundle, each from a distinct observer. FPR of
                    # OR aggregation is measured, not assumed to remain 5%.
                    k = (usable.shape[0]//3)*3
                    u = usable[:k].reshape(-1, 3, usable.shape[1])
                    a = alarm[:k].reshape(-1, 3, alarm.shape[1])
                    for minimum in (1, 2):
                        hu = u.sum(axis=1) >= minimum
                        ha = hu & (a.sum(axis=1) >= minimum)
                        history.append(dict(**tag, case=case, rule=f'at_least_{minimum}_alarms',
                                            **metrics(hu, ha)))
    for sd in cfg['noise_sd_db']:
        for count in cfg['antenna_counts']:
            for pm in cfg['power_modes']: run('main', sd, count, pm)
    for distance in cfg['distance_bins_m']:
        run('distance', 2, 4, 'joint_unbounded', distance=distance)
    for scenario in ('ideal','gain_drift2','yaw5','nlos','rf_missing','quantization','n_mismatch','switched_packets'):
        run('stress', 2, 4, 'joint_unbounded', scenario)
    for gap in cfg['async_max_gaps_s']:
        for scenario in ('ideal', 'async_drift'):
            run('async', 2, 4, 'joint_unbounded', scenario, gap=gap)
    for scenario in ('ideal','layout_line','layout_cluster'):
        run('layout',2,4,'joint_unbounded',scenario)
    if empirical_pools is not None:
        for parity, pools in enumerate(empirical_pools):
            rng=np.random.default_rng(np.random.SeedSequence([seed,751]))
            for data, pool in zip((cal,test),pools):
                for suffix, base in (('0','noise0'),('1','noise1'),('2','noise2')):
                    data['empirical'+suffix]=rng.choice(pool,size=data[base].shape)
            run(f'empirical_parity{parity}',0,4,'joint_unbounded','empirical_indoor')
    return rows, threshold_rows, history


def aggregate(rows, history=False):
    keys = ['study','noise_sd_db','antennas','power_mode','scenario','distance_m','gap_s','case']
    keys += ['rule'] if history else ['model','shift_m','direction']
    groups = collections.defaultdict(list)
    for r in rows: groups[tuple(r[k] for k in keys)].append(r)
    out=[]; rng=np.random.default_rng(8841)
    for key, group in groups.items():
        group = sorted(group, key=lambda r:r['seed'])
        row=dict(zip(keys,key)); row['independent_seeds']=len(group)
        for metric in ('events','decided','alarms'): row[metric]=sum(r[metric] for r in group)
        indices = rng.integers(0,len(group),(1000,len(group)))
        for metric in ('alarm_conditional','alarm_all','abstain_rate'):
            values=np.array([np.nan if r[metric] is None else r[metric] for r in group])
            if not np.all(np.isfinite(values)):
                row[metric]=row[metric+'_lo']=row[metric+'_hi']=None
            else:
                bootstrap=values[indices].mean(axis=1)
                row[metric]=float(values.mean())
                row[metric+'_lo'],row[metric+'_hi']=map(float,np.quantile(bootstrap,[.025,.975]))
        if not history:
            row['mean_bearing_change_deg']=float(np.mean([r['mean_bearing_change_deg'] for r in group]))
            row['attack_power_shift_min_db']=min(r['attack_power_shift_min_db'] for r in group)
            row['attack_power_shift_max_db']=max(r['attack_power_shift_max_db'] for r in group)
        out.append(row)
    return out


def counterexamples(cfg):
    theta=np.linspace(-np.pi,np.pi,50); g=pattern(theta,4)
    d1,d2=20.,120.; b=10*cfg['path_loss_exponent']; p1,p2=-42.,-42.+b*np.log10(d2/d1)
    a=p1-b*np.log10(d1)+g; c=p2-b*np.log10(d2)+g
    # A 2-element opposed cosine pattern has a left/right mirror ambiguity.
    mirror=float(np.max(np.abs(pattern(theta,2)-pattern(-theta,2))))
    rng=np.random.default_rng(77); raw=rng.normal(size=(50,4))+g
    mask=np.ones_like(raw,dtype=bool)
    invariant=float(np.max(np.abs(centered_score(raw,g,mask)-centered_score(raw+rng.uniform(-100,100,(50,1)),g,mask))))
    return dict(radial_equal_rssi_max_db=float(np.max(np.abs(a-c))),
                radial_power_difference_db=p2-p1, mirror_two_antenna_max_db=mirror,
                arbitrary_common_power_score_difference_db=invariant,
                scope='Exact analytic model, no claim of RF attack feasibility')


def write_csv(path, rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def append_csv(path, rows):
    existed=path.exists()
    with path.open('a',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        if not existed: writer.writeheader()
        writer.writerows(rows);f.flush();os.fsync(f.fileno())


def indoor_pools(data, parity):
    pools=[[],[]]; sectors=[set(),set()]
    for groups in data.values():
        for (sector, _), values in groups.items():
            baseline=float(np.median(values[:50]))
            index=0 if sector % 2 == parity else 1
            pools[index].extend(v-baseline for v in values[50:]);sectors[index].add(sector)
    if sectors[0]&sectors[1]: raise AssertionError('calibration/test sector leakage')
    arrays=[np.asarray(p,float) for p in pools]
    stats=[dict(count=len(p),mean_db=float(p.mean()),rms_db=float(np.sqrt(np.mean(p*p))),
                abs_p95_db=float(np.quantile(np.abs(p),.95))) for p in arrays]
    return arrays,dict(calibration_parity=parity,calibration=stats[0],test=stats[1],disjoint_sector_sets=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,default=Path(__file__).with_name('directional_config.json'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--empirical-raw',type=Path,help='Pinned public indoor BLE CSVs in ignored captures/, optional')
    args=parser.parse_args()
    cfg=json.loads(args.config.read_text());args.output.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter();rows=[];thresholds=[];hist=[]
    (args.output/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
    pools=None; empirical_sources=[];pool_stats=[]
    if args.empirical_raw:
        from recheck_ble import load
        data,empirical_sources=load(args.empirical_raw);pools=[]
        for parity in (0,1):
            pair,stats=indoor_pools(data,parity);pools.append(pair);pool_stats.append(stats)
    for seed in cfg['seeds']:
        r,t,h=evaluate(cfg,seed,pools);rows.extend(r);thresholds.extend(t);hist.extend(h)
        # Completed seeds survive SSH/process termination. No automatic cache reuse.
        for name, data in [('per_seed',r),('thresholds',t),('history_per_seed',h)]:
            append_csv(args.output/(name+'.csv'),data)
        checkpoint=args.output/'progress.json.tmp'
        checkpoint.write_text(json.dumps(dict(status='running',completed_seeds=sorted({x['seed'] for x in rows}),
            total_seeds=len(cfg['seeds']),note='Completed CSV blocks retained; rerun into a new directory, no resume option'))+'\n')
        checkpoint.replace(args.output/'progress.json')
        print(f'seed {seed}: {len(r)} evaluations completed',flush=True)
    summary=aggregate(rows);history_summary=aggregate(hist,True)
    for name, data in [('summary',summary),('history_summary',history_summary)]:
        write_csv(args.output/(name+'.csv'),data)
    (args.output/'progress.json').write_text(json.dumps(dict(status='complete',completed_seeds=cfg['seeds'],total_seeds=len(cfg['seeds'])))+'\n')
    (args.output/'summary.json').write_text(json.dumps(dict(scope=cfg['scope'],metrics=summary,
        histories=history_summary,counterexamples=counterexamples(cfg),
        empirical_sources=empirical_sources,empirical_pool_statistics=pool_stats,
        empirical_scope='Indoor BLE marginal residuals resampled independently per channel/event; not measured simultaneous-antenna correlation or UAV RID validation',
        intervals='95% percentile bootstrap of independent seed-level rates (1000 resamples); packets within flights are not independent replicates',
        note='M0_free abstains structurally; M0_stat relies on a normal-power distribution. All scenario parameters are illustrative.'),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    files=[Path(__file__),args.config]+([Path(__file__).with_name('recheck_ble.py')] if args.empirical_raw else [])
    manifest=dict(python=platform.python_version(),numpy=np.__version__,platform=platform.platform(),
        runtime_s=time.perf_counter()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if platform.system()=='Darwin' else 1024),
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        output_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.iterdir() if p.is_file()},
        reproduction=f'python3 {Path(__file__)} --config {args.config} --output NEW_DIRECTORY'+(f' --empirical-raw {args.empirical_raw}' if args.empirical_raw else ''))
    (args.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(runtime_s=manifest['runtime_s'],peak_rss_bytes=manifest['peak_rss_bytes'],groups=len(summary))))


if __name__=='__main__': main()
