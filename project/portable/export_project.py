"""Create-only, byte-exact portable snapshot; never rewrites source history."""
import argparse,json,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
from portable.archive import digest

def export(source,destination,preview=False):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(source):raise ValueError('Use a NEW export directory outside the source checkout')
    names=set(subprocess.check_output(['git','ls-files','-z'],cwd=source).decode().split('\0'))-{''}
    if preview:
        names.update(p.relative_to(source).as_posix() for p in (source/'portable').rglob('*') if p.is_file() and not set(p.relative_to(source/'portable').parts)&{'local','__pycache__','.pytest_cache'})
    else:
        changed=subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=source).strip()
        if changed:raise ValueError('Tracked source changes must be committed before final export')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source).decode().strip()
    packed=json.loads((source/'portable/packed-manifest.json').read_bytes())['files']
    excluded={x['target'] for x in packed}
    destination.mkdir(parents=True);root=destination/'project';root.mkdir()
    files={};size=0
    for name in sorted(names):
        original=source/name
        if original.is_symlink() or not original.is_file():raise ValueError('Expected regular source file: '+name)
        files[name]=digest(original);size+=original.stat().st_size
        if name in excluded:continue
        if original.stat().st_size>=100*1024*1024:raise ValueError('Unpacked source exceeds GitHub limit: '+name)
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
        if digest(target)!=files[name]:raise ValueError('Copy differs: '+name)
    manifest={'schema':1,'source_commit':commit,'source_branch':subprocess.check_output(['git','branch','--show-current'],cwd=source).decode().strip(),'created_at':datetime.now(timezone.utc).isoformat(),'preview':preview,'files':files}
    (root/'portable/SOURCE_TREE.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    for p in (source/'portable/export-root').iterdir():shutil.copyfile(p,destination/p.name)
    result={'status':'copied','source_commit':commit,'preview':preview,'project_files':len(files),'original_bytes':size,'packed_original_files':[x for x in excluded if x in files],'dashboard_sha256':files['output/inflation_dashboard_r35/index.html']}
    (destination/'TRANSFER_VERIFICATION.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    # Exact explicit paths let the packager preserve historically tracked ignored files.
    stage=['project/'+x for x in names if x not in excluded]+['project/portable/SOURCE_TREE.json','TRANSFER_VERIFICATION.json']+[p.name for p in (source/'portable/export-root').iterdir()]
    (destination/'STAGE_PATHS.txt').write_bytes(('\0'.join(sorted(stage))+'\0').encode())
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--destination',type=Path,required=True);p.add_argument('--preview',action='store_true');a=p.parse_args();print(json.dumps(export(a.source,a.destination,a.preview),indent=2))
