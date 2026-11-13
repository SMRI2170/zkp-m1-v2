#!/usr/bin/env python3
"""Aggregate private RF matrix captures; publish no identifiers/coordinates/raw rows."""
import argparse
from collections import defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import statistics


def quantile(values,p):
    if not values:return None
    x=sorted(values);a=(len(x)-1)*p;i=int(a)
    return x[i]+(x[min(i+1,len(x)-1)]-x[i])*(a-i)


def summarize_samples(rows,receipt,capture):
    matched=[r for r in rows if r.get('vendor_content_digest')==receipt['vendor_content_sha256']
             and r.get('odid_counter')==receipt['counter']]
    start=capture['started_boottime_s'];duration=capture['elapsed_s'];end=start+duration
    samples={}
    for r in matched:
        stamp=r.get('monotonic_time_us')
        if (stamp is None or r.get('rssi_dbm') is None or r.get('cache_stale') or r.get('rid_parse_status')!='decoded'):
            continue
        t=stamp/1e6
        if not start<=t<=end:continue
        samples[(r.get('bssid'),r.get('frequency_mhz'),t)]=r
    by_source=defaultdict(list)
    for (bssid,freq,t),r in samples.items():by_source[(bssid,freq)].append(t)
    intervals=[];silences=[]
    for stamps in by_source.values():
        stamps=sorted(stamps)
        gaps=[b-a for a,b in zip(stamps,stamps[1:])]
        intervals+=gaps;silences.extend([stamps[0]-start,*gaps,end-stamps[-1]])
    rssis=[r['rssi_dbm'] for r in samples.values()]
    bins=[]
    for i in range(int(duration//5)):
        values=[r['rssi_dbm'] for (_,_,t),r in samples.items() if i*5<=t-start<(i+1)*5]
        bins.append(dict(bin_start_s=i*5,count=len(values),rssi_median_dbm=statistics.median(values) if values else None))
    stats=dict(saved_candidate_records=len(rows),matching_records=len(matched),other_content_records=len(rows)-len(matched),
               matching_missing_rssi=sum(r.get('rssi_dbm') is None for r in matched),current_rssi_updates=len(samples),
               interval_count=len(intervals),interval_median_s=statistics.median(intervals) if intervals else None,
               interval_p95_s=quantile(intervals,.95),interval_max_s=max(intervals) if intervals else None,
               max_observed_silence_s=max(silences) if silences else duration,
               rssi_median_dbm=statistics.median(rssis) if rssis else None)
    return stats,bins


def number(v):
    try:
        n=int(v)
        return n if 0<=n<2**63 else None
    except (ValueError,TypeError):return None


def write_csv(path,rows,fields=None):
    with path.open('x',newline='') as f:
        fields=fields or (list(rows[0]) if rows else ['status'])
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)


def analyze(matrix,snapshots,output):
    output.mkdir(parents=True,exist_ok=False)
    trials=[json.loads(p.read_text()) for p in sorted(matrix.glob('trial-*.json'))]
    plan=json.loads((matrix/'plan.json').read_text())
    records=[];resource_rows=[];timebins=[];errors=[]
    for t in trials:
        condition=t['condition'];receipt=t.get('tx_receipt_final')
        valid=(t['status']=='COMPLETED' and not t.get('cleanup_errors') and receipt and receipt.get('temporary_ap_removed') is True)
        for node,detail in t['receivers'].items():
            capture=detail.get('capture') or {}
            run_id=detail['run_id']
            if not re.fullmatch(r'[0-9TZ.]+',run_id):raise ValueError('invalid capture run id')
            path=snapshots/node/'captures'/('observer-'+node)/run_id/'observations.jsonl'
            row=dict(trial=t['index'],kind=condition['kind'],repetition=condition['repetition'],
                     transmitter=condition['transmitter'],receiver=node,scope=condition['scope'],
                     spacing_s=condition['spacing_s'],transmitter_frequency_mhz=receipt.get('frequency_mhz') if receipt else None,
                     requested_duration_s=condition['duration_s'],
                     elapsed_s=capture.get('elapsed_s'),valid_completed_run=bool(valid),
                     exit_code=detail['exit_code'],stopped_reason=capture.get('stopped_reason'))
            try:
                raw=[json.loads(l) for l in path.read_text().splitlines()]
                stats,bins=summarize_samples(raw,receipt,capture)
                row.update(stats)
                if condition['kind']=='sustain':
                    timebins += [dict(trial=t['index'],transmitter=condition['transmitter'],receiver=node,**b) for b in bins]
            except (OSError,ValueError,KeyError,TypeError) as e:
                errors.append(dict(trial=t['index'],receiver=node,error_type=type(e).__name__))
                row['valid_completed_run']=False
                row.update({k:None for k in ['saved_candidate_records','matching_records','other_content_records',
                           'matching_missing_rssi','current_rssi_updates','interval_count','interval_median_s',
                           'interval_p95_s','interval_max_s','max_observed_silence_s','rssi_median_dbm']})
            counts=capture.get('counts',{})
            row.update(scan_requests=counts.get('scan_requests'),scan_accepted=counts.get('scan_accepted'),scan_failed=counts.get('scan_failed'),
                       child_peak_rss_kib=detail.get('child_peak_rss_kib'))
            resources=[s for s in t.get('resources',[]) if s['node']==node]
            mem=[number(s.get('MemoryPeak')) for s in resources];mem=[m for m in mem if m is not None]
            current=[number(s.get('MemoryCurrent')) for s in resources];current=[m for m in current if m is not None]
            avail=[s['mem_available_kib'] for s in resources]
            cpu=[number(s.get('CPUUsageNSec')) for s in resources];cpu=[x for x in cpu if x is not None]
            row.update(cgroup_memory_peak_mib=max(mem)/1024**2 if mem else None,
                       cgroup_memory_current_max_mib=max(current)/1024**2 if current else None,
                       mem_available_min_mib=min(avail)/1024 if avail else None,
                       unit_cpu_s=max(cpu)/1e9 if cpu else None,
                       ssh_status_max_s=max((s['ssh_elapsed_s'] for s in resources),default=None))
            records.append(row)
        for s in t.get('resources',[]):
            resource_rows.append(dict(trial=t['index'],receiver=s['node'],
                relative_s=(datetime.fromisoformat(s['sampled_at_utc'])-datetime.fromisoformat(t['started_at_utc'])).total_seconds(),
                memory_current_bytes=number(s.get('MemoryCurrent')),memory_peak_bytes=number(s.get('MemoryPeak')),
                cpu_usage_ns=number(s.get('CPUUsageNSec')),mem_available_kib=s['mem_available_kib'],
                ssh_elapsed_s=s['ssh_elapsed_s'],state=s['ActiveState']))
    groups=defaultdict(list)
    for r in records:
        if r['kind']=='matrix':groups[(r['transmitter'],r['receiver'],r['scope'],r['spacing_s'])].append(r)
    aggregates=[]
    for (tx,rx,scope,spacing),rs in sorted(groups.items()):
        good=[r for r in rs if r['valid_completed_run'] and r['interval_median_s'] is not None]
        med=[r['interval_median_s'] for r in good]
        aggregates.append(dict(transmitter=tx,receiver=rx,scope=scope,spacing_s=spacing,attempted_runs=len(rs),
            usable_runs=len(good),median_of_run_medians_s=statistics.median(med) if med else None,
            min_run_median_s=min(med) if med else None,max_run_median_s=max(med) if med else None,
            matching_records=sum(r['matching_records'] or 0 for r in good),
            scan_failed=sum(r['scan_failed'] or 0 for r in rs)))
    write_csv(output/'runs.csv',records);write_csv(output/'groups.csv',aggregates,fields=['transmitter','receiver','scope','spacing_s','attempted_runs','usable_runs',
                    'median_of_run_medians_s','min_run_median_s','max_run_median_s','matching_records','scan_failed'])
    write_csv(output/'resources.csv',resource_rows);write_csv(output/'sustain-rssi-bins.csv',timebins)
    memory=[]
    for node in 'abc':
        rs=[r for r in records if r['receiver']==node and r['valid_completed_run']]
        child=[r['child_peak_rss_kib']/1024 for r in rs if r['child_peak_rss_kib'] is not None]
        peak=[r['cgroup_memory_peak_mib'] for r in rs if r['cgroup_memory_peak_mib'] is not None]
        current=[r['cgroup_memory_current_max_mib'] for r in rs if r['cgroup_memory_current_max_mib'] is not None]
        avail=[r['mem_available_min_mib'] for r in rs if r['mem_available_min_mib'] is not None]
        ssh=[r['ssh_status_max_s'] for r in rs if r['ssh_status_max_s'] is not None]
        memory.append(dict(receiver=node,runs=len(rs),child_peak_rss_mean_mib=statistics.mean(child) if child else None,
                           child_peak_rss_sd_mib=statistics.stdev(child) if len(child)>1 else None,
                           child_peak_rss_max_mib=max(child) if child else None,cgroup_peak_max_mib=max(peak) if peak else None,
                           cgroup_current_observed_max_mib=max(current) if current else None,
                           host_mem_available_min_mib=min(avail) if avail else None,ssh_status_max_s=max(ssh) if ssh else None))
    write_csv(output/'memory-statistics.csv',memory)
    summary=dict(planned_trials=len(plan),recorded_trials=len(trials),
                 completed_trials=sum(t['status']=='COMPLETED' and not t.get('cleanup_errors') for t in trials),
                 expected_receiver_runs=len(plan)*2,
                 receiver_runs=len(records),completed_receiver_runs=sum(r['valid_completed_run'] for r in records),
                 usable_receiver_runs=sum(r['valid_completed_run'] and r['interval_median_s'] is not None for r in records),
                 errors=errors,total_matching_records=sum(r['matching_records'] or 0 for r in records),
                 total_missing_rssi=sum(r['matching_missing_rssi'] or 0 for r in records),
                 source='controlled_Pi_RF_synthetic_RID_claims',physical_packet_match='unconfirmed',
                 independent_flights=False,groups=aggregates,runs=records,memory_statistics=memory,
                 boundaries=['cache updates not physical packets','no M350 test','no absolute RSSI calibration',
                             'no range/propagation/position-falsification evaluation','memory samples are cgroup/RSS not PSS'])
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def plot(results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    d=json.loads((results/'summary.json').read_text())
    fig,axes=plt.subplots(1,2,figsize=(10,4),sharey=True)
    for ax,scope in zip(axes,['target','all']):
        for tx,rx in [('a','b'),('a','c'),('b','a'),('b','c')]:
            rows=sorted([r for r in d['groups'] if r['scope']==scope and r['transmitter']==tx and r['receiver']==rx and r['usable_runs']],key=lambda r:r['spacing_s'])
            if not rows:continue
            y=[r['median_of_run_medians_s'] for r in rows]
            ax.errorbar([r['spacing_s'] for r in rows],y,
                        yerr=[[v-r['min_run_median_s'] for v,r in zip(y,rows)],
                              [r['max_run_median_s']-v for v,r in zip(y,rows)]],marker='o',capsize=4,label=f'{tx.upper()} -> {rx.upper()}')
        ax.set(title='Confirmed single frequency' if scope=='target' else 'All supported channels',
               xlabel='Requested scan spacing (s)',xticks=[.25,1])
        ax.grid(alpha=.2)
        if ax.lines:ax.legend(fontsize=8)
        ax.set_ylim(bottom=0)
    upper=max((r['max_run_median_s'] for r in d['groups'] if r['max_run_median_s'] is not None),default=1)*1.12
    for ax in axes:ax.set_ylim(0,upper)
    axes[0].set_ylabel('RSSI cache update interval (s)')
    fig.suptitle('Three attempted runs per setting; bars show range of usable run medians')
    fig.tight_layout()
    if d['groups']:save(fig,results/'repeated-update-intervals')
    plt.close(fig)
    fig,axes=plt.subplots(3,1,figsize=(9,7),sharex=True)
    with (results/'sustain-rssi-bins.csv').open() as f:bins=list(csv.DictReader(f))
    for ax,rx in zip(axes,'abc'):
        for tx in 'ab':
            rows=[r for r in bins if r['receiver']==rx and r['transmitter']==tx]
            if rows:ax.plot([float(r['bin_start_s'])+2.5 for r in rows],
                            [float(r['rssi_median_dbm']) if r['rssi_median_dbm'] else float('nan') for r in rows],
                            'o-',markersize=3,label=f'{tx.upper()} -> {rx.upper()}')
        ax.set_ylabel('RSSI (dBm)');ax.set_title('Receiver '+rx.upper());ax.grid(alpha=.2);ax.legend(fontsize=8)
    axes[-1].set_xlabel('Seconds from receiver start (5-second bin medians)')
    scope_label=', '.join(sorted({r['scope'] for r in d['runs'] if r['kind']=='sustain'}))
    fig.suptitle(f'90-second runs ({scope_label}): controlled Pi Beacon, fixed synthetic RID claim')
    fig.tight_layout();save(fig,results/'sustain-rssi');plt.close(fig)


def save(fig,base):
    for ext in ['png','svg']:
        p=base.with_suffix('.'+ext);fig.savefig(p,dpi=160)
        if ext=='svg':p.write_text('\n'.join(l.rstrip() for l in p.read_text().splitlines())+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matrix',required=True,type=Path);p.add_argument('--snapshots',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path);p.add_argument('--plot',action='store_true')
    args=p.parse_args();s=analyze(args.matrix,args.snapshots,args.output_dir)
    if args.plot:plot(args.output_dir)
    print(json.dumps({k:s[k] for k in ['planned_trials','recorded_trials','completed_trials','receiver_runs','usable_receiver_runs','total_matching_records','total_missing_rssi']}))


if __name__=='__main__':main()
