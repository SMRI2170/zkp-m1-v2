"""Verify public Dataset-21 audit aggregates; never reopen raw GPS/RSS in CI."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def validate(folder):
    x=json.loads((folder/'summary.json').read_text())
    assert x['status']=='AUDITED_SAME_TRANSMISSION_NOT_ESTABLISHED'
    assert x['archive']['sha256']=='ff930df7158d4e9a4d2a038d225fb805b88031adef5628137bd3754ad2bd9ae1'
    assert x['archive']['all_extracted_files_match'] and x['archive']['crc_verified']
    assert x['archive']['file_count']==len(x['inventory'])==16
    assert hashlib.sha256(Path(__file__).with_name('aerpaw21_local.py').read_bytes()).hexdigest()==x['code_sha256']
    assert len(x['stations'])==len(x['pairing'])==5
    assert sum(r['selected_rss_rows'] for r in x['stations'])==x['selected_rss_rows']==16618
    assert x['reference_rows']==3530 and x['rt']['trajectory_samples']==3530
    for row in x['stations']:
        assert row['finite_rss1']==row['finite_rss2']==row['selected_rss_rows']
        assert row['selected_raw_mapping_exact'] and row['common_gps_reference']
    for row in x['pairing']:
        assert row['distinct_source_rows']+row['reused_reference_rows']==row['reference_rows']==3530
    assert len(x['calibration'])==10
    for row in x['calibration']:
        assert row['constant_offset_max_error_db']<1.e-8
        assert not row['physical_absolute_calibration_established']
        if row['manual_override']:assert row['station']=='LW5' and row['d3_offset_db']==-10
        else:assert abs(row['d3_offset_db']-row['rt_fitted_optimum_db'])<1.e-8
    assert x['global_minimum_all_station_recorded_span_ms']==21
    assert not x['gates']['same_transmission_comparison_allowed'] and not x['gates']['position_spoof_detection_run']
    assert all(not r['same_transmission_verified'] for r in x['tolerances'])
    assert all(r['nearest_time_candidate_rows']==0 for r in x['tolerances'] if r['max_recorded_span_ms']<=20)
    for name in ['stations','pairing','calibration','tolerances']:
        with (folder/(name+'.csv')).open() as f:rows=list(csv.DictReader(f))
        assert rows==[{k:'' if v is None else str(v) for k,v in r.items()} for r in x[name]],name
    manifest=folder/'manifest.json'
    if manifest.exists():
        for name,digest in json.loads(manifest.read_text())['sha256'].items():
            assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
    print('Dataset-21 audit verified: archive, 5 stations, nearest-time reuse, offsets and same-transmission gate. Raw data not read in CI.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);validate(p.parse_args().folder)
