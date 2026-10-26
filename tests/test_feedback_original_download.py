"""Public archive download parity and path restrictions; synthetic originals."""
import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes import shared_feedback as routes
from src.portwatch_os.learning import intelligence_reconciliation as collector
from src.portwatch_os.ledger.store import SqliteLedgerStore


@pytest.fixture
def public_download(tmp_path,monkeypatch):
    monkeypatch.setattr(collector,'DB',tmp_path/'store'/'public.db')
    monkeypatch.setattr(collector,'ROOT',tmp_path/'default-archive')
    store=SqliteLedgerStore(collector.DB)
    app=FastAPI();app.include_router(routes.router,prefix='/api')
    with TestClient(app) as client:
        yield store,client,tmp_path
    store.close()


def retain(store,raw,root,*,product=None):
    digest=collector.retain_response(store,raw,'https://fixture.example/public-source',
        '2026-10-20T12:00:00+00:00',root,product=product)
    return digest,Path(root)/'shared_feedback'/(digest+'.response')


@pytest.mark.parametrize('location',['store-adjacent','receipt-path'])
def test_public_record_download_matches_original_across_supported_archives(public_download,location):
    store,client,root=public_download
    folder=Path(store.path).parent if location=='store-adjacent' else root/'separate-public-archive'
    raw=b'SIMULATED public evidence original\n'
    digest,path=retain(store,raw,folder)
    response=client.get('/api/intelligence/feedback/evidence/'+digest)
    assert response.status_code==200,response.text
    assert response.content==raw
    assert response.headers['x-source-sha256']==hashlib.sha256(response.content).hexdigest()==digest
    assert str(root) not in response.text


def test_unreferenced_disk_file_cannot_be_downloaded(public_download):
    store,client,root=public_download
    raw=b'SIMULATED file without a public retained record'
    digest=hashlib.sha256(raw).hexdigest()
    folder=collector.ROOT/'shared_feedback';folder.mkdir(parents=True)
    (folder/(digest+'.response')).write_bytes(raw)
    assert client.get('/api/intelligence/feedback/evidence/'+digest).status_code==404
    assert not store.feedback('receipt')


def test_corruption_blocks_download_but_valid_retained_copy_is_usable(public_download):
    store,client,root=public_download
    raw=b'SIMULATED public evidence original'
    digest,path=retain(store,raw,root/'separate-public-archive')
    path.write_bytes(b'SIMULATED corrupt bytes')
    assert client.get('/api/intelligence/feedback/evidence/'+digest).status_code==503
    folder=collector.ROOT/'shared_feedback';folder.mkdir(parents=True)
    (folder/(digest+'.response')).write_bytes(raw)
    response=client.get('/api/intelligence/feedback/evidence/'+digest)
    assert response.status_code==200 and response.content==raw


def test_unparsed_gac_receipt_retains_local_only_distribution_boundary(public_download):
    store,client,root=public_download
    digest,path=retain(store,b'SIMULATED unsupported GAC response retained before extraction',
        root/'separate-public-archive',product='GAC_EASTHAM_NOTICE_ANNOUNCEMENT_V1')
    assert not store.feedback('claim')
    response=client.get('/api/intelligence/feedback/evidence/'+digest)
    assert response.status_code==403
    assert path.is_file()


def test_receipt_archive_path_must_follow_retained_hash_filename_contract(public_download):
    store,client,root=public_download
    raw=b'SIMULATED arbitrary filename cannot be a source selector'
    digest=hashlib.sha256(raw).hexdigest()
    path=root/'private-unrelated.txt';path.write_bytes(raw)
    store.append_feedback('receipt',{'id':'fixture-invalid-path','responseSha256':digest,
        'source':'https://fixture.example','receivedAt':'2026-10-20T12:00:00+00:00','archivePath':str(path)})
    assert client.get('/api/intelligence/feedback/evidence/'+digest).status_code==404
