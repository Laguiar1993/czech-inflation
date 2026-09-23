"""Independent saved FMIE join, annual-target, score and source-clock audit."""
from pathlib import Path
import hashlib,json,math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/research_r14/survey'
BASE='INDEPENDENT_BRIDGE'
PRIMARY=[BASE,'PIPELINE_FOOD_FUEL_R14','PIPELINE_GAP_RIDGE_R14','PIPELINE_GAP_RF_R14']
COUNTS={};MAX={}
def read(name):return pd.read_csv(ROOT/name,float_precision='round_trip')
def same(a,b,label,tol=1e-10):
    aa=np.asarray(a,dtype=float);bb=np.asarray(b,dtype=float)
    assert aa.shape==bb.shape and np.array_equal(np.isfinite(aa),np.isfinite(bb)),label
    ok=np.isfinite(aa);delta=float(np.max(abs(aa[ok]-bb[ok]))) if ok.any() else 0.
    assert delta<=tol,(label,delta)
    COUNTS[label]=COUNTS.get(label,0)+aa.size;MAX[label]=max(MAX.get(label,0),delta)
def local(clock):
    p=pd.Timestamp(clock)
    assert pd.notna(p)
    return p.tz_convert('Europe/Prague').tz_localize(None) if p.tzinfo else p
def product(values):
    q=np.asarray(values,dtype=float)
    return 100*(math.prod(1+q/100)-1) if np.isfinite(q).all() and (q>-100).all() else np.nan
def main():
    manifest=json.loads((OUT/'manifest.json').read_text())
    for directory,hashes in [(ROOT,manifest['inputs']),(OUT,manifest['outputs'])]:
        for name,digest in hashes.items():assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest,name
    COUNTS['hashes']=len(manifest['inputs'])+len(manifest['outputs'])
    panel=read('data/research_r14/benchmarks/fmie_official_panel.csv').set_index('survey_month')
    assert list(panel.index)==list(map(str,pd.period_range('2023-08','2025-07',freq='M')))
    prediction=read('output/research_r14/survey/predictions.csv')
    monthly=read('output/research_r14/survey/monthly_paths.csv')
    comparison=read('output/research_r14/survey/comparisons.csv')
    summary=read('output/research_r14/survey/summary.csv')
    assert not prediction.duplicated(['survey_month','model']).any()
    assert not monthly.duplicated(['survey_month','model','h']).any()
    raw=read('output/independent_path_frozen_inputs.csv');headline=pd.Series(raw.headline_mm.to_numpy(),index=pd.PeriodIndex(raw.iloc[:,0],freq='M'))
    for row in prediction.itertuples():
        source=panel.loc[row.survey_month];t=pd.Period(row.survey_month,'M')
        assert row.target_month==str(t+12) and row.model_origin==str(t) and row.model_h==12
        assert pd.Timestamp(row.as_of)==pd.Timestamp(source.available_from_document_day_after)
        clock=(pd.Timestamp(source.document_issue_date)+pd.Timedelta(days=1)).tz_localize('Europe/Prague')
        assert pd.Timestamp(row.as_of)==clock
        legs=monthly[monthly.survey_month.eq(row.survey_month)&monthly.model.eq(row.model)].sort_values('h')
        assert legs.h.tolist()==list(range(1,13))
        assert legs.target.tolist()==list(map(str,pd.period_range(t+1,t+12,freq='M')))
        cols=['contribution_'+k for k in ('core','food','administered','alcohol_tobacco','fuel','wedge')]
        # Match scalar arithmetic: Python 3.14 sum(float) uses compensated sums,
        # whereas a sequence of NumPy scalars dispatches scalar array addition.
        summed=[sum(map(float,x)) if np.isfinite(x).all() else np.nan for x in legs[cols].to_numpy()]
        same(legs.mm_forecast,summed,'monthly_component_sum',0.)
        same([row.forecast],[product(legs.mm_forecast)],'annual_product')
        result=comparison[comparison.survey_month.eq(row.survey_month)&comparison.model.eq(row.model)].iloc[0]
        truth=product(headline.reindex(pd.period_range(t+1,t+12,freq='M')))
        same([result.actual,result.survey_mean_yoy_pct,result.error,result.survey_error],
             [truth,source.survey_mean_yoy_pct,row.forecast-truth,source.survey_mean_yoy_pct-truth],'join_targets_errors')
        assert result.pdf_sha256==source.pdf_sha256 and result.source_url==source.source_url
        assert hashlib.sha256((ROOT/source.source_document).read_bytes()).hexdigest()==source.pdf_sha256
    # Every unchanged component remains exactly the custom-clock bridge component.
    unchanged=['administered','alcohol_tobacco','wedge']
    baseline=monthly[monthly.model.eq(BASE)].set_index(['survey_month','h']).sort_index()
    for name,group in monthly.groupby('model'):
        group=group.set_index(['survey_month','h']).sort_index()
        for k in unchanged:same(group['contribution_'+k],baseline['contribution_'+k],'unchanged_'+k,0.)
        if name in ('PIPELINE_FOOD_FUEL_R14','STABLE_PIPELINE_R14B'):
            same(group.contribution_core,baseline.contribution_core,'unchanged_base_core',0.)
    for row in summary.itertuples():
        names=PRIMARY if row.scope=='primary_common' else list(dict.fromkeys([BASE,row.scope.removeprefix('paired_')]))
        selected=comparison[comparison.model.isin(names)]
        wide=selected.pivot(index='survey_month',columns='model',values='forecast').reindex(columns=names)
        truth=selected.drop_duplicates('survey_month').set_index('survey_month')
        ok=wide.index[np.isfinite(wide).all(axis=1)&np.isfinite(truth.actual.reindex(wide.index))&np.isfinite(truth.survey_mean_yoy_pct.reindex(wide.index))]
        own=truth.survey_mean_yoy_pct if row.model=='FMIE' else wide[row.model]
        pred=own.reindex(ok);error=pred-truth.actual.reindex(ok)
        nown=int((np.isfinite(own)&np.isfinite(truth.actual.reindex(own.index))&np.isfinite(truth.survey_mean_yoy_pct.reindex(own.index))).sum())
        same([row.n_intended,row.n,row.n_own_scored,row.n_available_targets,row.rmse,row.mae,row.bias],
             [24,len(ok),nown,np.isfinite(truth.actual).sum(),math.sqrt(float((error**2).mean())),float(error.abs().mean()),float(error.mean())],'paired_metrics')
    invariant=read('output/research_r14/survey/h0_invariance.csv')
    assert len(invariant)==24
    same(invariant.max_future_h0_difference,np.zeros(24),'h0_future_invariance',0.)
    same(invariant.annual_h0_difference,np.zeros(24),'h0_annual_invariance',0.)
    audits=json.loads((OUT/'fit_audit.json').read_text())
    for record in audits:
        t=pd.Period(record['survey_month'],'M');clock=local(record['as_of'])
        for family in ('core','extended_core'):
            for fit in record.get(family,[]):
                state=fit['current_state'];assert local(state['as_of'])==clock
                assert state['history_end']==str(t-1) and local(state['last_core_release'])<=clock
                assert set(state['x'])=={'core1','core3','core12','core_acceleration','import3','import12','fx3','fx12'}
                for source in state['sources'].values():assert local(source['last_available_from'])<=clock
                if fit['training_last_release'] is not None:assert local(fit['training_last_release'])<=clock
                hi=[3,6,9,12][fit['band']]
                if fit['last_training_origin'] is not None:assert pd.Period(fit['last_training_origin'],'M')+hi<t
                COUNTS['core_clock_bands']=COUNTS.get('core_clock_bands',0)+1
        food=record['food']
        for variable,month in food['last_released_month'].items():
            assert pd.Period(month,'M')<t and local(food['last_release_timestamp'][variable])<=clock
        if 'stable_food' in record:
            for variable,month in record['stable_food']['last_released_rate'].items():
                assert pd.Period(month,'M')<t
                assert all(local(v)<=clock for v in record['stable_food']['last_rate_endpoint_releases'][variable].values())
            for fit in record['stable_food_fits']:
                assert fit['spectral_radius']<=.98+1e-10 and all(pd.Period(d,'M')<t for d in fit['training_dates'])
        for source in ('pump','oil','fx'):assert local(record['fuel'][source+'_available_end'])<=clock
        COUNTS['component_clock_origins']=COUNTS.get('component_clock_origins',0)+1
    for directory,hashes in [(ROOT,manifest['inputs']),(OUT,manifest['outputs'])]:
        for name,digest in hashes.items():assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest,name
    report=dict(status='passed',counts=COUNTS,max_abs_differences=MAX,models=sorted(comparison.model.unique()),
        rows=len(comparison),summary_rows=len(summary),interpretation='All24document-date clocks retained; no survey values enterforecast construction. FMIE respondent cutoff and actualwebpublicationtime remainunknown.')
    (Path(__file__).parent/'survey_results_receipt.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
