#!/usr/bin/env python3
"""Issue93: private RID claim tracks coloured by receiver RSSI; no inferred receiver sites."""
import argparse
import collections
import csv
import json
import math
import os
from pathlib import Path

from audit_field_time import clock_partitions,sha
from build_drone_trajectory import enu,valid_location
from build_drone_android_3d import line_coordinates


def finite(value):
    return isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value)


def track_points(rows,reference,gap_s=60):
    result=[];previous=None;previous_type=None;segment=0;seen=set()
    for row in sorted(rows,key=lambda x:x['mono']):
        key=(row.get('mono'),row.get('payload'),row.get('key'))
        if key in seen:continue
        seen.add(key)
        ht=row['reference'].get('height_type')
        if previous is None or row['mono']-previous>gap_s or ht!=previous_type:segment+=1
        d=row['reference'];east,north,_=enu(d['claimed_latitude'],d['claimed_longitude'],d['claimed_altitude_geo_m'],reference)
        result.append(dict(time=row['mono'],segment=segment,east_m=east,north_m=north,
            geo_m=d['claimed_altitude_geo_m'],height_m=d.get('claimed_height_m'),
            height_type=d.get('height_type'),rssi_dbm=row.get('rssi')))
        previous=row['mono'];previous_type=ht
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--observations',type=Path,required=True)
    p.add_argument('--private-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if not a.private_output.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'captures'):raise ValueError('Tracks stay in captures/')
    if (a.private_output/'tracks-private.csv').exists():raise ValueError('Use a new private output version')
    for d in [a.private_output,a.output]:d.mkdir(parents=True,exist_ok=True)
    before=sha(a.observations);raw=[json.loads(l) for l in a.observations.open()]
    rows=[r for r in raw if valid_location(r['reference']) and finite(r.get('mono')) and finite(r.get('utc'))]
    if not rows:raise ValueError('No valid claimed locations')
    d=rows[0]['reference'];reference=[d['claimed_latitude'],d['claimed_longitude'],d['claimed_altitude_geo_m']]
    groups={};summary=dict(nodes={},source_sha256=before,code_sha256=sha(Path(__file__)),
        clock_alignment_verified=False,independent_position_truth=False,receiver_sites_known=False,
        service_state_alignment='NOT_EVALUABLE',packet_delivery_rate='NOT_EVALUABLE',gap_s=60,
        note='Coordinates are RID claims. Relative receiver RSSI values are uncalibrated. No service-state evidence is inferred from gaps.')
    counters=collections.Counter();private=[]
    for node,boot,origin,group in clock_partitions(rows):
        counters[node]+=1;name=f'{node}-G{counters[node]}'
        points=track_points(group,reference);groups[name]=points
        ns=summary['nodes'].setdefault(node,dict(points=0,rssi_missing=0,segments=0,clock_groups=0))
        ns['points']+=len(points);ns['rssi_missing']+=sum(not finite(x['rssi_dbm']) for x in points)
        ns['segments']+=max(x['segment'] for x in points);ns['clock_groups']+=1
        private.extend(dict(node=node,group=name,**x) for x in points)
    with (a.private_output/'tracks-private.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(private[0]));w.writeheader();w.writerows(private)
    (a.private_output/'inputs-private.json').write_text(json.dumps(dict(path=str(a.observations),sha256=before,reference_wgs84=reference),indent=2)+'\n')
    values=[x['rssi_dbm'] for x in private if finite(x['rssi_dbm'])]
    if not values:raise ValueError('No finite RSSI')
    vmin,vmax=min(values),max(values)
    if vmin==vmax:vmax=vmin+1
    summary['shared_color_limits_dbm']=[vmin,vmax]
    import plotly.graph_objects as go
    for zkey,label,filename in [('geo_m','申告Geo高度 [m]','01_rssi_geo_3d.html'),('height_m','申告Height [m]：基準整合性未確認','02_rssi_height_3d.html')]:
        fig=go.Figure();trace_groups=[]
        for name,points in groups.items():
            # Invalid/missing heights break lines rather than becoming interpolated positions.
            usable=[dict(x,**{zkey:x[zkey] if finite(x[zkey]) else None}) for x in points]
            x,y,z=line_coordinates(usable,zkey,60)
            fig.add_trace(go.Scatter3d(x=x,y=y,z=z,mode='lines',line=dict(color='#b8bdc5',width=2),name=name+' 申告軌跡',showlegend=False));trace_groups.append(name)
            good=[x for x in usable if finite(x[zkey]) and finite(x['rssi_dbm'])]
            fig.add_trace(go.Scatter3d(x=[x['east_m'] for x in good],y=[x['north_m'] for x in good],z=[x[zkey] for x in good],mode='markers',
                marker=dict(size=4,color=[x['rssi_dbm'] for x in good],coloraxis='coloraxis'),name=name,
                text=[f"{name}<br>局内経過 {(x['time']-points[0]['time'])/60:.2f}分<br>RSSI {x['rssi_dbm']} dBm<br>{label} {x[zkey]}" for x in good],hovertemplate='%{text}<extra></extra>'));trace_groups.append(name)
            missing=[x for x in usable if finite(x[zkey]) and not finite(x['rssi_dbm'])]
            fig.add_trace(go.Scatter3d(x=[x['east_m'] for x in missing],y=[x['north_m'] for x in missing],z=[x[zkey] for x in missing],mode='markers',marker=dict(size=4,color='gray',symbol='x'),name=name+' RSSI不明'));trace_groups.append(name)
        nodes=list(summary['nodes'])
        buttons=[dict(label='全端末：時刻未統一',method='update',args=[dict(visible=[True]*len(fig.data))])]
        buttons.extend(dict(label=node,method='update',args=[dict(visible=[g.startswith(node+'-G') for g in trace_groups])]) for node in nodes)
        fig.update_layout(title=dict(text='実測RSSIで色分けしたRID申告位置：真位置の推定ではない',x=.03,y=.98,yanchor='top',font=dict(size=17)),height=900,
            margin=dict(t=190,b=100),coloraxis=dict(colorscale='Viridis',cmin=vmin,cmax=vmax,colorbar=dict(title='RSSI [dBm]',x=1.04)),
            legend=dict(orientation='h',x=0,y=-.10,yanchor='top'),
            scene=dict(xaxis_title='東 [m]：共通ENU',yaxis_title='北 [m]',zaxis_title=label,aspectmode='data',camera=dict(eye=dict(x=1.7,y=1.7,z=1.1))),
            annotations=[dict(text='局間時計未統一／60秒超の空白で線を切断／受信機設置位置・サービス状態・通信範囲は未確定',xref='paper',yref='paper',x=0,y=1.16,showarrow=False,xanchor='left')],
            updatemenus=[dict(type='dropdown',x=0,y=1.08,buttons=buttons),dict(type='buttons',x=.45,y=1.08,direction='left',buttons=[
                dict(label='上面',method='relayout',args=[{'scene.camera.eye':dict(x=0,y=0,z=2.5),'scene.camera.up':dict(x=0,y=1,z=0)}]),
                dict(label='側面',method='relayout',args=[{'scene.camera.eye':dict(x=2.5,y=0,z=0),'scene.camera.up':dict(x=0,y=0,z=1)}]),
                dict(label='斜め',method='relayout',args=[{'scene.camera.eye':dict(x=1.4,y=1.4,z=1.1),'scene.camera.up':dict(x=0,y=0,z=1)}])])])
        fig.write_html(a.private_output/filename,include_plotlyjs=True,full_html=True,auto_play=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib.ticker import MaxNLocator
    plt.rcParams.update({'font.family':FontProperties(fname='/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc').get_name(),'axes.unicode_minus':False})
    fig,axes=plt.subplots(len(groups),2,figsize=(12,3.1*len(groups)),squeeze=False)
    for pair,(name,points) in zip(axes,groups.items()):
        good=[x for x in points if finite(x['rssi_dbm'])]
        sc=pair[0].scatter([x['east_m'] for x in good],[x['north_m'] for x in good],c=[x['rssi_dbm'] for x in good],s=14,vmin=vmin,vmax=vmax,cmap='viridis')
        pair[0].set(title=name+'：RID申告位置',xlabel='東 [m]',ylabel='北 [m]',aspect='equal');fig.colorbar(sc,ax=pair[0],label='RSSI [dBm]')
        pair[0].xaxis.set_major_locator(MaxNLocator(3))
        pair[1].scatter([(x['time']-points[0]['time'])/60 for x in good],[x['rssi_dbm'] for x in good],s=8)
        pair[1].set(title='記録された点のみ：空白の原因は不明',xlabel='各時計群の初回対象観測から [分]',ylabel='RSSI [dBm]');pair[1].grid(alpha=.2)
    fig.suptitle('端末間の0分は同時刻を意味しない／設置位置や受信率は推定しない');fig.tight_layout()
    fig.savefig(a.private_output/'03_rssi_track_and_time.png',dpi=150);plt.close(fig)
    summary['input_unchanged']=before==sha(a.observations)
    if not summary['input_unchanged']:raise ValueError('Input changed')
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
