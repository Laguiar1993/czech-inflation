"""Origin-frozen cost gaps; quarterly labour data are never interpolated."""
import numpy as np
import pandas as pd
from tools.paper_replication.build_paper_panel import load_raw
import r17_common as c

COLUMNS=['ulc_gap','tightening','import_gap','ppi_gap','fx_news']


def local(value):
    t=pd.Timestamp(value)
    if pd.isna(t):raise ValueError('Missing clock')
    return t.tz_convert('Europe/Prague').tz_localize(None) if t.tzinfo else t


def visible(values,dates,end,clock):
    s=values.loc[values.index<=end].copy();a=pd.to_datetime(dates.reindex(s.index))
    return s.where(a.notna()&a.le(clock))


def chain(rates):
    if rates.empty:return rates
    ix=pd.period_range(rates.index.min(),rates.index.max(),freq=rates.index.freq)
    return rates.reindex(ix).cumsum(skipna=False)


def relative_gap(relative,reference,window):
    if reference is None:return np.nan
    ix=pd.period_range(reference-window,reference,freq=relative.index.freq)
    v=relative.reindex(ix)
    return float(v.iloc[-1]-v.iloc[:-1].median()) if np.isfinite(v).all() else np.nan


def features_at(core,core_dates,raw,fx,origin,asof,seasonal):
    t=pd.Period(origin,'M');edge=t-1;clock=local(asof)
    observed=visible(core,core_dates,edge,clock)
    logs=100*np.log1p(observed.where(observed>-100)/100)
    logs-=np.array([seasonal.get(p.month,seasonal.get(str(p.month),np.nan)) for p in logs.index])
    level=chain(logs);out={k:np.nan for k in COLUMNS};audit=[]
    def record(name,reference,dates,units):
        if not np.isfinite(out[name]):
            audit.append(dict(feature=name,reference=str(reference) if reference is not None else None,
                              last_publication=None,units=units,value=np.nan,status='missing_required_history'))
            return
        a=pd.to_datetime(pd.Series(dates)).dropna()
        last=a.max() if len(a) else pd.NaT
        if pd.notna(last) and last>clock:raise ValueError('Future source in provenance')
        audit.append(dict(feature=name,reference=str(reference) if reference is not None else None,
                          last_publication=last.isoformat() if pd.notna(last) else None,units=units,value=out[name],status='available'))
    q=raw[17];qe=edge.asfreq('Q')
    qv=visible(q.values,q.available,qe,clock).where(lambda x:x>0)
    coreq=level.groupby(level.index.asfreq('Q')).agg(['mean','count'])
    coreq=coreq['mean'].where(coreq['count'].eq(3))
    # Select latest reported complete quarter, not an older convenient finite gap.
    complete_q=pd.PeriodIndex([p for p in qv.dropna().index if p.asfreq('M','end')<=edge],freq='Q')
    ref=complete_q.max() if len(complete_q) else None
    rel=100*np.log(qv)-coreq.reindex(qv.index)
    out['ulc_gap']=relative_gap(rel,ref,12)
    usedq=pd.period_range(ref-12,ref,freq='Q') if ref is not None else qv.index[:0]
    core_used=core_dates.loc[core_dates.index<=ref.asfreq('M','end')] if ref is not None else core_dates.iloc[:0]
    record('ulc_gap',ref,[*q.available.reindex(usedq),*core_used], 'quarterly real-cost gap, log points')
    u=raw[11];uv=visible(u.values,u.available,edge,clock);ur=uv.last_valid_index()
    if ur is not None:
        pair=uv.reindex([ur-12,ur]);out['tightening']=float(pair.iloc[0]-pair.iloc[1]) if pair.notna().all() else np.nan
    record('tightening',ur,u.available.reindex([ur-12,ur]) if ur is not None else [],'negative unemployment change12, pp')
    refs={}
    for name,n in [('import_gap',26),('ppi_gap',47)]:
        r=raw[n];v=visible(r.values,r.available,edge,clock);ref=v.last_valid_index();refs[name]=ref
        if n==26:up=chain(100*np.log1p(v.where(v>-100)/100))
        else:up=100*np.log(v.where(v>0))
        rel=up-level.reindex(up.index);out[name]=relative_gap(rel,ref,36)
        idx=(r.values.index[r.values.index<=ref] if n==26 else pd.period_range(ref-36,ref,freq='M')) if ref is not None else r.values.index[:0]
        # Imports require the chained prefix; published PPI levels only use
        # the 37-month relative-level window. Core still requires its prefix.
        dates=[*r.available.reindex(idx),*core_dates.loc[core_dates.index<=ref]] if ref is not None else []
        record(name,ref,dates,'relative price gap, log points')
    fa=pd.Series((fx.index+1).to_timestamp(),index=fx.index)
    fv=visible(fx,fa,t,clock).where(lambda x:x>0);fr=fv.last_valid_index();ir=refs['import_gap']
    if fr is not None and ir is not None and fr>=ir:
        pair=fv.reindex([ir,fr]);out['fx_news']=float(100*np.log(pair.iloc[1]/pair.iloc[0])) if pair.notna().all() else np.nan
    record('fx_news',fr,[*fa.reindex([ir,fr]),raw[26].available.get(ir,pd.NaT)] if fr is not None and ir is not None else [],'FX log change since import reference')
    return pd.Series(out,dtype=float),audit


def load_inputs():
    files=['tests/fixtures/cleanup/cnb_core_mm.csv','data/release_calendar_cz_cpi.csv',
           'data/paper_replication/a6_inputs_20260912/exact_inputs_long.csv','data/paper_replication/a6_inputs_20260912/candidate_inputs_long.csv',
           'output/independent_path_frozen_inputs.csv','output/research_r15/states.json','tools/paper_replication/build_paper_panel.py',
           'tools/paper_replication/a6_catalog.py','data/cost_gaps_r23.py','r17_common.py']
    raw=load_raw(luci=c.ROOT/'data/research_r23_no_luci.csv')
    if raw[26].kind!='mm_change_pct':raise ValueError('Declared import monthly-percent source required')
    core=c.monthly(files[0],'core');dates=c.publication_dates(core.index);fx=c.monthly(files[4],'eurczk')
    return core,dates,raw,fx,{p:c.sha(c.ROOT/p) for p in files}
