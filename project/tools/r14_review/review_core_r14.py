"""Independent R14 numerical oracles; consumes artifacts and never edits them."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/research_r14/core'
extended='--extended' in sys.argv
if extended:OUT=ROOT/'output/research_r14b/core'
sys.path.insert(0,str(ROOT))
def load(name,index=False):
    a=pd.read_csv(ROOT/name,float_precision='round_trip',index_col=0 if index else None)
    if index:a.index=pd.PeriodIndex(a.index,freq='M')
    return a
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((OUT/'manifest.json').read_text())
changed_sources=[p for p,h in manifest['inputs'].items() if digest(ROOT/p)!=h]
assert not [p for p,h in manifest['outputs'].items() if digest(OUT/p)!=h]
core=load('tests/fixtures/cleanup/cnb_core_mm.csv',True).iloc[:,0]
features=load('tests/fixtures/cleanup/core_features.csv',True)
override={}
if extended:
    extension=load('data/research_r14b/imports/core_feature_extension.csv')
    for row in extension.itertuples():
        p=pd.Period(row.period,'M');assert pd.isna(features.loc[p,'import_l2'])
        features.loc[p,'import_l2']=row.import_l2
        date=pd.Timestamp(row.available_from)
        assert date==(p+1).to_timestamp().tz_localize('Europe/Prague')
        override[p]=date.tz_convert('Europe/Prague').tz_localize(None)
cal=load('data/release_calendar_cz_cpi.csv').set_index('target_month')
released=pd.Series({r:pd.Timestamp(cal.loc[str(r),'detail_release_dt']).normalize()+pd.Timedelta(hours=9)
                    if str(r) in cal.index else ((r+1).to_timestamp()+pd.Timedelta(days=19,hours=9) if r<pd.Period(cal.index.min(),'M') else pd.NaT) for r in core.index})
saved=json.loads((OUT/'historical_states.json').read_text())
states={};maxstate=0.
for origin,state in saved.items():
    t=pd.Period(origin,'M');clock=pd.Timestamp(state['as_of'])
    series=core.loc[(core.index<t)&released.le(clock)]
    assert series.index.equals(pd.period_range(series.index[0],t-1,freq='M'))
    q=np.log1p(series/100)*100
    centered=(q-q.rolling(12,min_periods=12).mean()).dropna().iloc[-120:]
    season=centered.groupby(centered.index.month).mean();season-=season.mean()
    trend=float(q.iloc[-12:].mean())
    adjusted=q-pd.Series([season[r.month] for r in q.index],index=q.index)
    x=dict(core1=adjusted.iloc[-1],core3=adjusted.iloc[-3:].mean(),core12=adjusted.iloc[-12:].mean())
    x['core_acceleration']=x['core3']-x['core12']
    for family,col,source_last,shift in [('import','import_l2',t-3,2),('fx','eurczk_mm',t-1,0)]:
        source=pd.period_range(source_last-11,source_last,freq='M')
        dates=[override.get(r+2,(r+2).to_timestamp()+pd.Timedelta(days=15)) if family=='import' else (r+1).to_timestamp() for r in source]
        assert max(dates)<=clock
        rates=features[col].reindex(source+shift).to_numpy()
        assert np.isfinite(rates).all()
        z=100*np.log1p(rates/100);x[family+'3']=z[-3:].mean();x[family+'12']=z.sum()
        assert state['sources'][family]['last']==str(source[-1])
        assert state['sources'][family]['last_available_from']==str(max(dates))
    assert state['history_end']==str(t-1)
    comparisons=[abs(trend-state['trend'])]+[abs(v-state['x'][k]) for k,v in x.items()]+[abs(v-state['seasonal'][str(k)]) for k,v in season.items()]
    maxstate=max(maxstate,max(comparisons));assert max(comparisons)<1e-12
    assert abs(season.sum())<1e-12
    states[t]=dict(x=x,trend=trend,season=season,clock=clock)

configs=[f'a{a}_w{w}' for a in (3,30,300) for w in ('60','expanding')]
bands=[(1,3),(4,6),(7,9),(10,12)]
design={};alllevels={}
for b,(lo,hi) in enumerate(bands):
    design[b]=pd.DataFrame({r:dict(**s['x'],calendar_sin=np.mean([np.sin(2*np.pi*(r+k).month/12) for k in range(lo,hi+1)]),
                                  calendar_cos=np.mean([np.cos(2*np.pi*(r+k).month/12) for k in range(lo,hi+1)])) for r,s in states.items()}).T
    alllevels[b]=pd.Series({r:np.mean([100*np.log1p(core.get(r+k,np.nan)/100)-s['season'][(r+k).month] for k in range(lo,hi+1)]) for r,s in states.items()})
def train_for(t,b,clock,window=None):
    lo,hi=bands[b]
    rows=[]
    for r in states:
        if r+hi>=t or (window is not None and r<t-window):continue
        dates=released.reindex(pd.period_range(r+lo,r+hi,freq='M'))
        if dates.isna().any() or dates.gt(clock).any() or not np.isfinite(alllevels[b].get(r,np.nan)):continue
        assert states[r]['clock']<clock
        rows.append(r)
    return pd.PeriodIndex(rows,freq='M')
def predict_ridge(x,y,now,alpha):
    a=x.to_numpy();yy=y.to_numpy();means=a.mean(axis=0);sd=a.std(axis=0)
    sd[np.array([len(np.unique(a[:,j]))<=1 for j in range(a.shape[1])])| (sd==0)]=1
    z=(a-means)/sd;beta=np.linalg.solve(z.T@z+np.eye(a.shape[1])*alpha,z.T@(yy-yy.mean()))
    return float(yy.mean()+((now.to_numpy()-means)/sd)@beta)

candidates=load(OUT/'sequential_candidates.csv');maxridge=0.;estimated=0
for row in candidates.itertuples():
    t=pd.Period(row.origin,'M');clock=pd.Timestamp(row.as_of);assert clock==states[t]['clock']
    alpha,win=row.config[1:].split('_w');tr=train_for(t,row.band,clock,None if win=='expanding' else int(win))
    assert row.n_train==len(tr)
    if len(tr):
        assert str(tr.min())==row.train_start and str(tr.max())==row.train_end
        assert row.last_training_target==str(tr.max()+bands[row.band][1])
        assert pd.Timestamp(row.last_training_release)<=clock
    if len(tr)<48:assert np.isnan(row.prediction);continue
    y=alllevels[row.band].loc[tr]-pd.Series({r:states[r]['trend'] for r in tr})
    expected=predict_ridge(design[row.band].loc[tr],y,design[row.band].loc[t],float(alpha))
    diff=abs(expected-row.prediction);maxridge=max(maxridge,diff);assert diff<1e-10,(row.origin,row.config,diff)
    estimated+=1

selections=json.loads((OUT/'selections.json').read_text());maxloss=0.
for s in selections:
    t=pd.Period(s['origin'],'M');b=s['band'];clock=pd.Timestamp(s['as_of']);tr=train_for(t,b,clock)
    p=candidates.loc[candidates.band.eq(b)&candidates.origin.isin(tr.astype(str))]
    wide=p.pivot(index='origin',columns='config',values='prediction').reindex(columns=configs).dropna().sort_index().tail(36)
    assert list(wide.index)==s['validation_origins'] and len(wide)==s['n_validation']
    if len(wide)<24:assert s['config']=='a30_wexpanding';continue
    actual=pd.Series({str(r):alllevels[b][r]-states[r]['trend'] for r in tr})
    loss=wide.sub(actual.reindex(wide.index),axis=0).pow(2).mean()
    tied=[c for c in configs if np.isclose(loss[c],loss.min(),rtol=1e-10,atol=1e-12)]
    chosen='a30_wexpanding' if 'a30_wexpanding' in tied else tied[0]
    assert chosen==s['config']
    maxloss=max(maxloss,max(abs(loss[k]-s['losses'][k]) for k in configs))
assert maxloss<1e-12

bandforecasts=load(OUT/'band_forecasts.csv');maxrf=0.;rfcount=0
for origin in ('2021-03','2022-06','2025-06'):
    t=pd.Period(origin,'M');clock=states[t]['clock']
    for b in range(4):
        tr=train_for(t,b,clock);level=alllevels[b].loc[tr];gap=level-pd.Series({r:states[r]['trend'] for r in tr})
        for name,y in [('CORE_LEVEL_RF_R14',level),('CORE_GAP_RF_R14',gap)]:
            if len(tr)<48:continue
            rf=RandomForestRegressor(n_estimators=200,min_samples_leaf=5,max_features=1/3,random_state=42,n_jobs=1,bootstrap=True)
            rf.fit(design[b].loc[tr].to_numpy(),y.to_numpy())
            prediction=rf.predict(design[b].loc[t].to_numpy().reshape(1,-1))[0]+(states[t]['trend'] if 'GAP' in name else 0)
            actual=bandforecasts.loc[bandforecasts.origin.eq(origin)&bandforecasts.band.eq(b)&bandforecasts.model.eq(name),'level_prediction'].iloc[0]
            maxrf=max(maxrf,abs(actual-prediction));assert abs(actual-prediction)<1e-12;rfcount+=1

native=load(OUT/'native_forecasts.csv');forecast=load(OUT/'forecasts.csv')
baseline=load('output/independent_bridge_forecasts.csv').set_index(['origin','h'])
noncore=[c for c in native if c.startswith('weight_') or (c.startswith('contribution_') and c!='contribution_core')]
maxcalendar=0.;maxannual=0.
headline=load('output/independent_path_frozen_inputs.csv',True).headline_mm
for (origin,name),g in native.groupby(['origin','model']):
    t=pd.Period(origin,'M');g=g.set_index('h');base=baseline.loc[origin]
    pd.testing.assert_frame_equal(g[noncore],base[noncore],check_exact=True)
    assert g.loc[0,'mm_forecast']==base.loc[0,'mm_forecast']
    for h in range(1,13):
        band=(h-1)//3
        v=bandforecasts.loc[bandforecasts.origin.eq(origin)&bandforecasts.model.eq(name)&bandforecasts.band.eq(band),'level_prediction'].iloc[0]
        want=100*np.expm1((v+states[t]['season'][(t+h).month])/100)
        got=g.loc[h,'value_core'];assert np.isfinite(got)==np.isfinite(want)
        if np.isfinite(want):maxcalendar=max(maxcalendar,abs(got-want));assert abs(got-want)<1e-12
        parts=[g.loc[h,c] for c in g if c.startswith('contribution_')]
        assert np.allclose(sum(parts),g.loc[h,'mm_forecast'],equal_nan=True,atol=1e-12,rtol=0)
for (origin,name),g in forecast.groupby(['origin','model']):
    t=pd.Period(origin,'M');g=g.set_index('h')
    assert len(g)==13
    for h in range(13):
        assert g.loc[h,'target']==str(t+h)
        months=pd.period_range(t+h-11,t+h,freq='M')
        rates=np.array([headline.get(r,np.nan) if r<t else g.loc[r.ordinal-t.ordinal,'mm_forecast'] for r in months])
        expected=100*(np.prod(1+rates/100)-1)
        got=g.loc[h,'yy_exante'];assert np.isfinite(got)==np.isfinite(expected)
        if np.isfinite(expected):maxannual=max(maxannual,abs(got-expected));assert abs(got-expected)<1e-11

summary=load(OUT/'summary.csv');maxscore=0.
summary['review_roster']=np.where(summary.scope.eq('own_coverage'),summary.model,'shared')
for keys,group in summary.groupby(['scope','sample','h','review_roster']):
    scope,sample,h,roster=keys;models=list(group.model)
    data=forecast.loc[forecast.h.eq(h)&forecast.model.isin(models)]
    if sample=='recent_targets':data=data.loc[data.target>='2024-01']
    if sample=='recent_origins':data=data.loc[data.origin>='2024-01']
    wide=data.pivot(index='origin',columns='model',values='yy_exante').reindex(columns=models)
    truth=data.drop_duplicates('origin').set_index('origin').yy_actual
    common=wide.index[np.isfinite(wide).all(axis=1)&np.isfinite(truth.reindex(wide.index))]
    for row in group.itertuples():
        assert row.n_common==len(common)
        d=data.loc[data.model.eq(row.model)].set_index('origin').reindex(common)
        for prefix,pred,act in [('yy','yy_exante','yy_actual'),('mm','mm_forecast','mm_actual'),('cumulative_log','cumulative_log_forecast','cumulative_log_actual')]:
            err=(d[pred]-d[act]).dropna()
            for metric,value in [('rmse',np.sqrt(np.mean(err**2))),('mae',np.mean(abs(err))),('bias',np.mean(err))]:
                saved_value=getattr(row,prefix+'_'+metric)
                assert np.isfinite(value)==np.isfinite(saved_value)
                if np.isfinite(value):maxscore=max(maxscore,abs(value-saved_value));assert abs(value-saved_value)<1e-11

report=dict(source_hash_mismatches_at_start=changed_sources,payloads=len(manifest['outputs']),historical_states=len(states),
    state_first=str(min(states)),state_last=str(max(states)),state_max_abs_delta=maxstate,
    candidates=len(candidates),estimated_candidate_refits=estimated,candidate_max_abs_delta=maxridge,
    selections=len(selections),selection_loss_max_abs_delta=maxloss,selected_forest_refits=rfcount,forest_max_abs_delta=maxrf,
    native_rows=len(native),native_calendar_max_abs_delta=maxcalendar,annual_rows=len(forecast),annual_max_abs_delta=maxannual,
    score_rows=len(summary),score_max_abs_delta=maxscore)
(Path(__file__).parent/('core_extended_review_oracles.json' if extended else 'core_review_oracles.json')).write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
