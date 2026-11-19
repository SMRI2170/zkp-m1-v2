#!/usr/bin/env python3
"""Rejoin a frozen horizontal selection to read-only original observations and fixes."""
import collections,csv,json,math,sqlite3
from pathlib import Path
from audit_android_position import association,fix_key,horizontal_distance
from build_quality_manifest import digest,number,reasons,load_selection


def same_number(a,b,tolerance=1e-6):
    x,y=number(a),number(b)
    return x is None and y is None or x is not None and y is not None and abs(x-y)<=tolerance


def row_consistency(row,raw,reference,index):
    """Mismatch is fatal: never demote/rewrite inconsistent evidence just to pass."""
    quality=association(raw,index)
    fix=raw.get('receiver_position') or {}
    d=horizontal_distance(fix['latitude'],fix['longitude'],reference['claimed_latitude'],reference['claimed_longitude']) if quality=='ELIGIBLE_TIME_POSITION' and reference.get('location_valid') else None
    checks={'quality':row.get('quality')==quality,'rssi':same_number(row.get('rssi_dbm'),raw.get('rssi_dbm')),
            'distance':same_number(row.get('claimed_horizontal_distance_m'),d)}
    for field,key in [('receiver_latitude','latitude'),('receiver_longitude','longitude'),('accuracy_m','accuracy_m')]:
        checks[field]=same_number(row.get(field),fix.get(key))
    for field,key in [('claimed_latitude','claimed_latitude'),('claimed_longitude','claimed_longitude')]:
        checks[field]=same_number(row.get(field),reference.get(key))
    if not all(checks.values()):raise ValueError('Frozen CSV disagrees with source fields: '+','.join(k for k,v in checks.items() if not v))
    return quality


def raw_gate(row,raw,quality):
    why=reasons(row)
    if raw.get('cache_stale') is not False:why.append('RAW_FRESHNESS_NOT_CONFIRMED')
    if (raw.get('receiver_position') or {}).get('mock') is not False:why.append('RAW_MOCK_OR_UNKNOWN')
    if quality!='ELIGIBLE_TIME_POSITION':why.append('RAW_ASSOCIATION_REJECTED')
    observed,delivered=number(raw.get('monotonic_time_us')),number(raw.get('delivered_elapsed_us'))
    if observed is None or delivered is None or not 0<observed<=delivered:why.append('RAW_DELIVERY_TIME_INVALID')
    return sorted(set(why))


def audit(config,raw_config,manifest,private_output):
    paths={k:Path(v) for k,v in config.items()}
    rows=list(csv.DictReader(paths['positions'].open()))
    selected=load_selection(manifest,paths['positions'],rows)
    legacy_indices={i for i,r in enumerate(rows) if not reasons(r)}
    if len(selected)!=len(legacy_indices):raise ValueError('Frozen selection mismatch')
    identity=json.loads(Path(raw_config['identity_file']).read_text())['claimed_id']
    source_audit=json.loads(paths['source_inputs'].read_text())
    expected_hashes={x['source']:x['sha256'] for x in source_audit}
    sources={s['node']:s for s in raw_config['sources']}
    if len(sources)!=len(raw_config['sources']):raise ValueError('Duplicate source aliases')
    if set(sources)!={*json.loads(paths['position_summary'].read_text())['nodes']}:raise ValueError('Source aliases changed')
    all_paths=[*paths.values(),Path(manifest),Path(raw_config['identity_file'])]
    for s in sources.values():all_paths.extend([Path(s['database']),Path(s['reference_jsonl'])])
    fingerprints={str(p):digest(p) for p in all_paths}
    mask=[];nodes={};private_sources=[];checked_indices=set()
    for node,source in sources.items():
        dbpath=Path(source['database'])
        if digest(dbpath)!=expected_hashes[node]:raise ValueError('Source DB does not match original audit')
        references={}
        with Path(source['reference_jsonl']).open() as f:
            for line in f:
                x=json.loads(line);ref=x['reference']
                if ref.get('reference_decode_ok') and bytes.fromhex(ref.get('id_hex','')).rstrip(b'\0').decode(errors='replace')==identity:
                    key=x['capture']['odid_payload_hex']
                    if key in references and references[key]!=ref:raise ValueError('Conflicting reference decoding')
                    references[key]=ref
        with sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Original DB integrity failed')
            fixes=collections.defaultdict(list)
            for (text,) in db.execute('SELECT raw_json FROM receiver_fixes'):
                f=json.loads(text);fixes[fix_key(f.get('boot_scope'),f)].append(f)
            lookup=collections.defaultdict(list);target_count=0
            for row_id,text in db.execute('SELECT id,raw_json FROM observations'):
                raw=json.loads(text);ref=references.get(raw.get('odid_payload_hex'))
                if ref is not None:
                    target_count+=1;lookup[(str(raw.get('boot_scope') or ''),number(raw.get('monotonic_time_us')))].append((row_id,raw,ref))
            group=[(i,r) for i,r in enumerate(rows) if r['node']==node]
            if len(group)!=target_count:raise ValueError('Reference-decoded target denominator changed')
            counters=collections.Counter();details=[];payloads=set();height_types=collections.Counter()
            for i,row in group:
                matches=lookup.get((str(row.get('boot_scope') or ''),number(row.get('observed_us'))),[])
                if len(matches)!=1:raise ValueError('Observation join missing or ambiguous')
                row_id,raw,ref=matches[0];quality=row_consistency(row,raw,ref,fixes);why=raw_gate(row,raw,quality)
                legacy=i in legacy_indices;keep=not why
                if keep!=legacy:raise ValueError('Raw policy changes frozen selection; investigate before downstream evaluation')
                checked_indices.add(i);counters.update(why[:1]);height_types[str(ref.get('height_type'))]+=1
                detail=dict(row_index=i,node=node,selected=keep,reasons=why,source_row_id=row_id,
                    raw_association=quality,cache_stale=raw.get('cache_stale'),mock=(raw.get('receiver_position') or {}).get('mock'),
                    fix_delta_s=number(row.get('fix_delta_s')),absolute_power_calibrated=raw.get('absolute_power_calibrated'),
                    delivered_minus_observed_s=(raw['delivered_elapsed_us']-raw['monotonic_time_us'])/1e6,
                    content_digest=raw.get('vendor_content_digest'))
                details.append(detail);mask.append(detail)
                if keep:payloads.add(raw.get('odid_payload_hex'))
            nodes[node]=dict(target_rows=len(group),selected_rows=sum(x['selected'] for x in details),held_rows=sum(not x['selected'] for x in details),
                exclusive_hold_reasons=dict(counters),raw_fresh_rows=sum(x['cache_stale'] is False for x in details),
                raw_nonmock_rows=sum(x['mock'] is False for x in details),source_joined_rows=len(details),
                calibrated_power_rows=sum(x['absolute_power_calibrated'] is True for x in details),selected_distinct_contents=len(payloads),height_type_counts=dict(height_types))
            private_sources.append(dict(node=node,path=str(dbpath),sha256=digest(dbpath)))
    if checked_indices!=set(range(len(rows))):raise ValueError('CSV contains unaccounted aliases/rows')
    if any(digest(Path(p))!=h for p,h in fingerprints.items()):raise ValueError('Source changed during audit')
    clock=json.loads(paths['clock_summary'].read_text())
    anchors=clock['independent_calendar_anchors_verified']
    if anchors!=0:raise ValueError('New clock evidence requires explicit review; no automatic promotion')
    gates=[dict(capability='within_phone_horizontal_proxy',status='EXECUTABLE_CONDITIONAL',reason='same-boot association and exploratory accuracy gate only'),
        dict(capability='cross_device_calendar_alignment',status='NOT_EVALUABLE',reason='no independent calendar anchors in supplied evidence'),
        dict(capability='physical_3d_distance',status='NOT_EVALUABLE',reason='no independent vertical-reference ledger'),
        dict(capability='same_physical_transmission_drss',status='NOT_EVALUABLE',reason='content equality is not verified physical packet identity'),
        dict(capability='physical_position_fpr_tpr',status='NOT_EVALUABLE',reason='no independently labelled true positions or attacks'),
        dict(capability='packet_delivery_ratio',status='NOT_EVALUABLE',reason='transmitted-packet denominator unavailable'),
        dict(capability='independent_run_uncertainty',status='NOT_EVALUABLE',reason='independent flight/run labels not established')]
    summary=dict(stage='issue89',status='COMPLETED_CURRENT_FROZEN_DATA_SCOPE',target_rows=len(rows),selected_rows=len(selected),nodes=nodes,gates=gates,
        independent_calendar_anchors=anchors,source_db_hashes_verified=len(private_sources),input_unchanged=True,
        raw_gate_preserves_frozen_selection=True,scope='Nov16 preserved target dataset only; not later lab-test records',physical_truth_verified=False)
    (private_output/'row-gates-private.json').write_text(json.dumps(mask,indent=2)+'\n')
    (private_output/'source-hashes-private.json').write_text(json.dumps(fingerprints,indent=2)+'\n')
    return summary,selected,fingerprints
