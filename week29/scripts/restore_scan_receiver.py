#!/usr/bin/env python3
"""Restore the fixed normal receiver after a bounded study; never delete interfaces/config."""
import argparse
import os
from pathlib import Path
import re
import subprocess

NORMAL='zkp-rid-observer.service'


def restore(unit,*,runner=subprocess.run,ap_exists=lambda:Path('/sys/class/net/ridtx0').exists()):
    if not re.fullmatch(r'zkp-scan-(rx|tx)-\d{8}t\d{6}z',unit):raise ValueError('Owned study unit name required')
    def state():
        result=runner(['systemctl','show',unit,'-p','LoadState','-p','ActiveState'],capture_output=True,text=True,timeout=10)
        values=dict(x.split('=',1) for x in result.stdout.splitlines() if '=' in x)
        if values.get('LoadState') not in ['loaded','not-found']:raise RuntimeError('Temporary unit state unconfirmed')
        return values
    before=state()
    if before['LoadState']=='loaded':
        result=runner(['systemctl','stop',unit],capture_output=True,text=True,timeout=45)
        after=state()
        # A successful transient unit may unload between show and stop. Confirm,
        # rather than treat every stop error as harmless.
        if result.returncode and after['LoadState']!='not-found':raise RuntimeError('Temporary unit stop failed')
        if after.get('ActiveState') not in ['inactive','failed']:raise RuntimeError('Temporary study still running')
    if ap_exists():raise RuntimeError('Study AP still exists; inspect before normal recording resumes')
    runner(['systemctl','start',NORMAL],capture_output=True,text=True,timeout=45,check=True)
    check=runner(['systemctl','is-active',NORMAL],capture_output=True,text=True,timeout=10)
    if check.returncode or check.stdout.strip()!='active':raise RuntimeError('Normal receiver restoration unconfirmed')
    return dict(receiver_active=True,temporary_unit_initially_unloaded=before['LoadState']=='not-found',temporary_ap_absent=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--transient-unit',required=True);a=p.parse_args()
    if os.getuid()!=0:p.error('root is required only to control these fixed system services')
    import json
    print(json.dumps(restore(a.transient_unit)))


if __name__=='__main__':main()
