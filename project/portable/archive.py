"""Lossless create-only restoration of files that exceed GitHub blob limits."""
import gzip,hashlib,json,os,re,tempfile
from pathlib import Path,PurePosixPath

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def safe(root,name):
    name=str(name).replace('\\','/');p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or ':' in name or not p.parts:raise ValueError('unsafe relative path: '+name)
    root=Path(root).resolve();out=(root/name).resolve()
    if not out.is_relative_to(root) or out==root:raise ValueError('path escapes repository: '+name)
    return out

def restore(root):
    root=Path(root).resolve();m=json.loads((root/'portable/packed-manifest.json').read_bytes())
    if m.get('schema')!=1:raise ValueError('Unsupported packed archive')
    count=present=0
    for item in m['files']:
        target=safe(root,item['target']);source=safe(root,item['archive'])
        if target.exists():
            if not target.is_file() or digest(target)!=item['sha256']:raise ValueError('Refusing to overwrite changed existing file: '+str(target))
            present+=1;continue
        if digest(source)!=item['archive_sha256']:raise ValueError('Compressed source hash mismatch: '+str(source))
        target.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.restore-',dir=target.parent);pending=Path(name)
        try:
            with os.fdopen(fd,'wb') as dst,gzip.open(source,'rb') as src:
                size=0
                for block in iter(lambda:src.read(1024*1024),b''):
                    size+=len(block)
                    if size>item['bytes']:raise ValueError('Expanded file exceeds declared size')
                    dst.write(block)
            if size!=item['bytes'] or digest(pending)!=item['sha256']:raise ValueError('Expanded source hash/size mismatch')
            # Exclusive creation: an existing destination is never replaced.
            with target.open('xb') as dst,pending.open('rb') as src:
                for block in iter(lambda:src.read(1024*1024),b''):dst.write(block)
            count+=1
        finally:pending.unlink(missing_ok=True)
    return {'restored':count,'already_present':present}

def verify_tree(root):
    root=Path(root).resolve();p=root/'portable/SOURCE_TREE.json'
    if not p.exists():return {'status':'source checkout','reason':'Full transfer manifest is generated in the exported repository'}
    manifest=json.loads(p.read_bytes());bad=[]
    for name,expected in manifest['files'].items():
        f=safe(root,name)
        if not f.is_file() or digest(f)!=expected:bad.append(name)
    if bad:raise ValueError('Transferred source bytes differ: '+', '.join(bad[:12]))
    return {'status':'verified','files':len(manifest['files']),'source_commit':manifest['source_commit']}
