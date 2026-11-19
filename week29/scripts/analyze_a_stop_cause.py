#!/usr/bin/env python3
"""Reconstruct accumulated byte history and compare deployed guards, without changing Pi."""
import argparse,ast,bisect,collections,csv,datetime as dt,hashlib,json,os,statistics
from pathlib import Path
JST=dt.timezone(dt.timedelta(hours=9));MIB=1024**2
ACTIVE='kit-509808cf5258-c838fbec'
def wall(v):return dt.datetime.fromisoformat(v.replace('Z','+00:00')).timestamp()
def iso(t):return dt.datetime.fromtimestamp(t,JST).isoformat()
def guard_expression(source,needle):
 tree=ast.parse(source)
 class Replace(ast.NodeTransformer):
  def visit_Call(self,n):
   if isinstance(n.func,ast.Name) and n.func.id=='sum':return ast.copy_location(ast.Name(id='used_bytes',ctx=ast.Load()),n)
   if isinstance(n.func,ast.Name) and n.func.id=='len':return ast.copy_location(ast.Name(id='file_count',ctx=ast.Load()),n)
   return self.generic_visit(n)
  def visit_Attribute(self,n):
   if n.attr=='free':return ast.copy_location(ast.Name(id='disk_free',ctx=ast.Load()),n)
   return self.generic_visit(n)
 for node in ast.walk(tree):
  if isinstance(node,ast.If) and any(isinstance(stmt,ast.Raise) and any(isinstance(x,ast.Constant) and x.value==needle for x in ast.walk(stmt)) for stmt in node.body):
   expr=ast.fix_missing_locations(ast.Expression(Replace().visit(node.test)))
   # Only pure expressions after replacing filesystem-dependent operations.
   for v in ast.walk(expr):
    if isinstance(v,(ast.Call,ast.Attribute,ast.Subscript)):raise ValueError('unexpected remaining operation')
   return ast.unparse(expr),compile(expr,'deployed guard','eval')
 raise ValueError('guard not found')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--private-output',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();os.umask(0o077)
 for p in [a.private_output,a.output]:p.mkdir(parents=True,exist_ok=True)
 root=a.input/'snapshot/releases'/ACTIVE/'captures';ev=a.input/'cause-evidence';deployed=json.loads((ev/'deployed-private.json').read_text());inventory=json.loads((a.input/'inventory-private.json').read_text())['files'];meta={f['path'].split('/releases/'+ACTIVE+'/captures/',1)[1]:f for f in inventory if '/releases/'+ACTIVE+'/captures/' in f['path']}
 recs=[];bases=[];kind_sizes=collections.Counter();first_last={};counts=collections.Counter()
 for sub,pattern,kind in [('flight-sensors','telemetry-*.jsonl','sensor'),('flight-tx','sent-*.jsonl','tx')]:
  for p in sorted((root/sub).glob(pattern)):
   for raw in p.open('rb'):
    o=json.loads(raw);t=o['host_monotonic_s'];recs.append((t,len(raw),kind));kind_sizes[kind]+=len(raw);counts[kind]+=1
    if kind=='sensor':bases.append(wall(o['host_utc'])-t)
 recs.sort();base=statistics.median(bases);start=recs[0][0];end=recs[-1][0]
 # Source emission time records are primary. Other files are added at their final mtime,
 # giving a completion-time approximation rather than pretending per-write measurements.
 extra=[]
 for rel,f in meta.items():
  if (rel.startswith('flight-sensors/telemetry-') or rel.startswith('flight-tx/sent-')) and rel.endswith('.jsonl'):continue
  extra.append((f['mtime']-base,f['size']))
 extra.sort();xt=[x[0] for x in extra];xc=[];z=0
 for _,n in extra:z+=n;xc.append(z)
 def extra_at(t):
  i=bisect.bisect_right(xt,t)-1;return xc[i] if i>=0 else 0
 events=[]
 for line in (a.input/'journal-boot-3.jsonl').open():
  o=json.loads(line);t=int(o['__MONOTONIC_TIMESTAMP'])/1e6;msg=o.get('MESSAGE','')
  k='sensor' if 'RuntimeError: sensor capture budget/headroom reached' in msg else 'tx' if 'RuntimeError: TX capture budget/headroom reached' in msg else 'rx' if 'CAPTURE_BUDGET_REACHED' in msg else None
  if k and start<=t<=end+600:events.append((t,k,int(o['__REALTIME_TIMESTAMP'])/1e6))
 stops={}
 for t,k,rt in sorted(events):stops.setdefault(k,dict(monotonic_s=t,jst=iso(rt),anchor_jst=iso(base+t),hours_since_start=(t-start)/3600))
 cum={'sensor':0,'tx':0};cross={};series=[];times=[];cs=[];ct=[];next_min=0
 for t,n,k in recs:
  cum[k]+=n;times.append(t);cs.append(cum['sensor']);ct.append(cum['tx'])
  threshold=(192 if k=='sensor' else 128)*MIB
  if cum[k]>threshold and k not in cross:cross[k]=dict(monotonic_s=t,jst=iso(base+t),hours_since_start=(t-start)/3600,bytes=cum[k])
  if (t-start)/60>=next_min:
   series.append(dict(hours=(t-start)/3600,jst=iso(base+t),sensor_mib=cum['sensor']/MIB,tx_mib=cum['tx']/MIB,jsonl_total_mib=sum(cum.values())/MIB,root_completed_mib=(sum(cum.values())+extra_at(t))/MIB));next_min=int((t-start)/60)+1
 series.append(dict(hours=(end-start)/3600,jst=iso(base+end),sensor_mib=cum['sensor']/MIB,tx_mib=cum['tx']/MIB,jsonl_total_mib=sum(cum.values())/MIB,root_completed_mib=(sum(cum.values())+extra_at(end))/MIB))
 comparisons={}
 for k,v in stops.items():
  t=v['monotonic_s'];i=bisect.bisect_right(times,t)-1;s=cs[i] if i>=0 else 0;tx=ct[i] if i>=0 else 0
  comparisons[k]=dict(**v,sensor_jsonl_mib=s/MIB,tx_jsonl_mib=tx/MIB,root_jsonl_mib=(s+tx)/MIB,root_completed_mib=(s+tx+extra_at(t))/MIB)
  if k in cross:comparisons[k]['seconds_from_jsonl_crossing']=t-cross[k]['monotonic_s']
 kernel=collections.Counter();voltage=[];other_examples=[]
 for p in ev.glob('kernel-clock-boot*.jsonl'):
  for line in p.open():
   try:o=json.loads(line)
   except ValueError:continue
   m=o.get('MESSAGE','').lower();t=int(o.get('__MONOTONIC_TIMESTAMP',0))/1e6
   if any(x in m for x in ['out of memory:','oom-kill:','killed process ']):kernel['oom']+=1
   if any(x in m for x in ['i/o error','ext4-fs error','mmc0: timeout']):kernel['sd_io_error']+=1
   if p.name=='kernel-clock-boot-3.jsonl' and start<=t<=max(v['monotonic_s'] for v in stops.values()):
    k='low' if 'undervoltage detected' in m or 'under-voltage detected' in m else 'normal' if 'voltage normalised' in m else None
    if k:voltage.append((t,k));kernel[k+'_during_history']+=1
 vb=collections.Counter(int((t-start)//1800) for t,k in voltage if k=='low')
 voltage_bins=[dict(hours_start=i*.5,hours_end=(i+1)*.5,low_voltage_events=vb[i]) for i in range(int((end-start)//1800)+1)]
 # Compare the exact pure byte/file/free-space predicates from deployed source.
 checks=[]
 for name,k,needle in [('flight_sensors.py','sensor','sensor capture budget/headroom reached'),('flight_beacon.py','tx','TX capture budget/headroom reached')]:
  expr,code=guard_expression(deployed['sources'][name]['text'],needle);sub='flight-sensors' if k=='sensor' else 'flight-tx';fs=[v for rel,v in meta.items() if rel.startswith(sub+'/')];used=sum(x['size'] for x in fs)
  observed={'used_bytes':used,'file_count':len(fs),'disk_free':deployed['disk']['free']}
  result=eval(code,{'__builtins__':{}},observed);empty=eval(code,{'__builtins__':{}},{**observed,'used_bytes':0,'file_count':0})
  checks.append(dict(kind=k,source_sha256=deployed['sources'][name]['sha256'],expression=expr,used_bytes=used,file_count=len(fs),current_disk_free_bytes=deployed['disk']['free'],observed_state_guard=result,empty_new_directory_guard=empty))
 for name in ['oom','sd_io_error','low_during_history','normal_during_history']:kernel.setdefault(name,0)
 # Receiver guard is a pure function; compile only that function from the deployed source.
 tree=ast.parse(deployed['sources']['boot_observer.py']['text']);func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='capacity');ns={'__builtins__':{}}
 exec(compile(ast.Module(body=[func],type_ignores=[]),'deployed receiver capacity','exec'),ns)
 mem_kib=int(next(line.split(':',1)[1].split()[0] for line in deployed['meminfo'].splitlines() if line.startswith('MemAvailable:')))
 used=sum(f['size'] for f in meta.values());free=deployed['disk']['free']
 receiver_probe=dict(expression='deployed capacity(root, mem_kib, disk_free, used_bytes, files)',source_sha256=deployed['sources']['boot_observer.py']['sha256'],snapshot_used_bytes=used,mem_available_kib=mem_kib,disk_free_bytes=free,observed_result=ns['capacity'](None,mem_kib,free,used,len(meta)),empty_new_directory_result=ns['capacity'](None,mem_kib,free,0,0))
 rates={}
 for k in ['sensor','tx']:
  rr=[(t,n) for t,n,kind in recs if kind==k];duration=rr[-1][0]-rr[0][0]
  rates[k]=dict(records=counts[k],jsonl_bytes=kind_sizes[k],duration_s=duration,records_per_s=(len(rr)-1)/duration,bytes_per_record=kind_sizes[k]/len(rr),mib_per_hour=kind_sizes[k]/MIB/(duration/3600),four_hour_jsonl_mib=kind_sizes[k]/MIB/(duration/3600)*4)
 summary=dict(start_jst=iso(base+start),end_jst=iso(base+end),clock_anchor_spread_s=max(bases)-min(bases),clock_anchor_basis='Median sensor host_utc minus host_monotonic_s; not an independent UTC calibration',stops=comparisons,crossings=cross,rates=rates,guard_checks=checks,receiver_probe=receiver_probe,kernel_evidence=dict(kernel),scope='Active A release, same long-running boot; later boot errors separately audited',limits=['Completed-file root history is an approximation, not historic disk telemetry.','No OOM/SD I/O message in collected kernel logs does not exclude all hardware faults.','Voltage events are warnings, not unique power outages.','No field reception or precise power-off duration is inferred.'])
 for name,rows in [('byte_history.csv',series),('voltage_history.csv',voltage_bins)]:
  with (a.output/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 # Exact low-voltage event times and source clock anchor remain private.
 (a.private_output/'voltage-events.json').write_text(json.dumps(voltage));(a.private_output/'clock-anchor.json').write_text(json.dumps({'base_unix_s':base,'first_monotonic_s':start}))
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
