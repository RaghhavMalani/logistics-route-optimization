"""Export reviewed Git bytes plus separately qualified public evidence/cache.

Never uploads, reads visitor scopes or copies the dirty checkout wholesale.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,io,json,re,stat,subprocess,zipfile,sys

RUNTIME_FILES=('port_state.json','forecast_by_port.json','model_pipeline.json','regime_by_port.json','decision_by_port.json',
 'benchmark.json','provenance.json','vessels.json','fleet.json','weather_by_port.json','weather_intelligence.json','news_bundle.json','live_status.json')
BACK_DIRS=('src/','backend/','app/','scripts/','data/','tests/')
BACK_FILES={'Dockerfile','requirements.txt','railway.json','.dockerignore','.gitignore','run_award_demo.py','run_demo.py','LICENSE'}
BAD_PATH=re.compile(r'(^|/)(?:\.env(?:\.|$)|\.aws|credentials|sessions|node_modules|\.git|\.output|\.vercel|\.railway|debug\.log|work|outputs)(?:/|$)',re.I)
SECRET=re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:AKIA|ASIA)[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}|Bearer [A-Za-z0-9_\-./+]{48,}')


def hash_bytes(raw):return hashlib.sha256(raw).hexdigest()
def row(name,raw,**more):return dict(path=name,bytes=len(raw),sha256=hash_bytes(raw),**more)
def write(root,name,raw):
    target=root/name
    if not target.resolve().is_relative_to(root.resolve()):raise ValueError('Output path escape')
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sha',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--seed',required=True);parser.add_argument('--runtime-cache',required=True);parser.add_argument('--candidate-api',required=True)
    args=parser.parse_args();repo=Path.cwd().resolve();output=Path(args.output).resolve()
    if not output.is_relative_to(repo/'work') or output.exists():raise ValueError('Use a fresh ignored work directory')
    if not re.fullmatch(r'https://[a-z0-9-]+\.up\.railway\.app',args.candidate_api):raise ValueError('An explicit candidate Railway hostname is required')
    sha=subprocess.check_output(['git','rev-parse','--verify',args.sha+'^{commit}'],text=True).strip()
    backend,frontend=output/'backend',output/'frontend';records={'backend':[],'frontend':[]};image=[]
    raw=subprocess.check_output(['git','-c','core.autocrlf=false','archive','--format=zip',sha])
    tree={}
    for item in subprocess.check_output(['git','ls-tree','-rz',sha]).split(b'\0'):
        if item:
            meta,name=item.split(b'\t',1);tree[name.decode()]=meta.decode().split()[-1]
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        for entry in source.infolist():
            if entry.is_dir():continue
            name=entry.filename
            scopes=[]
            if name.startswith(BACK_DIRS) or name in BACK_FILES:scopes.append(('backend',backend))
            if name.startswith('india-portwatch-terminal/') or name in ('.gitignore','LICENSE'):scopes.append(('frontend',frontend))
            if not scopes:continue
            relative=PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or stat.S_ISLNK(entry.external_attr>>16) or BAD_PATH.search(name) or name.endswith(('.db','.sqlite','.sqlite3','.log')):raise ValueError('Nonpublic/unsafe source path: '+name)
            content=source.read(entry)
            if SECRET.search(content):raise ValueError('Credential pattern in reviewed source: '+name)
            if name.startswith('data/research_release/') and name.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(content)) as nested:
                    for member in nested.infolist():
                        path=PurePosixPath(member.filename)
                        if path.is_absolute() or '..' in path.parts or stat.S_ISLNK(member.external_attr>>16) or re.search(r'(^|/)(\.env|credentials|sessions)(\.|/|$)',member.filename,re.I):raise ValueError('Unsafe nested public research archive')
            record=row(name,content,gitBlob=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest(),kind='REVIEWED_GIT_SOURCE')
            if record['gitBlob']!=tree[name]:raise ValueError('Export differs from reviewed Git blob: '+name)
            for scope,target in scopes:write(target,name,content);records[scope].append(record)
            if any(scope=='backend' for scope,_ in scopes) and (name.startswith(BACK_DIRS) or name in ('requirements.txt','run_award_demo.py','run_demo.py')):image.append(record)
    # The reviewed importer validates tables, columns, public body semantics,
    # credentials, original hashes, path containment and immutable identities.
    sys.path.insert(0,str(repo))
    from src.portwatch_os.learning.public_evidence_seed import validate_seed,_public_body
    qualified=validate_seed(args.seed);seed_path=Path(args.seed)
    for name,content in qualified['files'].items():
        target='data/cache/preview_public_seed/'+name;write(backend,target,content);records['backend'].append(row(target,content,kind='QUALIFIED_HISTORICAL_PUBLIC_EVIDENCE'))
    target='data/cache/preview_public_seed/manifest.json';content=seed_path.read_bytes();write(backend,target,content);records['backend'].append(row(target,content,kind='PUBLIC_SEED_MANIFEST'))
    caches=[]
    for name in RUNTIME_FILES:
        original=Path(args.runtime_cache)/name;content=original.read_bytes();_public_body(json.loads(content))
        if SECRET.search(content):raise ValueError('Credential pattern in runtime cache: '+name)
        target='data/cache/'+name;write(backend,target,content)
        if any(r['path']==target for r in records['backend']):raise ValueError('Runtime cache must not replace a tracked Git file')
        record=row(target,content,kind='RETAINED_PUBLIC_RUNTIME_CACHE',retainedFileMtime=original.stat().st_mtime,
            timeBasis='Retained filesystem timestamp; not provider issue/publication/first-availability')
        caches.append(record);records['backend'].append(record)
    required={'backend/app/routes/commercial.py','src/portwatch_os/decision/commercial_jobs.py','src/portwatch_os/decision/commercial_uncertainty.py'}
    if not required.issubset({r['path'] for r in image}):raise ValueError('Chosen commit does not contain the completed commercial/compute capability')
    manifest={'version':'preview-image-source-v1','applicationSha':sha,'files':image,'runtimeCache':caches,
        'seedManifestSha256':qualified['id'],'seedSourceSha':qualified['manifest']['releaseSha']}
    content=json.dumps(manifest,sort_keys=True,indent=2).encode();target='data/preview_release/source-manifest.json'
    write(backend,target,content);records['backend'].append(row(target,content,kind='IMAGE_SOURCE_MANIFEST'))
    # Candidate configuration is local to this upload. The tracked config and
    # both existing deployments' rewrite destinations remain unchanged.
    config_path='india-portwatch-terminal/vercel.json'
    config_input=config_path
    programmatic_config='india-portwatch-terminal/vercel.mjs'
    if (frontend/programmatic_config).is_file():
        # Detached uploads have no Git ref. Materialize the reviewed base
        # configuration with an explicit candidate rewrite for that upload.
        config_input='india-portwatch-terminal/vercel.base.json'
        (frontend/programmatic_config).unlink()
    config=json.loads((frontend/config_input).read_bytes())
    prior=config['rewrites'][-1]['destination'];config['rewrites'][-1]['destination']=args.candidate_api+'/api/:path*'
    content=json.dumps(config,indent=2).encode();write(frontend,config_path,content)
    records['frontend']=[r for r in records['frontend'] if r['path'] not in (config_path,programmatic_config)]
    records['frontend'].append(row(config_path,content,kind='CANDIDATE_ONLY_REWRITE',originalDestination=prior))
    fingerprints={scope:hash_bytes(json.dumps(sorted(rows,key=lambda r:r['path']),sort_keys=True,separators=(',',':')).encode()) for scope,rows in records.items()}
    release={'applicationSha':sha,'sourceFingerprint':fingerprints['frontend'],'scope':'INTEGRATED_PREVIEW_ONLY','backend':args.candidate_api}
    content=json.dumps(release,sort_keys=True).encode();target='india-portwatch-terminal/public/release.json';write(frontend,target,content);records['frontend'].append(row(target,content,kind='NONSECRET_RELEASE_BINDING'))
    for scope,directory in [('backend',backend),('frontend',frontend)]:
        expected={r['path'] for r in records[scope]};actual={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
        if expected!=actual:raise ValueError('Unexpected files in clean '+scope+' package')
    report={'version':'integrated-preview-package-v1','applicationSha':sha,'source':'Git archive; dirty CSV versions excluded',
        'candidateApi':args.candidate_api,'seedManifestSha256':qualified['id'],'seedSourceSha':qualified['manifest']['releaseSha'],
        'sourceFingerprints':fingerprints,'files':records,'imageManifestSha256':hash_bytes((backend/'data/preview_release/source-manifest.json').read_bytes()),
        'packagingDifference':'Candidate-only final API rewrite and nonsecret release binding; originals preserved',
        'privateSessionsOrOperationalStoresIncluded':False}
    output.mkdir(parents=True,exist_ok=True);(output/'package-manifest.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))


if __name__=='__main__':main()
