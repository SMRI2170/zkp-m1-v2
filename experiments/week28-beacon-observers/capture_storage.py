#!/usr/bin/env python3
"""Private per-invocation capture sessions. Never delete or silently roll over data."""
from datetime import datetime,timezone
import json
import fcntl
import os
from pathlib import Path
import shutil
import time
import uuid

MIB=1024**2
MIN_FREE=1024*MIB
BUDGETS={'receiver':1024*MIB,'sensors':1024*MIB,'transmitter':512*MIB}
class StorageLimit(RuntimeError):
    """Exit 78: operator intervention or a new boot/session is required."""

def private_directory(path,anchor):
    path=Path(os.path.abspath(path));anchor=Path(os.path.abspath(anchor))
    if not path.is_relative_to(anchor):raise ValueError('output outside capture root')
    for p in reversed([path,*path.parents]):
        if p==anchor or p.is_relative_to(anchor):
            if p.is_symlink():raise ValueError('capture symlink rejected')
            p.mkdir(mode=0o700,exist_ok=True)
            st=p.stat()
            if st.st_uid!=os.getuid() or st.st_mode&0o077:raise ValueError('owner-private capture directory required')
    return path

def atomic_status(path,data):
    path=Path(path)
    if path.is_symlink():raise ValueError('status symlink rejected')
    temp=path.with_name('.'+path.name+'-'+uuid.uuid4().hex)
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(data,f,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    temp.replace(path)

def usage(path):
    size=count=0
    for p in Path(path).rglob('*'):
        if p.is_symlink():raise ValueError('symlink in current session')
        if p.is_file():size+=p.stat().st_size;count+=1
    return size,count

def limit_reason(used,files,free,budget,reserve=0):
    if free<MIN_FREE+reserve:return 'DISK_HEADROOM_LOW'
    if used+reserve>budget:return 'SESSION_BUDGET_REACHED'
    if files>=10000:return 'SESSION_FILE_BUDGET_REACHED'
    return None

def boot_id():
    try:
        b=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return str(uuid.UUID(b))
    except (OSError,ValueError):return 'unknown'

class CaptureSession:
    def __init__(self,base,anchor,role,*,budget=None,boot=None,free_fn=shutil.disk_usage,clock=time.monotonic):
        if role not in BUDGETS:raise ValueError('unknown capture role')
        self.base=private_directory(base,anchor);self.role=role
        self.budget=BUDGETS[role] if budget is None else budget
        if not isinstance(self.budget,int) or self.budget<64*MIB:raise ValueError('bounded capture budget required')
        fd=os.open(self.base/'.writer.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        st=os.fstat(fd)
        if st.st_uid!=os.getuid() or st.st_mode&0o077:os.close(fd);raise ValueError('private writer lock required')
        self.lock=os.fdopen(fd,'a+')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:self.lock.close();raise ValueError('capture role already running')
        self.free_fn=free_fn;self.clock=clock;self.boot=boot_id() if boot is None else boot
        self.id=uuid.uuid4().hex;self.started=clock();self.last_emit=-float('inf');self.records=0;self.last_record=None;self.last_used=0;self.last_files=0
        self.path=private_directory(self.base/'sessions'/self.id,anchor)
        self.status_path=self.base/'storage-status.json'
        self.status('STARTING')
        atomic_status(self.path/'session.json',{'schema':'capture_session_v1','session_id':self.id,'role':role,'boot_id':self.boot,'created_utc':datetime.now(timezone.utc).isoformat(),'created_monotonic_s':self.started,'byte_budget':self.budget,'minimum_disk_free_bytes':MIN_FREE,'auto_delete':False})
    def status(self,state,**extra):
        atomic_status(self.status_path,dict(schema='capture_storage_status_v1',role=self.role,session_id=self.id,boot_id=self.boot,state=state,updated_utc=datetime.now(timezone.utc).isoformat(),updated_monotonic_s=self.clock(),records_written=self.records,last_record_monotonic_s=self.last_record,session_bytes=self.last_used,session_files=self.last_files,byte_budget=self.budget,minimum_disk_free_bytes=MIN_FREE,**extra))
        self.last_emit=self.clock()
    def check(self,reserve=0):
        self.last_used,self.last_files=usage(self.path)
        free=self.free_fn(self.path).free
        reason=limit_reason(self.last_used,self.last_files,free,self.budget,reserve)
        if reason:
            self.status(reason,disk_free_bytes=free);raise StorageLimit(reason)
        self.status('CAPTURE_ACTIVE',disk_free_bytes=free)
    def progress(self,records,*,force=False):
        if records>self.records:self.last_record=self.clock()
        self.records=records
        if force or self.clock()-self.last_emit>=2:self.status('CAPTURE_ACTIVE')
    def finish(self,state='STOPPED',**extra):
        self.last_used,self.last_files=usage(self.path);self.status(state,**extra)
    def close(self):
        if not self.lock.closed:fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close()
