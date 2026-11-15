#!/usr/bin/env python3
"""Stream real/private Pi JSONL into CSV or a JSON array without changing raw captures."""
import argparse
import csv
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'uav'))
from wifi_beacon_capture import private_output

FIELDS=['node_id','polled_at_utc','received_at_utc','monotonic_time_us','bssid','rssi_dbm',
        'frequency_mhz','vendor_format','rid_parse_status','rid_parse_reason','cache_stale',
        'claimed_uas_ids','messages','source_annotation','receiver_position','raw_vendor_ie_hex','raw_json']


def csv_value(value):
    if isinstance(value,(dict,list)):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
    if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')):return "'"+value
    return value


def export(inputs,out,kind):
    writer=csv.writer(out,lineterminator='\n') if kind=='csv' else None
    if writer:writer.writerow(FIELDS)
    else:out.write('[\n')
    count=0
    for path in inputs:
        with Path(path).open() as source:
            for line in source:
                row=json.loads(line)
                if not isinstance(row,dict) or row.get('schema_version')!='wifi_observation_v1':
                    raise ValueError('not an observation JSONL; partial export retained')
                raw=json.dumps(row,ensure_ascii=False,separators=(',',':'))
                if writer:writer.writerow([raw if f=='raw_json' else csv_value(row.get(f)) for f in FIELDS])
                else:
                    if count:out.write(',\n')
                    out.write(raw)
                count+=1
    if not writer:out.write('\n]\n')
    return count


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--format',choices=['csv','json'],default='csv');a=p.parse_args()
    with private_output(a.output) as out:count=export(a.input,out,a.format)
    print('EXPORTED_PRIVATE_OBSERVATIONS rows='+str(count))


if __name__=='__main__':main()
