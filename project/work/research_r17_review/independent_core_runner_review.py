from pathlib import Path
import argparse,json,sys,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--run',default='output/research_r17_core');args=parser.parse_args()
folder=ROOT/args.run;OUT=ROOT/'work/research_r17_review'
read=lambda f:pd.read_csv(f,float_precision='round_trip')
manifest=json.loads((folder/'manifest.json').read_text())
hash_checks={}
for fn,dig in manifest['inputs'].items():hash_checks[fn]=hashlib.sha256((ROOT/fn).read_bytes()).hexdigest()==dig
for fn,dig in manifest['outputs'].items():hash_checks[str(folder.relative_to(ROOT)/fn)]=hashlib.sha256((folder/fn).read_bytes()).hexdigest()==dig
assert all(hash_checks.values())
hist=read(folder/'h0_history.csv');hist['month']=pd.PeriodIndex(hist.origin,freq='M')
archive=pd.DataFrame(json.loads((ROOT/'output/independent_nowcast_diagnostics.json').read_text())).query("policy=='hard'").set_index('period').core_forecast
core=read(ROOT/'tests/fixtures/cleanup/cnb_core_mm.csv').set_index('period').core
cal=read(ROOT/'data/release_calendar_cz_cpi.csv').set_index('target_month')
dates=pd.to_datetime(cal.detail_release_dt).dt.normalize()+pd.Timedelta(hours=9)
states=json.loads((folder/'states.json').read_text())
lineage_error=0.
for r in hist.itertuples():
 baseline=states[r.origin][r.parent]['h0_log']
 expected_h0=100*np.log1p(archive[r.origin]/100)
 expected_error=100*np.log1p(core[r.origin]/100)-baseline
 lineage_error=max(lineage_error,abs(r.baseline_log-baseline),abs(r.h0_log-expected_h0),abs(r.signal-(expected_h0-baseline)),abs(r.error-expected_error))
 assert pd.Timestamp(r.available_from)==dates[r.origin]
assert lineage_error<1e-12
updates=json.loads((folder/'updates.json').read_text());beta_error=0.;delta_error=0.;train_max=0
for u in updates:
 t=pd.Period(u['origin'],freq='M');clock=pd.Timestamp(u['as_of'])
 g=hist.loc[hist.parent.eq(u['parent'])&hist.month.lt(t)&pd.to_datetime(hist.available_from).le(clock)].sort_values('origin')
 g=g[np.isfinite(g[['signal','error']]).all(axis=1)].tail(60);n=len(g);denom=float(g.signal@g.signal)
 expected=float(np.clip(float(g.signal@g.error)/denom*n/(n+24),0,1)) if n>=12 and denom>1e-12 else 0.
 beta_error=max(beta_error,abs(u['beta']-expected))
 assert u['n_train']==n and u['training_origins']==g.origin.tolist()
 assert [pd.Timestamp(x) for x in u['training_releases']]==pd.to_datetime(g.available_from).tolist()
 current=hist.loc[hist.origin.eq(u['origin'])&hist.parent.eq(u['parent'])].iloc[0]
 delta_error=max(delta_error,abs(u['delta']-expected*current.signal));train_max=max(train_max,n)
assert beta_error<1e-12 and delta_error<1e-12
base=read(ROOT/'output/research_r15/native_forecasts.csv').query("model=='STATE_FAST_R15'")
native=read(folder/'native_forecasts.csv');compound=read(folder/'forecasts.csv');preds=read(folder/'core_predictions.csv')
x=native.merge(base,on=['origin','h'],suffixes=('','_base'),validate='many_to_one')
preserve=[c for c in native if c.startswith(('value_','contribution_','weight_')) and c not in ['value_core','contribution_core']]
for c in preserve:
 assert np.array_equal(x[c],x[c+'_base'],equal_nan=True),c
assert (x.as_of_utc==x.as_of_utc_base).all()
assert np.array_equal(x.loc[x.h.eq(0),'mm_forecast'],x.loc[x.h.eq(0),'mm_forecast_base'],equal_nan=True)
expected=x.mm_forecast_base+x.weight_core*(x.value_core-x.value_core_base);future=x.h.gt(0)
monthly_error=float(abs(x.loc[future,'mm_forecast']-expected[future]).max());assert monthly_error<1e-12
pred=preds.merge(native[['origin','model','h','value_core']],on=['origin','model','h'],validate='one_to_one')
assert np.max(abs(pred.core_mm-pred.value_core))<1e-12
assert np.max(abs(pred.core_mm-100*np.expm1(pred.core_log/100)))<1e-12
head=read(ROOT/'output/independent_path_frozen_inputs.csv').set_index('period').headline_mm
head.index=pd.PeriodIndex(head.index,freq='M')
annual_error=0.;cum_error=0.
for (origin,model),g in compound.groupby(['origin','model']):
 t=pd.Period(origin,'M');g=g.set_index('h').sort_index();assert g.index.tolist()==list(range(13))
 for h in range(13):
  window=pd.period_range(t+h-11,t+h,freq='M')
  values=np.array([head.get(m,np.nan) if m<t else g.at[m.ordinal-t.ordinal,'mm_forecast'] for m in window])
  expected_annual=100*(np.prod(1+values/100)-1)
  assert np.isfinite(expected_annual)==np.isfinite(g.at[h,'yy_exante'])
  if np.isfinite(expected_annual): annual_error=max(annual_error,abs(expected_annual-g.at[h,'yy_exante']))
  expected_cum=100*np.log1p(g.loc[1:h,'mm_forecast']/100).sum()
  cum_error=max(cum_error,abs(expected_cum-g.at[h,'cumulative_log_forecast']))
assert annual_error<1e-10 and cum_error<1e-12
stale=[]
for c in ['cumulative_log_forecast','yy_exante']:
 if c not in native:continue
 merged=native[['origin','model','h',c]].merge(compound[['origin','model','h',c]],on=['origin','model','h'],suffixes=('_native','_compound'))
 finite=merged[c+'_native'].notna()
 gap=abs(merged.loc[finite,c+'_native']-merged.loc[finite,c+'_compound'])
 if len(gap) and gap.max()>1e-10:stale.append({'column':c,'max_error':float(gap.max())})
result={'reviewed_run':args.run,'all_input_output_hashes_valid':True,'input_output_hash_count':len(hash_checks),'origin_count':native.origin.nunique(),'state_count':len(states),'h0_rows':len(hist),'h0_update_count':len(updates),'h0_lineage_log_max_error':lineage_error,'beta_manual_max_error':beta_error,'delta_manual_max_error':delta_error,'maximum_training_count':train_max,'h0_and_untouched_components_exact':True,'replacement_monthly_max_error':monthly_error,'annual_independent_product_max_error':annual_error,'cumulative_independent_log_max_error':cum_error,'stale_native_derived_columns':stale,'review_status':'needs_native_export_fix' if stale else 'pass'}
(OUT/('core_runner_'+folder.name+'_review.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))

