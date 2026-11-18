#!/usr/bin/env python3
"""Private WGS84 3D replay of received RID claims. No RSSI multilateration."""
import argparse
import csv
import json
import math
import os
from pathlib import Path

from analyze_b_candidate import deduplicate, split_segments


def ecef(latitude, longitude, altitude):
    lat, lon = math.radians(latitude), math.radians(longitude)
    e2 = 6.6943799901413165e-3
    n = 6378137 / math.sqrt(1-e2*math.sin(lat)**2)
    return ((n+altitude)*math.cos(lat)*math.cos(lon),
            (n+altitude)*math.cos(lat)*math.sin(lon),
            (n*(1-e2)+altitude)*math.sin(lat))


def enu(latitude, longitude, altitude, reference):
    p, q = ecef(latitude, longitude, altitude), ecef(*reference)
    x, y, z = (a-b for a,b in zip(p,q))
    lat, lon = math.radians(reference[0]), math.radians(reference[1])
    east = -math.sin(lon)*x+math.cos(lon)*y
    north = -math.sin(lat)*math.cos(lon)*x-math.sin(lat)*math.sin(lon)*y+math.cos(lat)*z
    up = math.cos(lat)*math.cos(lon)*x+math.cos(lat)*math.sin(lon)*y+math.sin(lat)*z
    return east, north, up


def valid_location(d):
    vals = [d.get('claimed_latitude'), d.get('claimed_longitude'), d.get('claimed_altitude_geo_m')]
    return (d.get('location_valid', False) and all(isinstance(x,(int,float)) and math.isfinite(x) for x in vals)
            and -90 <= vals[0] <= 90 and -180 <= vals[1] <= 180 and vals[2] > -1000)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--claimed-id', required=True)
    p.add_argument('--source', action='append', required=True, help='label=reference decoded JSONL')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]/'captures'
    if not a.output.resolve().is_relative_to(root):raise ValueError('Real trajectories must remain inside ignored captures/')
    os.umask(0o077); a.output.mkdir(parents=True, exist_ok=True)
    sources = {}
    for spec in a.source:
        label, file = spec.split('=',1)
        if label in sources:raise ValueError('duplicate source label')
        selected = []
        for line in Path(file).open():
            row = json.loads(line);d = row['reference']
            if (d.get('reference_decode_ok') and valid_location(d) and
                    bytes.fromhex(d['id_hex']).rstrip(b'\0').decode(errors='replace') == a.claimed_id):selected.append(row)
        sources[label] = deduplicate(selected)
    if not sources.get('B'):raise ValueError('B trajectory is required as the spatial reference and replay source')
    first=sources['B'][0]['reference']
    reference=(first['claimed_latitude'], first['claimed_longitude'], first['claimed_altitude_geo_m'])
    records,segments=[],[]
    for label,rows in sources.items():
        for i,g in enumerate(split_segments(rows),1):
            segment=f'{label}-S{i}'; points=[]
            for row in g:
                d,r=row['reference'],row['capture']
                east,north,up=enu(d['claimed_latitude'],d['claimed_longitude'],d['claimed_altitude_geo_m'],reference)
                point=dict(source=label,segment=segment,monotonic_s=row['mono'],
                    elapsed_s=row['mono']-rows[0]['mono'], elapsed_in_segment_s=row['mono']-g[0]['mono'],
                    latitude=d['claimed_latitude'],longitude=d['claimed_longitude'],east_m=east,north_m=north,up_m=up,
                    geo_altitude_m=d['claimed_altitude_geo_m'],height_m=d.get('claimed_height_m'),
                    height_type=d.get('height_type'),rid_seconds_within_hour=d.get('claimed_seconds_within_hour'),
                    rssi_dbm=r.get('rssi_dbm'), received_at_utc=r.get('received_at_utc'))
                records.append(point);points.append(point)
            segments.append((segment,points))
    with (a.output/'trajectory-private.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    summaries=[]
    for name,ps in segments:
        summaries.append(dict(segment=name,rows=len(ps),duration_s=ps[-1]['elapsed_s']-ps[0]['elapsed_s'],
            east_span_m=max(x['east_m'] for x in ps)-min(x['east_m'] for x in ps),
            north_span_m=max(x['north_m'] for x in ps)-min(x['north_m'] for x in ps),
            geo_min_m=min(x['geo_altitude_m'] for x in ps),geo_max_m=max(x['geo_altitude_m'] for x in ps),
            height_min_m=min(x['height_m'] for x in ps),height_max_m=max(x['height_m'] for x in ps),
            polyline_length_m=sum(math.dist((x['east_m'],x['north_m'],x['up_m']),
                                           (y['east_m'],y['north_m'],y['up_m'])) for x,y in zip(ps,ps[1:]))))
    (a.output/'summary-private.json').write_text(json.dumps(dict(reference_wgs84=reference,segments=summaries,
        observed_claims_only=True,ground_elevation_known=False,segment_gap_s=60,
        clock_aligned_across_devices=False,height_reference_resets_resolved=False),indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    from matplotlib.font_manager import FontProperties
    font=FontProperties(fname='/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc')
    plt.rcParams.update({'font.family':font.get_name(),'axes.unicode_minus':False})
    colors=['#1768aa','#d77a05','#248844','#b13e75','#7851a9']
    bsegments=[(n,ps) for n,ps in segments if ps[0]['source']=='B']
    fig=plt.figure(figsize=(14,6));ax=fig.add_subplot(121,projection='3d');xy=fig.add_subplot(122)
    for i,(name,ps) in enumerate(bsegments):
        c=colors[i%len(colors)]
        ax.plot([x['east_m'] for x in ps],[x['north_m'] for x in ps],[x['geo_altitude_m'] for x in ps],'.-',ms=2,lw=.9,color=c,label=name)
        xy.plot([x['east_m'] for x in ps],[x['north_m'] for x in ps],'.-',ms=2,lw=.9,color=c,label=name)
        first,last=ps[0],ps[-1]
        ax.scatter(first['east_m'],first['north_m'],first['geo_altitude_m'],marker='^',s=60,color=c)
        ax.scatter(last['east_m'],last['north_m'],last['geo_altitude_m'],marker='s',s=40,color=c)
    ax.set(xlabel='東 [m]：最初の申告点基準',ylabel='北 [m]',zlabel='申告Geo高度 [m・WGS84楕円体]',title='Bで受信した申告軌跡：▲開始／■終了')
    ax.xaxis.set_major_locator(MaxNLocator(4));ax.yaxis.set_major_locator(MaxNLocator(5))
    ranges=[max(r[k] for r in records if r['source']=='B')-min(r[k] for r in records if r['source']=='B') for k in ['east_m','north_m','geo_altitude_m']]
    ax.set_box_aspect([max(v,1) for v in ranges]);ax.view_init(elev=22,azim=-55)
    xy.set(xlabel='東 [m]：最初の申告点基準',ylabel='北 [m]',title='上から見た移動（軸の縮尺は同じ）',aspect='equal');xy.grid(alpha=.2);xy.legend()
    fig.suptitle('実機RIDの位置・高度を再生：実測電波から読み出した申告値／空白は接続しない')
    fig.tight_layout();fig.savefig(a.output/'01_B_3d_and_top.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True)
    for i,(name,ps) in enumerate(bsegments):
        t=[x['elapsed_s']/60 for x in ps];c=colors[i%len(colors)]
        axes[0].plot(t,[x['height_m'] for x in ps],'.-',ms=3,label=name,color=c)
        axes[1].plot(t,[x['geo_altitude_m'] for x in ps],'.-',ms=3,label=name,color=c)
    axes[0].set(ylabel='申告Height [m]',title='離陸点基準：地形の上からの高さとは限らない')
    axes[1].set(ylabel='申告Geo高度 [m]',xlabel='Bの最初の対象観測から [分]',title='WGS84楕円体基準：Heightとは別の値')
    for ax in axes:ax.grid(alpha=.2);ax.legend(ncol=5)
    fig.tight_layout();fig.savefig(a.output/'02_B_height_timeline.png',dpi=180);plt.close(fig)
    import plotly.graph_objects as go
    fig=go.Figure()
    for i,(name,ps) in enumerate(segments):
        hover=[f"{x['segment']}<br>局内経過 {x['elapsed_s']/60:.2f}分<br>RSSI {x['rssi_dbm']} dBm<br>Height {x['height_m']:.1f}m<br>Geo高度 {x['geo_altitude_m']:.1f}m" for x in ps]
        fig.add_trace(go.Scatter3d(x=[x['east_m'] for x in ps],y=[x['north_m'] for x in ps],z=[x['geo_altitude_m'] for x in ps],
            mode='lines+markers',line=dict(width=3),marker=dict(size=2),name=name,legendgroup=ps[0]['source'],
            visible=True if ps[0]['source']=='B' else 'legendonly',text=hover,hovertemplate='%{text}<extra></extra>'))
    b=[x for x in records if x['source']=='B'];marker_index=len(fig.data)
    fig.add_trace(go.Scatter3d(x=[b[0]['east_m']],y=[b[0]['north_m']],z=[b[0]['geo_altitude_m']],mode='markers',
        marker=dict(size=7,color='#d62728'),name='Bの再生位置（Geo高度のみ）',hovertemplate='受信順の再生位置<extra></extra>'))
    # Frames use Geo altitude only; the height mode is static to avoid mixed units during playback.
    frames=[];steps=[]
    for i,x in enumerate(b):
        frames.append(go.Frame(name=str(i),data=[go.Scatter3d(x=[x['east_m']],y=[x['north_m']],z=[x['geo_altitude_m']])],traces=[marker_index],
            layout=go.Layout(title=dict(text=f"実機RIDの3D申告軌跡 — B経過{x['elapsed_s']/60:.2f}分・{x['segment']}"))))
        if i%30==0 or i==len(b)-1 or (i and b[i-1]['segment']!=x['segment']):
            steps.append(dict(method='animate',args=[[str(i)],dict(mode='immediate',frame=dict(duration=0,redraw=True),transition=dict(duration=0))],
                              label=f"{x['elapsed_s']/60:.1f}分"))
    fig.frames=frames
    fig.update_layout(title='実機RIDの3D申告軌跡（地形・真位置の独立検証なし）',height=750,
        scene=dict(xaxis_title='東 [m]：最初の申告点基準',yaxis_title='北 [m]',zaxis_title='Geo高度 [m・WGS84楕円体]',aspectmode='data'),
        margin=dict(l=0,r=0,t=170,b=90),legend=dict(groupclick='toggleitem'),
        updatemenus=[dict(type='buttons',direction='left',x=0,xanchor='left',y=1.08,buttons=[
            dict(label='▶ 受信順に再生',method='animate',args=[None,dict(fromcurrent=True,frame=dict(duration=80,redraw=True),transition=dict(duration=0))]),
            dict(label='停止',method='animate',args=[[None],dict(mode='immediate',frame=dict(duration=0,redraw=False))])])],
        sliders=[dict(active=0,currentvalue=dict(prefix='ジャンプ先：'),steps=steps)],
        annotations=[dict(text='初期表示はB。凡例で他端末を表示／各端末の時計は未統一。再生速度は実時間と異なる。',xref='paper',yref='paper',x=0,xanchor='left',y=1.16,showarrow=False)])
    fig.write_html(a.output/'03_drone_3d_replay.html',include_plotlyjs=True,full_html=True,auto_play=False)
    # Height is an independent view, avoiding any mixing of replay frames with height units.
    height=go.Figure()
    for name,ps in segments:
        height.add_trace(go.Scatter3d(x=[x['east_m'] for x in ps],y=[x['north_m'] for x in ps],z=[x['height_m'] for x in ps],
            mode='lines+markers',marker=dict(size=2),name=name,visible=True if ps[0]['source']=='B' else 'legendonly'))
    height.update_layout(title='離陸点基準Heightによる3D表示（基準変更・地形は未確認）',height=700,
        scene=dict(xaxis_title='東 [m]',yaxis_title='北 [m]',zaxis_title='申告Height [m・離陸点基準]',aspectmode='data'))
    height.write_html(a.output/'04_drone_3d_height.html',include_plotlyjs=True,full_html=True,auto_play=False)
    print(json.dumps({'sources':{k:len(v) for k,v in sources.items()},'segments':len(segments),'private_output':str(a.output),'replay_points':len(b)}))


if __name__=='__main__':main()
