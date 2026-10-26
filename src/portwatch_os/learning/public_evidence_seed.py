"""Opt-in, additive import of a reviewed public-only preview evidence manifest.

The manifest is a server configuration, never an HTTP upload. Validate its full
file set and public row semantics before creating or changing durable resources.
Source clocks and IDs remain unchanged; import time is a separate audit record.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3


VERSION = 'public-preview-seed-v1'
HEX = re.compile(r'^[a-f0-9]{64}$')
FEEDBACK_KINDS = frozenset({'claim','evidence','assessment','match','economic-qualification',
    'economic-source-check','economic-missing-observation','missing-date','navigation-source-version',
    'news-source-quality','receipt','receipt-check','reviewed-news-source-check','run','version'})
DATABASES = {
    'feedback/public_feedback.sqlite3': ('feedback', {'shared_feedback','predictions'}),
    'weather/public_weather_forecasts.sqlite3': ('weather', {'predictions','weather_outcome_evidence',
        'weather_forecast_annotations','weather_correction_versions'}),
    'public_port_pilot/public_ports.db': ('ports', {'snapshots','cases','checks','parses','cohorts','cohort_cases','collections'}),
}
PORT_COLUMNS = {'snapshots': ('id','port','kind','sha','url','first_seen','report_date','parser','body'),
    'cases': ('id','port','issued','body'), 'checks': ('id','port','at','actor','body'),
    'parses': ('snapshot','parser','at','body'), 'cohorts': ('id','port','created','body'),
    'cohort_cases': ('cohort','case_id','at'), 'collections': ('id','port','at','body')}
KEYS = {'shared_feedback': ('kind','id'), 'predictions': ('prediction_id',),
    'weather_outcome_evidence': ('id',), 'weather_forecast_annotations': ('id',),
    'weather_correction_versions': ('id',), 'parses': ('snapshot','parser'),
    'cohort_cases': ('case_id',), **{t:('id',) for t in PORT_COLUMNS if t not in ('parses','cohort_cases')}}
OUTCOME_FIELDS = frozenset({'status','observed_value','observed_at','observation_source','error',
    'absolute_error','brier','log_loss','within_interval','lead_time_hours'})
PRIVATE_FIELDS = frozenset({'accessToken','refreshToken','password','password_hash','token_hash',
    'sessionId','visitorId','authorization','signingKey','privateKey','operationalEpisode','namespace',
    'apiKey','clientSecret','cookie','setCookie','secretKey','credentials'})
PRIVATE_KEYS = frozenset(re.sub(r'[_-]','',key).casefold() for key in PRIVATE_FIELDS)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))


def _instant(value):
    at=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if at.tzinfo is None:raise ValueError('Public evidence clocks require an explicit timezone')
    return at.astimezone(timezone.utc)


def _public_body(value):
    if isinstance(value,dict):
        if any(re.sub(r'[_-]','',str(key)).casefold() in PRIVATE_KEYS for key in value):
            raise ValueError('Private identity, credentials or operational scope in public seed')
        for nested in value.values():_public_body(nested)
    elif isinstance(value,list):
        for nested in value:_public_body(nested)


def _relative(name):
    path=PurePosixPath(name)
    if not isinstance(name,str) or '\\' in name or path.is_absolute() or '..' in path.parts or str(path)!=name:
        raise ValueError('Seed paths must be normalized relative public paths')
    if name in DATABASES:return path
    if len(path.parts)==3 and path.parts[:2]==('public_port_pilot','evidence'):
        if re.fullmatch(r'[a-f0-9]{64}\.pdf',path.name):return path
    if path.parts and path.parts[0]=='current_environment':
        if len(path.parts)==2 and (path.name=='hazards.json' or re.fullmatch(r'(surface|marine)-[A-Z0-9]{5}\.json',path.name)):
            return path
        if len(path.parts)==3 and path.parts[1] in {'archive','outcomes','shared_feedback','operational_notices','shipping_intelligence'}:
            if re.fullmatch(r'[a-f0-9]{64}\.(response|json)',path.name):return path
            if path.parts[1]=='operational_notices' and path.name in {'eastham-2026-18-latest.json','navcen-catalogue-latest.json'}:
                return path
    raise ValueError('Seed file is outside the public evidence allowlist')


def _source_rows(path,tables):
    connection=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    try:
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('BEGIN')
        definitions=connection.execute("SELECT name,type,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type IN ('table','view','trigger')").fetchall()
        if {r['name'] for r in definitions} != tables or any(r['type']!='table' or 'VIRTUAL' in r['sql'].upper() for r in definitions):
            raise ValueError('Seed database contains an unapproved table, view or trigger')
        return {table:[dict(row) for row in connection.execute('SELECT * FROM "'+table+'"')] for table in sorted(tables)}
    finally:connection.close()


def _validate_records(groups):
    from src.portwatch_os.ledger.store import _SCHEMA
    schema=sqlite3.connect(':memory:');schema.executescript(_SCHEMA)
    expected={table:tuple(r[1] for r in schema.execute('PRAGMA table_info("'+table+'")')) for table in ('shared_feedback','predictions')}
    schema.close()
    expected.update(PORT_COLUMNS)
    expected.update(weather_outcome_evidence=('id','body'),weather_forecast_annotations=('id','body'),
        weather_correction_versions=('id','cohort','body'))
    for tables in groups.values():
        for table,rows in tables.items():
            if any(tuple(row)!=expected[table] for row in rows):raise ValueError('Seed column contract differs from the application')
            keys=[tuple(row[k] for k in KEYS[table]) for row in rows]
            if len(set(keys))!=len(keys):raise ValueError('Duplicate immutable identities in public seed')
            for row in rows:
                for field in ('body','context','features','contributions','provenance'):
                    if row.get(field):_public_body(json.loads(row[field]))
    feedback=groups['feedback']['shared_feedback']
    if any(r['kind'] not in FEEDBACK_KINDS for r in feedback):raise ValueError('Nonpublic feedback kinds cannot be imported')
    claims={r['id']:json.loads(r['body']) for r in feedback if r['kind']=='claim'}
    evidence={r['id']:json.loads(r['body']) for r in feedback if r['kind']=='evidence'}
    for key,claim in claims.items():
        if claim.get('id')!=key or claim.get('kind') not in {'FORECAST','REPORTED_FACT','INFERRED_EXPOSURE'} or claim.get('operationalEpisode') or claim.get('namespace') or claim.get('target',{}).get('decisionId'):
            raise ValueError('Visitor or operator claims are outside the public seed')
        _instant(claim['firstAvailableAt']);_instant(claim['originAt'])
        if claim['kind']=='FORECAST' and not (claim.get('target',{}).get('series')=='DEXINUS' and claim.get('source')=='PortWatch persistence baseline'):
            raise ValueError('Only public DEXINUS forecasts belong in the feedback seed')
    for key,record in evidence.items():
        if record.get('id')!=key or record.get('recordKind') not in {'ECONOMIC_OBSERVATION','AUTHORITY_RECORD','CANCELLATION'} or record.get('operationalEpisode') or record.get('independentTargetKey'):
            raise ValueError('Actual, simulated or operator observations are outside the public seed')
        _instant(record['firstAvailableAt'])
    for row in feedback:
        body=json.loads(row['body'])
        if body.get('id')!=row['id']:raise ValueError('Public feedback identity differs from its immutable row')
        if row['kind'] in {'assessment','match','economic-qualification'} and body.get('claimId') not in claims:
            raise ValueError('Feedback refers to a missing public claim')
        if row['kind']=='match' and body.get('evidenceId') not in evidence:raise ValueError('Match refers to missing public evidence')
    for row in groups['feedback']['predictions']:
        item=claims.get(row['prediction_id'],{})
        if not (item.get('kind')=='FORECAST' and item.get('target',{}).get('series')=='DEXINUS' and row['model']=='economic_persistence'):
            raise ValueError('Feedback prediction is not bound to a public economic claim')
    weather=groups['weather'];ids={r['prediction_id'] for r in weather['predictions']}
    for row in weather['predictions']:
        if row['domain']!='weather' or row['model'] not in {'Open-Meteo surface','Open-Meteo marine'} or row['observation_source'] not in (None,'reanalysis: Open-Meteo ERA5 archive'):
            raise ValueError('Only public provider weather and automatic reanalysis may be imported')
        _instant(row['issued_at']);_instant(row['valid_at'])
    if any(r['id'] not in ids for r in weather['weather_forecast_annotations']):raise ValueError('Weather annotation has no public forecast')
    for row in weather['weather_outcome_evidence']:
        body=json.loads(row['body'])
        if body.get('kind')!='reanalysis' or body.get('source')!='Open-Meteo ERA5 archive':raise ValueError('Operator and station outcomes are not public seed data')
        _instant(body['availableAt'])
    # Correction artifacts are not an adoption authority. None are accepted by this preview importer.
    if weather['weather_correction_versions']:raise ValueError('Correction/model promotion artifacts require a separate reviewed transfer')
    for table,rows in groups['ports'].items():
        for row in rows:
            if table!='cohort_cases' and row.get('port') not in (None,'INPRT','INMAA'):raise ValueError('Unsupported public-port scope')
            if table in {'snapshots','cases','cohorts','collections'}:
                key={'snapshots':'collectedBy','cases':'freezeActor','cohorts':'createdBy','collections':'actor'}[table]
                if json.loads(row['body']).get(key)!='Backend public port collector':raise ValueError('Private/operator port records cannot be seeded')
            if table=='checks' and row['actor']!='Backend public port collector':raise ValueError('Operator checks cannot be seeded')


def validate_seed(manifest_path):
    path=Path(manifest_path).resolve();raw=path.read_bytes();manifest=json.loads(raw)
    if manifest.get('version')!=VERSION or any(manifest.get(k) is not False for k in ('privateVisitorsEnumerated','operatorRecordsIncluded','authOrSessionStateIncluded')):
        raise ValueError('Unsupported or nonpublic seed manifest')
    _instant(manifest['preparedAt'])
    if not re.fullmatch(r'[a-f0-9]{40}',str(manifest.get('releaseSha',''))):raise ValueError('Seed release SHA required')
    files=manifest.get('files')
    if not isinstance(files,dict) or not set(DATABASES).issubset(files):raise ValueError('All public seed databases must be declared')
    verified={};groups={}
    for name,metadata in files.items():
        relative=_relative(name);source=(path.parent/relative).resolve()
        if not source.is_relative_to(path.parent):raise ValueError('Seed symlink escapes its source directory')
        content=source.read_bytes()
        if _digest(content)!=metadata.get('sha256') or len(content)!=metadata.get('bytes'):raise ValueError('Seed file failed its manifest hash/size')
        if relative.suffix in ('.response','.pdf') and _digest(content)!=relative.stem:raise ValueError('Public original name is not its SHA-256')
        if relative.suffix=='.json':_public_body(json.loads(content))
        verified[name]=content
        if name in DATABASES:
            label,tables=DATABASES[name];groups[label]=_source_rows(source,tables)
            if _digest(source.read_bytes())!=metadata['sha256']:raise ValueError('Seed database changed during verification')
    _validate_records(groups)
    return {'id':_digest(raw),'manifest':manifest,'files':verified,'groups':groups}


def _equivalent(a,b):
    if set(a)!=set(b):return False
    for key in a:
        left,right=a[key],b[key]
        if key in {'body','context','features','contributions','provenance'} and left is not None and right is not None:
            left,right=json.loads(left),json.loads(right)
        if left!=right:return False
    return True


def import_public_seed(manifest_path,*,state_dir,current_environment_dir,weather_db,feedback_db,now=None,dry_run=False):
    plan=validate_seed(manifest_path)
    if dry_run:return {'status':'VALIDATED','manifestId':plan['id'],'files':len(plan['files']),
        'tables':{key:{table:len(rows) for table,rows in tables.items()} for key,tables in plan['groups'].items()}}
    from src.portwatch_os.ledger.store import SqliteLedgerStore
    from src.portwatch_os.learning.weather_reconciliation import WeatherEvidenceStore
    from src.portwatch_os.intelligence.public_ports import PublicPilot
    at=_instant(now or datetime.now(timezone.utc).isoformat()).isoformat()
    state,environment=Path(state_dir),Path(current_environment_dir)
    targets={'feedback':Path(feedback_db),'weather':Path(weather_db),'ports':state/'public_port_pilot/public_ports.db'}
    # The operator explicitly chose these destinations through preview server config.
    if len({p.resolve() for p in targets.values()})!=3:raise ValueError('Public seed stores must use separate database paths')
    if any(not p.resolve().is_relative_to(state.resolve()) for p in targets.values()):
        raise ValueError('Preview evidence databases must remain inside configured durable state')
    if not environment.resolve().is_relative_to(state.resolve()):
        raise ValueError('Preview originals must remain inside configured durable state')
    destinations={}
    for name in plan['files']:
        if name in DATABASES:continue
        relative=PurePosixPath(name)
        target=environment.joinpath(*relative.parts[1:]) if relative.parts[0]=='current_environment' else state.joinpath(*relative.parts)
        boundary=environment if relative.parts[0]=='current_environment' else state
        if not target.resolve().is_relative_to(boundary.resolve()):raise ValueError('Configured public archive path escapes its destination')
        destinations[name]=target
    audit_root=state/'public_evidence_import';audit_path=audit_root/(plan['id']+'.json')
    if not audit_root.resolve().is_relative_to(state.resolve()):
        raise ValueError('Public import audit must remain inside configured durable state')
    if audit_path.exists():return {**json.loads(audit_path.read_text()),'status':'ALREADY_IMPORTED'}
    backup_root=audit_root/'backups'/plan['id'];backup_root.mkdir(parents=True,exist_ok=True)
    backups=[]
    for label,target in targets.items():
        if not target.exists():continue
        backup=backup_root/(label+'.sqlite3')
        if not backup.exists():
            source=sqlite3.connect(target.resolve().as_uri()+'?mode=ro',uri=True);dest=sqlite3.connect(backup)
            try:source.backup(dest)
            finally:dest.close();source.close()
        backups.append({'store':label,'sha256':_digest(backup.read_bytes())})
    conflicts=[];files_added=0;files_kept=0
    for name,raw in plan['files'].items():
        if name in DATABASES:continue
        target=destinations[name]
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            files_kept+=1
            if target.read_bytes()!=raw:
                conflicts.append({'kind':'PUBLIC_FILE','key':name,'existingSha256':_digest(target.read_bytes()),'incomingSha256':_digest(raw)})
                quarantined=audit_root/'quarantine'/plan['id']/name
                if not quarantined.resolve().is_relative_to(state.resolve()):
                    raise ValueError('Public quarantine must remain inside configured durable state')
                quarantined.parent.mkdir(parents=True,exist_ok=True)
                if not quarantined.exists():quarantined.write_bytes(raw)
        else:
            with target.open('xb') as output:output.write(raw)
            files_added+=1
    stores=[SqliteLedgerStore(targets['feedback']),SqliteLedgerStore(targets['weather'])]
    weather=WeatherEvidenceStore(targets['weather']);weather.close()
    port=PublicPilot(targets['ports'].parent);port.close()
    for store in stores:store.close()
    counts={}
    for label,tables in plan['groups'].items():
        connection=sqlite3.connect(targets[label]);connection.row_factory=sqlite3.Row
        try:
            with connection:
                for table,rows in tables.items():
                    stats={'added':0,'unchanged':0,'outcomesFilled':0,'conflicts':0};counts[label+':'+table]=stats
                    for row in rows:
                        key=KEYS[table];where=' AND '.join('"'+k+'"=?' for k in key)
                        existing=connection.execute('SELECT * FROM "'+table+'" WHERE '+where,tuple(row[k] for k in key)).fetchone()
                        if existing is None:
                            columns=tuple(row);connection.execute('INSERT INTO "'+table+'" ('+','.join('"'+c+'"' for c in columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(row[c] for c in columns));stats['added']+=1
                        elif _equivalent(dict(existing),row):stats['unchanged']+=1
                        elif table=='predictions' and existing['status']=='open' and row['status']=='resolved' and _equivalent({k:existing[k] for k in row if k not in OUTCOME_FIELDS},{k:row[k] for k in row if k not in OUTCOME_FIELDS}):
                            fields=sorted(OUTCOME_FIELDS);connection.execute('UPDATE predictions SET '+','.join('"'+k+'"=?' for k in fields)+' WHERE '+where,tuple(row[k] for k in fields)+tuple(row[k] for k in key));stats['outcomesFilled']+=1
                        else:
                            stats['conflicts']+=1;conflicts.append({'kind':'PUBLIC_ROW','store':label,'table':table,'key':[row[k] for k in key],
                                'existingSha256':_digest(_canonical(dict(existing)).encode()),'incomingSha256':_digest(_canonical(row).encode()),
                                'incomingPublicRecord':row})
        finally:connection.close()
    report={'status':'IMPORTED_WITH_CONFLICTS' if conflicts else 'IMPORTED','manifestId':plan['id'],
        'sourceReleaseSha':plan['manifest']['releaseSha'],'sourcePreparedAt':plan['manifest']['preparedAt'],
        'importedAt':at,'filesAdded':files_added,'existingFilesPreserved':files_kept,'counts':counts,
        'conflictCount':len(conflicts),'backupIdentities':backups,'sourceClocksAndIdsPreserved':True,
        'privateVisitorsImported':False,'actualOperationalTargetsAdded':0}
    audit_root.mkdir(parents=True,exist_ok=True)
    if conflicts:(audit_root/(plan['id']+'.conflicts.json')).write_text(json.dumps(conflicts,indent=2))
    ledger=SqliteLedgerStore(targets['feedback'])
    try:ledger.append_feedback('public-seed-import',{'id':plan['id'],**report})
    finally:ledger.close()
    temporary=audit_path.with_suffix('.tmp');temporary.write_text(json.dumps(report,indent=2));temporary.replace(audit_path)
    return report


def import_configured_seed():
    """Absent configuration is a no-op; callers invoke before collectors start."""
    manifest=os.getenv('PORTWATCH_PUBLIC_EVIDENCE_SEED_MANIFEST')
    if not manifest:return {'status':'DISABLED'}
    from src.utils.config import STATE_DIR
    from src.portwatch_os.intelligence.current_environment import ROOT, FEEDBACK_DB
    from src.portwatch_os.learning.intelligence_reconciliation import DB
    return import_public_seed(manifest,state_dir=STATE_DIR,current_environment_dir=ROOT,
        weather_db=FEEDBACK_DB,feedback_db=DB)
