#!/usr/bin/env python3
"""Explicit opt-in installation of receiver-only systemd boot service; no sudoers/network changes."""
import argparse
import os
import re
import hashlib
from pathlib import Path
import pwd
import subprocess
from boot_observer import unit_text
from run_observer import read_config


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enable',action='store_true',required=True)
    a=p.parse_args()
    if os.getuid()!=0:p.error('run this explicit boot installer with sudo')
    root=Path(__file__).resolve().parents[2];base=root.parent.parent
    if root.parent.name!='releases' or base.name!='zkp-beacon-observer':p.error('versioned release layout required')
    owner=base.stat().st_uid;user=pwd.getpwuid(owner).pw_name
    if user!='pi':p.error('current installer supports pi-owned nodes only')
    read_config(base/'config/node.json')
    captures=root/'captures'
    if captures.is_symlink():p.error('capture symlink rejected')
    captures.mkdir(mode=0o700,exist_ok=True)
    if captures.stat().st_uid not in [0,owner] or captures.stat().st_mode&0o077:p.error('existing captures permissions need inspection')
    os.chown(captures,owner,owner);os.chmod(captures,0o700)
    target=Path('/etc/systemd/system/zkp-rid-observer.service');text=unit_text(root,base,user)
    if target.is_symlink():p.error('unit symlink rejected')
    if target.exists() and target.read_text()!=text:
        old=target.read_text()
        m=re.search(r'^ExecStart=/usr/bin/python3 (\S+)/experiments/week28-beacon-observers/boot_observer.py --config ',old,re.M)
        if not m or old!=unit_text(Path(m[1]),base,user):
            p.error('unrecognized existing unit retained; inspect before replacement')
        backup=target.with_name(target.name+'.backup-'+hashlib.sha256(old.encode()).hexdigest()[:12])
        if backup.exists() and backup.read_text()!=old:p.error('unit backup differs; retained')
        if not backup.exists():backup.write_text(old);backup.chmod(0o644)
        subprocess.run(['systemctl','stop',target.name],check=True)

    target.write_text(text);target.chmod(0o644)
    subprocess.run(['systemd-analyze','verify',str(target)],check=True)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now',target.name],check=True)
    print('RECEIVER_BOOT_SERVICE_ENABLED')


if __name__=='__main__':main()
