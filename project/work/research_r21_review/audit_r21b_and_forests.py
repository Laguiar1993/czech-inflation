"""Independent anchor reconstruction and sampled core-forest replay."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from quantile_forest import RandomForestQuantileRegressor

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from models.policy_anchor_r21 import core_anchor

HERE = Path(__file__).resolve().parent
stats = {}


def read(name):
    return pd.read_csv(ROOT/name, float_precision="round_trip", low_memory=False)


def monthly(name, key="period"):
    x=read(name).set_index(key)
    x.index=pd.PeriodIndex(x.index,freq="M")
    return x


def same(a,b):
    np.testing.assert_allclose(a,b,atol=1e-10,rtol=0,equal_nan=True)


cal=monthly("data/release_calendar_cz_cpi.csv","target_month")
detail=pd.to_datetime(cal.detail_release_dt)+pd.Timedelta(hours=9)
base=monthly("output/independent_nowcast_forecasts.csv")
errors=monthly("output/independent_nowcast_hard_errors.csv").iloc[:,0]
x=monthly("output/research_r21/nowcast/core_features_at_decision.csv")
diag=read("output/research_r21/nowcast/training.csv")
pred=read("output/research_r21/nowcast/predictions.csv")
forest_checks=[]
for origin in pd.PeriodIndex(["2019-02","2024-01","2026-07"],freq="M"):
    clock=pd.Timestamp(base.loc[origin,"as_of_eve"])
    eligible=errors[(errors.index<origin)&detail.reindex(errors.index).le(clock)].dropna()
    train=x.loc[eligible.index].astype(float)
    means=train.mean().fillna(0.)
    train=train.fillna(means)
    now=x.loc[[origin]].fillna(means)
    for name,klass,kw in [("MEAN",RandomForestRegressor,{}),("MEDIAN",RandomForestQuantileRegressor,{"quantiles":.5})]:
        model=klass(n_estimators=200,min_samples_leaf=8,max_features=1.,random_state=42,n_jobs=1)
        model.fit(train,eligible.to_numpy(float))
        correction=float(model.predict(now,**kw)[0])
        model_name="CORE_RF_"+name+"_R21"
        d=diag[diag.origin.eq(str(origin))&diag.model.eq(model_name)].iloc[0]
        p=pred[pred.origin.eq(str(origin))&pred.model.eq(model_name)].iloc[0]
        same(correction,d.correction)
        same(p.forecast,base.loc[origin,"HARD_BASE"]+base.loc[origin,"coreweight"]*correction)
        forest_checks.append(dict(origin=str(origin),model=model_name,n=len(eligible),correction=correction))
stats["forest_replays"]=forest_checks

survey=read("data/czcpmom_survey_history_extended.csv")
survey=survey[survey.era.ne("flash_survey_suspect")].set_index("target_month")
same(pred.actual,survey.loc[pred.origin,"actual"])
same(pred.consensus,survey.loc[pred.origin,"survey_median"])
stats["first_release_actual_and_consensus_source_rows_verified"]=len(pred)
scores=[]
for model,g in pred.groupby("model"):
    surprise=g.actual-g.consensus
    deviation=g.forecast-g.consensus
    error=g.forecast-g.actual
    gain=surprise.abs()-error.abs()
    for name,mask in {"full90":np.ones(len(g),bool),"common66":g.origin.ge("2021-02"),"2024+":g.origin.ge("2024-01"),"big":surprise.abs().ge(.4-1e-9),"alerts":deviation.abs().ge(.2-1e-9)}.items():
        err=error[mask]
        scores.append(dict(model=model,sample=name,n=int(mask.sum()),rmse=float(np.sqrt(np.mean(err**2))),mae=float(err.abs().mean()),material_wins=int(gain[mask].ge(.15-1e-9).sum()),material_losses=int(gain[mask].le(-.15+1e-9).sum())))
pd.DataFrame(scores).to_csv(HERE/"independent_nowcast_scores.csv",index=False)

anchor_dir=ROOT/"output/research_r21/path_anchor"
manifest=json.loads((anchor_dir/"manifest.json").read_text())
for name,digest in manifest["inputs"].items():
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
for name,digest in manifest["outputs"].items():
    assert hashlib.sha256((anchor_dir/name).read_bytes()).hexdigest()==digest,name
stats["anchor_verified_hashes"]=len(manifest["inputs"])+len(manifest["outputs"])
anchors=read("output/research_r21/path_anchor/anchors.csv")
native=read("output/research_r21/path_anchor/native_forecasts.csv")
prior=read("output/research_r21/path/native_forecasts.csv")
forecasts=read("output/research_r21/path_anchor/forecasts.csv")
core=monthly("tests/fixtures/cleanup/cnb_core_mm.csv").core
headline=monthly("output/independent_path_frozen_inputs.csv").headline_mm
states=json.loads((ROOT/"output/research_r15/states.json").read_text())
same(native.iloc[:len(prior)].mm_forecast,prior.mm_forecast)
assert native.iloc[:len(prior)].fillna("<NA>").equals(prior.fillna("<NA>"))
assert native.groupby("model").size().eq(1170).all()
spread_counts=[]
for origin, g in anchors.groupby("origin"):
    t=pd.Period(origin,"M")
    clock=pd.Timestamp(g.as_of.iloc[0])
    common=core.index.intersection(headline.index)
    spreads=[]
    for end in common[common<t]:
        window=pd.period_range(end-11,end,freq="M")
        releases=[]
        for month in window:
            d=detail.get(month,pd.NaT)
            if pd.isna(d) and month<cal.index.min():
                d=(month+1).to_timestamp()+pd.Timedelta(days=19,hours=9)
            releases.append(d)
        if any(pd.isna(d) or d>clock for d in releases):
            continue
        a=core.reindex(window).to_numpy()
        b=headline.reindex(window).to_numpy()
        if not np.isfinite(a).all() or not np.isfinite(b).all():
            continue
        annual=100*np.log(np.prod((1+a/100)/(1+b/100)))
        spreads.append((end,annual,max(releases)))
    spreads=spreads[-120:]
    n=len(spreads)
    median=np.median([q[1] for q in spreads])
    anchor=(100*np.log(1.02)+n/(n+120)*median)/12
    spread_counts.append(n)
    fast=prior[prior.origin.eq(origin)&prior.model.eq("STATE_FAST_R15")].set_index("h")
    state=states[origin]
    mu=state["filter_states"]["fast"]["mu"]
    cycle=state["filter_states"]["fast"]["cycle"]
    for row in g.itertuples():
        assert row.n==n
        same(row.anchor_log_monthly,anchor)
        same(row.median_annual_log_spread,median)
        assert row.first_target==str(spreads[0][0]) and row.last_target==str(spreads[-1][0])
        assert pd.Timestamp(row.last_release)==max(q[2] for q in spreads)
        hl=12 if row.model=="ANCHOR_HL12_R21" else 24
        out=native[native.origin.eq(origin)&native.model.eq(row.model)].set_index("h")
        f=forecasts[forecasts.origin.eq(origin)&forecasts.model.eq(row.model)].set_index("h")
        same(out.loc[0,"mm_forecast"],fast.loc[0,"mm_forecast"])
        for col in [c for c in out if c.startswith("weight_") or c.startswith(("value_","contribution_")) and c not in ["value_core","contribution_core"]]:
            same(out[col],fast[col])
        for h in range(1,13):
            trend=mu+(anchor-mu)*(1-np.exp(-np.log(2)*(h+1)/hl))
            log_rate=trend+cycle*.8**(h+1)+state["seasonal"][str((t+h).month)]
            value=100*(np.exp(log_rate/100)-1)
            same(out.loc[h,"value_core"],value)
            same(out.loc[h,"mm_forecast"],fast.loc[h,"mm_forecast"]+fast.loc[h,"weight_core"]*(value-fast.loc[h,"value_core"]))
            path=f.mm_forecast.to_dict()
            months=pd.period_range(t+h-11,t+h,freq="M")
            rates=[headline.loc[m] if m<t else path[m.ordinal-t.ordinal] for m in months]
            same(f.loc[h,"yy_exante"],100*(np.prod(1+np.array(rates)/100)-1))
        same(f.cumulative_log_forecast.loc[range(1,13)],100*np.log(np.cumprod(1+f.mm_forecast.loc[range(1,13)].to_numpy()/100)))
stats["anchor_diagnostics_and_paths_rebuilt"]=[len(anchors),len(anchors)*13]
stats["anchor_spread_counts_range"]=[min(spread_counts),max(spread_counts)]

# Delayed historical publication, a missing month, and future values are poisoned
# independently. A missing row must invalidate all twelve overlapping years.
ix=pd.period_range("2000-01",periods=180,freq="M")
c=pd.Series(.2,index=ix)
h=pd.Series(.1,index=ix)
a=pd.Series((ix+1).to_timestamp(),index=ix)
o=ix[160]
a.iloc[140]=pd.Timestamp("2050-01-01")
a.iloc[125]=pd.NaT
original=core_anchor(c,h,a,o,pd.Timestamp("2013-06-01"))
c.iloc[[125,140]]=1e50
h.iloc[[125,140]]=-1e50
c.iloc[160:]=-1e50
h.iloc[160:]=1e50
assert core_anchor(c,h,a,o,pd.Timestamp("2013-06-01"))==original
assert core_anchor(c.drop(ix[125]),h.drop(ix[125]),a,o,pd.Timestamp("2013-06-01"))==original
stats["anchor_delayed_missing_and_future_poison_invariant"]=True
(HERE/"anchor_and_forest_results.json").write_text(json.dumps(stats,indent=2),encoding="utf-8")
print(json.dumps(stats,indent=2))
