"""Read selected SigMF metadata through verified, bounded HTTP byte ranges.

Never downloads whole IQ archive; stores source material only under captures/.
Full archive MD5 is advertised but cannot be verified by partial retrieval.
"""
import argparse,csv,hashlib,io,json,os,urllib.request,zipfile,zlib
from pathlib import Path

URL='https://zenodo.org/api/records/20341802/files/sigmfs.zip/content'
SIZE=71002741525
BLOCK=65536
LIMIT=32*1024*1024


def private_write(path,body):
    if path.exists():
        if path.read_bytes()!=body:raise ValueError('Existing raw artifact differs')
        if path.stat().st_mode&0o077:raise ValueError('Unsafe raw permissions')
        return
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as s:s.write(body)


class RangeArchive(io.RawIOBase):
    def __init__(self,raw,opener=urllib.request.urlopen,size=SIZE):
        self.raw=raw;self.opener=opener;self.size=size;self.pos=0;self.used=0;self.ranges=[]
    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):
        p=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset
        if p<0 or p>self.size:raise ValueError('Invalid seek')
        self.pos=p;return p
    def read(self,size=-1):
        if size<0:size=self.size-self.pos
        size=min(size,self.size-self.pos)
        if size>LIMIT:raise ValueError('Unbounded read refused')
        output=bytearray()
        while size:
            start=self.pos if size>BLOCK else (self.pos//BLOCK)*BLOCK
            end=self.pos+size-1 if size>BLOCK else min(start+BLOCK,self.size)-1
            p=self.raw/f'range-{start}-{end}.bin'
            if p.exists():
                if p.stat().st_mode&0o077:raise ValueError('Unsafe cached range')
                body=p.read_bytes()
            else:
                if self.used+end-start+1>LIMIT:raise ValueError('Download budget exceeded')
                request=urllib.request.Request(URL,headers={'Range':f'bytes={start}-{end}'})
                with self.opener(request,timeout=30) as r:
                    if r.status!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{self.size}':raise ValueError('Range not honored')
                    body=r.read(end-start+2)
                if len(body)!=end-start+1:raise ValueError('Range length mismatch')
                private_write(p,body);self.used+=len(body)
            if len(body)!=end-start+1:raise ValueError('Cached range length mismatch')
            self.ranges.append(dict(start=start,end=end,sha256=hashlib.sha256(body).hexdigest()))
            offset=self.pos-start;take=min(size,len(body)-offset)
            output+=body[offset:offset+take];self.pos+=take;size-=take
        return bytes(output)


def choose(csvpath):
    if hashlib.sha256(csvpath.read_bytes()).hexdigest()!='f261a911a96c6e79b23272a21091b97e51719ef1c1033116d900862afde65fd3':raise ValueError('Unexpected CSV version')
    selected={}
    with csvpath.open() as f:
        for r in csv.DictReader(f):
            if r['area_type'] not in ('drone_los','drone_nlos') or not r['latitude'] or not r['longitude']:continue
            key=(r['name'],r['rrh_idx'])
            if key not in selected:selected[key]=r
    return selected


def fetch(raw,csvpath):
    raw.mkdir(mode=0o700,parents=True,exist_ok=True)
    if raw.stat().st_mode&0o077:raise ValueError('Raw directory must be owner-only')
    remote=RangeArchive(raw);items=[]
    with zipfile.ZipFile(remote) as z:
        names=set(z.namelist());selected=choose(csvpath)
        for (session,receiver),row in selected.items():
            expected=row['sigmf_file'].removeprefix('./').removesuffix('.sigmf-data')+'.sigmf-meta'
            # Resolve only a unique archive suffix; do not extract arbitrary paths.
            candidates=[n for n in names if n==expected or n.endswith('/'+expected)]
            if len(candidates)!=1:raise ValueError('Ambiguous or missing metadata member')
            name=candidates[0];info=z.getinfo(name)
            if info.file_size>1024*1024:raise ValueError('Oversized metadata')
            with z.open(info) as member:body=member.read(1024*1024+1)
            if len(body)!=info.file_size:raise ValueError('Metadata size mismatch')
            # zipfile verifies member CRC when the full member is read.
            label=f'{session}-rrh{receiver}.sigmf-meta';private_write(raw/label,body)
            items.append(dict(session=session,receiver=receiver,local_file=label,archive_member=name,
                crc32=f'{info.CRC:08x}',sha256=hashlib.sha256(body).hexdigest(),size_bytes=len(body)))
    manifest=dict(url=URL,size=SIZE,advertised_md5='3beba472df07f1041d52ef9ad770b01c',full_archive_hash_verified=False,
        items=items,ranges=list({(r['start'],r['end']):r for r in remote.ranges}.values()))
    private_write(raw/'manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())
    return manifest

def metadata_fields(meta):
    paths=set();comment_keys=set()
    for section in ('global','captures','annotations'):
        values=meta.get(section,{} if section=='global' else [])
        if isinstance(values,dict):values=[values]
        for entry in values:
            for key,value in entry.items():
                paths.add(section+'/'+key)
                if key=='core:comment' and isinstance(value,str):
                    for line in value.splitlines():
                        if '\t' in line:comment_keys.add(line.split('\t',1)[0])
    return sorted(paths),sorted(comment_keys)


def audit(raw):
    if raw.stat().st_mode&0o077:raise ValueError('Unsafe raw directory')
    manifest=json.loads((raw/'manifest.json').read_text());records=[]
    for r in manifest['ranges']:
        body=(raw/f"range-{r['start']}-{r['end']}.bin").read_bytes()
        if len(body)!=r['end']-r['start']+1 or hashlib.sha256(body).hexdigest()!=r['sha256']:raise ValueError('Range cache mismatch')
    for item in manifest['items']:
        p=raw/item['local_file']
        if p.stat().st_mode&0o077:raise ValueError('Unsafe metadata file')
        body=p.read_bytes()
        if hashlib.sha256(body).hexdigest()!=item['sha256'] or f'{zlib.crc32(body):08x}'!=item['crc32']:raise ValueError('Metadata cache mismatch')
        x=json.loads(body);paths,comment_keys=metadata_fields(x);g=x['global']
        records.append(dict(session=item['session'],receiver=item['receiver'],sha256=item['sha256'],
            size_bytes=len(body),member_crc32=item['crc32'],datatype=g['core:datatype'],
            sample_rate=g['core:sample_rate'],num_channels=g['core:num_channels'],
            metadata_paths=paths,comment_field_names=comment_keys,
            annotations=len(x.get('annotations',[])),iq_sha512_advertised='core:sha512' in g))
    fields=sorted({p for r in records for p in r['metadata_paths']+r['comment_field_names']})
    return dict(source_url='https://zenodo.org/records/20341802',archive_size=SIZE,
        archive_advertised_md5=manifest['advertised_md5'],full_archive_hash_verified=False,
        source_manifest_sha256=hashlib.sha256((raw/'manifest.json').read_bytes()).hexdigest(),
        selected_metadata_files=len(records),sessions=len({r['session'] for r in records}),
        receivers=sorted({r['receiver'] for r in records}),records=records,observed_fields=fields,
        unique_range_bytes=sum(r['end']-r['start']+1 for r in manifest['ranges']),
        metadata_bytes=sum(r['size_bytes'] for r in records),iq_binary_samples_downloaded=0,
        gates=dict(iq_format='cf32_le: two float32 components, 8 bytes per complex sample',
                   stored_scale='FULL_SCALE_REFERENCE_NOT_ESTABLISHED',receiver_gain='NOT_FOUND_IN_SELECTED_METADATA',
                   agc='NOT_FOUND_IN_SELECTED_METADATA',noise_power='NOT_FOUND_IN_SELECTED_METADATA',
                   dbm_calibration='NOT_ESTABLISHED',antenna_cable_calibration='NOT_FOUND_IN_SELECTED_METADATA',
                   uav_altitude='NOT_FOUND_IN_SELECTED_METADATA',relative_iq_power='COMPUTABLE_IN_STORED_UNITS_IF_IQ_FETCHED',
                   snr='AVAILABLE_BUT_NOISE_AND_ESTIMATOR_VALIDATION_PENDING',multi_site_attack_evaluation='NOT_RUN'),
        limitations=['First positioned CSV row per session/receiver selects metadata; not all files or flight times',
                    '24 selected metadata files do not prove absent fields for the entire dataset',
                    'Member CRC and downloaded-range SHA256 are not a full-archive checksum',
                    'Relative stored IQ energy is neither calibrated dBm nor automatically a defined dBFS measurement',
                    'No assumption of fixed gain, disabled AGC, constant/equal receiver noise floors, or independent truth'],
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',type=Path,required=True);p.add_argument('--csv',type=Path);p.add_argument('--fetch',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Use a fresh output path')
    if a.fetch:
        if a.csv is None:raise ValueError('--csv required for fetch')
        fetch(a.raw,a.csv)
    result=audit(a.raw);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['selected_metadata_files','unique_range_bytes','metadata_bytes','gates']},indent=2))
