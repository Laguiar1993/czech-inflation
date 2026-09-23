"""Frozen reference-period economic measurements with endpoint publication dates."""
import numpy as np
import pandas as pd
import r17_common as c
from tools.paper_replication.build_paper_panel import load_raw

SERVICES=['ict_services','recreation_services','cultural_services','package_holidays','catering','accommodation']
HOUSING=['actual_rent','imputed_rent']
ORDER=['core','services','housing','goods','unemployment','ulc','ip','imports','ppi','fx','brent','metals']


def log_change(levels,available,lag=1):
    ix=pd.period_range(levels.index.min(),levels.index.max(),freq=levels.index.freq)
    s=levels.reindex(ix);a=pd.to_datetime(available.reindex(ix));old=a.shift(lag)
    valid=s.gt(0)&s.shift(lag).gt(0)&a.notna()&old.notna()
    rate=(100*np.log(s/s.shift(lag))).where(valid)
    dates=pd.concat([a,old],axis=1).max(axis=1).where(valid)
    return rate,dates


def quarterly_pressure(levels,available):
    rate,dates=log_change(levels,available,4);values={};a={};q={}
    for quarter in rate.index:
        for m in pd.period_range(quarter.asfreq('M','end'),periods=3,freq='M'):
            values[m]=rate.loc[quarter];a[m]=dates.loc[quarter];q[m]=str(quarter)
    return pd.Series(values),pd.Series(a),pd.Series(q)


def load_inputs():
    files=['tests/fixtures/cleanup/cnb_core_mm.csv','data/research_r18/categories/primary_monthly_levels.csv',
        'data/research_r18/categories/metadata.json','data/release_calendar_cz_cpi.csv',
        'data/paper_replication/a6_inputs_20260912/exact_inputs_long.csv',
        'data/paper_replication/a6_inputs_20260912/candidate_inputs_long.csv',
        'output/independent_path_frozen_inputs.csv','data/research_transmission_r22.py',
        'tools/paper_replication/build_paper_panel.py','tools/paper_replication/a6_catalog.py']
    hashes={p:c.sha(c.ROOT/p) for p in files}
    raw=load_raw(luci=c.ROOT/'data/research_r22_no_luci.csv')
    core=c.monthly(files[0],'core');categories=c.monthly(files[1]);fx=c.monthly(files[6],'eurczk')
    goods=[x for x in categories if x not in SERVICES+HOUSING]
    if len(goods)!=10:raise ValueError('Declared ten goods measurements required')
    ix=pd.period_range('2015-02',max(core.index.max(),fx.index.max()),freq='M')
    values={};dates={};meta=[]
    values['core']=100*np.log1p(core/100);dates['core']=c.publication_dates(core.index)
    meta.append(dict(variable='core',source='CNB core',units='monthly log points',transform='100log1p(mm/100)'))
    for name,columns in [('services',SERVICES),('housing',HOUSING),('goods',goods)]:
        rates=[];available=[]
        for col in columns:
            r,a=log_change(categories[col],c.publication_dates(categories.index));rates.append(r);available.append(a)
        frame=pd.concat(rates,axis=1);a=pd.concat(available,axis=1)
        values[name]=frame.mean(axis=1).where(frame.notna().all(axis=1))
        dates[name]=a.max(axis=1).where(a.notna().all(axis=1))
        meta.append(dict(variable=name,source='CZSO R18 category proxy',units='mean monthly log points',members=columns,
                         limitation='Not exhaustive CNB core component; equal statistical measurement weights.'))
    for name,number,lag in [('unemployment',11,0),('ip',12,3),('imports',26,0),('ppi',47,1),('brent',60,1),('metals',62,1)]:
        r=raw[number]
        if name=='imports':
            if r.kind!='mm_change_pct':raise ValueError('Import monthly percent-change source required')
            values[name]=100*np.log1p(r.values.where(r.values>-100)/100);dates[name]=r.available
        elif not lag:values[name]=r.values;dates[name]=r.available
        else:values[name],dates[name]=log_change(r.values,r.available,lag)
        meta.append(dict(variable=name,source=r.source,source_kind=r.kind,units='percent level' if name=='unemployment' else 'log percentage points',
                         transform='reported level' if name=='unemployment' else f'log change lag{lag}' if lag else 'log1p monthly percent',
                         availability='existing per-observation available_from_assumed'))
    values['ulc'],dates['ulc'],quarters=quarterly_pressure(raw[17].values,raw[17].available)
    meta.append(dict(variable='ulc',source=raw[17].source,units='annual log growth of quarterly index; reference-step proxy',
         limitation='One quarterly observation carried from quarter-end through next two months, with identical source availability; no monthly observation claim.'))
    fxa=pd.Series((fx.index+1).to_timestamp(),index=fx.index)
    values['fx'],dates['fx']=log_change(fx,fxa)
    meta.append(dict(variable='fx',source=files[6]+':eurczk',units='monthly log points; positive=depreciation',availability='next-month day1'))
    panel=pd.DataFrame({k:v.reindex(ix) for k,v in values.items()})[ORDER]
    available=pd.DataFrame({k:pd.to_datetime(v.reindex(ix)) for k,v in dates.items()})[ORDER]
    if np.isinf(panel.to_numpy()).any():raise ValueError('Infinite transformed input')
    return panel,available,quarters.reindex(ix),meta,hashes
