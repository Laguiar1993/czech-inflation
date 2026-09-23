"""Independent R18 reconstruction: precision-update filter and augmented LS."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/research_r18_category';HERE=Path(__file__).parent
read=lambda file:pd.read_csv(file,float_precision='round_trip')
sha=lambda file:hashlib.sha256(file.read_bytes()).hexdigest()
manifest=json.loads((OUT/'manifest.json').read_text())
for name,digest in manifest['inputs'].items():assert sha(ROOT/name)==digest,name
for name,digest in manifest['outputs'].items():assert sha(OUT/name)==digest,name
states=json.loads((OUT/'states.json').read_text());updates=json.loads((OUT/'signal_updates.json').read_text())
levels=read(ROOT/'data/research_r18/categories/primary_monthly_levels.csv').set_index('target_month')
level_full=read(ROOT/'data/research_r18/categories/monthly_levels.csv').set_index('target_month')[levels.columns]
pd.testing.assert_frame_equal(levels,level_full)
availability=read(ROOT/'data/research_r18/categories/availability.csv').set_index('target_month')
metadata=read(ROOT/'data/research_r18/categories/series_metadata.csv').set_index('column')
cal=read(ROOT/'data/release_calendar_cz_cpi.csv').set_index('target_month')
core=read(ROOT/'tests/fixtures/cleanup/cnb_core_mm.csv').set_index('period').core
core=100*np.log1p(core/100);core.index=pd.PeriodIndex(core.index,freq='M')
clocks=json.loads((ROOT/'output/research_r15/states.json').read_text())
macro=read(ROOT/'output/research_r15/features_by_origin.csv').set_index('origin')
features=read(OUT/'features_by_origin.csv').set_index('origin')
macro_columns=['unemployment_change3','ip_growth3','ulc_growth12','fx3','cost_26_mean3','cost_45_mean3']
np.testing.assert_array_equal(features[macro_columns],macro.reindex(features.index)[macro_columns])
assert len(levels.columns)==18 and len(states)==90
assert metadata.reindex(levels.columns).sector.value_counts().to_dict()=={'goods':10,'services':6,'housing':2}
filter_origins=['2019-02','2020-04','2021-11','2022-12','2024-01','2026-07']
filter_checks=[]
for key in filter_origins:
    t=pd.Period(key,'M');clock=pd.Timestamp(clocks[key]['as_of'])
    # Gate endpoints independently on a full calendar, then difference.
    levels_origin=levels.copy();idx=pd.PeriodIndex(levels.index,freq='M')
    allowed=pd.to_datetime(availability.reindex(levels.index).available_from).le(clock).to_numpy()&(idx<t)
    levels_origin.loc[~allowed,:]=np.nan;rates=100*np.log(levels_origin/levels_origin.shift())
    rates.index=idx;history=core.rename('core').to_frame().join(rates,how='inner')
    published=pd.to_datetime(cal.reindex(history.index.astype(str)).detail_release_dt).to_numpy()+np.timedelta64(9,'h')
    history=history.loc[(history.index<t)&(published<=clock.to_datetime64())].dropna().tail(96)
    assert history.index.equals(pd.period_range(history.index.min(),t-1,freq='M'))
    season=np.stack([history.loc[history.index.month==m].to_numpy().mean(axis=0) for m in range(1,13)])
    y=history.to_numpy()-season[history.index.month-1]
    dy=np.diff(y,axis=0);r=np.maximum(.05,1.4826*np.median(np.abs(dy-np.median(dy,axis=0)),axis=0)/np.sqrt(2))**2
    n=y.shape[1];F=np.diag([1.,.3]+[.95]*n);H=np.zeros((n,n+2));H[:,:2]=1.;H[:,2:]=np.eye(n)
    for model,q in [('MCT_SLOW_R18',.0025),('MCT_FAST_R18',.01)]:
        mean=np.zeros(n+2);P=np.diag([1.,1.,*r]);Q=np.diag([q,.04,*list(.05*r)])
        for value in y:
            mu=F@mean;prior=F@P@F.T+Q;precision=np.linalg.inv(prior)
            # Information-form posterior, independently of Joseph/Kalman gain code.
            P=np.linalg.inv(precision+H.T@np.diag(1/r)@H)
            mean=P@(precision@mu+H.T@(value/r))
        expected=states[key][model]
        merror=float(np.max(abs(mean-np.array(expected['mean']))));perror=float(np.max(abs(P-np.array(expected['covariance']))))
        assert merror<1e-9 and perror<1e-9
        np.testing.assert_allclose(r,expected['observation_variance'],atol=1e-12,rtol=0)
        np.testing.assert_allclose(season,np.array([expected['seasonal'][str(m)] for m in range(1,13)]),atol=1e-12,rtol=0)
        for h in range(1,13):
            predicted=season[(t+h).month-1,0]+(H@np.linalg.matrix_power(F,h+1)@mean)[0]
            assert abs(predicted-expected['path'][str(h)])<1e-9
        residual_breadth=float(np.mean(np.mean(y[-3:,1:]>.05,axis=1)-np.mean(y[-3:,1:]<-.05,axis=1)))
        assert abs(expected['breadth3']-residual_breadth)<1e-12
        filter_checks.append(dict(origin=key,model=model,n_history=len(history),mean_max_abs=merror,covariance_max_abs=perror))
for key in features.index:
    parent=states[key]['MCT_FAST_R18'];sector=dict(zip(parent['columns'],parent['mean'][2:]))
    goods=np.mean([sector[col] for col in levels if metadata.loc[col,'sector']=='goods'])
    services=np.mean([sector[col] for col in levels if metadata.loc[col,'sector']=='services'])
    assert abs(features.loc[key,'goods_minus_services']-(goods-services))<1e-12
    assert features.loc[key,'breadth3']==parent['breadth3']
labels=read(OUT/'training_labels.csv');prediction=read(OUT/'state_predictions.csv')
for row in labels.itertuples():
    s=pd.Period(row.origin,'M');target=s+row.h
    assert str(target)==row.target
    assert abs(row.baseline_log-states[row.origin]['MCT_FAST_R18']['path'][str(row.h)])<1e-12
    actual=core.get(target,np.nan)
    assert (np.isnan(actual) and np.isnan(row.error)) or abs(row.error-(actual-row.baseline_log))<1e-12
    if row.target in cal.index and target in core.index:
        expected=pd.Timestamp(cal.loc[row.target,'detail_release_dt'])+pd.Timedelta(hours=9)
        assert pd.Timestamp(row.released)==expected
signal_checks=[];solve_origins=['2022-02','2022-12','2024-01','2025-06','2026-07']
for update in updates:
    key=update['origin'];t=pd.Period(key,'M');clock=pd.Timestamp(clocks[key]['as_of'])
    groups=[]
    for h in range(1,13):
        g=labels.loc[labels.h.eq(h)&labels.target.lt(key)&labels.origin.lt(key)&
            pd.to_datetime(labels.released).le(clock)&np.isfinite(labels.error)].sort_values('origin').tail(96)
        groups.append(g)
    if update['status']!='estimated':
        assert min(len(g) for g in groups)<24;continue
    assert update['n_by_h']==[len(g) for g in groups]
    assert update['training_origins']==[s for g in groups for s in g.origin]
    assert update['training_targets']==[s for g in groups for s in g.target]
    if key not in solve_origins:continue
    p=8;scale=np.sqrt(np.mean(np.concatenate([features.loc[g.origin].to_numpy() for g in groups])**2,axis=0));scale=np.where(scale<1e-8,1.,scale)
    blocks=[];target=[]
    for h,g in enumerate(groups):
        block=np.zeros((len(g),12*p));block[:,h*p:(h+1)*p]=features.loc[g.origin].to_numpy()/scale/np.sqrt(12*len(g))
        blocks.append(block);target.extend(g.error/np.sqrt(12*len(g)))
    blocks.append(np.eye(12*p)/np.sqrt(12));target.extend(np.zeros(12*p))
    diffs=np.zeros((11*p,12*p))
    for h in range(11):
        diffs[h*p:(h+1)*p,h*p:(h+1)*p]=-np.eye(p)/np.sqrt(11)
        diffs[h*p:(h+1)*p,(h+1)*p:(h+2)*p]=np.eye(p)/np.sqrt(11)
    blocks.append(diffs);target.extend(np.zeros(11*p))
    solution=np.linalg.lstsq(np.concatenate(blocks),np.asarray(target),rcond=None)[0].reshape(12,p)
    error=float(np.max(abs(solution-np.asarray(update['coefficients']))))
    correction=solution@(features.loc[key].to_numpy()/scale)
    delta=float(np.max(abs(correction-np.asarray(update['correction']))))
    assert error<1e-9 and delta<1e-9
    np.testing.assert_allclose(scale,update['rms'],atol=1e-12,rtol=0)
    signal_checks.append(dict(origin=key,coefficient_max_abs=error,correction_max_abs=delta,n_by_h=[len(g) for g in groups]))
native=read(OUT/'native_forecasts.csv');original=read(ROOT/'output/research_r15/native_forecasts.csv').query("model=='STATE_FAST_R15'")
maxsum=0.
for name,group in native.groupby('model'):
    joined=group.merge(original,on=['origin','h'],suffixes=('_new','_old'),validate='one_to_one')
    columns=[v for v in original if v.startswith('weight_') or v.startswith(('value_','contribution_')) and v not in ('value_core','contribution_core')]
    for col in columns:np.testing.assert_array_equal(joined[col+'_new'],joined[col+'_old'])
    np.testing.assert_array_equal(joined.loc[joined.h.eq(0),'mm_forecast_new'],joined.loc[joined.h.eq(0),'mm_forecast_old'])
    future=group[group.h.gt(0)];sumvalue=future[[v for v in original if v.startswith('contribution_')]].sum(axis=1,min_count=6)
    maxsum=max(maxsum,float(np.max(abs(future.mm_forecast-sumvalue))))
    assert maxsum<1e-12
status=read(OUT/'status.csv');count_discrepancies=[]
for row in status[status.model.isin(['MCT_FAST_R18','MCT_SLOW_R18'])].itertuples():
    actual_n=states[row.origin][row.model]['n_history']
    if row.n_history!=actual_n:count_discrepancies.append(dict(origin=row.origin,model=row.model,status_n=int(row.n_history),fit_n=actual_n))
result=dict(status='passed_with_audit_metadata_notes',inputs_verified=len(manifest['inputs']),outputs_verified=len(manifest['outputs']),
    independent_filters=filter_checks,independent_signal_solves=signal_checks,all54_signal_maturity_audited=True,
    all90_macro_and_state_predictors_match=True,all1080_generated_labels_verified=True,h0_noncore_exact=True,
    headline_component_sum_max_abs=maxsum,history_count_metadata_discrepancies=len(count_discrepancies),
    history_count_examples=count_discrepancies[:2]+count_discrepancies[-2:],
    interpretation='18 national category proxy measurements plus separate CNB core; no core partition or true-vintage claim')
(HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
