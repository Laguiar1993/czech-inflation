"""Verified R34 data assembly and create-only portable dashboard export."""
import argparse
from datetime import datetime,timezone
import hashlib
import io
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from tools.live_bundle_r32 import adapter
from tools.current_path_r34.run import load_record,PRIMARY,BLOCKS,clean_json
from tools.forecast_context_r34.build import assemble as context_assemble
from tools.inflation_dashboard_r33.analysis import explain_gap
from tools.inflation_dashboard_r32.build import quarter_average
from tools.cnb_tracker.component_gaps import BLOCK_MAP,WEIGHT,model_block_rates,annual_rates,cnb_weight

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
PARENT=ROOT/'output/inflation_dashboard_r33'
CNB=ROOT/'data/cnb_mpr_tables_20260917/cnb_mpr_indicators_long.csv'
R32_INIT='renderStatic();reportOptions();renderModelToggles();renderScores();navigate(location.hash.slice(1)||"overview",false);'
R33_INIT="renderStatic();reportOptions();renderModelToggles();renderScores();navigate(location.hash.slice(1)||'overview',false);visitMessage();"

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def key(path):return Path(path).resolve().relative_to(ROOT).as_posix()

def h0_rates(contributions,weights):
    if set(contributions)!=set(BLOCKS) or not all(math.isfinite(float(v)) for v in contributions.values()):raise ValueError('Complete finite recorded h0 components required')
    names=dict(core='core',food='food',fuel='fuel',administered='administered',alcohol_tobacco='alc')
    if any(k not in weights or not math.isfinite(float(weights[k])) or weights[k]<=0 for k in names.values()):raise ValueError('Positive recorded component weights required')
    if abs(sum(weights[k] for k in names.values())-1)>1e-8:raise ValueError('Recorded weights do not sum to one')
    return {b:float(contributions[b])/float(weights[k]) for b,k in names.items()}

def full_quarters(points):
    months=[p[0] for p in points]
    if len(set(months))!=len(months):raise ValueError('Duplicate monthly points')
    quarters=sorted({m[:4]+'Q'+str((int(m[5:])-1)//3+1) for m in months})
    return [dict(quarter=q,value=v) for q in quarters if (v:=quarter_average(points,q)) is not None]

def verify_parent():
    manifest=json.loads((PARENT/'manifest.json').read_bytes())
    files=adapter.checked_files(PARENT,manifest['outputs'])
    adapter.checked_files(ROOT,manifest['inputs']);adapter.checked_files(ROOT,manifest['code'])
    return json.loads(adapter.required(files,'dashboard_data.json'))

def current_gaps(meta,table,points,report,bundle,nowcast_run):
    replay_manifest=json.loads((ROOT/'output/cnb_rounds_v3/manifest.json').read_bytes())
    if digest(CNB)!=replay_manifest['inputs'][key(CNB)]:raise ValueError('Frozen CNB table hash mismatch')
    cnb=pd.read_csv(CNB,float_precision='round_trip')
    frames=adapter.load_bundle(bundle,ROOT).frames;t=pd.Period(meta['origin'],'M')
    actual=pd.concat([frames['core'].core,frames['components'].food,frames['components'].fuel,
                      frames['regulated'].regulated.rename('administered'),frames['alcohol'].alcohol_tobacco],axis=1)
    actual=actual.loc[actual.index<t]
    forecast=json.loads((nowcast_run/'adapter.json').read_bytes())['forecast']
    rates=h0_rates(forecast['main_contributions_pp'],forecast['weights'])
    block_monthly,weights=model_block_rates(table[table.model.eq(PRIMARY)],actual,t,h0_blocks=rates)
    yearly=annual_rates(block_monthly);out=[]
    for q in report['cnb']:
        mine=quarter_average(points,q['quarter'])
        if mine is None:continue
        span=pd.period_range(pd.Period(q['quarter'],'Q').asfreq('M','start'),pd.Period(q['quarter'],'Q').asfreq('M','end'),freq='M')
        parts={};block_details=[]
        for block in BLOCK_MAP:
            hit=cnb[cnb.report_date.eq(report['report_date'])&cnb.frequency.eq('Q')&cnb.indicator.eq(block)&cnb.period.eq(q['quarter'])]
            ours=yearly[block].reindex(span)
            if len(hit)!=1 or not ours.notna().all():parts[block]=float('nan');continue
            theirs=float(hit.value.iloc[0]);w=cnb_weight(hit.row_label.iloc[0])
            parts[block]=weights[block]*float(ours.mean())-w*theirs
            block_details.append(dict(block=block,model_rate=float(ours.mean()),cnb_rate=theirs,model_weight=weights[block],cnb_weight=w))
        gap=mine-q['value'];complete=all(np.isfinite(list(parts.values())))
        parts['unexplained']=gap-sum(parts.values()) if complete else float('nan')
        explained=explain_gap(dict(quarter=q['quarter'],complete=complete,parts=parts,gap=gap,model=mine,cnb=q['value']))
        explained['block_rates']=block_details;out.append(explained)
    return out

def assemble(path_run,*,rehearsal=False):
    path_run=Path(path_run).resolve();meta,table,history=load_record(path_run)
    if meta['mode']!='prospective' and not rehearsal:raise ValueError('Canonical dashboard requires a prospective path record')
    data=verify_parent()
    bundle=ROOT/meta['nowcast_bundle'];nowcast_run=ROOT/meta['h0_run']
    primary=table[table.model.eq(PRIMARY)].sort_values('h')
    if meta['origin']!=data['live']['target'] or abs(meta['h0']-data['live']['point'])>1e-12:raise ValueError('Path and displayed nowcast disagree')
    context=context_assemble(as_of=meta['as_of'],bundle=bundle,record=nowcast_run,
                             ledger_input=dict(history_mm={str(k):float(v) for k,v in history.items()},forecast_mm={r.target:float(r.mm_forecast) for r in primary.itertuples()}))
    ledger=context['base_effect_ledger']
    if not np.allclose([r['yy'] for r in ledger],primary.yy_exante,atol=1e-10,rtol=0):raise ValueError('Exact base ledger differs from forecast compounding')
    annual=100*np.expm1(np.log1p(history/100).rolling(12,min_periods=12).sum())
    realised=[[str(m),float(v)] for m,v in annual.dropna().tail(24).items()]
    points=realised[-2:]+[[r.target,float(r.yy_exante)] for r in primary.itertuples()]
    report=data['replay']['reportsByClock']['report'][-1]
    if pd.Timestamp(report['report_date'],tz='Europe/Prague')>pd.Timestamp(meta['as_of']):raise ValueError('CNB report postdates current path')
    current=dict(meta=meta,rows=primary.to_dict('records'),models={m:g.sort_values('h').to_dict('records') for m,g in table.groupby('model')},
                 realised=realised,points=points,quarter_means=full_quarters(points),latest_cnb=report,
                 gaps=current_gaps(meta,table,points,report,bundle,nowcast_run),ledger=ledger)
    data.update(schema_version=3,current_path=current,forecast_context=context,snapshot_date=meta['recorded_at'][:10])
    data['vintages']['model_origin']=meta['origin']
    for row in data['sources']:
        if row['name']=='Independent path':row.update(through=meta['as_of'],source='Fresh R27 run · Bloomberg plus dated official supplements',status='September-origin h0-h12 re-estimated; recorded h0 retained')
        elif row['name']=='Recorded BASE nowcast':row['status']='Prospective September nowcast; same h0 anchors the fresh path'
        elif row['name']=='Farm prices':row.update(name='Farm prices · monitor archive',status='July analytical cards; fresh path separately uses August')
        elif row['name']=='Food PPI':row.update(name='Food PPI · monitor archive',status='July analytical cards; fresh path separately uses August')
        elif row['name']=='Core & regulated CPI':row.update(name='Core & regulated CPI · Bloomberg archive',status='August forecast observations supplied separately by CNB ARAD')
    prov=meta['source_provenance']
    data['sources'].extend([
        dict(name='Forecast core & regulated CPI',through=prov['consumer_coverage']['core'],source='CNB ARAD observed supplement',status='August observations; separate from CNB forecasts'),
        dict(name='Path farm prices · four-product basket',through=prov['coverage']['agri4']['last'],source='CZSO CEN0203B · fresh official capture',status='Observed wheat, milk, pigs and chickens; historical training rows retained'),
        dict(name='Path food PPI',through=prov['coverage']['food_ppi']['last'],source='Bloomberg CZPPA10M · fresh capture',status='Accepted cumulated level; historical training rows retained'),
        dict(name='Path gross pump prices',through=prov['pump_coverage']['last'],source='Bloomberg EC bulletin observations',status='Weekly gross prices; availability clock checked'),
    ])
    data['sources'].insert(1,dict(name='Path price-index inputs',through='2026-08',source='Bloomberg CZCPI / CZCPF / CZPPA10M',status='Exact index-ratio headline history; accepted food-level transforms'))
    data['sources'].insert(2,dict(name='Path availability audit',through=meta['as_of'],source='Verified path-input provenance',status='Upstream series have separate release lags; inspect source files'))
    data=clean_json(data)
    data['fingerprint']=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()
    inputs={key(PARENT/'manifest.json'):digest(PARENT/'manifest.json'),key(PARENT/'dashboard_data.json'):digest(PARENT/'dashboard_data.json'),key(CNB):digest(CNB),
            key(ROOT/'output/cnb_rounds_v3/manifest.json'):digest(ROOT/'output/cnb_rounds_v3/manifest.json'),**context['sources']['inputs']}
    for p in path_run.rglob('*'):
        if p.is_file():inputs[key(p)]=digest(p)
    return data,inputs

def build(output,path_run,*,rehearsal=False):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT) or output.exists():raise ValueError('Choose a NEW dashboard directory within the repository')
    data,inputs=assemble(path_run,rehearsal=rehearsal)
    modules=[ROOT/'tools/inflation_dashboard_r32',ROOT/'tools/inflation_dashboard_r33',HERE,ROOT/'tools/forecast_context_r34']
    code={key(p):digest(p) for directory in modules for p in directory.glob('*') if p.is_file()}
    app=(modules[0]/'app.js').read_text(encoding='utf-8');r33=(modules[1]/'app.js').read_text(encoding='utf-8')
    if app.count(R32_INIT)!=1 or r33.count(R33_INIT)!=1:raise ValueError('Parent initialization contract changed')
    app=app.replace(R32_INIT,'')+'\n'+r33.replace(R33_INIT,'')+'\n'+(HERE/'app.js').read_text(encoding='utf-8')
    style='\n'.join((d/'style.css').read_text(encoding='utf-8') for d in modules[:3])
    encoded=json.dumps(data,ensure_ascii=False,allow_nan=False)
    safe=encoded.replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    html=(HERE/'template.html').read_text(encoding='utf-8').replace('/*__DATA__*/null',safe).replace('/*__STYLE__*/',style).replace('/*__APP__*/',app)
    output.mkdir(parents=True)
    (output/'.gitattributes').write_text('* -text\n',encoding='utf-8')
    (output/'index.html').write_text(html,encoding='utf-8')
    (output/'dashboard_data.json').write_text(encoded,encoding='utf-8')
    (output/'forecast_context.json').write_text(json.dumps(data['forecast_context'],ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    manifest=dict(built_at_utc=datetime.now(timezone.utc).isoformat(),schema='inflation-dashboard-r34/v1',rehearsal=rehearsal,inputs=inputs,code=code,
                  outputs={p.name:digest(p) for p in output.iterdir() if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return dict(page=str(output/'index.html'),origin=data['current_path']['meta']['origin'],path_mode=data['current_path']['meta']['mode'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--path-run',type=Path,required=True);p.add_argument('--rehearsal',action='store_true')
    a=p.parse_args();print(json.dumps(build(a.output,a.path_run,rehearsal=a.rehearsal)))
if __name__=='__main__':main()
