"""#69 mode E adapter. Export PRIVATE synthetic events, not a new detector/UI."""
import argparse
import json
import os
from pathlib import Path

from observations import asynchronous_view
from scene import RX_POSITIONS
from setup import REPO


def export_event(frame,metadata,method,score,threshold,decision,regime):
    if regime not in ['async_single_packet_per_observation','same_physical_packet_multirx']:
        raise ValueError('Explicit #69 observation regime required')
    if not frame or len({r['tx_event_id'] for r in frame})!=1:
        raise ValueError('One physical event only; never connect distinct transmissions')
    if any(r.get('source_run_id')!=metadata['source_run_id'] for r in frame):
        raise ValueError('One explicit source run required')
    if regime=='async_single_packet_per_observation' and len(frame)!=1:
        raise ValueError('Asynchronous mode permits only one selected RSSI')
    if decision not in ['FLAG','BELOW_THRESHOLD','UNDETERMINED']:raise ValueError('Unknown decision')
    return [dict(source_dataset='Issue70 uli-net-sim',scenario_mode='E',dataset_source='simulation',
                 simulation_engine='OMNeT++/INET',upstream_sha=metadata['upstream_sha'],scenario_seed=metadata['scenario_seed'],
                 source_run_id=metadata['source_run_id'],observer_regime=regime,
                 attack_type=metadata['attack_type'],transmit_power_regime=metadata['transmit_power_regime'],
                 event_id=r['tx_event_id'],timestamp_or_relative_t=r['tx_time'],
                 claimed_timestamp=r['claimed_timestamp'],tx_role='simulated UAV',rx_role='simulated fixed ground observer',rx_node_id=r['rx_node_id'],
                 observed_metric_name='RSS (desired signal + background)',observed_metric_unit='dBm',observed_value=r['rssi_dbm'],
                 measurement_provenance='OMNeT++/INET simulation, not real Remote ID',
                 position_source='simulation ground truth',true_xyz=r['true_tx_xyz'],
                 claimed_position_source='simulated received claim' if r['delivered'] else 'not received',claimed_xyz=r['rx_claimed_xyz'],
                 rx_xyz=r['rx_xyz'],altitude_status='synthetic known',
                 rx_status='not_delivered' if not r['delivered'] else 'missing_signal_power' if r['rssi_dbm'] is None else 'received',
                 detector_id=method,score=score,threshold=threshold,decision=decision,
                 decision_scope='event-level method outcome; not a separate verdict on this receiver',
                 decision_reason='unrestricted_unknown_power' if method=='FreePowerUND' else 'not_evaluated_or_insufficient_input' if decision=='UNDETERMINED' else 'model inconsistency only; below threshold does not prove position or safety',
                 aggregate_metrics='per-seed-metrics.csv / aggregate-metrics.csv') for r in frame]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scene-dir',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--index',type=int,default=5);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if not a.out.resolve().is_relative_to((REPO/'captures').resolve()):p.error('Coordinates may only be exported inside ignored captures/')
    if a.out.exists():p.error('Preserve prior exports; choose new path')
    import pyarrow.parquet as pq
    rows=pq.read_table(a.scene_dir/'observations.parquet').to_pylist()
    spec=json.loads((a.scene_dir/'spec.json').read_text());scores=json.loads((a.scene_dir/'detector-scores.json').read_text())
    provenance=json.loads((a.results/'provenance.json').read_text())
    view=asynchronous_view(rows,list(RX_POSITIONS),spec['count'])
    if not 0<=a.index<len(view):p.error('Event index outside recorded flight')
    for row in rows:row['source_run_id']=a.scene_dir.name
    selected=view[a.index];metadata=dict(upstream_sha=provenance['upstream_sha'],scenario_seed=spec['seed'],source_run_id=a.scene_dir.name,
                                       attack_type='synthetic claim offset' if spec['offset_x_m'] else 'normal',transmit_power_regime=spec['model'])
    event=export_event([selected],metadata,'FreePowerUND',None,None,scores['FreePowerUND']['decisions'][a.index],'async_single_packet_per_observation')
    link=next(link for link in ['strong','edge','weak'] if f'-{link}-' in a.scene_dir.name)
    threshold_key=f'{"risk" if a.scene_dir.name.startswith("risk-") else "main"}:{link}:{spec["model"]}'
    threshold=json.loads((a.results/'thresholds.json').read_text())[threshold_key]['DRSS5']
    event+=export_event([r for r in rows if r['tx_event_id']==selected['tx_event_id']],metadata,'DRSS5',scores['DRSS5']['scores'][a.index],threshold,scores['DRSS5']['decisions'][a.index],'same_physical_packet_multirx')
    a.out.parent.mkdir(parents=True,exist_ok=True,mode=0o700);a.out.write_text(json.dumps(event,indent=2)+'\n')
    print(json.dumps(dict(status='EXPORTED_PRIVATE_ONLY',records=len(event),event_index=a.index,public_coordinates=False)))


if __name__=='__main__':main()
