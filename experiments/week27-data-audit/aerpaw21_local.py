"""Audit official Dataset-21 bytes, clocks and RT-derived RSS offsets.

No detection experiment is run. No raw RSS, timestamps or positions are
published. Same-row, nearest-time and same-physical-transmission are distinct.
MATLAB scripts are inspected as text, never executed.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile
import numpy as np

ARCHIVE_SIZE=8736011
ARCHIVE_SHA256='ff930df7158d4e9a4d2a038d225fb805b88031adef5628137bd3754ad2bd9ae1'
FIELDS=['GPSx','GPSy','GPSz','RSS','RSS1','RSS2','timestamp_meas','timestamp_gps',
        'validindex','Time_s','fname','carrier_freq','timestamp_for_csv','time_stamp_gps_for_csv']


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def nearest_indices(reference,other):
    reference=np.asarray(reference);other=np.asarray(other)
    if reference.ndim!=1 or other.ndim!=1 or not len(reference) or not len(other):raise ValueError('Nonempty 1D times required')
    if not np.isfinite(reference).all() or not np.isfinite(other).all() or (np.diff(reference)<=0).any() or (np.diff(other)<=0).any():
        raise ValueError('Finite strictly increasing clocks required; do not silently sort')
    right=np.minimum(np.searchsorted(other,reference),len(other)-1);left=np.maximum(right-1,0)
    # MATLAB min(abs(...)) takes the first index on exact ties.
    return np.where(abs(other[left]-reference)<=abs(other[right]-reference),left,right)


def minimum_covering_span(times):
    """Exhaustive sliding-window minimum containing >=1 sample of EVERY station.

    No interpolation or row-index pairing. This does not authenticate clocks.
    """
    merged=sorted((int(t),i) for i,a in enumerate(times) for t in a)
    if not times or any(not len(a) for a in times):raise ValueError('Missing station')
    counts=[0]*len(times);covered=0;left=0;best=None
    for t,k in merged:
        counts[k]+=1
        if counts[k]==1:covered+=1
        while covered==len(times):
            width=t-merged[left][0];best=width if best is None else min(best,width)
            node=merged[left][1];counts[node]-=1;left+=1
            if counts[node]==0:covered-=1
    return best


def constant_offset(aligned,processed,tolerance=1.e-8):
    a=np.asarray(aligned,float);b=np.asarray(processed,float)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('Invalid finite aligned RSS')
    offset=float(np.median(b-a));error=float(np.max(abs(b-a-offset)))
    if error>tolerance:raise ValueError('D3 is not a constant-offset transform')
    return offset,error


def optimal_grid_offset(measured,target):
    measured=np.asarray(measured);target=np.asarray(target)
    mask=np.isfinite(target)&(target!=-90)&np.isfinite(measured)
    if not mask.any():raise ValueError('No valid RT targets')
    pool=np.round(np.arange(-50,50.001,.1),10)
    rmse=np.sqrt(np.mean((measured[mask,None]+pool-target[mask,None])**2,axis=0))
    index=int(np.argmin(rmse));return float(pool[index]),float(rmse[index]),int(mask.sum())


def stats(values):
    x=np.asarray(values,float)
    if not len(x) or not np.isfinite(x).all():raise ValueError('Finite statistics required')
    return dict(zip(['min','median','p95','max'],map(float,np.quantile(x,[0,.5,.95,1]))))


def write_table(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def audit(source,archive,private_out):
    from scipy.io import loadmat
    if archive.stat().st_size!=ARCHIVE_SIZE or sha(archive)!=ARCHIVE_SHA256:raise ValueError('Official archive size/hash mismatch')
    inventory=[]
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC mismatch')
        for p in sorted(source.rglob('*')):
            if not p.is_file():continue
            relative=str(p.relative_to(source));members=[v for v in z.namelist() if v.endswith('/'+relative) or v==relative]
            if len(members)!=1 or hashlib.sha256(z.read(members[0])).hexdigest()!=sha(p):raise ValueError('Extracted file differs: '+relative)
            inventory.append(dict(file=relative,bytes=p.stat().st_size,sha256=sha(p)))
        archived_files=[v for v in z.infolist() if not v.is_dir()]
        if len(inventory)!=len(archived_files):raise ValueError('Missing extracted file')
    data=[];stations=[];schemas=[]
    for i in range(1,6):
        path=source/f'D1_RSS_Measurements/LW{i}/GPS_RSS_data_40m_fs20MHz_LW{i}.mat'
        # Selected numeric/string variables avoid MATLAB MCOS opaque objects;
        # no unsupported object is silently interpreted as a timestamp or ID.
        d=loadmat(path,variable_names=FIELDS,simplify_cells=True)
        required=set(FIELDS)-{'carrier_freq'}
        if not required.issubset(d):raise ValueError('Missing required measurement fields')
        t=d['timestamp_meas'];gps=d['timestamp_gps'];nearest_indices(t,t);nearest_indices(gps,gps)
        idx=np.asarray(d['validindex'],int)-1
        if len(idx)!=len(t) or np.any(idx<0) or np.any(idx>=len(d['RSS'])) or len(set(idx))!=len(idx):raise ValueError('Invalid MATLAB selected indices')
        for channel in [1,2]:
            if not np.array_equal(d['RSS'][idx,channel-1],d[f'RSS{channel}']):raise ValueError('Selected raw RSS mismatch')
        if any(len(d[k])!=len(gps) or not np.isfinite(d[k]).all() for k in ['GPSx','GPSy','GPSz']):raise ValueError('Incomplete GPS')
        converted=loadmat(source/f'D1_RSS_Measurements/LW{i}/Converted_GPS_RSS_data_40m_fs20MHz_LW{i}.mat',simplify_cells=True)
        if any(len(converted[k])!=len(t) or not np.isfinite(converted[k]).all() for k in ['conv_mX','conv_mY','conv_mZ']):raise ValueError('Converted coordinate length mismatch')
        frequency=sorted({int(re.match(r'results_(\d+)_',str(v)).group(1)) for v in d['fname']})
        capture_width=np.ptp(d['Time_s'].reshape(2,-1,50),axis=2)*1000
        time_step=stats(np.diff(t)*1000)
        if data:
            if not all(np.array_equal(d[k],data[0][k]) for k in ['timestamp_gps','GPSx','GPSy','GPSz']):raise ValueError('Stations do not share the same GPS reference')
        stations.append(dict(station=f'LW{i}',raw_capture_rows=len(d['RSS']),selected_rss_rows=len(t),channels=2,
                             gps_rows=len(gps),finite_rss1=int(np.isfinite(d['RSS1']).sum()),finite_rss2=int(np.isfinite(d['RSS2']).sum()),
                             selected_raw_mapping_exact=True,time_step_median_ms=time_step['median'],time_step_min_ms=time_step['min'],time_step_p95_ms=time_step['p95'],time_step_max_ms=time_step['max'],
                             capture_span_median_ms=float(np.median(capture_width)),common_gps_reference=True,
                             filename_frequency_hz=frequency[0] if len(frequency)==1 else str(frequency),stored_carrier_freq_hz=d.get('carrier_freq')))
        schemas.append(dict(station=f'LW{i}',fields={k:dict(shape=list(np.shape(v)),dtype=str(np.asarray(v).dtype)) for k,v in d.items() if not k.startswith('__')}))
        data.append(d)
    processed=loadmat(source/'D3_RT_Measurement_RSS_postprocessed_data.mat',variable_names=['LWs','RSS_arr','path_gain_arr','tx_power_dBm'],simplify_cells=True)
    rt=loadmat(source/'D2_RT_RSS_results_data.mat',simplify_cells=True)['data_save']
    reference=data[0]['timestamp_meas'];elapsed=reference-data[0]['timestamp_gps'][0]
    mappings=[];matched=[];pairing=[];calibration=[]
    rt_rss_error=float(np.max(abs(processed['RSS_arr']-(processed['tx_power_dBm']+10*np.log10(processed['path_gain_arr'])))))
    if rt_rss_error>1.e-8 or len(rt)!=len(reference):raise ValueError('RT model/length mismatch')
    for i,d in enumerate(data):
        t=d['timestamp_meas'];idx=nearest_indices(reference,t);mappings.append(idx);matched.append(t[idx])
        actual=processed['LWs'][i]
        if not np.array_equal(actual[0],elapsed) or not np.array_equal(actual[1],processed['RSS_arr'][i]):raise ValueError('D3 reference/RT rows differ')
        delta=stats(abs(t[idx]-reference)*1000)
        pairing.append(dict(station=f'LW{i+1}',reference_rows=len(reference),distinct_source_rows=len(set(idx)),
                            reused_reference_rows=len(idx)-len(set(idx)),exact_recorded_time_matches=int(sum(t[idx]==reference)),
                            nearest_abs_delta_min_ms=delta['min'],nearest_abs_delta_median_ms=delta['median'],nearest_abs_delta_p95_ms=delta['p95'],nearest_abs_delta_max_ms=delta['max']))
        # Match the author's relative-time nearest-neighbour implementation.
        idx_relative=nearest_indices(elapsed,t-d['timestamp_gps'][0])
        if not np.array_equal(idx,idx_relative):raise ValueError('Absolute and relative clocks choose different samples')
        for ch in [1,2]:
            aligned=d[f'RSS{ch}'][idx];offset,error=constant_offset(aligned,actual[ch+1])
            optimum,rmse,n=optimal_grid_offset(aligned,processed['RSS_arr'][i])
            if i!=4 and abs(offset-optimum)>1.e-8:raise ValueError('D3 offset differs from C2 RT-fit minimum')
            if i==4 and abs(offset+10)>1.e-8:raise ValueError('LW5 manual -10dB override differs')
            calibration.append(dict(station=f'LW{i+1}',channel=ch,d3_offset_db=offset,constant_offset_max_error_db=error,
                                    rt_fitted_optimum_db=optimum,rt_fitted_rmse_db=rmse,rt_target_count=n,manual_override=i==4,
                                    physical_absolute_calibration_established=False))
    times=np.asarray(matched);spread=(times.max(axis=0)-times.min(axis=0))*1000
    tolerances=[dict(max_recorded_span_ms=v,reference_rows=len(reference),nearest_time_candidate_rows=int(sum(spread<=v)),
                     same_transmission_verified=False) for v in [0,1,5,10,20,50,100,200,500]]
    origin=min(d['timestamp_meas'][0] for d in data)
    ticks=[np.rint((d['timestamp_meas']-origin)*1.e6).astype(np.int64) for d in data]
    global_minimum=minimum_covering_span(ticks)/1000
    private_out.mkdir(parents=True,mode=0o700)
    np.savez_compressed(private_out/'nearest-time-candidates.npz',reference=reference,matched_times=times,indices=np.asarray(mappings),recorded_span_ms=spread)
    code=(source/'C2_RSS_postprocessing.m').read_text()
    if 'asynchronous' not in code or 'min(abs(time_reference(j) - time))' not in code or 'if i == 5' not in code:raise ValueError('C2 processing assumptions changed')
    return dict(status='AUDITED_SAME_TRANSMISSION_NOT_ESTABLISHED',dataset='AERPAW Dataset-21',
                archive=dict(size_bytes=ARCHIVE_SIZE,sha256=ARCHIVE_SHA256,crc_verified=True,all_extracted_files_match=True,file_count=len(inventory)),
                inventory=inventory,schemas=schemas,stations=stations,pairing=pairing,calibration=calibration,tolerances=tolerances,
                reference_rows=len(reference),selected_rss_rows=sum(r['selected_rss_rows'] for r in stations),
                all_station_nearest_span_ms=stats(spread),global_minimum_all_station_recorded_span_ms=global_minimum,
                rt=dict(trajectory_samples=len(rt),receivers=5,tx_power_dbm_for_simulation=int(processed['tx_power_dBm']),stored_rss_formula_max_error_db=rt_rss_error),
                gates=dict(real_measured_rss_present=True,recorded_time_proximity_comparable=True,same_packet_id_available=False,
                           receiver_clock_accuracy_established=False,same_transmission_comparison_allowed=False,
                           independent_absolute_power_calibration=False,position_spoof_detection_run=False),
                metadata_conflicts=dict(paper_carrier_frequency_hz=3300000000,filename_carrier_frequency_hz=3320000000,
                                        lw1_stored_carrier_freq_hz=data[0].get('carrier_freq'),paper_usrp='B205',readme_usrp='B210'),
                limits=['Nearest-time rows are not same-packet observations; repeated source samples are not independent.',
                        '20ms capture duration and trustworthy shared clocks would be additional assumptions, not established by a nearest join.',
                        'D3 uses full-trajectory RT-fitted per-channel offsets, with manual LW5 -10dB; not independent hardware dBm calibration.',
                        'No packet sequence, actual per-packet TX power or IQ samples in the exposed numeric fields.',
                        'Five receiver XYZ positions not available as explicit numeric fields; MATLAB MCOS objects were not decoded.',
                        'No MATLAB execution, new RF, real Remote ID or spoof-detection experiment.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--private-out',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();os.umask(0o077)
    repo=Path(__file__).resolve().parents[2]
    if not a.source.resolve().is_relative_to((repo/'captures').resolve()) or not a.private_out.resolve().is_relative_to((repo/'captures').resolve()):
        p.error('Keep raw source/derived mappings in ignored captures/')
    if a.out.exists() or a.private_out.exists():p.error('New output paths required')
    a.out.mkdir(parents=True)
    try:
        result=audit(a.source.resolve(),a.archive.resolve(),a.private_out.resolve())
        for key in ['stations','pairing','calibration','tolerances']:write_table(a.out/(key+'.csv'),result[key])
        result['code_sha256']=sha(Path(__file__))
        (a.out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ['inventory','schemas','stations','pairing','calibration','tolerances']},indent=2))
        return 0
    except Exception as error:
        (a.out/'failure.json').write_text(json.dumps(dict(status='AUDIT_FAILED',error=f'{type(error).__name__}: {error}'),indent=2)+'\n')
        raise


if __name__=='__main__':raise SystemExit(main())
