#!/usr/bin/env python3
"""Sequential bounded three-node RF experiments over existing SSH control sockets.

Passwords are read interactively, used on sudo stdin, never saved. This program
never changes networking, sudoers, keys, or service startup settings. Raw data
and connection configuration must remain in ignored owner-private captures/.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import resource
import shlex
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'uav'))
from wifi_beacon_capture import private_output


def plan(repetitions=3, duration=15, sustain=90, mode="full", sustain_scope="target"):
    if not 1 <= repetitions <= 3 or not 5 <= duration <= 30 or not 5 <= sustain <= 90:
        raise ValueError('repetitions 1..3, duration 5..30s, sustain 5..90s')
    if mode not in ['full','sustain-only'] or sustain_scope not in ['target','all']:
        raise ValueError('invalid bounded plan mode/scope')
    rows=[]
    # Reverse order each repetition; fixed explicit order, not randomized inference.
    profiles=[(scope, spacing) for scope in ['target','all'] for spacing in [.25,1.0]]
    for rep in range(repetitions if mode=='full' else 0):
        for scope,spacing in (profiles if rep%2==0 else list(reversed(profiles))):
            for tx in (['a','b'] if rep%2==0 else ['b','a']):
                rows.append(dict(kind='matrix', repetition=rep+1, transmitter=tx,
                                 scope=scope, spacing_s=spacing, duration_s=duration))
    for tx in ['a','b']:
        rows.append(dict(kind='sustain',repetition=1,transmitter=tx,scope=sustain_scope,spacing_s=.25,duration_s=sustain))
    return rows


class Runner:
    def __init__(self, config, output, password):
        self.nodes=config['nodes'];self.output=output;self.password=password
        self.tag='ext-'+uuid.uuid4().hex[:8]
        self.created=[]
        for key,node in self.nodes.items():
            if key not in ['a','b','c'] or not re.fullmatch(r'pi@[A-Za-z0-9.:-]+',node['host']):
                raise ValueError('only the configured observer pi hosts are allowed')
            if len(os.fsencode(node['socket']))>=104:raise ValueError('SSH control socket path must be shorter than 104 bytes')
            if not Path(node['socket']).is_socket():raise ValueError('existing SSH control socket required')
        if set(self.nodes)!=set('abc'):raise ValueError('three distinct configured nodes required')

    def ssh(self,node,command,root=False,timeout=12):
        target=self.nodes[node]
        # Do not open an alternate unauthenticated SSH path if a master is lost.
        subprocess.run(['ssh','-S',target['socket'],'-O','check',target['host']],
                       check=True,capture_output=True,timeout=3)
        if root:command=['sudo','-S','-p','',*command]
        result=subprocess.run(['ssh','-S',target['socket'],'-o','BatchMode=yes',target['host'],
                               shlex.join(command)],input=(self.password+'\n') if root else None,
                              text=True,capture_output=True,timeout=timeout)
        if result.returncode:raise RuntimeError(f'{node}: remote command exit {result.returncode}')
        return result.stdout

    def launch(self,node,unit,command,duration,receiver=False):
        args=['systemd-run','--unit='+unit,'--property=RuntimeMaxSec='+str(duration+30),
              '--property=MemoryMax=128M','--property=TimeoutStopSec=15']
        if receiver:args+=['--uid=pi','--property=AmbientCapabilities=CAP_NET_ADMIN',
                           '--property=CapabilityBoundingSet=CAP_NET_ADMIN']
        # Register before launch so an SSH response loss still gets exact-unit cleanup.
        self.created.append((node,unit))
        self.ssh(node,args+command,root=True)

    def status(self,node,unit):
        begin=time.monotonic()
        text=self.ssh(node,['systemctl','show',unit,'-p','ActiveState','-p','Result','-p','ExecMainStatus',
                            '-p','MemoryCurrent','-p','MemoryPeak','-p','CPUUsageNSec'])
        d=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
        mem=self.ssh(node,['grep','MemAvailable','/proc/meminfo'])
        d.update(node=node,unit=unit,mem_available_kib=int(mem.split()[1]),ssh_elapsed_s=time.monotonic()-begin)
        return d

    def receipt(self,node,run_id):
        return json.loads(self.ssh(node,['cat','/run/zkp-beacon-'+run_id+'/receipt.json'],root=True))

    def stop(self,node,unit):
        text=self.ssh(node,['systemctl','show',unit,'-p','ActiveState','-p','LoadState'])
        state=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
        if state.get('ActiveState') in ['inactive','failed']:
            return  # successful transient units may already be unloaded
        if state.get('ActiveState') not in ['active','activating','deactivating','reloading']:
            raise RuntimeError('cannot establish unit state before cleanup')
        self.ssh(node,['systemctl','stop',unit],root=True,timeout=20)

    def trial(self,index,item):
        tx=item['transmitter'];rx=[n for n in 'abc' if n!=tx]
        run_id=f'{self.tag}-{index:02d}'
        txunit='zkp-beacon-'+run_id
        result=dict(index=index,condition=item,run_id=run_id,started_at_utc=datetime.now(timezone.utc).isoformat(),
                    receivers={},resources=[],status='FAILED')
        # Hard transmitter bound remains <=120s; no bypass of the existing sender cap.
        command=['/usr/bin/python3',self.nodes[tx]['transmitter_script'],
                 '--encoder',self.nodes[tx]['encoder'],'--ap','ap0','--beacon-only-compat',
                 '--run-id',run_id,'--counter',str(40+index),'--lat','35','--lon','139','--alt','50',
                 '--duration',str(item['duration_s']+15)]
        jobs=[]
        with private_output(self.output/f'trial-{index:02d}.json') as detail:
            try:
                self.launch(tx,txunit,command,item['duration_s']+15)
                deadline=time.monotonic()+15
                receipt=None
                while time.monotonic()<deadline:
                    try:receipt=self.receipt(tx,run_id)
                    except (RuntimeError,json.JSONDecodeError):receipt=None
                    if receipt and receipt.get('status')=='AP_ENABLED':break
                    if receipt and receipt.get('status')=='FAILED':raise RuntimeError('transmitter failed startup')
                    time.sleep(1)
                else:raise RuntimeError('transmitter readiness deadline')
                result['tx_receipt_at_start']=receipt
                for node in rx:
                    unit='zkp-scan-'+run_id+'-'+node
                    args=['/home/pi/zkp-beacon-observer/run','--duration',str(item['duration_s']),
                          '--interval','0.1','--active-scan','--scan-interval',str(item['spacing_s'])]
                    if item['scope']=='target':args+=['--frequency',str(receipt['frequency_mhz'])]
                    jobs.append((node,unit));self.launch(node,unit,args,item['duration_s'],receiver=True)
                deadline=time.monotonic()+item['duration_s']+25
                while True:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        states=list(pool.map(lambda job:self.status(*job),jobs))
                    for state in states:
                        state['sampled_at_utc']=datetime.now(timezone.utc).isoformat()
                        result['resources'].append(state)
                    if any(s['mem_available_kib']<100*1024 for s in states):raise RuntimeError('low available host memory')
                    if all(s['ActiveState'] not in ['active','activating','deactivating'] for s in states):break
                    if time.monotonic()>deadline:raise RuntimeError('receiver completion deadline')
                    time.sleep(3)
                for node,unit in jobs:
                    log=self.ssh(node,['journalctl','-u',unit,'--no-pager','-o','cat'])
                    entries=[]
                    for line in log.splitlines():
                        try:
                            d=json.loads(line)
                            if isinstance(d,dict) and 'capture' in d:entries.append(d)
                        except json.JSONDecodeError:pass
                    if len(entries)!=1:raise RuntimeError('receiver summary missing or ambiguous')
                    result['receivers'][node]=entries[0]
                if any(v['exit_code'] not in (0,3) for v in result['receivers'].values()):
                    raise RuntimeError('receiver reported failure')
                result['status']='COMPLETED'
            except (RuntimeError,subprocess.SubprocessError,OSError) as e:
                result['error_type']=type(e).__name__;result['reason']=str(e)
            finally:
                errors=[]
                for node,unit in jobs+[(tx,txunit)]:
                    try:self.stop(node,unit)
                    except (RuntimeError,subprocess.SubprocessError,OSError):errors.append(node+':'+unit)
                result['cleanup_errors']=errors
                try:result['tx_receipt_final']=self.receipt(tx,run_id)
                except (RuntimeError,subprocess.SubprocessError,OSError,json.JSONDecodeError):
                    result['tx_receipt_final']=None
                result['finished_at_utc']=datetime.now(timezone.utc).isoformat()
                detail.write(json.dumps(result,indent=2)+'\n');detail.flush()
        clean=(not result['cleanup_errors'] and result['tx_receipt_final'] and
               result['tx_receipt_final'].get('temporary_ap_removed') is True)
        if not clean:raise RuntimeError('cleanup not confirmed; sequence stopped')
        return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--repetitions',type=int,default=3)
    p.add_argument('--duration',type=int,default=15)
    p.add_argument('--sustain',type=int,default=90)
    p.add_argument('--mode',choices=['full','sustain-only'],default='full')
    p.add_argument('--sustain-scope',choices=['target','all'],default='target')
    args=p.parse_args()
    items=plan(args.repetitions,args.duration,args.sustain,args.mode,args.sustain_scope)
    cfg=json.loads(args.config.read_text())
    if args.config.stat().st_mode&0o077:p.error('config must be owner-private')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    secret=getpass.getpass('Pi sudo password (not saved): ')
    runner=Runner(cfg,args.output_dir,secret)
    failed=0
    with private_output(args.output_dir/'plan.json') as f:f.write(json.dumps(items,indent=2)+'\n')
    with private_output(args.output_dir/'progress.jsonl') as progress:
        for index,item in enumerate(items):
            try:result=runner.trial(index,item)
            except (RuntimeError,subprocess.SubprocessError,OSError) as e:
                progress.write(json.dumps(dict(index=index,status='ABORTED',error_type=type(e).__name__))+'\n')
                print(json.dumps(dict(index=index,status='ABORTED',error_type=type(e).__name__)),flush=True)
                return 2
            status=dict(index=index,condition=item,status=result['status'],
                        receiver_codes={n:d['exit_code'] for n,d in result['receivers'].items()})
            progress.write(json.dumps(status)+'\n');progress.flush()
            print(json.dumps(status),flush=True)
            failed+=result['status']!='COMPLETED'
    return 2 if failed else 0


if __name__=='__main__':
    raise SystemExit(main())
