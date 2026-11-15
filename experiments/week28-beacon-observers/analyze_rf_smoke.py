#!/usr/bin/env python3
"""Summarize owner-private controlled RF logs without publishing raw identifiers.

Counters and exact Vendor content hashes distinguish test phases. They do not
establish one-to-one matching of physical 802.11 transmissions.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'uav'))
from observer_capture import parse_rid_payload


def summarize(rows, receipt, phase, receiver):
    selected = [r for r in rows if r.get('odid_counter') == receipt['counter']]
    matched = []
    for row in selected:
        payload = bytes.fromhex(row['odid_payload_hex'])
        digest = hashlib.sha256(bytes.fromhex('fa0bbc0d') + bytes([receipt['counter']]) + payload).hexdigest()
        if digest != row['vendor_content_digest'] or digest != receipt['vendor_content_sha256']:
            continue
        decoded = parse_rid_payload(payload)
        if {m.message_type for _, m in decoded} != {'basic_id', 'location'}:
            continue
        matched.append(row)
    rssi = [float(r['rssi_dbm']) for r in matched if r.get('rssi_dbm') is not None]
    return dict(phase=phase, receiver=receiver, recorded_scan_observations=len(selected),
                other_counter_rows=len(rows)-len(selected), exact_content_match_and_decode=len(matched),
                receipt_matches_all_selected=bool(selected) and len(selected)==len(matched),
                rssi_count=len(rssi), rssi_min_dbm=min(rssi) if rssi else None,
                rssi_median_dbm=statistics.median(rssi) if rssi else None,
                rssi_max_dbm=max(rssi) if rssi else None,
                physical_packet_match='NOT_ESTABLISHED',
                independent_packet_count=None, packet_reception_rate=None)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--private-dir', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        p.error('use a new output directory; preserve earlier results')
    legs = [('e2e-a4','observer-b','round-a4-b.jsonl'),
            ('e2e-a4','observer-c','round-a4-c.jsonl'),
            ('e2e-a4','pixel8','pixel-final.jsonl'),
            ('e2e-b1','observer-a','round-b1-a.jsonl'),
            ('e2e-b1','observer-c','round-b1-c.jsonl'),
            ('e2e-b1','pixel8','pixel-final.jsonl')]
    receipts = {name: json.loads((args.private_dir/name/'receipt.json').read_text())
                for name in ['e2e-a1','e2e-a2','e2e-a3','e2e-a4','e2e-b1']}
    metrics = []
    for phase, receiver, filename in legs:
        receipt = receipts[phase]
        assert receipt['temporary_ap_removed'] and receipt.get('kernel_interface_type') == 'AP'
        rows = [json.loads(l) for l in (args.private_dir/filename).read_text().splitlines() if l]
        metrics.append(summarize(rows, receipt, phase, receiver))
    trials = []
    for name, receipt in receipts.items():
        phase_metrics = [m for m in metrics if m['phase'] == name]
        received = bool(phase_metrics) and all(m['receipt_matches_all_selected'] for m in phase_metrics)
        trials.append(dict(phase=name, daemon_reported_status=receipt['status'],
                           kernel_ap_checked=receipt.get('kernel_interface_type') == 'AP',
                           temporary_ap_removed=receipt['temporary_ap_removed'],
                           functional_reception_confirmed=received))
    result = dict(source='controlled_real_wifi_test', transmitter_claims='synthetic_test_claims',
                  actual_hardware_receivers=['observer-a','observer-b','observer-c','pixel8'],
                  successful_radio_phases=sum(t['functional_reception_confirmed'] for t in trials),
                  earlier_unsuccessful_attempts=sum(not t['functional_reception_confirmed'] for t in trials),
                  frequency_mhz=2452, same_physical_packet_matching=False,
                  ghostbuster_detection_evaluated=False, metrics=metrics, trials=trials,
                  code_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                               for name in ['experiments/week28-beacon-observers/safe_beacon_tx.py',
                                            'experiments/week28-beacon-observers/analyze_rf_smoke.py']})
    args.out.mkdir(parents=True)
    (args.out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    with (args.out/'reception.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(metrics[0]),lineterminator='\n');writer.writeheader();writer.writerows(metrics)
    print(json.dumps(dict(legs=len(metrics),all_legs_received_and_matched=all(r['receipt_matches_all_selected'] for r in metrics))))


if __name__ == '__main__':
    main()
