#!/usr/bin/env python3
"""Read-only, sequential B--F audit and bounded storage/RAM sampling.

No installation, service restart, network change or capture deletion is performed.
Raw SSH results and connection settings stay in owner-private captures/.
"""
import argparse
import csv
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
GIB=1024**3
RESERVE=64*1024**2
PROBE=r'''
import hashlib,json,os,platform,shutil,subprocess,time
from pathlib import Path
base=Path.home()/'zkp-beacon-observer'
if base.is_symlink():raise ValueError('base symlink rejected')
config=base/'config/node.json'
if config.is_symlink():raise ValueError('config symlink rejected')
node=json.loads(config.read_text())['node_id']
release=(base/'current').resolve(strict=True)
if release.parent!=base/'releases':raise ValueError('current outside releases')
def system(*args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=5)
 return dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
def props(text):return dict(x.split('=',1) for x in text.splitlines() if '=' in x)
service=system('systemctl','show','zkp-rid-observer.service','-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStatus','-p','MemoryCurrent','-p','MemoryMax','-p','CPUUsageNSec','-p','NRestarts','-p','MainPID')
statuspath=release/'captures/receiver/storage-status.json';status=None
if statuspath.exists():
 if statuspath.is_symlink() or statuspath.stat().st_size>16384:raise ValueError('unsafe status')
 status=json.loads(statuspath.read_text())
mem=dict((x.split(':',1)[0],int(x.split()[1])*1024) for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith(('MemAvailable:','MemTotal:','SwapFree:','SwapTotal:')))
hashes={}
for p in (base/'config').glob('*'):
 if p.is_symlink():raise ValueError('config symlink rejected')
 if p.is_file():hashes[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps(dict(node_id=node,hostname=platform.node(),machine=platform.machine(),
 os_release=Path('/etc/os-release').read_text(),active_release=str(release),
 boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),remote_monotonic_s=time.monotonic(),
 disk_free_bytes=shutil.disk_usage(base).free,meminfo=mem,config_sha256=hashes,
 service=props(service['stdout']),service_query_ok=service['returncode']==0,
 unit=system('systemctl','cat','zkp-rid-observer.service'),
 clock=system('timedatectl','show','-p','NTPSynchronized','-p','Timezone'),storage_status=status)))
'''


def private_path(path):
    """Reject symlink path components, even if the link points back into captures/."""
    path=Path(os.path.abspath(path))
    if not path.is_relative_to(ROOT/'captures'):raise ValueError('Use repository captures/ for private settings/results')
    for part in [path,*path.parents]:
        if part.is_symlink():raise ValueError('Private path symlink rejected')
    return path


def settings(path):
    path=private_path(path)
    if path.stat().st_mode&0o077:raise ValueError('Settings require owner-only permissions')
    cfg=json.loads(path.read_text())
    if set(cfg)!={'nodes'}:raise ValueError('Only node settings accepted')
    nodes=cfg['nodes'];seen=set()
    if not 1<=len(nodes)<=5:raise ValueError('Expected one to five B--F entries')
    for node in nodes:
        if set(node)-{'node_id','known_hosts','targets','user'}:raise ValueError('Unknown or sensitive node settings')
        name=node['node_id']
        if name not in ['observer-'+x for x in 'bcdef'] or name in seen:raise ValueError('Duplicate/unsupported receiver identity')
        seen.add(name)
        if node.get('user','pi')!='pi':raise ValueError('Only existing pi user supported')
        if any(k in node for k in ['password','private_key','secret']):raise ValueError('Do not store passwords in settings')
        if not Path(node['known_hosts']).is_file():raise ValueError('Saved known_hosts required')
        if not 1<=len(node['targets'])<=4:raise ValueError('Expected bounded target list')
        for target in node['targets']:
            if set(target)!={'host','host_key_alias'}:raise ValueError('Only host and saved-key alias accepted')
            for value in [target['host'],target['host_key_alias']]:
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]{0,252}',value):raise ValueError('Invalid host/alias')
    return sorted(nodes,key=lambda x:x['node_id'])


def finite(value):return isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value)


def sample_state(sample,expected):
    if sample.get('node_id')!=expected or sample.get('hostname')!=expected:return 'IDENTITY_MISMATCH'
    service=sample.get('service',{})
    if not sample.get('service_query_ok'):return 'SERVICE_STATE_UNKNOWN'
    if service.get('ActiveState')!='active':return 'SERVICE_NOT_ACTIVE'
    status=sample.get('storage_status')
    if not isinstance(status,dict):return 'STORAGE_HEARTBEAT_MISSING'
    if status.get('boot_id')!=sample.get('boot_id'):return 'PREVIOUS_BOOT_HEARTBEAT'
    now=sample.get('remote_monotonic_s');updated=status.get('updated_monotonic_s')
    if not finite(now) or not finite(updated):return 'STORAGE_HEARTBEAT_INVALID'
    age=now-updated
    if not 0<=age<=120:return 'STORAGE_HEARTBEAT_STALE'
    if status.get('state') not in ['STARTING','CAPTURE_ACTIVE']:return 'STORAGE_STOPPED'
    records=status.get('records_written')
    if not finite(records) or records<0:return 'STORAGE_COUNTER_INVALID'
    return 'RECORDER_ACTIVE' if records>0 else 'WAITING_FOR_OBSERVATIONS'


def rate(previous,current):
    """No slope across SSH gaps, boots, sessions, stale heartbeats or counter resets."""
    if not previous:return None,'FIRST_SAMPLE'
    a=previous.get('storage_status');b=current.get('storage_status')
    if not isinstance(a,dict) or not isinstance(b,dict):return None,'STATUS_UNAVAILABLE'
    if previous.get('boot_id')!=current.get('boot_id'):return None,'BOOT_CHANGED'
    if not a.get('session_id') or a.get('session_id')!=b.get('session_id'):return None,'SESSION_CHANGED'
    for sample in [previous,current]:
        if sample_state(sample,sample.get('node_id')) not in ['RECORDER_ACTIVE','WAITING_FOR_OBSERVATIONS']:
            return None,'RECORDER_NOT_HEALTHY'
    dt=current['remote_monotonic_s']-previous['remote_monotonic_s']
    before=a.get('session_bytes');after=b.get('session_bytes')
    if not all(finite(x) for x in [dt,before,after]) or dt<=0 or before<0 or after<before:return None,'COUNTER_OR_TIME_INVALID'
    return (after-before)/dt,'OBSERVED_SESSION_COUNTER_RATE'


def capacity(sample,bytes_per_s,hours=4):
    if bytes_per_s is None:return dict(state='NOT_EVALUABLE_NO_VALID_RATE')
    status=sample.get('storage_status') or {};budget=status.get('byte_budget');used=status.get('session_bytes');free=sample.get('disk_free_bytes')
    if not all(finite(x) for x in [bytes_per_s,budget,used,free]) or min(bytes_per_s,budget,used,free)<0:return dict(state='NOT_EVALUABLE_INVALID_COUNTERS')
    projected=bytes_per_s*hours*3600
    # A session's explicit 64MiB receiver reserve and the SD's 1GiB guard both remain enabled.
    session_left=max(0,budget-used-RESERVE);disk_left=max(0,free-GIB-RESERVE)
    fits=projected+used+RESERVE<=budget and projected+GIB+RESERVE<=free
    return dict(state='ESTIMATE_FITS_OBSERVED_RATE' if fits else 'ESTIMATE_EXCEEDS_AVAILABLE_BUDGET',
        horizon_hours=hours,projected_additional_bytes=projected,session_available_bytes=session_left,
        disk_available_bytes=disk_left,assumes_unchanged_observed_rate=True,measured_four_hour_test=False)


class Transport:
    def __init__(self,env):self.env=env
    def probe(self,node):
        attempts=[]
        for target in node['targets']:
            host=target['host'];alias=target['host_key_alias']
            # A separate Python TCP probe can disagree with OpenSSH's resolver/route.
            # Use the actual strict-key SSH result instead of suppressing a valid SSH path.
            check=subprocess.run(['ssh-keygen','-F',alias,'-f',node['known_hosts']],capture_output=True,timeout=5)
            if check.returncode:attempts.append(dict(target=host,state='SAVED_HOST_KEY_UNAVAILABLE'));continue
            cmd=['ssh','-T','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(Path(node['known_hosts']).resolve()),
                '-o','HostKeyAlias='+alias,'-o','ConnectTimeout=4','-o','ConnectionAttempts=1','-o','NumberOfPasswordPrompts=1',
                '-o','BatchMode='+('no' if 'RID_DEPLOY_PASSWORD' in self.env else 'yes'),
                'pi@'+host,'python3 -c '+__import__('shlex').quote(PROBE)]
            try:
                r=subprocess.run(cmd,capture_output=True,env=self.env,timeout=30)
                if r.returncode:
                    error=r.stderr.decode(errors='replace')[-4000:]
                    if self.env.get('RID_DEPLOY_PASSWORD'):error=error.replace(self.env['RID_DEPLOY_PASSWORD'],'[REDACTED]')
                    attempts.append(dict(target=host,state='SSH_OR_PROBE_FAILED',stderr=error));continue
                if len(r.stdout)>256*1024:raise ValueError('Probe response limit')
                data=json.loads(r.stdout)
                if not isinstance(data,dict):raise ValueError('Probe object required')
                return dict(state='PROBE_RECEIVED',sample=data,attempts=attempts)
            except (OSError,subprocess.TimeoutExpired,ValueError) as e:
                attempts.append(dict(target=host,state='PROBE_FAILED',error_type=type(e).__name__))
        return dict(state='CONNECTION_NOT_ESTABLISHED',attempts=attempts)


def cycle(nodes,transport,output,previous,elapsed):
    results=[]
    for node in nodes:
        label=node['node_id'][-1].upper();result=transport.probe(node);sample=result.get('sample')
        # One owner-private receipt is flushed per node, including every failure.
        receipt=output/(label+'-'+str(time.time_ns())+'-private.json')
        receipt.write_text(json.dumps(result,indent=2)+'\n')
        state=sample_state(sample,node['node_id']) if sample else result['state']
        prior=previous.get(label)
        changed=None
        if sample and prior and isinstance(sample.get('config_sha256'),dict) and isinstance(prior.get('config_sha256'),dict):
            changed=sample['config_sha256']!=prior['config_sha256']
        if state=='IDENTITY_MISMATCH':rate_value,rate_reason=None,'IDENTITY_MISMATCH'
        elif changed:rate_value,rate_reason=None,'CONFIGURATION_CHANGED'
        else:rate_value,rate_reason=rate(prior,sample) if sample else (None,'SSH_GAP')
        if sample and state not in ['IDENTITY_MISMATCH','SERVICE_STATE_UNKNOWN']:previous[label]=sample
        else:previous.pop(label,None)
        forecast=capacity(sample,rate_value) if sample else dict(state='NOT_EVALUABLE_NO_SAMPLE')
        row=dict(node=label,elapsed_s=round(elapsed,3),state=state,bytes_per_s=rate_value,rate_reason=rate_reason,
            four_hour_estimate=forecast['state'],configuration_changed=changed)
        if sample:
            row.update(memory_available_bytes=(sample.get('meminfo') or {}).get('MemAvailable'),disk_free_bytes=sample.get('disk_free_bytes'),
                       service_memory_bytes=(sample.get('service') or {}).get('MemoryCurrent'),
                       service_cpu_ns=(sample.get('service') or {}).get('CPUUsageNSec'),
                       storage_state=(sample.get('storage_status') or {}).get('state'),
                       records_written=(sample.get('storage_status') or {}).get('records_written'),
                       session_bytes=(sample.get('storage_status') or {}).get('session_bytes'))
        results.append(row)
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--private-output',type=Path,required=True);p.add_argument('--summary',type=Path,required=True)
    p.add_argument('--duration',type=float,default=0,help='0: one audit; 1..21600: bounded sampling seconds')
    p.add_argument('--interval',type=float,default=30);p.add_argument('--ask-password',action='store_true')
    a=p.parse_args()
    if not math.isfinite(a.duration) or not 0<=a.duration<=21600 or not math.isfinite(a.interval) or not 1<=a.interval<=300:p.error('bounded duration 0..21600 and interval 1..300 required')
    os.umask(0o077);out=private_path(a.private_output)
    if out.exists():p.error('New output directory required; preserve previous runs')
    nodes=settings(a.config);out.mkdir(parents=True,mode=0o700);a.summary.parent.mkdir(parents=True,exist_ok=True)
    if a.summary.exists():p.error('New public summary filename required')
    env=dict(os.environ);env.pop('RID_DEPLOY_PASSWORD',None);askpass=out/'askpass.sh';password=None
    if a.ask_password:
        password=getpass.getpass('Pi SSH password (not saved): ')
        if not password:p.error('Empty password not accepted')
        askpass.write_text('#!/bin/sh\nprintf "%s\\n" "$RID_DEPLOY_PASSWORD"\n');askpass.chmod(0o700)
        env.update(SSH_ASKPASS=str(askpass.resolve()),SSH_ASKPASS_REQUIRE='force',DISPLAY=':0',RID_DEPLOY_PASSWORD=password)
    previous={};rows=[];start=time.monotonic();reason='ONE_AUDIT_COMPLETE';exit_code=0
    try:
        with (out/'samples.csv').open('x',newline='') as f:
            writer=None
            while True:
                if rows and a.duration and time.monotonic()-start>=a.duration:
                    reason='BOUNDED_MONITOR_FINISHED';break
                sample=cycle(nodes,Transport(env),out,previous,time.monotonic()-start)
                rows.extend(sample)
                if writer is None:
                    fields=['node','elapsed_s','state','bytes_per_s','rate_reason','four_hour_estimate','configuration_changed','memory_available_bytes','disk_free_bytes','service_memory_bytes','service_cpu_ns','storage_state','records_written','session_bytes']
                    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
                writer.writerows(sample);f.flush();os.fsync(f.fileno())
                if not a.duration:break
                if all(x['state']=='CONNECTION_NOT_ESTABLISHED' for x in sample):reason='ALL_CONNECTIONS_UNAVAILABLE_STOPPED_WITH_RECEIPTS';break
                left=a.duration-(time.monotonic()-start)
                if left<=0:reason='BOUNDED_MONITOR_FINISHED';break
                time.sleep(min(a.interval,left))
    except KeyboardInterrupt:
        reason='INTERRUPTED_PARTIAL_SAMPLES_RETAINED';exit_code=130
    except Exception as e:
        reason='MONITOR_ERROR_PARTIAL_SAMPLES_RETAINED';exit_code=1
        (out/'error-private.json').write_text(json.dumps({'error_type':type(e).__name__})+'\n')
    finally:
        # Credentials never enter configuration files, argv or persisted receipts.
        env.pop('RID_DEPLOY_PASSWORD',None);password=None
        if askpass.exists():askpass.unlink()
    summary=dict(operation='READ_ONLY_AUDIT_AND_MONITOR',source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        reason=reason,requested_duration_s=a.duration,wall_elapsed_s=round(time.monotonic()-start,3),
        deployments_executed=0,services_restarted=0,captures_deleted=0,four_hour_capture_verified=False,
        nodes={x['node_id'][-1].upper():dict(samples=sum(r['node']==x['node_id'][-1].upper() for r in rows),
            last_state=next((r['state'] for r in reversed(rows) if r['node']==x['node_id'][-1].upper()),'NOT_SAMPLED'),deployment='NOT_EXECUTED') for x in nodes})
    a.summary.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
    if exit_code:raise SystemExit(exit_code)


if __name__=='__main__':main()
