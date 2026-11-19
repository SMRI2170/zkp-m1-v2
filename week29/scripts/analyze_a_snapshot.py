#!/usr/bin/env python3
"""Read-only, streaming audit. Outputs remain private; no inferred power states."""
import argparse,collections,csv,datetime as dt,hashlib,json,os
from pathlib import Path
JST=dt.timezone(dt.timedelta(hours=9))
START=dt.datetime(2026,11,16,14,tzinfo=JST);END=dt.datetime(2026,11,16,18,tzinfo=JST)
def stamp(v):
 if not isinstance(v,str):return None
 try:
  x=dt.datetime.fromisoformat(v.replace('Z','+00:00'))
  return x.astimezone(JST) if x.tzinfo else None
 except ValueError:return None
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--input',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
 os.umask(0o077);out=args.output;out.mkdir(parents=True,exist_ok=True,mode=0o700)
 root=args.input/'snapshot';active='kit-509808cf5258-c838fbec'
 stats={};days=collections.Counter();bins=collections.Counter();manifest=[];seen=set()
 files=list(root.rglob('*'));allfiles=[p for p in files if p.is_file()]
 for p in sorted(allfiles):
  rel=str(p.relative_to(root));sha=digest(p);manifest.append(dict(path=rel,bytes=p.stat().st_size,sha256=sha))
  if p.suffix!='.jsonl':continue
  kind='sensor' if p.name.startswith('telemetry-') else 'tx' if p.name.startswith('sent-') else 'rx' if p.name=='observations.jsonl' else 'event'
  scope='active' if active in p.parts else 'historical'
  key=scope+'/'+kind
  s=stats.setdefault(key,dict(files=0,duplicate_files=0,rows=0,invalid_json=0,timestamped=0,without_timestamp=0,field_rows=0,first=None,last=None,gps_valid=0,bme_valid=0,rssi_rows=0))
  s['files']+=1
  # Identical exported files are counted once within each scope and record kind.
  dedupe=(scope,kind,sha)
  if dedupe in seen:s['duplicate_files']+=1;continue
  seen.add(dedupe)
  with p.open(errors='replace') as f:
   for line in f:
    if not line.strip():continue
    try:r=json.loads(line)
    except (ValueError,UnicodeError):s['invalid_json']+=1;continue
    if not isinstance(r,dict):s['invalid_json']+=1;continue
    s['rows']+=1
    if (r.get('gps') or {}).get('valid') is True:s['gps_valid']+=1
    if (r.get('bme280') or {}).get('valid') is True:s['bme_valid']+=1
    if isinstance(r.get('rssi_dbm'),(float,int)):s['rssi_rows']+=1
    t=next((x for k in ['host_utc','received_at_utc','polled_at_utc','captured_at_utc','utc'] if (x:=stamp(r.get(k))) is not None),None)
    if t is None:s['without_timestamp']+=1;continue
    s['timestamped']+=1;iso=t.isoformat()
    if s['first'] is None or iso<s['first']:s['first']=iso
    if s['last'] is None or iso>s['last']:s['last']=iso
    days[(scope,kind,t.date().isoformat())]+=1
    if START<=t<END:
     s['field_rows']+=1;bins[(scope,kind,int((t-START).total_seconds()//1800))]+=1
 boot=[]
 for p in args.input.glob('journal-boot*.jsonl'):
  label=p.stem.replace('journal-boot','boot ');rows=[];first_errors={}
  for line in p.open():
   try:r=json.loads(line)
   except ValueError:continue
   rows.append(r);msg=r.get('MESSAGE','')
   k='rx' if 'CAPTURE_BUDGET_REACHED' in msg else 'sensor' if 'RuntimeError: sensor capture budget/headroom reached' in msg else 'tx' if 'RuntimeError: TX capture budget/headroom reached' in msg else None
   if k and k not in first_errors:
    us=int(r.get('__MONOTONIC_TIMESTAMP',0));wall=int(r.get('__REALTIME_TIMESTAMP',0))
    first_errors[k]=dict(since_boot_s=us/1e6,recorded_utc=dt.datetime.fromtimestamp(wall/1e6,dt.timezone.utc).isoformat())
  boot.append(dict(label=label,journal_rows=len(rows),first_budget_errors=first_errors))
 summary=dict(window_jst=[START.isoformat(),END.isoformat()],scope='All capture directories under A release root; active and historical are separate',snapshot_files=len(allfiles),snapshot_bytes=sum(p.stat().st_size for p in allfiles),archive_sha256=digest(args.input/'a-captures.tar.gz'),stats=stats,boot_errors=boot,limits=['Host timestamps are not independently field-validated.','TX JSONL lacks UTC; it is not assigned to the field window.','No log does not prove power-off or reception failure.','Historical records are not field measurements of this experiment.'])
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 (out/'manifest-private.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 with (out/'daily_counts.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['scope','kind','recorded_jst_date','rows']);w.writerows((*k,v) for k,v in sorted(days.items()))
 with (out/'field_30min_counts.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['scope','kind','window_start_jst','rows'])
  for scope in ['active','historical']:
   for kind in ['rx','sensor','tx']:
    for i in range(8):w.writerow([scope,kind,(START+dt.timedelta(minutes=30*i)).isoformat(),bins[scope,kind,i]])
 print(json.dumps({k:v for k,v in stats.items() if k.startswith('active/')},ensure_ascii=False,indent=2));print('SNAPSHOT',len(allfiles),'files')
if __name__=='__main__':main()
