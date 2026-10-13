"""Reviewed Peel Ports restrictions, immutable originals and separate receipts.

Only MNTM 2026-18 has a supported operational parser. Construction text alone
never becomes a closure; unsupported revisions and provider failures block.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import io
import json
import re
import threading
from urllib.parse import urljoin, urlparse
import requests
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from src.portwatch_os.clock import wall_now
from src.portwatch_os.intelligence.current_environment import ROOT, instant

SOURCE='https://www.peelports.com/marine/'
PDF='https://www.peelports.com/media/joolgbfb/mntm-2026-18-temporary-closures-of-eastham-80-lock.pdf'
LOCK=threading.RLock(); STOP=threading.Event(); THREAD=None; TTL=timedelta(hours=6)


def parse_eastham(raw):
    text=' '.join(' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(raw)).pages).split())
    if not re.search(r'№\s*18\s*[–-]\s*2026',text): raise ValueError('Unsupported notice reference')
    if not all(x in text for x in ('NOTICE TO MARINERS','18','2026','HARBOUR AND PORT OF MANCHESTER','EASTHAM')): raise ValueError('Unsupported authority notice')
    if re.search(r'(?:this notice (?:has been|is)|notice status[: ]*)\s*(?:withdrawn|cancelled|canceled)',text,re.I): return {'noticeRef':'MNTM 2026-18','status':'CANCELLED','windows':[]}
    if not all(x in text.lower() for x in ('closed to vessel movements','first operational tide','these works do not affect the queen elizabeth ii lock')): raise ValueError('Explicit restriction or unaffected alternative changed; review required')
    rows=re.findall(r'(\d{1,2} \w+ 2026) until (\d{1,2} \w+ 2026).*?Last operational tide:\s*(\d{2}\.\d{2})\s*\((BST|GMT)\) HW on (\d{1,2} \w+ 2026).*?First operational tide:\s*(\d{2}\.\d{2})\s*\((BST|GMT)\) HW on (\d{1,2} \w+ 2026)',text)
    if len(rows)!=3: raise ValueError('Expected three explicit closure periods and operational tides')
    def day(value): return datetime.strptime(value,'%d %B %Y')
    def tide(date,time,zone): return datetime.combine(day(date).date(),datetime.strptime(time,'%H.%M').time(),timezone(timedelta(hours=1 if zone=='BST' else 0)))
    windows=[]
    for start,end,last,zone,last_day,first,first_zone,first_day in rows:
        access=tide(first_day,first,first_zone)
        windows.append({'start':day(start).replace(tzinfo=ZoneInfo('Europe/London')).astimezone(timezone.utc).isoformat(),'end':access.astimezone(timezone.utc).isoformat(),
            'closureStartDate':day(start).date().isoformat(),'closureEndDate':day(end).date().isoformat(),
            'localDate':day(first_day).date().isoformat(),'localEnd':first,'timeZone':first_zone,
            'lastOperationalTide':tide(last_day,last,zone).astimezone(timezone.utc).isoformat(),'firstOperationalTide':access.astimezone(timezone.utc).isoformat(),
            'startPrecision':'DATE_ONLY; midnight normalization is not a stated exact work-start time',
            'accessBasis':'First published operational high-water tide; actual lock slot/reopening is not measured'})
    published=re.search(r'MOM/[^ ]+\s+(\d{1,2} \w+ 2026)',text)
    withdrawal=re.search(r'withdrawn at (\d{2}\.\d{2})\s*\((BST|GMT)\) on (\d{1,2} \w+ 2026)',text)
    if not published or not withdrawal: raise ValueError('Publication or withdrawal time missing')
    withdraw_at=tide(withdrawal[3],withdrawal[1],withdrawal[2]).astimezone(timezone.utc).isoformat()
    for window in windows:
        window['calculationSupported']=instant(window['end'])<=instant(withdraw_at)
        if not window['calculationSupported']: window['reason']='Published withdrawal time precedes first operational tide; authority clarification required'
    return {'noticeRef':'MNTM 2026-18','title':'Eastham 80-foot Lock scheduled closure','status':'SCHEDULED',
        'publishedDate':day(published[1]).date().isoformat(),'withdrawsAt':withdraw_at,'effectiveFrom':windows[0]['closureStartDate'],
        'effectiveThrough':day(withdrawal[3]).date().isoformat(),'windows':windows,'areaId':'EASTHAM_80_LOCK','area':'Eastham 80-foot Lock, Manchester Ship Canal',
        'applicability':{'vesselScope':'ALL_VESSELS_USING_THIS_LOCK','directions':['INBOUND','OUTBOUND'],
            'characteristicRule':'Closure applies to this declared lock route regardless of vessel size; suitability of this vessel for the lock remains unverified.'},
        'restriction':'Eastham 80-foot Lock closed to vessel movements during the published periods.',
        'unaffectedAlternative':'Queen Elizabeth II Lock is explicitly unaffected; its availability, suitability and booking for this voyage are not supplied.',
        'confirmation':'First published operational tide is a conditional planning point, not a confirmed slot, actual reopening or navigation clearance.',
        'mechanism':'A declared passage using the closed lock overlaps the published closure; compare waiting with requesting the first published operational tide.',
        'calculationScope':'Scheduled lock route only; no closure of the entire canal, berth, clearance, alternate-lock, fuel, cost or safety benefit.'}


def _retain(root,raw):
    digest=hashlib.sha256(raw).hexdigest();path=root/(digest+'.response')
    if not path.exists(): path.write_bytes(raw)
    return digest


def refresh(force=False):
    with LOCK:
        root=ROOT/'operational_notices';root.mkdir(parents=True,exist_ok=True)
        pointer=root/'eastham-2026-18-latest.json';old=json.loads(pointer.read_text()) if pointer.exists() else None
        if old and not force and wall_now()-instant(old['checkedAt'])<TTL: return old
        hashes={};pdf_url=PDF
        try:
            response=requests.get(SOURCE,timeout=(5,20));response.raise_for_status();hashes['responseSha256']=_retain(root,response.content)
            links=re.findall(r'href=[\"\']([^\"\']+)[\"\']',response.text)
            matches=[urljoin(SOURCE,x) for x in links if re.search(r'mntm[-_]2026[-_]18.*eastham.*lock.*\.pdf',x,re.I)]
            if len(set(matches))!=1: raise ValueError('Supported notice link absent or ambiguous; authority review required')
            pdf_url=matches[0]
            if urlparse(pdf_url).hostname!='www.peelports.com': raise ValueError('Unsupported publisher host')
            pdf=requests.get(pdf_url,timeout=(5,20));pdf.raise_for_status()
            if not pdf.content.startswith(b'%PDF-'): raise ValueError('Original PDF unavailable')
            hashes['pdfSha256']=_retain(root,pdf.content);facts=parse_eastham(pdf.content);received=wall_now().isoformat()
            revision=hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest();path=root/(revision+'.json')
            if not path.exists():
                body={**facts,'id':revision,'revisionId':revision,'previousRevisionId':old.get('revisionId') if old else None,
                    'issuer':'Manchester Ship Canal Company / Peel Ports','source':SOURCE,'pdfSource':pdf_url,**hashes,'availableAt':received,
                    'publicationPrecision':'DATE_ONLY','availabilityBasis':'First successful PortWatch receipt of this parsed restriction revision'}
                path.write_text(json.dumps(body,indent=2))
            latest={**json.loads(path.read_text()),'checkedAt':received,'latestResponseSha256':hashes['responseSha256'],
                'latestPdfSha256':hashes['pdfSha256'],'sourceStatus':'CURRENT','reason':None}
        except (requests.RequestException,ValueError,KeyError,OSError,PdfReadError) as exc:
            latest={**(old or {'noticeRef':'MNTM 2026-18','source':SOURCE,'pdfSource':pdf_url,'windows':[]}),
                'sourceStatus':'UNAVAILABLE','checkedAt':wall_now().isoformat(),'reason':str(exc)[:180],'failedReceiptHashes':hashes}
        with (root/'receipts.jsonl').open('a') as stream:
            stream.write(json.dumps({'receivedAt':latest['checkedAt'],'revisionId':latest.get('revisionId'),**hashes,
                'url':SOURCE,'pdfUrl':pdf_url,'sourceStatus':latest['sourceStatus'],'reason':latest.get('reason')})+'\n')
        temporary=pointer.with_suffix('.tmp');temporary.write_text(json.dumps(latest,indent=2));temporary.replace(pointer)
        return latest


def require_revision(basis):
    latest=refresh()
    if latest.get('sourceStatus')!='CURRENT' or latest.get('status')!='SCHEDULED': raise ValueError('Authority restriction unavailable, withdrawn or cancelled; further action blocked')
    if latest.get('revisionId')!=basis['restriction']['revisionId']: raise ValueError('Authority restriction revised; explicitly refresh to a linked comparison')
    if instant(latest['checkedAt'])+TTL<wall_now(): raise ValueError('Authority receipt expired')
    if wall_now()>=instant(latest['withdrawsAt']): raise ValueError('Authority notice withdrawn by its published effective time')
    root=ROOT/'operational_notices'
    for key in ('responseSha256','pdfSha256'):
        digest=basis['reportedFact'][key];path=root/(digest+'.response')
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise ValueError('Original authority evidence unavailable or corrupt')
    return latest


def planned_consequence(notice,plan):
    if notice.get('sourceStatus')!='CURRENT' or notice.get('status')!='SCHEDULED': raise ValueError('Current reviewed restriction required')
    if plan['areaId']!=notice['areaId'] or plan['direction'] not in notice['applicability']['directions']: raise ValueError('Declared passage does not match restricted lock/direction')
    if plan['alternativeAccess']!='NOT_VERIFIED': raise ValueError('Alternate-lock access needs separate suitability and booking evidence')
    requested=instant(plan['passageAt']);window=next((w for w in notice['windows'] if instant(w['start'])<=requested<instant(w['end'])),None)
    if not window: raise ValueError('Declared passage does not overlap an explicit closure period; no delay asserted')
    if not window['calculationSupported']: raise ValueError(window['reason'])
    wait=(instant(window['end'])-requested).total_seconds()/3600
    return {'window':window,'requestedPassage':requested.isoformat(),'earliestScheduledAccess':window['end'],'actualEarliestPermittedAccess':None,
        'calculatedWaitHours':wait,'totalScheduleShiftHours':wait,'status':'CONDITIONAL_SCHEDULE_CALCULATION','condition':notice['confirmation']}


def start():
    global THREAD
    if THREAD and THREAD.is_alive(): return
    STOP.clear()
    def run():
        while not STOP.is_set():
            try: refresh()
            except Exception: pass
            STOP.wait(TTL.total_seconds())
    THREAD=threading.Thread(target=run,name='authority-notices',daemon=True);THREAD.start()


def stop(): STOP.set()
