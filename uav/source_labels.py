"""Local operator annotations only. IDs/MACs are spoofable, never authentication."""
import json
import os
from pathlib import Path
import re
import stat


def validate_rules(rules):
    if not isinstance(rules,list) or len(rules)>32:raise ValueError('source registry must contain at most 32 rules')
    for r in rules:
        if not isinstance(r,dict):raise ValueError('source rule must be an object')
        if r.get('role') not in ['drone','onboard_pi','unknown']:raise ValueError('invalid source role')
        if not isinstance(r.get('label'),str) or not 1<=len(r['label'])<=40 or any(ord(c)<32 for c in r['label']):raise ValueError('invalid local label')
        if not r.get('uas_id') and not r.get('bssid'):raise ValueError('an observed BSSID or claimed ID is required')
        if r.get('uas_id') and (len(r['uas_id'])>20 or not all(32<=ord(c)<127 for c in r['uas_id'])):raise ValueError('invalid claimed ID')
        if r.get('bssid') and not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',r['bssid']):raise ValueError('invalid observed BSSID')
    return rules


def load_rules(path):
    if path is None:return []
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        info=os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>16384:
            raise ValueError('source registry must be an owner-private regular file <=16KiB')
        return validate_rules(json.load(f))


def classify(bssid,uas_ids,rules=()):
    ids=set(uas_ids);matches=[]
    for r in rules:
        if r.get('bssid') and r['bssid'].lower()!=bssid.lower():continue
        if r.get('uas_id') and r['uas_id'] not in ids:continue
        score=int(bool(r.get('bssid')))+int(bool(r.get('uas_id')))
        matches.append((score,r))
    if matches:
        maximum=max(m[0] for m in matches);best=[r for score,r in matches if score==maximum]
        choices={(r['role'],r['label']) for r in best}
        if len(choices)>1:return dict(role='unknown',label='登録競合',basis='conflicting_local_rules',identity_verified=False)
        r=best[0]
        return dict(role=r['role'],label=r['label'],basis='configured_id_and_bssid' if r.get('uas_id') and r.get('bssid') else
                    'configured_claimed_id' if r.get('uas_id') else 'configured_bssid',identity_verified=False)
    if any(i.startswith('PI-RID-') for i in ids):
        return dict(role='onboard_pi',label='Piマーカー（申告）',basis='unverified_test_marker',identity_verified=False)
    return dict(role='unknown',label='未登録',basis='none',identity_verified=False)


def text_line(row):
    # JSON escaping keeps a single physical line even with untrusted broadcast strings.
    return ' '.join(k+'='+json.dumps(v,ensure_ascii=False,separators=(',',':')) for k,v in [
        ('received_at_utc',row.get('received_at_utc')),('bssid',row.get('bssid')),
        ('source',row.get('source_annotation')),('claimed_uas_ids',row.get('claimed_uas_ids',[])),
        ('rssi_dbm',row.get('rssi_dbm')),('frequency_mhz',row.get('frequency_mhz')),
        ('parse_status',row.get('rid_parse_status')),('raw_vendor_ie_hex',row.get('raw_vendor_ie_hex'))])
