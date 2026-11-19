#!/usr/bin/env python3
"""Read-only snapshot audit, bounded SQLite workspace and conservative clock candidates.

All raw values, keys, paths and matching ledgers stay in ignored captures/.
Content equality never promotes a candidate to a confirmed physical packet.
"""
import argparse
import collections
import csv
import datetime as dt
import hashlib
import itertools
import json
import math
import os
import sqlite3
import statistics
import subprocess
from pathlib import Path


def epoch(value):
    if not isinstance(value,str):return None
    try:
        t=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        return t.timestamp() if t.tzinfo is not None else None
    except (ValueError,OverflowError):return None


def circular_difference(a,b,period=3600):
    return (a-b+period/2)%period-period/2


def unwrap_next(previous,within_hour,elapsed):
    """Hypothesis only: choose hour nearest elapsed monotonic prediction."""
    return within_hour+3600*round((previous+elapsed-within_hour)/3600)


def packet_shape(payload):
    try:r=bytes.fromhex(payload)
    except (TypeError,ValueError):return False
    return (len(r)>=3 and r[0]>>4==15 and r[0]&15<=2 and r[1]==25 and
            1<=r[2]<=9 and len(r)==3+25*r[2])


def observation_key(node,row,locator):
    t=epoch(row.get('received_at_utc') or row.get('polled_at_utc'))
    mono=row.get('monotonic_time_us')
    if t is None or not isinstance(mono,(float,int)):
        # Missing clocks are not deduplicated by guessed time or content alone.
        parts=(node,'unknown-clock',locator)
    else:
        parts=(node,round(t*1e6),mono,row.get('bssid'),row.get('frequency_mhz'),
               row.get('vendor_content_digest'),row.get('odid_payload_hex'),row.get('raw_vendor_ie_hex'))
    return hashlib.sha256(json.dumps(parts,sort_keys=True).encode()).hexdigest()


def clock_partitions(rows,tolerance_s=5):
    """Cluster UTC-minus-monotonic offsets without minute-rounding boundary artifacts.

    Bounded offset spread is a clock correspondence, never a verified boot ID.
    """
    buckets=collections.defaultdict(list)
    for row in rows:
        if row['utc'] is None or row['mono'] is None:
            buckets[(row['node'],row['boot'],'unknown:'+row['key'])].append(row)
        else:buckets[(row['node'],row['boot'],'known')].append(row)
    result=[]
    for (node,boot,known),items in sorted(buckets.items()):
        if known!='known':result.append((node,boot,None,items));continue
        current=[];origin=None
        for row in sorted(items,key=lambda r:r['utc']-r['mono']):
            offset=row['utc']-row['mono']
            if current and offset-origin>tolerance_s:
                result.append((node,boot,origin,current));current=[]
            if not current:origin=offset
            current.append(row)
        if current:result.append((node,boot,origin,current))
    return result


def read_jsonl(path):
    with path.open(errors='replace') as f:
        for i,line in enumerate(f,1):
            if not line.strip():continue
            try:
                row=json.loads(line)
                if not isinstance(row,dict):raise ValueError('non-object')
                yield i,row,None
            except ValueError:
                yield i,None,dict(line=i,final_line_without_newline=not line.endswith('\n'))


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def describe(values):
    if not values:return dict(n=0)
    median=statistics.median(values)
    return dict(n=len(values),min=min(values),median=median,max=max(values),
                mad=statistics.median(abs(x-median) for x in values))


class Audit:
    def __init__(self,config,private,output):
        self.config=config;self.private=private;self.output=output
        self.db=sqlite3.connect(private/'audit-private.sqlite')
        self.db.executescript('''PRAGMA cache_size=-32768; PRAGMA temp_store=FILE;
        CREATE TABLE observations (key TEXT PRIMARY KEY,node TEXT,release TEXT,locator TEXT,
          received TEXT,utc REAL,mono REAL,boot TEXT,payload TEXT,rssi REAL,role TEXT,
          parse_status TEXT,reason TEXT,vendor_format TEXT,receiver_position INTEGER,
          stale INTEGER,copies INTEGER DEFAULT 1);
        CREATE TABLE payloads (payload TEXT PRIMARY KEY,decoded TEXT,classification TEXT);
        CREATE INDEX observation_payload ON observations(payload);
        CREATE INDEX observation_node ON observations(node);
        ''')
        self.summary=dict(nodes={},clock_groups=[],content_matches=[],limitations=[
            'RID time-within-hour does not identify a date or hour.',
            'Content matches and fitted clock offsets are candidates, not same-physical-packet proof.',
            'Recorded calendar windows are not independently verified field-time assignments.',
            'Declared RID/GPS positions are not independently established truth.',
            'No transmitter packet denominator is available.'])
        self.summary['audit_code_sha256']=sha(Path(__file__))
        if config.get('reference_binary'):
            self.summary['reference_binary_sha256']=sha(Path(config['reference_binary']))
        self.files=[];self.bad=[];self.sensor_phases=[]

    def observation(self,node,release,row,locator):
        t=row.get('received_at_utc') or row.get('polled_at_utc');m=row.get('monotonic_time_us')
        payload=row.get('odid_payload_hex') or ''
        if not isinstance(payload,str):payload=''
        fix=row.get('receiver_position') or {}
        key=observation_key(node,row,locator)
        self.db.execute('''INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
          ON CONFLICT(key) DO UPDATE SET copies=copies+1,
          boot=CASE WHEN boot='' THEN excluded.boot ELSE boot END,
          receiver_position=MAX(receiver_position,excluded.receiver_position)''',
          (key,node,release,locator,t,epoch(t),m/1e6 if isinstance(m,(int,float)) else None,
           str(row.get('boot_scope') or ''),payload,row.get('rssi_dbm'),
           (row.get('source_annotation') or {}).get('role'),row.get('rid_parse_status'),
           row.get('rid_parse_reason'),row.get('vendor_format'),
           int(fix.get('latitude') is not None and fix.get('longitude') is not None),
           int(bool(row.get('cache_stale')))))
        if payload and packet_shape(payload):
            self.db.execute('INSERT OR IGNORE INTO payloads(payload) VALUES (?)',(payload,))

    def source(self,source):
        node=source['node'];snap=Path(source['snapshot']).resolve()
        expected=json.loads(Path(source['manifest']).read_text())
        if isinstance(expected,list):expected={x['path']:x['sha256'] for x in expected}
        actual={};scope=collections.defaultdict(collections.Counter);seen_files={};scope_names={}
        files=sorted(x for x in snap.rglob('*') if x.is_file())
        for index,path in enumerate(files):
            rel=str(path.relative_to(snap));digest=sha(path);actual[rel]=digest
            if path.stat().st_mode&0o077:raise ValueError(f'{node}: non-private input')
            release=path.parts[path.parts.index('releases')+1] if 'releases' in path.parts else 'app'
            if release not in scope_names:scope_names[release]=f'R{len(scope_names)+1:02d}'
            label=scope_names[release]
            kind=('rx' if path.name=='observations.jsonl' else 'sensor' if path.name.startswith('telemetry-')
                  else 'tx' if path.name.startswith('sent-') else 'event' if path.suffix=='.jsonl' else 'metadata')
            s=scope[label+'/'+kind];s['files']+=1;s['bytes']+=path.stat().st_size
            duplicate=seen_files.get((kind,digest));seen_files.setdefault((kind,digest),rel)
            self.files.append(dict(node=node,path=str(path),sha256=digest,bytes=path.stat().st_size,
                                   release=label,kind=kind,identical_to=duplicate))
            if path.suffix!='.jsonl':continue
            if duplicate is not None:s['identical_file_skipped']+=1;continue
            for line,row,error in read_jsonl(path):
                if error:s['invalid_json']+=1;self.bad.append(dict(node=node,path=rel,**error));continue
                s['valid_rows']+=1
                if kind=='rx':self.observation(node,label,row,rel+':'+str(line))
                if kind=='sensor':
                    gps=row.get('gps') or {};utc=epoch(row.get('host_utc'))
                    if gps.get('valid'):s['valid_gps_rows']+=1
                    clock=gps.get('nmea_utc_time')
                    if gps.get('valid') and utc is not None and isinstance(clock,str):
                        try:
                            seconds=int(clock[:2])*3600+int(clock[2:4])*60+float(clock[4:])
                            self.sensor_phases.append(circular_difference(utc,seconds,86400));s['nmea_time_only_rows']+=1
                        except ValueError:s['invalid_nmea_time']+=1
            if index%100==0:
                self.db.commit();(self.private/'progress.json').write_text(json.dumps({'node':node,'file_index':index,'files':len(files)}))
        self.db.commit()
        mismatches=[k for k,v in expected.items() if actual.get(k)!=v]
        additions=set(actual)-set(expected)
        if mismatches:raise ValueError(f'{node}: preserved manifest mismatch ({len(mismatches)})')
        self.summary['nodes'][node]=dict(snapshot_files=len(files),snapshot_bytes=sum(p.stat().st_size for p in files),
            baseline_manifest_entries=len(expected),baseline_hashes_verified=True,additional_files=len(additions),
            scopes={k:dict(v) for k,v in scope.items()},role='pi' if source.get('kind')=='pi' else 'android',
            field_assignment='NOT_EVALUABLE_without_additional_clock_anchors')
        if source.get('database'):
            path=Path(source['database']).resolve();db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
            integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
            if integrity!='ok':raise ValueError(f'{node}: SQLite integrity failure')
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0]!='sqlite_sequence']
            counts={t:db.execute('SELECT COUNT(*) FROM "'+t.replace('"','""')+'"').fetchone()[0] for t in tables}
            # Additional JSONL was scanned first: duplicates add provenance counts, not new observations.
            for ident,raw in db.execute('SELECT id,raw_json FROM observations'):
                self.observation(node,'DB',json.loads(raw),f'DB:observations:{ident}')
            self.summary['nodes'][node].update(sqlite_integrity=integrity,sqlite_tables=counts)
            db.close();self.db.commit()

    def decode(self):
        ident=json.loads(Path(self.config['identity_file']).read_text())['claimed_id']
        raw_ids={};counter=collections.Counter()
        cursor=self.db.execute('SELECT payload FROM payloads')
        while batch:=cursor.fetchmany(2000):
            p=subprocess.run([self.config['reference_binary']],input='\n'.join(x[0] for x in batch)+'\n',text=True,
                             capture_output=True,timeout=30);p.check_returncode()
            answers=[json.loads(l) for l in p.stdout.splitlines()]
            if len(answers)!=len(batch):raise ValueError('reference decode count mismatch')
            for (payload,),d in zip(batch,answers):
                match=d.get('reference_decode_ok') and bytes.fromhex(d.get('id_hex','')).rstrip(b'\0').decode(errors='replace')==ident
                kind='confirmed_drone' if match else 'other_decoded_rid' if d.get('reference_decode_ok') else 'reference_rejected'
                counter[kind]+=1
                self.db.execute('UPDATE payloads SET decoded=?,classification=? WHERE payload=?',(json.dumps(d),kind,payload))
            self.db.commit()
        self.summary['payload_decode_unique_counts']=dict(counter)

    def analysis(self):
        start,end=map(epoch,self.config['field_utc'])
        for node,s in self.summary['nodes'].items():
            s['canonical_observations']=self.db.execute('SELECT COUNT(*) FROM observations WHERE node=?',(node,)).fetchone()[0]
            s['duplicate_observation_occurrences']=self.db.execute('SELECT COALESCE(SUM(copies-1),0) FROM observations WHERE node=?',(node,)).fetchone()[0]
            classes=collections.Counter()
            for classification,role,vendor,n in self.db.execute('''SELECT p.classification,o.role,o.vendor_format,COUNT(*) FROM observations o LEFT JOIN payloads p USING(payload)
                WHERE node=? GROUP BY p.classification,o.role,o.vendor_format''',(node,)):
                kind=('confirmed_drone' if classification=='confirmed_drone' else 'onboard_pi' if role=='onboard_pi'
                      else 'unclassified_vendor' if vendor=='unclassified_wifi_candidate' else classification or 'unknown')
                classes[kind]+=n
            s['canonical_classification']=dict(classes)
            s['recorded_calendar_field_window_rows']=self.db.execute('SELECT COUNT(*) FROM observations WHERE node=? AND utc>=? AND utc<?',(node,start,end)).fetchone()[0]
        # Target observations with decoded claims, raw identifiers and exact clock groups stay private.
        target=[]
        self.db.row_factory=sqlite3.Row
        query='''SELECT o.*,p.decoded FROM observations o JOIN payloads p USING(payload) WHERE classification='confirmed_drone'
                 ORDER BY o.node,o.utc,o.mono'''
        for row in self.db.execute(query):
            d=dict(row);d['reference']=json.loads(d.pop('decoded'));target.append(d)
        private_groups=[]
        grouped=collections.defaultdict(list)
        for node,boot,origin,rows in clock_partitions(target):
            label=node+'-G'+str(sum(x['node']==node for x in private_groups)+1)
            for row in rows:row['clock_group']=label
            bymono=sorted(rows,key=lambda x:x['mono'] if x['mono'] is not None else float('inf'))
            phase=[circular_difference(x['utc'],x['reference']['claimed_seconds_within_hour']) for x in rows
                   if x['utc'] is not None and x['reference'].get('claimed_seconds_within_hour') is not None]
            item=dict(node=node,clock_group=label,rows=len(rows),recorded_utc_first=min(x['received'] for x in rows),
                recorded_utc_last=max(x['received'] for x in rows),rid_phase_receive_minus_claim_s=describe(phase),
                recorded_calendar_field_rows=sum(x['utc'] is not None and start<=x['utc']<end for x in rows),
                status='candidate_calendar_only' if any(x['utc'] is not None and start<=x['utc']<end for x in rows) else 'unresolved_calendar_offset',
                boot_id_verified=False)
            self.summary['clock_groups'].append(item)
            private_groups.append(dict(node=node,clock_group=label,boot_scope=boot,offset_bucket=origin))
            grouped[label]=rows
        matches=[]
        for (ga,ra),(gb,rb) in itertools.combinations(grouped.items(),2):
            if ra[0]['node']==rb[0]['node']:continue
            ma=collections.defaultdict(list);mb=collections.defaultdict(list)
            for r in ra:ma[r['payload']].append(r)
            for r in rb:mb[r['payload']].append(r)
            shared=set(ma)&set(mb)
            if not shared:continue
            offsets=[];unique=0;ambiguous=0
            for payload in sorted(shared):
                aa,bb=ma[payload],mb[payload]
                if len(aa)==len(bb)==1:unique+=1
                else:ambiguous+=1
                # Descriptive median-per-content; never claim selected observations were simultaneous.
                ta=[x['utc'] for x in aa if x['utc'] is not None];tb=[x['utc'] for x in bb if x['utc'] is not None]
                if ta and tb:offsets.append(statistics.median(tb)-statistics.median(ta))
                matches.append(dict(group_a=ga,group_b=gb,payload_sha256=hashlib.sha256(bytes.fromhex(payload)).hexdigest(),
                    observations_a=[x['locator'] for x in aa],observations_b=[x['locator'] for x in bb],
                    utc_offset_candidates_s=[y-x for x in ta for y in tb],physical_packet_status='candidate_content_only'))
            self.summary['content_matches'].append(dict(group_a=ga,group_b=gb,shared_contents=len(shared),
                one_to_one_content_candidates=unique,ambiguous_repeated_contents=ambiguous,
                utc_b_minus_a_descriptive_s=describe(offsets),status='candidate_content_only',
                physical_packet_confirmed=False))
        self.summary['target_canonical_rows']=len(target)
        self.summary['independent_calendar_anchors_verified']=0
        self.summary['sensor_time_only_phase_s']=describe(self.sensor_phases)
        (self.private/'target-observations-private.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in target))
        for name,data in [('file-manifest-private.json',self.files),('invalid-json-private.json',self.bad),
                          ('clock-groups-private.json',private_groups),('content-matches-private.json',matches)]:
            (self.private/name).write_text(json.dumps(data,indent=2)+'\n')
        (self.output/'summary.json').write_text(json.dumps(self.summary,indent=2)+'\n')
        for name,rows in [('clock-groups.csv',self.summary['clock_groups']),('content-matches.csv',self.summary['content_matches'])]:
            with (self.output/name).open('w',newline='') as f:
                if rows:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
                    for r in rows:w.writerow({k:json.dumps(v) if isinstance(v,dict) else v for k,v in r.items()})
        self.db.commit();self.db.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True)
    p.add_argument('--private-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if not a.private_output.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'captures'):
        raise ValueError('Private audit outputs must remain inside ignored captures/')
    if (a.private_output/'audit-private.sqlite').exists():raise ValueError('Use a new audit directory; do not overwrite prior workspaces')
    for folder in [a.private_output,a.output]:folder.mkdir(parents=True,exist_ok=True)
    config=json.loads(a.config.read_text());audit=Audit(config,a.private_output,a.output)
    (a.output/'status.json').write_text(json.dumps({'completed':False,'state':'running'})+'\n')
    try:
        for source in config['sources']:
            audit.source(source);print(source['node']+' snapshot audit complete',flush=True)
        audit.decode();print('reference decoding complete',flush=True)
        audit.analysis();print('clock candidate analysis complete',flush=True)
        (a.output/'status.json').write_text(json.dumps({'completed':True,'state':'complete'})+'\n')
    except Exception as e:
        (a.private_output/'failure-private.json').write_text(json.dumps({'error':str(e),'completed':False})+'\n')
        (a.output/'status.json').write_text(json.dumps({'completed':False,'state':'failed'})+'\n')
        raise


if __name__=='__main__':main()
