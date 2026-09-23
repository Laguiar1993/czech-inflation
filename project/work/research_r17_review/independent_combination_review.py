"""Independent prefit combination contracts; no fitting or scoring writes."""
from pathlib import Path
import hashlib,itertools,json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from models import path_components_r17 as e
from path_component_experiment_r17 import fixed_combinations
from tools.review.evaluate_r17 import sustained_rows,sustained_summary
OUT=ROOT/'work/research_r17_review'
pool=e.pool_grid();expected={tuple(x/4 for x in w) for w in itertools.product(range(5),repeat=4) if sum(w)==4 and w[0]>=2 and max(w[1:])<=1}
assert len(pool)==7 and set(pool.values())==expected and next(iter(pool.values()))==(1,0,0,0)
configs={'BASE':(1.,0.),'QUARTER':(.75,.25),'HALF':(.5,.5)}
origins=pd.period_range('2008-01','2020-06',freq='M');rows=[]
for i,s in enumerate(origins):
 for name,w in configs.items():
  for h in range(1,13):
   actual=.08*i+.1*h
   err={'BASE':.8,'QUARTER':.3,'HALF':.05}[name]+.02*np.sin(i+h)
   rows.append(dict(origin=str(s),h=h,model=name,yy_exante=actual+err,yy_actual=actual))
frame=pd.DataFrame(rows);months=pd.period_range('2008-01','2022-01',freq='M')
dates=pd.Series([(m+1).to_timestamp()+pd.Timedelta(days=15,hours=9) for m in months],index=months)
dates.loc[pd.Period('2017-09','M')]=pd.Timestamp('2030-01-01')
frame.loc[frame.origin.eq('2017-10')&frame.model.eq('QUARTER')&frame.h.eq(4),'yy_exante']=np.nan
origin='2020-04';clock=pd.Timestamp('2020-04-16T09:00:00+02:00');local=clock.tz_localize(None)
eligible=[];sse={k:[] for k in configs};release=[]
for s in origins:
 if s+12>=pd.Period(origin,'M'):continue
 target=[s+h for h in range(1,13)]
 if any(pd.isna(dates.get(m)) or dates[m]>local for m in target):continue
 g=frame[frame.origin.eq(str(s))]
 complete=all(len(g[g.model.eq(k)])==12 and np.isfinite(g[g.model.eq(k)][['yy_exante','yy_actual']]).all().all() for k in configs)
 if not complete:continue
 eligible.append(str(s));release.append(str(max(dates[m] for m in target)))
 for k in configs:
  errors=[float(g.loc[g.model.eq(k)&g.h.eq(h),'yy_exante'].iloc[0]-g.loc[g.model.eq(k)&g.h.eq(h),'yy_actual'].iloc[0]) for h in range(1,13)]
  sse[k].append(sum(v*v for v in errors)/12)
objective={k:sum(v[-36:])/len(v[-36:])+.05*sum(x*x for x in configs[k][1:]) for k,v in sse.items()}
manual=min(configs,key=lambda k:(objective[k],-configs[k][0],list(configs).index(k)))
choice,meta=e.choose_path(frame,dates,origin,clock,configs,'BASE')
assert choice==manual and meta['validation_origins']==eligible[-36:] and meta['validation_releases']==release[-36:] and meta['n_validation']==36
objective_error=max(abs(meta['objectives'][k]-objective[k]) for k in configs);assert objective_error<1e-14
poison=frame.copy();ineligible=~poison.origin.isin(eligible);poison.loc[ineligible,'yy_actual']=1e9
assert e.choose_path(poison,dates,origin,clock,configs,'BASE')==(choice,meta)
short=frame[frame.origin.isin(eligible[-11:])]
default,early=e.choose_path(short,dates,origin,clock,configs,'BASE');assert default=='BASE' and early['n_validation']==11
# Equal MSE plus a nonFAST penalty must retain the allFAST default.
equal=frame.copy();equal.yy_exante=equal.yy_actual
assert e.choose_path(equal,dates,origin,clock,configs,'BASE')[0]=='BASE'

base=pd.DataFrame(dict(origin='2020-01',h=range(13),target=pd.period_range('2020-01',periods=13,freq='M').astype(str),as_of_utc='2020-02-10T22:59:00Z',model='STATE_FAST_R15'))
for block,weight,value in [('core',.5,.2),('food',.2,.3),('fuel',.05,.1),('administered',.2,.4),('alcohol_tobacco',.05,.25)]:
 base['weight_'+('alc' if block=='alcohol_tobacco' else block)]=weight;base['value_'+block]=value;base['contribution_'+block]=weight*value
base['value_wedge']=.03;base['contribution_wedge']=.03
base['mm_forecast']=base.filter(like='contribution_').sum(axis=1)
base['yy_exante']=777.;base['cumulative_log_forecast']=777.;base['yy_conditional']=777.
models={'CORE_NEWS_H0_R17':('core',1.),'MONTHLY_BOTH_CORE_R17':('core',.6),'FOOD_SYMMETRIC_R17':('food',1.2),'FUEL_ANNUAL_R17':('fuel',-.4),'STABLE_LOCAL_CORE_R14B':('core',.8)}
parts=[base]
for name,(block,value) in models.items():
 f=base.copy();f['model']=name;mask=f.h.gt(0);old=f.loc[mask,'contribution_'+block].copy();weight=f.loc[mask,'weight_'+block]
 f.loc[mask,'value_'+block]=value;f.loc[mask,'contribution_'+block]=weight*value;f.loc[mask,'mm_forecast']+=weight*value-old;parts.append(f)
combo=fixed_combinations(pd.concat(parts,ignore_index=True))
core=combo.query("model=='COMBO_CORE_R17' and h>0");allpath=combo.query("model=='COMBO_ALL_R17' and h>0")
assert np.max(abs(core.value_core-.8))<1e-15
assert np.max(abs(allpath.value_core-.8))<1e-15 and np.max(abs(allpath.value_food-1.2))<1e-15 and np.max(abs(allpath.value_fuel+.4))<1e-15
identity_error=float(abs(combo.mm_forecast-combo.filter(like='contribution_').sum(axis=1)).max());assert identity_error<1e-14
assert (combo.loc[combo.h.eq(0),'mm_forecast']==base.mm_forecast.iloc[0]).all()
mix=e.blend_native([parts[0],parts[1]],[.5,.5],'MIX')
mixannual=100*(np.prod(1+mix.loc[mix.h.gt(0),'mm_forecast']/100)-1)
annualaverage=.5*100*(np.prod(1+parts[0].loc[parts[0].h.gt(0),'mm_forecast']/100)-1)+.5*100*(np.prod(1+parts[1].loc[parts[1].h.gt(0),'mm_forecast']/100)-1)
assert abs(mixannual-annualaverage)>1e-4
# Common movement support excludes an origin if any declared model is unavailable.
b=[]
for o in ['2020-01','2020-02']:
 for name in ['a','b']:
  for band in range(1,5):b.append(dict(origin=o,model=name,band=band,predicted_sa_annualized=[2,2.2,2.6,2.6][band-1],actual_sa_annualized=[2,2.1,2.6,2.6][band-1]))
bands=pd.DataFrame(b);bands.loc[bands.origin.eq('2020-02')&bands.model.eq('b')&bands.band.eq(2),'predicted_sa_annualized']=np.nan
signals=sustained_rows(bands);summary=sustained_summary(signals,['a','b']);full=summary[summary['sample'].eq('full')]
assert len(full)==2 and full.n.eq(1).all() and full.hits.eq(1).all() and full.false_calls.eq(0).all()
old=pd.read_csv(ROOT/'output/research_r16/forecasts.csv',float_precision='round_trip');roster=sorted(old.model.unique());assert len(roster)==15
finite=old.h.gt(0)&np.isfinite(old.yy_exante)&np.isfinite(old.yy_actual)
counts=old.loc[finite].groupby(['origin','h']).model.nunique();expected_support=set(counts[counts.eq(15)].index)
support=pd.read_csv(ROOT/'output/research_r17/attribution/primary_support.csv');actual_support=set(map(tuple,support.to_numpy()))
assert len(support)==len(actual_support)==969 and actual_support==expected_support
source_paths=['models/path_components_r17.py','path_component_experiment_r17.py','tools/review/evaluate_r17.py','docs/implementation/R17_COMBINATION_SPEC_2026-09-14.md','tests/test_path_components_r17.py']
result=dict(status='pass_prefit_selector_and_accounting;component_scoring_gap_reported_separately',allowed_pool_weights=7,latest_common_complete_validation_origins=36,manual_objective_max_error=objective_error,unreleased_incomplete_future_label_poisoning_invariant=True,under12_default_FAST=True,monthly_contribution_identity_max_error=identity_error,mixture_h0_exact=True,annual_of_monthly_mixture_differs_from_average_annual=True,sustained_common_support_verified=True,original15_model_primary_support=969,source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_paths})
(OUT/'combination_prefit_review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
