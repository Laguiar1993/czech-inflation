"""Create a compact category-momentum view around the immutable R34 forecast."""
import argparse,copy,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from tools.live_bundle_r32.adapter import checked_files,required
from tools.momentum_r35.build import load as load_analysis,clean
from tools.inflation_dashboard_r34.build import R32_INIT,R33_INIT

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
PARENT=ROOT/'output/inflation_dashboard_r34'
RETAINED=('current_path','live','replay','forecast_context','archive_path')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def key(p):return Path(p).resolve().relative_to(ROOT).as_posix()

def verify_retained(before,after):
    for name in RETAINED:
        if name not in after or after[name]!=before[name]:raise ValueError('Recorded forecast/replay changed: '+name)
    return True

def assemble(analysis_dir,rehearsal=False):
    m=json.loads((PARENT/'manifest.json').read_bytes());files=checked_files(PARENT,m['outputs'])
    checked_files(ROOT,m['inputs']);checked_files(ROOT,m['code'])
    parent=json.loads(required(files,'dashboard_data.json'));data=copy.deepcopy(parent)
    directory=Path(analysis_dir).resolve();momentum=load_analysis(directory)
    if not rehearsal and momentum['mode']!='current_analysis':raise ValueError('Canonical dashboard requires final analysis')
    data['category_momentum']=momentum;data['schema_version']=4
    data['sources'].insert(0,dict(name='Category momentum · current analysis',through=momentum['month'],source='CZSO CEN0101E + Census X-13',status='37 groups; fixed 2026 weights; source and adjustment evidence archived'))
    for row in data['sources']:
        if row['name']=='37 CPI groups & rents':row.update(name='37 CPI groups · prior monitor archive',status='Older July view retained under Data & reliability; current analysis listed above')
    data['snapshot_date']=momentum['completed_at'][:10]
    data=clean(data);verify_retained(parent,data)
    data['fingerprint']=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    inputs={key(PARENT/'manifest.json'):sha(PARENT/'manifest.json'),key(PARENT/'dashboard_data.json'):sha(PARENT/'dashboard_data.json'),key(directory/'manifest.json'):sha(directory/'manifest.json'),key(directory/'momentum.json'):sha(directory/'momentum.json')}
    return data,inputs

def build(analysis_dir,output,rehearsal=False):
    out=Path(output).resolve()
    if not out.is_relative_to(ROOT) or out.exists():raise ValueError('Choose a new dashboard directory')
    data,inputs=assemble(analysis_dir,rehearsal)
    modules=[ROOT/('tools/inflation_dashboard_r'+str(n)) for n in (32,33,34,35)]
    code={key(p):sha(p) for folder in modules for p in folder.iterdir() if p.is_file()}
    apps=[]
    for i,folder in enumerate(modules):
        s=(folder/'app.js').read_text(encoding='utf-8')
        if i<3:
            init=R32_INIT if i==0 else R33_INIT
            if s.count(init)!=1:raise ValueError('Inherited initialization changed')
            s=s.replace(init,'')
        apps.append(s)
    encoded=json.dumps(data,ensure_ascii=False,allow_nan=False)
    safe=encoded.replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    html=(HERE/'template.html').read_text(encoding='utf-8').replace('/*__DATA__*/null',safe).replace('/*__STYLE__*/','\n'.join((f/'style.css').read_text(encoding='utf-8') for f in modules)).replace('/*__APP__*/','\n'.join(apps))
    out.mkdir(parents=True);(out/'.gitattributes').write_bytes(b'* -text\n')
    (out/'index.html').write_text(html,encoding='utf-8',newline='\n');(out/'dashboard_data.json').write_text(encoded,encoding='utf-8',newline='\n')
    (out/'manifest.json').write_text(json.dumps(dict(schema='inflation-dashboard-r35/v1',rehearsal=rehearsal,built_at=datetime.now(timezone.utc).isoformat(),inputs=inputs,code=code,outputs={p.name:sha(p) for p in out.iterdir() if p.is_file()}),indent=2),encoding='utf-8',newline='\n')
    return dict(page=str(out/'index.html'),category_month=data['category_momentum']['month'],forecast_origin=data['current_path']['meta']['origin'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rehearsal',action='store_true')
    a=p.parse_args();print(json.dumps(build(a.analysis,a.output,a.rehearsal)))
if __name__=='__main__':main()
