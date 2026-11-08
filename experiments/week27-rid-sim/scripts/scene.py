"""A reusable, actual INET scene. All coordinates/ledgers stay in captures/."""
import hashlib
from decimal import Decimal
import json
import math
from pathlib import Path
import random
import subprocess
import shutil

from normalize import normalize,read_vectors,write_csv
from run_power import physical_audit,target_events
from run_smoke import run_logged
from setup import ROOT

RX_POSITIONS={0:(100,100,2),2:(300,100,2),3:(100,300,2),4:(300,300,2),5:(200,100,8)}


def ini_for(spec):
    count=spec['count'];gap=spec['gap_s']
    if count<1 or gap<=0:
        raise ValueError('Require actual positive spacing between distinct transmissions')
    angle=spec.get('angle_deg',random.Random(spec['seed']).uniform(0,360))
    duration=Decimal('0.15')+(count-1)*Decimal(str(gap))
    values=[
        '[General]', 'network = uav_rid.rid_network.BasicUav',
        f'sim-time-limit = {duration}s',
        'num-rngs = 2','cmdenv-express-mode = true','cmdenv-interactive = false',
        'record-eventlog = false',
        # Do not instantiate unrelated queue-rate/statistics timers. These
        # recorders are not radio/mobility logic. All direct audit vectors stay.
        '**.statistic-recording = false',
        '*.host[*].wlan[0].mgmt.*.vector-recording = true',
        '*.host[1].wlan[0].radio.transmitter.*.vector-recording = true',
        '*.gcs[0].*.vector-recording = true','**.vector-recording = false',
        '*.hasVisualizer = false','*.numHosts = 6','*.numGcs = 1',
        '*.gcs[0].pyClass = "smoke_callback.SmokeAudit"',
        f'*.pyBridge.pythonPath = "{ROOT}/scripts"',
        '*.host[*].mobility.initFromDisplayString = false',
        '*.host[1].typename = "Issue70PowerHost"',
        '*.host[1].wlan[0].mgmt.transmitBeacon = true',
        '*.host[*].wlan[0].mgmt.transmitBeacon = false',
        '*.host[*].wlan[0].mgmt.gcsModulePath = "^.^.^.gcs[0]"',
        '*.host[1].mobility.typename = "CircleMobility"',
        '*.host[1].mobility.cx = 200m','*.host[1].mobility.cy = 200m',
        f'*.host[1].mobility.cz = {spec.get("height_m",40)}m',
        f'*.host[1].mobility.r = {spec.get("radius_m",80)}m',
        '*.host[1].mobility.speed = 3mps',
        f'*.host[1].mobility.startAngle = {angle}deg',
        '*.host[1].mobility.updateInterval = 0s',
        '*.host[1].mobility.faceForward = false',
        f'*.host[1].wlan[0].mgmt.beaconInterval = {gap}s',
        '*.host[1].wlan[0].mgmt.beaconOffset = 100ms',
        '*.host[1].wlan[0].mgmt.startupJitter = 0s',
        f'*.host[1].wlan[0].mgmt.powerModel = "{spec["model"]}"',
        f'*.host[1].wlan[0].mgmt.nominalDbm = {spec.get("nominal_dbm",13)}',
        f'*.host[1].wlan[0].mgmt.rangeDb = {3 if spec["model"]=="uniform" else 10}',
        f'*.host[1].wlan[0].mgmt.claimOffsetX = {spec.get("offset_x_m",0)}m',
        f'*.host[1].wlan[0].mgmt.claimOffsetY = {spec.get("offset_y_m",0)}m',
        f'*.host[1].wlan[0].mgmt.claimOffsetZ = {spec.get("offset_z_m",0)}m',
    ]
    for node,position in RX_POSITIONS.items():
        values.append(f'*.host[{node}].mobility.typename = "StationaryMobility"')
        for axis,value in zip('XYZ',position):
            values.append(f'*.host[{node}].mobility.initial{axis} = {value}m')
        if spec.get('record_kf',False):
            values.append(f'*.host[{node}].wlan[0].mgmt.typename = "KalmanFilterDetectMgmt"')
    return '\n'.join(values)+'\n'


def run_scene(spec,workspace,directory,ini_renderer=ini_for):
    if directory.exists():
        raise ValueError('Scene output already exists; preserving evidence')
    if shutil.disk_usage(directory.parent).free<8*1024**3:
        raise ValueError('Need 8 GiB disk headroom; no prior evidence deleted')
    directory.mkdir(parents=True,mode=0o700)
    (directory/'spec.json').write_text(json.dumps(spec,indent=2)+'\n')
    ini=directory/'scene.ini';ini.write_text(ini_renderer(spec))
    upstream=workspace/'uli-net-sim';binary=workspace/'project-build/out/clang-release/rid_smoke'
    lock=json.loads((ROOT/'upstream.lock.json').read_text())
    if subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()!=lock['uli_net_sim']['sha']:
        raise ValueError('Upstream SHA mismatch')
    if subprocess.check_output(['git','-C',str(upstream),'status','--porcelain'],text=True).strip():
        raise ValueError('Upstream edited')
    exclude=';'.join((workspace/'inet4.5/.nedexclusions').read_text().splitlines())
    command=[binary,'-u','Cmdenv','-n',f'{ROOT}/native:{upstream}/src:{workspace}/inet4.5/src',
             '-x',exclude,'-f',ini,'-r','0',f'--seed-set={spec["seed"]}',
             f'--output-vector-file={directory}/run.vec',f'--output-scalar-file={directory}/run.sca']
    receipt=run_logged(workspace,command,upstream,directory/'simulation.log',120,
                       watch_dir=directory,max_bytes=128*1024**2,min_free_bytes=8*1024**3)
    (directory/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if receipt['exit_code']:
        raise ValueError('Simulation failed: '+directory.name)
    if (directory/'run.vec').stat().st_size>128*1024**2:
        raise ValueError('Vector exceeds parser budget; preserved, not parsed')
    events=read_vectors(directory/'run.vec')
    cfg=dict(seed=spec['seed'],tx_host=1,rx_hosts=list(RX_POSITIONS),
             observer_regime='same_packet_multisite_comparison_only',
             phy_model='INET 4.5.4 dimensional / FreeSpace / Dipole / -100dBm background',
             decision_reason='No detector; provenance audit')
    rows,tx,gcs,summary=normalize(target_events(events,receivers=tuple(RX_POSITIONS)),spec['case'],cfg)
    summary.update(physical_audit(events,tx,rows))
    if len(tx)!=spec['count'] or summary['phy_tx_count']!=spec['count']:
        raise ValueError('Actual TX/PHY count differs from requested schedule')
    tx.sort(key=lambda t:t['tx_time'])
    schedule_error=max(abs(t['tx_time']-(.1+i*spec['gap_s'])) for i,t in enumerate(tx))
    if schedule_error>1e-8:
        raise ValueError('Actual simulator times do not match intended spacing')
    # Verify on-demand mobility really advanced, including long gaps.
    angle=spec.get('angle_deg',random.Random(spec['seed']).uniform(0,360))
    radius=spec.get('radius_m',80);height=spec.get('height_m',40)
    movement_error=max(math.dist(t['true_tx_xyz'],[
        200+radius*math.cos(math.radians(angle)+3/radius*t['tx_time']),
        200+radius*math.sin(math.radians(angle)+3/radius*t['tx_time']),height]) for t in tx)
    if movement_error>1e-6:
        raise ValueError('Long-gap motion differs from analytic CircleMobility')
    summary.update(schedule_max_error_s=schedule_error,trajectory_max_error_m=movement_error,
                   first_tx_time_s=tx[0]['tx_time'],last_tx_time_s=tx[-1]['tx_time'],
                   execution_exit_code=receipt['exit_code'],simulation_log_sha256=receipt['log_sha256'],
                   vector_sha256=hashlib.sha256((directory/'run.vec').read_bytes()).hexdigest())
    import pyarrow as pa
    import pyarrow.parquet as pq
    write_csv(directory/'observations.csv',rows);write_csv(directory/'tx-ledger.csv',tx);write_csv(directory/'gcs.csv',gcs)
    pq.write_table(pa.Table.from_pylist(rows),directory/'observations.parquet')
    (directory/'audit.json').write_text(json.dumps(summary,indent=2)+'\n')
    return rows,tx,summary
