"""Read-only audit of the R34 delivery and preserved earlier snapshots."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.current_path_r34.run import load_record
from tools.inflation_dashboard_r33.analysis import scenario_path

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def audit():
    meta,table,history=load_record(ROOT/'output/current_path_r34/final')
    assert meta['mode']=='prospective' and meta['origin']=='2026-09' and len(table)==39
    counts={}
    for folder in ['output/current_path_r34/final','output/inflation_dashboard_r34','output/inflation_dashboard_r33','output/inflation_dashboard_r32']:
        p=ROOT/folder;m=json.loads((p/'manifest.json').read_bytes());n=0
        for kind in ['inputs','code','outputs']:
            for rel,expected in m.get(kind,{}).items():
                f=(p if kind=='outputs' else ROOT)/rel
                assert digest(f)==expected,str(f)
                n+=1
        counts[folder]=n
    for manifest in (ROOT/'output/current_path_r34_inputs').rglob('MANIFEST.json'):
        m=json.loads(manifest.read_bytes());files=m['files'] if 'files' in m else m['sha256']
        for name,expected in files.items():
            if isinstance(expected,dict):expected=expected['sha256']
            assert digest(manifest.parent/name)==expected,str(manifest.parent/name)
        counts[manifest.parent.relative_to(ROOT).as_posix()]=len(files)
    m=json.loads((ROOT/'output/forecast_updates_r33/FINAL_DELIVERY_MANIFEST.json').read_bytes())
    for rel,expected in m['files'].items():
        if isinstance(expected,dict):expected=expected['sha256']
        assert digest(ROOT/rel)==expected,rel
    counts['output/forecast_updates_r33/FINAL_DELIVERY_MANIFEST.json']=len(m['files'])
    d=json.loads((ROOT/'output/inflation_dashboard_r34/dashboard_data.json').read_bytes())
    parent=json.loads((ROOT/'output/inflation_dashboard_r33/dashboard_data.json').read_bytes())
    assert d['replay']==parent['replay'] and d['archive_path']==parent['archive_path']
    assert all(r['mm_forecast']==d['live']['point'] for r in table[table.h.eq(0)].to_dict('records'))
    rows=[dict(month=r['target'],model_mm=r['mm_forecast'],implied_yy_model=r['yy_exante'],forecast_kind='rebased') for r in d['current_path']['rows']]
    expected=scenario_path(rows,.05,.02,.3)
    js=json.loads((ROOT/'output/inflation_dashboard_r34_delivery/scenario-js.json').read_bytes())
    error=max(abs(a['scenario_yy']-e['scenario_yy']) for a,e in zip(js,expected))
    assert len(js)==len(expected)==13 and error<1e-10
    ledger=d['current_path']['ledger'];assert all(abs(r['base_effect_pp']+r['new_price_pp']-r['change_pp'])<1e-10 for r in ledger)
    recent=[r for r in ledger if r['month']<='2026-12']
    return dict(verified_hash_counts=counts,rows=len(table),canonical_record={k:meta[k] for k in ['mode','origin','as_of','completed_at','h0','h0_as_of']},
        historical_replay_unchanged=True,july_archive_unchanged=True,scenario_js_python_error=error,
        august_to_december=dict(start_yy=recent[0]['previous_yy'],end_yy=recent[-1]['yy'],old_month_removal_pp=sum(r['base_effect_pp'] for r in recent),new_months_pp=sum(r['new_price_pp'] for r in recent)))
if __name__=='__main__':print(json.dumps(audit(),indent=2))
