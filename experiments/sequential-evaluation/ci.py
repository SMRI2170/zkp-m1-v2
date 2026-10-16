"""Review CI in the background job, never by keeping a chat turn waiting."""
import argparse,csv,json,subprocess,time
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--job',type=Path,required=True);a=p.parse_args()
 commit=json.loads((a.job/'status.json').read_text())['source_commit'];deadline=time.monotonic()+600
 commits=[commit,*json.loads((a.job/'plan.json').read_text()).get('related_ci_commits',[])]
 while True:
  rows=[]
  missing=False
  for sha in commits:
   r=subprocess.run(['gh','run','list','--commit',sha,'--limit','30','--json','databaseId,name,status,conclusion,url,headSha'],text=True,capture_output=True,timeout=30)
   if r.returncode:
    (a.job/'ci-results.json').write_text(json.dumps({'status':'blocked','reason':'GitHub CLI lookup failed'})+'\n');return 3
   found=json.loads(r.stdout);missing|=not bool(found);rows+=found
  (a.job/'ci-results.json').write_text(json.dumps({'source_commit':commit,'runs':rows},indent=2)+'\n')
  with (a.job/'ci-results.csv').open('w',newline='') as f:
   fields=['databaseId','name','status','conclusion','url','headSha'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
  if rows and not missing and all(x['status']=='completed' for x in rows):
   failed=False
   for x in rows:
    # Keep exact logs privately for review; public tables contain only statuses/links.
    with (a.job/'private'/('ci-'+str(x['databaseId'])+'.log')).open('w') as log:
     logs=subprocess.run(['gh','run','view',str(x['databaseId']),'--log'],stdout=log,stderr=subprocess.STDOUT,timeout=60)
    failed|=x['conclusion']!='success' or logs.returncode!=0
   return 1 if failed else 0
  if time.monotonic()>=deadline:return 3
  time.sleep(20)
if __name__=='__main__':raise SystemExit(main())
