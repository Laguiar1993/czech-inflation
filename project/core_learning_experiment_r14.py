"""R14 frozen core band-learning experiment. --verify refits fully offline."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from core_split_experiment import publication_dates
from models.core_learning_r14 import (BANDS,CONFIGS,DEFAULT,MODELS,origin_state,band_design,
    labels_at,ridge,select_config,monthly_path,config_values)
from models.core_path_r13 import replace_core
from path_improvements_experiment_r12 import (read,sha,dump,verify_baseline,score_panel,
    add_outcomes_and_compound,benchmark_rw)

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/research_r14/core'
DECLARATION='06c2907'
REFS=('INDEPENDENT_BRIDGE','RF_U_FX','BVAR_U_FX','NAIVE','LAST_YOY_RW')
PAIRS=[(m,'INDEPENDENT_BRIDGE') for m in MODELS]+[
    ('CORE_GAP_RIDGE_R14','CORE_LEVEL_RIDGE_R14'),('CORE_GAP_RF_R14','CORE_LEVEL_RF_R14'),
    ('CORE_GAP_ADAPT_R14','CORE_GAP_RIDGE_R14')]


def reference_rows(frame,origins,columns):
    return frame.loc[frame.origin.isin(origins)&frame.model.isin(REFS[1:-1]),columns]


def native_metadata(frame,missing_reason='unavailable_core_or_noncore'):
    """Candidate availability is separate from inherited source-model metadata."""
    result=frame.copy()
    legacy=('origin_status','converged','fallback_used','unemployment_end',
            'unemployment_adjustments','adjustments','fx_end','headline_n')
    result=result.rename(columns={c:'legacy_source_'+c for c in legacy if c in result})
    finite=np.isfinite(result.mm_forecast)
    result['status']=np.where(finite,'estimated',missing_reason)
    result['origin_status']='estimated' if finite.all() else 'failed_nonfinite'
    # This legacy-schema field means a finite numerical forecast, not optimisation.
    result['converged']=finite
    result['core_fallback_used']=False
    result['fallback_used']=result.get('legacy_source_fallback_used',False)
    return result


def load_feature_extension(feature_extension):
    """Validate the frozen extension and every declared source/preparer payload."""
    folder=Path(feature_extension)
    folder=(folder if folder.is_absolute() else ROOT/folder).resolve()
    folder.relative_to(ROOT.resolve())
    metadata=folder/'manifest.json';meta=json.loads(metadata.read_text(encoding='utf-8'))
    if not meta.get('inputs') or 'core_feature_extension.csv' not in meta.get('outputs',{}):
        raise ValueError('Extension manifest requires source inputs and extension output hashes')
    hashes={metadata.relative_to(ROOT.resolve()).as_posix():sha(metadata)}
    for base,items in [(ROOT,meta['inputs']),(folder,meta['outputs'])]:
        for relative,expected in items.items():
            path=(base/relative).resolve()
            path.relative_to(base.resolve())
            if not path.is_file() or sha(path)!=expected:
                raise ValueError(f'Extension source/output hash mismatch: {relative}')
            hashes[path.relative_to(ROOT.resolve()).as_posix()]=expected
    data=pd.read_csv(folder/'core_feature_extension.csv',float_precision='round_trip')
    if set(data.columns)!={'period','import_l2','available_from'}:
        raise ValueError('Extension columns must be period, import_l2, available_from')
    if not data.period.astype(str).str.fullmatch(r'\d{4}-\d{2}').all():
        raise ValueError('Extension periods must be explicit monthly fixture keys')
    data.index=pd.PeriodIndex(data.pop('period'),freq='M')
    if not len(data) or not data.index.is_unique or not data.index.is_monotonic_increasing:
        raise ValueError('Extension periods must be nonempty, unique and ordered')
    if not np.isfinite(data.import_l2).all() or (data.import_l2<=-100).any():
        raise ValueError('Extension import rates must be finite and greater than -100')
    dates=[]
    for period,value in data.available_from.items():
        date=pd.Timestamp(value)
        if pd.isna(date) or date.tzinfo is None:
            raise ValueError('Extension publication dates must be timezone-aware')
        expected=(period+1).to_timestamp().tz_localize('Europe/Prague')
        if date!=expected:
            raise ValueError('Extension publication must equal next fixture month start in Prague')
        dates.append(date.tz_convert('UTC'))
    data['available_from']=pd.DatetimeIndex(dates)
    return data,hashes,folder.relative_to(ROOT.resolve()).as_posix()


def apply_feature_extension(features,feature_extension=None):
    """Fill only missing pre-first-valid imports; never alter baseline frames."""
    result=features.copy()
    if feature_extension is None:return result,None,dict(policy='frozen')
    extension,_,relative=load_feature_extension(feature_extension)
    if not extension.index.isin(features.index).all():
        raise ValueError('Extension must use existing frozen fixture months')
    if features.import_l2.reindex(extension.index).notna().any():
        raise ValueError('Extension cannot overwrite finite frozen import cells')
    first=features.import_l2.first_valid_index()
    if first is None or (extension.index>=first).any():
        raise ValueError('Only missing historical imports before the first finite value may be filled')
    result.loc[extension.index,'import_l2']=extension.import_l2
    audit=dict(policy='historical_import_extension',directory=relative,filled_cells=len(extension),
               first_fixture=str(extension.index.min()),last_fixture=str(extension.index.max()),
               publication_rule='source+3 month start, equivalent to fixture+1 month start Prague midnight',
               source_vintage='latest official levels; conservative reconstructed historical availability')
    return result,extension.available_from,audit


def dependencies(feature_extension=None):
    names=['core_learning_experiment_r14.py','models/core_learning_r14.py','test_core_learning_r14.py',
      'docs/implementation/R14_CORE_DESIGN.md','docs/implementation/R14_EXPERIMENT_PLAN_2026-09-09.md',
      'core_split_experiment.py','models/core_path_r13.py','path_improvements_experiment_r12.py',
      'forecast_independent.py','independent_nowcast_experiment.py','models/independent_nowcast.py','independent_bridge_experiment.py',
      'path_experiment.py','models/path_inputs.py','cz_struct.py','config.py','data/struct_inputs.py',
      'data/local_adapter.py','data/release_calendar_cz_cpi.csv','data/admin_announcements_history.csv',
      'output/independent_nowcast_forecasts.csv','output/independent_bridge_forecasts.csv',
      'output/independent_bridge_manifest.json','output/independent_path_forecasts.csv',
      'output/independent_path_frozen_inputs.csv','test_core_history_extension_r14.py']
    files=[ROOT/n for n in names]+list((ROOT/'tests/fixtures/cleanup').glob('*'))
    hashes={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(files)) if p.is_file()}
    if feature_extension is not None:
        hashes.update(load_feature_extension(feature_extension)[1])
        spec='docs/implementation/R14B_CORE_HISTORY_DESIGN.md'
        hashes[spec]=sha(ROOT/spec)
    return hashes


def scores(frame):
    tables=[score_panel(frame,[*MODELS,*REFS],'primary_common')]
    for m in (*MODELS,*REFS):tables.append(score_panel(frame,[m],'own_coverage'))
    for m,c in PAIRS:tables.append(score_panel(frame,[c,m],f'paired_{m}_vs_{c}'))
    return pd.concat(tables,ignore_index=True)


def uncertainty(frame):
    rng=np.random.default_rng(1409);rows=[]
    for sample,mask in [('full',np.ones(len(frame),bool)),('recent_targets',frame.target>='2024-01'),('recent_origins',frame.origin>='2024-01')]:
        for h in range(1,13):
            data=frame.loc[mask&frame.h.eq(h)].copy()
            data['error']=data.yy_exante-data.yy_actual
            wide=data.pivot(index='origin',columns='model',values='error')
            for m,c in PAIRS:
                pair=wide[[m,c]].dropna();n=len(pair)
                if not n:continue
                diff=(pair[m]**2-pair[c]**2).to_numpy()
                starts=rng.integers(0,n,size=(2000,int(np.ceil(n/12))))
                ind=((starts[:,:,None]+np.arange(12))%n).reshape(2000,-1)[:,:n]
                low,high=np.quantile(diff[ind].mean(axis=1),[.025,.975])
                rows.append(dict(sample=sample,h=h,model=m,control=c,n=n,mse_difference=float(diff.mean()),
                                  ci_low=float(low),ci_high=float(high),block_length=12,replicates=2000,seed=1409))
    return pd.DataFrame(rows)


def core_scores(native,baseline,core):
    rows=[]
    cols=['origin','h','target','model','value_core']
    for (origin,model),g in pd.concat([native[cols],baseline[cols]],ignore_index=True).groupby(['origin','model'],sort=False):
        t=pd.Period(origin,'M');p=g.set_index('h').value_core
        for h in range(1,13):
            pred=p.reindex(range(1,h+1)).to_numpy(dtype=float)
            actual=core.reindex(pd.period_range(t+1,t+h,freq='M')).to_numpy(dtype=float)
            rows.append(dict(origin=origin,target=str(t+h),h=h,model=model,mm_forecast=p.get(h,np.nan),
              mm_actual=core.get(t+h,np.nan),cumulative_log_forecast=float(100*np.log1p(pred/100).sum()) if np.isfinite(pred).all() and (pred>-100).all() else np.nan,
              cumulative_log_actual=float(100*np.log1p(actual/100).sum()) if np.isfinite(actual).all() and (actual>-100).all() else np.nan))
    detail=pd.DataFrame(rows);summary=[]
    for scope,models in [('core_common',list(MODELS)+['INDEPENDENT_BRIDGE'])]+[(f'paired_{m}',[m,'INDEPENDENT_BRIDGE']) for m in MODELS]:
        for sample,mask in [('full',np.ones(len(detail),bool)),('recent_targets',detail.target>='2024-01'),('recent_origins',detail.origin>='2024-01')]:
            for h in range(1,13):
                d=detail.loc[mask&detail.h.eq(h)&detail.model.isin(models)]
                wide=d.pivot(index='origin',columns='model',values='cumulative_log_forecast').reindex(columns=models)
                truth=d.drop_duplicates('origin').set_index('origin').cumulative_log_actual
                good=wide.index[np.isfinite(wide).all(axis=1)&np.isfinite(truth.reindex(wide.index))]
                for m in models:
                    own=d[d.model==m].set_index('origin').reindex(good);row=dict(scope=scope,sample=sample,h=h,model=m,n=len(good))
                    for metric in ('mm','cumulative_log'):
                        err=own[metric+'_forecast']-own[metric+'_actual']
                        row.update({metric+'_rmse':float(np.sqrt((err**2).mean())),metric+'_mae':float(err.abs().mean()),metric+'_bias':float(err.mean())})
                    summary.append(row)
    return detail,pd.DataFrame(summary)


def run(destination=OUT,feature_extension=None,declaration=DECLARATION):
    from forecast_independent import fixture_frames
    from path_experiment import _eve
    if feature_extension is not None and declaration==DECLARATION:
        raise ValueError('Historical extension requires its separate committed declaration')
    hashes=dependencies(feature_extension);destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    frames=fixture_frames();core=frames['core'].iloc[:,0];features=frames['features'];available=publication_dates(core.index)
    h0=pd.read_csv(ROOT/'output/independent_nowcast_forecasts.csv',float_precision='round_trip').set_index('period')
    baseline=pd.read_csv(ROOT/'output/independent_bridge_forecasts.csv',float_precision='round_trip')
    headline=read(ROOT/'output/independent_path_frozen_inputs.csv').headline_mm.dropna()
    validation=verify_baseline(frames,baseline,h0,headline)
    features,import_available,feature_policy=apply_feature_extension(features,feature_extension)
    print('Original bridge replay verified; constructing historical core states.',flush=True)
    clocks=pd.Series({r:_eve(r) for r in core.index})
    for ts,row in h0.iterrows():clocks.loc[pd.Period(ts,'M')]=pd.Timestamp(row.as_of_eve)
    last=pd.Period(h0.index[-1],'M');states={}
    for r in core.index[core.index<=last]:
        if pd.isna(clocks[r]):continue
        value=origin_state(core,features,available,r,clocks[r],import_available_from=import_available)
        if value is not None:states[r]=value
    dump(destination/'historical_states.json',{str(k):v for k,v in states.items()})
    designs={b:band_design(states,band) for b,band in enumerate(BANDS)}
    trends=pd.Series({r:s['trend'] for r,s in states.items()})
    rows=[];candidate_rows=[];fits=[];selections=[];band_forecasts=[]
    for i,(t,state) in enumerate(sorted(states.items())):
        ts=str(t);clock=clocks[t];is_outer=ts in h0.index
        predictions={m:{} for m in MODELS}
        for b,band in enumerate(BANDS):
            level,lab=labels_at(core,available,states,t,clock,band)
            x=designs[b];train=level.index.intersection(x.index);level=level.reindex(train)
            gap=level-trends.reindex(train);now=x.loc[t]
            current={};diagnostics={}
            for config in CONFIGS:
                alpha,window=config_values(config)
                chosen=train if window is None else train[train>=t-window]
                value,info=ridge(x.loc[chosen],gap.loc[chosen],now,alpha)
                current[config]=value;diagnostics[config]=info
                candidate_rows.append(dict(origin=ts,as_of=str(clock),band=b,config=config,prediction=value,
                  n_train=len(chosen),train_start=str(chosen.min()) if len(chosen) else None,
                  train_end=str(chosen.max()) if len(chosen) else None,
                  last_training_target=str(chosen.max()+band[1]) if len(chosen) else None,
                  last_training_release=str(lab.loc[lab.origin.isin(chosen.astype(str)),'available_from'].max()) if len(chosen) else None,
                  status=info['status']))
            if not is_outer:continue
            schedule=select_config(pd.DataFrame(candidate_rows),lab,t,clock,b)
            selections.append(dict(origin=ts,as_of=str(clock),band=b,**schedule))
            level_ridge,lev_info=ridge(x.loc[train],level,now,30.)
            predictions['CORE_LOCAL_R14'][b]=state['trend']
            predictions['CORE_LEVEL_RIDGE_R14'][b]=level_ridge
            predictions['CORE_GAP_RIDGE_R14'][b]=current[DEFAULT]+state['trend']
            predictions['CORE_GAP_ADAPT_R14'][b]=current[schedule['config']]+state['trend']
            for m,yy in [('CORE_LEVEL_RF_R14',level),('CORE_GAP_RF_R14',gap)]:
                value=np.nan
                if len(train)>=48:
                    forest=RandomForestRegressor(n_estimators=200,min_samples_leaf=5,max_features=1/3,random_state=42,n_jobs=1,bootstrap=True)
                    forest.fit(x.loc[train].to_numpy(),yy.to_numpy())
                    value=float(forest.predict(now.to_numpy().reshape(1,-1))[0])
                predictions[m][b]=value+(state['trend'] if 'GAP' in m else 0.)
            for key,info in [('level_fixed',lev_info),*diagnostics.items()]:
                fits.append(dict(origin=ts,as_of=str(clock),band=b,configuration=key,**info))
            for m in MODELS:
                band_forecasts.append(dict(origin=ts,as_of=str(clock),band=b,model=m,level_prediction=predictions[m][b],
                   current_trend=state['trend'],n_train=len(train),last_training_origin=str(train.max()) if len(train) else None,
                   last_training_target=str(train.max()+band[1]) if len(train) else None,
                   training_last_release=str(lab.available_from.max()) if len(lab) else None))
        if is_outer:
            base=baseline.loc[baseline.origin==ts].copy()
            for m,means in predictions.items():
                path=monthly_path(t,state['seasonal'],means)
                changed=replace_core(base,path);changed['model']=m
                changed=native_metadata(changed)
                # Native table is component output; all annual forecasts are rebuilt below.
                changed['yy_exante']=np.nan;changed['yy_conditional']=np.nan
                invariant=[c for c in base if (c.startswith('contribution_') and c!='contribution_core') or c.startswith('weight_')]
                pd.testing.assert_frame_equal(base[invariant],changed[invariant],check_exact=True)
                if base.loc[base.h.eq(0),'mm_forecast'].iloc[0]!=changed.loc[changed.h.eq(0),'mm_forecast'].iloc[0]:
                    raise AssertionError('HARD_BASE h0 changed')
                rows.extend(changed.to_dict('records'))
            if (h0.index.get_loc(ts)%10)==0 or ts==h0.index[-1]:
                print(f'Core paths: {h0.index.get_loc(ts)+1}/90 origins, {ts}',flush=True)
    # Missing states are retained explicitly rather than disappearing from the roster.
    for ts in h0.index:
        if pd.Period(ts,'M') in states:continue
        base=baseline.loc[baseline.origin==ts].copy()
        for m in MODELS:
            changed=replace_core(base,dict.fromkeys(range(1,13),np.nan));changed['model']=m
            changed=native_metadata(changed,'unavailable_current_state')
            changed['yy_exante']=np.nan;changed['yy_conditional']=np.nan
            rows.extend(changed.to_dict('records'))
    native=pd.DataFrame(rows).sort_values(['origin','model','h']).reset_index(drop=True)
    native.to_csv(destination/'native_forecasts.csv',index=False)
    pd.DataFrame(candidate_rows).to_csv(destination/'sequential_candidates.csv',index=False)
    pd.DataFrame(band_forecasts).to_csv(destination/'band_forecasts.csv',index=False)
    dump(destination/'fit_diagnostics.json',fits);dump(destination/'selections.json',selections)
    pd.DataFrame([{k:v for k,v in s.items() if not isinstance(v,(dict,list))} for s in selections]).to_csv(destination/'selection_summary.csv',index=False)
    references=pd.read_csv(ROOT/'output/independent_path_forecasts.csv',float_precision='round_trip')
    keep=['origin','h','target','as_of_utc','mm_forecast','model']
    rw=[]
    for ts,row in h0.iterrows():
        t=pd.Period(ts,'M');p=benchmark_rw(headline,t);stamp=baseline.loc[baseline.origin.eq(ts),'as_of_utc'].iloc[0]
        rw.extend(dict(origin=ts,h=h,target=str(t+h),as_of_utc=stamp,mm_forecast=p[h],model='LAST_YOY_RW') for h in range(13))
    combined=pd.concat([native[keep],baseline[keep],reference_rows(references,h0.index,keep),pd.DataFrame(rw)],ignore_index=True)
    forecasts,delta=add_outcomes_and_compound(combined,headline,baseline)
    forecasts.to_csv(destination/'forecasts.csv',index=False)
    summary=scores(forecasts);summary.to_csv(destination/'summary.csv',index=False)
    uncertainty(forecasts).to_csv(destination/'paired_uncertainty.csv',index=False)
    detail,cs=core_scores(native,baseline,core)
    detail.to_csv(destination/'core_outcomes.csv',index=False);cs.to_csv(destination/'core_summary.csv',index=False)
    validation.update(original_target_max_abs_difference=delta,n_origins=native.origin.nunique(),
      n_native_rows=len(native),h0_and_noncore='exact',native_annual_columns='intentionally unavailable; authoritative annual forecasts in forecasts.csv',
      native_status_policy='Candidate finite availability; converged does not denote optimiser convergence. Legacy driver metadata is prefixed legacy_source_; fallback_used retains noncore source evidence and core_fallback_used is false.',
      empirical_models=MODELS,source_vintage='latest stored CPI/import/FX, explicit publication rules; not true revision vintages')
    dump(destination/'validation.json',validation)
    if hashes!=dependencies(feature_extension):raise AssertionError('Consumed code/input changed during fitting')
    outputs={p.name:sha(p) for p in sorted(destination.iterdir()) if p.suffix in ('.csv','.json') and p.name not in ('manifest.json','verification_receipt.json')}
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(),declaration=declaration,feature_policy=feature_policy,inputs=hashes,outputs=outputs,
                  packages={p:importlib.metadata.version(p) for p in ('numpy','pandas','scipy','scikit-learn')})
    dump(destination/'manifest.json',manifest)
    print(summary.loc[summary.scope.eq('primary_common')&summary.h.isin([6,12]),['sample','h','model','n_common','yy_rmse','yy_bias']].to_string(index=False),flush=True)
    return manifest


def verify(destination=OUT,feature_extension=None,declaration=None):
    destination=Path(destination)
    frozen=json.loads((destination/'manifest.json').read_text())
    policy=frozen.get('feature_policy',dict(policy='frozen'))
    declared_extension=policy.get('directory')
    if feature_extension is None:feature_extension=declared_extension
    elif declared_extension is None or (ROOT/declared_extension).resolve()!=(ROOT/feature_extension).resolve():
        raise AssertionError('Requested extension differs from saved feature policy')
    if declaration is not None and declaration!=frozen['declaration']:
        raise AssertionError('Requested declaration differs from saved run')
    if dependencies(feature_extension)!=frozen['inputs']:raise AssertionError('Consumed input/code changed')
    for name,digest in frozen['outputs'].items():
        if sha(destination/name)!=digest:raise AssertionError(f'Changed output:{name}')
    with tempfile.TemporaryDirectory(prefix='r14_core_') as tmp,ExitStack() as stack:
        for target in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(target,side_effect=AssertionError('Offline replay attempted external access')))
        replay=run(Path(tmp),feature_extension=feature_extension,declaration=frozen['declaration'])
        if replay['outputs']!=frozen['outputs']:raise AssertionError('Offline full-refit payload mismatch')
    receipt=dict(status='passed',byte_identical_payloads=len(frozen['outputs']),verified_inputs=len(frozen['inputs']),checked_at=datetime.now(timezone.utc).isoformat())
    dump(destination/'verification_receipt.json',receipt);print(receipt,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify',action='store_true');parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--feature-extension',type=Path);parser.add_argument('--declaration')
    args=parser.parse_args()
    if args.verify:verify(args.output_dir,feature_extension=args.feature_extension,declaration=args.declaration)
    else:run(args.output_dir,feature_extension=args.feature_extension,declaration=args.declaration or DECLARATION)
