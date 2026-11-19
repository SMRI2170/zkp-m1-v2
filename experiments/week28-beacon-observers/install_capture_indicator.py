#!/usr/bin/env python3
"""Explicit ACT-only indicator. No radio capabilities, no capture writes, restore LED on stop."""
import argparse
import os
import re
from pathlib import Path
import subprocess
from capture_health import led_path

def unit_text(root,led,roles):
    if any(c in str(root) for c in ' \n%"') or not str(root).startswith('/home/pi/zkp-beacon-observer/releases/'):raise ValueError('unsafe release')
    if str(led) not in ['/sys/class/leds/ACT','/sys/class/leds/led0']:raise ValueError('activity LED only')
    if not roles or any(r not in ['receiver','sensors','transmitter'] for r in roles):raise ValueError('invalid roles')
    return f'''[Unit]
Description=Research recorder ACT status (not GPS or aircraft verification)
After=zkp-rid-observer.service zkp-flight-sensors.service zkp-flight-marker.service
[Service]
Type=simple
User=root
UMask=0077
ExecStart=/usr/bin/python3 {root}/experiments/week28-beacon-observers/capture_health.py --root {root}/captures --roles {' '.join(roles)} --led {led}
Restart=on-failure
RestartSec=10
TimeoutStopSec=5
NoNewPrivileges=true
CapabilityBoundingSet=CAP_DAC_READ_SEARCH
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={led}
PrivateNetwork=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
MemoryMax=48M
CPUQuota=5%
TasksMax=8
Environment=PYTHONDONTWRITEBYTECODE=1
[Install]
WantedBy=multi-user.target
'''
def main():
    p=argparse.ArgumentParser();p.add_argument('--enable',required=True,action='store_true');p.add_argument('--roles',nargs='+',required=True);a=p.parse_args()
    if os.getuid()!=0:p.error('explicit root installation required')
    root=Path(__file__).resolve().parents[2]
    led=next((p for p in [Path('/sys/class/leds/ACT'),Path('/sys/class/leds/led0')] if p.exists()),None)
    if led is None:p.error('activity LED not available')
    led_path(led);target=Path('/etc/systemd/system/zkp-capture-indicator.service');text=unit_text(root,led,a.roles)
    if target.is_symlink():p.error('unit symlink rejected')
    if target.exists() and target.read_text()!=text:
        old=target.read_text()
        match=re.search(r'^ExecStart=/usr/bin/python3 (\S+)/experiments/week28-beacon-observers/capture_health.py --root \S+ --roles ([a-z ]+) --led (/sys/class/leds/(?:ACT|led0))$',old,re.M)
        if not match or old!=unit_text(Path(match[1]),Path(match[3]),match[2].split()):p.error('unrecognized indicator retained')
        import hashlib
        backup=target.with_name(target.name+'.backup-'+hashlib.sha256(old.encode()).hexdigest()[:12])
        if backup.exists() and backup.read_text()!=old:p.error('backup differs')
        if not backup.exists():backup.write_text(old);backup.chmod(0o644)
    subprocess.run(['systemctl','stop',target.name],check=False,capture_output=True)
    target.write_text(text);target.chmod(0o644);subprocess.run(['systemd-analyze','verify',str(target)],check=True)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now',target.name],check=True)
    print('ACT_CAPTURE_INDICATOR_ENABLED')
if __name__=='__main__':main()
