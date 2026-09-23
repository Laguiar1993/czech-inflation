"""Frozen R17 integration/evaluation audit. No implementation writes or fitting."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'work/research_r17_review';run=ROOT/'output/research_r17/path';ev=run/'evaluation'
read=lambda p:pd.read_csv(p,float_precision='round_trip',low_memory=False)
partial='--integration-only' in sys.argv
checks={}
for source,base in ([(run/'manifest.json',ROOT)] if partial else [(run/'manifest.json',ROOT),(ev/'input_manifest.json',ROOT)]):
 manifest=json.loads(source.read_text())
 for cat,folder in [('inputs',base),('outputs',source.parent)]:
  for name,digest in manifest[cat].items():
   p=folder/name;checks[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()==digest
assert all(checks.values()),[k for k,v in checks.items() if not v]
manifest=json.loads((run/'manifest.json').read_text());roster=manifest['controls']+manifest['models'];nmodels=len(roster)
native=read(run/'native_forecasts.csv');forecast=read(run/'forecasts.csv');primary=None if partial else read(ev/'primary_rows.csv')
assert native.groupby('model').size().eq(90*13).all() and not native.duplicated(['origin','model','h']).any()
get=lambda m:native[native.model.eq(m)].sort_values(['origin','h']).reset_index(drop=True)
fast=get('STATE_FAST_R15');clocks=fast.drop_duplicates('origin').set_index('origin').as_of_utc
cols=[col for col in native if col.startswith(('value_','contribution_')) or col=='mm_forecast']
for model in roster:
 g=get(model);assert g[['origin','h','target','as_of_utc']].equals(fast[['origin','h','target','as_of_utc']])
 assert np.array_equal(g.loc[g.h.eq(0),'mm_forecast'],fast.loc[fast.h.eq(0),'mm_forecast'],equal_nan=True)
 for col in [k for k in native if k.startswith('weight_')]:assert np.array_equal(g[col],fast[col],equal_nan=True)
# Fixed whole monthly mixtures; all component/contribution columns, not annual rates.
recipes={'COMBO_CORE_R17':(['CORE_NEWS_H0_R17','MONTHLY_BOTH_CORE_R17'],[.5,.5]),'PATH_FAST_CURRENT_HALF_R17':(['STATE_FAST_R15','STABLE_LOCAL_CORE_R14B'],[.5,.5]),'PATH_COMPONENT_HALF_R17':(['STATE_FAST_R15','COMBO_ALL_R17'],[.5,.5])}
mix_error=0.
for name,(sources,weights) in recipes.items():
 actual=get(name);mask=actual.h.gt(0)
 for col in cols:
  expected=sum(w*get(m).loc[mask,col].to_numpy() for m,w in zip(sources,weights))
  diff=actual.loc[mask,col].to_numpy()-expected;assert np.array_equal(np.isfinite(actual.loc[mask,col]),np.isfinite(expected))
  if np.isfinite(diff).any():mix_error=max(mix_error,float(np.nanmax(abs(diff))))
for name,parent in [('COMBO_FOOD_FUEL_R17','STATE_FAST_R15'),('COMBO_ALL_R17','COMBO_CORE_R17')]:
 actual=get(name);expected=get(parent).copy();mask=actual.h.gt(0)
 for block,model in [('food','FOOD_SYMMETRIC_R17'),('fuel','FUEL_ANNUAL_R17')]:
  child=get(model);expected.loc[mask,'mm_forecast']+=child.loc[mask,'contribution_'+block].to_numpy()-expected.loc[mask,'contribution_'+block].to_numpy()
  for col in ['value_'+block,'contribution_'+block]:expected.loc[mask,col]=child.loc[mask,col].to_numpy()
 for col in cols:
  assert np.array_equal(np.isfinite(actual[col]),np.isfinite(expected[col]))
  if actual[col].notna().any():mix_error=max(mix_error,float(np.nanmax(abs(actual[col]-expected[col]))))
assert mix_error<1e-10
head=read(ROOT/'output/independent_path_frozen_inputs.csv').set_index('period').headline_mm;head.index=pd.PeriodIndex(head.index,freq='M')
annual=100*((1+head/100).rolling(12).apply(np.prod,raw=True)-1)
annual_error=0.;cum_error=0.
for (origin,model),g in forecast.groupby(['origin','model']):
 t=pd.Period(origin,'M');g=g.set_index('h').sort_index()
 for h in range(13):
  rates=[head.get(m,np.nan) if m<t else g.at[m.ordinal-t.ordinal,'mm_forecast'] for m in pd.period_range(t+h-11,t+h,freq='M')]
  expected=100*(np.prod(1+np.array(rates)/100)-1);actual=g.at[h,'yy_exante'];assert np.isfinite(expected)==np.isfinite(actual)
  if np.isfinite(expected):annual_error=max(annual_error,abs(expected-actual))
  expected_cum=100*np.log1p(g.loc[1:h,'mm_forecast']/100).to_numpy().sum();saved=g.at[h,'cumulative_log_forecast'];assert np.isfinite(expected_cum)==np.isfinite(saved)
  if np.isfinite(saved):cum_error=max(cum_error,abs(saved-expected_cum))
assert annual_error<1e-10 and cum_error<1e-10
for col in ['yy_exante','cumulative_log_forecast','cumulative_log_actual']:
 merged=native[['origin','h','model',col]].merge(forecast[['origin','h','model',col]],on=['origin','h','model'],suffixes=('_native','_forecast'),validate='one_to_one')
 assert np.allclose(merged[col+'_native'],merged[col+'_forecast'],atol=1e-10,rtol=0,equal_nan=True)

cn=read(run/'selection_candidate_native.csv');cf=read(run/'selection_candidate_forecasts.csv');selection=json.loads((run/'selections.json').read_text())
decl=json.loads((run/'declaration.json').read_text());config={'component':{'ALPHA_0':[1.,0.],'ALPHA_25':[.75,.25],'ALPHA_50':[.5,.5]},'pool':decl['pool_grid']}
sources={'component':['STATE_FAST_R15','COMBO_ALL_R17'],'pool':['STATE_FAST_R15','STABLE_LOCAL_CORE_R14B','DAMPED_P95_Q001_R16','COMBO_ALL_R17']}
calendar=read(ROOT/'data/release_calendar_cz_cpi.csv').set_index('target_month');calendar.index=pd.PeriodIndex(calendar.index,freq='M')
available=pd.to_datetime(calendar.detail_release_dt).dt.normalize()+pd.Timedelta(hours=9)
loss_cache={};release_cache={}
candidate_mix_error=0.
for family,configs in config.items():
 loss_cache[family]={};release_cache[family]={}
 for name,weights in configs.items():
  candidate=cn[cn.family.eq(family)&cn.model.eq(name)].sort_values(['origin','h']).reset_index(drop=True);mask=candidate.h.gt(0)
  for col in cols:
   expected=np.zeros(mask.sum())
   for source,w in zip(sources[family],weights):
    if w:expected+=w*get(source).loc[mask,col].to_numpy()
   assert np.array_equal(np.isfinite(expected),np.isfinite(candidate.loc[mask,col]))
   if np.isfinite(expected).any():candidate_mix_error=max(candidate_mix_error,float(np.nanmax(abs(expected-candidate.loc[mask,col]))))
 for origin,g in cf[cf.family.eq(family)&cf.h.gt(0)].groupby('origin'):
  t=pd.Period(origin,'M');releases=available.reindex(pd.period_range(t+1,t+12,freq='M'))
  if releases.isna().any():continue
  losses={};complete=True
  for name in configs:
   own=g[g.model.eq(name)].sort_values('h')
   if own.h.tolist()!=list(range(1,13)) or not np.isfinite(own[['yy_exante','yy_actual']]).all().all():complete=False;break
   losses[name]=float(np.mean((own.yy_exante-own.yy_actual)**2))
  if complete:loss_cache[family][origin]=losses;release_cache[family][origin]=releases.max()
selection_objective_error=0.;selected_path_error=0.;default_count=0
for row in selection:
 family=row['family'];configs=config[family];t=pd.Period(row['origin'],'M');clock=pd.Timestamp(row['as_of']).tz_convert('Europe/Prague').tz_localize(None)
 eligible=sorted(o for o in loss_cache[family] if pd.Period(o,'M')+12<t and release_cache[family][o]<=clock)[-36:]
 assert row['validation_origins']==eligible and row['n_validation']==len(eligible)
 assert [pd.Timestamp(x) for x in row['validation_releases']]==[release_cache[family][o] for o in eligible]
 objectives={name:float(np.mean([loss_cache[family][o][name] for o in eligible])+.05*sum(w*w for w in weights[1:])) for name,weights in configs.items()} if eligible else {}
 for name in objectives:selection_objective_error=max(selection_objective_error,abs(objectives[name]-row['objectives'][name]))
 chosen=min(configs,key=lambda k:(objectives[k],-configs[k][0],list(configs).index(k))) if len(eligible)>=12 else next(iter(configs))
 assert chosen==row['chosen'] and configs[chosen]==row['weights'];default_count+=len(eligible)<12
 target='PATH_COMPONENT_SELECT_R17' if family=='component' else 'PATH_POOL_R17'
 actual=native[native.origin.eq(row['origin'])&native.model.eq(target)].sort_values('h')
 expected=cn[cn.family.eq(family)&cn.origin.eq(row['origin'])&cn.model.eq(chosen)].sort_values('h')
 for col in cols:
  assert np.array_equal(actual[col].to_numpy(),expected[col].to_numpy(),equal_nan=True),col
assert max(candidate_mix_error,selection_objective_error)<1e-10 and len(selection)==180
if partial:
 result=dict(status='integration_pass_evaluation_pending',input_output_hashes_verified=len(checks),origins=90,models=nmodels,h0_weights_and_clocks_exact=True,fixed_mixture_max_error=mix_error,annual_ordinary_product_max_error=annual_error,cumulative_max_error=cum_error,candidate_mixture_max_error=candidate_mix_error,selection_rows=180,selector_objective_max_error=selection_objective_error,selected_paths_exact=True,early_FAST_defaults=default_count)
 (OUT/'integration_selector_review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));sys.exit(0)

old=read(ROOT/'output/research_r16/forecasts.csv');nold=old.model.nunique();assert nold==15
ok=old.h.gt(0)&np.isfinite(old.yy_exante)&np.isfinite(old.yy_actual);count=old.loc[ok].groupby(['origin','h']).model.nunique();support=set(count[count.eq(15)].index)
assert len(support)==969 and set(map(tuple,primary[['origin','h']].drop_duplicates().to_numpy()))==support and len(primary)==969*nmodels
for model,g in primary.groupby('model'):assert set(map(tuple,g[['origin','h']].to_numpy()))==support
actual_components=read(ROOT/'output/research_r14b/attribution/actual_component_targets.csv').set_index('period');actual_components.index=pd.PeriodIndex(actual_components.index,freq='M')
components=read(ev/'component_outcomes.csv');assert set(components.block)=={'core','food','fuel','administered','alcohol_tobacco'}
component_error=0.
for (origin,model,block),g in components.groupby(['origin','model','block']):
 g=g.sort_values('h');t=pd.Period(origin,'M');truth=actual_components[block].reindex(pd.period_range(t+1,t+12,freq='M')).to_numpy()
 pred=native.loc[native.origin.eq(origin)&native.model.eq(model)&native.h.gt(0)].sort_values('h')['value_'+block].to_numpy()
 for col,expected in [('mm_forecast',pred),('mm_actual',truth),('cumulative_log_forecast',np.cumsum(100*np.log1p(pred/100))),('cumulative_log_actual',np.cumsum(100*np.log1p(truth/100)))]:
  assert np.array_equal(np.isfinite(g[col]),np.isfinite(expected))
  if np.isfinite(expected).any():component_error=max(component_error,float(np.nanmax(abs(g[col]-expected))))
assert component_error<1e-10

scores=read(ev/'scoreboard.csv');component_scores=read(ev/'component_scoreboard.csv');score_error=0.;score_rows_checked=0
for data,table,metrics in [(forecast,scores,{'headline_yy':('yy_exante','yy_actual')}),(components,component_scores,{'monthly':('mm_forecast','mm_actual'),'cumulative_log':('cumulative_log_forecast','cumulative_log_actual')})]:
 groups=data.groupby('block') if 'block' in data else [('headline',data)]
 for block,full in groups:
  for metric,(p,a) in metrics.items():
   own=full[full.h.gt(0)&np.isfinite(full[p])&np.isfinite(full[a])]
   counts=own.groupby(['origin','h']).model.nunique();keys=counts[counts.eq(nmodels)].index
   common=own.set_index(['origin','h']).loc[lambda x:x.index.isin(keys)].reset_index()
   records=table[table.scope.eq('all_models_common')&table['sample'].eq('full')&table.metric.eq(metric)]
   if 'block' in table:records=records[records.block.eq(block)]
   for row in records.itertuples():
    g=common[common.model.eq(row.model)&common.h.eq(row.h)];errors=(g[p]-g[a]).to_numpy();assert row.n==len(errors)
    if len(errors):
     score_error=max(score_error,abs(row.rmse-float(np.sqrt(np.mean(errors**2)))),abs(row.mae-float(np.mean(abs(errors)))),abs(row.bias-float(errors.mean())))
    score_rows_checked+=1
assert score_error<1e-10

pair=read(ev/'cnb_pairs.csv');clock_rows=read(ev/'cnb_clocks.csv');rawcnb=read(ROOT/'data/cnb_mpr_cpi_quarterly.csv')
rawcnb=rawcnb[rawcnb.is_forecast.astype(str).str.lower().eq('true')]
clock_series=pd.to_datetime(clocks,utc=True);cnb_error=0.;quarter_error=0.
for row in clock_rows.itertuples():
 date=row.report_date if row.clock=='report' else row.cutoff_date
 boundary=(pd.Timestamp(date)+pd.Timedelta(days=int(row.clock=='cutoff'))).tz_localize('Europe/Prague').tz_convert('UTC')
 allowed=clock_series[clock_series<boundary].sort_values();assert row.origin==allowed.index[-1] and pd.Timestamp(row.as_of_utc)==allowed.iloc[-1]
for row in pair.itertuples():
 cnb=float(rawcnb.loc[rawcnb.report_date.eq(row.report_date)&rawcnb.quarter.eq(row.quarter),'value'].iloc[0]);q=pd.Period(row.quarter,'Q');months=pd.period_range(q.asfreq('M','start'),q.asfreq('M','end'),freq='M');truth=float(annual.reindex(months).mean())
 assert np.isfinite(annual.reindex(months)).all();origin=pd.Period(row.origin,'M')
 if row.model=='cnb':expected=cnb
 else:
  f=forecast[forecast.origin.eq(row.origin)&forecast.model.eq(row.model)].set_index('target').yy_exante
  expected=float(np.mean([annual[m] if m<origin else f.get(str(m),np.nan) for m in months]))
 quarter_error=max(quarter_error,abs(expected-row.forecast),abs(truth-row.realised))
 gain=abs(cnb-truth)-abs(expected-truth);cnb_error=max(cnb_error,abs(gain-row.abs_error_gain_vs_cnb))
 assert row.material_gain==(gain>=.15-1e-12) and row.material_loss==(gain<=-.15+1e-12)
assert max(quarter_error,cnb_error)<1e-10
assert pair.groupby(['clock','report_date','quarter']).model.nunique().eq(nmodels+1).all()
bands=read(ev/'underlying_core_bands.csv');signals=read(ev/'sustained_movement_pairs.csv');ss=read(ev/'sustained_movement_summary.csv')
def signal(vals):
 if not np.isfinite(vals).all():return np.nan
 a,b,c=vals
 if c-a>=.5 and b-a>-.5 and c-b>-.5:return 1
 if c-a<=-.5 and b-a<.5 and c-b<.5:return -1
 return 0
for row in signals.itertuples():
 g=bands[bands.origin.eq(row.origin)&bands.model.eq(row.model)].set_index('band').loc[[1,2,3]]
 for label,col in [('predicted','predicted_sa_annualized'),('actual','actual_sa_annualized')]:
  expected=signal(g[col].to_numpy());actual=getattr(row,label);assert actual==expected or np.isnan(actual) and np.isnan(expected)
counts=signals[signals.eligible].groupby('origin').model.nunique();common=signals[signals.origin.isin(counts[counts.eq(nmodels)].index)]
for row in ss[ss['sample'].eq('full')].itertuples():
 g=common[common.model.eq(row.model)];events=g.actual.ne(0);calls=g.predicted.ne(0);hits=events&calls&g.predicted.eq(g.actual)
 assert row.n==len(g) and row.actual_events==events.sum() and row.calls==calls.sum() and row.hits==hits.sum()
 assert row.misses==(events&~hits).sum() and row.false_calls==(calls&~hits).sum()
result=dict(status='pass',input_output_hashes_verified=len(checks),origins=90,models=nmodels,h0_weights_and_clocks_exact=True,fixed_mixture_max_error=mix_error,annual_ordinary_product_max_error=annual_error,cumulative_max_error=cum_error,candidate_mixture_max_error=candidate_mix_error,selection_rows=180,selector_objective_max_error=selection_objective_error,selected_paths_exact=True,early_FAST_defaults=default_count,primary_keys=969,component_rows=len(components),component_max_error=component_error,common_score_rows_checked=score_rows_checked,common_score_max_error=score_error,cnb_pair_rows=len(pair),cnb_quarter_max_error=quarter_error,cnb_gain_max_error=cnb_error,sustained_common_false_alarm_counts_verified=True)
(OUT/'integrated_output_review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
