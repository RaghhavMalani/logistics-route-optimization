"""Candidate-only consistent SQLite backup and isolated restoration check.

No active database is copied as a raw file. Concurrent writes make this attempt
unaccepted; callers retry in a quiet window. Nothing is deleted or restored over.
"""
from pathlib import Path
import hashlib,json,os,shutil,sqlite3
from uuid import uuid4


def _files(root):
    result=[]
    for path in root.rglob('*'):
        relative=path.relative_to(root)
        if relative.parts[0]=='backups' or path.name.endswith(('.tmp','-wal','-shm','-journal','.lock')) or path.name=='collector-owner.json':continue
        if path.is_symlink():raise ValueError('Backup does not follow links')
        if path.is_file():result.append(path)
    return sorted(result)


def _connect(path):return sqlite3.connect('file:'+path.as_posix()+'?mode=ro',uri=True,timeout=5)
def _sha(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):result.update(chunk)
    return result.hexdigest()


def signature(connection):
    digest=hashlib.sha256();counts={}
    for name,sql in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        digest.update(str(sql).encode());quoted='"'+name.replace('"','""')+'"'
        columns=len(connection.execute('PRAGMA table_info('+quoted+')').fetchall())
        count=0
        for row in connection.execute('SELECT * FROM '+quoted+' ORDER BY '+','.join(str(i) for i in range(1,columns+1))):
            encoded=repr(row).encode();digest.update(str(len(encoded)).encode()+b':'+encoded);count+=1
        counts[name]=count
    return {'sha256':digest.hexdigest(),'tableCounts':counts}


def backup_and_verify(root):
    root=Path(root).resolve();folder=root/'backups'/('verified-'+uuid4().hex)
    if not folder.resolve().is_relative_to(root/'backups'):raise ValueError('Invalid backup destination')
    folder.mkdir(parents=True);snapshot=folder/'snapshot';restored=folder/'restore-check'
    source_files=_files(root);databases={};records=[]
    try:
        for path in source_files:
            if path.suffix in ('.db','.sqlite','.sqlite3'):
                connection=_connect(path);databases[path]=(connection,connection.execute('PRAGMA data_version').fetchone()[0])
        # Keep all read-only connections open across the complete snapshot. A
        # commit from any application writer changes its data_version.
        for path in source_files:
            relative=path.relative_to(root);target=snapshot/relative;target.parent.mkdir(parents=True,exist_ok=True)
            if path in databases:
                output=sqlite3.connect(target)
                try:databases[path][0].backup(output)
                finally:output.close()
            else:shutil.copy2(path,target)
            records.append({'path':relative.as_posix(),'bytes':target.stat().st_size,'sha256':_sha(target),'sqlite':path in databases})
        if _files(root)!=source_files:raise ValueError('Source file set changed during backup; retry this unaccepted attempt')
        for path,(connection,before) in databases.items():
            if connection.execute('PRAGMA data_version').fetchone()[0]!=before:raise ValueError('Concurrent SQLite write; retry this unaccepted attempt')
        for record in records:
            if not record['sqlite'] and _sha(root/record['path'])!=record['sha256']:raise ValueError('Concurrent source-file write; retry this unaccepted attempt')
        for record in records:
            source=snapshot/record['path'];target=restored/record['path'];target.parent.mkdir(parents=True,exist_ok=True)
            if record['sqlite']:
                first=_connect(source);second=sqlite3.connect(target)
                try:
                    first.backup(second)
                    if second.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or signature(first)!=signature(second):raise ValueError('Restored SQLite content does not match its backup')
                    record['restoration']=signature(second)
                finally:first.close();second.close()
            else:
                shutil.copy2(source,target)
                if _sha(target)!=record['sha256']:raise ValueError('Restored file differs from its backup')
        report={'version':'candidate-state-backup-v1','result':'VERIFIED','sourceQuiescent':True,
            'sqliteDatabases':len(databases),'files':records,'scope':'Candidate volume only; contains private state, never publish or seed'}
        (folder/'manifest.json').write_text(json.dumps(report,indent=2))
        return folder,report
    finally:
        for connection,_ in databases.values():connection.close()


def main():
    if not os.getenv('PORTWATCH_RELEASE_ENVIRONMENT','').startswith('integrated-preview-'):raise SystemExit('This utility refuses non-candidate environments')
    root=Path(os.getenv('PORTWATCH_STATE_DIR','')).resolve()
    if root!=Path('/app/state'):raise SystemExit('Expected the explicitly configured candidate volume /app/state')
    folder,report=backup_and_verify(root)
    print(json.dumps({'result':report['result'],'sqliteDatabases':report['sqliteDatabases'],'files':len(report['files']),
        'manifest':str(folder/'manifest.json'),'manifestSha256':_sha(folder/'manifest.json')}))


if __name__=='__main__':main()
