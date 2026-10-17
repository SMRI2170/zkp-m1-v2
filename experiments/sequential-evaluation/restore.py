"""Restore the existing runtime-only guard once, preserving partial/mismatched state."""
import argparse,hashlib,json,shlex,subprocess
from pathlib import Path
import pi
INSTALLER='82d1c7c89dcb4759e39686707e3bf3a58ecca70f163a8418088418cae6cfd311'
WATCHDOG='f1f72622b08685f2d31ecbcf58cd602de7d338ea1df93b6e2f266db12ea383ce'

def decision(state):
 if state.get('installer_sha256')!=INSTALLER or state.get('watchdog_sha256')!=WATCHDOG:return 'blocked_source_mismatch'
 present=state.get('runtime_paths_present')
 if not isinstance(present,list):return 'blocked_missing_inspection'
 if present:return 'blocked_existing_state_requires_inspection'
 return 'install_existing_guard'

def main():
 p=argparse.ArgumentParser();p.add_argument('--job',type=Path,required=True);a=p.parse_args()
 result={'status':'blocked','reason':None,'ssh_restarted':False,'persistent_os_changes':False}
 code="""import json,hashlib
from pathlib import Path
r=Path('/home/pi/.cache/week24')
paths=['/run/week24/memory_watchdog.py','/run/systemd/system/week24.slice','/run/systemd/system/week24-memory-watchdog.service','/run/systemd/system/ssh.service.d/week24-memory-guard.conf']
print(json.dumps({'installer_sha256':hashlib.sha256((r/'install_memory_guard.py').read_bytes()).hexdigest(),'watchdog_sha256':hashlib.sha256((r/'memory_watchdog.py').read_bytes()).hexdigest(),'runtime_paths_present':[p for p in paths if Path(p).exists()]}))
"""
 try:
  r=pi.ssh(shlex.join(['python3','-c',code]),timeout=20)
  if r.returncode:result['reason']='SSH inspection failed';result['ssh_exit_code']=r.returncode
  else:
   state=json.loads(r.stdout);result['inspection']=state;action=decision(state);result['reason']=action
   if action=='install_existing_guard':
    opts,env,target=pi.transport();password=env.get('EVAL_SUDO_PASSWORD',env.get('EVAL_SSH_PASSWORD'))
    cmd=['sudo','-S' if password else '-n','-p','','python3','/home/pi/.cache/week24/install_memory_guard.py','--watchdog-sha256',WATCHDOG]
    r=pi.ssh(shlex.join(cmd),timeout=45,input=password+'\n' if password else None)
    result['installer_exit_code']=r.returncode
    if r.returncode==0:
     result.update(status='completed',reason='existing runtime-only guard installed',installer_result=json.loads(r.stdout))
    else:result['reason']='installation unconfirmed; preserve partial state and do not retry automatically'
 except (OSError,ValueError,subprocess.TimeoutExpired):result['reason']='SSH/telemetry failure; installation unconfirmed, no automatic retry'
 (a.job/'guard-restoration.json').write_text(json.dumps(result,indent=2)+'\n')
 return 0 if result['status']=='completed' else 3
if __name__=='__main__':raise SystemExit(main())
