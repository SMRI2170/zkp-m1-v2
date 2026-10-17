"""Recover only allowlisted metrics over one SSH connection, never proof fixtures."""
import argparse,hashlib,json,os,shlex,shutil,subprocess,sys,zipfile
from pathlib import Path
import pi
FILES=['benchmark.jsonl','memory.jsonl','resource.json','filesystem-audit.json','metadata.json']
def extract(archive,out,tag):
 allowed={tag+'-'+name+'/'+file for name in pi.TRIALS for file in FILES}
 with zipfile.ZipFile(archive) as z:
  names=z.namelist()
  if len(names)!=len(set(names)) or not set(names)<=allowed:raise ValueError('Unexpected/duplicate archive member')
  if z.testzip() is not None:raise ValueError('Archive CRC mismatch')
  for name in names:
   target=out/name;target.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
   with z.open(name) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
 return names

def main():
 p=argparse.ArgumentParser();p.add_argument('--job',type=Path,required=True);p.add_argument('--tag',required=True);a=p.parse_args();os.umask(0o077)
 if not a.tag.isascii() or not a.tag.replace('-','').isalnum():p.error('invalid tag')
 archive=a.job/'private/metrics-bundle.zip.part'
 script='''from pathlib import Path
import sys,zipfile,json
base=Path('/home/pi/.cache/week24/runs')
tag=TAG
trials=TRIALS
files=FILES
with zipfile.ZipFile(sys.stdout.buffer,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for name in trials:
  run=base/(tag+'-'+name)
  if run.is_symlink() or not run.is_dir():continue
  for file in files:
   p=run/file
   if p.is_file() and not p.is_symlink():z.write(p,arcname=run.name+'/'+file)
'''.replace('TAG',repr(a.tag)).replace('TRIALS',repr(pi.TRIALS)).replace('FILES',repr(FILES))
 opts,env,target=pi.transport();result={'proof_relaunched':False,'transport_connections':1,'status':'failed'}
 try:
  with archive.open('xb') as output,(a.job/'private/bundle-ssh.log').open('xb') as err:
   r=subprocess.run(['ssh',*opts,target,shlex.join(['python3','-c',script])],env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=err,timeout=120)
  result['ssh_exit_code']=r.returncode
  if r.returncode==0:
   names=extract(archive,a.job/'pi-runs',a.tag)
   result.update(status='completed' if names else 'blocked',files_collected=names,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
 except (OSError,ValueError,zipfile.BadZipFile,subprocess.TimeoutExpired) as e:result['reason']=type(e).__name__
 (a.job/'bundle-status.json').write_text(json.dumps(result,indent=2)+'\n')
 return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
