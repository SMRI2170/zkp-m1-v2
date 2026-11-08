"""PR5 attack specification and private truth audit, separated from detectors."""
import hashlib
import json
import math
from pathlib import Path

from normalize import read_vectors,write_csv
from scene import RX_POSITIONS,ini_for,run_scene
from run_evaluation import create_spec

CASES=['position_only','reference_rx0','schedule_aware','schedule_blind']
SCHEDULE=list(RX_POSITIONS)
AUDIT_FIELDS={'Attack Requested Delta','Attack Applied Delta','Attack Bound Clamped','Attack PHY Clamped',
              'Attack Compensation Error','Attack Target RX','Attack Nominal dBm','Power Packet Index','Requested PHY Power'}


def delta_for(actual,claim,receiver):
    d=math.dist(actual,receiver);q=math.dist(claim,receiver)
    if not all(math.isfinite(v) and v>1e-3 for v in [d,q]):raise ValueError('Nonfinite or near-zero compensation distance')
    return 20*math.log10(d/q)


def attack_delta(case,actual,claim,catalog,target=None):
    if case=='position_only':return 0.
    if case=='reference_rx0':return delta_for(actual,claim,catalog[0])
    if case=='schedule_aware':
        if target not in catalog:raise ValueError('Oracle target not in catalog')
        return delta_for(actual,claim,catalog[target])
    if case=='schedule_blind':return sum(delta_for(actual,claim,p) for p in catalog.values())/len(catalog)
    raise ValueError('Unknown attack case')


def apply_limits(nominal,requested,bound,minimum,maximum):
    if not all(math.isfinite(x) for x in [nominal,requested,bound,minimum,maximum]) or bound<0 or minimum>maximum:
        raise ValueError('Invalid power constraints')
    bounded=max(-bound,min(bound,requested));power=max(minimum,min(maximum,nominal+bounded))
    return dict(requested_delta_db=requested,applied_delta_db=power-nominal,effective_phy_tx_dbm=power,
                clamped_by_attack_bound=bounded!=requested,clamped_by_phy_limit=power!=nominal+bounded,
                compensation_error_db=power-nominal-requested)


def attack_spec(seed,case,offset,link,bound=10,phy=(-80,23),count=20,schedule=None):
    if case not in CASES:raise ValueError('Unknown attack case')
    spec=create_spec(seed,'fixed' if case=='position_only' else 'adaptive',offset,link,count,10)
    schedule=list(SCHEDULE if schedule is None else schedule)
    if not schedule or any(node not in RX_POSITIONS for node in schedule):raise ValueError('Invalid defender schedule')
    spec.update(attack_case=case,attack_bound_db=bound,phy_min_dbm=phy[0],phy_max_dbm=phy[1],defender_schedule=schedule)
    return spec


def attack_ini(spec):
    text=ini_for(spec).replace('*.host[1].typename = "Issue70PowerHost"','*.host[1].typename = "Issue75PowerHost"')
    catalog=spec.get('catalog_override',RX_POSITIONS)
    encoded=';'.join(f'{node}:{p[0]},{p[1]},{p[2]}' for node,p in catalog.items())
    prefix='*.host[1].wlan[0].mgmt.'
    text+=f'{prefix}attackMode = "{spec["attack_case"]}"\n{prefix}receiverCatalog = "{encoded}"\n'
    # Existing INI sets rangeDb, so replace that value rather than rely on
    # ambiguous duplicate assignments. Other PR4 rendering stays unchanged.
    text=text.replace(f'{prefix}rangeDb = 10\n',f'{prefix}rangeDb = {spec["attack_bound_db"]}\n')
    text+=f'{prefix}minimumDbm = {spec["phy_min_dbm"]}\n{prefix}maximumDbm = {spec["phy_max_dbm"]}\n'
    if spec['attack_case']=='schedule_aware':
        text+=f'{prefix}observerSchedule = "'+ ' '.join(map(str,spec['defender_schedule']))+'"\n'
    return text


def audit_attack(events,tx,rows,spec):
    values={}
    for (module,event,time),fields in events.items():
        if 'Attack Requested Delta' in fields:
            if not AUDIT_FIELDS.issubset(fields) or 'Transmission Packet ID' not in fields:raise ValueError('Incomplete attack audit event')
            packet=int(fields['Transmission Packet ID'])
            if packet in values:raise ValueError('Duplicate attack audit')
            values[packet]=fields
    tx=sorted(tx,key=lambda t:t['tx_time']);ledger=[]
    for index,t in enumerate(tx):
        fields=values.get(t['tx_event_id'])
        if fields is None or fields['Power Packet Index']!=index:raise ValueError('Missing/incorrect physical packet index')
        target=spec['defender_schedule'][index%len(spec['defender_schedule'])]
        actual_target=target if spec['attack_case']=='schedule_aware' else 0 if spec['attack_case']=='reference_rx0' else -1
        catalog=spec.get('catalog_override',RX_POSITIONS)
        requested=attack_delta(spec['attack_case'],t['true_tx_xyz'],t['claimed_xyz'],catalog,target)
        expected=apply_limits(spec['nominal_dbm'],requested,spec['attack_bound_db'],spec['phy_min_dbm'],spec['phy_max_dbm'])
        mapping={'requested_delta_db':'Attack Requested Delta','applied_delta_db':'Attack Applied Delta',
                 'effective_phy_tx_dbm':'Requested PHY Power','clamped_by_attack_bound':'Attack Bound Clamped',
                 'clamped_by_phy_limit':'Attack PHY Clamped','compensation_error_db':'Attack Compensation Error'}
        if fields['Attack Target RX']!=actual_target:raise ValueError('Attack target differs from declared knowledge')
        for key,field in mapping.items():
            if abs(fields[field]-expected[key])>1e-8:raise ValueError('Actual native compensation differs: '+key)
        if abs(fields['Attack Nominal dBm']-spec['nominal_dbm'])>1e-8:raise ValueError('Nominal power differs')
        selected=next(r for r in rows if r['tx_event_id']==t['tx_event_id'] and r['rx_node_id']==target)
        if abs(selected['phy_tx_power_dbm_truth_only']-expected['effective_phy_tx_dbm'])>1e-8:raise ValueError('Compensation did not reach actual PHY')
        ledger.append(dict(t,**expected,target_rx_id=actual_target,evaluation_rx_id=target,
                           target_mismatch=actual_target!=target if actual_target>=0 else None,
                           oracle_requested_delta_db=delta_for(t['true_tx_xyz'],t['claimed_xyz'],catalog[target]),
                           delivered=selected['delivered'],rssi_dbm=selected['rssi_dbm']))
    if len(values)!=len(tx):raise ValueError('Unexpected audit events')
    return ledger


def run_attack_scene(spec,workspace,directory):
    rows,tx,audit=run_scene(spec,workspace,directory,ini_renderer=attack_ini)
    ledger=audit_attack(read_vectors(directory/'run.vec'),tx,rows,spec)
    write_csv(directory/'attack-truth-ledger.csv',ledger)
    (directory/'attack-truth-ledger.json').write_text(json.dumps(ledger)+'\n')
    audit.update(attack_case=spec['attack_case'],attack_ledger_sha256=hashlib.sha256((directory/'attack-truth-ledger.json').read_bytes()).hexdigest(),
                 attack_bound_clamped=sum(r['clamped_by_attack_bound'] for r in ledger),phy_clamped=sum(r['clamped_by_phy_limit'] for r in ledger),
                 selected_received=sum(r['delivered'] for r in ledger),target_mismatches=sum(r['target_mismatch'] is True for r in ledger))
    (directory/'attack-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    return rows,tx,audit,ledger


def compare_legacy(rows,tx,old_directory):
    """A/B reproduction only: verify original vectors before reading them."""
    from normalize import normalize
    from run_power import target_events
    audit=json.loads((old_directory/'audit.json').read_text())
    vector=old_directory/'run.vec'
    if hashlib.sha256(vector.read_bytes()).hexdigest()!=audit['vector_sha256']:raise ValueError('Legacy vector changed')
    config=dict(seed=audit['seed'],tx_host=1,rx_hosts=list(RX_POSITIONS),observer_regime='same_packet_multisite_comparison_only',phy_model='INET FreeSpace/Dipole')
    old_rows,old_tx,gcs,_=normalize(target_events(read_vectors(vector),receivers=tuple(RX_POSITIONS)),audit['case'],config)
    old_tx.sort(key=lambda r:r['tx_time']);tx=sorted(tx,key=lambda r:r['tx_time'])
    if len(tx)!=len(old_tx) or len(rows)!=len(old_rows):raise ValueError('Legacy count mismatch')
    for a,b in zip(tx,old_tx):
        if abs(a['tx_time']-b['tx_time'])>1e-10 or math.dist(a['true_tx_xyz'],b['true_tx_xyz'])>1e-8 or math.dist(a['claimed_xyz'],b['claimed_xyz'])>1e-8 or abs(a['tx_power_dbm_truth_only']-b['tx_power_dbm_truth_only'])>1e-8:
            raise ValueError('Legacy power/trajectory/claim mismatch')
    errors=[]
    for a,b in zip(rows,old_rows):
        if a['delivered']!=b['delivered'] or a['rx_node_id']!=b['rx_node_id']:raise ValueError('Legacy delivery mismatch')
        if (a['rssi_dbm'] is None)!=(b['rssi_dbm'] is None):raise ValueError('Legacy RSS missingness mismatch')
        if a['rssi_dbm'] is not None:errors.append(abs(a['rssi_dbm']-b['rssi_dbm']))
    if errors and max(errors)>1e-8:raise ValueError('Legacy measured RSS changed')
    return dict(status='PASSED',legacy_run=old_directory.name,legacy_vector_sha256=audit['vector_sha256'],
                rx_opportunities=len(rows),max_measured_rss_difference_db=max(errors) if errors else None)
