#!/usr/bin/env python3
"""Audit operator-identified RID claims. Neither ID nor coordinates enter public outputs."""
import argparse
import collections
import csv
import itertools
import json
import math
import os
import statistics
from pathlib import Path

from analyze_b_snapshot import percentile, utc


def horizontal_distance(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    v = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2
    return 2*6371000*math.asin(math.sqrt(min(1, max(0, v))))


def stats(values):
    values = [x for x in values if isinstance(x, (int, float)) and math.isfinite(x)]
    return dict(n=len(values), min=min(values), median=statistics.median(values),
                p95=percentile(values, .95), max=max(values)) if values else dict(n=0)


def payload_overlap(a, b):
    return len({x['capture']['odid_payload_hex'] for x in a} &
               {x['capture']['odid_payload_hex'] for x in b})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--claimed-id', required=True)
    p.add_argument('--source', action='append', required=True, help='anonymous-label=private decoded JSONL')
    p.add_argument('--private-output', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    private_root = Path(__file__).resolve().parents[2]/'captures'
    if not a.private_output.resolve().is_relative_to(private_root):
        raise ValueError('Private trajectory outputs must stay in captures/')
    os.umask(0o077)
    for directory in [a.private_output, a.output]:directory.mkdir(parents=True, exist_ok=True)
    sources = {}
    for arg in a.source:
        label, path = arg.split('=', 1)
        if label in sources:raise ValueError('duplicate source label')
        selected = []
        for line in Path(path).open():
            x = json.loads(line); d = x['reference']
            if (d.get('reference_decode_ok') and
                    bytes.fromhex(d['id_hex']).rstrip(b'\0').decode(errors='replace') == a.claimed_id):
                selected.append(x)
        sources[label] = selected
    summary = dict(operator_confirmed_aircraft_id=True, cryptographic_identity_verified=False,
                   true_position_independently_verified=False, field_date_alignment_verified=False,
                   sources={}, pairwise_payload_overlap={})
    private_rows = []
    for label, rows in sources.items():
        seen, unique = set(), []
        for x in rows:
            r = x['capture']; m = r.get('monotonic_time_us')
            t = r.get('received_at_utc')
            origin = round((utc(t)-m/1e6)/60)*60 if t and m is not None else None
            key = (origin, r.get('boot_scope'), r.get('bssid'), r.get('frequency_mhz'), m,
                   r.get('vendor_content_digest'), r.get('odid_payload_hex'))
            if key not in seen:seen.add(key);unique.append(x)
        positions, accuracies, deltas, offsets, rssis = [], [], [], [], []
        for x in unique:
            r, d = x['capture'], x['reference']; fix = r.get('receiver_position') or {}
            dist = None
            if (d.get('location_valid') and fix.get('latitude') is not None and
                    fix.get('longitude') is not None and fix.get('match_status') == 'MATCHED'):
                dist = horizontal_distance(fix['latitude'], fix['longitude'], d['claimed_latitude'], d['claimed_longitude'])
                positions.append(dist);accuracies.append(fix.get('accuracy_m'))
                delta = fix.get('scan_delta_us')
                if delta is not None:deltas.append(abs(delta)/1e6)
            # Hour-ambiguous difference; never turn into a calendar/clock correction.
            if r.get('received_at_utc') and d.get('claimed_seconds_within_hour') is not None:
                offset = ((utc(r['received_at_utc'])-d['claimed_seconds_within_hour']+1800)%3600)-1800
                offsets.append(offset)
            rssis.append(r.get('rssi_dbm'))
            private_rows.append(dict(source=label, received_at_utc=r.get('received_at_utc'),
                monotonic_time_us=r.get('monotonic_time_us'), rssi_dbm=r.get('rssi_dbm'),
                claimed_latitude=d.get('claimed_latitude'), claimed_longitude=d.get('claimed_longitude'),
                claimed_height_m=d.get('claimed_height_m'), claimed_altitude_geo_m=d.get('claimed_altitude_geo_m'),
                receiver_latitude=fix.get('latitude'), receiver_longitude=fix.get('longitude'),
                receiver_accuracy_m=fix.get('accuracy_m'), horizontal_claim_distance_m=dist))
        item=dict(raw_rows=len(rows), deduplicated_rows=len(unique),
                  distinct_payloads=len({x['capture']['odid_payload_hex'] for x in rows}),
                  exact_duplicate_rows=len(rows)-len(unique), rssi_dbm=stats(rssis),
                  matched_receiver_position_rows=len(positions),
                  receiver_accuracy_m=stats(accuracies), receiver_fix_delta_s=stats(deltas),
                  hour_ambiguous_receive_minus_rid_s=stats(offsets),
                  cache_stale_rows=sum(bool(x['capture'].get('cache_stale')) for x in unique))
        summary['sources'][label]=item
    for (la,ra),(lb,rb) in itertools.combinations(sources.items(),2):
        summary['pairwise_payload_overlap'][la+' / '+lb]=payload_overlap(ra,rb)
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (a.private_output/'confirmed-drone-records.csv').open('w',newline='') as f:
        if private_rows:
            w=csv.DictWriter(f,fieldnames=list(private_rows[0]));w.writeheader();w.writerows(private_rows)
    (a.private_output/'operator-identification-private.json').write_text(json.dumps(
        {'claimed_id':a.claimed_id, 'basis':'user explicitly identified ID as actual experiment drone',
         'hardware_or_cryptographic_authentication':False},indent=2)+'\n')
    # Distance statistics stay alongside the real location records, not in Git.
    private_summary={label:stats([x['horizontal_claim_distance_m'] for x in private_rows if x['source']==label]) for label in sources}
    (a.private_output/'distance-summary-private.json').write_text(json.dumps(private_summary,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    labels=list(sources);xx=list(range(len(labels)))
    fig,ax=plt.subplots(figsize=(9,4.5))
    ax.bar([i-.2 for i in xx],[summary['sources'][k]['raw_rows'] for k in labels],.4,label='Saved rows')
    ax.bar([i+.2 for i in xx],[summary['sources'][k]['distinct_payloads'] for k in labels],.4,label='Distinct Message Pack contents')
    ax.set(xticks=xx,xticklabels=labels,ylabel='Count (not physical packet count)',title='Operator-identified drone: saved observations vs distinct contents')
    ax.legend();ax.grid(axis='y',alpha=.2);fig.tight_layout();fig.savefig(a.output/'observation_counts.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4.5))
    for label in sources:
        ps=[x for x in private_rows if x['source']==label and x['horizontal_claim_distance_m'] is not None]
        if ps:ax.scatter([x['horizontal_claim_distance_m'] for x in ps],[x['rssi_dbm'] for x in ps],s=12,alpha=.6,label=label)
    ax.set(xlabel='Receiver GPS to claimed drone position: horizontal distance [m]',ylabel='Measured RSSI [dBm]',title='PRIVATE: claimed distance vs RSSI (not independent flight truth)')
    ax.grid(alpha=.2);ax.legend();fig.tight_layout();fig.savefig(a.private_output/'claimed_distance_vs_rssi.png',dpi=170);plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
