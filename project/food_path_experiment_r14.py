"""Fixed R14 food-price pipeline replay; --verify performs full offline refits."""
from contextlib import ExitStack
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
import argparse
import importlib.metadata
import json
import platform
import tempfile

import numpy as np
import pandas as pd

from models.food_path_r14 import MODELS,load_inputs,forecast_origin,replace_food
from models.path_inputs import compound_path
from path_improvements_experiment_r12 import (read,sha,dump,verify_baseline,score_panel,add_outcomes_and_compound)

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/research_r14/food'
DECLARATION='9379968'
REFERENCES=('INDEPENDENT_BRIDGE','FOOD_TREND_R12','FOOD_COST_R12')
PAIRS=[(name,'INDEPENDENT_BRIDGE') for name in MODELS]+[(MODELS[0],MODELS[1])]


def all_scores(frame):
    tables=[score_panel(frame,[*MODELS,*REFERENCES],'common')]
    for name in (*MODELS,*REFERENCES):
        tables.append(score_panel(frame,[name],'own_coverage'))
    for name,control in PAIRS:
        tables.append(score_panel(frame,[control,name],f'paired_{name}_vs_{control}'))
    return pd.concat(tables,ignore_index=True)


def uncertainty(frame):
    rng=np.random.default_rng(1409); records=[]
    for sample,mask in [('full',np.ones(len(frame),bool)),('recent_targets',frame.target>='2024-01'),
                        ('recent_origins',frame.origin>='2024-01')]:
        for h in range(1,13):
            g=frame.loc[mask & frame.h.eq(h)]
            for name,control in PAIRS:
                a=g[g.model.eq(name)].set_index('origin'); b=g[g.model.eq(control)].set_index('origin')
                pair=pd.concat([(a.yy_exante-a.yy_actual).rename('a'),(b.yy_exante-b.yy_actual).rename('b')],axis=1).dropna().sort_index()
                n=len(pair)
                if not n:continue
                d=(pair.a**2-pair.b**2).to_numpy()
                starts=rng.integers(0,n,size=(2000,int(np.ceil(n/12))))
                indices=((starts[:,:,None]+np.arange(12))%n).reshape(2000,-1)[:,:n]
                lo,hi=np.quantile(d[indices].mean(axis=1),[.025,.975])
                records.append(dict(sample=sample,h=h,model=name,control=control,n=n,mse_difference=d.mean(),
                    ci_low=lo,ci_high=hi,block_length=12,replicates=2000,seed=1409))
    return pd.DataFrame(records)


def food_scores(native,food):
    rows=[]
    for (origin,name),g in native.groupby(['origin','model'],sort=False):
        t=pd.Period(origin,'M'); pred=g.set_index('h').value_food
        for h in range(1,13):
            forecast=pred.reindex(range(1,h+1)).to_numpy(dtype=float)
            actual=food.reindex(pd.period_range(t+1,t+h,freq='M')).to_numpy(dtype=float)
            row=dict(origin=origin,target=str(t+h),h=h,model=name,mm_forecast=pred.get(h,np.nan),mm_actual=food.get(t+h,np.nan))
            for suffix,array in [('forecast',forecast),('actual',actual)]:
                q=float(100*np.log1p(array/100).sum()) if np.isfinite(array).all() and (array>-100).all() else np.nan
                row[f'cumulative_log_{suffix}']=q
                row[f'cumulative_pct_{suffix}']=100*np.expm1(q/100)
            rows.append(row)
    detail=pd.DataFrame(rows); summaries=[]
    for scope,names in [('common',list(MODELS)+list(REFERENCES))]+[(f'paired_{a}_vs_{b}',[b,a]) for a,b in PAIRS]:
        for sample,mask in [('full',np.ones(len(detail),bool)),('recent_targets',detail.target>='2024-01'),('recent_origins',detail.origin>='2024-01')]:
            for h in range(1,13):
                selected=detail.loc[mask & detail.h.eq(h) & detail.model.isin(names)]
                wide=selected.pivot(index='origin',columns='model',values='cumulative_log_forecast').reindex(columns=names)
                truth=selected.drop_duplicates('origin').set_index('origin').cumulative_log_actual
                common=wide.index[np.isfinite(wide).all(axis=1)&np.isfinite(truth.reindex(wide.index))]
                for name in names:
                    own=selected[selected.model.eq(name)].set_index('origin'); scored=own.reindex(common)
                    row=dict(scope=scope,sample=sample,h=h,model=name,n_intended=len(own),n_common=len(common),
                        n_own_forecasts=int(np.isfinite(own.cumulative_log_forecast).sum()))
                    for metric in ('mm','cumulative_log','cumulative_pct'):
                        error=scored[f'{metric}_forecast']-scored[f'{metric}_actual']; finite=np.isfinite(error)
                        row.update({metric+'_n':int(finite.sum()),metric+'_rmse':float(np.sqrt(np.mean(error[finite]**2))) if finite.any() else np.nan,
                                    metric+'_mae':float(error[finite].abs().mean()) if finite.any() else np.nan,
                                    metric+'_bias':float(error[finite].mean()) if finite.any() else np.nan})
                    summaries.append(row)
    return detail,pd.DataFrame(summaries)


def dependency_hashes():
    names=['food_path_experiment_r14.py','models/food_path_r14.py','test_food_path_r14.py',
        'tools/r14_food/prepare_inputs.py','docs/implementation/R14_FOOD_DESIGN.md',
        'path_improvements_experiment_r12.py','independent_bridge_experiment.py','forecast_independent.py',
        'independent_nowcast_experiment.py','models/path_inputs.py','models/independent_nowcast.py',
        'models/horizon_models.py','models/trend_gap.py','data/local_adapter.py','data/struct_inputs.py','config.py','cz_struct.py',
        'output/independent_bridge_forecasts.csv','output/independent_bridge_manifest.json',
        'output/independent_nowcast_forecasts.csv','output/independent_path_forecasts.csv',
        'output/independent_path_frozen_inputs.csv','output/research_r12/path/native_forecasts.csv',
        'output/research_r12/path/manifest.json','data/cz_agri_prices_raw.csv','data/cz_ppi_product_raw.csv',
        'data/release_calendar_cz_cpi.csv','data/admin_announcements_history.csv','data/cnb_mpr_cpi_quarterly.csv']
    files=[ROOT/name for name in names]+list((ROOT/'tests/fixtures/cleanup').glob('*'))
    files+=list((ROOT/'data/research_r14/food').glob('*'))
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(files)) if p.is_file()}


def run(destination=OUT):
    from forecast_independent import fixture_frames
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    hashes=dependency_hashes(); levels,available,input_meta=load_inputs(); frames=fixture_frames()
    food=frames['components'].food
    headline=read(ROOT/'output/independent_path_frozen_inputs.csv').headline_mm.dropna()
    h0=pd.read_csv(ROOT/'output/independent_nowcast_forecasts.csv',float_precision='round_trip').set_index('period')
    baseline=pd.read_csv(ROOT/'output/independent_bridge_forecasts.csv',float_precision='round_trip')
    r12=pd.read_csv(ROOT/'output/research_r12/path/native_forecasts.csv',float_precision='round_trip')
    r12=r12[r12.model.isin(REFERENCES[1:])]
    if list(h0.index)!=list(map(str,pd.period_range('2019-02','2026-07',freq='M'))):
        raise ValueError('Exactly the original 90 origins are required')
    validation=verify_baseline(frames,baseline,h0,headline)
    print('Frozen bridge replay and source checks passed.',flush=True)
    rows=[]; fits=[]; diagnostics=[]
    invariant=[c for c in baseline if c.startswith('weight_') or
               (c.startswith('contribution_') and c!='contribution_food')]
    for i,(origin,row) in enumerate(h0.iterrows()):
        t=pd.Period(origin,'M'); clock=pd.Timestamp(row.as_of_eve)
        result=forecast_origin(levels,available,t,clock)
        base=baseline[baseline.origin.eq(origin)].copy()
        for name,path in result['paths'].items():
            changed=replace_food(base,path); changed['model']=name
            pd.testing.assert_frame_equal(changed[invariant],base[invariant],check_exact=True)
            if changed.loc[changed.h.eq(0),'mm_forecast'].iloc[0]!=base.loc[base.h.eq(0),'mm_forecast'].iloc[0]:
                raise AssertionError('Original bridge/HARD_BASE h0 changed')
            # Future food values changed; inherited food-fallback/status and annual paths must change too.
            changed['status']=np.where(np.isfinite(changed.mm_forecast),'estimated','unavailable')
            changed['origin_status']='estimated' if np.isfinite(changed.mm_forecast).all() else 'unavailable'
            changed['converged']=np.isfinite(changed.mm_forecast); changed['fallback_used']=False
            allpath=changed.set_index('h').mm_forecast.to_dict(); hist=headline.loc[headline.index<t]
            for ix,r in changed.iterrows():
                h=int(r.h)
                changed.loc[ix,'yy_exante']=compound_path(hist,allpath,t,h,allpath[0])
                changed.loc[ix,'yy_conditional']=compound_path(hist,allpath,t,h,float(headline.get(t,np.nan)))
            rows.extend(changed.to_dict('records'))
        fits.extend(dict(origin=origin,**f) for f in result['fits'])
        diagnostics.append(dict(origin=origin,**result['diagnostics'],forecast_food_levels=result['forecast_food_levels']))
        if i%15==0 or i==89:print(f'Constructed food paths {i+1}/90: {origin}',flush=True)
    native=pd.DataFrame(rows)
    native.to_csv(destination/'native_forecasts.csv',index=False)
    dump(destination/'fit_diagnostics.json',fits); dump(destination/'origin_diagnostics.json',diagnostics)
    scalar=[{k:v for k,v in fit.items() if not isinstance(v,(list,dict))} for fit in fits]
    pd.DataFrame(scalar).to_csv(destination/'fit_audit.csv',index=False)
    # Forecasts are saved before scoring realised errors.
    keep=['origin','h','target','as_of_utc','model','mm_forecast']
    combined=pd.concat([native[keep],baseline[keep],r12[keep]],ignore_index=True)
    forecasts,target_delta=add_outcomes_and_compound(combined,headline,baseline)
    forecasts.to_csv(destination/'forecasts.csv',index=False)
    summary=all_scores(forecasts); summary.to_csv(destination/'summary.csv',index=False)
    uncertainty(forecasts).to_csv(destination/'paired_uncertainty.csv',index=False)
    food_native=pd.concat([native,baseline,r12],ignore_index=True)
    food_detail,food_summary=food_scores(food_native,food)
    food_detail.to_csv(destination/'food_outcomes.csv',index=False); food_summary.to_csv(destination/'food_summary.csv',index=False)
    coverage=[]
    for (name,h),group in forecasts.groupby(['model','h']):
        valid=group[np.isfinite(group.yy_exante)]
        coverage.append(dict(model=name,h=h,n_intended=len(group),n_finite_monthly=int(np.isfinite(group.mm_forecast).sum()),
            n_finite_annual=len(valid),n_available_annual_targets=int(np.isfinite(group.yy_actual).sum()),
            first_finite_origin=valid.origin.min() if len(valid) else None))
    pd.DataFrame(coverage).to_csv(destination/'coverage.csv',index=False)
    validation.update(target_reconstruction_max_abs_difference=target_delta,food_input_reconstruction=input_meta['food_reconstruction_max_abs_difference'],
        exact_nonfood_weights_h0=True,n_forecast_rows=len(forecasts),all_90_origins_retained=forecasts.origin.nunique()==90,
        inherited_annual_fields='Both yy_exante and diagnostic yy_conditional recomputed on changed native rows')
    dump(destination/'validation.json',validation)
    if dependency_hashes()!=hashes:raise AssertionError('Source/model changed during food experiment')
    outputs={p.name:sha(p) for p in sorted(destination.iterdir()) if p.suffix in ('.csv','.json') and p.name not in ('manifest.json','verification_receipt.json')}
    manifest=dict(prespec_commit=DECLARATION,completed_at=datetime.now(timezone.utc).isoformat(),inputs=hashes,outputs=outputs,
        command='python food_path_experiment_r14.py',models=list(MODELS),primary=MODELS[0],origins=90,
        python=platform.python_version(),packages={p:importlib.metadata.version(p) for p in ('numpy','pandas','scipy','statsmodels')},
        interpretation='Fixed statistical food pipeline; no structural identification, historical vintages, or fresh holdout claim.')
    dump(destination/'manifest.json',manifest)
    print(summary.loc[summary.scope.eq('common') & summary.h.isin([1,3,6,12]),
        ['sample','h','model','n_common','yy_rmse','yy_bias','mm_rmse']].to_string(index=False),flush=True)
    return manifest


def verify():
    saved=json.loads((OUT/'manifest.json').read_text())
    if dependency_hashes()!=saved['inputs']:raise AssertionError('Changed source/code hashes')
    for name,digest in saved['outputs'].items():
        if sha(OUT/name)!=digest:raise AssertionError(f'Changed output: {name}')
    def forbidden(*args,**kwargs):raise AssertionError('Offline food replay attempted network/database access')
    with tempfile.TemporaryDirectory(prefix='r14_food_') as folder,ExitStack() as stack:
        for target in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(target,side_effect=forbidden))
        replay=run(Path(folder))
        if replay['outputs']!=saved['outputs']:
            raise AssertionError(f"Full food replay mismatch: {[n for n,d in saved['outputs'].items() if replay['outputs'].get(n)!=d]}")
    receipt=dict(status='passed',refitted_origins=90,byte_identical_payloads=len(saved['outputs']),verified_inputs=len(saved['inputs']),
        network_database='blocked',checked_at=datetime.now(timezone.utc).isoformat())
    dump(OUT/'verification_receipt.json',receipt); print(receipt,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--verify',action='store_true')
    args=parser.parse_args(); verify() if args.verify else run()
