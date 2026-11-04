from pathlib import Path
import sqlite3
import pytest
from scripts import candidate_state_backup as backup


def test_wal_backup_restoration_and_private_files_stay_inside_snapshot(tmp_path):
    root=tmp_path/'candidate';root.mkdir();db=sqlite3.connect(root/'sessions.sqlite3')
    db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE records(id TEXT PRIMARY KEY,body BLOB)')
    db.execute('INSERT INTO records VALUES (?,?)',('fixture',b'explicit fictional private data'));db.commit()
    (root/'signing-key.fixture').write_text('deliberately fake local test material')
    try:
        folder,report=backup.backup_and_verify(root)
        assert report['result']=='VERIFIED' and report['sqliteDatabases']==1
        assert report['files'][0]['path'] in ('sessions.sqlite3','signing-key.fixture')
        restored=sqlite3.connect(folder/'restore-check/sessions.sqlite3')
        assert restored.execute('SELECT body FROM records').fetchone()[0]==b'explicit fictional private data'
        restored.close()
        assert not any(r['path'].endswith(('-wal','-shm')) for r in report['files'])
    finally:db.close()


def test_concurrent_mutation_is_not_reported_as_verified(tmp_path,monkeypatch):
    root=tmp_path/'candidate';root.mkdir();(root/'record.json').write_text('original fixture')
    copy=backup.shutil.copy2
    def changing(source,target):
        result=copy(source,target)
        if Path(source)==root/'record.json':Path(source).write_text('changed fixture')
        return result
    monkeypatch.setattr(backup.shutil,'copy2',changing)
    with pytest.raises(ValueError,match='Concurrent source-file'):backup.backup_and_verify(root)
    assert not list((root/'backups').glob('*/manifest.json'))


def test_requested_backup_is_idempotent_and_detects_changed_manifest(tmp_path):
    (tmp_path/'record.json').write_text('private fixture')
    request='a'*32
    result=backup.run_once(tmp_path,request)
    assert result['status']=='RESTORE_VERIFIED'
    assert backup.run_once(tmp_path,request)==result
    assert len(list((tmp_path/'backups').glob('verified-*')))==1
    (tmp_path/result['manifest']).write_text('changed fixture')
    with pytest.raises(ValueError,match='manifest changed'):backup.run_once(tmp_path,request)


def test_startup_request_cannot_target_production_or_another_volume(monkeypatch,tmp_path):
    monkeypatch.delenv('PORTWATCH_CANDIDATE_BACKUP_REQUEST',raising=False)
    assert backup.configured_backup()=={'status':'DISABLED'}
    monkeypatch.setenv('PORTWATCH_CANDIDATE_BACKUP_REQUEST','a'*32)
    monkeypatch.setenv('PORTWATCH_RELEASE_ENVIRONMENT','production')
    monkeypatch.setenv('PORTWATCH_STATE_DIR',str(tmp_path))
    with pytest.raises(ValueError,match='refuses'):backup.configured_backup()
    monkeypatch.setenv('PORTWATCH_RELEASE_ENVIRONMENT','integrated-preview-fixture')
    with pytest.raises(ValueError,match='refuses'):backup.configured_backup()
    with pytest.raises(ValueError,match='Invalid candidate backup request'):backup.run_once(tmp_path,'../escape')
