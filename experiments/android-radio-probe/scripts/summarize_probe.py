"""Whitelist-only public aggregate report. Raw targets, angles, IEs never copied."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def summarize(raw, apk):
    for name in ('summary.json','observations.jsonl'):
        if (raw/name).stat().st_mode & 0o077:raise ValueError('Raw data must be owner-only')
    s=json.loads((raw/'summary.json').read_text())
    events=[json.loads(line) for line in (raw/'observations.jsonl').read_text().splitlines()]
    keys=('model','android','sdk','running','active_duration_s','wifi_scan_requests','wifi_scan_accepted',
          'wifi_fresh_broadcasts','wifi_rid_observations','ble_packets','ble_rid_observations','heading_count',
          'rotation_samples','fitted_targets','pose_rejected','target_limit_rejections')
    result={k:s.get(k) for k in keys}
    fresh=[r for r in events if r['type']=='wifi_observation' and r['fresh_broadcast'] and r['unique_timestamp']]
    caps=s['capabilities']
    cap_keys=('availability','uwb_capabilities_present','cs_capabilities_present','uwb_azimuth','uwb_elevation')
    api=caps.get('ranging_api')
    rf_observed=s.get('ble_packets',0)>0 or len(fresh)>0
    result.update(schema='rid-radio-probe-public-v1',
        scope='Physical RF reception smoke test, not AoA accuracy or aircraft authentication' if rf_observed else 'Launch/capability check only; no RF reception established in this run',
        rf_reception_observed=rf_observed,
        fresh_unique_wifi_observations=len(fresh),
        fresh_information_elements=sum(len(r['ies']) for r in fresh),
        fresh_vendor_information_elements=sum(ie['id']==221 for r in fresh for ie in r['ies']),
        wifi_all_rows_including_cache=s['wifi_rows_including_cache'],
        total_information_elements_including_cache=s['wifi_information_elements'],
        total_vendor_elements_including_cache=s['wifi_vendor_elements'],
        sensor_rotation_available=caps.get('rotation_vector'),uwb_feature=caps.get('uwb_feature'),
        ranging_api={k:api[k] for k in cap_keys if k in api} if api else None,
        errors=[{k:e[k] for k in ('stage','error','code') if k in e} for e in s['errors']],
        active_segments=[dict(duration_s=r['duration_s'],reason=r.get('reason','not_recorded')) for r in events if r['type']=='stop'],
        heading_fit_status_counts={status:sum(t['estimate']['status']==status for t in s['targets'])
                                  for status in sorted({t['estimate']['status'] for t in s['targets']})},
        heldout_physical_validations=sum(r['type']=='heldout_validation' for r in events),
        accuracy_established=False,
        tested_apk=(json.loads((raw/'apk-info.json').read_text()) if (raw/'apk-info.json').exists() else None),
        tested_apk_provenance='recorded before install' if (raw/'apk-info.json').exists() else 'not recorded in this early run; do not equate it with current build',
        current_build_apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),current_build_apk_size_bytes=apk.stat().st_size,
        parser_scope='structural ODID framing only, no authentication or full field validation',
        wifi_scope='Android scan result information elements; not raw monitor-mode beacon frames',
        no_rid_scope='No RID-format messages in this run; does not establish receiver incompatibility')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--apk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=summarize(args.raw,args.apk)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
