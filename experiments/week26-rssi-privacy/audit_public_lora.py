"""Check saved aggregates independently of the plotting code."""
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path


def audit(root):
    def read(name):
        with (root / name).open() as f:
            return list(csv.DictReader(f))

    s = json.loads((root / 'summary.json').read_text())
    inv = read('inventory.csv')
    fits = read('model-fits.csv')
    windows = read('window-fold-metrics.csv')
    delays = read('delay-fold-metrics.csv')
    drops = read('dropout-fold-seed-metrics.csv')
    checks = []
    assert len(inv) == 52 and sum(int(r['rows']) for r in inv) == 142039
    assert len({r['condition'] for r in inv}) == 19
    checks.append('19 public condition counts match paper; 142039 rows, 52 archive run groups')
    assert len(fits) == 48
    assert all(len({r['train_run'], r['cal_run'], r['test_run']}) == 3 for r in fits)
    assert len({(r['condition'], r['test_run']) for r in fits}) == 48
    checks.append('48 held-out folds; three distinct run IDs and one test use per eligible run')
    assert len(windows) == 48 * 3 * 7 and len(delays) == 48 * 4 and len(drops) == 48 * 10 * 4 * 3
    checks.append('window, delay and thinning row counts match design')
    for r in windows:
        assert int(r['n_cal']) > 0 and int(r['n_test']) > 0
        if r['compensated'] == 'True' or float(r['radial_range_shift_m']) == 0:
            assert math.isclose(float(r['alarm_fraction']), float(r['normal_fpr']), abs_tol=1e-12)
    checks.append('model-compensated and zero-displacement controls equal normal alarms')
    for summary in s['window']:
        rows = [r for r in windows if int(r['window_packets']) == summary['window_packets']
                and int(r['radial_range_shift_m']) == summary['radial_range_shift_m']
                and (r['compensated'] == 'True') == summary['compensated']]
        assert len(rows) == 48
        for key in ['alarm_fraction', 'normal_fpr', 'mae_m', 'prior_mae_m', 'span_median_s']:
            assert math.isclose(sum(float(r[key]) for r in rows) / 48, summary[key], abs_tol=1e-10)
    checks.append('window macro summaries independently recomputed from saved fold CSV')
    counts = collections.defaultdict(set)
    for r in delays:
        counts[(r['condition'], r['test_run'])].add(int(r['n_test']))
        assert float(r['actual_age_median_s']) >= float(r['requested_delay_s']) - 1e-9
    assert len(counts) == 48 and all(len(v) == 1 for v in counts.values())
    checks.append('delay cohorts have identical counts in each fold; realized age is not younger than requested')
    missing = 0
    for r in drops:
        available = bool(int(r['n_cal']) and int(r['n_test']))
        assert float(r['evaluable_seed_fraction']) == float(available)
        if not available:
            missing += 1
            assert r['normal_fpr'] == '' and r['shifted100_alarm_fraction'] == ''
        assert 0 <= float(r['processed_original_packet_fraction']) <= 1
    checks.append(f'thinning retains unavailable cases explicitly: {missing}; no empty-cohort zero-error claims')
    source = Path(__file__).with_name('recheck_lora.py')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == s['runner_sha256']
    checks.append('saved execution matches current runner source hash')
    assert s['status'] == 'complete' and json.loads((root / 'status.json').read_text())['folds'] == 48
    checks.append('run completed all 48 folds')
    result = dict(status='passed', checks=checks)
    (root / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('result', type=Path)
    audit(p.parse_args().result)
