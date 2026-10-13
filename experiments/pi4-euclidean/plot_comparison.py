"""Reproducible means/size charts from the seven committed Pi Euclidean runs.
No hardware execution, private fixtures, proofs, or witness material is read.
"""
import hashlib
import json
import math
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNS = [
    ('gnark Groth16', 'euclidean-groth16-v1', False),
    ('gnark PLONK', 'euclidean-plonk-v1', False),
    ('Circom / RapidSnark', 'euclidean-rapid-v3', False),
    ('Halo2 IPA / Pasta', 'euclidean-halo2-v2', False),
    ('Noir / Barretenberg', 'euclidean-noir-v1', False),
    ('Nova / CycleFold', 'euclidean-nova-v2', True),
    ('HyperNova / CycleFold', 'euclidean-hypernova-v1', True),
]
OUTPUT = ROOT / 'week24/plots'
OUTPUT.mkdir(exist_ok=True)
COLORS = {'zk': '#2369a5', 'ivc': '#8459a6', 'witness': '#86bfc5',
          'prove': '#2369a5', 'verify': '#e4aa48', 'peak': '#d6814b', 'json': '#d6814b'}
plt.rcParams.update({'svg.fonttype': 'none', 'font.size': 10,
                     'axes.spines.top': False, 'axes.spines.right': False})

def describe(values):
    xs = sorted(values)
    f = (len(xs)-1)*.95
    i = int(f)
    p95 = xs[i] if i+1 == len(xs) else xs[i]+(xs[i+1]-xs[i])*(f-i)
    return {'n': len(xs), 'mean': statistics.mean(xs),
            'population_sd': statistics.pstdev(xs), 'min': min(xs), 'max': max(xs), 'p95': p95}

records = []
for label, name, ivc in RUNS:
    run = ROOT / 'week24/logs/pi-euclidean' / name
    logs = [json.loads(line) for line in (run/'benchmark.jsonl').read_text().splitlines()]
    resource = json.loads((run/'resource.json').read_text())
    assert resource['exit_code'] == 0 and resource['stop_reason'] is None
    assert logs[-1]['all_verified']
    samples = [row for row in logs if row['phase'] == 'sample' and not row.get('warmup', False)]
    assert samples and all(row['verified'] for row in samples)
    witness_key = 'execute_compile_witness_ms' if 'noir' in name else 'witness_ms'
    prove_key = 'prove_with_vk_ms' if 'noir' in name else 'prove_ms'
    witness = [row[witness_key] for row in samples] if witness_key in samples[0] else None
    prove = [row[prove_key] for row in samples]
    verify = [row['verify_ms'] for row in samples]
    # Missing separate witness time is NOT an observed zero. Flow is the sum
    # of only logged intervals, with missing/included scope recorded below.
    flow = [row[prove_key]+row['verify_ms']+row.get(witness_key, 0) for row in samples]
    memory = [json.loads(line) for line in (run/'memory.jsonl').read_text().splitlines()]
    durations = [b['elapsed_s']-a['elapsed_s'] for a,b in zip(memory,memory[1:])]
    assert durations and all(d > 0 for d in durations)
    weighted_mean = sum(row['cgroup_current_bytes']*dt for row,dt in zip(memory,durations))/sum(durations)
    cached = json.loads((run/'memory-summary.json').read_text())
    assert math.isclose(weighted_mean, cached['time_weighted']['mean_bytes'], rel_tol=1e-12)
    size_key = next((k for k in ['proof_bytes','proof_json_bytes'] if k in samples[0]), None)
    size = describe([row[size_key] for row in samples]) if size_key else None
    scope = ('prove/update + verify; separate witness time unmeasured' if ivc else
             'prove (witness processing included) + verify' if 'halo2' in name else
             'execute (compile + witness) + prove (VK generation included) + verify' if 'noir' in name else
             'witness + prove + verify; native CLI launch included' if 'rapid' in name else
             'witness + prove + verify; compile/key load excluded')
    record = {
        'framework': label, 'run': name, 'ivc_only': ivc, 'measured_samples': len(samples),
        'excluded_warmups': sum(row.get('warmup', False) for row in logs if row['phase']=='sample'),
        'flow_scope': scope, 'flow_ms': describe(flow), 'witness_ms': describe(witness) if witness else None,
        'prove_or_ivc_update_ms': describe(prove), 'verify_ms': describe(verify),
        'cgroup_memory_time_weighted_mean_bytes': weighted_mean,
        'cgroup_memory_sample_distribution_bytes': describe([r['cgroup_current_bytes'] for r in memory]),
        'cgroup_memory_kernel_peak_bytes': resource['cgroup_peak_bytes'],
        'observed_memory_span_s': sum(durations), 'memory_samples': len(memory),
        'serialized_proof_size_bytes': size,
        'size_encoding': 'unmeasured; raw IVC is not final ZK proof' if ivc else
                         'JSON text; not binary proof encoding' if size_key=='proof_json_bytes' else
                         'native serialized binary; not a uniform wire/EVM format',
        'serialized_public_size_bytes': describe([r['public_bytes'] for r in samples]) if 'public_bytes' in samples[0] else None,
        'pi_prepare_once_ms': next((r['setup_ms'] for r in logs if r['phase']=='keys'), None),
        'pi_compile_once_ms': logs[0].get('compile_ms'), 'pi_key_load_once_ms': logs[0].get('key_load_ms'),
        'source_log_sha256': {p: hashlib.sha256((run/p).read_bytes()).hexdigest()
                              for p in ['benchmark.jsonl','resource.json','memory.jsonl']},
    }
    assert math.isclose(record['flow_ms']['mean'], statistics.mean(prove)+statistics.mean(verify)+
                        (statistics.mean(witness) if witness else 0), rel_tol=1e-12)
    records.append(record)

summary = {'data_scope': 'Existing synthetic Pi4 integer Euclidean distance runs; no new measurements',
           'sample_selection': 'Same seven successful runs as report03; exclude gnark warmups; keep cold first cases of the other five',
           'mean_definition': 'Time: arithmetic mean of per-case logged intervals. Memory: duration-weighted whole-cgroup mean, previous value held until next sample.',
           'limitations': ['Different setup/serialization/public statements and sample counts; no universal speed ranking',
                          'IVC steps are ordered and not independent repeated trials; not final ZK proofs',
                          'No process launch, queue, sensor capture, negative tests, startup or teardown in reported per-case flow',
                          'Memory includes startup, normal and negative verification, and all child processes',
                          'Noir first case includes cold CRS/preparation costs; timings include VK generation and execute/compile',
                          'Proof size excludes public input, keys and transport envelope; missing IVC sizes are null, never zero'],
           'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'plot_library_versions': {'matplotlib': matplotlib.__version__, 'numpy': np.__version__},
           'records': records}
(ROOT/'week24/logs/euclidean-comparison-summary.json').write_text(json.dumps(summary, indent=2)+'\n')

labels = [r['framework']+(' [IVC]' if r['ivc_only'] else '') for r in records]
colors = [COLORS['ivc'] if r['ivc_only'] else COLORS['zk'] for r in records]
y = np.arange(len(records))

def format_axes(ax, title, xlabel):
    ax.set_title(title, loc='left', fontweight='bold', pad=12)
    ax.set_xlabel(xlabel)
    ax.set_yticks(y, labels)
    ax.set_ylim(len(records)-.5, -.5)
    ax.grid(axis='x', alpha=.18)
    ax.set_axisbelow(True)

def annotate(ax, values, precision=2, suffix='', log=False):
    for yy, value in enumerate(values):
        ax.annotate(f'{value:,.{precision}f}{suffix}', (value, yy), xytext=(5,0),
                    textcoords='offset points', va='center', fontsize=9)

def draw_flow(ax, prove_only=False):
    key = 'prove_or_ivc_update_ms' if prove_only else 'flow_ms'
    values = [r[key]['mean']/1000 for r in records]
    ax.barh(y, values, color=colors, height=.60)
    ax.set_xscale('log');ax.set_xlim(.01,10)
    title = 'B  Mean proof generation / IVC update' if prove_only else 'A  Mean measured per-case flow'
    format_axes(ax,title,'Seconds (log scale)')
    annotate(ax,values,3,' s')

def draw_memory(ax):
    means=[r['cgroup_memory_time_weighted_mean_bytes']/2**20 for r in records]
    peaks=[r['cgroup_memory_kernel_peak_bytes']/2**20 for r in records]
    ax.barh(y-.18,means,height=.32,color=COLORS['zk'],label='Time-weighted mean')
    ax.barh(y+.18,peaks,height=.32,color=COLORS['peak'],label='Kernel peak')
    format_axes(ax,'C  Whole experiment memory','MiB (1 MiB = 1,048,576 bytes)')
    ax.set_xlim(0,230)
    for yy,a,b in zip(y,means,peaks):
        for offset,v in [(-.18,a),(.18,b)]:
            ax.annotate(f'{v:.1f}',(v,yy+offset),xytext=(4,0),textcoords='offset points',va='center',fontsize=8)
    ax.legend(loc='upper right',fontsize=8)

def draw_sizes(ax):
    for yy,r in enumerate(records):
        size=r['serialized_proof_size_bytes']
        if size is None:
            ax.text(.16,yy,'N/A: not measured; IVC only',va='center',fontsize=9,color='#735092')
            continue
        value=size['mean']/1024
        color=COLORS['json'] if 'JSON' in r['size_encoding'] else COLORS['zk']
        ax.barh(yy,value,color=color,height=.60)
        tag=' JSON' if 'JSON' in r['size_encoding'] else ' binary'
        ax.annotate(f'{size["mean"]:,.1f} B{tag}',(value,yy),xytext=(5,0),textcoords='offset points',va='center',fontsize=8)
    format_axes(ax,'D  Mean serialized proof size','KiB; excludes public inputs, keys, envelopes')
    ax.set_xlim(0,9.7)

fig,axes=plt.subplots(2,2,figsize=(16,11.5))
draw_flow(axes[0,0]);draw_flow(axes[0,1],True);draw_memory(axes[1,0]);draw_sizes(axes[1,1])
fig.suptitle('Pi4 | Integer Euclidean distance circuits\nMeans from existing successful runs; blue = single proof, purple = IVC',fontsize=16,fontweight='bold')
fig.text(.02,.014,'Flow = logged witness/execute + prove/update + verify; missing separate witness time is disclosed.\n'
         'gnark n=20 (warmup excluded); others n=7 (cold case included). IVC is not final ZK. Memory covers full run, including negative tests.\n'
         'Noir includes compile/VK costs; RapidSnark includes CLI launch. Binary and JSON sizes are different encodings.',fontsize=9,color='#444444')
fig.tight_layout(rect=[0,.075,1,.93],h_pad=3,w_pad=3)

def save(fig, name):
    fig.savefig(OUTPUT/(name+'.png'),dpi=180)
    fig.savefig(OUTPUT/(name+'.svg'))
    p=OUTPUT/(name+'.svg');p.write_text('\n'.join(line.rstrip() for line in p.read_text().splitlines())+'\n')

save(fig,'euclidean-pi-comparison')
plt.close(fig)

fig,axes=plt.subplots(1,2,figsize=(15,6.5))
for ax,idxs,title in [(axes[0],[0,1,2],'Short flows (seconds)'),(axes[1],[3,4,5,6],'Longer flows (seconds)')]:
    yy=np.arange(len(idxs));left=np.zeros(len(idxs))
    for key,label,color in [('witness_ms','Witness / execute',COLORS['witness']),
                            ('prove_or_ivc_update_ms','Prove / IVC update',COLORS['prove']),
                            ('verify_ms','Verify',COLORS['verify'])]:
        values=[records[i][key]['mean']/1000 if records[i][key] else 0 for i in idxs]
        ax.barh(yy,values,left=left,color=color,label=label,height=.65)
        left+=np.array(values)
    for j,total in enumerate(left):
        ax.annotate(f'{total:.3f} s',(total,j),xytext=(5,0),textcoords='offset points',va='center',fontsize=10)
    ax.set_yticks(yy,[labels[i] for i in idxs]);ax.invert_yaxis();ax.set_title(title,loc='left',fontweight='bold')
    ax.set_xlabel('Seconds (linear scale; separate axis range)');ax.set_xlim(0,max(left)*1.25)
    ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
axes[1].legend(loc='upper right',fontsize=9)
fig.suptitle('Mean logged flow components | Pi4 Euclidean distance',fontsize=16,fontweight='bold')
fig.text(.02,.025,'No separate witness interval was logged for Halo2 or IVC: zero-width segment means unmeasured/included, not zero cost.\n'
         'Startup/key load/negative tests are excluded. Noir execute includes compile; prove includes VK generation. IVC: update, not final ZK.',fontsize=9)
fig.tight_layout(rect=[0,.12,1,.91],w_pad=3)
save(fig,'euclidean-pi-flow-breakdown')
plt.close(fig)
print(json.dumps({'frameworks':len(records),'measured_cases':sum(r['measured_samples'] for r in records),
                  'summary':'week24/logs/euclidean-comparison-summary.json','figures':['euclidean-pi-comparison','euclidean-pi-flow-breakdown']}))
