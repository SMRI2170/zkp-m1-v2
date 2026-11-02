"""Common-flight multi-observer experiments with explicit non-identifiability.

Synthetic only. No real RID capture or proof generation. A simulator event ID
is an oracle association, not a real receiver's ability to identify RF packets.
"""
import os
for _key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS']:
    os.environ[_key] = '1'
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import platform
import resource
import sys
import time
import numpy as np


def generate(cfg, seed, split):
    """One shared smooth 3D trajectory for all receivers in each flight."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, split, 517]))
    nf = cfg['calibration_flights'] if split == 0 else cfg['test_flights']
    ne = cfg['events_per_flight']
    u = np.linspace(0, 1, ne)[None, :]
    angle = rng.uniform(0, 2 * np.pi, (nf, 1))
    along = -180 + 360 * u
    cross = rng.uniform(-65, 65, (nf, 1)) + 15 * np.sin(2 * np.pi * u)
    xyz = np.stack([along * np.cos(angle) - cross * np.sin(angle),
                    along * np.sin(angle) + cross * np.cos(angle),
                    rng.uniform(20, 60, (nf, 1)) + 3 * np.sin(2 * np.pi * u)], axis=2)
    sites = np.asarray(cfg['observer_xyz_m'], dtype=float)
    dist = np.linalg.norm(xyz[:, :, None, :] - sites[None, None, :, :], axis=3)
    flight_power = cfg['reference_received_dbm'] + rng.normal(0, cfg['flight_power_sd_db'], (nf, 1))
    power = flight_power + rng.normal(0, cfg['per_event_power_sd_db'], (nf, ne))
    # Shared hardware residuals across splits, not freshly learned on test.
    bias = np.random.default_rng(np.random.SeedSequence([seed, 919])).normal(
        0, cfg['receiver_calibration_residual_sd_db'], len(sites))
    noise = rng.normal(size=dist.shape)
    keep = (dist <= cfg['coverage_distance_m']) & (rng.random(dist.shape) >= cfg['scan_drop_probability'])
    direction = rng.uniform(0, 2 * np.pi, (nf, 1))
    shift_direction = np.stack([np.cos(direction), np.sin(direction), np.zeros_like(direction)], axis=2)
    return dict(xyz=xyz, dist=dist, power=power, stable_power=np.broadcast_to(flight_power, power.shape),
                bias=bias, noise=noise, keep=keep, direction=shift_direction)


def rssi(data, cfg, sd, stable=False):
    p = data['stable_power'] if stable else data['power']
    return p[:, :, None] - 10 * cfg['path_loss_exponent'] * np.log10(data['dist']) + data['bias'] + sd * data['noise']


def claimed_distances(data, cfg, delta):
    points = data['xyz'] + delta * data['direction']
    return np.linalg.norm(points[:, :, None, :] - np.asarray(cfg['observer_xyz_m'])[None, None, :, :], axis=3)


def mask_for(data, mode, count=5):
    if mode == 'full':
        result = np.zeros_like(data['keep'])
        result[:, :, :count] = True
        return result
    if mode == 'partial':
        return data['keep'].copy()
    if mode == 'single':
        # At most one receiver hears each event, preserving an actual shared path.
        result = np.zeros_like(data['keep'])
        nearest = np.argmin(np.where(data['keep'], data['dist'], np.inf), axis=2)
        np.put_along_axis(result, nearest[:, :, None], True, axis=2)
        return result & np.any(data['keep'], axis=2)[:, :, None]
    raise ValueError(mode)


def profile_score(raw, distance, mask, b):
    """Project out one arbitrary common power per event; m<2 -> undefined."""
    m = mask.sum(axis=2)
    residual = raw + b * np.log10(distance)
    center = np.sum(np.where(mask, residual, 0), axis=2) / np.maximum(m, 1)
    variance = np.sum(np.where(mask, (residual - center[:, :, None])**2, 0), axis=2) / np.maximum(m, 1)
    score = np.sqrt(variance)
    score[m < 2] = np.nan
    pattern = np.sum(mask.astype(int) * (2 ** np.arange(mask.shape[2]))[None, None, :], axis=2)
    return score, pattern, m


def thresholds(cal_score, patterns, cfg):
    output = {}
    for p in np.unique(patterns):
        v = cal_score[(patterns == p) & np.isfinite(cal_score)]
        if len(v) >= cfg['minimum_calibration_events_per_subset']:
            output[int(p)] = float(np.quantile(v, 1 - cfg['normal_alarm_target']))
    return output


def decisions(score, pattern, table):
    threshold = np.full_like(score, np.nan)
    for p, q in table.items():
        threshold[pattern == p] = q
    usable = np.isfinite(score) & np.isfinite(threshold)
    return usable, usable & (score > threshold)


def metrics(score, pattern, table):
    usable, alarm = decisions(score, pattern, table)
    n, k = score.size, int(usable.sum())
    return dict(emitted_events=n, decidable_events=k, alarms=int(alarm.sum()),
        decision_fraction=k / n, abstain_fraction=1 - k / n,
        conditional_alarm_fraction=float(alarm.sum() / k) if k else None,
        all_event_alarm_fraction=float(alarm.mean()))


def counterexamples(cfg):
    sites = np.asarray([[100, 0, 0], [0, 100, 0], [-100, 0, 0], [0, -100, 0]], dtype=float)
    p = np.array([0, 0, 20.]); q = np.array([0, 0, 80.])
    d = np.linalg.norm(sites - p, axis=1); dc = np.linalg.norm(sites - q, axis=1)
    b = 10 * cfg['path_loss_exponent']; base_power = -42.
    # Truthful world at q vs attack world at p, both claim q.
    attack_power = base_power + b * np.log10(d[0] / dc[0])
    truthful = base_power - b * np.log10(dc)
    attack = attack_power - b * np.log10(d)
    err = float(np.max(np.abs(truthful - attack)))
    if err > 1e-10:
        raise AssertionError('geometric ambiguity construction failed')
    # Different frames: each receiver gets an independent freely chosen power.
    irregular = np.asarray(cfg['observer_xyz_m'])
    p2 = np.array([-30., 10., 30.]); q2 = np.array([60., -40., 50.])
    d2 = np.linalg.norm(irregular - p2, axis=1); dq2 = np.linalg.norm(irregular - q2, axis=1)
    null = base_power - b * np.log10(dq2)
    powers = base_power + b * np.log10(d2 / dq2)
    changed = powers - b * np.log10(d2)
    async_err = float(np.max(np.abs(null - changed)))
    if async_err > 1e-10:
        raise AssertionError('single receiver per event construction failed')
    return dict(circle=dict(observer_count=4, radius_m=100, true_height_m=20, claimed_height_m=80,
        attack_power_change_db=float(attack_power - base_power), max_rssi_difference_db=err,
        true_xyz=p.tolist(), claim_xyz=q.tolist(), observer_xyz=sites.tolist(),
        truthful_rssi_dbm=truthful.tolist(), attack_rssi_dbm=attack.tolist()),
        disjoint=dict(observer_count=5, max_rssi_difference_db=async_err,
            required_power_changes_db=(powers - base_power).tolist(),
            truthful_rssi_dbm=null.tolist(), attack_rssi_dbm=changed.tolist()))


def evaluate_seed(cfg, seed):
    cal, test = generate(cfg, seed, 0), generate(cfg, seed, 1)
    b = 10 * cfg['path_loss_exponent']
    cases, curves, pairing, uploads, calibration = [], [], [], [], []
    for sd in cfg['link_noise_sd_db']:
        cr, tr = rssi(cal, cfg, sd), rssi(test, cfg, sd)
        for mode in ['full', 'partial', 'single']:
            cm, tm = mask_for(cal, mode), mask_for(test, mode)
            cs, cp, _ = profile_score(cr, cal['dist'], cm, b)
            table = thresholds(cs, cp, cfg)
            for pattern, q in table.items():
                calibration.append(dict(seed=seed, noise_sd_db=sd, mode=mode, pattern=pattern,
                    sample_count=int(np.sum((cp == pattern) & np.isfinite(cs))), threshold_db=q))
            normal, tp, m = profile_score(tr, test['dist'], tm, b)
            for name, delta in [('normal', 0), ('power_plus16', 0), ('power_random16', 0),
                                ('position30', 30), ('position100', 100), ('joint100', 100)]:
                cd = claimed_distances(test, cfg, delta)
                observed = tr.copy()
                if name == 'power_plus16':
                    observed += 16
                elif name == 'power_random16':
                    rng = np.random.default_rng(np.random.SeedSequence([seed, 707]))
                    observed += rng.normal(0, 16, test['power'].shape)[:, :, None]
                elif name == 'joint100':
                    # Best common mean compensation on the observed subset.
                    shift = b * np.log10(test['dist'] / cd)
                    offset = np.sum(np.where(tm, shift, 0), axis=2) / np.maximum(m, 1)
                    observed += offset[:, :, None]
                score, pattern, _ = profile_score(observed, cd, tm, b)
                if name in ['power_plus16', 'power_random16']:
                    np.testing.assert_allclose(score, normal, atol=1e-10, equal_nan=True)
                cases.append(dict(seed=seed, noise_sd_db=sd, mode=mode, case=name,
                    overlapping_event_fraction=float(np.mean(m >= 2)),
                    received_event_fraction=float(np.mean(m >= 1)),
                    **metrics(score, pattern, table)))
            # Upload arrives later, but event identity/observation stays unchanged.
            if mode == 'full':
                nd, na = decisions(normal, tp, table)
                for delay in cfg['upload_spread_s']:
                    uploads.append(dict(seed=seed, noise_sd_db=sd, upload_spread_s=delay,
                        decision_wait_s=delay, decidable_events=int(nd.sum()), alarms=int(na.sum()),
                        score_difference_max_db=0.0))
        for count in [1, 2, 3, 5]:
            cm, tm = mask_for(cal, 'full', count), mask_for(test, 'full', count)
            cs, cp, _ = profile_score(cr, cal['dist'], cm, b)
            table = thresholds(cs, cp, cfg)
            for delta in cfg['claim_displacements_m']:
                cd = claimed_distances(test, cfg, delta)
                score, pattern, _ = profile_score(tr, cd, tm, b)
                curves.append(dict(seed=seed, noise_sd_db=sd, receivers=count, shift_m=delta,
                                   **metrics(score, pattern, table)))
        # Wrongly fuse different physical events as if they were one event.
        max_age = int(round(max(cfg['pairing_spread_s']) / cfg['event_spacing_s']))
        query = np.arange(max_age, cfg['events_per_flight'])
        for stability in ['stable', 'per_event_variable']:
            stable = stability == 'stable'
            c_raw, t_raw = rssi(cal, cfg, sd, stable), rssi(test, cfg, sd, stable)
            cs, cp, _ = profile_score(c_raw, cal['dist'], mask_for(cal, 'full'), b)
            table = thresholds(cs, cp, cfg)
            for spread in cfg['pairing_spread_s']:
                lags = np.rint(np.linspace(0, spread, t_raw.shape[2]) / cfg['event_spacing_s']).astype(int)
                mixed = np.stack([t_raw[:, query - lag, node] for node, lag in enumerate(lags)], axis=2)
                score, pattern, _ = profile_score(mixed, test['dist'][:, query], np.ones_like(mixed, dtype=bool), b)
                pairing.append(dict(seed=seed, noise_sd_db=sd, power_mode=stability,
                    maximum_pairing_age_s=spread, **metrics(score, pattern, table)))
    return dict(cases=cases, curves=curves, pairing=pairing, uploads=uploads, calibration=calibration)


KEYS = dict(cases=['noise_sd_db', 'mode', 'case'], curves=['noise_sd_db', 'receivers', 'shift_m'],
            pairing=['noise_sd_db', 'power_mode', 'maximum_pairing_age_s'],
            uploads=['noise_sd_db', 'upload_spread_s'])


def aggregate(rows, keys):
    groups = collections.defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in keys)].append(r)
    output = []
    for key, group in sorted(groups.items()):
        row = dict(zip(keys, key), seeds=len(group))
        for field in group[0]:
            if field in keys or field == 'seed':
                continue
            values = [r[field] for r in group if r[field] is not None]
            row[field] = float(np.mean(values)) if values else None
            if field in ['conditional_alarm_fraction', 'decision_fraction', 'all_event_alarm_fraction']:
                row[field + '_seed_min'] = min(values) if values else None
                row[field + '_seed_max'] = max(values) if values else None
        output.append(row)
    return output


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('event_scenarios_config.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    if args.out.exists() and any(args.out.iterdir()):
        raise ValueError('Existing output preserved; select a new directory')
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'config.json').write_text(json.dumps(cfg, indent=2) + '\n')
    started = time.perf_counter()
    result = {key: [] for key in [*KEYS, 'calibration']}
    for index, seed in enumerate(cfg['seeds']):
        (args.out / 'status.json').write_text(json.dumps(dict(status='running', completed_seeds=index, seed=seed)) + '\n')
        seed_result = evaluate_seed(cfg, seed)
        for study, rows in seed_result.items():
            result[study].extend(rows)
            write_csv(args.out / f'{study}-seed-metrics.csv', result[study])
        with (args.out / 'progress.jsonl').open('a') as f:
            f.write(json.dumps(dict(seed=seed, status='complete')) + '\n')
        print(f'Completed seed {seed} ({index + 1}/{len(cfg["seeds"])})', flush=True)
    summary = {key: aggregate(result[key], keys) for key, keys in KEYS.items()}
    for key, rows in summary.items():
        write_csv(args.out / f'{key}-summary.csv', rows)
    summary.update(dict(status='complete', config=cfg, counterexamples=counterexamples(cfg),
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        config_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest(),
        runtime=dict(python=platform.python_version(), platform=platform.platform(), numpy=np.__version__,
            wall_seconds=time.perf_counter() - started,
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)),
        interpretation='Alarm means model inconsistency, never cause attribution. A missing conditional rate is undefined, not zero.',
        weighting='Equal independent synthetic seed means; events within a flight are not independent trials.'))
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    (args.out / 'status.json').write_text(json.dumps(dict(status='complete', completed_seeds=len(cfg['seeds']))) + '\n')
    print(json.dumps(summary['runtime'], indent=2))


if __name__ == '__main__':
    main()
