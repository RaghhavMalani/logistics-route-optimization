"""Restart only the recorded, verified local provider process. Windows utility."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'work/ui-visual-upgrade-20261101/provider-state'
ENTRY=ROOT/'scripts/run_local_provider_backend.py'
OWNER=STATE/'collector-owner.json'


def process_identity(pid,terminate=False):
    if os.name!='nt': raise RuntimeError('This checked local restart utility requires Windows')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    handle=kernel.OpenProcess(0x1000|(0x100001 if terminate else 0),False,pid)
    if not handle: raise RuntimeError('Recorded process cannot be opened; no process was stopped')
    try:
        name=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(name))
        if not kernel.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)): raise RuntimeError('Cannot verify executable')
        created,exited,system,user=(wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle,*map(ctypes.byref,(created,exited,system,user))): raise RuntimeError('Cannot verify creation time')
        result={'pid':pid,'executable':str(Path(name.value).resolve()),'creationTicks':str((created.dwHighDateTime<<32)|created.dwLowDateTime)}
        if terminate: return kernel,handle,result
        return result
    finally:
        if not terminate: kernel.CloseHandle(handle)


def main():
    owner=json.loads(OWNER.read_text())
    if Path(owner['script']).resolve()!=ENTRY.resolve() or owner.get('port')!=8820 or Path(owner['state']).resolve()!=STATE.resolve(): raise RuntimeError('Owner record is not this repository local profile')
    kernel,handle,current=process_identity(int(owner['pid']),terminate=True)
    try:
        if current!={k:owner[k] for k in ('pid','executable','creationTicks')}: raise RuntimeError('Process identity changed; no process was stopped')
        kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT];kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        if not kernel.TerminateProcess(handle,0): raise RuntimeError('Verified process could not be stopped')
        if kernel.WaitForSingleObject(handle,10000)!=0: raise RuntimeError('Verified process did not stop')
    finally: kernel.CloseHandle(handle)
    environment=os.environ.copy();environment['PYTHONPATH']=str(ROOT/'work/india-pilot-20261016/python-deps')+';'+str(ROOT)
    with (STATE.parent/'provider-recovery.stdout.log').open('ab') as stdout,(STATE.parent/'provider-recovery.stderr.log').open('ab') as stderr:
        child=subprocess.Popen([sys.executable,'-u',str(ENTRY)],cwd=ROOT,env=environment,creationflags=subprocess.CREATE_NO_WINDOW,stdout=stdout,stderr=stderr)
    print('Verified local provider restarted',current['pid'],'->',child.pid,'; durable state retained')


if __name__=='__main__': main()
