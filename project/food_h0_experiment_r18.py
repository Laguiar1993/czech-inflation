"""Offline R18 food-h0 experiment; immutable sources and predeclared profiles."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd

import r17_common as common
from models import food_h0_r18 as engine
from models.food_path_r14 import _aware,load_inputs
from food_transmission_experiment_r17 import (integrate_food,component_outcomes,
    component_scores,verify_manifest,dump,sha)

ROOT=Path(__file__).resolve().parent
SPEC='docs/implementation/R18_FOOD_SPEC_2026-09-15.md'
OUT=ROOT/'output/research_r18_food'
MODELS=(*engine.PROFILES,engine.SELECT)
SOURCE_FILES=['output/cz_struct_backtest.csv','output/independent_nowcast_manifest.json',
    'output/independent_nowcast_forecasts.csv','output/research_r14b/food/origin_diagnostics.json',
    'output/research_r14b/food/manifest.json','output/research_r15/states.json',
    'output/research_r15/native_forecasts.csv','data/release_calendar_cz_cpi.csv',
    'output/cleanup_check_v26/cz_struct_backtest.csv',
    'output/research_r17/attribution/primary_support.csv','output/independent_path_frozen_inputs.csv',
    'output/research_r17/path/evaluation/primary_scoreboard.csv']
CODE_FILES=[SPEC,'models/food_h0_r18.py','food_h0_experiment_r18.py','tests/test_food_h0_r18.py',
    'r17_common.py','food_transmission_experiment_r17.py','models/food_path_r14.py',
    'models/food_stable_r14b.py','models/path_inputs.py','path_improvements_experiment_r12.py',
    'independent_nowcast_experiment.py','cz_struct.py','tools/review/r17_component_attribution.py']


def load_sources():
    return (common.read(SOURCE_FILES[0]).set_index('period'),
        json.loads((ROOT/SOURCE_FILES[3]).read_text()),
        json.loads((ROOT/SOURCE_FILES[5]).read_text()),
        common.read(SOURCE_FILES[6]).query('model==@engine.CONTROL'),
        common.read(SOURCE_FILES[2]).set_index('period'),
        common.read(SOURCE_FILES[7]).set_index('target_month'))


def validate_sources(backtest,diagnostics,states,baseline,nowcast,calendar):
    expected=list(map(str,pd.period_range('2019-02','2026-07',freq='M')))
    if not backtest.index.is_unique or list(backtest.index)!=expected:raise ValueError('Wrong h0 origin calendar')
    if not nowcast.index.is_unique or not calendar.index.is_unique:raise ValueError('Duplicate nowcast/release month')
    if [r['origin'] for r in diagnostics]!=expected:raise ValueError('Wrong pipeline origin calendar')
    saved={};audit=[]
    for row in diagnostics:
        key=row['origin'];t=pd.Period(key,'M');g=baseline.loc[baseline.origin.eq(key)].sort_values('h')
        if g.h.tolist()!=list(range(13)) or g.target.tolist()!=list(map(str,pd.period_range(t,t+12,freq='M'))):
            raise ValueError('Wrong pipeline/FAST horizons')
        clock=_aware(backtest.loc[key,'as_of_eve'])
        if not all(clock==_aware(value) for value in (row['as_of'],states[key]['as_of'],g.as_of_utc.iloc[0],nowcast.loc[key,'as_of_eve'])):
            raise ValueError('Historical origin clock mismatch')
        local=clock.tz_convert('Europe/Prague').tz_localize(None)
        first=pd.Timestamp(calendar.loc[key,'first_release_dt'])
        detail=pd.Timestamp(calendar.loc[key,'detail_release_dt'])
        if local!=first.normalize()-pd.Timedelta(minutes=1):raise ValueError('h0 clock must precede first release by one calendar day at23:59')
        if backtest.loc[key,'elig_edge_eve']!=str(t-1):raise ValueError('Saved h0 history edge mismatch')
        rates=np.asarray(row['forecast_food_rates']['FOOD_STABLE_PIPELINE_R14B'])
        if rates.shape!=(13,) or not np.isfinite(rates).all():raise ValueError('Invalid saved pipeline path')
        exact=100*np.expm1(rates[1:]/100)
        if not np.array_equal(exact,g.value_food.iloc[1:].to_numpy()):raise ValueError('Saved pipeline differs from FAST')
        h0=float(backtest.loc[key,'food_pred_eve'])
        if not np.isfinite(h0) or h0<=-100:raise ValueError('Invalid archived food h0')
        h0_log=float(100*np.log1p(h0/100))
        if not np.isclose(g.mm_forecast.iloc[0],nowcast.loc[key,'HARD_BASE'],atol=1e-15,rtol=0):
            raise ValueError('Independent headline h0 mismatch')
        saved[key]=dict(origin=key,as_of=clock.isoformat(),baseline_log=rates.tolist(),
            baseline_mm=g.value_food.iloc[1:].tolist(),raw_h0_mm=h0,raw_h0_log=h0_log,signal=h0_log-rates[0])
        audit.append(dict(origin=key,raw_h0_source=SOURCE_FILES[0],raw_h0_column='food_pred_eve',
            pipeline_source=SOURCE_FILES[3],pipeline_h0_index=0,as_of_eve=backtest.loc[key,'as_of_eve'],
            as_of_local=clock.isoformat(),as_of_utc=clock.tz_convert('UTC').isoformat(),
            first_release_date=str(first.date()),detail_release_date=str(detail.date()),
            first_release_source=calendar.loc[key,'first_release_source'],detail_release_source=calendar.loc[key,'detail_release_source'],
            first_release_eve_match=True,detail_release_eve_match=local.normalize()==detail.normalize()-pd.Timedelta(days=1),
            eligible_history_end=backtest.loc[key,'elig_edge_eve'],pipeline_fast_max_abs=0.,
            raw_h0_mm=h0,state_h0_log=float(rates[0]),signal=float(h0_log-rates[0]),
            headline_archive_serialization_abs=float(abs(g.mm_forecast.iloc[0]-nowcast.loc[key,'HARD_BASE'])),
            vintage_status='saved pseudo-OOS; frozen current-vintage inputs and reconstructed release gates'))
    return saved,pd.DataFrame(audit)


def dependencies():
    hashes={}
    for name in ('output/research_r15/manifest.json','output/research_r16/manifest.json','data/research_r14/food/input_manifest.json'):
        hashes.update(verify_manifest(ROOT,ROOT/name))
    old=json.loads((ROOT/'output/research_r14b/food/manifest.json').read_text())
    for name,digest in old['outputs'].items():
        path=ROOT/'output/research_r14b/food'/name
        if sha(path)!=digest:raise ValueError('Preserved R14B food output hash changed: '+name)
        hashes[path.relative_to(ROOT).as_posix()]=digest
    now=json.loads((ROOT/'output/independent_nowcast_manifest.json').read_text())
    if sha(ROOT/SOURCE_FILES[0])!=now['inputs'][SOURCE_FILES[0]]:raise ValueError('Authoritative food h0 source changed')
    for name,digest in now['inputs'].items():
        path=ROOT/name if name.startswith(('output/','data/')) else ROOT/'tests/fixtures/cleanup'/name
        if sha(path)!=digest:raise ValueError('Preserved nowcast source hash changed: '+name)
        hashes[path.relative_to(ROOT).as_posix()]=digest
    hashes.update({name:sha(ROOT/name) for name in SOURCE_FILES+CODE_FILES})
    return dict(sorted(hashes.items()))


def primary_scores(outcomes,forecasts,support):
    rows=[];keys=['origin','h']
    for kind,data,metrics in [('food',outcomes,('mm','cumulative_log','cumulative_pct')),
                              ('headline',forecasts,('yy',))]:
        for name,group in data.groupby('model'):
            g=support.merge(group,on=keys,how='left',validate='one_to_one')
            for sample in ('full','recent_origins','recent_targets'):
                selected=g if sample=='full' else g.loc[g.origin.ge('2024-01') if sample=='recent_origins' else g.target.ge('2024-01')]
                for h in range(13):
                    chosen=selected if h==0 else selected[selected.h.eq(h)]
                    for metric in metrics:
                        pred='yy_exante' if metric=='yy' else metric+'_forecast';truth=metric+'_actual'
                        errors=chosen[pred]-chosen[truth];finite=np.isfinite(errors);e=errors[finite]
                        rows.append(dict(scope='original_R16_calendar',component=kind,model=name,sample=sample,h=h,metric=metric,
                            n_intended=len(chosen),n_scored=int(finite.sum()),n_missing_forecast=int((~np.isfinite(chosen[pred])).sum()),
                            n_missing_actual=int((~np.isfinite(chosen[truth])).sum()),rmse=float(np.sqrt(np.mean(e*e))) if len(e) else np.nan,
                            mae=float(e.abs().mean()) if len(e) else np.nan,bias=float(e.mean()) if len(e) else np.nan))
    return pd.DataFrame(rows)


def run(destination=OUT,end='2026-07'):
    destination=Path(destination)
    if destination.exists():raise FileExistsError('Refusing existing destination: '+str(destination))
    if not '2019-02'<=end<='2026-07':raise ValueError('End outside original outer calendar')
    hashes=dependencies();sources=load_sources();saved,audit=validate_sources(*sources)
    levels,available,_=load_inputs();baseline=sources[3].loc[sources[3].origin.le(end)].copy()
    saved={k:v for k,v in saved.items() if k<=end};audit=audit.loc[audit.origin.le(end)].copy()
    cleanup=common.read(SOURCE_FILES[8]).set_index('period')
    audit['cleanup_replay_h0_abs_difference']=[abs(v.raw_h0_mm-cleanup.loc[v.origin,'food_pred_eve']) for v in audit.itertuples()]
    destination.mkdir(parents=True)
    dump(destination/'declaration.json',dict(declared_at=datetime.now(timezone.utc).isoformat(),inputs=hashes,
        specification=SPEC,models=MODELS,profiles=engine.PROFILES,ridge=engine.RIDGE,min_train=engine.MIN_ORIGINS,
        train_window=engine.TRAIN_WINDOW,selection_window=engine.VALIDATION_WINDOW,intercept=False,
        coefficient_units='beta original signal units, dimensionless; theta log points; beta=clip(theta/RMS(x),0,1)',
        independent_clock='eve of first release; separate detailed food endpoint maturity',
        first_origin='2019-02',last_origin=end,earlier_h0_lineage_available=False,
        evaluator_version='R18 primary_scores + frozen R17 food component/accounting helpers',parameters_frozen_before_fit=True))
    dump(destination/'snapshots.json',saved);audit.to_csv(destination/'source_audit.csv',index=False)
    print('Declared inputs and source clocks; fitting',len(saved),'origins.',flush=True)
    predictions=[];fits=[];training=[];selections=[];history={}
    for i,(key,state) in enumerate(saved.items()):
        paths={engine.CONTROL:dict(log_rates=state['baseline_log'][1:],mm_rates=state['baseline_mm'],status='preserved_control',reason='')}
        for name,rho in engine.PROFILES.items():
            fit=engine.fit_profile(saved,levels.food,available.food,key,state['as_of'],rho)
            training.extend(dict(fit_origin=key,model=name,fit_as_of=state['as_of'],**row) for row in fit.pop('training'))
            fits.append(dict(origin=key,model=name,rho=rho,as_of=state['as_of'],**fit))
            path=engine.corrected_path(state,fit['beta'],rho)
            path.update(status=fit['status'],reason=path['reason'] or fit['reason']);paths[name]=path
        choice=engine.select_path(history,saved,levels.food,available.food,key,state['as_of'])
        selections.append(dict(origin=key,as_of=state['as_of'],**choice))
        paths[engine.SELECT]=dict(paths[choice['selected']])
        if choice['status']=='fallback':paths[engine.SELECT].update(status='fallback',reason=choice['reason'])
        elif choice['selected']==engine.CONTROL:paths[engine.SELECT].update(status='selected_control',reason='past_food_path_loss')
        history[key]={name:paths[name]['log_rates'] for name in engine.PREFERENCE}
        for name in MODELS:
            path=paths[name]
            for h in range(1,13):
                predictions.append(dict(origin=key,as_of_utc=_aware(state['as_of']).tz_convert('UTC').isoformat(),
                    h=h,target=str(pd.Period(key,'M')+h),model=name,log_rate_forecast=path['log_rates'][h-1],
                    mm_forecast=path['mm_rates'][h-1],status=path['status'],reason=path['reason'],
                    selected_model=choice['selected'] if name==engine.SELECT else name))
        if i%12==0 or i==len(saved)-1:print('Food h0 paths',i+1,'/',len(saved),key,flush=True)
    predictions=pd.DataFrame(predictions);predictions.to_csv(destination/'food_predictions.csv',index=False)
    dump(destination/'fit_coefficients.json',fits);dump(destination/'selections.json',selections)
    pd.DataFrame([{k:v for k,v in f.items() if k!='training_origins'} for f in fits]).to_csv(destination/'fit_coefficients.csv',index=False)
    pd.DataFrame(training).to_csv(destination/'training_rows.csv',index=False)
    headline=common.monthly('output/independent_path_frozen_inputs.csv','headline_mm')
    native=integrate_food(baseline,predictions,headline)
    contribution_cols=[f'contribution_{n}' for n in ('core','administered','alcohol_tobacco','fuel','wedge','food')]
    np.testing.assert_array_equal(native.loc[native.h.gt(0),'mm_forecast'],native.loc[native.h.gt(0),contribution_cols].sum(axis=1,min_count=6))
    native.to_csv(destination/'native_forecasts.csv',index=False)
    control=common.read('output/research_r16/forecasts.csv').query('model==@engine.CONTROL and origin<=@end')
    columns=['origin','target','h','as_of_utc','model','mm_forecast','mm_actual','yy_exante','yy_actual','cumulative_log_forecast','cumulative_log_actual']
    forecasts=pd.concat([native[columns],control[columns]],ignore_index=True)
    forecasts.to_csv(destination/'forecasts.csv',index=False)
    outcomes=component_outcomes(predictions,baseline,levels);outcomes.to_csv(destination/'food_outcomes.csv',index=False)
    component_scores(outcomes).to_csv(destination/'food_summary.csv',index=False)
    support=common.read('output/research_r17/attribution/primary_support.csv').query('origin<=@end')
    if end=='2026-07' and len(support)!=969:raise AssertionError('Original score calendar changed')
    support.to_csv(destination/'primary_support.csv',index=False)
    primary=primary_scores(outcomes,forecasts,support);primary.to_csv(destination/'primary_scoreboard.csv',index=False)
    coverage=predictions[['origin','h','target','model','status','reason','selected_model']].copy()
    coverage['finite_food']=np.isfinite(predictions.mm_forecast)
    coverage=coverage.merge(outcomes[['origin','h','model','mm_actual']],on=['origin','h','model'],validate='one_to_one')
    coverage['outcome_status']=np.where(np.isfinite(coverage.mm_actual),'realised','not_yet_realised')
    coverage.to_csv(destination/'coverage.csv',index=False)
    h0=[]
    for key,state in saved.items():
        t=pd.Period(key,'M');actual=levels.food.get(t,np.nan)-levels.food.get(t-1,np.nan)
        h0.append(dict(origin=key,state_log=state['baseline_log'][0],raw_log=state['raw_h0_log'],actual_log=actual,signal=state['signal']))
    pd.DataFrame(h0).to_csv(destination/'h0_diagnostics.csv',index=False)
    if dependencies()!=hashes:raise ValueError('Declared code/source changed during fit')
    validation=dict(status='passed',origin_count=len(saved),models=MODELS,prediction_rows=len(predictions),
        native_rows=len(native),full_run=end=='2026-07',h0_unchanged=True,nonfood_weights_exact=True,
        six_component_monthly_sum_exact=True,pipeline_fast_max_abs=0.,original_primary_keys=len(support),
        finite_future_food=int(np.isfinite(predictions.mm_forecast).sum()),source_first_eve_matches=int(audit.first_release_eve_match.sum()),
        source_detail_eve_matches=int(audit.detail_release_eve_match.sum()),
        independent_replay_h0_max_abs=float(audit.cleanup_replay_h0_abs_difference.max()))
    dump(destination/'validation.json',validation)
    outputs={p.name:sha(p) for p in destination.iterdir() if p.is_file() and p.name!='manifest.json'}
    dump(destination/'manifest.json',dict(completed_at=datetime.now(timezone.utc).isoformat(),inputs=hashes,outputs=outputs,
        models=MODELS,control=engine.CONTROL,origin_count=len(saved),parameters_frozen_before_fit=True,
        specification_sha256=hashes[SPEC],evaluator_sha256=hashes['food_h0_experiment_r18.py'],
        original_nowcast_source_manifest=SOURCE_FILES[1],vintage='pseudo-OOS frozen inputs, reconstructed release gates'))
    print(primary.loc[primary.component.eq('headline') & primary['sample'].isin(['full','recent_origins']) & primary.h.isin([3,6,12]),
        ['sample','h','model','n_scored','rmse','mae']].to_string(index=False),flush=True)
    return validation


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUT)
    parser.add_argument('--end',default='2026-07');args=parser.parse_args();run(args.output,args.end)
