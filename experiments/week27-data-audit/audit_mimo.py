"""Sparse real-UAV CSI acquisition/audit. CSI gain is NOT RSSI in dBm.

Raw data/positions remain in ignored captures. Exports contain aggregates only.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.request
import numpy as np

RECORD = 'https://zenodo.org/api/records/15655702'
KEYS = ['20240514_122613_n64_l1_s150000_sr2_f2.610G_g25.0',
        '20240514_124034_n64_l1_s150000_sr2_f2.610G_g25.0',
        '20240514_125316_n64_l1_s150000_sr2_f2.610G_g25.0']
INDICES = list(range(0, 150000, 5000)) + [149999]
SYMBOL_BYTES = 64 * 100 * 4


def sha(data): return hashlib.sha256(data).hexdigest()


def private_file(path, data):
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Preserving different existing source: ' + path.name)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream: stream.write(data)
    path.chmod(0o600)


def fetch(raw):
    with urllib.request.urlopen(RECORD, timeout=20) as response:
        metadata_bytes = response.read(1024 * 1024 + 1)
    if len(metadata_bytes) > 1024 * 1024: raise ValueError('Metadata too large')
    metadata = json.loads(metadata_bytes)
    # Never execute downloaded scripts; read them only as documentation.
    inventory = {'metadata': {'license': metadata['metadata'].get('license')},
                 'files': sorted([{k:f[k] for k in ('key','size','checksum','links')} for f in metadata['files']], key=lambda f:f['key'])}
    private_file(raw / 'zenodo-inventory.json', json.dumps(inventory,sort_keys=True).encode())
    for item in metadata['files']:
        name = item['key']
        if not (name.endswith('.csv') or name in ('README.txt','binary_interpreter.py','prepare_data.py')):
            continue
        if item['size'] > 3_000_000: raise ValueError('Unexpected small file size')
        destination = raw / name
        if destination.exists(): data = destination.read_bytes()
        else:
            with urllib.request.urlopen(item['links']['self'], timeout=20) as response:
                data = response.read(item['size'] + 1)
        if len(data) != item['size'] or 'md5:' + hashlib.md5(data).hexdigest() != item['checksum']:
            raise ValueError('Small-file size/hash mismatch: ' + name)
        private_file(destination, data)
    records = []
    for key in KEYS:
        item = next(x for x in metadata['files'] if x['key'] == key)
        for index in INDICES:
            start = index * SYMBOL_BYTES; end = start + SYMBOL_BYTES - 1
            path = raw / (key + '.symbol-' + str(index))
            if path.exists():
                data = path.read_bytes()
            else:
                request = urllib.request.Request(item['links']['self'], headers={'Range':f'bytes={start}-{end}'})
                with urllib.request.urlopen(request, timeout=20) as response:
                    if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{item["size"]}':
                        raise ValueError('Range ignored/mismatched; refusing full binary')
                    data = response.read(SYMBOL_BYTES + 1)
            if len(data) != SYMBOL_BYTES: raise ValueError('Invalid fragment size')
            private_file(path, data)
            records.append(dict(file=key,symbol=index,bytes=len(data),sha256=sha(data)))
    private_file(raw/'verified-fragments.json',json.dumps(records,indent=2).encode())


def channel_gain_db(payload):
    if len(payload) != SYMBOL_BYTES: raise ValueError('Incomplete symbol')
    values = np.frombuffer(payload, dtype='>i2').astype(np.float64) / 256.0
    # Public interpreter interleaves Q,I. Total power is invariant to antenna permutation.
    power = float(np.sum(values**2))
    if power <= 0 or not np.isfinite(power): raise ValueError('Nonpositive/nonfinite channel gain')
    return 10.0 * np.log10(power)


def nearest_time(times, stamp, tolerance=.15):
    if not len(times) or stamp < times[0] or stamp > times[-1]: return None
    at = int(np.searchsorted(times, stamp))
    candidates = [i for i in (at-1, at) if 0 <= i < len(times)]
    chosen = min(candidates, key=lambda i: abs(times[i]-stamp))
    return chosen if abs(times[chosen]-stamp) <= tolerance else None


def consolidate_telemetry(times, xyz):
    """Explicitly consolidate exact repeated positions; quarantine conflicts."""
    if np.any(np.diff(times) < 0) or not np.isfinite(times).all() or not np.isfinite(xyz).all():
        raise ValueError('Nonfinite or backwards telemetry')
    unique, starts, counts = np.unique(times, return_index=True, return_counts=True)
    kept=[]; positions=[]; conflicts=[]; redundant=0
    for stamp, start, count in zip(unique, starts, counts):
        block=xyz[start:start+count]
        if np.all(block == block[0]):
            kept.append(stamp); positions.append(block[0]); redundant += count-1
        else:
            conflicts.append(stamp)
    return np.array(kept),np.asarray(positions),np.array(conflicts),int(redundant)


def epoch(value):
    return dt.datetime.fromisoformat(value).replace(tzinfo=dt.timezone.utc).timestamp()


def audit(raw):
    metadata = json.loads((raw/'zenodo-inventory.json').read_text())
    trajectories = []; inventory = []; hashes = []
    for path in sorted(raw.glob('*.csv')):
        data = path.read_bytes()
        item = next(f for f in metadata['files'] if f['key'] == path.name)
        if 'md5:' + hashlib.md5(data).hexdigest() != item['checksum']: raise ValueError('CSV mismatch')
        rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
        # Same relative-time reconstruction as public prepare_data.py; do not adjust clocks to force joins.
        first = epoch(rows[0]['datetime(utc)']); ms = float(rows[0]['time(millisecond)'])
        times = np.array([first + (float(r['time(millisecond)'])-ms)/1000 for r in rows])
        xyz = np.array([[float(r[k]) for k in ('latitude','longitude','altitude(m)')] for r in rows])
        raw_times=times.copy()
        times,xyz,conflicts,redundant=consolidate_telemetry(times,xyz)
        trajectories.append((times, xyz, conflicts))
        inventory.append(dict(source_file=path.name,rows=len(rows),span_s=float(times[-1]-times[0]),
                              median_positive_interval_s=float(np.median(np.diff(raw_times)[np.diff(raw_times)>0])),
                              repeated_timestamp_rows=int(np.sum(np.diff(raw_times)==0)),
                              identical_redundant_rows_consolidated=redundant,
                              conflicting_timestamp_groups_quarantined=len(conflicts)))
        hashes.append(dict(file=path.name,bytes=len(data),sha256=sha(data),published_md5_verified=True))
    fragment_list=json.loads((raw/'verified-fragments.json').read_text())
    output=[]
    for key in KEYS:
        start=dt.datetime.strptime(key[:15],'%Y%m%d_%H%M%S').replace(tzinfo=dt.timezone.utc).timestamp()
        match_counts=[]; offsets=[]; powers=[]; coords=[]; zero_symbols=0
        for symbol in INDICES:
            path=raw/(key+'.symbol-'+str(symbol));data=path.read_bytes()
            record=next(r for r in fragment_list if r['file']==key and r['symbol']==symbol)
            if sha(data)!=record['sha256']:raise ValueError('Fragment hash mismatch')
            if not any(data): zero_symbols+=1
            else: powers.append(channel_gain_db(data))
            stamp=start+symbol*.001
            matches=[]
            for times,xyz,conflicts in trajectories:
                if len(conflicts) and np.min(np.abs(conflicts-stamp)) <= .15:
                    matches.extend([(None,None),(None,None)]);continue
                i=nearest_time(times,stamp)
                if i is not None:matches.append((abs(times[i]-stamp),xyz[i]))
            match_counts.append(len(matches))
            if len(matches)==1:offsets.append(matches[0][0]);coords.append(matches[0][1])
        output.append(dict(source_file=key,sampled_symbols=len(INDICES),valid_channel_symbols=len(powers),zero_channel_symbols=zero_symbols,
                           uniquely_joined=sum(n==1 for n in match_counts),unmatched=sum(n==0 for n in match_counts),
                           ambiguous=sum(n>1 for n in match_counts),
                           max_join_offset_s=max(offsets) if offsets else None,
                           channel_gain_db_min=float(min(powers)) if powers else None,channel_gain_db_max=float(max(powers)) if powers else None,
                           telemetry_altitude_span_m=float(np.ptp(np.array(coords)[:,2])) if coords else None))
    return dict(scope='Sparse real-UAV CSI data audit; not RSSI or attack detection evaluation',
                source=RECORD,license=metadata['metadata'].get('license'),
                clock_assumption='Binary filename interpreted as UTC following public prepare_data.py; no independent clock calibration',
                max_join_tolerance_s=.15,raw_csv_count=len(inventory),raw_telemetry_rows=sum(r['rows'] for r in inventory),
                full_csv_files_verified=True,full_binary_checksums_verified=False,
                sparse_samples=sum(x['sampled_symbols'] for x in output),sparse_bytes=sum(r['bytes'] for r in fragment_list),
                provenance=dict(csv=hashes,fragments=fragment_list),inventory=inventory,channel_records=output,
                gate='C_PROPAGATION_ONLY',
                limits=['CSI gain is not receiver RSSI in dBm','64 antennas at one base station are not 64 independent receiver sites',
                        'No antenna phase/array calibration or AoA implemented','Sparse sample selection is not a full-flight performance evaluation',
                        'Identical repeated telemetry consolidated explicitly; conflicting timestamp groups quarantined and near-conflict joins rejected',
                        'No residual or detection result is produced by this audit'])


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--fetch',action='store_true');args=p.parse_args()
    if 'captures' not in args.raw.resolve().parts:raise ValueError('Raw source must stay under captures')
    args.raw.mkdir(parents=True,exist_ok=True);args.raw.chmod(0o700)
    if args.fetch:fetch(args.raw)
    for f in args.raw.iterdir():
        if f.is_file() and f.stat().st_mode & 0o077:raise ValueError('Raw files require owner-only permissions')
    report=audit(args.raw)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('gate','raw_csv_count','raw_telemetry_rows','sparse_samples','channel_records')},indent=2))
