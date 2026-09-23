"""Offline category-trend backtest with immutable inputs and saved own-origin states."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import r17_common as c
from models import category_trend_r18 as e
from tools.research_r18.category_inputs import load_categories,levels_asof

MODELS={'MCT_SLOW_R18':.0025,'MCT_FAST_R18':.01}
MACRO=['unemployment_change3','ip_growth3','ulc_growth12','fx3','cost_26_mean3','cost_45_mean3']


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=c.ROOT/'output/research_r18_category')
    p.add_argument('--limit-origins',type=int);args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    hashes=c.preserved_hashes();package=c.ROOT/'data/research_r18/categories'
    source=json.loads((package/'manifest.json').read_text(encoding='utf-8'))
    for name,record in source['files'].items():
        path=package/name
        if c.sha(path)!=record['sha256']:raise ValueError('Category source changed '+name)
        hashes[path.relative_to(c.ROOT).as_posix()]=record['sha256']
    files=['category_trend_experiment_r18.py','models/category_trend_r18.py',
           'docs/implementation/R18_CATEGORY_SPEC_2026-09-15.md','tests/test_category_trend_r18.py',
           'tools/research_r18/category_inputs.py','data/research_r18/categories/manifest.json',
           'tests/fixtures/cleanup/cnb_core_mm.csv','data/release_calendar_cz_cpi.csv','r17_common.py']
    hashes.update({f:c.sha(c.ROOT/f) for f in files})
    c.dump(out/'declaration.json',dict(inputs=hashes,models=[*MODELS,'MCT_SIGNALS_R18'],parameters=MODELS,
           target='CNB core monthly log inflation; category proxies are separate measurements'))
    levels,metadata,availability=load_categories();meta=metadata.set_index('column')
    rawcore=c.monthly('tests/fixtures/cleanup/cnb_core_mm.csv','core');core=100*np.log1p(rawcore/100)
    released=c.publication_dates(core.index)
    baseline=c.read('output/research_r15/native_forecasts.csv').query('model == @c.FAST')
    clocks=json.loads((c.ROOT/'output/research_r15/states.json').read_text())
    origins=sorted(baseline.origin.unique())
    if args.limit_origins:origins=origins[:args.limit_origins]
    macros=c.read('output/research_r15/features_by_origin.csv').set_index('origin')
    saved={};predictions=[];features={};labelrows=[];statuses=[]
    for key in origins:
        t=pd.Period(key,'M');clock=pd.Timestamp(clocks[key]['as_of']);states={}
        lev=levels_asof(levels,availability,clock);lev.index=pd.PeriodIndex(lev.index,freq='M')
        lev=lev[lev.index<t]
        # Gating before differencing ensures no unavailable endpoint is consumed.
        rates=100*np.log(lev/lev.shift(1));rates=rates.iloc[1:]
        if not rates.empty and not rates.index.equals(pd.period_range(rates.index[0],rates.index[-1],freq='M')):
            raise ValueError('Gap in category levels')
        hist=core.reindex(rates.index).rename('core').to_frame().join(rates)
        known=released.reindex(hist.index)
        hist=hist.loc[known.notna()&known.le(clock)]
        base=baseline[baseline.origin.eq(key)].set_index('h')
        for model,q in MODELS.items():
            reason=''
            try:
                state=e.fit_path(hist,key,q);status='estimated';path=state['path']
                state['as_of']=str(clock);state['last_release']=str(known.reindex(hist.index).max())
                state['measurement_definition']='national category proxies plus separate CNB core; no exact core partition'
            except ValueError as err:
                status='fallback_FAST';reason=str(err);path={h:float(100*np.log1p(base.loc[h,'value_core']/100)) for h in range(1,13)}
                state=dict(status=status,reason=reason,path=path)
            states[model]=state
            statuses.append(dict(origin=key,model=model,status=status,reason=reason,n_history=len(hist)))
            for h,value in path.items():
                predictions.append(dict(origin=key,h=h,model=model,core_log=value,core_mm=float(100*np.expm1(value/100)),status=status))
                if model=='MCT_FAST_R18':
                    target=t+h;truth=core.get(target,np.nan)
                    labelrows.append(dict(origin=key,h=h,target=str(target),released=str(released.get(target,pd.NaT)),
                                          error=truth-value,baseline_log=value,actual_log=truth))
        parent=states['MCT_FAST_R18']
        if 'mean' in parent:
            sector=dict(zip(parent['columns'],parent['mean'][2:]))
            group=lambda group:np.mean([sector[col] for col in levels if meta.loc[col,'sector']==group])
            features[key]=[*macros.loc[key,MACRO].to_numpy(float),parent['breadth3'],float(group('goods')-group('services'))]
        else:features[key]=[np.nan]*8
        saved[key]=states
    # Persist first stage before learning from its historical errors.
    c.dump(out/'states.json',saved)
    pd.DataFrame(predictions).to_csv(out/'state_predictions.csv',index=False)
    c.dump(out/'signal_declaration.json',dict(states_sha256=c.sha(out/'states.json'),
        predictions_sha256=c.sha(out/'state_predictions.csv'),features=[*MACRO,'breadth3','goods_minus_services']))
    labels=pd.DataFrame(labelrows);updates=[]
    for key in origins:
        fit=e.smooth_correction(features,labels,key,clocks[key]['as_of'],features[key]);updates.append(dict(origin=key,**fit))
        parent=saved[key]['MCT_FAST_R18']['path']
        for h,delta in enumerate(fit['correction'],1):
            value=parent[h]+delta
            predictions.append(dict(origin=key,h=h,model='MCT_SIGNALS_R18',core_log=value,
                                    core_mm=float(100*np.expm1(value/100)),status=fit['status']))
        statuses.append(dict(origin=key,model='MCT_SIGNALS_R18',status=fit['status'],reason='',n_history=fit.get('n_by_h',[0])[0]))
    predictions=pd.DataFrame(predictions);native=[]
    invariants=[x for x in baseline if x.startswith('weight_') or
        (x.startswith(('value_','contribution_')) and x not in ('value_core','contribution_core'))]
    for (key,model),g in predictions.groupby(['origin','model']):
        base=baseline[baseline.origin.eq(key)].sort_values('h').copy()
        changed=c.replace_block(base,'core',g.set_index('h').core_mm.to_dict());changed['model']=model
        changed['r18_status']=changed.h.map(g.set_index('h').status).fillna('preserved_h0')
        pd.testing.assert_frame_equal(base[invariants],changed[invariants],check_exact=True)
        assert base[base.h.eq(0)].mm_forecast.iloc[0]==changed[changed.h.eq(0)].mm_forecast.iloc[0]
        native.append(changed)
    native=pd.concat(native,ignore_index=True);forecasts=c.compound(native)
    derived=['yy_exante','cumulative_log_forecast','cumulative_log_actual'];keys=['origin','h','model']
    native=native.drop(columns=derived).merge(forecasts[keys+derived],on=keys,validate='one_to_one')
    for name,frame in [('native_forecasts',native),('forecasts',forecasts),('core_predictions',predictions),
                       ('training_labels',labels),('status',pd.DataFrame(statuses)),
                       ('features_by_origin',pd.DataFrame.from_dict(features,orient='index',columns=[*MACRO,'breadth3','goods_minus_services']).rename_axis('origin').reset_index())]:
        frame.to_csv(out/(name+'.csv'),index=False)
    c.dump(out/'signal_updates.json',updates)
    c.finish(out,hashes,models=[*MODELS,'MCT_SIGNALS_R18'],n_origins=len(origins),
             h0_and_noncore_unchanged=True,category_count=len(levels.columns))
    print('Completed',out,'origins',len(origins),flush=True)


if __name__=='__main__':main()
