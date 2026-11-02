"""Audit saved denominators, negative controls and source/config provenance."""
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path


def main():
    p = argparse.ArgumentParser(); p.add_argument('result', type=Path)
    root = p.parse_args().result
    s = json.loads((root / 'summary.json').read_text()); cfg = s['config']
    def read(study):
        with (root / f'{study}-seed-metrics.csv').open() as f:
            return list(csv.DictReader(f))
    cases, curves, pairing, uploads = [read(k) for k in ['cases', 'curves', 'pairing', 'uploads']]
    checks = []
    ns = len(cfg['seeds'])
    assert [len(cases), len(curves), len(pairing), len(uploads)] == [ns * 36, ns * 40, ns * 20, ns * 6]
    checks.append('All 10 seeds, 2 noise settings and declared scenario combinations saved')
    for rows in [cases, curves, pairing]:
        for r in rows:
            n, k, alarms = [int(r[t]) for t in ['emitted_events', 'decidable_events', 'alarms']]
            assert 0 <= alarms <= k <= n
            assert math.isclose(float(r['decision_fraction']), k / n, abs_tol=1e-12)
            assert math.isclose(float(r['abstain_fraction']), 1 - k / n, abs_tol=1e-12)
            assert math.isclose(float(r['all_event_alarm_fraction']), alarms / n, abs_tol=1e-12)
            assert (r['conditional_alarm_fraction'] == '') == (k == 0)
            if k:
                assert math.isclose(float(r['conditional_alarm_fraction']), alarms / k, abs_tol=1e-12)
    checks.append('All emitted/decidable/alarm denominators and undefined rates valid')
    grouped = collections.defaultdict(dict)
    for r in cases:
        grouped[(r['seed'], r['noise_sd_db'], r['mode'])][r['case']] = r
    assert len(grouped) == ns * 6
    for rows in grouped.values():
        assert len({r['decidable_events'] for r in rows.values()}) == 1
        for name in ['power_plus16', 'power_random16']:
            assert rows['normal']['alarms'] == rows[name]['alarms']
        assert rows['position100']['alarms'] == rows['joint100']['alarms']
    checks.append('Common power changes leave normal decisions unchanged; joint and position-only scores give identical alarms')
    assert all(int(r['decidable_events']) == 0 and r['conditional_alarm_fraction'] == ''
               for r in cases if r['mode'] == 'single')
    checks.append('Single-observer events explicitly abstain rather than claim zero detection or perfect accuracy')
    assert all(int(r['decidable_events']) == int(r['emitted_events']) for r in cases if r['mode'] == 'full')
    checks.append('Full-overlap scenario evaluates all emitted events')
    up = collections.defaultdict(list)
    for r in uploads:
        up[(r['seed'], r['noise_sd_db'])].append(r)
        assert float(r['decision_wait_s']) == float(r['upload_spread_s'])
    assert all(len(v) == 3 and len({r['alarms'] for r in v}) == 1 for v in up.values())
    checks.append('Oracle same-event delayed submissions preserve decisions while increasing wait')
    cohort = collections.defaultdict(set)
    for r in pairing:
        cohort[(r['seed'], r['noise_sd_db'], r['power_mode'])].add(int(r['emitted_events']))
    assert all(len(v) == 1 for v in cohort.values())
    checks.append('Mispairing spreads use the same query event cohort in each seed/condition')
    for kind in ['circle', 'disjoint']:
        c = s['counterexamples'][kind]
        difference = max(abs(a - b) for a, b in zip(c['truthful_rssi_dbm'], c['attack_rssi_dbm']))
        assert difference < 1e-10
        assert math.isclose(difference, c['max_rssi_difference_db'], abs_tol=1e-12)
    checks.append('Both constructed truthful/attack worlds produce indistinguishable RSSI vectors')
    from event_scenarios import KEYS
    for name, keys in KEYS.items():
        source = read(name)
        for target in s[name]:
            rows = [r for r in source if all(str(r[k]) == str(target[k]) for k in keys)]
            # CSV integers and JSON numeric categories have matching lexical form.
            assert len(rows) == ns
            for field in ['conditional_alarm_fraction', 'decision_fraction', 'all_event_alarm_fraction']:
                if field not in target:
                    continue
                values = [float(r[field]) for r in rows if r[field] != '']
                assert (target[field] is None) == (not values)
                if values:
                    assert math.isclose(sum(values) / len(values), target[field], abs_tol=1e-12)
    checks.append('Aggregate rates independently recomputed from saved seed CSV')
    here = Path(__file__).parent
    assert hashlib.sha256((here / 'event_scenarios.py').read_bytes()).hexdigest() == s['runner_sha256']
    assert hashlib.sha256((here / 'event_scenarios_config.json').read_bytes()).hexdigest() == s['config_sha256']
    assert json.loads((root / 'status.json').read_text()) == dict(status='complete', completed_seeds=ns)
    checks.append('Source/config hashes and completed status match execution')
    result = dict(status='passed', checks=checks)
    (root / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
