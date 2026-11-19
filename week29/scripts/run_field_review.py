#!/usr/bin/env python3
"""Finite ordered #89 -> #96 -> #93 review, with explicit non-evaluable gates."""
import argparse,csv,json,os
from pathlib import Path
from audit_frozen_field_rows import audit
from diagnose_frozen_proxy import diagnose
from build_quality_manifest import private_path,digest


def write_csv(path,rows):
    if not rows:return
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence-config',type=Path,required=True);p.add_argument('--raw-config',type=Path,required=True)
    p.add_argument('--selection-manifest',type=Path,required=True);p.add_argument('--baseline-summary',type=Path,required=True);p.add_argument('--private-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    private=private_path(a.private_output)
    if private.exists() or a.output.exists():raise ValueError('Fresh output directories required; no overwrite')
    for path in (a.evidence_config,a.raw_config,a.selection_manifest):private_path(path,existing=True)
    private.mkdir(parents=True,mode=0o700);a.output.mkdir(parents=True)
    receipt=dict(status='running',stages=[],code_sha256={name:digest(Path(__file__).with_name(name)) for name in ('run_field_review.py','audit_frozen_field_rows.py','diagnose_frozen_proxy.py','render_field_review.py','evaluate_claim_attacks.py','build_quality_manifest.py','audit_android_position.py')})
    def save():(a.output/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
    save()
    try:
        evidence=json.loads(a.evidence_config.read_text());raw=json.loads(a.raw_config.read_text())
        quality,selected,fingerprints=audit(evidence,raw,a.selection_manifest,private)
        packet_path=Path(__file__).resolve().parents[1]/'results/issue95-matches-a/summary.json'
        packet=json.loads(packet_path.read_text())
        if packet['confirmed_physical_packets']!=0 or packet['clock_alignment_verified'] is not False:raise ValueError('New packet evidence requires explicit review')
        (a.output/'packet-status.json').write_text(json.dumps(dict(source_summary_sha256=digest(packet_path),confirmed_physical_packets=0,cross_device_clock_verified=False,row_level_mapping='NOT_EVALUABLE_no_confirmed_join',pair_content_candidates=packet['pair_results'],cancellation='NOT_EVALUABLE'),indent=2)+'\n')
        (a.output/'quality-gates.json').write_text(json.dumps(quality,indent=2)+'\n');write_csv(a.output/'capabilities.csv',quality['gates'])
        receipt['stages'].append(dict(issue=89,status='completed_current_dataset',selected_rows=quality['selected_rows']));save();print('#89 raw evidence audit completed',flush=True)
        rows=list(csv.DictReader(Path(evidence['positions']).open()))
        model,paired,sensitivity,events=diagnose(selected,rows,json.loads(a.baseline_summary.read_text()),private)
        (a.output/'model-diagnosis.json').write_text(json.dumps(model,indent=2)+'\n');write_csv(a.output/'paired-transitions.csv',paired);write_csv(a.output/'claim-dependent-selection.csv',sensitivity);write_csv(a.output/'descriptive-blocks.csv',model['descriptive_blocks'])
        receipt['stages'].append(dict(issue=96,status='completed_failure_diagnosis',detector_adopted=False));save();print('#96 frozen-model diagnosis completed',flush=True)
        from render_field_review import render
        render(quality,model,paired,sensitivity,events,a.output,private)
        receipt['stages'].append(dict(issue=93,status='completed_visuals',real_events_public=False));save();print('#93 figures and private event viewer generated',flush=True)
        if any(digest(Path(x))!=h for x,h in fingerprints.items()):raise ValueError('Input changed during downstream work')
        receipt.update(status='completed',input_unchanged=True,real_fpr_tpr='NOT_EVALUABLE',independent_truth=False);save()
    except Exception as exc:
        receipt.update(status='failed',failure_type=type(exc).__name__);save();raise

if __name__=='__main__':main()
