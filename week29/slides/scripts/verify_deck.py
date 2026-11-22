"""Compare editable slide chart values to the existing public research aggregates."""
import csv, json, math, re, posixpath, hashlib
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as E
ROOT=Path(__file__).resolve().parents[3]
R=ROOT/'week29/results';D=R/'research-review-20261119-f'
def js(p):return json.loads(p.read_text())
def csvs(p):return list(csv.DictReader(p.open()))
interval=js(R/'issue92-intervals-a/summary.json')['nodes']
scan=js(R/'scan-busy-20261118T160046Z/analysis.json')['groups']
def busy(mode,period):
 g=next(g for g in scan if g['strategy']==mode and g['configured_interval_s']==period)
 return 100*g['busy']/g['requests']
android=js(R/'android-background-20261119T003039Z/summary.json')['nodes']
quality=js(D/'quality-gates.json')['nodes']
model=js(D/'model-diagnosis.json')
pairs=csvs(D/'paired-transitions.csv')
def pair(mode):return next(x for x in pairs if x['direction']=='away' and x['shift_m']=='50' and x['mode']==mode)
a=pair('claim_only');b=pair('model_matched_unbounded')
synth=js(D/'synthetic-explanation.json')
gate=csvs(D/'claim-dependent-selection.csv')
original_expected={
 9:[[round(interval[n]['pack_change_intervals_s']['median'],2) for n in ['B','Pixel','ASUS-1','ASUS-2']]],
 14:[[busy('all_channels',.5),busy('fixed_frequency',.5)]],
 15:[[p['target_distinct_vendor_contents'] for p in node['phases']] for node in android],
 18:[[quality[n]['selected_rows'] for n in ['Pixel','ASUS-1','ASUS-2']],[quality[n]['held_rows'] for n in ['Pixel','ASUS-1','ASUS-2']]],
 24:[[100*p['alarm_fraction'] for p in model['partitions']]],
 27:[[13,int(a['alarm_to_alarm'])],[0,int(a['quiet_to_alarm'])],[14,int(a['quiet_to_quiet'])]],
 28:[[13,int(a['alarm_to_alarm']),int(b['alarm_to_alarm'])],[0,int(a['quiet_to_alarm']),int(b['quiet_to_alarm'])],[14,int(a['quiet_to_quiet']),int(b['quiet_to_quiet'])]],
 29:[[synth['baseline_score'],synth['claim_only_score'],synth['compensated_score']],[synth['threshold']]*3],
 30:[[quality['Pixel']['selected_rows']]+[sum(int(x['after_claim_change_selected']) for x in gate if int(x['synthetic_away_shift_m'])==d) for d in [20,50,100]]],
 37:[[busy(mode,p) for p in [.5,1,2,5]] for mode in ['all_channels','fixed_frequency']],
 40:[[100*b['baseline_alarm_fraction'] for b in model['descriptive_blocks']]],
}
expected={(n+3 if 7<=n<=16 else n+4 if n>=17 else n):v for n,v in original_expected.items()}
P=ROOT/'week29/slides/output/第29回_実験説明版.pptx'
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
checks=[]
with ZipFile(P) as z:
 slides=[n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
 assert len(slides)==46
 assert not any('/notesSlides/' in n for n in z.namelist())
 for n in slides:
  root=E.fromstring(z.read(n));i=int(re.search(r'slide(\d+)',n)[1])
  assert len(root.findall('.//a:fld[@type="slidenum"]',ns))==1
  assert '__AUTO_SLIDE__' not in str(z.read(n))
  strings=[e.text or '' for e in root.findall('.//a:t',ns)]
  if i not in (37,38):assert not any('DOI:' in x or 'developer.android.com' in x or '出典：' in x for x in strings)
 for owner,want in expected.items():
  root=E.fromstring(z.read(f'ppt/slides/slide{owner}.xml'))
  relid=root.find('.//c:chart',ns).get('{'+ns['r']+'}id')
  rels=E.fromstring(z.read(f'ppt/slides/_rels/slide{owner}.xml.rels'))
  rel=next(r for r in rels if r.get('Id')==relid)
  chartpath=posixpath.normpath(posixpath.join('ppt/slides',rel.get('Target'))).lstrip('/')
  cr=E.fromstring(z.read(chartpath)); got=[]
  for ser in cr.findall('.//c:ser',ns):
   vals=ser.findall('c:val//c:numCache/c:pt/c:v',ns)
   if not vals:vals=ser.findall('c:val/c:numLit/c:pt/c:v',ns)
   got.append([float(v.text) for v in vals])
  assert len(got)==len(want),(owner,got,want)
  for g,w in zip(got,want):
   assert len(g)==len(w)
   assert all(math.isclose(x,y,rel_tol=0,abs_tol=1e-7) for x,y in zip(g,w)),(owner,g,w)
  checks.append({'slide':owner,'series':len(got),'numeric_cells':sum(map(len,got)),'source_aggregate_match':True})
report={'slides':46,'notes_parts':0,'native_slide_number_fields':46,'references_after_future_work':True,'chart_source_checks':checks,'pptx_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'rendering':'LibreOffice PDF and Poppler PNG; PowerPoint GUI not tested'}
path=ROOT/'.cache/week29-slides-build/source-verification-experiment.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'slide_count':46,'chart_count':len(checks),'numeric_values_verified':sum(c['numeric_cells'] for c in checks),'passed':True}))
