#!/usr/bin/env python3
"""Private capture -> identifier-free CSV/JSON/SVG; no claim that rows are RF packets."""
import argparse
import csv
import json
import statistics
from html import escape
from pathlib import Path


def read_jsonl(path):
    rows = []
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid or incomplete JSONL at line {number}") from exc
    return rows


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    x = (len(values)-1)*q
    a = int(x)
    return values[a] + (values[min(a+1, len(values)-1)]-values[a])*(x-a)


def analyze(observations, events, phases):
    result = []
    for phase in phases:
        lo, hi = phase['start_us'], phase['end_us']
        if hi < lo:raise ValueError('phase ends before it starts')
        rows = [r for r in observations if r.get('monotonic_time_us') is not None and lo <= r['monotonic_time_us'] < hi]
        fresh = [r for r in rows if not r.get('cache_stale', True) and r.get('rid_parse_status') == 'decoded']
        # Never measure an update interval between different transmitters.
        grouped = {}
        for r in fresh:
            grouped.setdefault((r.get('bssid'), r.get('frequency_mhz')), set()).add(r['monotonic_time_us'])
        intervals, max_silence = [], []
        for times in grouped.values():
            t = sorted(times)
            intervals += [(b-a)/1e6 for a, b in zip(t, t[1:])]
            max_silence.append(max([t[0]-lo, hi-t[-1]] + [b-a for a, b in zip(t, t[1:])])/1e6)
        ev = [e for e in events if lo <= e.get('elapsed_us', -1) < hi]
        samples = [e['pss_kib'] for e in ev if e.get('pss_kib') is not None]
        def delta(field):
            vals = [e[field] for e in ev if e.get(field) is not None]
            return vals[-1]-vals[0] if len(vals)>1 else None
        duration = (hi-lo)/1e6
        result.append(dict(phase=phase['name'], phase_complete=phase.get('finished',False), duration_s=duration,
            scan_observations=len(rows), fresh_decoded_observations=len(fresh),
            stale_observations=sum(bool(r.get('cache_stale')) for r in rows),
            invalid_observations=sum(r.get('rid_parse_status') != 'decoded' for r in rows),
            update_interval_median_s=statistics.median(intervals) if intervals else None,
            update_interval_p95_s=percentile(intervals, .95),
            max_edge_inclusive_gap_s=max(max_silence) if max_silence else duration,
            interval_pairs=len(intervals), pss_max_kib=max(samples) if samples else None,
            pss_samples=len(samples), duplicates_counter_delta=delta('duplicate_results'),
            requests_rejected_counter_delta=delta('requests_rejected'),
            process_cpu_ms_delta=delta('process_cpu_ms'),
            cpu_counter_coverage='between_first_and_last_telemetry_only',
            battery_level_first=next((e.get('battery_level') for e in ev if e.get('battery_level') is not None), None),
            battery_level_last=next((e.get('battery_level') for e in reversed(ev) if e.get('battery_level') is not None), None),
            battery_plugged_values=sorted({e['battery_plugged'] for e in ev if e.get('battery_plugged') is not None})))
    return result


def svg_bars(rows, field, title, units):
    values = [r[field] for r in rows]
    high = max([v for v in values if v is not None] + [1])
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="880" height="420" viewBox="0 0 880 420"><rect width="880" height="420" fill="white"/><g font-family="sans-serif" fill="#102749"><text x="30" y="32" font-size="20">{title}</text><text x="30" y="57">Y: {units} / X: observation phase</text>']
    for k, r in enumerate(rows):
        v = r[field]; x = 100+k*240
        h = 250*v/high if v is not None else 0
        parts += [f'<rect x="{x}" y="{330-h}" width="130" height="{h}" fill="#1d4ed8"/>',
            f'<text x="{x}" y="{max(80,320-h)}">{round(v,2) if v is not None else "not measured"}</text>',
            f'<text x="{x}" y="360">{escape(r["phase"])}</text>']
    return ''.join(parts)+'</g></svg>\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    obs = read_jsonl(args.capture/'observations.jsonl')
    ev = read_jsonl(args.capture/'events.jsonl')
    plan = json.loads((args.capture/'phases.json').read_text())
    rows = analyze(obs, ev, plan['phases'])
    args.output.mkdir(parents=True, exist_ok=False)
    # No IDs/coordinates, absolute times, serials, raw paths or payloads in these artifacts.
    report = {'kind':'observational_scan_capture_analysis', 'source_type':plan['source_type'],
        'physical_packet_match':'unconfirmed', 'source_kind':plan.get('source_kind','unknown'),
        'debug_scan_throttle_disabled':plan.get('debug_scan_throttle_disabled'), 'phases':rows,
        'session_end_reasons':[e.get('reason') for e in ev if e.get('event')=='session_end'],
        'session_complete':any(e.get('event')=='session_end' for e in ev),
        'notes':['No known packet count: no RF packet reception rate calculated.',
                 'Intervals pooled within each transmitter; no intervals across transmitters.',
                 'Counter deltas cover first through last telemetry in phase, not all phase boundaries.',
                 'Phase assignment uses device observation timestamps; cached observations from before phase excluded.']}
    (args.output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    with (args.output/'summary.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['phase'], lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    for field, title, unit in [('fresh_decoded_observations','Fresh decoded scan observations','observations'),
                              ('update_interval_median_s','Within-transmitter update interval (median)','seconds'),
                              ('update_interval_p95_s','Within-transmitter update interval (p95)','seconds'),
                              ('max_edge_inclusive_gap_s','Largest per-transmitter gap including phase edges','seconds'),
                              ('pss_max_kib','Maximum sampled process PSS','KiB')]:
        plot=svg_bars(rows, field, title, unit)
        if plan.get('debug_scan_throttle_disabled') is True:
            plot=plot.replace('</g></svg>', '<text x="30" y="399" font-size="12">Developer test: scan throttling OFF; compare under the recorded source and duration only.</text></g></svg>')
        (args.output/(field+'.svg')).write_text(plot)
    print('Analysis completed; identifier-free summaries created. No new RF experiment was run.')

if __name__ == '__main__':
    main()
