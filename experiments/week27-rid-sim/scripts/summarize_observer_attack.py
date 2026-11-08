"""Post-evaluation strata and paired B→C comparisons; no RF/threshold changes."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

from evaluation import metrics
from normalize import write_csv
from run_observer_attack import bootstrap
from setup import REPO


def read_csv(path):
    with path.open() as stream:return list(csv.DictReader(stream))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--results',type=Path,required=True)
    a=p.parse_args();summary=json.loads((a.results/'summary.json').read_text())
    if summary['status']!='PR5_EVALUATION_PASSED':raise ValueError('Do not summarize an incomplete run as complete')
    analysis=a.raw_dir/'analyses'/hashlib.sha256(str(a.results.resolve()).encode()).hexdigest()[:16]
    if not analysis.exists():raise ValueError('Matching private analysis namespace not found')
    cfg=json.loads((a.results/'configuration.json').read_text());repeats=cfg['bootstrap_repeats']
    rows=read_csv(a.results/'per-seed-metrics.csv');lookup={tuple(r[k] for k in ['phy','link','seed','attack_case','offset_m','bound_db','method']):r for r in rows}
    compared=defaultdict(list)
    for r in rows:
        if r['phy']!='default' or r['attack_case']!='schedule_aware':continue
        key=(r['phy'],r['link'],r['seed'],'reference_rx0',r['offset_m'],r['bound_db'],r['method'])
        before=lookup[key]
        group=tuple(r[k] for k in ['link','offset_m','bound_db','method'])
        compared[group].append((before,r))
    differences=[];shared_cohorts=[]
    for group,pairs in compared.items():
        result=dict(zip(['link','offset_m','bound_db','method'],group))
        for metric in ['alarm_scored','alarm_all_tx','und_rate','received_rate']:
            values=[float(after[metric])-float(before[metric]) for before,after in pairs if before[metric] and after[metric]]
            result.update({f'C_minus_B_{metric}_{k}':v for k,v in bootstrap(values,repeats).items()})
        differences.append(result)
    write_csv(a.results/'B-to-C-paired-difference.csv',differences)
    for r in rows:
        if r['phy']!='default' or r['attack_case']!='schedule_aware':continue
        prefix=f'default-eval-{r["link"]}-{r["seed"]}-'
        ending=f'-offset{r["offset_m"]}-bound{r["bound_db"]}-scores.json'
        before=json.loads((analysis/(prefix+'reference_rx0'+ending)).read_text())[r['method']]
        after=json.loads((analysis/(prefix+'schedule_aware'+ending)).read_text())[r['method']]
        shared=[i for i,(x,y) in enumerate(zip(before['decisions'],after['decisions'])) if x!='UNDETERMINED' and y!='UNDETERMINED']
        shared_cohorts.append(dict(seed=int(r['seed']),link=r['link'],offset_m=int(r['offset_m']),bound_db=int(r['bound_db']),method=r['method'],
                                   shared_scored_count=len(shared),shared_B_flags=sum(before['decisions'][i]=='FLAG' for i in shared),shared_C_flags=sum(after['decisions'][i]=='FLAG' for i in shared),
                                   B_received=sum(before['received']),C_received=sum(after['received']),shared_received=sum(x and y for x,y in zip(before['received'],after['received'])),
                                   scope='Paired schedule indices across independent counterfactual RF runs, not one shared physical packet across runs'))
    write_csv(a.results/'B-to-C-shared-cohort.csv',shared_cohorts)
    factors=read_csv(a.results/'factor-audit.csv');groups=defaultdict(list)
    for r in factors:groups[tuple(r[k] for k in ['phy','link','attack_case','offset_m','bound_db'])].append(r)
    aggregated=[]
    for group,values in groups.items():
        record=dict(zip(['phy','link','attack_case','offset_m','bound_db'],group))
        for key in ['attack_bound_clamped','phy_clamped','selected_received','target_mismatches','single_flags_clipped','single_flags_unclipped','kf_received_startup_und']:
            samples=[int(r[key])/int(r['tx_count']) for r in values]
            record.update({f'{key}_rate_{k}':v for k,v in bootstrap(samples,repeats).items()})
        for key in ['rssi_response_max_error_db','mean_abs_oracle_delta_mismatch_db']:
            available=[float(r[key]) for r in values if r[key]!='']
            record[f'{key}_max']=max(available) if available else None
        aggregated.append(record)
    write_csv(a.results/'factor-aggregate.csv',aggregated)
    thresholds=json.loads((a.results/'thresholds.json').read_text())
    power_bins=[(-80,-10),(-10,-5),(-5,0),(0,10),(10,23),(23,41)]
    stratified=[];decomposition=[];ledger_hashes=[];target_audits=[];clipping_strata=[]
    receipts=[json.loads(line) for line in (a.results/'case-receipts.jsonl').read_text().splitlines()]
    for receipt in receipts:
        rid=receipt['run_id']
        if '-eval-' not in rid:continue
        spec=receipt['spec'];phy=rid.split('-eval-')[0]
        link=next(v for v in cfg['links'] if f'-{v}-' in rid)
        case='normal' if rid.endswith('-normal') else spec['attack_case'];bound=0 if case=='normal' else spec['attack_bound_db']
        ledger_path=a.raw_dir/rid/'attack-truth-ledger.json'
        digest=hashlib.sha256(ledger_path.read_bytes()).hexdigest()
        if digest!=receipt['attack_ledger_sha256']:raise ValueError('Private truth ledger changed')
        ledger_hashes.append(digest);ledger=json.loads(ledger_path.read_text())
        targets={str(node):sum(r['target_rx_id']==node for r in ledger) for node in [-1,0,2,3,4,5]}
        if spec['attack_case']=='schedule_aware':
            if any(r['target_rx_id']!=spec['defender_schedule'][i%len(spec['defender_schedule'])] for i,r in enumerate(ledger)):raise ValueError('Oracle target schedule mismatch')
        target_audits.append(dict(run_id=rid,attack_case=case,tx_count=len(ledger),**{f'target_{k}_count':v for k,v in targets.items()}))
        scored=json.loads((analysis/f'{rid}-scores.json').read_text())
        for method,data in scored.items():
            key=(phy,link,str(spec['seed']),case,str(spec['offset_x_m']),str(bound),method)
            source=lookup[key]
            checked=metrics(data['decisions'],data['received'])
            if any(int(source[k])!=checked[k] for k in ['tx_count','received_count','scored_count','flag_count','below_count','und_count']):raise ValueError('Saved private decisions disagree with public counts')
            for low,high in power_bins:
                selected=[i for i,r in enumerate(ledger) if low<=r['effective_phy_tx_dbm']<high]
                if not selected:continue
                stratified.append(dict(phy=phy,link=link,seed=spec['seed'],attack_case=case,offset_m=spec['offset_x_m'],bound_db=bound,method=method,
                                       power_bin_dbm=f'[{low},{high})',stratum_provenance='evaluation truth only, not detector input',
                                       **metrics([data['decisions'][i] for i in selected],[data['received'][i] for i in selected])))
            if method in ['SingleResidual','KF_NIS'] and case!='normal':
                for attack_clip,phy_clip in [(False,False),(True,False),(False,True),(True,True)]:
                    selected=[i for i,r in enumerate(ledger) if r['clamped_by_attack_bound']==attack_clip and r['clamped_by_phy_limit']==phy_clip]
                    if selected:clipping_strata.append(dict(phy=phy,link=link,seed=spec['seed'],attack_case=case,offset_m=spec['offset_x_m'],bound_db=bound,method=method,
                                                           constraint_stratum=f'attack={attack_clip},phy={phy_clip}',
                                                           **metrics([data['decisions'][i] for i in selected],[data['received'][i] for i in selected])))
        private=analysis/f'{rid}-decomposition.json'
        if private.exists():
            values=json.loads(private.read_text())
            errors=[abs(r['observed_residual_db']-r['ideal_unclipped_residual_db']-r['total_clipping_error_db']) for r in values]
            if errors and max(errors)>1e-6:raise ValueError('RSS residual decomposition did not reconcile')
            ideal=[r['ideal_unclipped_residual_db'] for r in values]
            import statistics
            centered=[abs(x-statistics.median(ideal)) for x in ideal] if ideal else []
            decomposition.append(dict(phy=phy,link=link,seed=spec['seed'],attack_case=case,offset_m=spec['offset_x_m'],bound_db=bound,
                                      paired_received=len(values),max_decomposition_identity_error_db=max(errors) if errors else None,
                                      ideal_unclipped_centered_residual_mean_db=statistics.mean(centered) if centered else None,
                                      scope='Algebraic paired-received diagnostic, not another RF run or counterfactual detection/delivery estimate'))
    write_csv(a.results/'power-stratified-metrics.csv',stratified);write_csv(a.results/'residual-decomposition.csv',decomposition)
    write_csv(a.results/'clipping-stratified-metrics.csv',clipping_strata)
    for name,records,stratum_field in [('power',stratified,'power_bin_dbm'),('clipping',clipping_strata,'constraint_stratum')]:
        strata=defaultdict(list);keys=['phy','link','attack_case','offset_m','bound_db','method',stratum_field]
        for r in records:strata[tuple(r[k] for k in keys)].append(r)
        output=[]
        for key,values in strata.items():
            record=dict(zip(keys,key));record['seeds_with_tx_in_stratum']=len(values)
            for metric in ['alarm_scored','alarm_all_tx','und_rate','received_rate','eligible_rate']:
                record.update({f'{metric}_{k}':v for k,v in bootstrap([r[metric] for r in values],repeats).items()})
            for metric in ['tx_count','received_count','scored_count','flag_count','und_count']:
                record[metric]=sum(r[metric] for r in values)
            output.append(record)
        write_csv(a.results/f'{name}-stratified-aggregate.csv',output)
    write_csv(a.results/'attack-target-audit.csv',target_audits)
    receipt=dict(status='PASSED',source_sha256=hashlib.sha256((a.results/'per-seed-metrics.csv').read_bytes()).hexdigest(),
                 verified_private_ledgers=len(ledger_hashes),private_ledger_catalog_sha256=hashlib.sha256(''.join(sorted(ledger_hashes)).encode()).hexdigest(),
                 paired_comparisons=len(differences),power_strata_rows=len(stratified),decomposition_rows=len(decomposition),
                 raw_rf_rerun=False,thresholds_changed=False,
                 scope='Power strata and model/clipping decomposition use private truth AFTER scoring only. CI resamples independent seeds, not packets.')
    (a.results/'stratification-audit.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
