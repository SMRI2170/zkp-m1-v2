"""Audit the fixed LoRaIQ v2 CSV without publishing source positions/timestamps.

SNR is never re-labelled as RSSI; IQ/dBm calibration is a separate gate.
"""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import urllib.request

RECORD='https://zenodo.org/records/20341802'
FILES={'dataset.csv':(28253049,'0a225350d1c3b01ff9168bdcd3915b05'),
       'rrh_locations.md':(390,'f913bef452fc604247223e8003bce73d'),
       'load_and_plot_samples.py':(2831,'71ebf5d337e6a8434597b218c93cdd53')}


def fetch(raw):
    raw.mkdir(parents=True,exist_ok=True,mode=0o700);raw.chmod(0o700)
    for name,(size,md5) in FILES.items():
        target=raw/name
        if target.exists():continue # verify below; never overwrite mismatched input
        req=urllib.request.Request(RECORD+'/files/'+name+'?download=1')
        with urllib.request.urlopen(req,timeout=30) as response:
            body=response.read(size+1)
        if len(body)!=size or hashlib.md5(body).hexdigest()!=md5:raise ValueError('Download checksum/size mismatch')
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as out:out.write(body)


def group_audit(rows):
    grouped=defaultdict(list)
    for row in rows:grouped[(row['name'],row['transmission_idx'])].append(row)
    counts=Counter();duplicates=0;inconsistent=0;spreads=[];conflicts=Counter();complete=0;eligible_multi=0
    for group in grouped.values():
        receivers=[r['rrh_idx'] for r in group]
        duplicates+=len(receivers)!=len(set(receivers))
        counts[len(set(receivers))]+=1
        # Packet identity needs metadata agreement, not merely a close timestamp.
        fields=('latitude','longitude','payload_base64','sf','cr','fc','bandwidth','area','area_type')
        bad=[field for field in fields if len({r[field] for r in group})!=1]
        conflicts.update(bad);inconsistent+=bool(bad)
        if not bad and len(receivers)==len(set(receivers)) and all(r['latitude'] and r['longitude'] for r in group):
            complete+=1;eligible_multi+=len(set(receivers))>=2
        times=[float(r['rx_timestamp_full'])+float(r['rx_timestamp_frac']) for r in group]
        if not all(math.isfinite(t) for t in times):raise ValueError('Nonfinite time')
        spreads.append(max(times)-min(times))
    ordered=sorted(spreads)
    return dict(transmissions=len(grouped),receiver_count_histogram={str(k):v for k,v in sorted(counts.items())},
        duplicate_receiver_groups=duplicates,inconsistent_identity_or_position_groups=inconsistent,
        multi_receiver_groups=sum(v for k,v in counts.items() if k>=2),
        field_conflict_groups=dict(conflicts),complete_consistent_position_groups=complete,
        complete_consistent_multi_receiver_groups=eligible_multi,
        receive_timestamp_spread_median_s=ordered[len(ordered)//2] if ordered else None,
        receive_timestamp_spread_max_s=max(spreads) if spreads else None)


def audit(raw):
    if raw.stat().st_mode&0o077:raise ValueError('Raw directory must be owner-only')
    inputs={}
    for name,(size,md5) in FILES.items():
        p=raw/name
        if p.stat().st_mode&0o077:raise ValueError('Raw file must be owner-only')
        body=p.read_bytes()
        if len(body)!=size or hashlib.md5(body).hexdigest()!=md5:raise ValueError('Input checksum/size mismatch')
        inputs[name]=dict(size=size,md5=md5,sha256=hashlib.sha256(body).hexdigest())
    with (raw/'dataset.csv').open() as stream:
        reader=csv.DictReader(stream);columns=reader.fieldnames;rows=list(reader)
    for r in rows:
        if r['rrh_idx'] not in ('1','2','3','4') or not math.isfinite(float(r['snr'])):raise ValueError('Invalid receiver/SNR')
        if r['latitude'] and r['longitude'] and not (-90<=float(r['latitude'])<=90 and -180<=float(r['longitude'])<=180):raise ValueError('Invalid position')
    uav=[r for r in rows if r['area_type'] in ('drone_los','drone_nlos')]
    located=[r for r in uav if r['latitude'] and r['longitude']]
    sessions=Counter(r['name'] for r in uav)
    index_names=defaultdict(set)
    for r in rows:index_names[r['transmission_idx']].add(r['name'])
    return dict(source_url=RECORD,version='v2',inputs=inputs,columns=columns,total_rows=len(rows),uav_rows=len(uav),
        excluded_non_uav_rows=len(rows)-len(uav),uav_area_types=dict(Counter(r['area_type'] for r in uav)),
        uav_session_rows=dict(sorted(sessions.items())),uav_session_count=len(sessions),
        transmission_indices_reused_across_sessions=sum(len(v)>1 for v in index_names.values()),
        all_frames=group_audit(rows),uav_frames=group_audit(uav),
        uav_rows_missing_position=len(uav)-len(located),position_available_uav_rows=len(located),
        position_available_uav_frames=group_audit(located),
        missing_position_by_session=dict(Counter(r['name'] for r in uav if not r['latitude'] or not r['longitude'])),
        per_uav_session={name:group_audit([r for r in uav if r['name']==name]) for name in sorted(sessions)},
        gates=dict(uav_to_ground='DOCUMENTED_BY_SOURCE',packet_grouping='CSV_METADATA_AUDITED_NOT_INDEPENDENT_RF_VALIDATION',
                   rssi_dbm='ABSENT_FROM_CSV',uav_altitude='ABSENT_FROM_CSV',iq='NOT_DOWNLOADED',
                   attack_detection='NOT_RUN',direction_estimation='NOT_RUN'),
        limitations=['SNR is not RSSI; receiver noise floors/calibration not established',
                    'Timestamp spread is not a verified clock accuracy or propagation time',
                    'Missing receiver rows are unavailable observations, not established RF packet losses',
                    'UAV session names are not proof of independent flights/days',
                    'CSV transmitter positions are annotations, not an independently authenticated truth ledger',
                    'Position-available subset removes missing rows, not an imputation; whole-group strict counts are separate',
                    'No absolute power, true 3D range or antenna phase calibration established',
                    'LoRa at 862.5MHz is not Wi-Fi/BLE Remote ID'],
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',type=Path,required=True);p.add_argument('--fetch',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Output already exists')
    if a.fetch:fetch(a.raw)
    result=audit(a.raw);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['total_rows','uav_rows','uav_session_count','uav_frames','gates']},indent=2))
