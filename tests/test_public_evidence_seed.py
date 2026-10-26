"""Portable synthetic public-seed merge tests; no live stores/providers."""
import hashlib
import json
import sqlite3

import pytest

from src.portwatch_os.learning import public_evidence_seed as seed
from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning.weather_reconciliation import WeatherEvidenceStore
from src.portwatch_os.intelligence.public_ports import PublicPilot


RAW = b'SYNTHETIC public source original, not provider accuracy evidence'
DIGEST = hashlib.sha256(RAW).hexdigest()
AT = '2026-10-20T00:00:00+00:00'


def make_seed(root):
    root.mkdir()
    base = root/'schema.db'
    store = SqliteLedgerStore(base); store.close()
    weather = WeatherEvidenceStore(base); weather.close()
    pilot = PublicPilot(root/'port-schema'); pilot.close()
    for relative, (label, tables) in seed.DATABASES.items():
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
        source=sqlite3.connect(root/'port-schema/public_ports.db' if label=='ports' else base)
        out=sqlite3.connect(target)
        for table in tables:
            definition=source.execute('select sql from sqlite_master where type=\'table\' and name=?',(table,)).fetchone()[0]
            out.execute(definition)
        if label=='feedback':
            body={'id':'synthetic-news','kind':'REPORTED_FACT','wording':'SYNTHETIC announced restriction',
                  'entity':'SYNTHETIC_LOCK','geography':'SYNTHETIC_AREA','firstAvailableAt':AT,'originAt':AT,
                  'target':{'kind':'ANNOUNCEMENT','from':'2026-10-21','through':'2026-10-22'},'responseSha256':DIGEST}
            out.execute('insert into shared_feedback(kind,id,body) values(?,?,?)',('claim',body['id'],json.dumps(body)))
        out.commit();out.close();source.close()
    original=root/'current_environment/shared_feedback'/f'{DIGEST}.response'
    original.parent.mkdir(parents=True);original.write_bytes(RAW)
    files={str(p.relative_to(root)).replace('\\','/'):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
           for p in [*(root/name for name in seed.DATABASES),original]}
    manifest={'version':seed.VERSION,'preparedAt':AT,'releaseSha':'0'*40,'privateVisitorsEnumerated':False,
              'operatorRecordsIncluded':False,'authOrSessionStateIncluded':False,'files':files}
    path=root/'manifest.json';path.write_text(json.dumps(manifest));return path


def run(manifest, state, **kwargs):
    return seed.import_public_seed(manifest,state_dir=state,current_environment_dir=state/'current_environment',
        weather_db=state/'weather.sqlite3',feedback_db=state/'feedback.sqlite3',now=AT,**kwargs)


def refresh_hash(manifest, relative):
    value=json.loads(manifest.read_text());path=manifest.parent/relative
    value['files'][relative]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
    manifest.write_text(json.dumps(value))


def test_unconfigured_import_is_disabled(monkeypatch):
    monkeypatch.delenv('PORTWATCH_PUBLIC_EVIDENCE_SEED_MANIFEST',raising=False)
    assert seed.import_configured_seed()=={'status':'DISABLED'}


def test_public_ids_originals_and_clocks_survive_import_and_retry(tmp_path):
    manifest=make_seed(tmp_path/'seed');state=tmp_path/'state'
    first=run(manifest,state);second=run(manifest,state)
    assert first['status']=='IMPORTED' and second['status']=='ALREADY_IMPORTED'
    assert first['manifestId']==second['manifestId'] and first['importedAt']==AT
    assert (state/'current_environment/shared_feedback'/f'{DIGEST}.response').read_bytes()==RAW
    with sqlite3.connect(state/'feedback.sqlite3') as db:
        claim=json.loads(db.execute("select body from shared_feedback where kind='claim'").fetchone()[0])
        assert claim['firstAvailableAt']==AT and claim['id']=='synthetic-news'
        assert db.execute("select count(*) from shared_feedback where kind='public-seed-import'").fetchone()[0]==1


def test_all_hashes_validate_before_destination_writes(tmp_path):
    manifest=make_seed(tmp_path/'seed');state=tmp_path/'state'
    (manifest.parent/'current_environment/shared_feedback'/f'{DIGEST}.response').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='hash/size'):run(manifest,state)
    assert not state.exists()


def test_private_record_rejected_even_with_updated_file_hash(tmp_path):
    manifest=make_seed(tmp_path/'seed');relative='feedback/public_feedback.sqlite3'
    with sqlite3.connect(manifest.parent/relative) as db:
        db.execute('insert into shared_feedback(kind,id,body) values(?,?,?)',('consumption','private',json.dumps({'id':'private'})))
    refresh_hash(manifest,relative)
    with pytest.raises(ValueError,match='Nonpublic feedback'):run(manifest,tmp_path/'state')
    assert not (tmp_path/'state').exists()


def test_unapproved_path_rejected_before_writes(tmp_path):
    manifest=make_seed(tmp_path/'seed');value=json.loads(manifest.read_text())
    value['files']['../identity.db']={'sha256':'a'*64,'bytes':1};manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='relative public paths'):run(manifest,tmp_path/'state')
    assert not (tmp_path/'state').exists()


def test_nested_authorization_metadata_is_not_public_seed_data(tmp_path):
    manifest=make_seed(tmp_path/'seed');relative='feedback/public_feedback.sqlite3'
    with sqlite3.connect(manifest.parent/relative) as db:
        body=json.loads(db.execute("select body from shared_feedback where kind='claim'").fetchone()[0])
        body['metadata']={'Authorization':'SYNTHETIC_CREDENTIAL'}
        db.execute("update shared_feedback set body=? where kind='claim'",(json.dumps(body),))
    refresh_hash(manifest,relative)
    with pytest.raises(ValueError,match='Private identity'):run(manifest,tmp_path/'state')
    assert not (tmp_path/'state').exists()


def test_existing_conflict_and_private_visitor_records_are_preserved(tmp_path):
    manifest=make_seed(tmp_path/'seed');state=tmp_path/'state';state.mkdir()
    existing=SqliteLedgerStore(state/'feedback.sqlite3')
    existing.append_feedback('claim',{'id':'synthetic-news','wording':'Existing newer public record'})
    existing.append_feedback('review-task',{'id':'synthetic-private-task','visitorId':'SYNTHETIC'})
    existing.close()
    result=run(manifest,state)
    assert result['status']=='IMPORTED_WITH_CONFLICTS' and result['conflictCount']==1
    with sqlite3.connect(state/'feedback.sqlite3') as db:
        assert 'Existing newer' in db.execute("select body from shared_feedback where kind='claim'").fetchone()[0]
        assert db.execute("select count(*) from shared_feedback where kind='review-task'").fetchone()[0]==1
    assert result['backupIdentities'][0]['store']=='feedback'
    conflict=json.loads((state/'public_evidence_import'/(result['manifestId']+'.conflicts.json')).read_text())[0]
    assert 'SYNTHETIC announced' in conflict['incomingPublicRecord']['body']


def test_archive_destination_must_be_durable(tmp_path):
    manifest=make_seed(tmp_path/'seed');state=tmp_path/'state'
    with pytest.raises(ValueError,match='originals.*durable'):
        seed.import_public_seed(manifest,state_dir=state,current_environment_dir=tmp_path/'ephemeral',
            weather_db=state/'weather.sqlite3',feedback_db=state/'feedback.sqlite3',now=AT)
    assert not state.exists()


def test_corrupt_existing_original_is_preserved_and_incoming_copy_quarantined(tmp_path):
    manifest=make_seed(tmp_path/'seed');state=tmp_path/'state'
    original=state/'current_environment/shared_feedback'/f'{DIGEST}.response'
    original.parent.mkdir(parents=True);original.write_bytes(b'Existing corrupt copy')
    result=run(manifest,state)
    assert result['status']=='IMPORTED_WITH_CONFLICTS' and original.read_bytes()==b'Existing corrupt copy'
    quarantined=state/'public_evidence_import/quarantine'/result['manifestId']/'current_environment/shared_feedback'/f'{DIGEST}.response'
    assert quarantined.read_bytes()==RAW
