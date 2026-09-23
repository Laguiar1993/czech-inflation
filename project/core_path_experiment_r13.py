"""Offline R13 fixed core-path factorial. --verify fully refits and re-scores."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from core_split_experiment import publication_dates
from data.core_split import load_frozen, monthly_rates, weights_at
from models.core_path_r13 import PRIMARY, LABOUR, external_at, forecast_origin, replace_core
from path_improvements_experiment_r12 import (
    read, sha, dump, verify_baseline, score_panel, add_outcomes_and_compound, benchmark_rw)

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/research_r13/core_path'
REFERENCE=('INDEPENDENT_BRIDGE','RF_U_FX','BVAR_U_FX','NAIVE','LAST_YOY_RW')
DECLARATION='a74a536f70050968ec594f40400cfa0842e94749'
PAIRS=[(m,'INDEPENDENT_BRIDGE') for m in (*PRIMARY,*LABOUR)]+[
    (PRIMARY[1],PRIMARY[0]),(PRIMARY[3],PRIMARY[2]),
    (PRIMARY[2],PRIMARY[0]),(PRIMARY[3],PRIMARY[1]),(LABOUR[0],LABOUR[1])]


def all_scores(frame):
    tables=[score_panel(frame,[*PRIMARY,*REFERENCE],'primary_common'),
            score_panel(frame,[*LABOUR,'INDEPENDENT_BRIDGE'],'labour_common')]
    for model in (*PRIMARY,*LABOUR,*REFERENCE):
        tables.append(score_panel(frame,[model],'own_coverage'))
    for model,control in PAIRS:
        tables.append(score_panel(frame,[control,model],f'paired_{model}_vs_{control}'))
    return pd.concat(tables,ignore_index=True)


def paired_bootstrap(frame):
    rng=np.random.default_rng(1309); rows=[]
    for sample,mask in [('full',np.ones(len(frame),bool)),
                        ('recent_targets',frame.target>='2024-01'),
                        ('recent_origins',frame.origin>='2024-01')]:
        for h in range(1,13):
            g=frame.loc[mask & frame.h.eq(h)]
            for model,control in PAIRS:
                a=g[g.model==model].set_index('origin')
                b=g[g.model==control].set_index('origin')
                pair=pd.concat([(a.yy_exante-a.yy_actual).rename('a'),
                                (b.yy_exante-b.yy_actual).rename('b')],axis=1).dropna().sort_index()
                n=len(pair)
                if not n:
                    continue
                delta=(pair.a**2-pair.b**2).to_numpy()
                starts=rng.integers(0,n,size=(2000,int(np.ceil(n/12))))
                indices=((starts[:,:,None]+np.arange(12))%n).reshape(2000,-1)[:,:n]
                lower,upper=np.quantile(delta[indices].mean(axis=1),[.025,.975])
                rows.append(dict(sample=sample,h=h,model=model,control=control,n=n,
                    mse_difference=delta.mean(),ci_low=lower,ci_high=upper,
                    block_length=12,replicates=2000,seed=1309))
    return pd.DataFrame(rows)


def core_evaluation(native,core,baseline):
    """Arithmetic target error and its divergence from compounded core inflation."""
    reference=baseline[['origin','h','target','model','value_core']]
    combined=pd.concat([native[['origin','h','target','model','value_core']],reference],ignore_index=True)
    records=[]
    for (origin,model),g in combined.groupby(['origin','model'],sort=False):
        t=pd.Period(origin,'M'); values=g.set_index('h').value_core
        for h in range(1,13):
            actual=core.reindex(pd.period_range(t+1,t+h,freq='M')).to_numpy(dtype=float)
            predicted=values.reindex(range(1,h+1)).to_numpy(dtype=float)
            row=dict(origin=origin,target=str(t+h),model=model,h=h,
                     mm_forecast=values.get(h,np.nan),mm_actual=core.get(t+h,np.nan))
            for prefix,array in [('forecast',predicted),('actual',actual)]:
                finite=np.isfinite(array).all()
                arithmetic=float(array.sum()) if finite else np.nan
                compounded=float(100*np.expm1(np.log1p(array/100).sum())) if finite and (array>-100).all() else np.nan
                row.update({f'cumulative_arithmetic_{prefix}':arithmetic,
                            f'cumulative_compounded_{prefix}':compounded,
                            f'arithmetic_minus_compounded_{prefix}':arithmetic-compounded})
            records.append(row)
    detail=pd.DataFrame(records); scores=[]
    for scope,models in [('primary_common',[*PRIMARY,'INDEPENDENT_BRIDGE']),
                         ('labour_common',[*LABOUR,'INDEPENDENT_BRIDGE'])]:
        for sample,mask in [('full',np.ones(len(detail),bool)),
                            ('recent_targets',detail.target>='2024-01'),
                            ('recent_origins',detail.origin>='2024-01')]:
            for h in range(1,13):
                selected=detail.loc[mask & detail.h.eq(h) & detail.model.isin(models)]
                wide=selected.pivot(index='origin',columns='model',values='cumulative_arithmetic_forecast').reindex(columns=models)
                truth=selected.drop_duplicates('origin').set_index('origin').cumulative_arithmetic_actual
                common=wide.index[np.isfinite(wide).all(axis=1)&np.isfinite(truth.reindex(wide.index))]
                for model in models:
                    own=selected[selected.model==model].set_index('origin')
                    data=own.reindex(common); row=dict(scope=scope,sample=sample,h=h,model=model,n_common=len(common))
                    for metric in ('mm','cumulative_arithmetic','cumulative_compounded'):
                        error=data[f'{metric}_forecast']-data[f'{metric}_actual']; finite=np.isfinite(error)
                        row.update({metric+'_n':int(finite.sum()),metric+'_rmse':float(np.sqrt(np.mean(error[finite]**2))) if finite.any() else np.nan,
                                    metric+'_mae':float(error[finite].abs().mean()) if finite.any() else np.nan,
                                    metric+'_bias':float(error[finite].mean()) if finite.any() else np.nan})
                    scores.append(row)
    return detail,pd.DataFrame(scores)


def dependency_hashes():
    names=['core_path_experiment_r13.py','models/core_path_r13.py','test_core_path_r13.py',
        'docs/implementation/R13_CORE_PATH_SPEC.md','path_improvements_experiment_r12.py',
        'core_split_experiment.py','data/core_split.py','data/vintages.py',
        'models/core_split.py','models/core_tuning.py','models/path_inputs.py',
        'path_experiment.py','forecast_independent.py','independent_nowcast_experiment.py',
        'independent_bridge_experiment.py','models/independent_nowcast.py','models/trend_gap.py',
        'models/horizon_models.py','data/local_adapter.py','data/struct_inputs.py','config.py','cz_struct.py',
        'output/independent_bridge_forecasts.csv','output/independent_bridge_manifest.json',
        'output/independent_nowcast_forecasts.csv','output/independent_path_forecasts.csv',
        'output/independent_path_frozen_inputs.csv','data/release_calendar_cz_cpi.csv',
        'data/admin_announcements_history.csv','data/cnb_mpr_cpi_quarterly.csv',
        'data/vintages/unemployment.csv.gz','data/vintages/manifest.json']
    files=[ROOT/name for name in names]
    files+=list((ROOT/'tests/fixtures/cleanup').glob('*'))
    files+=[p for p in (ROOT/'data/core_split').rglob('*') if p.is_file()]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(files)) if p.is_file()}


def verify_h0(changed,baseline,hard_base):
    """Bridge h0 exact; stored HARD_BASE may differ by pre-existing CSV ulps."""
    got=changed.loc[changed.h.eq(0),'mm_forecast'].iloc[0]
    original=baseline.loc[baseline.h.eq(0),'mm_forecast'].iloc[0]
    if got!=original or not np.isfinite(got) or abs(got-hard_base)>1e-12:
        raise AssertionError('Supplied HARD_BASE h0 changed')


def run(destination=OUT):
    from forecast_independent import fixture_frames
    from path_experiment import _eve
    from data.vintages import _validated
    hashes=dependency_hashes(); destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    frames=fixture_frames(); source=load_frozen(); categories=monthly_rates(source['levels'])
    core=frames['core'].iloc[:,0]
    headline=read(ROOT/'output/independent_path_frozen_inputs.csv').headline_mm.dropna()
    h0=pd.read_csv(ROOT/'output/independent_nowcast_forecasts.csv',float_precision='round_trip').set_index('period')
    baseline=pd.read_csv(ROOT/'output/independent_bridge_forecasts.csv',float_precision='round_trip')
    references=pd.read_csv(ROOT/'output/independent_path_forecasts.csv',float_precision='round_trip')
    expected=pd.period_range('2019-02','2026-07',freq='M')
    if not pd.PeriodIndex(h0.index,freq='M').equals(expected):
        raise ValueError('Exactly the saved 90 origins are required')
    validation=verify_baseline(frames,baseline,h0,headline)
    print('Original bridge source hashes and all-origin replay verified.',flush=True)
    dates=publication_dates(core.index)
    clocks=pd.Series({r:_eve(r) for r in core.index})
    for r,row in h0.iterrows():
        clocks.loc[pd.Period(r,'M')]=pd.Timestamp(row.as_of_eve)
    if not clocks.is_monotonic_increasing:
        raise AssertionError('Historical decision clocks must be increasing')
    labour=_validated(pd.read_csv(ROOT/'data/vintages/unemployment.csv.gz'))
    external_rows=[]; source_audit=[]
    for r in core.index[core.index<=expected[-1]]:
        values,audit=external_at(frames['features'],labour,r,clocks[r],clocks[r])
        external_rows.append(dict(period=r,**values.to_dict())); source_audit.append(audit)
    external=pd.DataFrame(external_rows).set_index('period')
    pd.DataFrame(source_audit).to_csv(destination/'external_source_audit.csv',index=False)
    external.to_csv(destination/'external_predictors.csv',index_label='period')
    rows=[]; fits=[]; contributions=[]; checks=[]
    for i,(name,row) in enumerate(h0.iterrows()):
        t=pd.Period(name,'M'); clock=pd.Timestamp(row.as_of_eve)
        weights=weights_at(source['weights'],t,clock)
        base=baseline[baseline.origin==name].copy()
        # h1 shares the current regime for release-eve origins in this experiment.
        observed=base.loc[base.h.eq(1),'weight_core'].iloc[0]
        if abs(observed-row.coreweight)>1e-10:
            raise AssertionError(f'Origin core weight disagrees with replayed bridge: {name}')
        result=forecast_origin(core,categories,weights,row.coreweight,dates,clocks,external,t,clock)
        for model,path in result['paths'].items():
            changed=replace_core(base,path); changed['model']=model
            changed['status']=np.where(np.isfinite(changed.mm_forecast),'estimated','unavailable_candidate_or_noncore')
            for col in ('origin_status','converged','fallback_used'):
                if col in changed:
                    changed=changed.drop(columns=[col])
            changed['fallback_used']=False
            invariant=[c for c in base if (c.startswith('contribution_') and c!='contribution_core') or c.startswith('weight_')]
            pd.testing.assert_frame_equal(base[invariant],changed[invariant],check_exact=True)
            verify_h0(changed,base,row.HARD_BASE)
            rows.extend(changed.to_dict('records'))
        fits.extend(dict(origin=name,**fit) for fit in result['fits'])
        contributions.extend(dict(origin=name,**value) for value in result['contributions'])
        checks.append(dict(origin=name,origin_coreweight=row.coreweight,basket_effective_year=weights.attrs['effective_year'],
            basket_available_from=weights.attrs['availability_assumption_date'],
            max_reconciliation_error=result['max_reconciliation_error']))
        if i%10==0 or i==len(h0)-1:
            print(f'Constructed {i+1}/90 core-path origins: {name}',flush=True)
    native=pd.DataFrame(rows)
    native.to_csv(destination/'native_forecasts.csv',index=False)
    dump(destination/'fit_diagnostics.json',fits)
    scalar_fits=pd.DataFrame([{k:v for k,v in f.items() if not isinstance(v,dict)} for f in fits])
    scalar_fits.to_csv(destination/'fit_audit.csv',index=False)
    pd.DataFrame(contributions).to_csv(destination/'core_target_contributions.csv',index=False)
    pd.DataFrame(checks).to_csv(destination/'origin_checks.csv',index=False)
    # Only after frozen candidate predictions are stored, join scoring outcomes.
    keep=['origin','h','target','as_of_utc','mm_forecast','model']
    rw=[]
    for name,row in h0.iterrows():
        t=pd.Period(name,'M'); path=benchmark_rw(headline,t)
        stamp=pd.Timestamp(row.as_of_eve).tz_localize('Europe/Prague').tz_convert('UTC').isoformat()
        rw.extend(dict(origin=name,h=h,target=str(t+h),as_of_utc=stamp,model='LAST_YOY_RW',mm_forecast=path[h]) for h in range(13))
    old=references.loc[references.origin.isin(h0.index)&references.model.isin(REFERENCE[1:-1]),keep]
    combined=pd.concat([native[keep],baseline[keep],old,pd.DataFrame(rw)],ignore_index=True)
    forecasts,target_delta=add_outcomes_and_compound(combined,headline,baseline)
    forecasts.to_csv(destination/'forecasts.csv',index=False)
    summary=all_scores(forecasts); summary.to_csv(destination/'summary.csv',index=False)
    paired_bootstrap(forecasts).to_csv(destination/'paired_uncertainty.csv',index=False)
    core_rows,core_scores=core_evaluation(native,core,baseline)
    core_rows.to_csv(destination/'core_outcomes.csv',index=False)
    core_scores.to_csv(destination/'core_summary.csv',index=False)
    coverage=[]
    for (model,h),g in forecasts.groupby(['model','h']):
        finite=g[np.isfinite(g.mm_forecast)]
        coverage.append(dict(model=model,h=h,n_intended_origins=len(g),n_finite_monthly=len(finite),
            first_finite_origin=finite.origin.min() if len(finite) else None,
            last_finite_origin=finite.origin.max() if len(finite) else None,
            n_finite_annual=int(np.isfinite(g.yy_exante).sum()),
            n_monthly_targets=int(np.isfinite(g.mm_actual).sum())))
    pd.DataFrame(coverage).to_csv(destination/'coverage.csv',index=False)
    validation.update(original_target_max_abs_difference=target_delta,
        all_origins_retained=forecasts.origin.nunique()==90,
        unique_keys=not forecasts.duplicated(['origin','h','model']).any(),
        noncore_columns_and_weights='exact at every candidate origin and horizon',
        max_target_reconciliation_error=max(r['max_reconciliation_error'] for r in checks),
        h1_max_differences={p:float(np.nanmax(np.abs(
            native.loc[native.model.eq(p+'_MONTHLY_R13')&native.h.eq(1),'value_core'].to_numpy()-
            native.loc[native.model.eq(p+'_CUMULATIVE_R13')&native.h.eq(1),'value_core'].to_numpy()))) for p in ('CORE_AGG','CORE_SPLIT')})
    dump(destination/'validation.json',validation)
    if dependency_hashes()!=hashes:
        raise AssertionError('Consumed source or model code changed during the run')
    outputs={p.name:sha(p) for p in sorted(destination.iterdir()) if p.suffix in ('.csv','.json') and p.name not in ('manifest.json','verification_receipt.json')}
    manifest=dict(completed_at=datetime.now(timezone.utc).isoformat(),prespec_commit=DECLARATION,
        command='python core_path_experiment_r13.py',inputs=hashes,outputs=outputs,
        primary=list(PRIMARY),labour_diagnostic=list(LABOUR),n_origins=90,
        packages={p:importlib.metadata.version(p) for p in ('numpy','pandas','scipy','scikit-learn','statsmodels')},
        target='Arithmetic cumulative monthly core rates; exact additive remainder, exact final headline compounding.',
        vintage='Latest stored CPI/import/FX histories with reconstructed release rules; archived unemployment selected at historical clocks.',
        historical_status='Repeatedly inspected pseudo-out-of-sample research, no fresh holdout; prospective evaluation required.')
    dump(destination/'manifest.json',manifest)
    print(summary.loc[summary.scope.eq('primary_common')&summary.h.isin([3,6,12]),
        ['sample','h','model','n_common','yy_rmse','yy_bias','mm_rmse']].to_string(index=False),flush=True)
    return manifest


def verify():
    frozen=json.loads((OUT/'manifest.json').read_text())
    if dependency_hashes()!=frozen['inputs']:
        raise AssertionError('Input/code hashes changed since saved run')
    for name,digest in frozen['outputs'].items():
        if sha(OUT/name)!=digest:
            raise AssertionError(f'Output hash mismatch: {name}')
    def forbidden(*args,**kwargs):
        raise AssertionError('Offline replay attempted network/database access')
    with tempfile.TemporaryDirectory(prefix='r13_core_') as folder, ExitStack() as stack:
        for target in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(target,side_effect=forbidden))
        replay=run(Path(folder))
        if replay['outputs']!=frozen['outputs']:
            mismatch=[name for name,value in frozen['outputs'].items() if replay['outputs'].get(name)!=value]
            raise AssertionError(f'Full-refit output mismatch: {mismatch}')
    receipt=dict(status='passed',verification='Full 90-origin refit and scoring; network/database blocked',
        byte_identical_payloads=len(frozen['outputs']),inputs_verified=len(frozen['inputs']),
        checked_at=datetime.now(timezone.utc).isoformat())
    dump(OUT/'verification_receipt.json',receipt); print(receipt,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    verify() if args.verify else run()
