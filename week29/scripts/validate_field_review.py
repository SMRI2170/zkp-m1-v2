#!/usr/bin/env python3
"""Compare plotted Matplotlib artists with independently loaded public aggregates."""
import argparse,csv,json,math
from pathlib import Path

def validate(root):
    q=json.loads((root/'quality-gates.json').read_text());m=json.loads((root/'model-diagnosis.json').read_text())
    rows=list(csv.DictReader((root/'paired-transitions.csv').open()));sensitivity=list(csv.DictReader((root/'claim-dependent-selection.csv').open()))
    if sum(x['target_rows'] for x in q['nodes'].values())!=q['target_rows'] or sum(x['selected_rows'] for x in q['nodes'].values())!=q['selected_rows']:raise ValueError('Quality denominator mismatch')
    if sum(m['counts'][k] for k in ('train','calibration','evaluation','purged'))!=m['counts']['eligible']:raise ValueError('Split denominator mismatch')
    if m['counts']['eligible']!=q['selected_rows']:raise ValueError('Selection changed between stages')
    for x in rows:
        if sum(int(x[k]) for k in ('quiet_to_quiet','quiet_to_alarm','alarm_to_quiet','alarm_to_alarm'))!=int(x['evaluated_rows']):raise ValueError('Transition denominator mismatch')
        if int(x['evaluated_rows'])+int(x['held_rows'])!=m['counts']['evaluation']:raise ValueError('Held denominator mismatch')
    focus=[next(x for x in rows if x['direction']=='away' and int(x['shift_m'])==50 and x['mode']==mode) for mode in ('claim_only','model_matched_unbounded')]
    syn=json.loads((root/'synthetic-explanation.json').read_text())
    expected=dict(quality_selected=[x['selected_rows'] for x in q['nodes'].values()],quality_held=[x['held_rows'] for x in q['nodes'].values()],
        partition_alarm_percent=[x['alarm_count']/x['n']*100 for x in m['partitions']],block_alarm_percent=[x['baseline_alarm_count']/x['n']*100 for x in m['descriptive_blocks']],
        paired_counts_50m=[int(x[k]) for k in ('alarm_to_alarm','quiet_to_alarm','alarm_to_quiet','quiet_to_quiet') for x in focus],
        synthetic_scores=[syn[k] for k in ('baseline_score','claim_only_score','compensated_score')],
        selection_counts=[q['selected_rows']]+[sum(int(x['after_claim_change_selected']) for x in sensitivity if int(x['synthetic_away_shift_m'])==d) for d in (20,50,100)])
    drawn={x['name']:x['drawn'] for x in json.loads((root/'figure-series.json').read_text())}
    if set(drawn)!=set(expected):raise ValueError('Missing figure series')
    for name,values in expected.items():
        if len(drawn[name])!=len(values) or any(not math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-10) for a,b in zip(drawn[name],values)):raise ValueError('Figure differs from source aggregates: '+name)
    for file in ('01_quality_and_capabilities.png','02_frozen_model_failure.png','03_paired_alarms_and_synthetic_example.png','04_claim_dependent_gate.png'):
        if (root/file).read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Missing/invalid figure')
    return dict(status='passed',figure_series_checked=len(expected),figures_checked=4,paired_conditions_checked=len(rows),counts_consistent=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);a=p.parse_args();print(json.dumps(validate(a.results)))
