"""Audit OMNeT++ ETV vectors using simulator event numbers, never row indices.

Management enqueue time is not PHY airtime. Missing RSSI remains null. Packet
tree IDs identify physical transmission candidates; claimed serial/time do not.
Truth fields are audit-only and must not enter future detector inputs.
"""
import csv
from collections import Counter
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import shlex


def read_vectors(path):
    definitions, events = {}, {}
    runs = 0
    with Path(path).open() as stream:
        for line in stream:
            if line.startswith('run '):
                runs += 1
                if runs > 1:
                    raise ValueError('Expected a single run per vector file')
            elif line.startswith('vector '):
                _, index, module, name, columns = shlex.split(line)
                if columns != 'ETV':
                    raise ValueError('Require event-number/time/value vectors (ETV)')
                if index in definitions:
                    raise ValueError('Duplicate vector definition')
                definitions[index] = (module, name)
            elif line[:1].isdigit():
                parts = line.split()
                if len(parts) != 4 or parts[0] not in definitions:
                    raise ValueError('Malformed vector record')
                index, event, time, value = parts
                module, name = definitions[index]
                # Unrelated MAC/mobility statistics are not our evidence.
                if not re.search(r'\.host\[\d+\]\.wlan\[0\]\.(mgmt|radio\.transmitter)$', module) and not re.search(r'\.gcs\[\d+\]$', module):
                    continue
                key = (module, int(event), Decimal(time))
                fields = events.setdefault(key, {})
                if name in fields:
                    if '.gcs[' not in module:
                        raise ValueError('Repeated field in one event; refusing ambiguous alignment')
                    old = fields[name]
                    fields[name] = (old if isinstance(old, list) else [old]) + [float(value)]
                else:
                    fields[name] = float(value)
    # The GCS may process several groups in a single OMNeT++ event. Only our
    # complete, fixed-shape callback with an explicit sequence can disambiguate
    # that case. A missing field/counter is an error, never an index shift.
    for key, fields in list(events.items()):
        if '.gcs[' not in key[0] or not any(isinstance(v, list) for v in fields.values()):
            continue
        counters = fields.get('callback_id')
        if not isinstance(counters, list) or len(set(counters)) != len(counters):
            raise ValueError('Repeated GCS event requires unique callback_id values')
        required = {'packet_id','report_count','claimed_timestamp_ms','claimed_serial','callback_id'}
        if not required.issubset(fields) or any(not isinstance(v,list) or len(v) != len(counters) for v in fields.values()):
            raise ValueError('Incomplete GCS callback fields; refusing ordinal alignment')
        del events[key]
        for i, callback in enumerate(counters):
            events[(key[0], (key[1], integer(callback)), key[2])] = {name: values[i] for name,values in fields.items()}
    return events


def finite(value):
    return value if value is not None and math.isfinite(value) else None


def integer(value):
    value = finite(value)
    if value is None or value != int(value) or abs(value) >= 2**53:
        raise ValueError('Invalid or imprecise packet/identifier value')
    return int(value)


def xyz(fields, prefix):
    result = [finite(fields.get(prefix + axis + ' Coordinate')) for axis in ('X', 'Y', 'Z')]
    return result if all(v is not None for v in result) else None


def normalize(events, case, config):
    tx, rx, gcs = {}, [], []
    for (module, event, time), fields in events.items():
        if '.gcs[' in module:
            if 'packet_id' in fields:
                gcs.append(dict(tx_event_id=integer(fields['packet_id']), sim_time=float(time),
                                report_count=integer(fields['report_count']),
                                claimed_timestamp=finite(fields.get('claimed_timestamp_ms')),
                                serial=finite(fields.get('claimed_serial'))))
            continue
        node = int(re.search(r'\.host\[(\d+)\]', module).group(1))
        if 'Transmission Packet ID' in fields:
            packet = integer(fields['Transmission Packet ID'])
            if packet in tx:
                raise ValueError('Duplicate TX packet ID')
            tx[packet] = dict(tx_event_id=packet, tx_node_id=node, tx_time=float(time),
                              true_tx_xyz=xyz(fields, 'Transmission My '),
                              claimed_xyz=xyz(fields, 'Transmission '),
                              tx_power_dbm_truth_only=finite(fields.get('Requested PHY Power', fields.get('Transmission Power'))),
                              tx_power_source='packet_tag_request' if 'Requested PHY Power' in fields else 'configured_parameter_sample',
                              is_spoofed=integer(fields.get('Transmission Is Spoofed')))
        if 'Packet ID' in fields:
            rx.append(dict(tx_event_id=integer(fields['Packet ID']), rx_event_id=f'{node}:{event}',
                           rx_time=float(time), rx_node_id=node,
                           rx_signal_start_time=finite(fields.get('Reception Time')),
                           rx_xyz=xyz(fields, 'Reception My '),
                           rx_claimed_xyz=xyz(fields, 'Reception '),
                           serial=integer(fields['Serial Number']) if 'Serial Number' in fields else None,
                           claimed_timestamp=finite(fields.get('Reception Timestamp')),
                           rssi_dbm=finite(fields.get('Reception Power'))))
    if not tx:
        raise ValueError('No TX events: no communication evidence')
    rows, seen = [], set()
    for observation in rx:
        packet, node = observation['tx_event_id'], observation['rx_node_id']
        if packet not in tx:
            raise ValueError('RX has no exact TX packet-ID match')
        if (packet, node) in seen:
            raise ValueError('Duplicate RX for one TX/receiver opportunity')
        seen.add((packet, node))
        truth = tx[packet]
        if node not in config['rx_hosts'] or node == truth['tx_node_id']:
            raise ValueError('Unexpected receiver')
        if observation['rx_time'] < truth['tx_time']:
            raise ValueError('Reception precedes enqueue time')
        if truth['claimed_xyz'] != observation['rx_claimed_xyz']:
            raise ValueError('Received claim does not match exact TX')
        rows.append(dict(truth, **observation, delivery='RECEIVED', delivered=True))
    for packet, truth in tx.items():
        if truth['tx_node_id'] != config['tx_host']:
            raise ValueError('Unexpected transmitter: receive-only setting failed')
        for node in config['rx_hosts']:
            if (packet, node) not in seen:
                rows.append(dict(truth, rx_node_id=node, rx_event_id=None, rx_time=None,
                                 rx_signal_start_time=None, rx_xyz=None, rx_claimed_xyz=None,
                                 serial=None, claimed_timestamp=None, rssi_dbm=None,
                                 delivery='NOT_OBSERVED', delivered=False))
    common = dict(dataset_source='simulation', case=case, seed=config['seed'],
                  observer_regime=config['observer_regime'], phy_model=config['phy_model'],
                  score=None, decision='UNDETERMINED',
                  decision_reason=config.get('decision_reason', 'PR1 communication audit; no detector executed'))
    rows = [dict(common, **row) for row in sorted(rows, key=lambda r: (r['tx_time'], r['rx_node_id']))]
    summary = dict(case=case, seed=config['seed'], status='COMMUNICATION_AUDITED',
                   tx_enqueued=len(tx), receiver_opportunities=len(rows),
                   rx_delivered=len(rx), rss_samples=sum(r['rssi_dbm'] is not None for r in rows),
                   delivered_without_rssi=sum(r['delivered'] and r['rssi_dbm'] is None for r in rows),
                   not_observed=sum(not r['delivered'] for r in rows),
                   reception_rate=len(rx)/len(rows), gcs_events=len(gcs),
                   gcs_report_count=sum(g['report_count'] for g in gcs),
                   decision='UNDETERMINED', fpr=None, tpr=None,
                   tx_log_scope='management enqueue, not confirmed PHY transmission',
                   non_delivery_scope='Not observed by horizon; PHY loss/MAC drop/in-flight not separated')
    if summary['gcs_report_count'] != len(rx):
        raise ValueError('GCS report total differs from RX total')
    if any(g['tx_event_id'] not in tx for g in gcs):
        raise ValueError('GCS packet ID not present in TX ledger')
    rx_counts = Counter(r['tx_event_id'] for r in rx)
    gcs_counts = Counter()
    for g in gcs:
        gcs_counts[g['tx_event_id']] += g['report_count']
    if gcs_counts != rx_counts:
        raise ValueError('GCS per-packet report counts differ from RX ledger')
    return rows, list(tx.values()), gcs, summary


def write_csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys, lineterminator='\n')
        writer.writeheader()
        writer.writerows({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()} for row in rows)
