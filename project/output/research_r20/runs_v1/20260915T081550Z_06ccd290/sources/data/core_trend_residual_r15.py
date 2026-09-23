"""Own-origin independent predictor blocks; input panels already carry release masks."""
import numpy as np
import pandas as pd
from tools.paper_replication.a6_catalog import ROWS

HARD_ROWS=tuple(r.number for r in ROWS if r.kind=='hard' and r.number not in (14,15,16))
DOMESTIC=('services_yoy','services_change3','unemployment','unemployment_change3','ip_growth3','ulc_growth12')
IMPORTED=('goods_yoy','goods_change3','fx1','fx3',*[f'cost_{r}_{suffix}' for r in (23,26,45,47,56,62) for suffix in ('now','mean3')])


def local(value):
    stamp=pd.Timestamp(value)
    return stamp.tz_convert('Europe/Prague').tz_localize(None) if stamp.tzinfo else stamp


def features_at(state,panel,broad,fx,available,origin,as_of):
    t=pd.Period(origin,'M');edge=t-1;clock=local(as_of)
    if not panel.index.is_unique or not broad.index.is_unique or not fx.index.is_unique:
        raise ValueError('Predictor periods must be unique')
    p=panel.loc[:edge];out=dict(state['x'])
    def value(column,month=edge):
        return float(p[column].get(month,np.nan))
    def growth(column,lag):
        a,b=value(column),value(column,edge-lag)
        return float(100*np.log(a/b)) if np.isfinite(a) and np.isfinite(b) and min(a,b)>0 else np.nan
    for name in ('services','goods'):
        vals=[]
        for month in (edge,edge-3):
            released=available.get(month,pd.NaT)
            vals.append(float(broad[name].get(month,np.nan)) if pd.notna(released) and local(released)<=clock else np.nan)
        out[name+'_yoy']=vals[0];out[name+'_change3']=vals[0]-vals[1]
    out.update(unemployment=value('a6_11'),unemployment_change3=value('a6_11')-value('a6_11',edge-3),
               ip_growth3=growth('a6_12',3),ulc_growth12=growth('a6_17',12))
    moves=fx.reindex(pd.period_range(edge-2,edge,freq='M'))
    logmoves=100*np.log1p(moves.where(moves>-100)/100)
    out.update(fx1=float(logmoves.iloc[-1]),fx3=float(logmoves.sum(min_count=3)))
    for row in (23,26,45,47,56,62):
        series=p[f'a6_{row:02}'].reindex(pd.period_range(edge-2,edge,freq='M'))
        out[f'cost_{row}_now']=float(series.iloc[-1])
        out[f'cost_{row}_mean3']=float(series.mean()) if series.notna().all() else np.nan
    for row in HARD_ROWS:
        out[f'a6_{row:02}']=value(f'a6_{row:02}')
    result=pd.Series(out,dtype=float)
    if np.isinf(result).any():raise ValueError('Infinite predictor')
    return result


def feature_groups(columns):
    own=[c for c in columns if c not in (*DOMESTIC,*IMPORTED) and not c.startswith('a6_')]
    return dict(domestic=own+list(DOMESTIC),imported=own+list(IMPORTED),
                both=own+list(DOMESTIC)+list(IMPORTED),
                wide=own+['services_yoy','services_change3','goods_yoy','goods_change3','fx1','fx3']
                     +[f'a6_{r:02}' for r in HARD_ROWS])
