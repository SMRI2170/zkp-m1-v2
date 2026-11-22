"""Replace the explicit field token with an OOXML slide-number field; no slide content changes."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as E
import re, uuid, json
root=Path(__file__).resolve().parents[3]
a='http://schemas.openxmlformats.org/drawingml/2006/main'
p='http://schemas.openxmlformats.org/presentationml/2006/main'
E.register_namespace('a',a);E.register_namespace('p',p)
E.register_namespace('r','http://schemas.openxmlformats.org/officeDocument/2006/relationships')
count=0
with ZipFile(root/'.cache/week29-slides-build/candidate-base.pptx') as src,ZipFile(root/'.cache/week29-slides-build/candidate.pptx','w',ZIP_DEFLATED) as dst:
 for info in src.infolist():
  if info.filename.startswith(('ppt/notesSlides/','ppt/notesMasters/')): continue
  data=src.read(info.filename)
  if info.filename.endswith('.rels'):
   E.register_namespace('', 'http://schemas.openxmlformats.org/package/2006/relationships')
   rel=E.fromstring(data)
   for item in list(rel):
    if item.get('Type','').endswith(('/notesSlide','/notesMaster')): rel.remove(item)
   data=E.tostring(rel,encoding='utf-8',xml_declaration=True)
  if info.filename=='[Content_Types].xml':
   E.register_namespace('', 'http://schemas.openxmlformats.org/package/2006/content-types')
   ct=E.fromstring(data)
   for item in list(ct):
    if item.get('PartName','').startswith(('/ppt/notesSlides/','/ppt/notesMasters/')): ct.remove(item)
   data=E.tostring(ct,encoding='utf-8',xml_declaration=True)
  if info.filename=='ppt/presentation.xml':
   pr=E.fromstring(data)
   for item in list(pr):
    if item.tag==f'{{{p}}}notesMasterIdLst':pr.remove(item)
   data=E.tostring(pr,encoding='utf-8',xml_declaration=True)
  m=re.fullmatch(r'ppt/slides/slide(\d+)\.xml',info.filename)
  if m:
   tree=E.fromstring(data)
   for para in tree.iter(f'{{{a}}}p'):
    for index,child in enumerate(list(para)):
     if child.tag==f'{{{a}}}r' and child.findtext(f'{{{a}}}t')=='__AUTO_SLIDE__':
      field=E.Element(f'{{{a}}}fld',{'id':'{'+str(uuid.uuid4()).upper()+'}','type':'slidenum'})
      props=child.find(f'{{{a}}}rPr')
      if props is not None:field.append(props)
      E.SubElement(field,f'{{{a}}}t').text=m.group(1)
      para.remove(child);para.insert(index,field);count+=1
   data=E.tostring(tree,encoding='utf-8',xml_declaration=True)
  dst.writestr(info,data)
expected=len(json.loads((root/'.cache/week29-slides-build/deck-manifest.json').read_text())['titles'])
assert count==expected,count
print(f'native slide-number fields: {count}')
