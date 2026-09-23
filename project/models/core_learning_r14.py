"""R14 origin-specific core trends and delayed band learning; no I/O or surveys."""
from __future__ import annotations

import numpy as np
import pandas as pd

BANDS=((1,3),(4,6),(7,9),(10,12))
CONFIGS=tuple(f'a{a}_w{w}' for a in (3,30,300) for w in ('60','expanding'))
DEFAULT='a30_wexpanding'
MODELS=('CORE_LOCAL_R14','CORE_LEVEL_RIDGE_R14','CORE_GAP_RIDGE_R14',
        'CORE_GAP_ADAPT_R14','CORE_LEVEL_RF_R14','CORE_GAP_RF_R14')
FEATURES=('core1','core3','core12','core_acceleration','import3','import12','fx3','fx12')


def local_clock(value):
    stamp=pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError('A valid decision clock is required')
    return stamp.tz_convert('Europe/Prague').tz_localize(None) if stamp.tzinfo else stamp


def origin_state(core,features,available,origin,as_of,*,import_available_from=None):
    """Build an own-clock row; optional import dates are keyed by fixture month."""
    r=pd.Period(origin,'M');clock=local_clock(as_of)
    import_dates={}
    if import_available_from is not None:
        idx=import_available_from.index
        if not isinstance(idx,pd.PeriodIndex) or idx.freqstr!='M' or not idx.is_unique:
            raise ValueError('Import availability requires unique monthly fixture keys')
        for month,value in import_available_from.items():
            stamp=pd.Timestamp(value)
            if pd.isna(stamp) or stamp.tzinfo is None:
                raise ValueError('Import availability overrides must be valid timezone-aware dates')
            import_dates[month]=local_clock(stamp)
    history=core.loc[core.index<r]
    release=pd.to_datetime(available.reindex(history.index))
    history=history.loc[release.notna() & release.le(clock)]
    if not len(history):return None
    history=history.loc[history.first_valid_index():]
    if len(history)<36 or history.index[-1]!=r-1:return None
    if not history.index.equals(pd.period_range(history.index[0],r-1,freq='M')):
        return None
    if not np.isfinite(history).all() or (history<=-100).any():return None
    q=100*np.log1p(history/100)
    detrended=(q-q.rolling(12,min_periods=12).mean()).dropna().tail(120)
    seas=detrended.groupby(detrended.index.month).mean().reindex(range(1,13))
    if not np.isfinite(seas).all():return None
    seas-=seas.mean()
    adjusted=q-np.array([seas[m.month] for m in q.index])
    trend=float(q.tail(12).mean())
    values=dict(core1=float(adjusted.iloc[-1]),core3=float(adjusted.tail(3).mean()),
                core12=float(adjusted.tail(12).mean()))
    values['core_acceleration']=values['core3']-values['core12']
    source_audit={}
    for family,col,last in [('import','import_l2',r-3),('fx','eurczk_mm',r-1)]:
        months=pd.period_range(last-11,last,freq='M')
        fixture=months+2 if family=='import' else months
        source=features[col].reindex(fixture).to_numpy(dtype=float)
        pub=[(m+2).to_timestamp()+pd.Timedelta(days=15) if family=='import' else (m+1).to_timestamp() for m in months]
        if family=='import':
            pub=[import_dates.get(f,p) for f,p in zip(fixture,pub)]
        if any(p>clock for p in pub) or not np.isfinite(source).all() or (source<=-100).any():return None
        transformed=100*np.log1p(source/100)
        values[family+'3']=float(transformed[-3:].mean())
        values[family+'12']=float(transformed.sum())
        source_audit[family]=dict(first=str(months[0]),last=str(last),last_fixture=str(fixture[-1]),
                                 last_available_from=str(max(pub)))
        if family=='import' and import_available_from is not None:
            source_audit[family]['n_availability_overrides']=sum(f in import_dates for f in fixture)
    return dict(x=values,trend=trend,seasonal={int(k):float(v) for k,v in seas.items()},
                history_end=str(history.index[-1]),n_history=len(history),n_seasonal=len(detrended),
                last_core_release=str(release.loc[history.index[-1]]),sources=source_audit,as_of=str(clock))


def band_design(states,band):
    lo,hi=band
    rows=[]
    for r,s in sorted(states.items()):
        months=np.array([(r+h).month for h in range(lo,hi+1)])
        rows.append(dict(origin=r,**s['x'],calendar_sin=float(np.sin(2*np.pi*months/12).mean()),
                         calendar_cos=float(np.cos(2*np.pi*months/12).mean())))
    return pd.DataFrame(rows).set_index('origin')


def labels_at(core,available,states,origin,as_of,band):
    """Only fully matured band outcomes; seasonal factors stay at pseudo-origin."""
    t=pd.Period(origin,'M');clock=local_clock(as_of);lo,hi=band
    values={};audit=[]
    for r,s in sorted(states.items()):
        if r+hi>=t:continue
        months=pd.period_range(r+lo,r+hi,freq='M')
        dates=pd.to_datetime(available.reindex(months))
        if dates.isna().any() or dates.gt(clock).any():continue
        yy=core.reindex(months).to_numpy(dtype=float)
        if not np.isfinite(yy).all() or (yy<=-100).any():continue
        values[r]=float(np.mean(100*np.log1p(yy/100)-np.array([s['seasonal'][m.month] for m in months])))
        audit.append(dict(origin=str(r),last_target=str(months[-1]),available_from=str(dates.max()),actual=values[r]-s['trend']))
    return pd.Series(values,dtype=float),pd.DataFrame(audit,columns=['origin','last_target','available_from','actual'])


def ridge(x,y,now,alpha):
    info=dict(status='insufficient_history',n_train=len(x))
    if len(x)<48:return np.nan,info
    if not np.isfinite(x.to_numpy(dtype=float)).all() or not np.isfinite(y).all():
        raise ValueError('Training inputs must be complete and finite')
    if not np.isfinite(now.to_numpy(dtype=float)).all():return np.nan,dict(info,status='unavailable_current_predictor')
    center=x.mean();scale=x.std(ddof=0).mask((x.nunique(dropna=False)<=1)|x.std(ddof=0).eq(0),1.)
    z=((x-center)/scale).to_numpy(dtype=float);yy=y.to_numpy(dtype=float)
    beta=np.linalg.solve(z.T@z+alpha*np.eye(z.shape[1]),z.T@(yy-yy.mean()))
    pred=float(yy.mean()+((now-center)/scale).to_numpy(dtype=float)@beta)
    return pred,dict(info,status='estimated',alpha=alpha,center=center.to_dict(),scale=scale.to_dict(),
                     coefficients=dict(zip(x.columns,beta.tolist())),intercept=float(yy.mean()))


def config_values(key):
    if key not in CONFIGS:raise ValueError('Unknown frozen configuration')
    a,w=key.split('_w')
    return float(a[1:]),None if w=='expanding' else int(w)


def select_config(predictions,outcomes,origin,as_of,band):
    t=pd.Period(origin,'M');clock=local_clock(as_of)
    result=dict(config=DEFAULT,n_validation=0,reason='insufficient_validation',validation_origins=[],losses={})
    if predictions.empty or outcomes.empty:return result
    p=predictions.loc[predictions.band.eq(band)&predictions.config.isin(CONFIGS)].copy()
    p=p.loc[p.origin.map(lambda r:pd.Period(r,'M')<t)]
    truth=outcomes.copy()
    dates=pd.to_datetime(truth.available_from)
    truth=truth.loc[dates.notna()&dates.le(clock)&truth.last_target.map(lambda r:pd.Period(r,'M')<t)]
    if truth.origin.duplicated().any() or p.duplicated(['origin','config']).any():
        raise ValueError('Duplicate sequential predictions/outcomes')
    joined=p.merge(truth,on='origin',how='inner',validate='many_to_one')
    joined=joined.loc[np.isfinite(joined.prediction)&np.isfinite(joined.actual)]
    joined['sq']=(joined.prediction-joined.actual)**2
    wide=joined.pivot(index='origin',columns='config',values='sq').reindex(columns=CONFIGS).dropna().sort_index().tail(36)
    result.update(n_validation=len(wide),validation_origins=list(wide.index))
    if len(wide):result['validation_last_release']=str(pd.to_datetime(truth.loc[truth.origin.isin(wide.index),'available_from']).max())
    if len(wide)<24:return result
    loss=wide.mean();tied=[c for c in CONFIGS if np.isclose(loss[c],loss.min(),rtol=1e-10,atol=1e-12)]
    winner=DEFAULT if DEFAULT in tied else tied[0]
    result.update(config=winner,reason='minimum_prior_mse' if len(tied)==1 else 'fixed_tie_order',losses=loss.to_dict())
    return result


def monthly_path(origin,seasonal,means):
    t=pd.Period(origin,'M');path={}
    for b,(lo,hi) in enumerate(BANDS):
        for h in range(lo,hi+1):
            value=means.get(b,np.nan)
            path[h]=float(100*np.expm1((value+seasonal[(t+h).month])/100)) if np.isfinite(value) else np.nan
    return path
