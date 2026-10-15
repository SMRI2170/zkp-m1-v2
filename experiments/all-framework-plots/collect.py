# coding: utf-8
"""Normalize public recorded metrics only. No proving, secrets, or cache input."""
import csv,hashlib,json,re,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
NAMES=['gnark Groth16','gnark PLONK','Circom / RapidSnark','Halo2 IPA / Pasta',
       'Noir / Barretenberg','Nova / CycleFold','HyperNova / CycleFold','arkworks Groth16',
       'Halo2 KZG / BN254','Spartan','Bulletproofs R1CS','Plonky3 HidingFRI',
       'Kimchi','Binius64','Jolt','Plonky2','RISC Zero','SP1']

class Inputs:
    def __init__(self):self.hashes={}
    def text(self,name):
        path=ROOT/name;body=path.read_bytes();self.hashes[name]=hashlib.sha256(body).hexdigest();return body.decode()
    def json(self,name):return json.loads(self.text(name))
    def rows(self,name):return [json.loads(s) for s in self.text(name).splitlines() if s.startswith('{')]

def base(name,run,cohort,host='Pi4 ARM64',workload='distance'):
    return dict(framework=name,run_id=run,cohort=cohort,host=host,workload=workload,status='completed',
                samples=None,cpu_quota_percent=25 if cohort in ['pi_quota25','pi_signed'] else None,
                flow_mean_ms=None,setup_ms=None,memory_mean_bytes=None,kernel_peak_bytes=None,
                observed_peak_bytes=None,observed_memory_metric=None,proof_bytes=None,
                proof_scope='native proof only',flow_scope='logged per-case flow; setup excluded',
                ivc_only=False,notes='',max_wait_ms=None)

def flow(row):return row['prove_ms']+row['verify_ms']+row.get('witness_ms',0)

def normalize(inp):
    records=[]
    for x in inp.json('week24/logs/euclidean-comparison-summary.json')['records']:
        name=x['framework'];name='Circom / RapidSnark' if name=='Circom / RapidSnark' else name
        r=base(name,x['run'],'pi_affinity1')
        r.update(samples=x['measured_samples'],flow_mean_ms=x['flow_ms']['mean'],
                 memory_mean_bytes=x['cgroup_memory_time_weighted_mean_bytes'],kernel_peak_bytes=x['cgroup_memory_kernel_peak_bytes'],
                 proof_bytes=x['serialized_proof_size_bytes']['mean'] if x['serialized_proof_size_bytes'] else None,
                 proof_scope=x['size_encoding'],flow_scope=x['flow_scope'],ivc_only=x['ivc_only'])
        if r['ivc_only']:r['status']='ivc_only';r['notes']='Ordered IVC steps; final external ZK proof not implemented'
        if 'RapidSnark' in name:r['proof_scope']='JSON proof only'
        records.append(r)
    additional=inp.json('week24/logs/euclidean-additional-summary.json')['records']
    for x in additional:
        name={'Spartan SNARK':'Spartan'}.get(x['framework'],x['framework'])
        assert name in NAMES[7:12],name
        r=base(name,x['run'],'pi_affinity1')
        r.update(samples=x['measured_samples'],flow_mean_ms=x['flow_mean_ms'],memory_mean_bytes=x['memory_time_weighted_mean_bytes'],
                 kernel_peak_bytes=x['memory_kernel_peak_bytes'],proof_bytes=x['proof_mean_bytes'],setup_ms=x['setup_once_ms'],flow_scope=x['flow_scope'])
        records.append(r)
    for x in inp.json('week24/logs/euclidean-next-summary.json')['results']:
        name=x['label'].split('\n')[0].replace('Jolt ZK','Jolt')
        assert name in NAMES[12:15],name
        r=base(name,x['run'],'pi_quota25')
        r.update(samples=x['n'],flow_mean_ms=x['flow_mean_ms'],memory_mean_bytes=x['memory_time_weighted_mean_bytes'],
                 kernel_peak_bytes=x['memory_kernel_peak_bytes'],proof_bytes=x['proof_mean_bytes'])
        if name=='Binius64':r['notes']='ARM portable BLAKE3; differs from Mac native SIMD'
        if name=='Jolt':r['notes']='Quick case only; n=1, no SD claim'
        records.append(r)
    folder='week24/logs/pi-euclidean-followup/additional-halo2-kzg-root-v2/'
    samples=[s for s in inp.rows(folder+'benchmark.jsonl') if s.get('phase')=='sample'];res=inp.json(folder+'resource.json')
    r=base('Halo2 KZG / BN254','additional-halo2-kzg-root-v2','pi_quota25')
    r.update(samples=len(samples),flow_mean_ms=statistics.mean(map(flow,samples)),kernel_peak_bytes=res['cgroup_peak_bytes'],proof_bytes=statistics.mean(s['proof_bytes'] for s in samples),notes='Independent modified-root followup; whole-run memory mean not collected here')
    records.append(r)
    folder='week24/logs/pi-euclidean-followup/additional-plonky2-cpu25-v4/'
    samples=[s for s in inp.rows(folder+'benchmark.jsonl') if s.get('phase')=='sample'];partial=inp.json(folder+'partial-memory-summary.json')
    r=base('Plonky2','additional-plonky2-cpu25-v4','pi_quota25')
    r.update(status='partial',samples=len(samples),flow_mean_ms=statistics.mean(map(flow,samples)),observed_peak_bytes=partial['sampled_max_cgroup_bytes'],observed_memory_metric='sampled cgroup (partial)',proof_bytes=statistics.mean(s['proof_with_public_bytes'] for s in samples),proof_scope='proof + public 16B',notes='2 proofs verified; reboot before full7/summary; no final kernel peak')
    records.append(r)
    for name,run in [('Kimchi','kimchi-next-host-v2'),('Binius64','binius-next-host-v1'),('Jolt','jolt-next-prebuilt-host-v4')]:
        folder='week24/logs/mac-euclidean-next/'+run+'/'
        ss=[s for s in inp.rows(folder+'benchmark.jsonl') if s.get('phase')=='sample'];res=inp.json(folder+'resource.json')
        assert len(ss)==7 and all(s['verified'] for s in ss)
        r=base(name,run,'mac_distance','Mac ARM64')
        r.update(samples=7,flow_mean_ms=statistics.mean(map(flow,ss)),observed_peak_bytes=res['sampled_process_tree_peak_bytes'],observed_memory_metric='sampled process-tree RSS',proof_bytes=statistics.mean(s['proof_bytes'] for s in ss),notes='Mac native configuration, separate from Pi ARM portable build')
        records.append(r)
    for x in inp.json('week24/data/euclidean-evaluation/summary.json')['results']:
        name={'kimchi':'Kimchi','binius64':'Binius64','jolt':'Jolt'}[x['framework']]
        r=base(name,x['run_id'],'pi_repeat3');r['cpu_quota_percent']=25
        r.update(samples=x['measured_samples'],flow_mean_ms=x['flow_ms_mean'],memory_mean_bytes=x['whole_unit_time_weighted_mean_bytes'],kernel_peak_bytes=x['whole_unit_peak_bytes'],proof_bytes=x['proof_bytes_mean'],setup_ms=x['setup_ms'],notes='Same input within one process; warmup1 excluded, repeat3; not independent cold trials')
        records.append(r)
    samples=[s for s in inp.rows('week24/logs/plonky2-followup-host.jsonl') if s.get('phase')=='sample']
    log=inp.text('week24/logs/plonky2-followup-host-stderr.log');peak=int(re.search(r'(\d+)\s+peak memory footprint',log).group(1))
    r=base('Plonky2','plonky2-followup-host','mac_distance','Mac ARM64')
    r.update(samples=len(samples),flow_mean_ms=statistics.mean(map(flow,samples)),observed_peak_bytes=peak,observed_memory_metric='peak footprint',proof_bytes=statistics.mean(s['proof_with_public_bytes'] for s in samples),proof_scope='proof + public 16B')
    records.append(r)
    folder='week24/logs/zkvm-followup/risc0-host-proof-v2/'
    s=next(s for s in inp.rows(folder+'benchmark.jsonl') if s.get('phase')=='summary');res=inp.json(folder+'resource.json')
    r=base('RISC Zero','risc0-host-proof-v2','mac_distance','Mac ARM64')
    r.update(samples=1,flow_mean_ms=s['prove_ms']+s['verify_ms'],observed_peak_bytes=res['sampled_process_tree_peak_bytes'],observed_memory_metric='sampled process-tree RSS',proof_bytes=s['receipt_serialized_bytes'],proof_scope='Composite receipt',flow_scope='prove + verify; no separate witness timing',notes='No Groth16 wrapper; not Pi metrics')
    records.append(r)
    for version in [1,2]:
        run=f'sp1-host-proof-v{version}';res=inp.json(f'week24/logs/zkvm-followup/{run}/resource.json')
        r=base('SP1',run,'mac_distance','Mac ARM64')
        r.update(status='stopped',samples=0,observed_peak_bytes=res['sampled_process_tree_peak_bytes'],observed_memory_metric='sampled process-tree RSS',notes='System-wide swap growth >512MiB; not proof success or measured OOM')
        records.append(r)
    for name in ['RISC Zero','SP1']:
        r=base(name,name.lower().replace(' ','')+'-pi-not-run','pi_not_run')
        r.update(status='not_run',notes='Pi proof not executed; Linux ARM64 sysroot/C headers missing')
        records.append(r)
    for x in inp.json('week24/data/pi-observation-scaling-v2/summary.json')['results']:
        r=base('gnark Groth16',x['run_id'],'pi_signed',workload='signed_observations')
        r.update(status='completed' if x['status']=='completed' else 'partial',samples=x['measured_samples'],observation_count=x['observation_count'],flow_mean_ms=x['flow_ms_mean'],setup_ms=x['setup_ms'],
                 memory_mean_bytes=x['whole_unit_time_weighted_mean_bytes'] if x['status']=='completed' else None,
                 kernel_peak_bytes=x['whole_unit_peak_bytes'],proof_bytes=x['proof_bytes_mean'],flow_scope='witness + prove + verify; signing/setup/queue excluded')
        if r['status']=='partial':
            p=inp.json('week24/logs/pi-observation-workload/'+x['run_id']+'/partial-memory-summary.json')
            r.update(observed_peak_bytes=p['sampled_max_cgroup_bytes'],observed_memory_metric='sampled cgroup (partial)',notes='Historic reboot partial, no proof / final resource')
        records.append(r)
    q=inp.rows('week24/data/pi-observation-scaling-v2/queue_observed_1hz.jsonl')
    for r in records:
        if r['cohort']=='pi_signed':
            waits=[x['wait_ms'] for x in q if x['run_id']==r['run_id'] and x['phase']=='input_dequeue']
            r['max_wait_ms']=max(waits) if waits else None
    macsamples=inp.rows('week24/data/observation-followup/samples.jsonl')
    for x in inp.json('week24/data/observation-followup/summary.json')['results']:
        r=base('gnark Groth16',x['run_id'],'mac_signed','Mac ARM64','signed_observations')
        completed=x['status']=='completed'
        sizes=[s['proof_bytes'] for s in macsamples if s['run_id']==x['run_id'] and not s['warmup']]
        r.update(status='completed' if completed else 'partial',samples=x['n'],observation_count=x['observation_count'],flow_mean_ms=x['flow_mean_ms'],setup_ms=x['setup_ms'],
                 observed_peak_bytes=x['whole_run_sampled_process_tree_rss_peak_bytes'],observed_memory_metric='sampled process-tree RSS',proof_bytes=statistics.mean(sizes) if sizes else None,
                 max_wait_ms=x['max_wait_ms'],notes='Fresh setup/key per process; one stopped run retains only recorded verified samples' if not completed else 'Fresh setup/key; not exact identical-witness cold repetition')
        records.append(r)
    return records

def coverage(inp,records):
    follow=inp.json('week24/logs/euclidean-followup-evaluation.json')
    assert follow['plonky2']['pi_verified_cases']==2 and follow['risc0']['mac_verified_cases']==1 and follow['sp1']['mac_verified_cases']==0
    def state(name,host,workload):
        group=[r for r in records if r['framework']==name and r['host'].startswith(host) and r['workload']==workload]
        for value,out in [('completed','verified'),('ivc_only','ivc_only'),('partial','partial'),('stopped','stopped'),('not_run','not_run')]:
            if any(r['status']==value for r in group):return out
        return 'not_summarized' if host=='Mac' and workload=='distance' else 'not_run'
    return [{'framework':name,'pi_distance':state(name,'Pi4','distance'),'mac_distance':state(name,'Mac','distance'),
             'pi_signed':state(name,'Pi4','signed_observations')} for name in NAMES]

def write_table(path,rows):
    fields=sorted(set().union(*(x.keys() for x in rows)))
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)

def collect(out):
    inp=Inputs();records=normalize(inp);states=coverage(inp,records);out.mkdir(parents=True,exist_ok=True)
    (out/'metrics.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    (out/'metrics.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in records));write_table(out/'metrics.csv',records)
    (out/'coverage.json').write_text(json.dumps(states,ensure_ascii=False,indent=2)+'\n');write_table(out/'coverage.csv',states)
    (out/'provenance.json').write_text(json.dumps({'source_sha256':inp.hashes,'new_measurements':False,
        'missing':'null / empty CSV, never zero-filled','cohorts':'Pi affinity1 quota unset / Pi25% / Mac / signed workload separated',
        'memory':'Pi kernel cgroup peak differs from sampled cgroup/RSS and Mac footprint; mean includes setup/negative tests',
        'statistics':'recorded means, variable cases / repeats / ordered IVC steps; no universal ranking or confidence intervals'},indent=2)+'\n')
    return records,states
