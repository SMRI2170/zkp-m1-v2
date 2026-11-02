"""Independent reanalysis of public UAV-received LoRa measurements.

Not a Remote ID dataset, not a reproduction of GhostBuster. Coordinates and
per-packet measurements stay inside ignored captures/. Only aggregates leave.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import time
import urllib.request
import zipfile

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np

URL = 'https://zenodo.org/records/17339095/files/dataset.zip?download=1'
SHA256 = '29c9715ca39d297ac7f00142958dc959fa154c34d684d32adeebe5f97681cc84'
PUBLISHED_MD5 = 'c9156712c90c5eb8fc5939b2171c7ac6'
PAPER_COUNTS = {
    'T1.0': 16624, 'T2.1': 11458, 'T2.2': 8294, 'T3.1': 4846,
    'T3.2': 5793, 'T4.1': 9218, 'T4.2': 8304, 'T5.1': 3821,
    'T5.2': 2616, 'T6.1': 7188, 'T6.2': 4903, 'T7.1': 8118,
    'T7.2': 8125, 'T8.1': 8832, 'T8.2': 8803, 'T9.1': 4150,
    'T9.2': 4099, 'T10.1': 8424, 'T10.2': 8423,
}
HEADER = ['dateString', 'timestamp[ms]', 'rssi[dBm]', 'snr[dB]',
          'longitude', 'latitude', 'height[m]', 'altitude[m a.s.l.]',
          'speed[m/s]', 'depth[m]', 'runID']


def distance_proxy(lon, lat, height, depth, target_lon, target_lat):
    """Spherical horizontal separation + AGL height/depth; flat-terrain proxy."""
    phi, phi0 = np.deg2rad(lat), np.deg2rad(target_lat)
    dphi, dlambda = phi - phi0, np.deg2rad(lon - target_lon)
    a = np.sin(dphi / 2)**2 + np.cos(phi) * np.cos(phi0) * np.sin(dlambda / 2)**2
    horizontal = 6371008.8 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return np.hypot(horizontal, height + depth)


def download(raw):
    raw.mkdir(parents=True, exist_ok=True)
    raw.chmod(0o700)
    path = raw / 'dataset.zip'
    if not path.exists():
        data = urllib.request.urlopen(URL, timeout=60).read()
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise ValueError('download differs from pinned public dataset')
        # Never replace unexpected local artifacts.
        with path.open('xb') as f:
            f.write(data)
        path.chmod(0o600)
    return path


def load(path):
    if path.stat().st_mode & 0o077:
        raise ValueError('raw archive must have owner-only permissions')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError('public archive SHA-256 mismatch')
    if hashlib.md5(payload).hexdigest() != PUBLISHED_MD5:
        raise ValueError('published archive MD5 mismatch')
    groups, inventory, sources = {}, [], []
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        for name in sorted(n for n in z.namelist() if n.endswith('/data.csv')):
            condition = name.split('/')[1]
            data_bytes = z.read(name)
            reader = csv.DictReader(io.StringIO(data_bytes.decode('utf-8-sig')))
            if reader.fieldnames != HEADER:
                raise ValueError(f'unexpected columns: {condition}')
            rows = list(reader)
            if len(rows) != PAPER_COUNTS[condition]:
                raise ValueError(f'published row count mismatch: {condition}')
            target_name = f'dataset/{condition}/target_position.csv'
            target = list(csv.DictReader(io.StringIO(z.read(target_name).decode())))[0]
            data = np.asarray([[float(r[k]) for k in HEADER[1:]] for r in rows])
            if not np.all(np.isfinite(data)):
                raise ValueError(f'nonfinite data: {condition}')
            d = distance_proxy(data[:, 3], data[:, 4], data[:, 5], data[:, 8],
                               float(target['longitude']), float(target['latitude']))
            if np.any(d <= 0) or np.any(data[:, 5] < 0):
                raise ValueError('invalid geometric distance proxy')
            runs = data[:, 9].astype(int)
            if not np.array_equal(runs, data[:, 9]):
                raise ValueError('noninteger run ID')
            groups[condition] = {}
            for run in sorted(set(runs)):
                m = runs == run
                # Internal arrays only. No row-level or absolute-time export.
                t = data[m, 0] / 1000
                if np.any(np.diff(t) <= 0):
                    raise ValueError('run timestamps must strictly increase')
                groups[condition][int(run)] = dict(t=t, r=data[m, 1], d=d[m])
                inventory.append(dict(condition=condition, run=int(run), rows=int(m.sum()),
                    duration_span_s=float(t[-1] - t[0]),
                    median_interval_s=float(np.median(np.diff(t))),
                    gaps_over_2s=int(np.sum(np.diff(t) > 2)),
                    distance_proxy_min_m=float(d[m].min()), distance_proxy_max_m=float(d[m].max())))
            # Verify run timestamp sets do not overlap within a condition.
            seen = set()
            for run in groups[condition].values():
                stamps = set(run['t'])
                if seen.intersection(stamps):
                    raise ValueError('run timestamp overlap within condition')
                seen.update(stamps)
            for member in [name, target_name]:
                b = z.read(member)
                sources.append(dict(member=member, bytes=len(b), sha256=hashlib.sha256(b).hexdigest()))
    if set(groups) != set(PAPER_COUNTS) or sum(x['rows'] for x in inventory) != 142039:
        raise ValueError('unexpected public archive inventory')
    return groups, inventory, sources


def fit_model(run):
    x = np.column_stack([np.ones(len(run['d'])), np.log10(run['d'])])
    return np.linalg.lstsq(x, run['r'], rcond=None)[0]


def expected(model, d):
    return model[0] + model[1] * np.log10(d)


def range_estimate(model, r):
    if model[1] >= 0:
        return None
    # No clipping/truncation of errors to improve metrics.
    result = 10 ** ((r - model[0]) / model[1])
    if not np.all(np.isfinite(result)):
        raise ValueError('range inversion overflow; report rather than clip')
    return result


def blocks(run, k, keep=None):
    """Full nonoverlapping causal blocks, never across gaps exceeding 2 s."""
    indices = np.arange(len(run['t'])) if keep is None else np.flatnonzero(keep)
    if not len(indices):
        return {key: np.empty(0) for key in ('t', 'r', 'd', 'span')}
    cuts = np.r_[0, np.flatnonzero(np.diff(run['t'][indices]) > 2) + 1, len(indices)]
    ix = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        complete = (b - a) // k * k
        if complete:
            ix.append(indices[a:a + complete].reshape(-1, k))
    if not ix:
        return {key: np.empty(0) for key in ('t', 'r', 'd', 'span')}
    ix = np.concatenate(ix)
    return dict(t=run['t'][ix[:, -1]], r=np.median(run['r'][ix], axis=1),
                d=run['d'][ix[:, -1]], span=run['t'][ix[:, -1]] - run['t'][ix[:, 0]])


def scores(model, block, delta=0, compensate=False):
    r = block['r'].copy()
    if compensate:
        r += expected(model, block['d'] + delta) - expected(model, block['d'])
    return np.abs(r - expected(model, block['d'] + delta))


def error_metrics(model, b):
    estimate = range_estimate(model, b['r'])
    if estimate is None:
        return dict(mae_m=None, p95_error_m=None)
    e = np.abs(estimate - b['d'])
    return dict(mae_m=float(e.mean()), p95_error_m=float(np.quantile(e, .95)))


def delayed_pairs(run, delays=(0, 1, 5, 15)):
    """Same query cohort for all delays. Latest PAST packet, never interpolation."""
    ix = np.arange(len(run['t']))
    selections, valid = {}, np.ones(len(ix), dtype=bool)
    # A sample from an earlier segment must never bridge a long outage.
    segment = np.cumsum(np.r_[0, np.diff(run['t']) > 2])
    for delay in delays:
        prev = np.searchsorted(run['t'], run['t'] - delay, side='right') - 1
        safe = np.maximum(prev, 0)
        age = run['t'] - run['t'][safe]
        valid &= (prev >= 0) & (age <= delay + 2) & (segment[safe] == segment)
        selections[delay] = safe
    return {delay: (prev[valid], ix[valid]) for delay, prev in selections.items()}


def save_csv(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def summarize(rows, keys, metrics):
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[tuple(row[k] for k in keys)].append(row)
    result = []
    for key, group in sorted(grouped.items()):
        row = dict(zip(keys, key), folds=len(group))
        for metric in metrics:
            values = [r[metric] for r in group if r[metric] is not None]
            row[metric] = float(np.mean(values)) if values else None
        result.append(row)
    return result


def evaluate(groups, out):
    main, delay_rows, missing, models, dependencies = [], [], [], [], []
    folds = []
    for condition, runs in groups.items():
        if len(runs) != 3:
            continue  # Inventory retains these runs; cannot fit/calibrate/test disjointly.
        ids = sorted(runs)
        for j in range(3):
            train_id, cal_id, test_id = ids[j], ids[(j + 1) % 3], ids[(j + 2) % 3]
            train, cal, test = runs[train_id], runs[cal_id], runs[test_id]
            model = fit_model(train)
            base = dict(condition=condition, train_run=train_id, cal_run=cal_id, test_run=test_id)
            models.append(dict(**base, intercept_db=float(model[0]), slope_db_decade=float(model[1]),
                               pathloss_exponent=float(-model[1] / 10),
                               invertible_decreasing=bool(model[1] < 0)))
            folds.append(base)
            residual = test['r'] - expected(model, test['d'])
            close = np.diff(test['t']) <= 2
            corr = float(np.corrcoef(residual[:-1][close], residual[1:][close])[0, 1])
            dependencies.append(dict(**base, adjacent_pairs=int(close.sum()),
                                     residual_lag1_correlation=corr))
            for k in [1, 5, 20]:
                cb, tb = blocks(cal, k), blocks(test, k)
                threshold = float(np.quantile(scores(model, cb), .95))
                normal = scores(model, tb)
                em = error_metrics(model, tb)
                prior_mae = float(np.mean(np.abs(np.median(train['d']) - tb['d'])))
                for delta in [0, 10, 30, 100]:
                    for compensated in ([False] if delta == 0 else [False, True]):
                        sc = scores(model, tb, delta, compensated)
                        if compensated and not np.allclose(sc, normal, atol=1e-10):
                            raise AssertionError('compensation counterexample mismatch')
                        required = expected(model, tb['d'] + delta) - expected(model, tb['d'])
                        main.append(dict(**base, window_packets=k, radial_range_shift_m=delta,
                            compensated=compensated, n_cal=len(cb['r']), n_test=len(tb['r']),
                            threshold_db=threshold, alarm_fraction=float(np.mean(sc > threshold)),
                            normal_fpr=float(np.mean(normal > threshold)),
                            span_median_s=float(np.median(tb['span'])), **em,
                            prior_mae_m=prior_mae,
                            compensation_abs_median_db=float(np.median(np.abs(required))),
                            compensation_abs_p95_db=float(np.quantile(np.abs(required), .95))))
            threshold = float(np.quantile(scores(model, blocks(cal, 1)), .95))
            for lag, (past, query) in delayed_pairs(test).items():
                b = dict(r=test['r'][past], d=test['d'][query])
                delay_rows.append(dict(**base, requested_delay_s=lag, n_test=len(query),
                    actual_age_median_s=float(np.median(test['t'][query] - test['t'][past])),
                    normal_fpr=float(np.mean(np.abs(b['r'] - expected(model, b['d'])) > threshold)),
                    **error_metrics(model, b)))
            # Synthetic thinning of already RECEIVED packets. Not original RF loss rate.
            for seed in range(10):
                rng = np.random.default_rng(202611400 + seed)
                uc, ut = rng.random(len(cal['t'])), rng.random(len(test['t']))
                for drop in [0, .25, .5, .75]:
                    for k in [1, 5, 20]:
                        cb, tb = blocks(cal, k, uc >= drop), blocks(test, k, ut >= drop)
                        available = bool(len(cb['r']) and len(tb['r']))
                        q = float(np.quantile(scores(model, cb), .95)) if available else None
                        missing.append(dict(**base, seed=202611400 + seed, drop_fraction=drop,
                            window_packets=k, n_cal=len(cb['r']), n_test=len(tb['r']),
                            processed_original_packet_fraction=len(tb['r']) * k / len(test['r']),
                            evaluable_seed_fraction=float(available),
                            span_median_s=float(np.median(tb['span'])) if len(tb['r']) else None,
                            normal_fpr=float(np.mean(scores(model, tb) > q)) if available else None,
                            shifted100_alarm_fraction=float(np.mean(scores(model, tb, 100) > q)) if available else None))
            print(f'completed {condition}: fit {train_id}, calibrate {cal_id}, test {test_id}', flush=True)
    for name, rows in [('model-fits', models), ('window-fold-metrics', main),
                       ('delay-fold-metrics', delay_rows), ('dropout-fold-seed-metrics', missing),
                       ('residual-dependence', dependencies)]:
        save_csv(out / f'{name}.csv', rows)
    window_summary = summarize(main, ['window_packets', 'radial_range_shift_m', 'compensated'],
        ['alarm_fraction', 'normal_fpr', 'mae_m', 'p95_error_m', 'prior_mae_m', 'span_median_s',
         'compensation_abs_median_db', 'compensation_abs_p95_db'])
    delay_summary = summarize(delay_rows, ['requested_delay_s'],
        ['mae_m', 'p95_error_m', 'normal_fpr', 'actual_age_median_s'])
    # First average seeds WITHIN a fold. Fold summaries then have equal weight.
    dropout_fold = summarize(missing, ['condition', 'train_run', 'cal_run', 'test_run',
                                      'drop_fraction', 'window_packets'],
        ['processed_original_packet_fraction', 'span_median_s', 'normal_fpr', 'shifted100_alarm_fraction', 'evaluable_seed_fraction'])
    dropout_summary = summarize(dropout_fold, ['drop_fraction', 'window_packets'],
        ['processed_original_packet_fraction', 'span_median_s', 'normal_fpr', 'shifted100_alarm_fraction', 'evaluable_seed_fraction'])
    for name, rows in [('window-summary', window_summary), ('delay-summary', delay_summary),
                       ('dropout-summary', dropout_summary)]:
        save_csv(out / f'{name}.csv', rows)
    return dict(folds=folds, window=window_summary, delay=delay_summary, dropout=dropout_summary,
        nondecreasing_models=sum(not r['invertible_decreasing'] for r in models),
        residual_lag1_median=float(np.median([r['residual_lag1_correlation'] for r in dependencies])))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, default=Path('captures/week26-public-lora'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--download', action='store_true')
    args = p.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        raise ValueError('choose a new output directory; existing results are preserved')
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'status.json').write_text(json.dumps(dict(status='running')) + '\n')
    start = time.perf_counter()
    path = download(args.raw) if args.download else args.raw / 'dataset.zip'
    groups, inventory, sources = load(path)
    save_csv(args.out / 'inventory.csv', inventory)
    result = evaluate(groups, args.out)
    result.update(dict(status='complete', dataset_doi='10.5281/zenodo.17339095',
        dataset_url=URL, archive_sha256=SHA256, archive_md5=PUBLISHED_MD5,
        source_members=sources, total_rows=sum(x['rows'] for x in inventory),
        conditions=len(groups), run_groups=len(inventory),
        published_count_checks=19, python=platform.python_version(), numpy=np.__version__,
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        wall_seconds=time.perf_counter() - start,
        scope='Independent reanalysis; LoRa UAV receiver, buried fixed transmitter. Not RID or original paper model reproduction.',
        distance_label='flat-terrain slant-range proxy: hypot(haversine, AGL height + burial depth)',
        weighting='equal fold weight, then seed mean within fold for thinning; no independent-trial confidence claim',
        excluded_from_three_way_evaluation=[c for c, r in groups.items() if len(r) != 3]))
    (args.out / 'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    (args.out / 'status.json').write_text(json.dumps(dict(status='complete', folds=len(result['folds']))) + '\n')
    print(json.dumps({k: result[k] for k in ['status', 'total_rows', 'conditions', 'run_groups',
        'nondecreasing_models', 'residual_lag1_median', 'wall_seconds']}, indent=2))


if __name__ == '__main__':
    main()
