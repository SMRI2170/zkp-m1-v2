#!/usr/bin/env python3
"""B snapshot audit with separate, untrusted reference decoding. No capture mutation."""
import argparse,collections,csv,datetime as dt,hashlib,json,os,statistics,subprocess
from pathlib import Path
MIB=1024**2

def utc(x):return dt.datetime.fromisoformat(x.replace('Z','+00:00')).timestamp()
def percentile(xs,p):
 if not xs:return None
 xs=sorted(xs);i=(len(xs)-1)*p;j=int(i);return xs[j]+(xs[min(j+1,len(xs)-1)]-xs[j])*(i-j)
def reference_decode(binary,payloads):
 if not payloads:return []
 r=subprocess.run([str(binary)],input='\n'.join(payloads)+'\n',capture_output=True,text=True,timeout=30);r.check_returncode();result=[json.loads(l) for l in r.stdout.splitlines()]
 if len(result)!=len(payloads):raise ValueError('reference output count mismatch')
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--reference-binary',type=Path,required=True);p.add_argument('--reference-metadata',type=Path,required=True);p.add_argument('--private-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();os.umask(0o077)
 if not a.private_output.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'captures'):raise ValueError('decoded IDs/coordinates must remain in ignored captures')
 for x in [a.private_output,a.output]:x.mkdir(parents=True,exist_ok=True)
 inv=json.loads((a.input/'inventory-private.json').read_text());root=a.input/'snapshot'/Path(inv['active_release']).relative_to('/home/pi/zkp-beacon-observer')/'captures'
 rows=[];files=0;incomplete=0
 for f in root.rglob('observations.jsonl'):
  files+=1
  for n,line in enumerate(f.open()):
   try:r=json.loads(line)
   except ValueError:incomplete+=1;continue
   r['_source_file']=str(f.relative_to(root));rows.append(r)
 bad=[r for r in rows if r.get('rid_parse_status')=='invalid'];decoded=reference_decode(a.reference_binary,[r['odid_payload_hex'] for r in bad]);ref_by_object={id(r):v for r,v in zip(bad,decoded)}
 # Keep all raw identifiers, claims and exact reference outputs private.
 with (a.private_output/'reference-decoded.jsonl').open('w') as f:
  for r,d in zip(bad,decoded):f.write(json.dumps({'capture':r,'reference':d})+'\n')
 clocks=collections.defaultdict(lambda:dict(rows=0,min_monotonic_s=float('inf'),max_monotonic_s=0,first_recorded_utc=None,last_recorded_utc=None,pi_rows=0,candidate_rows=0))
 series=[];candidate=[];seen=set();duplicates=0;duplicate_kinds=collections.Counter();roles=collections.Counter();parses=collections.Counter();versions=collections.Counter();reasons=collections.Counter();pi_identity_groups=set();candidate_identity_groups=set();ids=set();private_identity={}
 raw_pi_location=0;pi_looks_like_a=True
 for r in rows:
  role=r.get('source_annotation',{}).get('role','unknown');roles[role]+=1;parses[r.get('rid_parse_status')]+=1
  if r.get('rid_parse_reason'):reasons[r['rid_parse_reason']]+=1
  t=r.get('received_at_utc') or r.get('polled_at_utc');m=r.get('monotonic_time_us')
  if not t or m is None:continue
  unix=utc(t);mono=m/1e6;origin=round((unix-mono)/60)*60;c=clocks[origin];c['rows']+=1;c['min_monotonic_s']=min(c['min_monotonic_s'],mono);c['max_monotonic_s']=max(c['max_monotonic_s'],mono);c['first_recorded_utc']=min(c['first_recorded_utc'],t) if c['first_recorded_utc'] else t;c['last_recorded_utc']=max(c['last_recorded_utc'],t) if c['last_recorded_utc'] else t
  kind='registered_pi' if role=='onboard_pi' else 'unregistered_candidate'
  if kind=='registered_pi':
   c['pi_rows']+=1;pi_identity_groups.add((r.get('bssid'),tuple(r.get('claimed_uas_ids') or [])));raw_pi_location+=any(msg.get('latitude_deg') is not None for msg in r.get('messages') or []);pi_looks_like_a &= all(i.startswith('PI-RID-A-') for i in r.get('claimed_uas_ids') or [])
  else:c['candidate_rows']+=1;candidate_identity_groups.add(r.get('bssid'))
  raw=bytes.fromhex(r.get('odid_payload_hex') or '');version=raw[0]&15 if raw else None;versions[version]+=1
  key=(origin,r.get('bssid'),r.get('frequency_mhz'),m,r.get('vendor_content_digest'))
  if key in seen:duplicates+=1;duplicate_kinds[kind]+=1;continue
  seen.add(key);ref=ref_by_object.get(id(r),{})
  if ref.get('id_hex'):ids.add(ref['id_hex'])
  series.append(dict(clock_origin=origin,kind=kind,mono=mono,rssi=r.get('rssi_dbm'),version=version))
  if kind=='unregistered_candidate':candidate.append((mono,r,ref,origin))
 clock_keys=sorted(clocks);clock_labels={k:f'C{i+1}' for i,k in enumerate(clock_keys)}
 with (a.private_output/'source_rssi.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['clock_group','source_class','elapsed_s_within_clock_group','rssi_dbm','protocol_version'])
  for r in sorted(series,key=lambda x:(x['clock_origin'],x['mono'])):w.writerow([clock_labels[r['clock_origin']],r['kind'],r['mono']-clocks[r['clock_origin']]['min_monotonic_s'],r['rssi'],r['version']])
 candidate.sort(key=lambda x:(x[3],x[1].get('bssid',''),x[0]));dtimes=[b[0]-a0[0] for a0,b in zip(candidate,candidate[1:]) if b[3]==a0[3] and b[1].get('bssid')==a0[1].get('bssid') and b[0]>a0[0]];rssis=[x[1]['rssi_dbm'] for x in candidate if isinstance(x[1].get('rssi_dbm'),(int,float))]
 with (a.private_output/'candidate_intervals.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['positive_cache_update_interval_s']);w.writerows([x] for x in dtimes)
 # Position and altitude plots, if requested later, must use private decoded data, not public CSV.
 reference_counts=dict(attempted=len(bad),decode_success=sum(x.get('reference_decode_ok',False) for x in decoded),location_message=sum(x.get('location_valid',False) for x in decoded),nonzero_coordinate_claim=sum(bool(x.get('location_valid') and (x.get('claimed_latitude') or x.get('claimed_longitude'))) for x in decoded),height_claim=sum(x.get('claimed_height_m',-1000)>-1000 for x in decoded),geo_altitude_claim=sum(x.get('claimed_altitude_geo_m',-1000)>-1000 for x in decoded),timestamp_within_hour=sum(0<=x.get('claimed_seconds_within_hour',9999)<3600 for x in decoded),unique_claimed_ids=len(ids),identity_verified=False,real_drone_model_confirmed=False)
 metadata=json.loads(a.reference_metadata.read_text())
 summary=dict(snapshot_files=len(inv['files']),snapshot_bytes=sum(x['size'] for x in inv['files']),active_observation_files=files,raw_rows=len(rows),invalid_or_snapshot_tail_lines=incomplete,roles=dict(roles),production_parser_status=dict(parses),parser_reasons=dict(reasons),protocol_versions=dict(versions),exact_duplicate_rows=duplicates,exact_duplicate_rows_by_class=dict(duplicate_kinds),registered_pi_claimed_source_groups=len(pi_identity_groups),registered_pi_id_prefix_a=pi_looks_like_a,registered_pi_location_rows=raw_pi_location,unregistered_bssid_groups=len(candidate_identity_groups),reference=reference_counts,reference_commit=metadata['sha'],initial_clock_synchronized=False,initial_uptime_s=inv['remote_monotonic'],clock_groups=[dict(label=clock_labels[k],**v) for k,v in sorted(clocks.items())],candidate_rssi={'n':len(rssis),'min_dbm':min(rssis) if rssis else None,'median_dbm':statistics.median(rssis) if rssis else None,'max_dbm':max(rssis) if rssis else None},candidate_intervals={'n':len(dtimes),'median_s':statistics.median(dtimes) if dtimes else None,'p95_s':percentile(dtimes,.95),'max_s':max(dtimes) if dtimes else None},field_time_assignment='unresolved_due_to_historical_clock_offsets_and_missing_prior_boot_journal',physical_packet_count_known=False,settings_or_services_modified=False)
 (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
