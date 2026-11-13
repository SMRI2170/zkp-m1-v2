#!/usr/bin/env python3
"""Operator source annotation. No aircraft/observer authentication or automatic DJI claims."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'uav'))
from source_labels import load_rules,validate_rules


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--role',choices=['drone','onboard_pi','unknown'],required=True)
    p.add_argument('--label',required=True);p.add_argument('--uas-id');p.add_argument('--bssid');a=p.parse_args()
    rule=dict(role=a.role,label=a.label)
    if a.uas_id:rule['uas_id']=a.uas_id
    if a.bssid:rule['bssid']=a.bssid.lower()
    validate_rules([rule]);rules=load_rules(a.config) if a.config.exists() else []
    rules=[r for r in rules if (r.get('uas_id'),r.get('bssid','').lower() or None)!=(rule.get('uas_id'),rule.get('bssid'))]+[rule]
    validate_rules(rules);os.umask(0o077)
    a.config.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if a.config.is_symlink() or a.config.parent.stat().st_mode&0o077:raise ValueError('owner-private registry directory required')
    tmp=a.config.with_name('.receiver-sources-'+uuid.uuid4().hex)
    with tmp.open('x') as f:json.dump(rules,f,ensure_ascii=False);f.write('\n')
    tmp.replace(a.config)
    print('SOURCE_ANNOTATION_SAVED_NOT_IDENTITY_VERIFICATION')


if __name__=='__main__':main()
