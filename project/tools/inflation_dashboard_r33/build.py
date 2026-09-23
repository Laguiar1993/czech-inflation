"""Build a new portable R33 snapshot; never overwrite an existing snapshot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from tools.inflation_dashboard_r32 import build as base
from .analysis import assemble

ROOT=base.ROOT
HERE=Path(__file__).resolve().parent
INIT='renderStatic();reportOptions();renderModelToggles();renderScores();navigate(location.hash.slice(1)||"overview",false);'

def current_forecast(directory,data):
    from tools.forecast_updates_r33.workflow import load_run
    record=load_run(directory)
    if record['mode']!='prospective':raise ValueError('Current card requires a prospective record')
    if record['target']!=data['live']['target']:raise ValueError('Current record target does not match next release')
    return dict(status='recorded',target=record['target'],point=record['forecast']['point'],
                components=record['forecast']['components'],as_of=record['as_of'],recorded_at=record['recorded_at'],
                model=record['model'],reason='Recorded prospective nowcast; the monthly path retains its own archived origin.')

def build(out,old_run=None,new_run=None,current_run=None):
    out=out.resolve()
    if not out.is_relative_to(ROOT) or out.exists():
        raise ValueError('Output must be a new directory within the repository')
    if bool(old_run)!=bool(new_run):
        raise ValueError('Provide both old and new validated run directories')
    data=assemble()
    extra_inputs=[]
    if current_run:
        current_run=Path(current_run).resolve()
        if not current_run.is_relative_to(ROOT):raise ValueError('Current archive must be within the repository')
        data['live']=current_forecast(current_run,data)
        data['sources'].insert(0,dict(name='Recorded BASE nowcast',through=data['live']['as_of'],source='Bloomberg plus sourced CNB observed supplements',status='Prospective current run; archived path separate'))
        extra_inputs.extend(p for p in current_run.rglob('*') if p.is_file())
        data['snapshot_date']=datetime.now(timezone.utc).date().isoformat()
    if old_run:
        old_run,new_run=Path(old_run).resolve(),Path(new_run).resolve()
        if not all(p.is_relative_to(ROOT) for p in (old_run,new_run)):
            raise ValueError('Run archives must be within the repository')
        from tools.forecast_updates_r33.workflow import compare_runs
        revision=compare_runs(old_run,new_run)
        if revision['status']!='ok':
            raise ValueError('Revision export rejected: '+revision['reason'])
        data['revision']=dict(revision,status='available')
        for directory in (old_run,new_run):
            extra_inputs.extend(p for p in Path(directory).rglob('*') if p.is_file())
    data['fingerprint']=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    encoded=json.dumps(data,ensure_ascii=False,allow_nan=False)
    safe=encoded.replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    app=(base.HERE/'app.js').read_text(encoding='utf-8')
    if app.count(INIT)!=1:raise ValueError('Sealed base initialization changed')
    app=app.replace(INIT,'')+'\n'+(HERE/'app.js').read_text(encoding='utf-8-sig')
    style=(base.HERE/'style.css').read_text(encoding='utf-8')+'\n'+(HERE/'style.css').read_text(encoding='utf-8-sig')
    html=(HERE/'template.html').read_text(encoding='utf-8-sig').replace('/*__DATA__*/null',safe).replace('/*__APP__*/',app).replace('/*__STYLE__*/',style)
    code=[p for directory in (HERE,base.HERE,ROOT/'tools/forecast_updates_r33') for p in directory.glob('*') if p.is_file()]
    inputs=[ROOT/p for p in base.INPUTS.values()]+[ROOT/'data/core_split/canonical_metadata.json',ROOT/'data/core_split/manifest.json',ROOT/'output/bloomberg_core_check_r33/diagnosis.json',ROOT/'output/bloomberg_core_check_r33/manifest.json']+extra_inputs
    key=lambda p:str(p.relative_to(ROOT)).replace('\\','/')
    input_hashes={key(p):base.digest(p) for p in inputs}
    code_hashes={key(p):base.digest(p) for p in code}
    # Validate every source/path before producing any output bytes.
    out.mkdir(parents=True)
    (out/'.gitattributes').write_text('* -text\n',encoding='utf-8')
    (out/'index.html').write_text(html,encoding='utf-8')
    (out/'dashboard_data.json').write_text(encoded,encoding='utf-8')
    manifest=dict(built_at_utc=datetime.now(timezone.utc).isoformat(),snapshot_date=data['snapshot_date'],live_forecast=data['live']['status']=='recorded',
        inputs=input_hashes,code=code_hashes,
        outputs={p.name:base.digest(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(dict(page=str(out/'index.html'),live=data['live']['status']=='recorded',official_release='2026-08',detailed_panel='2026-07',model_origin='2026-07')))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--old-run',type=Path)
    parser.add_argument('--new-run',type=Path)
    parser.add_argument('--current-run',type=Path)
    args=parser.parse_args()
    build(args.output if args.output.is_absolute() else ROOT/args.output,args.old_run,args.new_run,args.current_run)
