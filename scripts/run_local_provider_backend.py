"""Explicit loopback noncommercial research profile; one collector owner.

Start directly; stopping this process stops collection. No scheduled task or
cloud resources are created. Credentials remain server-side environment only.
"""
from pathlib import Path
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
STATE=ROOT/'work/ui-visual-upgrade-20261101/provider-state'
STATE.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('PORTWATCH_AIS_BOUNDING_BOXES','[[[17,71],[20,74]],[[19,85],[22,88]],[[11,79],[14,82]]]')
os.environ.setdefault('PORTWATCH_AIS_RECORD_PATH',str(STATE/'ais/public-recording.jsonl'))
os.environ.update(PORTWATCH_STATE_DIR=str(STATE),PORTWATCH_FREE_SOURCE_DIR=str(STATE/'public_products'),
    PORTWATCH_CURRENT_ENVIRONMENT_DIR=str(STATE/'current_environment'),
    PORTWATCH_PUBLIC_FEEDBACK_DB=str(STATE/'public-feedback.sqlite3'),
    PORTWATCH_WEATHER_FEEDBACK_DB=str(STATE/'public-weather.sqlite3'),
    PORTWATCH_WEATHER_FEEDBACK_REPORT=str(STATE/'public-weather.json'),
    PORTWATCH_LOCAL_PROVIDER_PROFILE='1',PORTWATCH_LICENCE_MODE='DEMO',PORTWATCH_IDENTITY_MODE='verified',
    PORTWATCH_FRESHNESS_SCHEDULER='1',PORTWATCH_PUBLIC_PORT_AUTOREFRESH='1',
    PORTWATCH_PIPELINE_AUTOREFRESH='0',PORTWATCH_WEATHER_RECONCILIATION='1',PORTWATCH_INTELLIGENCE_RECONCILIATION='1',
    PORTWATCH_VESSELFINDER_ENABLED='0',PORTWATCH_PUBLIC_RESEARCH_DIR=str(ROOT/'data/research_release'),
    PORTWATCH_EXPERIMENT_DIR=str(ROOT/'data/research_release/capabilities'))


def main():
    lock=(STATE/'collector-owner.lock').open('a+b')
    if lock.tell()==0: lock.write(b'0');lock.flush()
    lock.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        lock.close();raise SystemExit('This local public state already has a collector owner. No second collector started.')
    from src.portwatch_os.hostperf import opt_out_of_power_throttling
    opt_out_of_power_throttling()
    if os.name=='nt':
        import json
        from scripts.restart_local_provider_backend import process_identity
        owner=process_identity(os.getpid())
        owner.update(script=str(Path(__file__).resolve()),state=str(STATE.resolve()),port=8820)
        (STATE/'collector-owner.json').write_text(json.dumps(owner),encoding='utf-8')
    import uvicorn
    try: uvicorn.run('backend.app.main:app',host='127.0.0.1',port=8820,workers=1)
    finally: lock.close()


if __name__=='__main__': main()
