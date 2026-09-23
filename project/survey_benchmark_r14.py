"""Rerun independent twelve-month paths at dated FMIE issue clocks, never as inputs."""
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
from sklearn.ensemble import RandomForestRegressor

from models.core_learning_r14 import BANDS,origin_state,band_design,labels_at,ridge,monthly_path
from models.food_path_r14 import load_inputs,forecast_origin as food_forecast
from models.fuel_path_r14 import forecast as fuel_forecast
from tools.r14_fuel.prepare import load as load_fuel
from forecast_independent import fixture_frames,runtime_identity
from independent_bridge_experiment import forecast_bridge
from core_split_experiment import publication_dates
from path_integration_r14 import survey_h12
from path_improvements_experiment_r12 import read,sha,dump

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/research_r14/survey'
PRIMARY=('INDEPENDENT_BRIDGE','PIPELINE_FOOD_FUEL_R14','PIPELINE_GAP_RIDGE_R14','PIPELINE_GAP_RF_R14')


def core_custom(core,features,dates,historical,t,clock,import_available=None):
    """Historical rows keep their own clock; current row is rebuilt at issue time."""
    local=pd.Timestamp(clock).tz_convert('Europe/Prague').tz_localize(None)
    states={}
    for r,s in historical.items():
        if r>=t or pd.Timestamp(s['as_of'])>local:continue
        seasonal={int(k):float(v) for k,v in s['seasonal'].items()}
        if len(s['seasonal'])!=12 or set(seasonal)!=set(range(1,13)) or not np.isfinite(list(seasonal.values())).all():
            raise ValueError('Historical state requires exactly twelve finite seasonal coefficients')
        states[r]=dict(s,seasonal=seasonal)
    current=origin_state(core,features,dates,t,clock,import_available_from=import_available)
    if current is None:return {name:dict.fromkeys(range(1,13),np.nan) for name in ('local','ridge','rf','level')},[]
    states[t]=current;trends=pd.Series({r:s['trend'] for r,s in states.items()})
    means={name:{} for name in ('local','ridge','rf','level')};audit=[]
    for b,band in enumerate(BANDS):
        x=band_design(states,band);level,labels=labels_at(core,dates,states,t,clock,band)
        train=level.index.intersection(x.index);gap=level.reindex(train)-trends.reindex(train)
        value,info=ridge(x.loc[train],gap,x.loc[t],30.)
        level_value,level_info=ridge(x.loc[train],level.reindex(train),x.loc[t],30.)
        rf=np.nan
        if len(train)>=48:
            forest=RandomForestRegressor(n_estimators=200,min_samples_leaf=5,max_features=1/3,random_state=42,n_jobs=1,bootstrap=True)
            forest.fit(x.loc[train].to_numpy(),gap.to_numpy())
            rf=float(forest.predict(x.loc[t].to_numpy().reshape(1,-1))[0])
        means['local'][b]=current['trend'];means['ridge'][b]=value+current['trend'];means['rf'][b]=rf+current['trend'];means['level'][b]=level_value
        audit.append(dict(band=b,training_last_release=str(labels.available_from.max()) if len(labels) else None,
            last_training_origin=str(train.max()) if len(train) else None,n_train=len(train),ridge_diagnostics=info,level_ridge_diagnostics=level_info,current_state=current))
    return {name:monthly_path(t,current['seasonal'],m) for name,m in means.items()},audit


def rebuild(base,food=None,fuel=None,core=None):
    path={0:0.};contributions={}
    for h in range(1,13):
        terms=dict(base['contributions'][h]);w=base['weights'][h]
        for b,p in [('food',food),('fuel',fuel),('core',core)]:
            if p is not None:terms[b]=w[b]*p[h]
        path[h]=float(sum(terms.values()));contributions[h]=terms
    return path,contributions


def dependencies(stable,extended=False):
    names=['survey_benchmark_r14.py','path_integration_r14.py','models/core_learning_r14.py','core_split_experiment.py',
       'models/food_path_r14.py','models/fuel_path_r14.py','tools/r14_fuel/prepare.py','forecast_independent.py',
       'independent_nowcast_experiment.py','independent_bridge_experiment.py','models/path_inputs.py','cz_struct.py',
       'models/independent_nowcast.py','models/components.py','models/horizon_models.py',
       'config.py','data/local_adapter.py','data/struct_inputs.py','path_improvements_experiment_r12.py',
       'docs/implementation/R14_BENCHMARK_SPEC.md','data/release_calendar_cz_cpi.csv','data/admin_announcements_history.csv',
       'output/research_r14/core/historical_states.json','output/research_r14/core/manifest.json',
       'output/independent_path_frozen_inputs.csv','output/independent_bridge_manifest.json',
       'test_path_integration_r14.py','test_survey_benchmark_r14.py']
    if stable:names+=['models/food_stable_r14b.py','docs/implementation/R14B_FOOD_DESIGN.md','docs/implementation/R14B_COMBINATIONS.md']
    if extended:names+=['core_learning_experiment_r14.py','docs/implementation/R14B_CORE_HISTORY_DESIGN.md',
        'output/research_r14b/core/historical_states.json','output/research_r14b/core/manifest.json','tools/r14b_imports/prepare.py']
    files=[ROOT/n for n in names]+list((ROOT/'tests/fixtures/cleanup').glob('*'))
    files+=[p for folder in ('data/research_r14/benchmarks','data/research_r14/fuel','data/research_r14/food') for p in (ROOT/folder).rglob('*') if p.is_file()]
    if extended:files += [p for p in (ROOT/'data/research_r14b/imports').rglob('*') if p.is_file()]
    frozen=json.loads((ROOT/'data/research_r14/benchmarks/fmie_official_manifest.json').read_text())
    for name,digest in frozen['inputs'].items():
        if sha(ROOT/name)!=digest:raise AssertionError('Frozen official FMIE source changed: '+name)
    if sha(ROOT/'data/research_r14/benchmarks/fmie_official_panel.csv')!=frozen['output_sha256']:
        raise AssertionError('Frozen official FMIE values changed')
    for history in (['research_r14/core','research_r14b/core'] if extended else ['research_r14/core']):
        archived=json.loads((ROOT/'output'/history/'manifest.json').read_text())
        if sha(ROOT/'output'/history/'historical_states.json')!=archived['outputs']['historical_states.json']:
            raise AssertionError('Frozen historical core states changed')
    original=json.loads((ROOT/'output/independent_bridge_manifest.json').read_text())
    for name,digest in original['fingerprints'].items():
        if sha(ROOT/name)!=digest:raise AssertionError('Frozen bridge source changed: '+name)
        files.append(ROOT/name)
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(files)) if p.is_file()}


def score(rows):
    models=list(rows.model.unique());tables=[]
    groups=[('primary_common',list(PRIMARY))]+[(f'paired_{m}',list(dict.fromkeys(['INDEPENDENT_BRIDGE',m]))) for m in models]
    for scope,names in groups:
        part=rows[rows.model.isin(names)]
        wide=part.pivot(index='survey_month',columns='model',values='forecast').reindex(columns=names)
        truth=part.drop_duplicates('survey_month').set_index('survey_month')
        good=wide.index[np.isfinite(wide).all(axis=1)&np.isfinite(truth.actual.reindex(wide.index))&np.isfinite(truth.survey_mean_yoy_pct.reindex(wide.index))]
        for name in [*names,'FMIE']:
            pred=truth.survey_mean_yoy_pct.reindex(good) if name=='FMIE' else wide.loc[good,name]
            err=pred-truth.actual.reindex(good)
            own=truth.survey_mean_yoy_pct if name=='FMIE' else wide[name]
            own_valid=np.isfinite(own)&np.isfinite(truth.actual.reindex(own.index))&np.isfinite(truth.survey_mean_yoy_pct.reindex(own.index))
            tables.append(dict(scope=scope,model=name,n_intended=24,n=len(good),n_own_scored=int(own_valid.sum()),n_available_targets=int(np.isfinite(truth.actual).sum()),rmse=float(np.sqrt((err**2).mean())),
               mae=float(err.abs().mean()),bias=float(err.mean()),model_target_horizon=12,source_clock_kind='document_date_next_day_reconstruction'))
    return pd.DataFrame(tables)


def run(folder=OUT,stable=False,extended=False):
    import cz_struct as s
    if extended and not stable:raise ValueError('Extended combinations require the declared stable food model')
    inputs=dependencies(stable,extended);runtime=runtime_identity();folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    panel=pd.read_csv(ROOT/'data/research_r14/benchmarks/fmie_official_panel.csv',float_precision='round_trip')
    if len(panel)!=24 or panel.survey_month.duplicated().any():raise ValueError('Exactly24 official survey reports required')
    if not np.isfinite(panel.survey_mean_yoy_pct).all() or not panel.horizon_months.eq(12).all():
        raise ValueError('Finite published one-year survey means required')
    frames=fixture_frames();core=frames['core'].iloc[:,0];dates=publication_dates(core.index)
    levels,food_dates,_=load_inputs();fuel_data=load_fuel()
    historical={pd.Period(k,'M'):v for k,v in json.loads((ROOT/'output/research_r14/core/historical_states.json').read_text()).items()}
    if extended:
        from core_learning_experiment_r14 import apply_feature_extension
        ext_features,ext_available,_=apply_feature_extension(frames['features'],ROOT/'data/research_r14b/imports')
        ext_historical={pd.Period(k,'M'):v for k,v in json.loads((ROOT/'output/research_r14b/core/historical_states.json').read_text()).items()}
    rows=[];details=[];monthly=[];invariance=[]
    for i,r in panel.iterrows():
        t=pd.Period(r.survey_month,'M');clock=pd.Timestamp(r.available_from_document_day_after)
        if pd.Period(r.target_month,'M')!=t+12:raise ValueError('Changed original survey target')
        base=forecast_bridge(frames,t,clock,0.)
        for placeholder in (-50.,100.):
            probe=forecast_bridge(frames,t,clock,placeholder)
            for family in ('block_values','contributions','weights'):
                for h in range(1,13):
                    if not np.array_equal(list(base[family][h].values()),list(probe[family][h].values()),equal_nan=True):
                        raise AssertionError('h0 changed future '+family)
            if not np.array_equal([base['path'][h] for h in range(1,13)],[probe['path'][h] for h in range(1,13)],equal_nan=True):
                raise AssertionError('h0 changed future headline path')
            if not np.array_equal([survey_h12(base['path'])],[survey_h12(probe['path'])],equal_nan=True):
                raise AssertionError('h12 depends on placeholderh0')
        invariance.append(dict(survey_month=str(t),max_future_h0_difference=0.,annual_h0_difference=0.,probed_h0='-50|0|100',checked_families='block_values|contributions|weights|headline'))
        cp,cd=core_custom(core,frames['features'],dates,historical,t,clock)
        food=food_forecast(levels,food_dates,t,clock)
        fuel=fuel_forecast(fuel_data,t,clock,s._petrol_share(t,clock.tz_convert('Europe/Prague').tz_localize(None)))
        fp=food['paths']['FOOD_DOMESTIC_PIPELINE_R14']
        fu={h:float(fuel['forecasts']['FUEL_ECM_R14'][h-1]) for h in range(1,13)}
        constant={h:float(fuel['forecasts']['FUEL_CONSTANT_PUMP_R14'][h-1]) for h in range(1,13)}
        specifications={'INDEPENDENT_BRIDGE':{},'PIPELINE_FOOD_FUEL_R14':dict(food=fp,fuel=fu),
          'PIPELINE_GAP_RIDGE_R14':dict(food=fp,fuel=fu,core=cp['ridge']),
          'PIPELINE_GAP_RF_R14':dict(food=fp,fuel=fu,core=cp['rf'])}
        if stable:
            from models.food_stable_r14b import forecast_origin as stable_food
            stable_result=stable_food(levels,food_dates,t,clock)
            sf=stable_result['paths']['FOOD_STABLE_PIPELINE_R14B']
            specifications.update(STABLE_PIPELINE_R14B=dict(food=sf,fuel=constant),
                                  STABLE_LOCAL_CORE_R14B=dict(food=sf,fuel=constant,core=cp['local']))
        if extended:
            ep,ed=core_custom(core,ext_features,dates,ext_historical,t,clock,ext_available)
            specifications.update(STABLE_LONG_CORE_R14B=dict(food=sf,fuel=constant,core=ep['level']),
                                  STABLE_LONG_GAP_R14B=dict(food=sf,fuel=constant,core=ep['ridge']))
        for name,overrides in specifications.items():
            path,contribution=rebuild(base,**overrides)
            rows.append(dict(survey_month=str(t),target_month=str(t+12),model=name,model_origin=str(t),model_h=12,
                as_of=clock.isoformat(),forecast=survey_h12(path),status='estimated' if np.isfinite(list(path.values())).all() else 'unavailable'))
            monthly.extend(dict(survey_month=str(t),model=name,h=h,target=str(t+h),mm_forecast=path[h],
                                 **{'contribution_'+b:v for b,v in contribution[h].items()}) for h in range(1,13))
        details.append(dict(survey_month=str(t),as_of=clock.isoformat(),core=cd,food=food['diagnostics'],food_fits=food['fits'],fuel=fuel['audit'],fuel_parameters=fuel['parameters']))
        if extended:details[-1]['extended_core']=ed
        if stable:
            details[-1]['stable_food']=stable_result['diagnostics']
            details[-1]['stable_food_fits']=stable_result['fits']
        print(f'FMIE issue-clock paths {i+1}/24: {t}',flush=True)
    predictions=pd.DataFrame(rows);predictions.to_csv(folder/'predictions.csv',index=False)
    pd.DataFrame(monthly).to_csv(folder/'monthly_paths.csv',index=False);dump(folder/'fit_audit.json',details)
    pd.DataFrame(invariance).to_csv(folder/'h0_invariance.csv',index=False)
    # Only now merge the external benchmark and realised target for scoring.
    headline=read(ROOT/'output/independent_path_frozen_inputs.csv').headline_mm.dropna()
    actual=100*np.expm1(np.log1p(headline/100).rolling(12).sum())
    result=predictions.merge(panel[['survey_month','survey_mean_yoy_pct','document_issue_date','source_url','pdf_sha256','availability_kind']],on='survey_month',validate='many_to_one')
    result['actual']=[actual.get(pd.Period(t,'M'),np.nan) for t in result.target_month]
    result['error']=result.forecast-result.actual;result['survey_error']=result.survey_mean_yoy_pct-result.actual
    result.to_csv(folder/'comparisons.csv',index=False);summary=score(result);summary.to_csv(folder/'summary.csv',index=False)
    if inputs!=dependencies(stable,extended) or runtime_identity()!=runtime:raise AssertionError('Consumed source/code/runtime changed during benchmark')
    outputs={p.name:sha(p) for p in sorted(folder.iterdir()) if p.suffix in ('.csv','.json') and p.name not in ('manifest.json','verification_receipt.json')}
    manifest=dict(inputs=inputs,outputs=outputs,runtime=runtime,include_stable=stable,include_extended=extended,created_at=datetime.now(timezone.utc).isoformat(),declaration='709d4b3' if extended else ('08d6843' if stable else '5c959d8'),
       interpretation='Independent h12 rerun at reconstructed document availability; actual survey information cutoff and web publication time unknown.')
    dump(folder/'manifest.json',manifest);print(summary.to_string(index=False),flush=True)
    return manifest


def verify(folder=OUT):
    original=json.loads((folder/'manifest.json').read_text());stable=original['include_stable'];extended=original['include_extended']
    if dependencies(stable,extended)!=original['inputs'] or runtime_identity()!=original['runtime']:raise AssertionError('Benchmark code/input/runtime hash changed')
    with tempfile.TemporaryDirectory(prefix='r14_survey_') as tmp,ExitStack() as stack:
        for target in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(target,side_effect=AssertionError('Offline survey benchmark used live source')))
        replay=run(Path(tmp),stable,extended)
        if replay['outputs']!=original['outputs']:raise AssertionError('Survey custom-clock replay mismatch')
    for name,digest in original['outputs'].items():
        if sha(folder/name)!=digest:raise AssertionError('Saved survey benchmark payload changed')
    dump(folder/'verification_receipt.json',dict(status='passed',payloads=len(original['outputs']),refitted_clocks=24,checked_at=datetime.now(timezone.utc).isoformat()))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify',action='store_true');p.add_argument('--include-stable',action='store_true');p.add_argument('--include-extended',action='store_true');p.add_argument('--output-dir',type=Path,default=OUT)
    args=p.parse_args();verify(args.output_dir) if args.verify else run(args.output_dir,args.include_stable,args.include_extended)
