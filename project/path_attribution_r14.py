"""Evaluation-only component errors and exact single-block annual oracles."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/research_r14b/attribution'
BASE='INDEPENDENT_BRIDGE'
STABLE=('STABLE_PIPELINE_R14B','STABLE_LOCAL_CORE_R14B','STABLE_LONG_CORE_R14B','STABLE_LONG_GAP_R14B')
BLOCKS=('core','food','fuel','administered','alcohol_tobacco')
FILES={'headline':('target_headline_cpi_mm.csv',0),'core':('cnb_core_mm.csv',0),
    'food':('component_food_fuel_mm.csv','food'),'fuel':('component_food_fuel_mm.csv','fuel'),
    'administered':('cnb_regulated_mm.csv',0),'alcohol_tobacco':('alcohol_tobacco.csv',0)}
METRICS=('monthly_error','monthly_weighted_error','cumulative_log_error',
    'cumulative_weighted_error','annual_error','annual_block_error','annual_other_error')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strict_sum(values):
    values=np.asarray(values,dtype=float)
    return float(values.sum()) if np.isfinite(values).all() else np.nan


def log_changes(values):
    values=np.asarray(values,dtype=float)
    return np.where(np.isfinite(values)&(values>-100),100*np.log1p(np.where(values>-100,values,np.nan)/100),np.nan)


def annual_value(values):
    values=np.asarray(values,dtype=float)
    return float(100*np.expm1(log_changes(values).sum()/100)) if len(values)==12 and np.isfinite(values).all() and (values>-100).all() else np.nan


def annual_path(headline,path,origin,h):
    window=pd.period_range(origin+h-11,origin+h,freq='M')
    return annual_value([headline.get(m,np.nan) if m<origin else path.get(m.ordinal-origin.ordinal,np.nan) for m in window])


def calculate(native,actual):
    """Pure evaluation: all supplied forecasts are fixed and remain unchanged."""
    if not isinstance(actual.index,pd.PeriodIndex) or actual.index.freqstr!='M' or not actual.index.is_unique:
        raise ValueError('Unique monthly actual grid required')
    if native.duplicated(['model','origin','h']).any(): raise ValueError('Native model/origin/horizon keys must be unique')
    rows=[]
    for (model,origin),group in native.groupby(['model','origin'],sort=True):
        t=pd.Period(origin,'M'); g=group.set_index('h').sort_index()
        if g.index.tolist()!=list(range(13)): raise ValueError('Complete native horizon grid0..12 required')
        if g.target.tolist()!=pd.period_range(t,t+12,freq='M').astype(str).tolist(): raise ValueError('Native target/horizon mismatch')
        if g.as_of_utc.nunique()!=1: raise ValueError('Conflicting native decision clocks')
        p=g.mm_forecast.to_dict(); history=actual.headline.loc[actual.index<t]
        future=pd.period_range(t+1,t+12,freq='M')
        forecast_annual={h:annual_path(history,p,t,h) for h in range(1,13)}
        actual_annual={h:annual_value(actual.headline.reindex(pd.period_range(t+h-11,t+h,freq='M'))) for h in range(1,13)}
        for b in BLOCKS:
            weight='weight_'+('alc' if b=='alcohol_tobacco' else b)
            prediction=g.loc[1:12,'value_'+b].to_numpy(dtype=float)
            truth=actual[b].reindex(future).to_numpy(dtype=float)
            weights=g.loc[1:12,weight].to_numpy(dtype=float)
            weighted_prediction=g.loc[1:12,'contribution_'+b].to_numpy(dtype=float)
            if not np.allclose(weighted_prediction,weights*prediction,atol=1e-10,rtol=0,equal_nan=True):
                raise ValueError('Saved component contribution/weight mismatch')
            error=prediction-truth; weighted_error=weights*error
            log_error=log_changes(prediction)-log_changes(truth)
            oracle=p.copy()
            for h in range(1,13):
                oracle[h]=p[h]-weighted_error[h-1]
            for h in range(1,13):
                predicted_yy=forecast_annual[h]; actual_yy=actual_annual[h]
                oracle_yy=annual_path(history,oracle,t,h)
                e=predicted_yy-actual_yy; berror=predicted_yy-oracle_yy; other=oracle_yy-actual_yy
                square=berror**2; othersquare=other**2; cross=2*berror*other
                gain=e**2-othersquare
                if np.isfinite([e,berror,other]).all():
                    if abs(e-berror-other)>1e-10 or abs(e**2-square-othersquare-cross)>1e-8 or abs(gain-square-cross)>1e-8:
                        raise AssertionError('Exact single-block annual attribution failed')
                saved=g.loc[h,'yy_exante'] if 'yy_exante' in g else np.nan
                if np.isfinite(saved) and np.isfinite(predicted_yy) and abs(saved-predicted_yy)>1e-8:
                    raise AssertionError('Saved annual forecast does not match its monthly path')
                n_prediction=int(np.isfinite(prediction[:h]).sum()); n_actual=int(np.isfinite(truth[:h]).sum())
                rows.append(dict(model=model,origin=origin,target=str(t+h),h=h,block=b,
                    as_of_utc=g.as_of_utc.iloc[0],weight_at_destination=weights[h-1],
                    monthly_forecast=prediction[h-1],monthly_actual=truth[h-1],monthly_error=error[h-1],
                    monthly_weighted_error=weighted_error[h-1],
                    cumulative_log_forecast=strict_sum(log_changes(prediction[:h])),
                    cumulative_log_actual=strict_sum(log_changes(truth[:h])),cumulative_log_error=strict_sum(log_error[:h]),
                    cumulative_weighted_forecast=strict_sum(weighted_prediction[:h]),
                    cumulative_weighted_actual=strict_sum(weights[:h]*truth[:h]),
                    cumulative_weighted_error=strict_sum(weighted_error[:h]),
                    n_prediction_months=n_prediction,n_actual_months=n_actual,
                    component_path_status='complete' if n_prediction==h and n_actual==h else 'unavailable_prediction_or_actual',
                    annual_forecast=predicted_yy,annual_actual=actual_yy,annual_oracle=oracle_yy,
                    annual_error=e,annual_block_error=berror,annual_other_error=other,
                    block_squared_error=square,other_squared_error=othersquare,cross_term=cross,
                    headline_squared_error=e**2,oracle_mse_gain=gain,
                    annual_oracle_status='complete' if np.isfinite([predicted_yy,actual_yy,oracle_yy]).all() else 'unavailable_prediction_or_actual'))
    return pd.DataFrame(rows)


def samples(frame):
    return [('full',np.ones(len(frame),bool)),('recent_targets',frame.target>='2024-01'),('recent_origins',frame.origin>='2024-01')]


def masks(frame,column):
    finite=pd.Series(np.isfinite(frame[column]),index=frame.index)
    return [('own_coverage',finite),
        ('model_all_blocks_common',finite.groupby([frame.model,frame.origin,frame.h]).transform('all')),
        ('all_models_all_blocks_common',finite.groupby([frame.origin,frame.h]).transform('all'))]


def summarize(frame):
    rows=[]; coverage=[]
    for sample,sm in samples(frame):
        g=frame.loc[sm]
        for metric in METRICS:
            for scope,valid in masks(g,metric):
                for (model,block,h),sub in g.groupby(['model','block','h'],sort=True):
                    error=sub.loc[valid.reindex(sub.index),metric].to_numpy(dtype=float)
                    coverage.append(dict(sample=sample,scope=scope,model=model,block=block,h=h,metric=metric,
                        n_roster=len(sub),n_valid=len(error),n_unavailable=len(sub)-len(error)))
                    rows.append(dict(sample=sample,scope=scope,model=model,block=block,h=h,metric=metric,n=len(error),
                        bias=float(np.mean(error)) if len(error) else np.nan,
                        rmse=float(np.sqrt(np.mean(error**2))) if len(error) else np.nan,
                        mae=float(np.mean(abs(error))) if len(error) else np.nan))
    return pd.DataFrame(rows),pd.DataFrame(coverage)


def summarize_oracles(frame):
    rows=[]
    for sample,sm in samples(frame):
        g=frame.loc[sm]
        for scope,valid in masks(g,'oracle_mse_gain'):
            for (model,block,h),sub in g.groupby(['model','block','h'],sort=True):
                selected=sub.loc[valid.reindex(sub.index)]
                cols=('annual_error','annual_block_error','annual_other_error','block_squared_error',
                      'other_squared_error','cross_term','headline_squared_error','oracle_mse_gain')
                means={c:float(selected[c].mean()) if len(selected) else np.nan for c in cols}
                rows.append(dict(sample=sample,scope=scope,model=model,block=block,h=h,n=len(selected),
                    n_roster=len(sub),headline_rmse=float(np.sqrt(means['headline_squared_error'])),
                    oracle_rmse=float(np.sqrt(means['other_squared_error'])),
                    block_marginal_rmse=float(np.sqrt(means['block_squared_error'])),
                    **{c+'_mean':v for c,v in means.items()}))
    return pd.DataFrame(rows)


def load_actuals():
    folder=ROOT/'tests/fixtures/cleanup'; manifest=json.loads((folder/'MANIFEST.json').read_text())
    series={}
    for block,(name,column) in FILES.items():
        if sha(folder/name)!=manifest[name]: raise ValueError('Frozen actual fixture changed: '+name)
        frame=pd.read_csv(folder/name,index_col=0,float_precision='round_trip')
        frame.index=pd.PeriodIndex(frame.index,freq='M')
        series[block]=frame.iloc[:,column] if isinstance(column,int) else frame[column]
    return pd.DataFrame(series).sort_index()


def inputs_and_native(baseline_only):
    names=['path_attribution_r14.py','test_path_attribution_r14.py',
        'output/research_r14b/attribution/SPEC.md','output/independent_bridge_forecasts.csv',
        'tests/fixtures/cleanup/MANIFEST.json','data/local_adapter.py','cz_struct.py']
    names+=['tests/fixtures/cleanup/'+name for name,col in FILES.values()]
    base=pd.read_csv(ROOT/'output/independent_bridge_forecasts.csv',float_precision='round_trip')
    base=base.loc[base.model.eq(BASE)].copy(); rows=[base]
    expected_origins=pd.period_range('2019-02','2026-07',freq='M').astype(str).tolist()
    if sorted(base.origin.unique())!=expected_origins: raise ValueError('Original90 origins required')
    if not baseline_only:
        file=ROOT/'output/research_r14b/integration/native_forecasts.csv'
        native=pd.read_csv(file,float_precision='round_trip')
        names.append(file.relative_to(ROOT).as_posix())
        manifest=file.with_name('manifest.json')
        if manifest.exists():
            info=json.loads(manifest.read_text())
            if 'native_forecasts.csv' in info.get('outputs',{}) and sha(file)!=info['outputs']['native_forecasts.csv']:
                raise ValueError('Integration native hash mismatch')
            names.append(manifest.relative_to(ROOT).as_posix())
        keys=['origin','h']; ref=base.sort_values(keys).reset_index(drop=True)
        for model in STABLE:
            g=native.loc[native.model.eq(model)].sort_values(keys).reset_index(drop=True)
            if not g[keys].equals(ref[keys]): raise ValueError('Missing or different stable model roster: '+model)
            if not g.as_of_utc.equals(ref.as_of_utc): raise ValueError('Stable decision clocks differ')
            weights=[c for c in ref if c.startswith('weight_')]
            if not g[weights].equals(ref[weights]): raise ValueError('Stable saved weights differ')
            if not np.array_equal(g.loc[g.h.eq(0),'mm_forecast'],ref.loc[ref.h.eq(0),'mm_forecast'],equal_nan=True):
                raise ValueError('Stable h0 differs')
            rows.append(g)
    return {name:sha(ROOT/name) for name in sorted(set(names))},pd.concat(rows,ignore_index=True)


def run(destination=None,baseline_only=False):
    destination=Path(destination or (OUT/'baseline_only' if baseline_only else OUT))
    destination.mkdir(parents=True,exist_ok=True)
    inputs,native=inputs_and_native(baseline_only); actual=load_actuals()
    detail=calculate(native,actual); detail.to_csv(destination/'component_errors.csv',index=False)
    summary,coverage=summarize(detail)
    summary.to_csv(destination/'component_summary.csv',index=False); coverage.to_csv(destination/'coverage.csv',index=False)
    oracle=summarize_oracles(detail);oracle.to_csv(destination/'oracle_summary.csv',index=False)
    detail.loc[detail.h.isin([6,12])].to_csv(destination/'events_h6_h12.csv',index=False)
    actual.to_csv(destination/'actual_component_targets.csv',index_label='period')
    result=dict(inputs=inputs,outputs={name:sha(destination/name) for name in
        ['component_errors.csv','component_summary.csv','coverage.csv','oracle_summary.csv','events_h6_h12.csv','actual_component_targets.csv']},
        models=sorted(native.model.unique()),n_origins=native.origin.nunique(),n_detail_rows=len(detail),
        baseline_only=baseline_only,meaning='Evaluation-only frozen-target single-block oracles; no additive causal shares',
        blocks={b:dict(actual_file=FILES[b][0],weight_column='weight_'+('alc' if b=='alcohol_tobacco' else b)) for b in BLOCKS})
    (destination/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Calculated {len(detail)} retained component rows across {native.model.nunique()} fixed models.')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');parser.add_argument('--baseline-only',action='store_true')
    args=parser.parse_args();folder=OUT/'baseline_only' if args.baseline_only else OUT
    if args.verify:
        expected=json.loads((folder/'manifest.json').read_text())
        for name,value in expected['inputs'].items(): assert sha(ROOT/name)==value, name
        for name,value in expected['outputs'].items(): assert sha(folder/name)==value, name
        with tempfile.TemporaryDirectory(prefix='r14_attribution_') as tmp,ExitStack() as stack:
            for target in ('socket.create_connection','socket.socket.connect','requests.sessions.Session.request'):
                stack.enter_context(patch(target,side_effect=AssertionError('Offline attribution forbids network')))
            got=run(tmp,args.baseline_only); assert got==expected, 'Offline attribution changed'
        print('Verified: six attribution outputs and manifest reproduce exactly offline.')
    else:run(baseline_only=args.baseline_only)
