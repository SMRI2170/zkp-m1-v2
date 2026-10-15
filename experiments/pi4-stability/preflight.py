# coding: utf-8
"""Public-safe, fail-closed Pi preflight; missing runtime guards are data, not crashes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

WATCHDOG_SHA256 = 'f1f72622b08685f2d31ecbcf58cd602de7d338ea1df93b6e2f266db12ea383ce'
LIMITS = {'memory.high': 1200 * 1024**2, 'memory.max': 1536 * 1024**2, 'memory.swap.max': 0}

def command(args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None, ''

def snapshot(root=Path('/'), run=command):
    errors = []
    def read(path, parse=str):
        try:
            return parse((root / path.lstrip('/')).read_text().strip())
        except (OSError, ValueError):
            errors.append('unavailable:' + path)
            return None
    mem = read('/proc/meminfo', lambda s: {k: int(v.split()[0])*1024 for k,v in
               (line.split(':', 1) for line in s.splitlines()) if k in ['MemAvailable','SwapTotal','SwapFree']}) or {}
    _, pid = run(['systemctl','show','ssh.service','-p','MainPID','--value'])
    ssh_adj = read('/proc/'+pid+'/oom_score_adj', int) if pid.isdecimal() and int(pid)>0 else None
    _, group = run(['systemctl','show','week24-memory-watchdog.service','-p','ControlGroup','--value'])
    power_rc, power = run(['vcgencmd','get_throttled'])
    try:
        bits = int(power.split('=', 1)[1], 16) if power_rc == 0 else None
    except (IndexError, ValueError):
        bits = None
    temp = read('/sys/class/thermal/thermal_zone0/temp', lambda s: int(s)/1000)
    limits = {n:read('/sys/fs/cgroup/week24.slice/'+n,int) for n in LIMITS}
    watch = root / 'run/week24/memory_watchdog.py'
    try:
        st = watch.stat()
        watch_secure = st.st_uid == 0 and st.st_mode & 0o022 == 0 and not watch.is_symlink()
        digest = hashlib.sha256(watch.read_bytes()).hexdigest()
    except OSError:
        watch_secure, digest = False, None
    state = {
        'schema_version': 1, 'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'uptime_s':read('/proc/uptime',lambda s:float(s.split()[0])),
        'mem_available_bytes':mem.get('MemAvailable'),
        'system_swap_used_bytes':mem['SwapTotal']-mem['SwapFree'] if all(k in mem for k in ['SwapTotal','SwapFree']) else None,
        'temperature_C':temp, 'throttled':hex(bits) if bits is not None else None,
        'slice_active':run(['systemctl','is-active','--quiet','week24.slice'])[0] == 0,
        'watchdog_active':run(['systemctl','is-active','--quiet','week24-memory-watchdog.service'])[0] == 0,
        'watchdog_secure_file':watch_secure, 'watchdog_sha256':digest,
        'watchdog_outside_slice':group.startswith('/') and group != '/' and not(group == '/week24.slice' or group.startswith('/week24.slice/')),
        'ssh_oom_score_adj':ssh_adj, 'parent_limits_bytes':limits,
        'reboot_cause':'unknown', 'scope':'instantaneous readiness; not a guarantee against reboot or SSH loss'}
    for label, boot in [('current','0'),('previous','-1')]:
        rc, log = run(['journalctl','-k','-b',boot,'--no-pager'])
        readable = rc == 0 and bool(log) and log != '-- No entries --'
        state[label+'_journal_readable'] = readable
        state[label+'_kernel_oom_matches'] = len(re.findall(r'oom-kill|out of memory|Killed process',log,re.I)) if readable else None
        state[label+'_kernel_undervoltage_matches'] = len(re.findall('Undervoltage detected',log)) if readable else None
    checks = {'memory_reserve':mem.get('MemAvailable',0)>=1024**3,
              'no_system_swap':state['system_swap_used_bytes']==0,
              'current_power_clear':bits is not None and bits & 0xF == 0,
              'temperature_available':temp is not None,
              'uptime_available':state['uptime_s'] is not None,
              'parent_limits':limits==LIMITS, 'slice_active':state['slice_active'],
              'watchdog_active':state['watchdog_active'],
              'watchdog_integrity':watch_secure and digest==WATCHDOG_SHA256,
              'watchdog_outside_slice':state['watchdog_outside_slice'], 'ssh_protected':ssh_adj == -900}
    state.update(checks=checks,ready=all(checks.values()),unavailable=errors)
    return state

def summarize(rows):
    uptimes = [x.get('uptime_s') for x in rows]
    no_reset = all(a is not None and b is not None and b>=a for a,b in zip(uptimes,uptimes[1:]))
    duration = uptimes[-1]-uptimes[0] if rows and no_reset and None not in uptimes else None
    return {'samples':len(rows),'observed_uptime_span_s':duration,
            'no_observed_uptime_reset':no_reset,'all_ready':bool(rows) and all(x['ready'] for x in rows),
            'scope':'sampled short preflight only; does not establish long-term stability or reboot cause'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--samples',type=int,default=3);p.add_argument('--interval-s',type=float,default=30)
    a=p.parse_args()
    if not 1 <= a.samples <= 121 or not 0 < a.interval_s <= 60: p.error('samples 1..121, interval (0,60]')
    a.out.mkdir(mode=0o700,parents=True) # Refuse reused or incomplete evidence directory.
    rows=[]
    with (a.out/'health.jsonl').open('x') as f:
        for i in range(a.samples):
            if i:time.sleep(a.interval_s)
            row=snapshot();rows.append(row);f.write(json.dumps(row)+'\n');f.flush()
            print(json.dumps({'sample':i,'ready':row['ready'],'failed_checks':[k for k,v in row['checks'].items() if not v]}),flush=True)
            if not row['ready']:break
    summary=summarize(rows);(a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if summary['all_ready'] and summary['no_observed_uptime_reset'] and len(rows)==a.samples else 1

if __name__ == '__main__':raise SystemExit(main())
