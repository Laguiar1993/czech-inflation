"""Build a byte-preserving working ZIP; retain the full repository separately."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def build(repository,trace,destination):
    repository=Path(repository).resolve();root=repository/'project';destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError(destination)
    tracked={x for x in subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0') if x}
    evidence=json.loads(Path(trace).read_bytes());reads=set(evidence['files']);selected=set()
    production=('forecast_updates_r33','live_bundle_r32','current_path_r34','current_path_r34_inputs','momentum_r35','momentum_r35_inputs','inflation_dashboard_r35','inflation_dashboard_r35_delivery','inflation_dashboard_r34','inflation_dashboard_r34_delivery','forecast_context_r34')
    for name in tracked:
        parts=Path(name).parts;top=parts[0]
        if len(parts)==1 or top in {'models','tools','docs','tests','portable','evaluation','backtest'}:
            selected.add(name)
        elif top=='data' and (len(parts)<2 or parts[1] not in {'paper_replication','research_r14'}):selected.add(name)
        elif top=='output' and len(parts)>1 and parts[1] in production:selected.add(name)
    selected|=reads&tracked
    selected.discard('portable/SOURCE_TREE.json')
    # Audit reads cover validation of exact saved inputs; include whole archived
    # prepared/capture packages so new preparation can validate their manifests.
    required_folders=['data/paper_replication','data/research_r14']
    for prefix in required_folders:
        for name in sorted(reads&tracked):
            if name.startswith(prefix+'/') and Path(name).name.lower() in {'manifest.json','provenance.json'}:
                parent=Path(name).parent.as_posix()+'/'
                selected.update(n for n in tracked if n.startswith(parent))
    missing=reads-selected
    missing={n for n in missing if n not in {'portable/SOURCE_TREE.json'} and not n.startswith('portable/local/')}
    if missing:raise ValueError('Unshipped trace dependencies: '+str(sorted(missing)))
    source_manifest=json.loads((root/'portable/SOURCE_TREE.json').read_bytes());expected={}
    for name in sorted(selected):
        actual=sha(root/name)
        if name in source_manifest['files'] and actual!=source_manifest['files'][name]:raise ValueError('Frozen source bytes changed: '+name)
        expected[name]=actual
    # Keep all existing portable restore commands valid, including the old DB.
    packed=json.loads((root/'portable/packed-manifest.json').read_bytes())['files']
    for item in packed:
        if item['target'] in source_manifest['files']:expected[item['target']]=item['sha256']
    manifest=dict(schema=1,profile='compact-working',source_commit=source_manifest['source_commit'],repository_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repository).decode().strip(),full_source_manifest_sha256=sha(root/'portable/SOURCE_TREE.json'),files=expected,
        omitted_note='Historical evaluation outputs, scratch files and unused raw research downloads remain in the full repository; all model source files and validated production dependencies are retained.')
    readme=r"""# Czech inflation â€” smaller working download

Extract the ZIP completely, then double-click **open-dashboard.cmd** to open the exact R35 page. No installation or login is needed to view it.

This package includes every model source file, the production nowcast/path inputs, Bloomberg and public-input tools, the manual-input guide, X-13, and setup files. Old bulk backtest outputs, scratch files and unused raw research downloads remain in the full repository. Historical research reruns that need those excluded archives should use the full repository.

For Bloomberg/model setup, open **project/portable/START_HERE.md** and follow its environment and operating commands. For exact manual sources and formats, open **project/portable/MANUAL_INPUTS.md**. Those archived guides also describe the full repository; the compact inventory is defined here and in project/portable/SOURCE_TREE.json.

From the project folder, after environment setup:

```powershell
& .\.venv\Scripts\python.exe -E -s -B -m portable restore
& .\.venv\Scripts\python.exe -E -s -B -m portable verify --models
& .\.venv\Scripts\python.exe -E -s -B -m portable doctor --bloomberg
```

The delivered page is the saved R35 snapshot. New model runs write new records; they do not automatically overwrite it.

Full archive: https://github.com/Laguiar1993/czech-inflation
"""
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9,allowZip64=True) as z:
        prefix='czech-inflation-small/'
        for name in sorted(selected):z.write(root/name,prefix+'project/'+name)
        z.writestr(prefix+'project/portable/SOURCE_TREE.json',json.dumps(manifest,indent=2)+'\n')
        z.writestr(prefix+'README.md',readme)
        z.write(repository/'open-dashboard.cmd',prefix+'open-dashboard.cmd')
    result={'profile':'compact-working','zip':destination.name,'bytes':destination.stat().st_size,'sha256':sha(destination),'source_project_files':len(selected),'model_source_files':len([n for n in selected if n.startswith('models/')]),'full_model_source_files':len([n for n in tracked if n.startswith('models/')]),'dashboard_sha256':sha(root/'output/inflation_dashboard_r35/index.html'),'omitted_files':len(tracked-selected),'manifest_generated_for_subset':True}
    if result['model_source_files']!=result['full_model_source_files']:raise ValueError('Model source omitted')
    with zipfile.ZipFile(destination) as z:
        bad=z.testzip()
        if bad:raise ValueError('Corrupt ZIP member '+bad)
    destination.with_suffix('.manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repository',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--trace',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.repository,a.trace,a.output),indent=2))
