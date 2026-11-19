#!/usr/bin/env python3
"""Analyze legacy RID claims offline; trajectories remain private, never field truth."""
import argparse
import csv
import json
import math
import os
import statistics
from pathlib import Path

from analyze_b_snapshot import percentile, utc


def deduplicate(rows):
    seen, kept = set(), []
    for item in rows:
        r = item['capture']
        m = r['monotonic_time_us'] / 1e6
        origin = round((utc(r['received_at_utc']) - m) / 60) * 60
        key = (origin, r.get('bssid'), r.get('frequency_mhz'),
               r['monotonic_time_us'], r.get('vendor_content_digest'))
        if key not in seen:
            seen.add(key)
            kept.append(dict(item, origin=origin, mono=m))
    return sorted(kept, key=lambda x: (x['origin'], x['mono']))


def split_segments(rows, gap_s=60):
    groups = []
    for row in rows:
        if (not groups or row['origin'] != groups[-1][-1]['origin'] or
                row['mono'] - groups[-1][-1]['mono'] > gap_s):
            groups.append([])
        groups[-1].append(row)
    return groups


def segment_stats(rows, label):
    rssi = [x['capture']['rssi_dbm'] for x in rows]
    intervals = [b['mono'] - a['mono'] for a, b in zip(rows, rows[1:])
                 if b['mono'] > a['mono']]
    return dict(segment=label, rows=len(rows), duration_s=rows[-1]['mono']-rows[0]['mono'],
                rssi_min_dbm=min(rssi), rssi_median_dbm=statistics.median(rssi),
                rssi_max_dbm=max(rssi), interval_median_s=statistics.median(intervals) if intervals else None,
                interval_p95_s=percentile(intervals, .95),
                distinct_claimed_positions=len({(x['reference']['claimed_latitude'],
                                                 x['reference']['claimed_longitude']) for x in rows}),
                distinct_payloads=len({x['capture']['odid_payload_hex'] for x in rows}))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--private-output', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--figures', type=Path, required=True)
    a = p.parse_args()
    private_root = Path(__file__).resolve().parents[2] / 'captures'
    if not a.private_output.resolve().is_relative_to(private_root):
        raise ValueError('Trajectory outputs must remain in ignored captures/')
    os.umask(0o077)
    for d in [a.private_output, a.output, a.figures]:
        d.mkdir(parents=True, exist_ok=True)
    raw = [json.loads(line) for line in a.input.open()]
    rows = deduplicate(raw)
    groups = split_segments(rows)
    stats = [segment_stats(g, f'S{i+1}') for i, g in enumerate(groups)]
    gaps = [b['mono']-x['mono'] for x, b in zip(rows, rows[1:])
            if x['origin'] == b['origin'] and b['mono']-x['mono'] > 60]
    summary = dict(raw_rows=len(raw), exact_duplicate_rows=len(raw)-len(rows),
                   retained_rows=len(rows), segmentation_gap_s=60,
                   segments=stats, gaps_over_60_s=gaps,
                   claimed_position_count=len({(x['reference']['claimed_latitude'], x['reference']['claimed_longitude']) for x in rows}),
                   distinct_payloads=len({x['capture']['odid_payload_hex'] for x in rows}),
                   height_reference_values=sorted({x['reference']['height_type'] for x in rows}),
                   receiver_position_present=sum(x['capture'].get('receiver_position') is not None for x in rows),
                   identity_verified=False, field_date_verified=False,
                   physical_position_verified=False, packet_delivery_rate_available=False)
    (a.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    with (a.output/'segments.csv').open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(stats[0])); w.writeheader(); w.writerows(stats)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font=FontProperties(fname='/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc')
    plt.rcParams.update({'font.family':font.get_name(), 'axes.unicode_minus':False})
    fig, axes=plt.subplots(len(groups), 1, figsize=(11, max(3, 2.8*len(groups))), squeeze=False)
    for ax,g,s in zip(axes[:,0],groups,stats):
        t=[(x['mono']-g[0]['mono'])/60 for x in g]
        ax.plot(t,[x['capture']['rssi_dbm'] for x in g], '.-', lw=.5, ms=3)
        ax.set(title=f"{s['segment']}: {len(g)}行・空白60秒以下で区分（飛行回数ではない）",
               xlabel='この区間の最初の観測からの経過時間 [分]', ylabel='実測RSSI [dBm]', ylim=(-90,-35))
        ax.grid(alpha=.2)
    fig.suptitle('未登録送信元：記録空白の前後を分けた受信強度')
    fig.tight_layout()
    fig.savefig(a.figures/'01_candidate_rssi_segments.png', dpi=170)
    plt.close(fig)
    # Exact coordinates and all claimed heights stay in private artifacts only.
    first=rows[0]['reference']; lat0=first['claimed_latitude']; lon0=first['claimed_longitude']
    private=[]
    for i,g in enumerate(groups):
        for x in g:
            d=x['reference']
            private.append(dict(segment=f'S{i+1}', elapsed_s=x['mono']-g[0]['mono'],
                latitude=d['claimed_latitude'], longitude=d['claimed_longitude'],
                east_m=math.radians(d['claimed_longitude']-lon0)*6371000*math.cos(math.radians(lat0)),
                north_m=math.radians(d['claimed_latitude']-lat0)*6371000,
                claimed_height_m=d['claimed_height_m'], claimed_altitude_geo_m=d['claimed_altitude_geo_m'],
                rssi_dbm=x['capture']['rssi_dbm']))
    with (a.private_output/'claimed_track.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(private[0])); w.writeheader(); w.writerows(private)
    fig,axes=plt.subplots(1,3,figsize=(15,4.8))
    for i,g in enumerate(groups):
        ps=[x for x in private if x['segment']==f'S{i+1}']
        axes[0].plot([x['east_m'] for x in ps],[x['north_m'] for x in ps],'.-',lw=.5,label=f'S{i+1}')
        axes[1].plot([x['elapsed_s']/60 for x in ps],[x['claimed_height_m'] for x in ps],'.-',lw=.5,label=f'S{i+1}')
        axes[2].plot([x['elapsed_s']/60 for x in ps],[x['claimed_altitude_geo_m'] for x in ps],'.-',lw=.5,label=f'S{i+1}')
    axes[0].set(xlabel='東方向：最初の申告点から [m]',ylabel='北方向 [m]',title='申告軌跡（真位置ではない）',aspect='equal')
    axes[1].set(xlabel='区間内経過 [分]',ylabel='申告Height [m]',title='Height：基準種別はsummaryを参照')
    axes[2].set(xlabel='区間内経過 [分]',ylabel='申告Geo高度 [m]',title='Geo高度：地上高ではない')
    for ax in axes: ax.legend(); ax.grid(alpha=.2)
    fig.suptitle('非公開：Remote ID申告値の可視化・機体認証／実位置検証なし')
    fig.tight_layout(); fig.savefig(a.private_output/'claimed_track_and_height.png',dpi=170); plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
