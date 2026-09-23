"""Versioned R18 runner: exact source-gap fallback and clear fitted history counts."""
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


def fit_origin(levels,availability,core,released,key,clock,base):
    """Apply source gates and fit both declared filters, retaining exact fallback mm."""
    t=pd.Period(key,'M');states={};predictions=[];statuses=[];source_error='';hist=pd.DataFrame()
    known=pd.Series(dtype='datetime64[ns]')
    try:
        lev=levels_asof(levels,availability,clock);lev.index=pd.PeriodIndex(lev.index,freq='M')
        lev=lev[lev.index<t]
        rates=100*np.log(lev/lev.shift(1));rates=rates.iloc[1:]
        if not rates.empty and not rates.index.equals(pd.period_range(rates.index[0],rates.index[-1],freq='M')):
            raise ValueError('Gap in category levels')
        hist=core.reindex(rates.index).rename('core').to_frame().join(rates)
        known=released.reindex(hist.index)
        hist=hist.loc[known.notna()&known.le(clock)]
    except ValueError as err:
        source_error='source_availability: '+str(err)
    for model,q in MODELS.items():
        reason=''
        try:
            if source_error:raise ValueError(source_error)
            state=e.fit_path(hist,key,q);status='estimated';path=state['path']
            state['as_of']=str(clock);state['last_release']=str(known.reindex(hist.index).max())
            state['measurement_definition']='national category proxies plus separate CNB core; no exact core partition'
            mm={h:float(100*np.expm1(value/100)) for h,value in path.items()}
        except ValueError as err:
            status='fallback_FAST';reason=str(err)
            mm={h:float(base.loc[h,'value_core']) for h in range(1,13)}
            path={h:float(100*np.log1p(value/100)) for h,value in mm.items()}
            state=dict(status=status,reason=reason,path=path)
        state['core_mm_path']=mm;states[model]=state
        statuses.append(dict(origin=key,model=model,status=status,reason=reason,
                             n_history=state.get('n_history',0),n_available_history=len(hist)))
        predictions.extend(dict(origin=key,h=h,model=model,core_log=value,core_mm=mm[h],status=status)
                           for h,value in path.items())
    return states,predictions,statuses


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=c.ROOT/'output/research_r18_category_verified')
    p.add_argument('--limit-origins',type=int);args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    hashes=c.preserved_hashes();package=c.ROOT/'data/research_r18/categories'
    original=c.ROOT/'output/research_r18_category';old=json.loads((original/'manifest.json').read_text())
    hashes['output/research_r18_category/manifest.json']=c.sha(original/'manifest.json')
    for kind,base in [('inputs',c.ROOT),('outputs',original)]:
        for name,digest in old[kind].items():
            path=base/name
            if c.sha(path)!=digest:raise ValueError('Original category experiment changed: '+str(path))
            hashes[path.relative_to(c.ROOT).as_posix()]=digest
    source=json.loads((package/'manifest.json').read_text(encoding='utf-8'))
    for name,record in source['files'].items():
        path=package/name
        if c.sha(path)!=record['sha256']:raise ValueError('Category source changed '+name)
        hashes[path.relative_to(c.ROOT).as_posix()]=record['sha256']
    files=['category_trend_experiment_r18.py','category_trend_experiment_r18_verified.py','models/category_trend_r18.py',
           'docs/implementation/R18_CATEGORY_SPEC_2026-09-15.md','tests/test_category_trend_r18.py',
           'tools/research_r18/category_inputs.py','data/research_r18/categories/manifest.json',
           'tests/fixtures/cleanup/cnb_core_mm.csv','data/release_calendar_cz_cpi.csv','r17_common.py',
           'tests/test_r18_category_audit.py','docs/implementation/R18_CATEGORY_CORRECTION_NOTE.md']
    hashes.update({f:c.sha(c.ROOT/f) for f in files})
    c.dump(out/'declaration.json',dict(inputs=hashes,models=[*MODELS,'MCT_SIGNALS_R18'],parameters=MODELS,
           target='CNB core monthly log inflation; category proxies are separate measurements',
           correction_note='docs/implementation/R18_CATEGORY_CORRECTION_NOTE.md',
           original_experiment='output/research_r18_category',parameters_unchanged=True))
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
        t=pd.Period(key,'M');clock=pd.Timestamp(clocks[key]['as_of'])
        base=baseline[baseline.origin.eq(key)].set_index('h')
        states,new_predictions,new_statuses=fit_origin(levels,availability,core,released,key,clock,base)
        predictions.extend(new_predictions);statuses.extend(new_statuses)
        for h,value in states['MCT_FAST_R18']['path'].items():
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
        parent=saved[key]['MCT_FAST_R18']['path'];parent_mm=saved[key]['MCT_FAST_R18']['core_mm_path']
        for h,delta in enumerate(fit['correction'],1):
            value=parent[h]+delta
            predictions.append(dict(origin=key,h=h,model='MCT_SIGNALS_R18',core_log=value,
                                    core_mm=parent_mm[h] if delta==0 else float(100*np.expm1(value/100)),status=fit['status']))
        eligible=labels.loc[labels.h.eq(1)&labels.target.lt(key)&pd.to_datetime(labels.released).le(pd.Timestamp(clocks[key]['as_of']))]
        statuses.append(dict(origin=key,model='MCT_SIGNALS_R18',status=fit['status'],reason='',
                             n_history=fit.get('n_by_h',[0])[0],n_available_history=len(eligible)))
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
    parity=[]
    for name in ['state_predictions','core_predictions','forecasts','native_forecasts','training_labels','features_by_origin']:
        before=c.read('output/research_r18_category/'+name+'.csv');after=pd.read_csv(out/(name+'.csv'),float_precision='round_trip')
        if args.limit_origins:before=before.loc[before.origin.isin(origins)]
        numeric=before.select_dtypes(include=[np.number]).columns.tolist()
        if name in ('native_forecasts','forecasts'):
            before=before.sort_values(['model','origin','h']).reset_index(drop=True)
            after=after.sort_values(['model','origin','h']).reset_index(drop=True)
        pd.testing.assert_frame_equal(before[numeric].reset_index(drop=True),after[numeric].reset_index(drop=True),check_exact=True)
        parity.append(dict(payload=name,rows=len(after),numeric_columns=numeric,bit_exact=True))
    c.dump(out/'original_point_parity.json',dict(original_directory='output/research_r18_category',checks=parity,
        parameters_unchanged=True,old_manifest_sha256=hashes['output/research_r18_category/manifest.json']))
    c.finish(out,hashes,models=[*MODELS,'MCT_SIGNALS_R18'],n_origins=len(origins),
             h0_and_noncore_unchanged=True,category_count=len(levels.columns),original_point_columns_bit_exact=True,
             original_directory='output/research_r18_category',correction_note=files[-1])
    print('Completed',out,'origins',len(origins),flush=True)


if __name__=='__main__':main()
