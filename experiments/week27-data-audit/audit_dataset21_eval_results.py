"""Offline accounting for real-input experiments; no phantom detection rates."""
import csv
import hashlib
import json
from pathlib import Path


def validate(folder):
    def read(name):
        with (folder/name).open() as f:return list(csv.DictReader(f))
    x=json.loads((folder/'summary.json').read_text())
    assert x['raw_source']=='D1_real_measured_RSS' and not x['d3_used'] and x['new_rf_runs']==0
    assert x['source']['raw_rows']==16618 and x['source']['independent_flights']==1
    for item in x['source']['coordinate_errors']:
        assert max(item['interpolation_max_error'].values())<1.e-9
    assert x['source']['split_fractions']==dict(train=[0,.4],calibrate=[.45,.65],evaluate=[.7,1])
    for name,digest in x['code_sha256'].items():
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()==digest
    availability=read('availability.csv');assert len(availability)==x['availability_cells']==210
    for r in availability:
        total,candidate,unique,reuse=(int(r[k]) for k in ['reference_rows','candidate_complete','unique_complete','source_reuse_removed'])
        assert 0<=unique<=candidate<=total and unique+reuse==candidate
        assert abs(float(r['candidate_rate'])-unique/total)<1.e-12
        assert 0<=int(r['complete_windows'])<=int(r['reference_windows'])
        assert r['physical_same_packet']=='False'
    injections=read('synthetic-input-checks.csv');assert len(injections)==20
    assert {int(r['offset_m']) for r in injections}=={20,50,100,200}
    assert sum(int(r['observations']) for r in injections)==4*16618
    assert all(float(r['maximum_displacement_error_m'])<1.e-8 and r['position_only_measured_rss_unchanged']=='True' for r in injections)
    if not x['geometric_detection_executed']:
        assert x['status']=='INPUT_EXPERIMENT_COMPLETE_GEOMETRIC_EVALUATION_NOT_RUN'
        rows=read('metrics.csv');assert all(r['status'].startswith('NOT_RUN') for r in rows)
        if x['geometry_gate']['status']=='MISSING_RECEIVER_METADATA':
            assert len(rows)==80 and all(r['status']=='NOT_RUN_MISSING_RECEIVER_GEOMETRY' for r in rows)
        assert all(r['fpr']==r['tpr']==r['und_rate']=='' for r in rows)
        assert not (folder/'figures/05_detection.png').exists()
        assert (folder/'figures/position_detection_graph_NOT_GENERATED.md').exists()
    if (folder/'manifest.json').exists():
        for name,digest in json.loads((folder/'manifest.json').read_text())['sha256'].items():
            assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
    print('Dataset-21 input experiment evidence verified: source/embargo, 210 availability cells, synthetic inputs and blank NOT_RUN detection rates. No raw data read in CI.')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);validate(p.parse_args().folder)
