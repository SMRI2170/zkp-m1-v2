"""Plot successful native Pi runs; keep missing measurements explicit."""
import hashlib
import json
from pathlib import Path
import statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
RUNS = [('arkworks Groth16', 'additional-arkworks-v1'),
        ('Halo2 KZG / BN254', 'additional-halo2-kzg-v1'),
        ('Spartan SNARK', 'additional-spartan-v1'),
        ('Bulletproofs R1CS', 'additional-bulletproofs-v2'),
        ('Plonky3 HidingFRI', 'additional-plonky3-v1')]

def collect():
    records = []
    for name, run in RUNS:
        directory = ROOT / 'week24/logs/pi-euclidean-additional' / run
        logs = [json.loads(s) for s in (directory/'benchmark.jsonl').read_text().splitlines()]
        samples = [r for r in logs if r['phase'] == 'sample']
        mem = json.loads((directory/'memory-summary.json').read_text())
        resource = json.loads((directory/'resource.json').read_text())
        assert len(samples) == 7 and resource['exit_code'] == 0
        flow = [s['prove_ms']+s['verify_ms']+s.get('witness_ms', 0) for s in samples]
        records.append(dict(framework=name, run=run, measured_samples=7,
            flow_mean_ms=statistics.mean(flow), flow_population_sd_ms=statistics.pstdev(flow),
            flow_min_ms=min(flow), flow_max_ms=max(flow),
            flow_scope='sum of logged witness (if separate), prove and verify; setup/negative tests excluded',
            separate_witness_measured='witness_ms' in samples[0],
            memory_time_weighted_mean_bytes=mem['time_weighted']['mean_bytes'],
            memory_kernel_peak_bytes=resource['cgroup_peak_bytes'],
            proof_mean_bytes=statistics.mean(s['proof_bytes'] for s in samples),
            proof_min_bytes=min(s['proof_bytes'] for s in samples),
            proof_max_bytes=max(s['proof_bytes'] for s in samples),
            setup_once_ms=next(s['setup_ms'] for s in logs if s['phase']=='keys'),
            source_log_sha256={f: hashlib.sha256((directory/f).read_bytes()).hexdigest()
                               for f in ['benchmark.jsonl', 'resource.json', 'memory.jsonl', 'memory-summary.json']}))
    return records

def main():
    records = collect()
    missing = {'Plonky2': 'No completed Pi proof: telemetry / reboot / undervoltage',
               'RISC Zero': 'Resource/toolchain preflight only; no Pi proof',
               'SP1': 'ARM64 CLI starts; resource preflight; no Pi proof'}
    result = dict(records=records, unmeasured=missing,
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Five additional Pi4 native proof implementations, seven synthetic cases each',
        limitations=['One run per implementation; seven distinct inputs are not repeated statistical trials',
                     'Memory includes runner, startup and negative tests; timing excludes them',
                     'Different curves, security assumptions and binary formats; no universal ranking',
                     'Unmeasured proof performance is null/missing, not zero; CLI and Mac timings excluded'])
    (ROOT/'week24/logs/euclidean-additional-summary.json').write_text(json.dumps(result, indent=2)+'\n')
    plt.rcParams.update({'svg.fonttype': 'none', 'font.size': 10})
    fig, axes = plt.subplots(1,3,figsize=(15,6.7),layout='constrained')
    labels = [r['framework'] for r in records]+list(missing)
    for ax in axes:
        ax.set_yticks(range(8), labels); ax.set_ylim(7.7,-.8)
        ax.grid(axis='x', alpha=.2); ax.set_axisbelow(True)
        ax.spines[['top','right']].set_visible(False)
    for i,r in enumerate(records):
        v=r['flow_mean_ms']; axes[0].barh(i,v,color='#2369a5')
        axes[0].text(v*1.07,i,f'{v:.1f}',va='center',fontsize=9)
        mean=r['memory_time_weighted_mean_bytes']/2**20; peak=r['memory_kernel_peak_bytes']/2**20
        axes[1].barh(i-.17,mean,height=.3,color='#2369a5',label='Time-weighted mean' if i==0 else None)
        axes[1].barh(i+.17,peak,height=.3,color='#d6814b',label='Kernel peak' if i==0 else None)
        axes[1].text(peak+.2,i,f'{mean:.2f} / {peak:.2f}',va='center',fontsize=9)
        size=r['proof_mean_bytes']; axes[2].barh(i,size,color='#2369a5')
        axes[2].text(size*1.13,i,f'{size:,.0f}',va='center',fontsize=9)
    for ax in axes:
        for i in range(5,8): ax.text(.03,i,'N/A - no completed Pi proof',transform=ax.get_yaxis_transform(),va='center',fontsize=9,color='#555')
    axes[0].set(xscale='log',xlim=(10,1200),xlabel='Mean measured flow (ms, log scale)',title='Generation + verification (n=7)')
    axes[1].set(xlim=(0,19),xlabel='Whole-unit memory (MiB)',title='Startup and negative tests included')
    axes[1].legend(loc='upper right',fontsize=8)
    axes[2].set(xscale='log',xlim=(50,2000000),xlabel='Native serialized proof (bytes, log scale)',title='Public inputs / keys excluded')
    fig.suptitle('Additional Euclidean-distance proof evaluation on Raspberry Pi 4 (4 GB)',fontsize=15)
    fig.supxlabel('Synthetic inputs; one run per framework. Formats and security assumptions differ. CLI/Mac results excluded.',fontsize=10)
    out=ROOT/'week24/plots'; out.mkdir(exist_ok=True)
    for suffix in ['png','svg']: fig.savefig(out/f'euclidean-additional.{suffix}',dpi=180)
    svg=out/'euclidean-additional.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    for r in records: print(r['framework'],round(r['flow_mean_ms'],3),round(r['memory_time_weighted_mean_bytes']/2**20,3),round(r['memory_kernel_peak_bytes']/2**20,3),round(r['proof_mean_bytes'],1))

if __name__ == '__main__': main()
