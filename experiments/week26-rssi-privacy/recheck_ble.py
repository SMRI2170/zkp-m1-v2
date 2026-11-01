"""Independent reconstruction of Week26 BLE analysis, not the missing ZIP code.

Only aggregate statistics leave ignored captures/. Standard library analysis;
plotting is optional. No UAV RF acquisition or ZKP generation is performed.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics as st
import subprocess
import sys
import time
import urllib.request

REPO = 'manwestc/ble-rssi-indoor-localization-dataset'
COMMIT = 'b38a9a4a53a01f52136f4e9b29b5045f61655a06'
FILES = {-8: 'Tx_8.csv', -4: 'Tx_4.csv', 0: 'Tx0.csv'}
HASHES = {
    'Tx_8.csv': 'bb578081c2002dcf49c71167f3f6143a943d85069c6b47d0c9c6b3dc1f7e0a26',
    'Tx_4.csv': '4a4cd6e0ec572646e51d2b2e9bed968f4e047e0d222fd2c62b027bd3f7f27ebd',
    'Tx0.csv': 'c964ba63925587081f657a83139562f6f60ad1c56a7ac34e3357bd8bbee2eae2',
}
BEACONS = [f'B{i}' for i in range(1, 7)]


def quantile(values, p):
    """Linear interpolation, equivalent to NumPy's default linear quantile."""
    values = sorted(values)
    if not values or not 0 <= p <= 1:
        raise ValueError('quantile needs data and probability in [0, 1]')
    idx = (len(values) - 1) * p
    lo = math.floor(idx)
    hi = math.ceil(idx)
    return values[lo] + (values[hi] - values[lo]) * (idx - lo)


def block_medians(values, window):
    """Nonoverlapping full blocks; a trailing partial block is excluded."""
    if window < 1:
        raise ValueError('window must be positive')
    return [st.median(values[i:i + window])
            for i in range(0, len(values) - window + 1, window)]


def download(raw):
    raw.mkdir(parents=True, exist_ok=True)
    os.chmod(raw, 0o700)
    for name in list(FILES.values()) + ['README.md']:
        url = f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/'
        url += ('data/' if name.endswith('.csv') else '') + name
        req = urllib.request.Request(url, headers={'User-Agent': 'week26-recheck'})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
        path = raw / name
        # Preserve unexpected local inputs rather than silently replacing them.
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f'local source differs from pinned commit: {path}')
        path.write_bytes(data)
        os.chmod(path, 0o600)


def load(raw):
    data = {}
    sources = []
    for power, name in FILES.items():
        path = raw / name
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != HASHES[name]:
            raise ValueError(f'source hash differs from pinned dataset: {name}')
        groups = collections.defaultdict(list)
        with path.open(newline='') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != BEACONS + ['Sector']:
                raise ValueError(f'unexpected header: {name}')
            rows = list(reader)
        for row in rows:
            sector = int(row['Sector'])
            for beacon in BEACONS:
                value = float(row[beacon])
                if not math.isfinite(value) or not -127 <= value <= 0:
                    raise ValueError(f'invalid RSSI: {name}')
                groups[(sector, beacon)].append(value)
        expected = {(s, b) for s in range(1, 29) for b in BEACONS}
        if set(groups) != expected or any(len(v) != 100 for v in groups.values()):
            raise ValueError(f'unexpected group sizes: {name}')
        data[power] = dict(groups)
        sources.append({'file': name, 'sha256': hashlib.sha256(payload).hexdigest(),
                        'bytes': len(payload), 'rows': len(rows),
                        'url': f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/data/{name}'})
    return data, sources


def detect(data):
    rows = []
    # First 50 baseline rows never enter normal calibration/evaluation scores.
    baseline = {key: st.median(v[:50]) for key, v in data[-8].items()}
    for window in [1, 5, 20]:
        scores = {}
        for power in FILES:
            scores[power] = {}
            for key, values in data[power].items():
                values = values[50:] if power == -8 else values
                scores[power][key] = [v - baseline[key] for v in block_medians(values, window)]
        for calibration_parity in [0, 1]:
            cal = {key for key in baseline if key[0] % 2 == calibration_parity}
            test = set(baseline) - cal
            assert not {k[0] for k in cal} & {k[0] for k in test}
            threshold = quantile([s for k in sorted(cal) for s in scores[-8][k]], .95)
            for power in FILES:
                values = [s for k in sorted(test) for s in scores[power][k]]
                hits = sum(s > threshold for s in values)
                rows.append({'window': window, 'calibration_sector_parity': calibration_parity,
                             'test_sector_parity': 1 - calibration_parity,
                             'nominal_tx_dbm': power, 'nominal_shift_db': power + 8,
                             'threshold_db': threshold, 'alarm_count': hits,
                             'decision_count': len(values), 'alarm_rate': hits / len(values),
                             'discarded_rows_per_group': (50 if power == -8 else 100) % window})
    summary = []
    for window in [1, 5, 20]:
        out = {'window': window}
        for power, label in [(-8, 'normal_fpr'), (-4, 'shift4_tpr'), (0, 'shift8_tpr')]:
            selected = [r for r in rows if r['window'] == window and r['nominal_tx_dbm'] == power]
            out[label] = sum(r['alarm_count'] for r in selected) / sum(r['decision_count'] for r in selected)
            out[label + '_decisions'] = sum(r['decision_count'] for r in selected)
            out[label + '_fold_min'] = min(r['alarm_rate'] for r in selected)
            out[label + '_fold_max'] = max(r['alarm_rate'] for r in selected)
        summary.append(out)
    return rows, summary


def paired_shifts(data, repetitions=3000):
    rng = random.Random(20261101)
    summaries = []
    for low, high in [(-8, -4), (-4, 0), (-8, 0)]:
        by_sector = {s: [st.median(data[high][s, b]) - st.median(data[low][s, b])
                         for b in BEACONS] for s in range(1, 29)}
        differences = [d for values in by_sector.values() for d in values]
        boot = []
        for _ in range(repetitions):
            sample = rng.choices(list(by_sector), k=28)
            boot.append(st.median([v for s in sample for v in by_sector[s]]))
        summaries.append({'low_tx_dbm': low, 'high_tx_dbm': high,
                          'nominal_shift_db': high - low, 'groups': len(differences),
                          'median_rssi_shift_db': st.median(differences),
                          'negative_shift_groups': sum(d < 0 for d in differences),
                          'zero_shift_groups': sum(d == 0 for d in differences),
                          'exploratory_sector_bootstrap_95pct_db': [quantile(boot, .025), quantile(boot, .975)]})
    return summaries


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plots(out, result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows = result['detection_summary']
    fig, ax = plt.subplots(figsize=(8.4, 5))
    for key, label, marker in [('normal_fpr', 'Normal false alarms', 'o'),
                                ('shift4_tpr', 'Nominal +4 dB setting', 's'),
                                ('shift8_tpr', 'Nominal +8 dB setting', '^')]:
        values = [r[key] * 100 for r in rows]
        ax.plot([1, 5, 20], values, marker=marker, label=label)
        for x, y in zip([1, 5, 20], values):
            ax.annotate(f'{y:.2f}%', (x, y), xytext=(-5 if x == 20 else 5, 6),
                        ha='right' if x == 20 else 'left', textcoords='offset points', fontsize=9)
    ax.axhline(5, color='gray', linestyle=':', linewidth=1)
    ax.set(xlabel='RSSI rows per nonoverlapping median', ylabel='Alarm rate (%)',
           title='Indoor BLE: sector-held-out RSSI change alarms', xticks=[1, 5, 20], ylim=(0, 75))
    ax.legend(); ax.grid(alpha=.2)
    fig.text(.5, .015, 'Known sector/beacon baseline; setting sessions are confounded. Not UAV or EIRP verification.',
             ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .045, 1, 1))
    for ext in ['png', 'svg']: fig.savefig(out / f'detection.{ext}', dpi=180)
    plt.close(fig)
    shifts = result['paired_setting_shifts']
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for i, r in enumerate(shifts):
        v = r['median_rssi_shift_db']; lo, hi = r['exploratory_sector_bootstrap_95pct_db']
        ax.bar(i - .16, r['nominal_shift_db'], width=.3, color='#A4B5C7', label='Nominal setting shift' if i == 0 else None)
        ax.bar(i + .16, v, width=.3, color='#2F64A1', label='Median measured RSSI shift' if i == 0 else None,
               yerr=[[v - lo], [hi - v]], capsize=4)
    ax.set(xticks=list(range(3)), xticklabels=['-8 to -4', '-4 to 0', '-8 to 0'],
           xlabel='Nominal TX setting (dBm)', ylabel='Shift (dB)', title='Nominal TX setting and observed RSSI shift')
    ax.legend();ax.grid(axis='y', alpha=.2)
    fig.text(.5, .015, 'Exploratory 28-sector bootstrap; session changes confound causal interpretation.', ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .045, 1, 1))
    for ext in ['png', 'svg']:fig.savefig(out / f'setting-shifts.{ext}', dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=Path('captures/week26-public-ble'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--plots', action='store_true')
    args = parser.parse_args()
    start = time.monotonic()
    if args.out.exists():
        parser.error('output directory already exists; use a new run directory')
    if args.download:download(args.raw)
    data, sources = load(args.raw)
    fold_rows, summary = detect(data)
    shifts = paired_shifts(data)
    residuals = [v - st.median(values) for groups in data.values() for values in groups.values() for v in values]
    expected = [(4.29, 14.36, 28.79), (4.82, 21.16, 41.04), (5.65, 33.57, 58.81)]
    agreement = []
    for row, reported in zip(summary, expected):
        for key, value in zip(['normal_fpr', 'shift4_tpr', 'shift8_tpr'], reported):
            recomputed = row[key] * 100
            agreement.append({'window': row['window'], 'metric': key, 'reported_percent': value,
                              'recomputed_percent': recomputed, 'matches_reported_two_decimals': round(recomputed, 2) == value})
    minimal = subprocess.run([sys.executable, str(Path(__file__).with_name('identifiability_minimal.py'))],
                             text=True, capture_output=True, timeout=10, check=True)
    result = {'scope': 'Independent reconstruction from documentation; public indoor BLE, not UAV RF',
              'source_commit': COMMIT, 'source_repository': 'https://github.com/' + REPO,
              'sources': sources, 'rssi_count': len(residuals),
              'method': {'normal_baseline_rows': [0, 50], 'normal_score_rows': [50, 100],
                         'calibration': 'even/odd sectors, swapped; 95th percentile of normal block scores',
                         'threshold': 'linear quantile; strictly greater than threshold',
                         'windows': [1, 5, 20], 'tail': 'discard incomplete block',
                         'row_order': 'source order; temporal independence is not established',
                         'pooling': 'micro-average over both test folds',
                         'bootstrap': '3000 paired sector-cluster resamples, seed 20261101; exploratory'},
              'group_residuals': {'absolute_median_db': st.median(map(abs, residuals)),
                                  'absolute_p90_db': quantile(list(map(abs, residuals)), .9),
                                  'absolute_p95_db': quantile(list(map(abs, residuals)), .95),
                                  'rms_db': math.sqrt(st.mean(v * v for v in residuals))},
              'detection_summary': summary, 'paired_setting_shifts': shifts,
              'reported_value_checks': agreement, 'minimal_counterexample_stdout': minimal.stdout,
              'runtime': {'platform': platform.platform(), 'python': sys.version,
                          'analysis_wall_seconds': time.monotonic() - start},
              'limitations': ['Fixed known sector/beacon baselines; not unknown-location inference',
                              'TX setting changes are confounded with measurement session',
                              'Frames/rows and beacons are not assumed independent trials',
                              'No outdoor UAV, Pi/Pixel acquisition, EIRP measurement, or ZKP',
                              'Original ZIP/CSV code was unavailable; this is a documented reconstruction']}
    args.out.mkdir(parents=True)
    (args.out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    write_csv(args.out / 'detection-folds.csv', fold_rows)
    write_csv(args.out / 'detection-summary.csv', summary)
    write_csv(args.out / 'reported-value-checks.csv', agreement)
    if args.plots:plots(args.out, result)
    print(json.dumps({'out': str(args.out), 'rssi_count': len(residuals),
                      'detection': summary, 'matched_reported_values': sum(r['matches_reported_two_decimals'] for r in agreement)}, indent=2))


if __name__ == '__main__':
    main()
