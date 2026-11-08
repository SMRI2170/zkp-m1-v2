"""D1-only real RSS adapter. Coordinates/truth never leave private captures.

Geometric GhostBuster evaluation is fail-closed without receiver coordinates
and a verified shared vertical reference. Nearest-time groups are NOT packets.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from aerpaw21_local import nearest_indices


def load_d1(source, receipt):
    from scipy.io import loadmat
    expected={r['file']:r['sha256'] for r in receipt['inventory']}
    streams={};coordinate_errors=[]
    for station in range(1,6):
        node=f'LW{station}';name=f'D1_RSS_Measurements/{node}/GPS_RSS_data_40m_fs20MHz_{node}.mat'
        path=source/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected[name]:raise ValueError('D1 source changed: '+node)
        fields=['RSS1','RSS2','timestamp_meas','timestamp_gps','GPSx','GPSy','GPSz','mX','mY','mZ']
        d=loadmat(path,variable_names=fields,simplify_cells=True)
        t=np.asarray(d['timestamp_meas']);gps=np.asarray(d['timestamp_gps'])
        nearest_indices(t,t);nearest_indices(gps,gps)
        if t[0]<gps[0] or t[-1]>gps[-1]:raise ValueError('RSS time outside GPS interpolation range')
        errors={out:float(np.max(abs(np.interp(t,gps,d[inp])-d[out]))) for inp,out in [('GPSx','mX'),('GPSy','mY'),('GPSz','mZ')]}
        if max(errors.values())>1.e-9:raise ValueError('Stored GPS interpolation cannot be reproduced')
        coordinate_errors.append(dict(station=node,interpolation_max_error=errors))
        if any(len(d[k])!=len(t) for k in ['RSS1','RSS2','mX','mY','mZ']):raise ValueError('Mismatched D1 rows')
        values=np.c_[d['RSS1'],d['RSS2']]
        if not np.isfinite(values).all():raise ValueError('Unexpected raw missing RSS; do not silently impute')
        streams[node]=dict(time=t,rss=values,lon=np.asarray(d['mX']),lat=np.asarray(d['mY']),z=np.asarray(d['mZ']),
                           source_row=np.arange(len(t)))
    origin=float(streams['LW1']['time'][0]);end=max(float(s['time'][-1]) for s in streams.values())
    duration=end-origin
    # Disjoint chronological blocks with ~46-second embargoes, same flight.
    for s in streams.values():
        elapsed=s['time']-origin;fraction=elapsed/duration
        role=np.full(len(elapsed),'embargo',dtype='<U10')
        role[(fraction>=0)&(fraction<.4)]='train'
        role[(fraction>=.45)&(fraction<.65)]='calibrate'
        role[(fraction>=.7)&(fraction<=1)]='evaluate'
        s.update(elapsed=elapsed,role=role)
    return streams,dict(source='D1_measured_RSS_GPS',duration_s=duration,coordinate_errors=coordinate_errors,
                        independent_flights=1,split_fractions=dict(train=[0,.4],calibrate=[.45,.65],evaluate=[.7,1]),
                        embargo_fraction=.05,raw_rows=sum(len(s['time']) for s in streams.values()))


def local_xy(lon,lat,origin_lon,origin_lat):
    """WGS84 ellipsoid at h=0 -> local east/north, not a measured altitude.

    z is supplied separately in a VERIFIED common local vertical reference.
    Avoid guessing that an AGL value is an ellipsoidal height.
    """
    a=6378137.;e2=6.6943799901413165e-3
    def ecef(lo,la):
        lo=np.deg2rad(lo);la=np.deg2rad(la);n=a/np.sqrt(1-e2*np.sin(la)**2)
        return np.stack([n*np.cos(la)*np.cos(lo),n*np.cos(la)*np.sin(lo),n*(1-e2)*np.sin(la)],axis=-1)
    delta=ecef(np.asarray(lon),np.asarray(lat))-ecef(np.asarray(origin_lon),np.asarray(origin_lat))
    lo=np.deg2rad(origin_lon);la=np.deg2rad(origin_lat)
    east=np.array([-np.sin(lo),np.cos(lo),0.]);north=np.array([-np.sin(la)*np.cos(lo),-np.sin(la)*np.sin(lo),np.cos(la)])
    return np.stack([delta@east,delta@north],axis=-1)


def geometry(streams,metadata_path):
    if metadata_path is None:return None,dict(status='MISSING_RECEIVER_METADATA',reason='Five verified receiver positions and shared vertical reference are required')
    meta=json.loads(metadata_path.read_text())
    if meta.get('horizontal_crs')!='EPSG:4326' or meta.get('vertical_reference')!='shared_local_m':raise ValueError('Unsupported/unverified coordinate references')
    if not meta.get('receiver_positions_verified') or not meta.get('uav_z_same_reference_verified') or not meta.get('provenance'):
        raise ValueError('Receiver geometry/datum provenance not verified')
    if set(meta.get('receivers',{}))!=set(streams):raise ValueError('All LW1..LW5 required')
    first=streams['LW1'];lo=float(first['lon'][0]);la=float(first['lat'][0]);receivers=[]
    for name,s in streams.items():
        r=meta['receivers'][name]
        values=np.array([r['longitude'],r['latitude'],r['z_same_reference_m']],float)
        if not np.isfinite(values).all() or abs(values[0])>180 or abs(values[1])>90:raise ValueError('Invalid geodetic receiver')
        xy=local_xy(values[0],values[1],lo,la);receivers.append([*xy,values[2]])
        s['xyz']=np.c_[local_xy(s['lon'],s['lat'],lo,la),s['z']]
    receivers=np.asarray(receivers)
    if np.linalg.norm(receivers[:,:2],axis=1).max()>5000:raise ValueError('Receiver outside validated local projection scale')
    if min(np.linalg.norm(receivers[i]-receivers[j]) for i in range(5) for j in range(i))<1:raise ValueError('Duplicate receiver positions')
    return receivers,dict(status='USER_SUPPLIED_VERIFIED_METADATA',metadata_sha256=hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
                          projection='WGS84 h=0 local east/north + separately verified common local z; planar horizontal approximation',
                          not_verified_by='Neither a cryptographic attestation nor an independent resurvey')


def source_mask(s,rate,seed):
    # A repeated source row stays missing in every reused group and both ch.
    digest=hashlib.sha256(str(seed).encode()+s['time'].tobytes()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8],'big')).random(len(s['time']))>=rate


def groups(streams,k,role,max_span_s,lag_s=0.,missing=0.,seed=801):
    """Correctly timestamped different observations; not clock corruption.

    lag selects data at later physical measurement times. Retain actual times;
    an out-of-recording target is unavailable, never clamped to the last sample.
    """
    if k not in range(1,6) or not 0<=missing<=1 or max_span_s<0 or lag_s<0:raise ValueError('Invalid grouping condition')
    names=list(streams)[:k];reference=streams['LW1'];indices=np.flatnonzero(reference['role']==role)
    t=reference['time'][indices];selected=[];present=[];actual=[]
    for i,name in enumerate(names):
        s=streams[name];target=t+lag_s*i/max(1,k-1)
        ix=nearest_indices(target,s['time'])
        valid=(target>=s['time'][0])&(target<=s['time'][-1])&(s['role'][ix]==role)&source_mask(s,missing,seed)[ix]
        selected.append(ix);present.append(valid);actual.append(s['time'][ix])
    selected=np.asarray(selected).T;present=np.asarray(present).T;actual=np.asarray(actual).T
    span=np.ptp(actual,axis=1)
    valid=present.all(axis=1)&(span<=max_span_s)
    # No source row may count as a new accepted observation twice.
    used=[set() for _ in names];accepted=np.zeros(len(indices),dtype=bool)
    for i in np.flatnonzero(valid):
        if any(int(selected[i,j]) in used[j] for j in range(k)):continue
        accepted[i]=True
        for j in range(k):used[j].add(int(selected[i,j]))
    return dict(reference_indices=indices,selected=selected,actual_times=actual,present=present,
                accepted=accepted,span_s=span,physical_same_packet=False,
                total=len(indices),candidate_complete=int(valid.sum()),unique_complete=int(accepted.sum()),
                source_reuse_removed=int(valid.sum()-accepted.sum()))
