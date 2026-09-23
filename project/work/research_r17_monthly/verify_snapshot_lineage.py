"""Verify every saved category snapshot directly against dated original inputs."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/research_r17_monthly'
saved=json.loads((OUT/'snapshots.json').read_text())
core_saved=json.loads((OUT/'core_states.json').read_text())
r15=json.loads((ROOT/'output/research_r15/states.json').read_text())
levels=pd.read_csv(ROOT/'data/core_split/monthly_levels.csv',index_col=0,float_precision='round_trip')
levels.index=pd.PeriodIndex(levels.index,freq='M')
available=pd.read_csv(ROOT/'data/release_calendar_cz_cpi.csv').set_index('target_month').detail_release_dt
available=pd.to_datetime(available).dt.normalize()+pd.Timedelta(hours=9)
available=available.dt.tz_localize('Europe/Prague');available.index=pd.PeriodIndex(available.index,freq='M')
weights=pd.read_csv(ROOT/'data/core_split/selected_basket_weights.csv')
macro=pd.read_csv(ROOT/'output/research_r15/features_by_origin.csv',index_col=0,float_precision='round_trip')
maximum=0.;weight_checks=0
for origin,state in saved.items():
    t=pd.Period(origin);clock=pd.Timestamp(state['as_of'])
    history=levels.loc[levels.index<t].copy();dates=available.reindex(history.index)
    history.loc[~(dates.notna()&dates.le(clock))]=np.nan
    rates=(100*np.log(history/history.shift())).iloc[-96:]
    means=rates.groupby(rates.index.month).mean().reindex(range(1,13)).to_numpy()
    adjusted=rates.to_numpy()-means[rates.index.month-1];sigma=np.maximum(.05,np.nanstd(adjusted,axis=0))
    last3=pd.period_range(t-3,t-1,freq='M');last=rates.reindex(last3).to_numpy()-means[last3.month-1]
    own=np.column_stack([last[-1]/sigma,last.mean(axis=0)/sigma])
    maximum=max(maximum,float(np.max(np.abs(means-np.array(state['seasonal'])))),float(np.max(np.abs(sigma-state['scales']))),float(np.max(np.abs(own-state['own']))))
    assert state['seasonal_dates']==list(map(str,rates.dropna().index))
    eligible=weights.loc[weights.effective_year.le(t.year)&pd.to_datetime(weights.availability_assumption_date).dt.tz_localize('Europe/Prague').le(clock)]
    regime=int(eligible.effective_year.max());chosen=eligible.loc[eligible.effective_year.eq(regime)].set_index('series_name').weight_permille.reindex(levels.columns)/1000
    np.testing.assert_array_equal(chosen.to_numpy(),state['weights']);assert state['weight_metadata']['effective_year']==regime;weight_checks+=1
    for name,value in state['macro'].items():assert value==macro.loc[origin,name]
    reference=r15[origin];expected=[reference['x']['core3']-reference['filter_states']['fast']['mu'],reference['x']['core1']-reference['x']['core3']]
    assert expected==core_saved[origin]['own']
    assert core_saved[origin]['fast_log']==[reference['forecasts_log']['fast'][str(h)] for h in range(1,13)]
assert maximum<1e-11
receipt=dict(status='passed',snapshots_verified=len(saved),seasonal_scale_own_feature_max_error=maximum,
             historical_weight_regimes_verified=weight_checks,all_macro_features_equal_saved_r15=True,
             all_core_features_fast_baselines_equal_saved_r15=True,unreleased_and_future_category_levels_excluded=True)
(ROOT/'work/research_r17_monthly/snapshot_lineage_verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
