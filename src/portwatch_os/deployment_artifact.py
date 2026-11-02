"""Verify clean image source bytes against its packaged Git-source manifest."""
from functools import lru_cache
import hashlib,json,os,re
from pathlib import Path,PurePosixPath

RUNTIME_NAMES={'port_state.json','forecast_by_port.json','model_pipeline.json','regime_by_port.json','decision_by_port.json',
 'benchmark.json','provenance.json','vessels.json','fleet.json','weather_by_port.json','weather_intelligence.json','news_bundle.json','live_status.json'}


def verify(root,manifest_path,expected_sha=None):
    root=Path(root).resolve();path=Path(manifest_path).resolve()
    if not path.is_relative_to(root):raise ValueError('Source manifest must be inside the image root')
    raw=path.read_bytes();manifest=json.loads(raw)
    sha=manifest.get('applicationSha','')
    if manifest.get('version')!='preview-image-source-v1' or not re.fullmatch('[a-f0-9]{40}',sha):raise ValueError('Invalid image source manifest')
    if expected_sha and sha!=expected_sha:raise ValueError('Image source manifest does not match the configured release')
    rows=manifest.get('files',[]);seen=set()
    if not rows:raise ValueError('No image source files are declared')
    caches=manifest.get('runtimeCache',[])
    for row,is_source in [(r,True) for r in rows]+[(r,False) for r in caches]:
        relative=PurePosixPath(row['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.as_posix()!=row['path'] or '\\' in row['path'] or row['path'] in seen:raise ValueError('Invalid or duplicate source path')
        seen.add(row['path']);target=root.joinpath(*relative.parts)
        if not is_source and (relative.parent.as_posix()!='data/cache' or relative.name not in RUNTIME_NAMES or row.get('kind')!='RETAINED_PUBLIC_RUNTIME_CACHE'):raise ValueError('Runtime cache is not in the reviewed public allowlist')
        if target.is_symlink() or not target.resolve().is_relative_to(root):raise ValueError('Source path escapes the image')
        size=target.stat().st_size
        sha256=hashlib.sha256();blob=hashlib.sha1(b'blob '+str(size).encode()+b'\0')
        with target.open('rb') as stream:
            while chunk:=stream.read(1024*1024):sha256.update(chunk);blob.update(chunk)
        if size!=row['bytes'] or sha256.hexdigest()!=row['sha256'] or (is_source and blob.hexdigest()!=row['gitBlob']):raise ValueError('Image bytes differ from their reviewed manifest: '+row['path'])
    return {'status':'VERIFIED','applicationSha':sha,'manifestSha256':hashlib.sha256(raw).hexdigest(),'checkedFiles':len(rows),'retainedRuntimeCaches':len(caches)}


@lru_cache(maxsize=32)
def _retained_cache_time(path,size,mtime_ns,manifest_path):
    # Read-only qualification. A later collector/pipeline write changes the stat
    # key and must match the retained body hash before retaining an older age.
    manifest=json.loads(Path(manifest_path).read_bytes())
    for row in manifest.get('runtimeCache',[]):
        if row['path']=='data/cache/'+Path(path).name and row['bytes']==size and hashlib.sha256(Path(path).read_bytes()).hexdigest()==row['sha256']:
            return float(row['retainedFileMtime'])
    return None


def retained_cache_time(path):
    root=Path(__file__).resolve().parents[2];manifest=root/'data/preview_release/source-manifest.json';path=Path(path)
    if not manifest.is_file() or path.resolve().parent!=root/'data/cache':return None
    stat=path.stat()
    return _retained_cache_time(str(path),stat.st_size,stat.st_mtime_ns,str(manifest))


@lru_cache(maxsize=1)
def current():
    root=Path(__file__).resolve().parents[2];manifest=root/'data/preview_release/source-manifest.json'
    if not manifest.exists():
        if os.getenv('PORTWATCH_REQUIRE_RELEASE_MANIFEST')=='1':raise RuntimeError('Required image source manifest is absent')
        return {'status':'UNCONFIGURED','applicationSha':'UNKNOWN','manifestSha256':None,'checkedFiles':0}
    return verify(root,manifest,os.getenv('PORTWATCH_RELEASE_SHA') or None)
