"""Anonymous analysis helpers shared by Android/Pi controlled-source studies."""
import math


def study_ids(row):
    values=set(x for x in row.get('claimed_uas_ids') or [] if isinstance(x,str))
    values.update(x['uas_id'] for x in row.get('rid_messages') or [] if isinstance(x,dict) and isinstance(x.get('uas_id'),str))
    return values


def in_phase(value,start,end):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and start+100000<=value<end-100000


def target_counts(rows,start,end,target):
    selected=[r for r in rows if in_phase(r.get('monotonic_time_us'),start,end) and target in study_ids(r)]
    fresh=[r for r in selected if r.get('cache_stale') is False]
    timestamps=sorted({r['monotonic_time_us'] for r in fresh})
    bins=[0]*max(1,round((end-start)/5e6))
    for t in timestamps:
        i=int((t-start)//5e6)
        if i<len(bins):bins[i]+=1
    return dict(target_records=len(selected),target_fresh_records=len(fresh),
                target_distinct_vendor_contents=len({r['vendor_content_digest'] for r in fresh if r.get('vendor_content_digest')}),
                target_distinct_observation_timestamps=len(timestamps),target_new_timestamp_bins_5s=bins,
                target_observed_span_s=(timestamps[-1]-timestamps[0])/1e6 if timestamps else None,
                target_rssi_present_records=sum(isinstance(r.get('rssi_dbm'),(int,float)) and math.isfinite(r['rssi_dbm']) for r in selected))


def doze_verified(text):
    import re
    return bool(re.search(r'\bmState=IDLE\b',text))
