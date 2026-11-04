"""Preserve Artifact Tool output; add native slide-number fields and omit notes."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import re,uuid,xml.etree.ElementTree as E
ROOT=Path(__file__).resolve().parents[2]
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
for k,v in NS.items():E.register_namespace(k,v)
F='Hiragino Kaku Gothic ProN W3'
for tag in ['C']:
 folder=ROOT/'.cache/week26-slides'/tag
 with ZipFile(folder/'draft.pptx') as z,ZipFile(folder/'candidate.pptx','w',ZIP_DEFLATED) as out:
  nums=0
  for n in z.namelist():
   if n.startswith(('ppt/notesSlides/','ppt/notesMasters/')):continue
   b=z.read(n)
   if re.fullmatch(r'ppt/slides/slide\d+\.xml',n):
    x=E.fromstring(b);no=int(re.search(r'slide(\d+)',n)[1]);found=0
    for sp in x.findall('.//p:sp',NS):
     ph=sp.find('p:nvSpPr/p:nvPr/p:ph',NS)
     if ph is None or ph.get('type')!='sldNum':continue
     tb=sp.find('p:txBody',NS)
     if tb is None:continue
     for p in list(tb.findall('a:p',NS)):tb.remove(p)
     p=E.SubElement(tb,f'{{{NS["a"]}}}p');E.SubElement(p,f'{{{NS["a"]}}}pPr',{'algn':'r'})
     fld=E.SubElement(p,f'{{{NS["a"]}}}fld',{'id':'{'+str(uuid.uuid5(uuid.NAMESPACE_URL,tag+':'+n))+'}','type':'slidenum'})
     rp=E.SubElement(fld,f'{{{NS["a"]}}}rPr',{'lang':'ja-JP','sz':'1100'})
     fill=E.SubElement(rp,f'{{{NS["a"]}}}solidFill');E.SubElement(fill,f'{{{NS["a"]}}}srgbClr',{'val':'7B8591'})
     for t in ['latin','ea','cs']:E.SubElement(rp,f'{{{NS["a"]}}}{t}',{'typeface':F})
     E.SubElement(fld,f'{{{NS["a"]}}}t').text=str(no);found+=1
    if found!=1:raise ValueError((tag,n,'expected one native number placeholder',found))
    nums+=found;b=E.tostring(x,encoding='utf-8',xml_declaration=True)
   elif n.endswith('.rels'):
    x=E.fromstring(b)
    for r in list(x):
     if r.get('Type','').endswith(('/notesSlide','/notesMaster')):x.remove(r)
    b=E.tostring(x,encoding='utf-8',xml_declaration=True)
   elif n=='[Content_Types].xml':
    x=E.fromstring(b)
    for el in list(x):
     if el.get('PartName','').startswith(('/ppt/notesSlides/','/ppt/notesMasters/')):x.remove(el)
    E.register_namespace('', 'http://schemas.openxmlformats.org/package/2006/content-types')
    b=E.tostring(x,encoding='utf-8',xml_declaration=True)
   elif n=='ppt/presentation.xml':
    x=E.fromstring(b)
    for el in list(x):
     if el.tag.endswith('notesMasterIdLst'):x.remove(el)
    b=E.tostring(x,encoding='utf-8',xml_declaration=True)
   out.writestr(n,b)
  assert nums==50
 print(tag,'prepared 50 native number fields, no speaker notes')
