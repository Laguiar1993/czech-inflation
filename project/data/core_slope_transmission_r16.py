"""Separate annual-price signal features and saved-projection core designs."""
import numpy as np
import pandas as pd
from data.core_trend_residual_r15 import features_at,local

SIGNALS=('services','goods')
FAMILIES=('own','services','goods','both')


def signal_features_at(panel,broad,fx,available,origin,as_of):
    t=pd.Period(origin,'M');clock=local(as_of)
    base=features_at({'x':{}},panel,broad,fx,available,t,clock)
    result={}
    for signal in SIGNALS:
        values=[]
        for month in (t-1,t-4,t-13):
            raw=broad[signal].get(month,np.nan);date=available.get(month,pd.NaT)
            values.append(float(100*np.log1p(raw/100)) if pd.notna(date) and local(date)<=clock and np.isfinite(raw) and raw>-100 else np.nan)
        own=dict(level=values[0],change3=values[0]-values[1],change12=values[0]-values[2])
        columns=('unemployment_change3','ulc_growth12','ip_growth3') if signal=='services' else (
            'cost_26_mean3','cost_45_mean3','cost_47_mean3','fx3','cost_62_mean3')
        result[signal]=pd.Series(own|base.reindex(columns).to_dict(),dtype=float)
    return result


def stage2_design(projections,acceleration,band,family):
    if family not in FAMILIES:raise ValueError('Unknown transmission family')
    if projections.duplicated(['origin','band','signal']).any():raise ValueError('Duplicate saved projection')
    if not acceleration.index.is_unique:raise ValueError('Duplicate acceleration origin')
    design=acceleration.to_frame('core_acceleration').copy()
    selected=projections[projections.band.eq(band)]
    for signal in SIGNALS if family=='both' else (() if family=='own' else (family,)):
        rows=selected[selected.signal.eq(signal)].copy()
        rows.index=pd.PeriodIndex(rows.origin,freq='M')
        prediction=rows.predicted_change.reindex(design.index)
        if np.isinf(prediction).any():raise ValueError('Infinite generated forecast')
        design[signal+'_projection']=prediction/12
        # An unmade first-stage forecast cannot become an imputed predictor.
        design=design.loc[prediction.notna()]
    return design
