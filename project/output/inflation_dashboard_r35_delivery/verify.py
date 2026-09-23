"""Read-only checks of R35 analysis, browser evidence and preserved R34 records."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.momentum_r35.build import load
from tools.inflation_dashboard_r35.build import verify_retained

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def audit():
    analysis=ROOT/'output/momentum_r35/final';page=ROOT/'output/inflation_dashboard_r35'
    data=load(analysis)
    assert data['mode']=='current_analysis' and data['month']=='2026-08'
    counts={}
    for folder in [analysis,page]:
        manifest=json.loads((folder/'manifest.json').read_bytes());n=0
        for kind in ['inputs','code','outputs']:
            for rel,digest in manifest.get(kind,{}).items():
                f=(folder if kind=='outputs' else ROOT)/rel
                assert sha(f)==digest,str(f)
                n+=1
        counts[folder.relative_to(ROOT).as_posix()]=n
    fits=0
    for f in (analysis/'x13').rglob('manifest.json'):
        for name,digest in json.loads(f.read_bytes())['files'].items():assert sha(f.parent/name)==digest,str(f.parent/name)
        fits+=1
    current=json.loads((page/'dashboard_data.json').read_bytes())
    before=json.loads((ROOT/'output/inflation_dashboard_r34/dashboard_data.json').read_bytes())
    assert verify_retained(before,current) and current['category_momentum']==data
    seal=json.loads((ROOT/'output/inflation_dashboard_r34_delivery/DELIVERY_MANIFEST.json').read_bytes())
    files=seal['files']
    for rel,digest in files.items():
        if isinstance(digest,dict):digest=digest['sha256']
        assert sha(ROOT/rel)==digest,rel
    browser=json.loads((Path(__file__).parent/'browser/checks.json').read_bytes())
    assert browser['status']=='passed' and browser['pageErrors']==[]
    assert abs(sum(r['weight'] for r in data['rows'])-1000)<1e-6
    assert data['driver_complete'] and abs(sum(r['value'] for r in data['drivers'])-data['driver_total_log_pp'])<1e-10
    ownseal=Path(__file__).parent/'DELIVERY_MANIFEST.json'
    if ownseal.exists():
        for rel,digest in json.loads(ownseal.read_bytes())['files'].items():assert sha(ROOT/rel)==digest,rel
    return dict(status='passed',hash_counts=counts,x13_archives=fits,preserved_r34_hashes=len(files),category_month=data['month'],
        categories=len(data['rows']),groups=len(data['groups']),coverage=data['breadth']['coverage'],
        preserved_forecast_origin=current['current_path']['meta']['origin'],retained_forecast_and_replay=True,
        analysis_as_of=data['as_of'],analysis_completed_at=data['completed_at'],browser=browser,
        driver_total_log_pp=data['driver_total_log_pp'])
if __name__=='__main__':print(json.dumps(audit(),indent=2))
