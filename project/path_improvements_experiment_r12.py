"""Portable frozen-input R12 path study. Run: python path_improvements_experiment_r12.py.

Only output/research_r12/path is written; no network or database inputs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time
from unittest.mock import patch

import numpy as np
import pandas as pd

from models.food_path_r12 import forecast_food
from models.cumulative_path_r12 import forecast_targets
from models.path_inputs import compound_path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/research_r12/path'
NEW=['FOOD_TREND_R12','FOOD_COST_R12','DIRECT_MONTHLY_R12','DIRECT_CUMULATIVE_R12']
REFERENCE=['INDEPENDENT_BRIDGE','RF_U_FX','BVAR_U_FX','NAIVE']


def read(path):
    frame=pd.read_csv(path,index_col=0,float_precision='round_trip')
    frame.index=pd.PeriodIndex(frame.index,freq='M')
    return frame


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,value):
    def convert(v):
        if isinstance(v,(np.integer,np.floating,np.bool_)):return v.item()
        if isinstance(v,(pd.Period,pd.Timestamp,Path)):return str(v)
        if isinstance(v,np.ndarray):return v.tolist()
        raise TypeError(type(v).__name__)
    Path(path).write_text(json.dumps(value,indent=2,default=convert),encoding='utf-8')


def replace_food(frame,food_path):
    frame=frame.copy()
    for h,value in food_path.items():
        if h<4:raise ValueError('R12 long-food replacement requires h>=4')
        selected=frame.h==h
        delta=frame.loc[selected,'weight_food']*(value-frame.loc[selected,'value_food'])
        frame.loc[selected,'mm_forecast']+=delta
        frame.loc[selected,'value_food']=value
        frame.loc[selected,'contribution_food']=frame.loc[selected,'weight_food']*value
    return frame


def score_panel(frame,models,scope='roster_common'):
    rows=[]
    for sample,mask in [('full',np.ones(len(frame),dtype=bool)),
                        ('recent_targets',frame.target>='2024-01'),
                        ('recent_origins',frame.origin>='2024-01')]:
        chosen=frame.loc[mask & frame.model.isin(models)]
        for h in range(1,13):
            data=chosen.loc[chosen.h==h]
            if data.empty:continue
            wide=data.pivot(index='origin',columns='model',values='yy_exante').reindex(columns=models)
            actual=data.drop_duplicates('origin').set_index('origin').yy_actual
            common=wide.index[np.isfinite(wide.to_numpy()).all(axis=1)&np.isfinite(actual.reindex(wide.index))]
            for model in models:
                own=data.loc[data.model==model].set_index('origin')
                scored=own.reindex(common)
                row=dict(scope=scope,sample=sample,h=h,model=model,n_intended_origins=len(own),
                    n_available_targets=int(np.isfinite(own.yy_actual).sum()),
                    n_own_forecasts=int((np.isfinite(own.yy_actual)&np.isfinite(own.yy_exante)).sum()),n_common=len(common))
                for prefix,pred,truth in [('yy','yy_exante','yy_actual'),('mm','mm_forecast','mm_actual'),
                    ('cumulative_log','cumulative_log_forecast','cumulative_log_actual')]:
                    error=scored[pred]-scored[truth]
                    finite=np.isfinite(error)
                    row[f'{prefix}_n']=int(finite.sum())
                    row[f'{prefix}_rmse']=float(np.sqrt(np.mean(error[finite]**2))) if finite.any() else np.nan
                    row[f'{prefix}_mae']=float(np.mean(np.abs(error[finite]))) if finite.any() else np.nan
                    row[f'{prefix}_bias']=float(np.mean(error[finite])) if finite.any() else np.nan
                rows.append(row)
    return pd.DataFrame(rows)


def verify_cost_mapping(food_features):
    """Verify source-month recovery against cached raw data, before any fit."""
    import cz_struct as s
    from data.struct_inputs import load_agri_price_mm
    agri=load_agri_price_mm().shift(-1,freq='M')
    raw=pd.read_csv(ROOT/'data/cz_ppi_product_raw.csv',low_memory=False)
    div=raw['CZCPA3.CZCPA_U2'].astype(str).str.replace('.0','',regex=False)
    selected=raw[(div=='10')&raw['CZCPA3.CZCPA_U3'].isna()&(raw.TYPUDAJE5A=='IZ2015')]
    selected=selected[selected.CASMKMQRM12.astype(str).str.match(r'^\d{4}-\d{2}$')]
    level=pd.Series(selected.Hodnota.to_numpy(dtype=float),index=pd.PeriodIndex(selected.CASMKMQRM12,freq='M')).groupby(level=0).last().sort_index()
    ppi=100*level.pct_change(fill_method=None)
    recovered=pd.concat([food_features.agri_l1.shift(-2,freq='M').rename('agri'),
                         food_features.food_ppi_l1.shift(-1,freq='M').rename('ppi')],axis=1)
    report={}
    for col,actual in [('agri',agri),('ppi',ppi)]:
        pair=pd.concat([recovered[col],actual.rename('raw')],axis=1).dropna()
        delta=float(np.max(np.abs(pair.iloc[:,0]-pair.raw)))
        if not len(pair) or delta>1e-10:raise AssertionError(f'{col} raw-source mapping mismatch {delta}')
        report[col]=dict(n_source_months=len(pair),max_abs_difference=delta,
            units='mean available-product log m/m percentage' if col=='agri' else 'arithmetic m/m percentage',
            first=str(pair.index.min()),last=str(pair.index.max()))
    # Calendar arithmetic precedes localization so DST cannot move the release date.
    recovered['agri_available_at']=[((p+1).to_timestamp()+pd.Timedelta(days=25)).tz_localize('Europe/Prague') for p in recovered.index]
    recovered['ppi_available_at']=[((p+1).to_timestamp()+
        pd.Timedelta(days=s._availability_rule('food_ppi_l1',p+1)[1]-1)).tz_localize('Europe/Prague') for p in recovered.index]
    report['clock_quality']='Reconstructed source publication rules, not archived observation releases; r-2 source cap retained.'
    return recovered,report


def verify_baseline(frames,baseline,h0,headline):
    """Replay unchanged regressions/weights, reusing only unchanged short X13."""
    import cz_struct as s
    from independent_bridge_experiment import forecast_bridge
    old=json.loads((ROOT/'output/independent_bridge_manifest.json').read_text())
    checked=[]
    for relative,value in old['fingerprints'].items():
        if sha(ROOT/relative)!=value:raise AssertionError(f'Frozen bridge source changed: {relative}')
        checked.append(relative)
    maxima=dict(monthly=0.,contributions=0.,food_long=0.,annual=0.,h0=0.)
    copied_short=0; total=0
    for ts,g in baseline.groupby('origin',sort=True):
        t=pd.Period(ts,'M'); g=g.set_index('h')
        local=pd.Timestamp(h0.loc[ts,'as_of_eve']); aware=local.tz_localize('Europe/Prague')
        refh0=float(h0.loc[ts,'HARD_BASE'])
        maxima['h0']=max(maxima['h0'],abs(g.loc[0,'mm_forecast']-refh0))
        def short_reuse(*args,h=0,**kwargs):
            if h not in (1,2,3):raise AssertionError('Only unchanged X13 h1..3 may be reused')
            s.FOOD_DIAG.clear();s.FOOD_DIAG.update(method='frozen_identical_X13_reuse')
            return float(g.loc[h,'value_food'])
        with patch.object(s,'food_forecast',short_reuse):
            replay=forecast_bridge(frames,t,aware,refh0)
        for h in range(13):
            got=replay['path'][h]; want=g.loc[h,'mm_forecast']; total+=1
            if np.isfinite(got)!=np.isfinite(want):raise AssertionError('Baseline finite mask changed')
            if np.isfinite(got):maxima['monthly']=max(maxima['monthly'],abs(got-want))
            for block,value in replay['contributions'].get(h,{}).items():
                expected=g.loc[h,f'contribution_{block}']
                if np.isfinite(value)!=np.isfinite(expected):raise AssertionError('Contribution finite mask mismatch')
                if np.isfinite(value):maxima['contributions']=max(maxima['contributions'],abs(value-expected))
            if h>=4:maxima['food_long']=max(maxima['food_long'],abs(replay['block_values'][h]['food']-g.loc[h,'value_food']))
            yy=compound_path(headline.loc[headline.index<t],replay['path'],t,h,refh0)
            expected=g.loc[h,'yy_exante']
            if np.isfinite(yy)!=np.isfinite(expected):raise AssertionError('Annual finite mask mismatch')
            if np.isfinite(yy):maxima['annual']=max(maxima['annual'],abs(yy-expected))
        copied_short+=3
    if max(maxima.values())>1e-10:raise AssertionError(f'Baseline replay mismatch {maxima}')
    return dict(status='passed',points=total,max_abs_differences=maxima,
        source_hashes_checked=checked,short_food_values_reused=copied_short,
        reuse_reason='Identical code and frozen feature/data hashes. Only X13 h1..3 reused; all weights and nonfood components replayed at all origins.')


def released_at_origin(series,t,local_clock):
    import cz_struct as s
    hist=series.loc[series.index<t]
    mask=s._released_index(hist.index,local_clock)
    result=hist.loc[mask]
    if len(result)!=len(hist):raise AssertionError('Unreleased prior CPI would violate contiguous-history convention')
    return result


def benchmark_rw(headline,t):
    history=headline.loc[headline.index<t]
    known=history.reindex(pd.period_range(t-12,t-1,freq='M'))
    q=float(100*np.log1p(known/100).sum())
    path={}
    for h in range(13):
        target=t+h
        prev=[]
        for p in pd.period_range(target-11,target-1,freq='M'):
            prev.append(history.get(p,np.nan) if p<t else path[p.ordinal-t.ordinal])
        path[h]=float(100*np.expm1(q/100-np.log1p(np.array(prev)/100).sum()))
    return path


def add_outcomes_and_compound(frame,headline,stored):
    rows=[]; max_actual_delta=0.
    exact=stored.set_index(['origin','h'])
    for (origin,model),g in frame.groupby(['origin','model'],sort=False):
        t=pd.Period(origin,'M'); path=g.set_index('h').mm_forecast.to_dict()
        for row in g.to_dict('records'):
            h=row['h']; target=t+h
            yy=compound_path(headline.loc[headline.index<t],path,t,h,path[0])
            month=float(headline.get(target,np.nan))
            actual_window=headline.reindex(pd.period_range(target-11,target,freq='M'))
            annual=float(100*np.expm1(np.log1p(actual_window/100).sum())) if np.isfinite(actual_window).all() else np.nan
            reference=exact.loc[(origin,h)]
            for a,b in [(month,reference.mm_actual),(annual,reference.yy_actual)]:
                if np.isfinite(a)!=np.isfinite(b):raise AssertionError('Changed original target finite mask')
                if np.isfinite(a):max_actual_delta=max(max_actual_delta,abs(a-b))
            future=headline.reindex(pd.period_range(t+1,t+h,freq='M')) if h else pd.Series(dtype=float)
            predicted=np.array([path[k] for k in range(1,h+1)])
            row.update(mm_actual=reference.mm_actual,yy_actual=reference.yy_actual,yy_exante=yy,
                cumulative_log_forecast=float(100*np.log1p(predicted/100).sum()) if np.isfinite(predicted).all() else np.nan,
                cumulative_log_actual=float(100*np.log1p(future/100).sum()) if np.isfinite(future).all() else np.nan)
            rows.append(row)
    if max_actual_delta>1e-10:raise AssertionError(f'Original target mismatch {max_actual_delta}')
    return pd.DataFrame(rows),max_actual_delta


def paired_bootstrap(frame,models):
    rng=np.random.default_rng(1209); records=[]
    for sample,mask in [('full',np.ones(len(frame),dtype=bool)),('recent_targets',frame.target>='2024-01'),('recent_origins',frame.origin>='2024-01')]:
        selected=frame.loc[mask]
        for h in range(1,13):
            g=selected.loc[selected.h==h]
            base=g[g.model=='INDEPENDENT_BRIDGE'].set_index('origin')
            for model in models:
                other=g[g.model==model].set_index('origin')
                pair=pd.concat([(other.yy_exante-other.yy_actual).rename('challenger'),
                    (base.yy_exante-base.yy_actual).rename('bridge')],axis=1).dropna().sort_index()
                n=len(pair)
                if not n:continue
                d=(pair.challenger**2-pair.bridge**2).to_numpy()
                starts=rng.integers(0,n,size=(2000,int(np.ceil(n/12))))
                idx=((starts[:,:,None]+np.arange(12))%n).reshape(2000,-1)[:,:n]
                draws=d[idx].mean(axis=1)
                lo,hi=np.quantile(draws,[.025,.975])
                records.append(dict(sample=sample,h=h,model=model,n=n,mse_difference=float(d.mean()),
                    ci_low=float(lo),ci_high=float(hi),block_length=12,replicates=2000,seed=1209))
    return pd.DataFrame(records)


def all_scores(frame):
    scores=[score_panel(frame,NEW+REFERENCE+['LAST_YOY_RW'])]
    for model in NEW+['LAST_YOY_RW']:
        scores.append(score_panel(frame,['INDEPENDENT_BRIDGE',model],f'paired_{model}'))
    return pd.concat(scores,ignore_index=True)


def cnb_comparison(frame,headline):
    from independent_bridge_experiment import match_cnb_quarters,_quarter_metrics
    models=NEW+REFERENCE+['LAST_YOY_RW']
    quarters=match_cnb_quarters(frame,pd.read_csv(ROOT/'data/cnb_mpr_cpi_quarterly.csv'),headline,models)
    tables=[]
    for sample,selected in [('all_reports',quarters),('recent_reports',quarters.loc[quarters.report_date>='2024-01-01'])]:
        tables.append(_quarter_metrics(selected,models+['CNB'],'R12_common',sample))
    return quarters,pd.concat(tables,ignore_index=True)


def verify_saved(folder):
    """Offline deterministic scoring replay plus all payload/source hash checks."""
    manifest=json.loads((folder/'manifest.json').read_text())
    for relative,value in manifest['fingerprints'].items():
        if sha(ROOT/relative)!=value:raise AssertionError(f'Input/code hash mismatch: {relative}')
    for name,value in manifest['output_hashes'].items():
        if sha(folder/name)!=value:raise AssertionError(f'Payload hash mismatch: {name}')
    saved=pd.read_csv(folder/'forecasts.csv',float_precision='round_trip')
    headline=read(ROOT/'output/independent_path_frozen_inputs.csv').headline_mm.dropna()
    original=pd.read_csv(ROOT/'output/independent_bridge_forecasts.csv',float_precision='round_trip')
    replay,_=add_outcomes_and_compound(saved,headline,original)
    for col in ['mm_actual','yy_actual','yy_exante','cumulative_log_forecast','cumulative_log_actual']:
        if not np.allclose(saved[col],replay[col],atol=1e-12,rtol=0,equal_nan=True):
            raise AssertionError(f'Outcome/compounding replay mismatch {col}')
    expected=all_scores(replay)
    observed=pd.read_csv(folder/'summary.csv',float_precision='round_trip')
    pd.testing.assert_frame_equal(expected,observed,check_dtype=False,atol=1e-12,rtol=0)
    uncertainty=paired_bootstrap(replay,NEW)
    pd.testing.assert_frame_equal(uncertainty,pd.read_csv(folder/'paired_uncertainty.csv',float_precision='round_trip'),
        check_dtype=False,atol=1e-12,rtol=0)
    quarters,quarter_scores=cnb_comparison(replay,headline)
    # The mixed 'all'/integer grouping column round-trips through CSV as text.
    quarter_scores['quarters_ahead']=quarter_scores.quarters_ahead.astype(str)
    pd.testing.assert_frame_equal(quarter_scores,pd.read_csv(folder/'cnb_summary.csv',float_precision='round_trip'),
        check_dtype=False,atol=1e-12,rtol=0)
    receipt=dict(status='passed',source_hashes=len(manifest['fingerprints']),payload_hashes=len(manifest['output_hashes']),
        forecast_rows=len(saved),summary_rows=len(observed),bootstrap_rows=len(uncertainty),cnb_rows=len(quarter_scores),
        tolerance=1e-12,refits=0,clock='saved frozen release-eve',checked_at=datetime.now(timezone.utc).isoformat())
    dump(folder/'verification_receipt.json',receipt)
    print(json.dumps(receipt,indent=2),flush=True)


def main(argv=None):
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--verify',action='store_true',help='Replay saved arithmetic/scoring offline and verify hashes, without fitting')
    parser.add_argument('--output-dir',type=Path,default=OUT)
    args=parser.parse_args(argv)
    permitted=(ROOT/'output/research_r12/path').resolve()
    OUT=args.output_dir.resolve()
    if not OUT.is_relative_to(permitted):raise ValueError('Output directory must remain under output/research_r12/path')
    OUT.mkdir(parents=True,exist_ok=True)
    if args.verify:
        verify_saved(OUT)
        return
    import cz_struct as s
    from forecast_independent import fixture_frames
    from path_experiment import _eve
    start=time.monotonic()
    frames=fixture_frames()
    headline=read(ROOT/'output/independent_path_frozen_inputs.csv').headline_mm.dropna()
    h0=pd.read_csv(ROOT/'output/independent_nowcast_forecasts.csv',float_precision='round_trip').set_index('period')
    baseline=pd.read_csv(ROOT/'output/independent_bridge_forecasts.csv',float_precision='round_trip')
    references=pd.read_csv(ROOT/'output/independent_path_forecasts.csv',float_precision='round_trip')
    validation=verify_baseline(frames,baseline,h0,headline)
    costs,mapping=verify_cost_mapping(frames['food_features'])
    validation['cost_raw_mapping']=mapping
    dump(OUT/'validation.json',validation)
    print('Frozen baseline and cost source mapping verified.',flush=True)
    if args.verify_only:return
    code=[Path(__file__),ROOT/'models/food_path_r12.py',ROOT/'models/cumulative_path_r12.py',
          ROOT/'test_path_improvements_r12.py',ROOT/'docs/implementation/R12_PATH_SPEC.md']
    inputs=[ROOT/'output/independent_bridge_forecasts.csv',ROOT/'output/independent_bridge_manifest.json',
        ROOT/'output/independent_nowcast_forecasts.csv',ROOT/'output/independent_path_forecasts.csv',
        ROOT/'output/independent_path_frozen_inputs.csv',ROOT/'data/cz_agri_prices_raw.csv',
        ROOT/'data/cz_ppi_product_raw.csv',ROOT/'data/release_calendar_cz_cpi.csv',ROOT/'data/struct_inputs.py',
        ROOT/'data/cnb_mpr_cpi_quarterly.csv',ROOT/'independent_bridge_experiment.py',
        ROOT/'path_experiment.py',ROOT/'forecast_independent.py',ROOT/'independent_nowcast_experiment.py',
        ROOT/'models/trend_gap.py',ROOT/'models/independent_nowcast.py',ROOT/'models/horizon_models.py',
        ROOT/'config.py',ROOT/'data/local_adapter.py',ROOT/'data/admin_announcements_history.csv',
        ROOT/'tests/fixtures/cleanup/MANIFEST.json',
        ROOT/'cz_struct.py',ROOT/'models/path_inputs.py']+list((ROOT/'tests/fixtures/cleanup').glob('*.csv'))
    manifest=dict(started_at=datetime.now(timezone.utc).isoformat(),prespec_commit='abd1342',
        command='python path_improvements_experiment_r12.py',output_directory=str(OUT.relative_to(ROOT)),origins=h0.index.tolist(),variants=NEW,
        fingerprints={p.relative_to(ROOT).as_posix():sha(p) for p in code+inputs},
        packages={p:importlib.metadata.version(p) for p in ['numpy','pandas','scikit-learn','statsmodels']},
        vintage_limit='Latest stored statistical values; reconstructed release timing. No expectations. Repeatedly inspected pseudo-out-of-sample research.',
        target_clock='h0=t; h12=t+12; CPI training labels released and <=t-1',
        prediction_stage_before_scoring=True)
    dump(OUT/'manifest.json',manifest)
    historical_clocks={r:_eve(r).tz_localize('Europe/Prague') for r in frames['components'].index}
    # Assert the historical state feature edge was actually released at its own clock.
    for r,clock in historical_clocks.items():
        previous=r-1
        if previous in frames['components'].index and not s._released_index(pd.PeriodIndex([previous],freq='M'),clock.tz_localize(None))[0]:
            raise AssertionError(f'Historical feature label {previous} unavailable at pseudo-origin {r}')
    rows=[]; diagnostics=[]
    keep=['origin','h','target','as_of_utc','mm_forecast','model']
    for i,ts in enumerate(h0.index):
        t=pd.Period(ts,'M'); local=pd.Timestamp(h0.loc[ts,'as_of_eve']); aware=local.tz_localize('Europe/Prague')
        y=released_at_origin(headline,t,local)
        food=released_at_origin(frames['components'].food,t,local)
        a=forecast_food(food,t,costs,historical_clocks,aware)
        b=forecast_targets(y,t,float(h0.loc[ts,'HARD_BASE']))
        base=baseline.loc[baseline.origin==ts].copy()
        for model,path in a['paths'].items():
            changed=replace_food(base,path);changed['model']=model
            rows.extend(changed[keep+['value_food','contribution_food','weight_food']].to_dict('records'))
        for model,path in b['paths'].items():
            rows.extend(dict(origin=ts,h=h,target=str(t+h),as_of_utc=aware.tz_convert('UTC').isoformat(),
                mm_forecast=path[h],model=model) for h in range(13))
        diagnostics.append(dict(origin=ts,food=a['diagnostics'],targets=b['diagnostics'],headline_edge=str(y.index[-1]),food_edge=str(food.index[-1])))
        print(f'{ts}: {i+1}/{len(h0)} origins constructed; {time.monotonic()-start:.1f}s',flush=True)
    # Preserve forecasts before any realised-error computation.
    native=pd.DataFrame(rows)
    native.to_csv(OUT/'native_forecasts.csv',index=False)
    dump(OUT/'diagnostics.json',diagnostics)
    rw=[]
    for ts in h0.index:
        t=pd.Period(ts,'M'); path=benchmark_rw(headline,t)
        stamp=pd.Timestamp(h0.loc[ts,'as_of_eve']).tz_localize('Europe/Prague').tz_convert('UTC').isoformat()
        for h in range(13):rw.append(dict(origin=ts,h=h,target=str(t+h),as_of_utc=stamp,model='LAST_YOY_RW',mm_forecast=path[h]))
    existing=references.loc[references.model.isin(REFERENCE[1:]) & references.origin.isin(h0.index),keep]
    all_native=pd.concat([native,baseline[keep],existing,pd.DataFrame(rw)],ignore_index=True)
    frame,max_target_delta=add_outcomes_and_compound(all_native,headline,baseline)
    frame.to_csv(OUT/'forecasts.csv',index=False)
    summary=all_scores(frame)
    summary.to_csv(OUT/'summary.csv',index=False)
    uncertainty=paired_bootstrap(frame,NEW)
    uncertainty.to_csv(OUT/'paired_uncertainty.csv',index=False)
    quarters,quarter_scores=cnb_comparison(frame,headline)
    quarters.to_csv(OUT/'cnb_quarters.csv',index=False)
    quarter_scores.to_csv(OUT/'cnb_summary.csv',index=False)
    validation.update(original_target_max_abs_difference=max_target_delta,
        target_rows=len(frame),unique_keys=not frame.duplicated(['origin','h','model']).any(),
        all_origins_retained=frame.origin.nunique()==90,
        h1_monthly_cumulative_max_delta=float(np.max(np.abs(native.loc[(native.model=='DIRECT_MONTHLY_R12')&(native.h==1),'mm_forecast'].to_numpy()-native.loc[(native.model=='DIRECT_CUMULATIVE_R12')&(native.h==1),'mm_forecast'].to_numpy()))))
    dump(OUT/'validation.json',validation)
    if (OUT/'prereview_native_forecasts.csv').exists():
        prior=pd.read_csv(OUT/'prereview_native_forecasts.csv',float_precision='round_trip')
        delta=native.mm_forecast-prior.mm_forecast
        validation['constant_scale_fix_empirical_max_abs_difference']=float(np.nanmax(np.abs(delta)))
        validation['constant_scale_fix_changed_rows']=int((np.abs(delta)>1e-12).sum())
        dump(OUT/'validation.json',validation)
    payload=['native_forecasts.csv','diagnostics.json','forecasts.csv','summary.csv','paired_uncertainty.csv',
        'validation.json','cnb_quarters.csv','cnb_summary.csv']
    manifest.update(completed_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-start,
        forecast_rows=len(frame),output_hashes={name:sha(OUT/name) for name in payload},
        log_policy='Operational logs are excluded from payload hashes because open stdout logs remain mutable.')
    dump(OUT/'manifest.json',manifest)
    print(summary.loc[(summary.scope=='roster_common')&summary.h.isin([1,6,12]),
        ['sample','h','model','n_common','yy_rmse','yy_bias','mm_rmse','cumulative_log_rmse']].to_string(index=False),flush=True)


if __name__=='__main__':
    main()
