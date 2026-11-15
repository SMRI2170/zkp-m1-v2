#!/usr/bin/env python3
"""Stream sensor JSONL into a new owner-private CSV; missing values stay empty, not zero."""
import argparse
import csv
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'uav'))
from wifi_beacon_capture import private_output

FIELDS=['sensor_session','sequence','host_utc','host_monotonic_s','gps_valid','gps_reason','gps_age_s',
        'latitude','longitude','gps_altitude_msl_m','gps_geoid_separation_m','gps_altitude_ellipsoid_m',
        'bme_valid','bme_reason','pressure_hpa','temperature_c','humidity_percent','pressure_altitude_isa_m',
        'relative_boot_height_m','reference_pressure_hpa','reference_kind']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    count=0
    with private_output(a.output) as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        for file in a.input:
            with file.open() as source:
                for line in source:
                    r=json.loads(line);g=r['gps'];b=r['bme280']
                    row={k:r.get(k) for k in FIELDS[:4]}
                    row.update(gps_valid=g.get('valid'),gps_reason=g.get('reason'),gps_age_s=g.get('age_s'),latitude=g.get('latitude'),longitude=g.get('longitude'),
                        gps_altitude_msl_m=g.get('altitude_msl_m'),gps_geoid_separation_m=g.get('geoid_separation_m'),gps_altitude_ellipsoid_m=g.get('altitude_ellipsoid_m'),bme_valid=b.get('valid'),bme_reason=b.get('reason'))
                    row.update({k:b.get(k) for k in FIELDS[14:]});writer.writerow(row);count+=1
    print('CSV rows='+str(count)+' (private field data; not for Git)')


if __name__=='__main__':main()
