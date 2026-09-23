"""Rebuild saved monthly experiment equations and arithmetic independently."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
CATEGORIES=['actual_rent','imputed_rent','catering','accommodation','package_holidays']
GROUPS={'ar':[],'domestic':['unemployment_change3','ip_growth3','ulc_growth12'],
        'imported':['fx3','cost_26_mean3','cost_45_mean3']}
GROUPS['both']=GROUPS['domestic']+GROUPS['imported']


def read(path):return pd.read_csv(path,float_precision='round_trip')


def check(out,receipt):
    out=Path(out);manifest=json.loads((out/'manifest.json').read_text())
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    for n,h in manifest['inputs'].items():assert digest(ROOT/n)==h,n
    for n,h in manifest['outputs'].items():assert digest(out/n)==h,n
    stage2_declaration=json.loads((out/'stage2_declaration.json').read_text())
    for n,h in stage2_declaration['generated_inputs'].items():assert digest(out/n)==h
    snapshots=json.loads((out/'snapshots.json').read_text());states=json.loads((out/'core_states.json').read_text())
    signals=json.loads((out/'generated_signals.json').read_text());statuses=json.loads((out/'generated_status.json').read_text())
    f1=json.loads((out/'firststage_fits.json').read_text());c1=json.loads((out/'firststage_training_calendars.json').read_text())
    f2=json.loads((out/'secondstage_fits.json').read_text());c2=json.loads((out/'secondstage_training_calendars.json').read_text())
    levels=read(ROOT/'data/core_split/monthly_levels.csv').set_index('target_month');levels.index=pd.PeriodIndex(levels.index,freq='M')
    actual=100*np.log(levels/levels.shift());core=read(ROOT/'tests/fixtures/cleanup/cnb_core_mm.csv').set_index('period').core
    core.index=pd.PeriodIndex(core.index,freq='M');core_log=100*np.log1p(core/100)
    dates=read(ROOT/'data/release_calendar_cz_cpi.csv').set_index('target_month').detail_release_dt
    first=read(out/'firststage_predictions.csv');core_preds=read(out/'core_predictions.csv')
    first_lookup=first.set_index(['origin','family','h','component']);core_lookup=core_preds.set_index(['origin','family','h'])
    category_coef_error=0.;category_prediction_error=0.;core_coef_error=0.;core_prediction_error=0.;clock_checks=0;fitted1=0;fitted2=0
    for fit in f1:
        rows=c1[fit['training_calendar_id']];clock=pd.Timestamp(snapshots[fit['origin']]['as_of']);t=pd.Period(fit['origin'])
        assert len(rows)==fit['n_train_origins'] and len(rows)<=96
        if fit['status']!='estimated':continue
        fitted1+=1;x=[];y=[]
        for row in rows:
            s=snapshots[row['origin']];target=pd.Period(row['target']);assert target<t
            assert pd.Period(row['origin'])+fit['h']==target
            assert pd.Timestamp(s['as_of'])<clock
            for endpoint in (target-1,target):
                release=(pd.Timestamp(dates.loc[str(endpoint)]).normalize()+pd.Timedelta(hours=9)).tz_localize('Europe/Prague')
                assert release<=clock;clock_checks+=1
            for j in range(5):
                x.append([*s['own'][j],*[s['macro'][n] for n in GROUPS[fit['family']]]])
                y.append((actual.iloc[:,j].loc[target]-s['seasonal'][target.month-1][j])/s['scales'][j])
        x=np.array(x);y=np.array(y);rms=np.sqrt((x*x).mean(axis=0));rms[rms<=1e-12]=1.;z=x/rms
        beta=np.linalg.solve(z.T@z/len(y)+np.diag(fit['penalties']),z.T@y/len(y))
        category_coef_error=max(category_coef_error,float(np.max(np.abs(beta-fit['beta']))))
        s=snapshots[fit['origin']];target=pd.Period(fit['origin'])+fit['h']
        for j,c in enumerate(CATEGORIES):
            now=np.array([*s['own'][j],*[s['macro'][n] for n in GROUPS[fit['family']]]])
            forecast=s['seasonal'][target.month-1][j]+s['scales'][j]*((now/rms)@beta)
            category_prediction_error=max(category_prediction_error,abs(forecast-first_lookup.loc[(fit['origin'],fit['family'],fit['h'],c),'log_forecast']))
    pressure_error=0.
    for (origin,family,h),group in first.groupby(['origin','family','h']):
        g=group.set_index('component');w=np.array(snapshots[origin]['weights']);q=g.reindex(CATEGORIES).mm_forecast.to_numpy()
        pressure=w@q/w.sum();log_pressure=100*np.log1p(pressure/100)
        pressure_error=max(pressure_error,abs(log_pressure-signals[origin][family][h-1]),abs(pressure-g.loc['covered_pressure','mm_forecast']))
        assert abs(w@q-g.loc['covered_pressure','contribution_diagnostic'])<1e-12
    for fit in f2:
        rows=c2[fit['training_calendar_id']];clock=pd.Timestamp(states[fit['origin']]['as_of']);t=pd.Period(fit['origin'])
        assert len(rows)==fit['n_train'] and len(rows)<=96
        expected=sum(all(statuses[r['origin']][f][fit['h']-1]=='estimated' for f in GROUPS) for r in rows)
        assert fit['n_generated_estimated']==expected
        if fit['status']!='estimated':continue
        fitted2+=1;x=[];y=[]
        for row in rows:
            s=states[row['origin']];target=pd.Period(row['target']);assert target<t
            assert pd.Timestamp(s['as_of'])<clock
            release=(pd.Timestamp(dates.loc[str(target)]).normalize()+pd.Timedelta(hours=9)).tz_localize('Europe/Prague')
            assert release<=clock;clock_checks+=1
            g=signals[row['origin']];signal=[] if fit['family']=='own' else [g[fit['family']][fit['h']-1]-g['persistence'][fit['h']-1]]
            x.append([*s['own'],*signal]);y.append(core_log.loc[target]-s['fast_log'][fit['h']-1])
        x=np.array(x);y=np.array(y);rms=np.sqrt((x*x).mean(axis=0));rms[rms<=1e-12]=1;z=x/rms
        beta=np.linalg.solve(z.T@z/len(y)+np.diag(fit['penalties']),z.T@y/len(y));core_coef_error=max(core_coef_error,float(np.max(np.abs(beta-fit['beta']))))
        s=states[fit['origin']];g=signals[fit['origin']];signal=[] if fit['family']=='own' else [g[fit['family']][fit['h']-1]-g['persistence'][fit['h']-1]]
        now=np.array([*s['own'],*signal]);forecast=s['fast_log'][fit['h']-1]+(now/rms)@beta
        core_prediction_error=max(core_prediction_error,abs(forecast-core_lookup.loc[(fit['origin'],fit['family'],fit['h']),'core_log']))
    for error in (category_coef_error,category_prediction_error,core_coef_error,core_prediction_error,pressure_error):assert error<1e-10
    native=read(out/'native_forecasts.csv');base=read(ROOT/'output/research_r15/native_forecasts.csv');base=base.loc[base.model.eq('STATE_FAST_R15')&base.origin.isin(native.origin.unique())]
    fixed=[c for c in base if c.startswith('weight_') or (c.startswith('value_') and c!='value_core') or (c.startswith('contribution_') and c!='contribution_core')]
    hist=read(ROOT/'output/independent_path_frozen_inputs.csv').set_index('period').headline_mm;hist.index=pd.PeriodIndex(hist.index,freq='M')
    annual_error=0.;conditional_error=0.;cumulative_error=0.
    for model,group in native.groupby('model'):
        g=group.set_index(['origin','h']).sort_index();b=base.set_index(['origin','h']).sort_index()
        pd.testing.assert_frame_equal(g[fixed],b[fixed],check_exact=True)
        np.testing.assert_array_equal(g.xs(0,level='h').mm_forecast,b.xs(0,level='h').mm_forecast)
        for origin,path in g.groupby(level='origin'):
            p=path.droplevel('origin');t=pd.Period(origin);cumulative=0.
            for h,row in p.iterrows():
                if h:cumulative+=100*np.log1p(row.mm_forecast/100)
                cumulative_error=max(cumulative_error,abs(cumulative-row.cumulative_log_forecast))
                window=pd.period_range(t+h-11,t+h,freq='M')
                exante=[hist.get(m,np.nan) if m<t else p.loc[m.ordinal-t.ordinal,'mm_forecast'] for m in window]
                conditional=[hist.get(m,np.nan) if m<=t else p.loc[m.ordinal-t.ordinal,'mm_forecast'] for m in window]
                annual_error=max(annual_error,abs(100*(np.prod(1+np.array(exante)/100)-1)-row.yy_exante))
                conditional_error=max(conditional_error,abs(100*(np.prod(1+np.array(conditional)/100)-1)-row.yy_conditional))
    assert max(annual_error,conditional_error,cumulative_error)<1e-10
    rec=read(out/'statistical_reconciliation.csv')
    assert np.max(np.abs(rec.pressure_mm_forecast+rec.statistical_remainder_forecast-rec.core_mm_forecast))<1e-12
    result=dict(status='passed',source_hashes=len(manifest['inputs']),output_hashes=len(manifest['outputs']),
        firststage_rebuilt_fits=fitted1,secondstage_rebuilt_fits=fitted2,publication_checks=clock_checks,
        firststage_coefficient_max_error=category_coef_error,firststage_forecast_max_error=float(category_prediction_error),
        pressure_log_max_error=float(pressure_error),secondstage_coefficient_max_error=core_coef_error,secondstage_forecast_max_error=float(core_prediction_error),
        annual_product_max_error=float(annual_error),conditional_annual_max_error=float(conditional_error),cumulative_log_max_error=float(cumulative_error),
        h0_noncore_weights_exact=True,stage2_generated_file_hashes_verified=True,statistical_reconciliation_exact=True,
        outer_origins=int(native.origin.nunique()),snapshot_count=len(snapshots))
    Path(receipt).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default=ROOT/'output/research_r17_monthly',type=Path)
    p.add_argument('--receipt',default=ROOT/'work/research_r17_monthly/independent_verification.json',type=Path)
    a=p.parse_args();check(a.output,a.receipt)
