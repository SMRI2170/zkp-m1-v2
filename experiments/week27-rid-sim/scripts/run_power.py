"""PR2 actual packet-tag power experiment. No RSSI postprocessing additions."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

from normalize import normalize, read_vectors, write_csv
from run_smoke import run_logged
from setup import ROOT, REPO


def render(cases):
    text = (ROOT / 'config/smoke.ini').read_text().replace('@CALLBACK_PATH@', str(ROOT / 'scripts'))
    text = text.replace('[Config Normal]', 'num-rngs = 2\n\n[Config Normal]')
    for case in cases:
        text += f'\n[Config {case["name"]}]\nextends = Normal\n'
        text += '*.host[1].typename = "Issue70PowerHost"\n'
        prefix = '*.host[1].wlan[0].mgmt.'
        for key, value in dict(powerModel=f'"{case["model"]}"',
                               nominalDbm=case.get('nominal_dbm', 13), rangeDb=case.get('range_db', 3),
                               maxStepDb=case.get('step_db', 2), claimOffsetX=f'{case["offset_m"]}m').items():
            text += f'{prefix}{key} = {value}\n'
        if 'jammer_dbm' in case:
            text += '*.numHosts = 4\n*.host[3].typename = "Issue70PowerHost"\n'
            text += '*.host[3].mobility.typename = "StationaryMobility"\n'
            for axis, value in zip('XYZ', case.get('jammer_xyz', [110, 100, 20])):
                text += f'*.host[3].mobility.initial{axis} = {value}m\n'
            text += f'*.host[3].wlan[0].mgmt.nominalDbm = {case["jammer_dbm"]}\n'
            text += '*.host[3].wlan[0].mgmt.beaconInterval = 250us\n'
            text += f'*.host[3].wlan[0].mgmt.beaconOffset = {case.get("jammer_offset_s",.099)}s\n'
            text += '*.host[3].wlan[0].mgmt.gcsModulePath = ""\n'
    return text


def target_events(events, host=1, receivers=(0, 2)):
    packets = {int(v['Transmission Packet ID']) for (module, _, _), v in events.items()
               if f'.host[{host}].wlan[0].mgmt' in module and 'Transmission Packet ID' in v}
    return {key: value for key, value in events.items()
            if ('Transmission Packet ID' in value and int(value['Transmission Packet ID']) in packets)
            or ('Packet ID' in value and int(value['Packet ID']) in packets
                and any(f'.host[{node}].wlan[0].mgmt' in key[0] for node in receivers))
            or ('packet_id' in value and int(value['packet_id']) in packets)}


def physical_audit(events, tx, rows):
    physical = {}
    for (module, _, time), fields in events.items():
        if 'PHY Packet ID' not in fields:
            continue
        packet = int(fields['PHY Packet ID'])
        if packet in physical:
            raise ValueError('Unexpected duplicate PHY transmission ID')
        physical[packet] = dict(time=float(time), power=fields['PHY Power dBm'], tag=fields['PHY Power Tag Present'])
    powers, delays = [], []
    for transmission in tx:
        packet = transmission['tx_event_id']
        if packet not in physical:
            continue
        actual = physical[packet]
        if actual['tag'] != 1 or abs(actual['power']-transmission['tx_power_dbm_truth_only']) > 1e-8:
            raise ValueError('Requested power did not reach the actual PHY transmitter')
        powers.append(actual['power'])
        delays.append(actual['time']-transmission['tx_time'])
    for row in rows:
        phy = physical.get(row['tx_event_id'])
        if row['delivered'] and phy is None:
            raise ValueError('RX without PHY transmission')
        row['phy_tx_time_truth_only'] = phy['time'] if phy else None
        row['phy_tx_power_dbm_truth_only'] = phy['power'] if phy else None
        if phy is None:
            row['delivery'] = 'PHY_TX_NOT_LOGGED_BY_HORIZON'
    return dict(phy_tx_count=len(powers), phy_power_min_dbm=min(powers) if powers else None,
                phy_power_max_dbm=max(powers) if powers else None,
                mean_phy_access_delay_s=sum(delays)/len(delays) if delays else None,
                enqueued_without_phy=len(tx)-len(powers), phy_power_tag_verified=True)


def compare_rssi(a, b):
    first = {(r['tx_time'], r['rx_node_id']): r['rssi_dbm'] for r in a if r['rssi_dbm'] is not None}
    second = {(r['tx_time'], r['rx_node_id']): r['rssi_dbm'] for r in b if r['rssi_dbm'] is not None}
    shared = first.keys() & second.keys()
    return [second[k]-first[k] for k in sorted(shared)]


def expected_total_rss(base_dbm, change_db, noise_dbm=-100):
    # ReceiverBase::computeSignalPower reports minimum signal PLUS noise, not
    # isolated desired-signal power. Here only the controlled, single-TX cases
    # use the configured stationary background noise (no interferer).
    noise=10**(noise_dbm/10)
    signal=10**(base_dbm/10)-noise
    if signal<=0:
        raise ValueError('RSS does not exceed known background noise')
    return 10*math.log10(signal*10**(change_db/10)+noise)


def check_paired_geometry(all_tx):
    anchor = sorted(all_tx['FixedNormal'],key=lambda t:t['tx_time'])
    max_distance = max_time = 0.
    for transmissions in all_tx.values():
        current = sorted(transmissions,key=lambda t:t['tx_time'])
        if len(current)!=len(anchor):
            raise ValueError('Target enqueue counts differ')
        for a,b in zip(anchor,current):
            dt=abs(a['tx_time']-b['tx_time']); d=math.dist(a['true_tx_xyz'],b['true_tx_xyz'])
            max_distance=max(max_distance,d);max_time=max(max_time,dt)
            # Double precision LinearMobility accumulates sub-nanometre
            # roundoff under different event loads. This is not a policy or
            # detector tolerance: any larger trajectory difference fails.
            if dt>1e-12 or d>1e-8:
                raise ValueError('Target true trajectories/schedules differ')
    return dict(max_position_difference_m=max_distance,max_enqueue_time_difference_s=max_time,
                comparison_tolerance_m=1e-8,comparison_tolerance_s=1e-12)


def check_paired_claim_inputs(all_rows, all_tx):
    for normal, spoof in [('FixedNormal','PositionOnly'),('UniformNormal','UniformSpoof'),('SlewNormal','SlewSpoof')]:
        if normal not in all_rows or spoof not in all_rows:
            continue
        def claims(rows):
            return {(r['tx_time'],r['rx_node_id']):(r['serial'],r['claimed_timestamp']) for r in rows if r['delivered']}
        if claims(all_rows[normal]) != claims(all_rows[spoof]):
            raise ValueError('Paired identity/timestamp or received cohorts differ')
        def powers(tx):
            return sorted((t['tx_time'],t['tx_power_dbm_truth_only']) for t in tx)
        if powers(all_tx[normal]) != powers(all_tx[spoof]):
            raise ValueError('Paired power sequences differ')
    return dict(identity_timestamp_pairs_verified=True,power_sequence_pairs_verified=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-dir', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--workspace', type=Path, default=REPO / '.cache/issue70')
    a = p.parse_args()
    os.umask(0o077)
    if not a.raw_dir.resolve().is_relative_to((REPO/'captures').resolve()):
        p.error('Use ignored captures/')
    if a.raw_dir.exists() or a.out.exists():
        p.error('Preserve prior evidence; choose new output directories')
    a.raw_dir.mkdir(parents=True, mode=0o700); a.out.mkdir(parents=True)
    raw, workspace = a.raw_dir.resolve(), a.workspace.resolve()
    cfg = json.loads((ROOT/'config/power.json').read_text())
    lock = json.loads((ROOT/'upstream.lock.json').read_text())
    result = dict(dataset_source='simulation', stage='PR2', status='NOT_RUN', cases=[],
                  seed=cfg['seed'], attacker_knowledge=cfg['attacker_knowledge'],
                  upstream_sha=lock['uli_net_sim']['sha'], detector='NOT_RUN',
                  observer_nodes=cfg['rx_hosts'],
                  non_observer_jammer_node=3)
    all_rows, all_tx = {}, {}
    try:
        upstream = workspace/'uli-net-sim'
        if subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip() != result['upstream_sha']:
            raise ValueError('Upstream SHA mismatch')
        if subprocess.check_output(['git','-C',str(upstream),'status','--porcelain'],text=True).strip():
            raise ValueError('Upstream was modified')
        ini = raw/'power.ini'; ini.write_text(render(cfg['cases']))
        exclusions = ';'.join((workspace/'inet4.5/.nedexclusions').read_text().splitlines())
        binary = workspace/'project-build/out/clang-release/rid_smoke'
        result['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
        for case in cfg['cases']:
            name = case['name']; directory = raw/name; directory.mkdir(mode=0o700)
            summary = dict(case=name, status='NOT_RUN'); result['cases'].append(summary)
            command = [binary,'-u','Cmdenv','-n',f'{ROOT}/native:{upstream}/src:{workspace}/inet4.5/src',
                       '-x',exclusions,'-f',ini,'-c',name,'-r','0',f'--seed-set={cfg["seed"]}',
                       f'--output-vector-file={directory}/run.vec',f'--output-scalar-file={directory}/run.sca']
            receipt = run_logged(workspace, command, upstream, directory/'simulation.log', 120)
            (directory/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
            summary.update(execution_exit_code=receipt['exit_code'],status='SIMULATION_FAILED',
                           simulation_log_sha256=receipt['log_sha256'])
            if receipt['exit_code']:
                raise ValueError(name+' simulation failed')
            summary['status'] = 'SIMULATION_COMPLETED_AUDIT_PENDING'
            events = read_vectors(directory/'run.vec')
            rows, tx, gcs, metrics = normalize(target_events(events), name, cfg)
            summary.update(metrics, **physical_audit(events, tx, rows), status='POWER_AUDITED')
            summary['reception_rate_confirmed_phy'] = summary['rx_delivered']/(summary['phy_tx_count']*len(cfg['rx_hosts'])) if summary['phy_tx_count'] else None
            if any(t['is_spoofed'] != int(case['offset_m'] != 0) for t in tx):
                raise ValueError('Position labels incorrect')
            if any(r['serial'] != 1 for r in rows if r['delivered']):
                raise ValueError('Unexpected identity modification')
            import pyarrow as pa
            import pyarrow.parquet as pq
            write_csv(directory/'observations.csv',rows); write_csv(directory/'tx-ledger.csv',tx)
            write_csv(directory/'gcs.csv',gcs)
            pq.write_table(pa.Table.from_pylist(rows), directory/'observations.parquet')
            all_rows[name], all_tx[name] = rows, tx
        result['paired_geometry']=check_paired_geometry(all_tx)
        result.update(check_paired_claim_inputs(all_rows,all_tx))
        shifts = compare_rssi(all_rows['FixedNormal'],all_rows['HighControl'])
        base_rss={(r['tx_time'],r['rx_node_id']):r['rssi_dbm'] for r in all_rows['FixedNormal'] if r['rssi_dbm'] is not None}
        errors=[abs(r['rssi_dbm']-expected_total_rss(base_rss[(r['tx_time'],r['rx_node_id'])],6))
                for r in all_rows['HighControl'] if r['rssi_dbm'] is not None and (r['tx_time'],r['rx_node_id']) in base_rss]
        if not errors or max(errors)>1e-8:
            raise ValueError('Physical power control does not match signal-plus-noise prediction')
        indexed = {m['case']:m for m in result['cases']}
        if indexed['AllLow']['rx_delivered'] != 0 or not 0 < indexed['AlternatingNormal']['rx_delivered'] < indexed['FixedNormal']['rx_delivered']:
            raise ValueError('Physical delivery control failed')
        result.update(status='PR2_PHYSICAL_POWER_PASSED', paired_true_schedule_verified=True,
                      measured_control_shift_db=sum(shifts)/len(shifts),
                      signal_plus_noise_prediction_max_error_db=max(errors),
                      interference_changes_target_delivery=indexed['InterferenceLow']['rx_delivered'] != indexed['InterferenceHigh']['rx_delivered'],
                      hidden_interference_changes_target_delivery=indexed['HiddenInterferenceLow']['rx_delivered'] != indexed['HiddenInterferenceHigh']['rx_delivered'])
    except Exception as error:
        result.update(status='PR2_FAILED',error=str(error))
    for case in cfg['cases'][len(result['cases']):]:
        result['cases'].append(dict(case=case['name'],status='NOT_RUN'))
    (a.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    write_csv(a.out/'case-summary.csv',result['cases'])
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='PR2_PHYSICAL_POWER_PASSED' else 2


if __name__=='__main__':
    raise SystemExit(main())
