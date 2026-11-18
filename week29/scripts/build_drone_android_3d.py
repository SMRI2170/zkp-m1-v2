#!/usr/bin/env python3
"""New private 3D replay: RID drone track plus Android GPS tracks, unchanged originals."""
import argparse
import bisect
import csv
import datetime as dt
import json
import math
import os
import sqlite3
import statistics
from pathlib import Path

from build_drone_trajectory import enu

JST=dt.timezone(dt.timedelta(hours=9))
COLORS={'Drone':'#1768aa','Pixel':'#20924a','ASUS-1':'#d58116','ASUS-2':'#944aab'}


def time_model(node,observations,candidates):
    matches=[x for x in candidates if x.get('node')==node and x.get('offset_to_anchor_low_s') is not None]
    if len(matches)!=1:raise ValueError(f'{node}: no unique candidate clock group')
    candidate=matches[0]
    rows=[x for x in observations if x['node']==node and x['clock_group']==candidate['clock_group']]
    good=[x for x in rows if x['utc'] is not None and x['mono'] is not None]
    if not good:raise ValueError(f'{node}: no clock observations')
    return dict(origin=statistics.median(x['utc']-x['mono'] for x in good),
                offset=(candidate['offset_to_anchor_low_s']+candidate['offset_to_anchor_high_s'])/2,
                boots={x['boot'] for x in good},candidate=candidate)


def nearest(points,t,max_delta=3):
    """Nearest recorded fix within tolerance; never hold stale positions or extrapolate."""
    times=[x['time'] for x in points]
    i=bisect.bisect_left(times,t)
    choices=[points[k] for k in [i-1,i] if 0<=k<len(points)]
    if not choices:return None
    result=min(choices,key=lambda x:abs(x['time']-t))
    return result if abs(result['time']-t)<=max_delta else None


def line_coordinates(points,zkey,gap_s):
    result=[[],[],[]]
    for i,p in enumerate(points):
        if i and (p['time']-points[i-1]['time']>gap_s or p.get('segment')!=points[i-1].get('segment')):
            for array in result:array.append(None)
        for array,k in zip(result,['east_m','north_m',zkey]):array.append(p[k])
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--audit-private',type=Path,required=True)
    p.add_argument('--clock-summary',type=Path,required=True)
    p.add_argument('--drone-trajectory',type=Path,required=True)
    p.add_argument('--android',action='append',required=True,help='label=preserved SQLite database')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if not a.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'captures'):
        raise ValueError('Real GPS replay outputs must remain in ignored captures/')
    if (a.output/'summary-private.json').exists():raise ValueError('Choose a new output directory; preserve earlier versions')
    a.output.mkdir(parents=True,exist_ok=True)
    observations=[json.loads(l) for l in (a.audit_private/'target-observations-private.jsonl').open()]
    candidates=json.loads(a.clock_summary.read_text())['candidates']
    reference=json.loads((a.drone_trajectory/'summary-private.json').read_text())['reference_wgs84']
    model=time_model('B',observations,candidates)
    tracks={'Drone':[]};models={'Drone':model}
    with (a.drone_trajectory/'trajectory-private.csv').open() as f:
        for r in csv.DictReader(f):
            if r['source']!='B':continue
            tracks['Drone'].append(dict(source='Drone',segment=r['segment'],
                time=float(r['monotonic_s'])+model['origin']+model['offset'],
                east_m=float(r['east_m']),north_m=float(r['north_m']),
                geo_m=float(r['geo_altitude_m']),height_m=float(r['height_m']),
                latitude=float(r['latitude']),longitude=float(r['longitude']),accuracy_m=None,
                mock=None,provider='RID claim',original_fix_utc=None))
    tracks['Drone'].sort(key=lambda x:x['time'])
    begin=tracks['Drone'][0]['time']-60;end=tracks['Drone'][-1]['time']+60
    selection={}
    for spec in a.android:
        label,path=spec.split('=',1)
        if label in tracks:raise ValueError('duplicate source label')
        m=time_model(label,observations,candidates);models[label]=m
        if not m['boots'] or '' in m['boots']:raise ValueError(f'{label}: boot scope missing')
        tracks[label]=[];counts=dict(all_fixes=0,other_boot=0,outside_window=0,invalid_fix=0)
        db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
        for (raw,) in db.execute('SELECT raw_json FROM receiver_fixes'):
            r=json.loads(raw);counts['all_fixes']+=1
            if str(r.get('boot_scope') or '') not in m['boots']:counts['other_boot']+=1;continue
            us=r.get('fix_elapsed_us');lat=r.get('latitude');lon=r.get('longitude');alt=r.get('altitude_ellipsoid_m')
            if (not all(isinstance(x,(int,float)) and math.isfinite(x) for x in [us,lat,lon,alt])
                    or not -90<=lat<=90 or not -180<=lon<=180):counts['invalid_fix']+=1;continue
            t=us/1e6+m['origin']+m['offset']
            if not begin<=t<=end:counts['outside_window']+=1;continue
            east,north,up=enu(lat,lon,alt,reference)
            tracks[label].append(dict(source=label,segment='gps',time=t,east_m=east,north_m=north,geo_m=alt,
                height_m=None,latitude=lat,longitude=lon,accuracy_m=r.get('accuracy_m'),mock=r.get('mock'),
                provider=r.get('provider'),original_fix_utc=r.get('fix_utc')))
        db.close();tracks[label].sort(key=lambda x:x['time']);counts['selected_fixes']=len(tracks[label]);selection[label]=counts
        if not tracks[label]:raise ValueError(f'{label}: no usable GPS fixes in candidate window')
    for label,points in tracks.items():
        baseline=points[0]['geo_m']
        for x in points:x['relative_geo_m']=x['geo_m']-baseline
    allrows=[x for points in tracks.values() for x in points]
    with (a.output/'drone_android_tracks_private.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
    summary=dict(selection=selection,points={k:len(v) for k,v in tracks.items()},reference_wgs84=reference,
        candidate_window_jst=[dt.datetime.fromtimestamp(t,JST).isoformat() for t in [begin,end]],
        clock_alignment_verified=False,frame_nearest_fix_limit_s=3,phone_gap_s=10,drone_gap_s=60,
        relative_height_definition='each source recorded Geo altitude minus its first selected Geo altitude; not a common ground-height reference',
        vertical_datum_consistency_verified=False,pi_observer_position_known=False,
        altitude_ranges={k:[min(x['geo_m'] for x in v),max(x['geo_m'] for x in v)] for k,v in tracks.items()},
        accuracy_medians={k:statistics.median(x['accuracy_m'] for x in v if x['accuracy_m'] is not None)
                          for k,v in tracks.items() if k!='Drone'})
    # Two separate figures keep the measured altitude disagreement visible instead of correcting it away.
    import plotly.graph_objects as go
    for filename,zkey,title,ztitle in [
        ('01_drone_android_relative_3d.html','relative_geo_m','ドローン＋Androidの移動：各端末初回からの高度変化','各端末の初回Geo高度からの差 [m]'),
        ('02_drone_android_raw_altitude_3d.html','geo_m','ドローン＋Androidの移動：記録されたGeo高度','記録Geo高度 [m]：基準整合性は未確認')]:
        fig=go.Figure();labels=list(tracks)
        for label,points in tracks.items():
            x,y,z=line_coordinates(points,zkey,60 if label=='Drone' else 10)
            fig.add_trace(go.Scatter3d(x=x,y=y,z=z,mode='lines',line=dict(color=COLORS[label],width=3),
                name=label+' 軌跡',legendgroup=label,hovertemplate=f'{label} の記録軌跡<extra></extra>'))
        dynamic_indices=[]
        for label in labels:
            dynamic_indices.append(len(fig.data))
            fig.add_trace(go.Scatter3d(x=[None],y=[None],z=[None],mode='markers',marker=dict(size=7,color=COLORS[label]),
                name=label+' 現在位置（候補）',legendgroup=label,showlegend=False))
        frames=[];steps=[];missing={label:0 for label in labels if label!='Drone'}
        for i,drone in enumerate(tracks['Drone']):
            data=[]
            for label in labels:
                point=drone if label=='Drone' else nearest(tracks[label],drone['time'],3)
                if point is None:
                    missing[label]+=1;data.append(go.Scatter3d(x=[None],y=[None],z=[None]));continue
                stamp=dt.datetime.fromtimestamp(point['time'],JST).strftime('%H:%M:%S')
                text=(f'{label}<br>補正候補 {stamp}<br>Geo高度 {point["geo_m"]:.1f} m'
                      f'<br>初回からの高度差 {point["relative_geo_m"]:.1f} m')
                if label!='Drone':text+=f'<br>OS水平精度 {point["accuracy_m"]} m<br>再生時刻との差 {point["time"]-drone["time"]:+.2f} 秒'
                data.append(go.Scatter3d(x=[point['east_m']],y=[point['north_m']],z=[point[zkey]],text=[text],hovertemplate='%{text}<extra></extra>'))
            stamp=dt.datetime.fromtimestamp(drone['time'],JST).strftime('%H:%M:%S')
            frames.append(go.Frame(name=str(i),data=data,traces=dynamic_indices,
                layout=go.Layout(title=dict(text=title+' — '+stamp+'（補正候補）'))))
            if i%30==0 or i==len(tracks['Drone'])-1:
                steps.append(dict(method='animate',args=[[str(i)],dict(mode='immediate',frame=dict(duration=0,redraw=True),transition=dict(duration=0))],label=stamp[:5]))
        fig.frames=frames
        # Start with the first observation's real, available marker positions.
        for index,frame_trace in zip(dynamic_indices,frames[0].data):
            fig.data[index].update(x=frame_trace.x,y=frame_trace.y,z=frame_trace.z,text=frame_trace.text,hovertemplate=frame_trace.hovertemplate)
        note=('横位置は共通ENU。縦軸は各端末別の初回基準で、共通の地上高ではありません。' if zkey=='relative_geo_m'
              else 'スマホと機体に約100mの高度差が記録されています。補正せず表示。真の上下関係とは未検証。')
        fig.update_layout(title=title,height=800,margin=dict(l=0,r=0,t=175,b=85),
            scene=dict(xaxis_title='東 [m]：機体最初の申告点基準',yaxis_title='北 [m]',zaxis_title=ztitle,aspectmode='data'),
            annotations=[dict(text=note+'<br>時刻は補正候補／GPSの揺らぎを含む。Pi Bの設置位置は不明のため描画しません。',
                xref='paper',yref='paper',x=0,xanchor='left',y=1.17,showarrow=False)],
            legend=dict(groupclick='togglegroup'),
            updatemenus=[dict(type='buttons',direction='left',x=0,xanchor='left',y=1.08,buttons=[
                dict(label='▶ 移動を再生',method='animate',args=[None,dict(fromcurrent=True,frame=dict(duration=100,redraw=True),transition=dict(duration=0))]),
                dict(label='停止',method='animate',args=[[None],dict(mode='immediate',frame=dict(duration=0,redraw=False))])])],
            sliders=[dict(active=0,currentvalue=dict(prefix='ジャンプ先（候補）：'),steps=steps)])
        fig.write_html(a.output/filename,include_plotlyjs=True,full_html=True,auto_play=False)
    summary['missing_phone_marker_frames']=missing
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    plt.rcParams.update({'font.family':FontProperties(fname='/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc').get_name(),'axes.unicode_minus':False})
    fig,axes=plt.subplots(1,2,figsize=(14,6))
    for label,points in tracks.items():
        x,y,z=line_coordinates(points,'relative_geo_m',60 if label=='Drone' else 10)
        axes[0].plot(x,y,lw=.7,color=COLORS[label],label=label)
        first,last=points[0],points[-1]
        axes[0].scatter(first['east_m'],first['north_m'],color=COLORS[label],marker='^',s=55)
        axes[0].scatter(last['east_m'],last['north_m'],color=COLORS[label],marker='s',s=35)
        # Break time-series lines at the same observation gaps as the 3D tracks.
        times=[];zs=[]
        for i,point in enumerate(points):
            if i and (point['time']-points[i-1]['time']>(60 if label=='Drone' else 10) or point['segment']!=points[i-1]['segment']):times.append(None);zs.append(None)
            times.append((point['time']-begin)/60);zs.append(point['relative_geo_m'])
        axes[1].plot(times,zs,lw=.7,color=COLORS[label],label=label)
    axes[0].set(xlabel='東 [m]：機体の最初の申告点基準',ylabel='北 [m]',aspect='equal',title='機体とAndroid 3台の水平位置（▲開始・■終了）')
    axes[1].set(xlabel='表示窓開始からの時間 [分]：補正候補',ylabel='各端末初回のGeo高度からの差 [m]',title='高度変化：基準は端末別／GPSの揺らぎを含む')
    for ax in axes:ax.grid(alpha=.2);ax.legend()
    fig.suptitle('実機RID＋スマホ自己位置：時刻補正・位置・高度の独立検証は未完了')
    fig.tight_layout();fig.savefig(a.output/'03_android_tracks_top_and_height.png',dpi=170);plt.close(fig)
    (a.output/'summary-private.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='reference_wgs84'},indent=2))


if __name__=='__main__':main()
