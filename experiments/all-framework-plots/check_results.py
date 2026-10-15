# coding: utf-8
"""Validate coverage, source provenance, nulls, and exported figure integrity."""
import hashlib,json,struct,zipfile
from pathlib import Path
from collect import ROOT,Inputs,normalize,coverage

def main():
    manifest=json.loads((ROOT/'week24/manifests/all-framework-plots.json').read_text())
    for name,digest in manifest['file_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    folder=ROOT/'week24/data/all-frameworks'
    records=json.loads((folder/'metrics.json').read_text());states=json.loads((folder/'coverage.json').read_text())
    inp=Inputs();derived=normalize(inp);assert records==derived,'published metrics differ from recorded inputs'
    assert states==coverage(inp,derived)
    assert len(records)==38 and len(states)==18 and len({s['framework'] for s in states})==18
    assert {r['framework'] for r in records}=={s['framework'] for s in states}
    assert sum(s['pi_distance']=='ivc_only' for s in states)==2
    assert sum(s['pi_distance']=='verified' for s in states)==13
    assert sum(s['pi_distance']=='partial' for s in states)==1
    assert sum(s['pi_distance']=='not_run' for s in states)==2
    for r in records:
        if r['ivc_only']:assert r['proof_bytes'] is None
        if r['status'] in ['stopped','not_run']:assert r['flow_mean_ms'] is None and r['proof_bytes'] is None
        if r['status']=='partial':assert r['kernel_peak_bytes'] is None
        if r['host'].startswith('Mac'):assert r['kernel_peak_bytes'] is None
    provenance=json.loads((folder/'provenance.json').read_text());assert provenance['new_measurements'] is False
    assert provenance['source_sha256']==inp.hashes
    for name,digest in provenance['source_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    figures=ROOT/'week24/plots/all-frameworks'
    pngs=list(figures.glob('*.png'));svgs=list(figures.glob('*.svg'));assert len(pngs)==len(svgs)==7
    for p in pngs:
        body=p.read_bytes();assert body[:8]==b'\x89PNG\r\n\x1a\n'
        w,h=struct.unpack('>II',body[16:24]);assert w>1400 and h>600,p.name
    for p in svgs:assert '<svg' in p.read_text() and '<path' in p.read_text()
    with zipfile.ZipFile(ROOT/'week24/plots/all-frameworks.zip') as z:
        assert sum(n.endswith('.png') for n in z.namelist())==7
        assert sum(n.endswith('.svg') for n in z.namelist())==7
    print('All-framework figures verified: 18 configurations / 38 records / 7 PNG + SVG, missing/partial/IVC/host scopes preserved; no new measurements.')

if __name__=='__main__':main()
