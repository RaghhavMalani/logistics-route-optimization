from pathlib import Path
import hashlib,json
import pytest
from src.portwatch_os.deployment_artifact import verify,_retained_cache_time


def fixture(tmp_path):
    root=tmp_path/'image';(root/'src').mkdir(parents=True)
    raw=b'original reviewed source\n';(root/'src/app.py').write_bytes(raw)
    row={'path':'src/app.py','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'gitBlob':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
    manifest=root/'manifest.json';manifest.write_text(json.dumps({'version':'preview-image-source-v1','applicationSha':'a'*40,'files':[row]}))
    return root,manifest,row


def test_image_bytes_and_configured_sha_are_both_required(tmp_path):
    root,path,row=fixture(tmp_path)
    assert verify(root,path,'a'*40)['status']=='VERIFIED'
    with pytest.raises(ValueError):verify(root,path,'b'*40)
    (root/'src/app.py').write_text('changed source')
    with pytest.raises(ValueError):verify(root,path,'a'*40)


@pytest.mark.parametrize('name',['../outside.py','/absolute.py','src/./app.py','src\\app.py'])
def test_noncanonical_image_paths_are_refused(tmp_path,name):
    root,path,row=fixture(tmp_path);row['path']=name
    path.write_text(json.dumps({'version':'preview-image-source-v1','applicationSha':'a'*40,'files':[row]}))
    with pytest.raises(ValueError):verify(root,path)


def test_old_cache_keeps_original_filesystem_age_only_while_body_matches(tmp_path):
    root,path,row=fixture(tmp_path);cache=root/'data/cache/port_state.json';cache.parent.mkdir(parents=True)
    raw=b'{"INPRT":{"age":"historical fixture"}}';cache.write_bytes(raw)
    manifest=json.loads(path.read_text());manifest['runtimeCache']=[{'path':'data/cache/port_state.json','kind':'RETAINED_PUBLIC_RUNTIME_CACHE',
        'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'retainedFileMtime':1000}];path.write_text(json.dumps(manifest))
    assert verify(root,path)['retainedRuntimeCaches']==1
    stat=cache.stat();assert _retained_cache_time(str(cache),stat.st_size,stat.st_mtime_ns,str(path))==1000
    cache.write_bytes(b'{"INPRT":{"age":"changed new fixture"}}');stat=cache.stat()
    assert _retained_cache_time(str(cache),stat.st_size,stat.st_mtime_ns,str(path)) is None
