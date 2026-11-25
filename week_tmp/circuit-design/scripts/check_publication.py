#!/usr/bin/env python3
"""Defense-in-depth publication check; does not replace manual privacy review."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BLOCK_EXT={'.pk','.vk','.proof','.ptau','.zkey','.wtns','.r1cs','.jsonl','.sqlite','.db','.pem','.key'}
BLOCK_KEYS={'private_key','session_key','proof_hex','proof_bytes','witness_hex','odid_payload_hex','raw_vendor_ie_hex','received_at_utc','receiver_latitude','receiver_longitude','claimed_latitude','claimed_longitude'}
def check(root):
 problems=[]
 def inspect(obj,path=''):
  if isinstance(obj,dict):
   for k,v in obj.items():
    if k.lower() in BLOCK_KEYS:problems.append('raw/private JSON field: '+path+'/'+k)
    if k.lower() in {'latitude','longitude'} and not ((path.endswith('/fix_nonnull') or path.endswith('/target_nonnull')) and isinstance(v,int) and not isinstance(v,bool) and v>=0):problems.append('coordinate field: '+path+'/'+k)
    inspect(v,path+'/'+k)
  elif isinstance(obj,list):
   for v in obj:inspect(v,path+'[]')
 for f in root.rglob('*'):
  if not f.is_file() or '__pycache__' in f.parts or 'ci-results' in f.parts:continue
  rel=str(f.relative_to(root));name=f.name.lower()
  if f.is_symlink() or f.suffix.lower() in BLOCK_EXT or name in {'ledger.json','.lock'} or '.pending-' in name or '-private.' in name or '_private.' in name or name.endswith(('.db-wal','.db-shm','.sqlite-wal','.sqlite-shm')) or 'captures' in f.relative_to(root).parts:problems.append('forbidden artifact: '+rel)
  if f.suffix=='.json':
   try:inspect(json.loads(f.read_text()),rel)
   except (UnicodeError,json.JSONDecodeError):problems.append('invalid public JSON: '+rel)
  if f.suffix in {'.md','.go','.py','.json','.log'}:
   text=f.read_text()
   if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',text):problems.append('private key marker: '+rel)
 return problems
if __name__=='__main__':
 problems=check(ROOT)
 if problems:print('\n'.join(problems));raise SystemExit(1)
 print('Publication artifact guard passed; manual field-data review is also required.')
