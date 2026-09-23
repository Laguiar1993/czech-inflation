"""Recombine only predeclared R14 paths; exact headline and external benchmarks."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from path_improvements_experiment_r12 import read,sha,dump,score_panel,add_outcomes_and_compound
from independent_bridge_experiment import match_cnb_quarters,_quarter_metrics

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/research_r14/integration'
PRIMARY=('PIPELINE_FOOD_FUEL_R14','PIPELINE_GAP_RIDGE_R14','PIPELINE_GAP_RF_R14')
BASE='INDEPENDENT_BRIDGE'
BLOCKS=('core','food','administered','alcohol_tobacco','fuel','wedge')
CORE_FOR={PRIMARY[0]:None,PRIMARY[1]:'CORE_GAP_RIDGE_R14',PRIMARY[2]:'CORE_GAP_RF_R14'}


def combine_components(baseline,food,fuel,core,name):
    """Fail closed on mismatched clocks/weights; missing component stays missing."""
    keys=['origin','h'];base=baseline.sort_values(keys).reset_index(drop=True).copy()
    out=base.copy();weightcols=[c for c in base if c.startswith('weight_')]
    for block,candidate in [('food',food),('fuel',fuel),('core',core)]:
        if candidate is None:continue
        c=candidate.sort_values(keys).reset_index(drop=True)
        if c.duplicated(keys).any() or len(c)!=len(base) or not c[keys].equals(base[keys]):
            raise ValueError('Component keys differ from base')
        if not c.as_of_utc.equals(base.as_of_utc):raise ValueError('Component clock differs from base')
        if not c[weightcols].equals(base[weightcols]):raise ValueError('Component weights differ from base')
        future=base.h.gt(0)
        for column in ('value_'+block,'contribution_'+block):out.loc[future,column]=c.loc[future,column]
    future=base.h.gt(0)
    out.loc[future,'mm_forecast']=out.loc[future,['contribution_'+b for b in BLOCKS]].sum(axis=1,min_count=6)
    out['model']=name;out['yy_exante']=np.nan;out['yy_conditional']=np.nan
    out['status']=np.where(np.isfinite(out.mm_forecast),'research_estimated','unavailable_component')
    for field in ('fallback_used','origin_status','converged'):
        if field in base:out['legacy_source_'+field]=base[field]
    out['converged']=np.isfinite(out.mm_forecast)
    complete=out.groupby('origin').converged.transform('all')
    out['origin_status']=np.where(complete,'research_estimated','unavailable_component')
    # The bridge fallback flag concerns its food block. Both replacement food
    # engines fail closed rather than substitute a fallback. Keep the source
    # flag explicitly; only retain it when that original food is actually used.
    out['fallback_used']=base.get('fallback_used',False) if food is None else False
    out['fuel_fallback_used']=False
    if fuel is not None and 'fallback_used' in fuel:
        out['fuel_fallback_used']=fuel.sort_values(keys).reset_index(drop=True).fallback_used.fillna(False).astype(bool)
        out.loc[future,'fallback_used'] |= out.loc[future,'fuel_fallback_used']
    return out


def survey_h12(path):
    """Annual CPI at t+12 uses precisely h1..12; h0 is mathematically irrelevant."""
    q=np.asarray([path.get(h,np.nan) for h in range(1,13)],dtype=float)
    return float(100*np.expm1(np.log1p(q/100).sum())) if np.isfinite(q).all() and (q>-100).all() else np.nan


def dependencies():
    names=['path_integration_r14.py','test_path_integration_r14.py','path_improvements_experiment_r12.py',
       'independent_bridge_experiment.py','models/path_inputs.py','docs/implementation/R14_EXPERIMENT_PLAN_2026-09-09.md',
       'data/cnb_mpr_cpi_quarterly.csv','output/independent_bridge_forecasts.csv','output/independent_path_frozen_inputs.csv']
    for block in ('core','food','fuel'):
        manifest=ROOT/f'output/research_r14/{block}/manifest.json'
        obj=json.loads(manifest.read_text())
        payloads=obj.get('outputs',obj.get('output_hashes',{}))
        for relative,digest in payloads.items():
            p=manifest.parent/relative
            if not p.exists():p=ROOT/relative
            if sha(p)!=digest:raise AssertionError(f'Component payload changed: {p}')
        names.extend([str(manifest.relative_to(ROOT)),f'output/research_r14/{block}/native_forecasts.csv'])
    return {n:sha(ROOT/n) for n in names}


def comparison_scores(frame,models):
    tables=[score_panel(frame,[BASE,*PRIMARY],'combined_common'),score_panel(frame,models,'all_research_common')]
    for m in models:
        tables.append(score_panel(frame,[m],'own_coverage'))
        if m!=BASE:tables.append(score_panel(frame,[BASE,m],f'paired_{m}'))
    return pd.concat(tables,ignore_index=True)


def bootstrap(frame,models):
    rng=np.random.default_rng(1409);rows=[]
    for sample,mask in [('full',np.ones(len(frame),bool)),('recent_targets',frame.target>='2024-01'),('recent_origins',frame.origin>='2024-01')]:
        for h in range(1,13):
            g=frame.loc[mask&frame.h.eq(h)].copy();g['error']=g.yy_exante-g.yy_actual
            wide=g.pivot(index='origin',columns='model',values='error')
            for m in models:
                if m==BASE:continue
                p=wide[[m,BASE]].dropna();n=len(p)
                if not n:continue
                d=(p[m]**2-p[BASE]**2).to_numpy();starts=rng.integers(0,n,(2000,int(np.ceil(n/12))))
                ix=((starts[:,:,None]+np.arange(12))%n).reshape(2000,-1)[:,:n]
                lo,hi=np.quantile(d[ix].mean(axis=1),[.025,.975])
                rows.append(dict(sample=sample,h=h,model=m,n=n,mse_difference=float(d.mean()),lower=float(lo),upper=float(hi),block=12,draws=2000,seed=1409))
    return pd.DataFrame(rows)


def generate(folder=OUT):
    inputs=dependencies();folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    base=pd.read_csv(ROOT/'output/independent_bridge_forecasts.csv',float_precision='round_trip')
    core=pd.read_csv(ROOT/'output/research_r14/core/native_forecasts.csv',float_precision='round_trip')
    food=pd.read_csv(ROOT/'output/research_r14/food/native_forecasts.csv',float_precision='round_trip')
    fuel=pd.read_csv(ROOT/'output/research_r14/fuel/native_forecasts.csv',float_precision='round_trip')
    food=food[food.model.ne(BASE)];fuel=fuel[fuel.model.ne(BASE)]
    new=[]
    for name,coremodel in CORE_FOR.items():
        cf=core.loc[core.model.eq(coremodel)] if coremodel else None
        new.append(combine_components(base,food[food.model.eq('FOOD_DOMESTIC_PIPELINE_R14')],
            fuel[fuel.model.eq('FUEL_ECM_R14')],cf,name))
    native=pd.concat(new,ignore_index=True)
    native.to_csv(folder/'native_forecasts.csv',index=False)
    allnative=pd.concat([base,core,food,fuel,native],ignore_index=True)
    keep=['origin','h','target','as_of_utc','model','mm_forecast']
    if allnative.duplicated(['origin','h','model']).any():raise AssertionError('Duplicate combined model rows')
    headline=read(ROOT/'output/independent_path_frozen_inputs.csv').headline_mm.dropna()
    forecasts,delta=add_outcomes_and_compound(allnative[keep],headline,base)
    forecasts.to_csv(folder/'forecasts.csv',index=False)
    models=[BASE]+sorted(set(forecasts.model)-{BASE})
    summary=comparison_scores(forecasts,models);summary.to_csv(folder/'summary.csv',index=False)
    bootstrap(forecasts,models).to_csv(folder/'paired_uncertainty.csv',index=False)
    quarters=match_cnb_quarters(forecasts,pd.read_csv(ROOT/'data/cnb_mpr_cpi_quarterly.csv'),headline,models)
    quarters.to_csv(folder/'cnb_quarters.csv',index=False)
    cnb=[]
    for sample,group in [('all_reports',quarters),('recent_reports',quarters[quarters.report_date>='2024-01-01'])]:
        cnb.append(_quarter_metrics(group,[BASE,*PRIMARY,'CNB'],'combined_common',sample))
        for model in models:
            cnb.append(_quarter_metrics(group,list(dict.fromkeys([BASE,model,'CNB'])),f'paired_{model}',sample))
    pd.concat(cnb,ignore_index=True).to_csv(folder/'cnb_summary.csv',index=False)
    coverage=forecasts.groupby(['model','h']).agg(n_intended=('origin','size'),n_forecast=('yy_exante','count'),n_actual=('yy_actual','count')).reset_index()
    coverage.to_csv(folder/'coverage.csv',index=False)
    latest=forecasts[forecasts.origin.eq(forecasts.origin.max())]
    latest.to_csv(folder/'latest_archived_paths.csv',index=False)
    dump(folder/'validation.json',dict(n_origins=forecasts.origin.nunique(),unique_keys=True,target_difference=delta,
      unchanged_h0=True,combination_choice='fixed before fits, 9379968',forecast_status='research, not promoted'))
    if inputs!=dependencies():raise AssertionError('Component outputs changed during integration')
    outputs={p.name:sha(p) for p in sorted(folder.iterdir()) if p.suffix in ('.csv','.json') and p.name not in ('manifest.json','verification_receipt.json')}
    manifest=dict(inputs=inputs,outputs=outputs,created_at=datetime.now(timezone.utc).isoformat())
    dump(folder/'manifest.json',manifest)
    print(summary.loc[summary.scope.eq('combined_common')&summary.h.isin([6,12]),['sample','h','model','n_common','yy_rmse','yy_bias']].to_string(index=False),flush=True)
    return manifest


def verify():
    frozen=json.loads((OUT/'manifest.json').read_text())
    if dependencies()!=frozen['inputs']:raise AssertionError('Integration input hashes changed')
    with tempfile.TemporaryDirectory(prefix='r14_integration_') as tmp,ExitStack() as stack:
        for target in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(target,side_effect=AssertionError('Offline verification attempted external access')))
        replay=generate(Path(tmp))
        if replay['outputs']!=frozen['outputs']:raise AssertionError('Integration replay mismatch')
    for name,digest in frozen['outputs'].items():
        if sha(OUT/name)!=digest:raise AssertionError(f'Changed saved integration payload:{name}')
    dump(OUT/'verification_receipt.json',dict(status='passed',payloads=len(frozen['outputs']),checked_at=datetime.now(timezone.utc).isoformat()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    verify() if args.verify else generate()
