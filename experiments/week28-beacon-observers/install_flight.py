#!/usr/bin/env python3
"""Explicitly switch observer-a to a sensor logger and Pi study Beacon role."""
import argparse
import os
import re
import hashlib
from pathlib import Path
import pwd
import subprocess
from run_observer import read_config


def units(root,base,gps_port=None):
    for path in [root,base]:
        if not str(path).startswith('/home/pi/zkp-beacon-observer') or any(c in str(path) for c in ' \n%"'):raise ValueError('unsafe service path')
    port='' if gps_port is None else ' --gps-port '+gps_port
    if gps_port is not None:
        import re
        if not re.fullmatch(r'/dev/(?:tty(?:ACM|USB|AMA|S)\d+|serial\d+)',gps_port):raise ValueError('explicit GPS device path required')
    common=f'''User=pi
Group=pi
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={root}/captures
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
MemoryMax=96M
CPUQuota=50%
TasksMax=16
Restart=on-failure
RestartSec=10
TimeoutStopSec=15
'''
    sensor=f'''[Unit]
Description=Pi study GPS and BME280 logger (unverified sensors)
StartLimitIntervalSec=300
StartLimitBurst=3
[Service]
{common}SupplementaryGroups=dialout i2c
CapabilityBoundingSet=
ExecStart=/usr/bin/python3 {root}/experiments/week28-beacon-observers/flight_sensors.py --output {root}/captures/flight-sensors{port}
[Install]
WantedBy=multi-user.target
'''
    beacon=f'''[Unit]
Description=Pi research marker Beacon (not aircraft authentication)
Wants=zkp-flight-sensors.service
After=NetworkManager.service zkp-flight-sensors.service
StartLimitIntervalSec=300
StartLimitBurst=3
[Service]
{common}AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
RuntimeDirectory=zkp-flight-marker
RuntimeDirectoryMode=0700
ExecStart=/usr/bin/python3 {root}/experiments/week28-beacon-observers/flight_beacon.py --marker {base}/config/marker.json --sensor {root}/captures/flight-sensors/latest.json --output {root}/captures/flight-tx --runtime /run/zkp-flight-marker --continuous
[Install]
WantedBy=multi-user.target
'''
    return {'zkp-flight-sensors.service':sensor,'zkp-flight-marker.service':beacon}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enable',required=True,action='store_true');p.add_argument('--gps-port')
    a=p.parse_args()
    if os.getuid()!=0:p.error('explicit installation requires sudo')
    root=Path(__file__).resolve().parents[2];base=root.parent.parent
    if root.parent.name!='releases' or base.name!='zkp-beacon-observer':p.error('versioned layout required')
    cfg=read_config(base/'config/node.json')
    if cfg['node_id']!='observer-a':p.error('only operator-designated A may become transmitter')
    if base.stat().st_uid!=pwd.getpwnam('pi').pw_uid:p.error('pi-owned base required')
    contents=units(root,base,a.gps_port)
    captures=root/'captures';captures.mkdir(mode=0o700,exist_ok=True)
    if captures.is_symlink() or captures.stat().st_mode&0o077:p.error('private captures required')
    os.chown(captures,pwd.getpwnam('pi').pw_uid,pwd.getpwnam('pi').pw_gid)
    # Reserve only our new virtual interface; existing station profiles are unchanged.
    rule=Path('/etc/udev/rules.d/90-zkp-flight-marker.rules')
    text='SUBSYSTEM=="net", ACTION=="add", KERNEL=="ridtx0", ENV{NM_UNMANAGED}="1"\n'
    if rule.exists() and rule.read_text()!=text:p.error('different udev rule retained')
    rule.write_text(text);rule.chmod(0o644)
    subprocess.run(['udevadm','control','--reload-rules'],check=True)
    for name,text in contents.items():
        target=Path('/etc/systemd/system')/name
        if target.exists() and target.read_text()!=text:
            old=target.read_text()
            match=re.search(r'^ExecStart=/usr/bin/python3 (\S+)/experiments/week28-beacon-observers/flight_',old,re.M)
            port_match=re.search(r' --gps-port (/dev/\S+)\s*$',old,re.M)
            old_port=port_match[1] if port_match else None
            if not match or old!=units(Path(match[1]),base,old_port).get(name):
                p.error('unrecognized flight unit retained; inspect before upgrade')
            backup=target.with_name(name+'.backup-'+hashlib.sha256(old.encode()).hexdigest()[:12])
            if backup.exists() and backup.read_text()!=old:p.error('unit backup differs; retained')
            if not backup.exists():backup.write_text(old);backup.chmod(0o644)
            subprocess.run(['systemctl','stop',name],check=True)

        target.write_text(text);target.chmod(0o644)
        subprocess.run(['systemd-analyze','verify',str(target)],check=True)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','disable','--now','zkp-rid-observer.service'],check=True)
    subprocess.run(['systemctl','enable','--now',*contents],check=True)
    print('A_FLIGHT_SENSOR_AND_STUDY_MARKER_ENABLED')


if __name__=='__main__':main()
