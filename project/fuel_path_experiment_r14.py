"""Frozen R14 future-fuel experiment; --verify refits all90 origins offline."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from tools.r14_fuel.prepare import ROOT,DATA,load,sha
from models.fuel_path_r14 import forecast,MODELS
from models.path_inputs import compound_path
from path_improvements_experiment_r12 import read,dump,score_panel,add_outcomes_and_compound

OUT=ROOT/'output/research_r14/fuel'
BASE='INDEPENDENT_BRIDGE'
PAIRS=[(m,BASE) for m in MODELS]+[('FUEL_ECM_R14','FUEL_CONSTANT_PUMP_R14'),('FUEL_ECM_R14','FUEL_ZERO_R14')]


def hashes():
    names=['fuel_path_experiment_r14.py','models/fuel_path_r14.py','test_fuel_path_r14.py',
        'tools/r14_fuel/prepare.py','docs/implementation/R14_FUEL_DESIGN.md','path_improvements_experiment_r12.py',
        'models/path_inputs.py','models/components.py','cz_struct.py','independent_bridge_experiment.py',
        'data/release_calendar_cz_cpi.csv','output/independent_bridge_forecasts.csv',
        'output/independent_bridge_manifest.json','tests/fixtures/cleanup/target_headline_cpi_mm.csv',
        'tests/fixtures/cleanup/component_food_fuel_mm.csv','tests/fixtures/cleanup/fuel_weekly.csv']
    old=json.loads((ROOT/'output/independent_bridge_manifest.json').read_text())
    for name,expected in old['fingerprints'].items():
        if sha(ROOT/name)!=expected: raise AssertionError(f'frozen baseline dependency changed: {name}')
    names+=list(old['fingerprints'])
    names+=[p.relative_to(ROOT).as_posix() for p in DATA.rglob('*') if p.is_file()]
    return {name:sha(ROOT/name) for name in sorted(set(names))}


def sample_masks(frame):
    return [('full',np.ones(len(frame),bool)),('recent_targets',frame.target>='2024-01'),
            ('recent_origins',frame.origin>='2024-01')]


def fuel_scores(native,actual):
    rows=[]
    for (origin,model),group in native.groupby(['origin','model'],sort=False):
        t=pd.Period(origin,'M'); p=group.set_index('h').value_fuel
        for h in range(1,13):
            pred=p.reindex(range(1,h+1)).to_numpy()
            real=actual.reindex(pd.period_range(t+1,t+h,freq='M')).to_numpy()
            rows.append(dict(origin=origin,target=str(t+h),h=h,model=model,
                mm_forecast=p.loc[h],mm_actual=actual.get(t+h,np.nan),
                cumulative_forecast=100*np.expm1(np.log1p(pred/100).sum()) if np.isfinite(pred).all() and (pred>-100).all() else np.nan,
                cumulative_actual=100*np.expm1(np.log1p(real/100).sum()) if np.isfinite(real).all() and (real>-100).all() else np.nan))
    detail=pd.DataFrame(rows); scores=[]
    for sample,mask in sample_masks(detail):
        for h in range(1,13):
            g=detail.loc[mask&detail.h.eq(h)]
            for metric in ('mm','cumulative'):
                wide=g.pivot(index='origin',columns='model',values=metric+'_forecast')
                truth=g.drop_duplicates('origin').set_index('origin')[metric+'_actual']
                common=wide.index[wide.notna().all(axis=1)&truth.reindex(wide.index).notna()]
                for model in wide:
                    error=wide.loc[common,model]-truth.reindex(common)
                    scores.append(dict(sample=sample,h=h,model=model,metric=metric,n=len(error),
                        rmse=float(np.sqrt(np.mean(error**2))) if len(error) else np.nan,
                        mae=float(abs(error).mean()) if len(error) else np.nan,bias=float(error.mean()) if len(error) else np.nan))
    return detail,pd.DataFrame(scores)


def uncertainty(frame):
    rng=np.random.default_rng(42); bootstrap=[]; omitted=[]
    for sample,mask in sample_masks(frame):
        for h in range(1,13):
            g=frame.loc[mask&frame.h.eq(h)]
            for candidate,reference in PAIRS:
                a=g[g.model==candidate].set_index('origin'); b=g[g.model==reference].set_index('origin')
                pair=pd.concat([(a.yy_exante-a.yy_actual).rename('a'),(b.yy_exante-b.yy_actual).rename('b')],axis=1).dropna().sort_index()
                n=len(pair)
                if not n: continue
                ae,be=pair.a.to_numpy(),pair.b.to_numpy()
                for block in (12,6,18):
                    starts=rng.integers(0,n,(5000,int(np.ceil(n/block))))
                    ix=((starts[:,:,None]+np.arange(block))%n).reshape(5000,-1)[:,:n]
                    for metric in ('rmse','mae'):
                        if metric=='rmse': delta=np.sqrt(np.mean(ae[ix]**2,axis=1))-np.sqrt(np.mean(be[ix]**2,axis=1)); observed=np.sqrt(np.mean(ae**2))-np.sqrt(np.mean(be**2))
                        else: delta=np.mean(abs(ae[ix]),axis=1)-np.mean(abs(be[ix]),axis=1); observed=np.mean(abs(ae))-np.mean(abs(be))
                        lo,hi=np.quantile(delta,[.025,.975])
                        bootstrap.append(dict(sample=sample,h=h,candidate=candidate,reference=reference,n=n,
                            metric=metric,delta=observed,lower=lo,upper=hi,block=block,draws=5000,seed=42))
                if sample=='full':
                    for origin in pair.index:
                        keep=pair.index!=origin
                        omitted.append(dict(h=h,candidate=candidate,reference=reference,omitted_origin=origin,n=int(keep.sum()),
                            delta_rmse=np.sqrt(np.mean(ae[keep]**2))-np.sqrt(np.mean(be[keep]**2))))
    return pd.DataFrame(bootstrap),pd.DataFrame(omitted)


def attribution(native,head,fuel):
    annual_oracle={}; monthly_oracle={}
    for origin,g in native[native.model==BASE].groupby('origin'):
        t=pd.Period(origin,'M'); g=g.set_index('h'); p=g.mm_forecast.to_dict()
        for h in range(1,13):
            row=g.loc[h]; p[h]+=row.weight_fuel*(fuel.get(t+h,np.nan)-row.value_fuel)
            monthly_oracle[(origin,h)]=p[h]
        for h in range(1,13): annual_oracle[(origin,h)]=compound_path(head.loc[head.index<t],p,t,h,p[0])
    rows=[]
    for candidate,reference in PAIRS:
        a=native[native.model==candidate].set_index(['origin','h'])
        b=native[native.model==reference].set_index(['origin','h'])
        for key,ar in a[a.index.get_level_values('h')>0].iterrows():
            br=b.loc[key]
            for metric,forecast_col,actual_col,oracle in [('yy','yy_exante','yy_actual',annual_oracle),('mm','mm_forecast','mm_actual',monthly_oracle)]:
                common=oracle[key]; other=common-ar[actual_col]
                ac=ar[forecast_col]-common; bc=br[forecast_col]-common
                headline_gain=(br[forecast_col]-ar[actual_col])**2-(ar[forecast_col]-ar[actual_col])**2
                core_gain=bc**2-ac**2; cross=2*other*(bc-ac)
                if np.isfinite(headline_gain) and abs(headline_gain-core_gain-cross)>1e-9:
                    raise AssertionError('fuel/shared-other attribution failed')
                rows.append(dict(origin=key[0],target=ar.target,h=key[1],candidate=candidate,reference=reference,metric=metric,
                    candidate_fuel_error=ac,reference_fuel_error=bc,shared_other_error=other,
                    fuel_squared_gain=core_gain,cross_term_gain=cross,headline_squared_gain=headline_gain))
    return pd.DataFrame(rows)


def run(destination=OUT):
    import cz_struct as s
    inputs=hashes(); data=load(); destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    baseline=pd.read_csv(ROOT/'output/independent_bridge_forecasts.csv',float_precision='round_trip')
    baseline=baseline[baseline.model==BASE].copy()
    if sorted(baseline.origin.unique())!=pd.period_range('2019-02','2026-07',freq='M').astype(str).tolist():
        raise AssertionError('declared90 origins required')
    rows=[baseline]; audits=[]; parameters=[]; used=[]; weekly=[]
    for i,(origin,g) in enumerate(baseline.groupby('origin',sort=True)):
        t=pd.Period(origin,'M'); clock=pd.Timestamp(g.as_of_utc.iloc[0]).tz_convert('Europe/Prague').tz_localize(None)
        share=s._petrol_share(t,clock)
        result=forecast(data,t,clock,share)
        for name,path in result['forecasts'].items():
            changed=g.copy(); changed['model']=name
            for h,prediction in enumerate(path,1):
                mask=changed.h.eq(h)
                changed.loc[mask,'mm_forecast']+=changed.loc[mask,'weight_fuel']*(prediction-changed.loc[mask,'value_fuel'])
                changed.loc[mask,'value_fuel']=prediction
                changed.loc[mask,'contribution_fuel']=changed.loc[mask,'weight_fuel']*prediction
            changed['fallback_used']=result['audit']['fallback_used'] if name=='FUEL_ECM_R14' else False
            changed['status']=np.where(changed.mm_forecast.notna(),'estimated','unavailable_nonfuel')
            # Derived annual columns are cleared until exact post-fit compounding.
            changed[['yy_exante','yy_conditional']]=np.nan
            rows.append(changed)
        audits.append(dict(origin=origin,as_of=clock,**result['audit']))
        parameters.extend(dict(origin=origin,as_of=str(clock),**p) for p in result['parameters'])
        used.append(result['fit_rows'].assign(origin=origin))
        weekly.append(result['weekly_paths'].assign(origin=origin))
        if i%15==0: print(f'Fitted fuel origin{i+1}/90: {origin}',flush=True)
    native=pd.concat(rows,ignore_index=True)
    # Fits cannot access scoring outcomes; those are read only after fitting.
    head=read(ROOT/'tests/fixtures/cleanup/target_headline_cpi_mm.csv').iloc[:,0]
    fuel=read(ROOT/'tests/fixtures/cleanup/component_food_fuel_mm.csv').fuel
    keep=['origin','h','target','as_of_utc','mm_forecast','model']
    scored,target_delta=add_outcomes_and_compound(native[keep],head,baseline)
    derived=[c for c in scored if c not in keep]
    native=native.drop(columns=[c for c in derived if c in native]).merge(scored[['origin','h','model',*derived]],on=['origin','h','model'],validate='one_to_one')
    native.to_csv(destination/'native_forecasts.csv',index=False)
    scored.to_csv(destination/'forecasts.csv',index=False)
    pd.DataFrame(audits).to_csv(destination/'origin_audit.csv',index=False)
    pd.DataFrame(parameters).to_csv(destination/'parameters.csv',index=False)
    pd.concat(used,ignore_index=True).to_csv(destination/'training_rows.csv',index=False)
    pd.concat(weekly,ignore_index=True).to_csv(destination/'weekly_paths.csv',index=False)
    summaries=[score_panel(scored,[BASE,*MODELS],'roster_common')]
    for a,b in PAIRS: summaries.append(score_panel(scored,[b,a],f'paired_{a}_vs_{b}'))
    summary=pd.concat(summaries,ignore_index=True); summary.to_csv(destination/'summary.csv',index=False)
    detail,component_scores=fuel_scores(native,fuel)
    detail.to_csv(destination/'fuel_outcomes.csv',index=False); component_scores.to_csv(destination/'fuel_summary.csv',index=False)
    boot,omissions=uncertainty(scored)
    boot.to_csv(destination/'bootstrap.csv',index=False); omissions.to_csv(destination/'leave_one_out.csv',index=False)
    attr=attribution(native,head,fuel); attr.to_csv(destination/'attribution.csv',index=False)
    attr_summary=[]
    for sample,mask in sample_masks(attr):
        tab=attr.loc[mask].groupby(['candidate','reference','h','metric'])[['fuel_squared_gain','cross_term_gain','headline_squared_gain']].agg(['count','mean'])
        tab.columns=['_'.join(c) for c in tab.columns]; attr_summary.append(tab.reset_index().assign(sample=sample))
    pd.concat(attr_summary,ignore_index=True).to_csv(destination/'attribution_summary.csv',index=False)
    specification=dict(primary='FUEL_ECM_R14',models=[BASE,*MODELS],n_origins=90,
        status_counts=pd.DataFrame(audits).status.value_counts().to_dict(),fallback_origins=[r['origin'] for r in audits if r['fallback_used']],
        source_vintage='Current frozen primary histories with reconstructed publication clocks; no archived vintages.',
        scenario='Latest origin-observable oil, FX, effective tax/reconciliation wedge and VAT held unchanged.',
        target_delta=target_delta,no_promotion=True,selection_status='Reused historical sample; intervals are not selection-adjusted.')
    dump(destination/'specification.json',specification)
    if hashes()!=inputs: raise AssertionError('fuel dependencies changed during execution')
    outputs={p.name:sha(p) for p in sorted(destination.glob('*.csv'))}; outputs['specification.json']=sha(destination/'specification.json')
    manifest=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),inputs=inputs,outputs=outputs)
    dump(destination/'manifest.json',manifest)
    print(summary.query("scope=='roster_common' and h in [1,3,6,12]")
        [['sample','h','model','n_common','yy_rmse','yy_mae','yy_bias']].to_string(index=False),flush=True)
    return manifest


def verify():
    frozen=json.loads((OUT/'manifest.json').read_text())
    for name,expected in frozen['inputs'].items():
        if sha(ROOT/name)!=expected: raise AssertionError(f'fuel input changed:{name}')
    for name,expected in frozen['outputs'].items():
        if sha(OUT/name)!=expected: raise AssertionError(f'fuel output changed:{name}')
    def forbidden(*a,**kw): raise AssertionError('offline fuel replay attempted network/database access')
    with tempfile.TemporaryDirectory(prefix='fuel_r14_') as folder,ExitStack() as stack:
        for target in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(target,side_effect=forbidden))
        replay=run(folder)
    if replay['outputs']!=frozen['outputs']: raise AssertionError('freshly fitted fuel output differs')
    print(f"Offline fresh refit: {len(frozen['outputs'])} fuel outputs byte-identical.")


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--verify',action='store_true')
    args=parser.parse_args(); verify() if args.verify else run()
