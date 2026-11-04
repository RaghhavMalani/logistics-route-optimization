"""Daily Paradip context over the canonical public-port archive, never delay.

The read path uses mode=ro SQLite (including committed WAL), never PublicPilot's
initializing constructor. Context parses are separate from prospective cases.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import lru_cache
import copy
import hashlib
import io
import json
import re
import sqlite3

from src.portwatch_os.clock import world_now
from src.portwatch_os.learning.weather_feedback import instant
from .public_ports import IST, PARADIP_INDEX, VERSION as REPORT_PARSER, approved, digest, stamp

FAMILY = 'PARADIP_DAILY_OPERATIONAL_CONTEXT'
PARSER = 'paradip-context-sections-v1.1'
POLICY = 'paradip-daily-context-v1'
BINDING = 'port-context-review-v1'
METRICS = {'WORKING_LISTED_ROWS', 'ANCHORAGE_LISTED_ROWS', 'ANCHORAGE_READY_ROWS', 'ANCHORAGE_NOT_READY_ROWS'}
USE = {'attribution':'Paradip Port Authority', 'scope':'Attributed factual metadata and aggregate metrics; follow the issuer for full report.',
       'policy':'https://paradipport.gov.in/website-policies/', 'fullDocumentDownload':False}


@lru_cache(maxsize=24)
def verified_extraction(raw,parser):
    if parser not in (PARSER,'paradip-context-sections-v1'):raise ValueError('Context parser version is unavailable')
    return extract(raw,strict=parser==PARSER)


def root_path():
    from .operational_quality import _pilot_root
    return _pilot_root()


def extract(raw,strict=True):
    """Read cells by reviewed page regions/baselines, not flattened column order."""
    import pdfplumber
    if not raw.startswith(b'%PDF-') or len(raw)>5_000_000: raise ValueError('Bounded PDF required')
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        if not 3<=len(pdf.pages)<=12: raise ValueError('Unsupported report page layout')
        text=pdf.pages[0].extract_text() or ''
        dates=re.findall(r'HELD ON DT:\s*(\d{2}-\d{2}-\d{4})',text)
        times=re.findall(r'A\. WORKING VESSELS AS ON\s*(\d{2}-\d{2}-\d{4})\s+AT\s+(\d{4})\s+HRS',text)
        previous=re.findall(r'DAILY TRAFFIC UPDATE FOR\s*(\d{2}-\d{2}-\d{4})',text)
        if len(set(dates))!=1 or len(times)!=1 or times[0][0]!=dates[0] or len(previous)!=1:
            raise ValueError('Conflicting or missing section dates')
        day=datetime.strptime(dates[0],'%d-%m-%Y').date()
        before=datetime.strptime(previous[0],'%d-%m-%Y').date()
        if before!=day-timedelta(days=1): raise ValueError('Traffic period conflicts with report date')
        working=datetime.strptime(times[0][0]+' '+times[0][1],'%d-%m-%Y %H%M').replace(tzinfo=IST)
        counts={'working':0,'ready':0,'notReady':0};refs={'working':[],'anchorage':[]};issues=[]
        found_anchor=False
        for page_number,page in enumerate(pdf.pages,1):
            if abs(page.width-841)>2 or abs(page.height-595)>2: raise ValueError('Page geometry changed')
            body=page.extract_text() or ''
            if 'B. VESSELS WAITING AT ANCHORAGE' in body:
                if found_anchor: raise ValueError('Duplicate anchorage section')
                found_anchor=True;status=None;names=set()
                # The category is in the same bounded name/marker band as each
                # row. Repeated vessel names and unreviewed categories withhold
                # all affected aggregate counts rather than guessing alignment.
                for line in page.crop((26,25,230,page.height-45)).extract_text_lines(x_tolerance=2,y_tolerance=2):
                    value=line['text'].strip()
                    if value in ('READY','NOT READY'):status=value;continue
                    if strict and (value.startswith('FOR ') or value=='Others'):status=None;continue
                    if re.match(r'^\d+\s+(?:MV|MT|RV)\.',value):
                        name=re.split(r'\s+(?:GL/|ICT/)?(?:NR|R)$',value)[0]
                        if strict:name=re.sub(r'^\d+\s+','',name)
                        if name in names or status not in ('READY','NOT READY'):
                            issues.append('AMBIGUOUS_ANCHORAGE_CATEGORY_OR_DUPLICATE')
                        names.add(name);counts['ready' if status=='READY' else 'notReady']+=1
                        refs['anchorage'].append({'page':page_number,'row':len(names),'category':status,'nameHash':digest(name)})
                    elif strict and value not in ('B. VESSELS WAITING AT ANCHORAGE','NAME OF THE VESSEL') and not value.startswith('*A-'):
                        issues.append('UNREVIEWED_ANCHORAGE_MARKER_OR_ROW')
                if not names:issues.append('NO_IDENTIFIABLE_ANCHORAGE_ROWS')
            elif page_number<=2:
                names=[]
                for line in page.crop((47,70,184,page.height-15)).extract_text_lines(x_tolerance=2,y_tolerance=2):
                    if re.match(r'^(?:MV|MT|RV)\. ',line['text']):names.append(line['text'])
                counts['working']+=len(names)
                refs['working'].extend({'page':page_number,'row':i+1,'nameHash':digest(name)} for i,name in enumerate(names))
        if not counts['working'] or not found_anchor:raise ValueError('Required section absent')
        date_scope={'date':day.isoformat(),'precision':'DATE_ONLY','timeZoneAssumption':'Asia/Kolkata; not publisher-confirmed',
                    'earliestPossibleAsOf':stamp(datetime.combine(day,datetime.min.time(),IST)),
                    'latestPossibleAsOfExclusive':stamp(datetime.combine(day+timedelta(days=1),datetime.min.time(),IST)),
                    'meaning':'Whole report-date uncertainty bound, not a midnight observation or publication'}
        metrics=[{'id':'WORKING_LISTED_ROWS','value':counts['working'],'unit':'listed vessel rows','section':'A. Working vessels',
                  'asOf':stamp(working),'precision':'MINUTE_ASSUMED_TIMEZONE','rawAsOf':times[0][0]+' '+times[0][1]+' HRS',
                  'pages':sorted({r['page'] for r in refs['working']}),'rowReferences':refs['working'],
                  'meaning':'Rows listed in the working section, including completed/departed entries; not active berth occupancy or available capacity.'}]
        for key,value,label in [('ANCHORAGE_LISTED_ROWS',counts['ready']+counts['notReady'],'Listed anchorage rows'),('ANCHORAGE_READY_ROWS',counts['ready'],'Rows under READY headings'),('ANCHORAGE_NOT_READY_ROWS',counts['notReady'],'Rows under NOT READY headings')]:
            metrics.append({'id':key,'value':None if issues else value,'unit':'listed vessel rows','section':'B. Vessels waiting at anchorage',
                            'dateScope':date_scope,'precision':'DATE_ONLY','pages':sorted({r['page'] for r in refs['anchorage']}),
                            'rowReferences':refs['anchorage'],'meaning':label+'; no individual wait, congestion forecast or readiness guarantee.'})
        return {'portCode':'INPRT','reportDate':day.isoformat(),'publicationAt':None,'publicationPrecision':'UNKNOWN',
                'priorDayTrafficDate':before.isoformat(),'parserVersion':PARSER if strict else 'paradip-context-sections-v1','reportParserVersion':REPORT_PARSER,'metrics':metrics,'issues':issues,
                'scheduledSections':'Expected-vessel and movement rows remain programmes, not observed arrivals or clearances.', 'sourceUse':USE}


@contextmanager
def archive(root=None):
    root=Path(root) if root is not None else root_path();path=root/'public_ports.db'
    if not path.is_file():yield None;return
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:yield db
    finally:db.close()


def retained(*,root=None,as_of=None):
    try:return _retained(root=root,as_of=as_of)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,sqlite3.Error):
        return {'sourceFamily':FAMILY,'policyVersion':POLICY,'status':'UNAVAILABLE','metrics':[],
                'sourceUse':USE,'reason':'Retained source metadata could not be qualified; earlier comparisons remain inspectable.'}


def _retained(*,root=None,as_of=None):
    at=world_now() if as_of is None else instant(as_of);root=Path(root) if root is not None else root_path()
    empty={'sourceFamily':FAMILY,'policyVersion':POLICY,'asOf':stamp(at),'status':'UNAVAILABLE','metrics':[],
           'sourceUse':USE,'reason':'No qualified retained context parse; explicit collection is required.','realOperationalTargetsResolved':0}
    with archive(root) as db:
        if db is None:return empty
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='operational_contexts'").fetchone():return empty
        rows=db.execute('SELECT c.at AS context_at,c.body AS context_body,s.* FROM operational_contexts c JOIN snapshots s ON c.snapshot=s.id WHERE s.port=? AND c.at<=? AND s.first_seen<=? ORDER BY s.report_date,c.at,s.id',('INPRT',stamp(at),stamp(at))).fetchall()
        if not rows:return empty
        checks=[dict(r) for r in db.execute('SELECT at,body FROM checks WHERE port=? AND at<=? ORDER BY at,id',('INPRT',stamp(at)))]
        latest_date=max(r['report_date'] for r in rows)
        lineage=[];conflict=False
        for check in checks:
            check_body=json.loads(check['body'])
            if check_body.get('errors'):continue
            ids={r.get('snapshotId') for r in check_body.get('results',[]) if isinstance(r,dict)}
            candidates=[r for r in rows if r['id'] in ids and r['report_date']==latest_date and r['context_at']<=check['at']]
            if len({r['id'] for r in candidates})>1:conflict=True;continue
            if not candidates:continue
            selected=max(candidates,key=lambda r:r['context_at']);body=json.loads(selected['context_body'])
            identity=digest(json.dumps([selected['id'],body.get('parserVersion')],sort_keys=True))
            if not lineage or lineage[-1]['identity']!=identity:
                lineage.append({'identity':identity,'revisionId':digest(json.dumps([identity,lineage[-1]['revisionId'] if lineage else None,check['at']])),
                    'availableAt':check['at'],'snapshot':selected})
            conflict=False
        selected=lineage[-1]['snapshot'] if lineage else rows[-1]
        body=json.loads(selected['context_body']);sha=selected['sha']
        if not approved(selected['url']) or selected['port']!='INPRT' or not re.fullmatch(r'[0-9a-f]{64}',sha):return {**empty,'reason':'Invalid retained source identity'}
        original=root/'evidence'/(sha+'.pdf')
        try:
            raw=original.read_bytes();verified=digest(raw)==sha and verified_extraction(raw,body['parserVersion'])==body
        except (OSError,ValueError,KeyError):verified=False
        last=checks[-1] if checks else None
        success=[r for r in checks if not json.loads(r['body']).get('errors') and any(v.get('snapshotId')==selected['id'] and v.get('contextStatus')!='UNSUPPORTED_LAYOUT_OR_SCOPE' for v in json.loads(r['body']).get('results',[]))]
        checked=success[-1]['at'] if success else None
        status='CURRENT_ELIGIBLE';reason=[]
        if not verified:status='UNAVAILABLE';reason.append('Original missing or corrupt')
        if not checked or at-instant(checked)>timedelta(hours=6):status='LATEST_AVAILABLE';reason.append('No successful selected-product check within six hours')
        if last and json.loads(last['body']).get('errors'):status='RETAINED_AFTER_FAILURE';reason.append('Latest refresh failed; previous evidence retained')
        if last and not json.loads(last['body']).get('errors'):
            received=json.loads(last['body']).get('results',[])
            if any(v.get('contextStatus')=='UNSUPPORTED_LAYOUT_OR_SCOPE' for v in received) or (received and not any(v.get('snapshotId')==selected['id'] for v in received)):
                status='RETAINED_AFTER_UNSUPPORTED_PARSE';reason.append('Latest collected product has no qualified section parse; prior context is retained without active eligibility')
        if conflict:status='AMBIGUOUS';reason.append('One received check contains conflicting same-date products')
        age=(at.astimezone(IST).date()-datetime.fromisoformat(body['reportDate']).date()).days
        if age not in (0,1):status='LATEST_AVAILABLE';reason.append('Report is outside current/previous local calendar day')
        metrics=copy.deepcopy(body['metrics'])
        for metric in metrics:
            earliest=instant(metric['asOf']) if metric.get('asOf') else instant(metric['dateScope']['earliestPossibleAsOf'])
            metric['oldestPossibleAgeHours']=(at-earliest).total_seconds()/3600
            metric['eligibility']='CURRENT_ELIGIBLE' if status=='CURRENT_ELIGIBLE' and metric['value'] is not None and 0<=metric['oldestPossibleAgeHours']<=36 else 'LATEST_AVAILABLE'
            metric['calculationEffect']='NONE; operator review criterion only, never delay or capacity'
        if not any(m['eligibility']=='CURRENT_ELIGIBLE' for m in metrics) and status=='CURRENT_ELIGIBLE':status='LATEST_AVAILABLE';reason.append('All section age/coverage limits failed')
        revision=lineage[-1]['revisionId'] if lineage else digest(json.dumps([selected['id'],selected['parser'],body],sort_keys=True))
        return {**empty,**body,'status':status,'reason':'; '.join(reason) or 'Qualified daily context at this query time; not live operations',
                'snapshotId':selected['id'],'revisionId':revision,'source':selected['url'],'catalogueSource':PARADIP_INDEX,'originalSha256':sha,
                'firstReceivedAt':selected['first_seen'],'availableAt':lineage[-1]['availableAt'] if lineage else selected['context_at'],'parserAvailableAt':selected['context_at'],'checkedAt':last['at'] if last else None,
                'previousRevisionId':lineage[-2]['revisionId'] if len(lineage)>1 else None,
                'lastSuccessfulCheckAt':checked,'originalStatus':'HASH_VERIFIED' if verified else 'UNAVAILABLE','metrics':metrics,'latestAvailable':True,
                'publicationAt':None,'privatePathExposed':False,'fullDocumentDownload':False}
