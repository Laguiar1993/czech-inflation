"""Independent strict-turn, CNB omission/capture and bootstrap-support checks."""
from pathlib import Path
import json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.review.evaluate_r15 import gain_fields
OUT=ROOT/'work/research_r17_review';run=ROOT/'output/research_r17/path';ev=run/'evaluation'
read=lambda p:pd.read_csv(p,float_precision='round_trip',low_memory=False)
native=read(run/'native_forecasts.csv');states=json.loads((ROOT/'output/research_r15/states.json').read_text());bands=read(ev/'underlying_core_bands.csv')
actual=read(ROOT/'tests/fixtures/cleanup/cnb_core_mm.csv').set_index('period').core;actual.index=pd.PeriodIndex(actual.index,freq='M')
lookup=native.set_index(['origin','model','h']).value_core;band_error=0.
for row in bands.itertuples():
 t=pd.Period(row.origin,'M');months=[t+h for h in range(3*row.band-2,3*row.band+1)];season=states[row.origin]['seasonal']
 for col,vals in [('predicted_sa_annualized',[lookup[(row.origin,row.model,h)] for h in range(3*row.band-2,3*row.band+1)]),('actual_sa_annualized',[actual.get(m,np.nan) for m in months])]:
  expected=12*np.mean([100*np.log1p(v/100)-season[str(m.month)] for v,m in zip(vals,months)]);saved=getattr(row,col)
  assert np.isfinite(expected)==np.isfinite(saved)
  if np.isfinite(saved):band_error=max(band_error,abs(expected-saved))
assert band_error<1e-10
blookup=bands.set_index(['origin','model','band']);turns=read(ev/'underlying_core_turns.csv');ts=read(ev/'underlying_core_turn_summary.csv');nmodels=native.model.nunique()
for row in turns.itertuples():
 calculated={}
 for label,col in [('predicted','predicted_sa_annualized'),('actual','actual_sa_annualized')]:
  a,b,c=[blookup.at[(row.origin,row.model,k),col] for k in [row.band-1,row.band,row.band+1]]
  expected=None if not np.isfinite([a,b,c]).all() else 'peak' if b-a>=.5-1e-12 and c-b<=-.5+1e-12 else 'trough' if b-a<=-.5+1e-12 and c-b>=.5-1e-12 else 'none'
  saved=getattr(row,label+'_turn');assert saved==expected or expected is None and pd.isna(saved);calculated[label]=expected
 eligible=all(v is not None for v in calculated.values());hit=eligible and calculated['actual']!='none' and calculated['actual']==calculated['predicted']
 assert row.eligible==eligible and row.exact_hit==hit
 assert row.missed_turn==(eligible and calculated['actual']!='none' and not hit)
 assert row.false_turn==(eligible and calculated['predicted']!='none' and not hit)
counts=turns[turns.eligible].groupby(['origin','band']).model.nunique();keys=set(counts[counts.eq(nmodels)].index)
common=turns[[tuple(x) in keys for x in turns[['origin','band']].to_numpy()]]
for row in ts[ts.scope.eq('all_models_common')&ts['sample'].eq('full')].itertuples():
 g=common[common.model.eq(row.model)]
 assert row.n==len(g) and row.actual_turns==g.actual_turn.ne('none').sum() and row.predicted_turns==g.predicted_turn.ne('none').sum()
 assert row.exact_band_hits==g.exact_hit.sum() and row.missed_turns==g.missed_turn.sum() and row.false_turns==g.false_turn.sum()

# Literal convention check: realised_cnb_error is actual minus CNB, not forecast error.
literal=[]
for prediction,expected in [(4.,.5),(3.,1.),(0.,2.5),(6.,-.5)]:
 f=gain_fields(prediction,5.,3.);ratio=f['model_cnb_deviation']/f['realised_cnb_error'];assert ratio==expected
 literal.append(dict(cnb=5.,actual=3.,model=prediction,capture=ratio))
pairs=read(ev/'cnb_pairs.csv');cross=read(ev/'cnb_cross_clock_matched_pairs.csv');loo=read(ev/'cnb_leave_one_report_out.csv')
assert np.max(abs((pairs.forecast-pairs.realised)-pairs.error))<1e-12
groups={};expected_omissions=set();loo_error=0.
for scope,frame in [('within_clock_common',pairs),('cross_clock_common',cross)]:
 for sample,data in [('full',frame),('reports_2024plus',frame[frame.report_date.ge('2024-01-01')])]:
  for (clock,model),g in data.groupby(['clock','model']):
   groups[(scope,sample,clock,model)]=g
   expected_omissions.update((scope,sample,clock,model,d) for d in g.report_date.unique())
assert set(map(tuple,loo[['scope','sample','clock','model','omitted_report']].to_numpy()))==expected_omissions and len(loo)==len(expected_omissions)
for row in loo.itertuples():
 g=groups[(row.scope,row.sample,row.clock,row.model)];g=g[g.report_date.ne(row.omitted_report)]
 assert row.n==len(g) and row.report_count==g.report_date.nunique() and row.unique_target_quarters==g.quarter.nunique()
 e=g.error.to_numpy();b=g.realised_cnb_error.to_numpy()
 for field,expected in [('mae',np.mean(abs(e))),('rmse',np.sqrt(np.mean(e**2))),('bias',np.mean(e)),('cnb_rmse',np.sqrt(np.mean(b**2))),('cnb_mae',np.mean(abs(b))),('rmse_gain_vs_cnb',np.sqrt(np.mean(b**2))-np.sqrt(np.mean(e**2))),('mae_gain_vs_cnb',np.mean(abs(b))-np.mean(abs(e)))]:
  assert np.isfinite(getattr(row,field))==np.isfinite(expected)
  if np.isfinite(expected):loo_error=max(loo_error,abs(getattr(row,field)-expected))
assert loo_error<1e-12
large=read(ev/'cnb_large_departure_pairs.csv');summary=read(ev/'cnb_large_departure_summary.csv');capture_error=0.
for threshold,g in large.groupby('threshold'):
 expected=pairs[pairs.model.ne('cnb')&pairs.realised_cnb_error.abs().ge(threshold)]
 assert set(map(tuple,g[['clock','report_date','quarter','model']].to_numpy()))==set(map(tuple,expected[['clock','report_date','quarter','model']].to_numpy()))
 # Recover CNB level without relying on the saved departure field's name.
 joined=g.merge(pairs[pairs.model.eq('cnb')][['clock','report_date','quarter','forecast']],on=['clock','report_date','quarter'],suffixes=('','_cnb'),validate='many_to_one')
 correct=(joined.forecast-joined.forecast_cnb)/(joined.realised-joined.forecast_cnb)
 capture_error=max(capture_error,float(abs(correct-joined.capture_ratio).max()))
for row in summary.itertuples():
 g=large[large.threshold.eq(row.threshold)&large.clock.eq(row.clock)&large.model.eq(row.model)]
 if row.sample=='reports_2024plus':g=g[g.report_date.ge('2024-01-01')]
 assert row.n==len(g) and row.reports==g.report_date.nunique()
 assert row.material_gains==g.material_gain.sum() and row.material_losses==g.material_loss.sum() and row.actual_direction_hits==g.deviation_direction_correct.sum() and row.overshoot_beyond_twice==g.capture_ratio.gt(2).sum()
 for field,expected in [('mean_abs_gain',g.abs_error_gain_vs_cnb.mean()),('median_capture',g.capture_ratio.median()),('median_relative_abs_gain',g.relative_absolute_error_gain.median())]:
  if np.isfinite(expected):capture_error=max(capture_error,abs(getattr(row,field)-expected))
assert capture_error<1e-12
boot=read(ev/'headline_paired_block_bootstrap.csv');diff=read(ev/'paired_loss_differences.csv');bd=diff[diff.metric.eq('headline_yy')&diff.scope.str.startswith('paired_fast')]
for row in boot.itertuples():
 g=bd[bd.scope.eq(row.scope)&bd.model.eq(row.model)&bd.h.eq(row.h)]
 if row.sample=='origins_2019_2021':g=g[g.origin.between('2019-01','2021-12')]
 elif row.sample=='origins_2022_2023':g=g[g.origin.between('2022-01','2023-12')]
 elif row.sample=='origins_2024plus':g=g[g.origin.ge('2024-01')]
 elif row.sample=='recent_targets':g=g[g.target.ge('2024-01')]
 g=g.sort_values('origin');ordinal=pd.PeriodIndex(g.origin,freq='M').asi8
 windows=[set(range(i,i+12)) for i in range(len(g)-11) if ordinal[i+11]-ordinal[i]==11 and len(set(ordinal[i:i+12]))==12]
 covered=set().union(*windows) if windows else set()
 status='insufficient_contiguous_support' if not windows else 'uncovered_support_origins' if len(covered)<len(g) else 'ok'
 assert row.block==12 and row.draws==2000 and row.seed==1509 and row.n==len(g) and row.eligible_blocks==len(windows) and row.n_origins_in_blocks==len(covered) and row.status==status
 if status!='ok':assert pd.isna(row.ci_low) and pd.isna(row.ci_high)
result=dict(status='pass',core_band_rows=len(bands),core_band_manual_max_error=band_error,strict_turn_rows=len(turns),strict_turn_common_keys=len(keys),strict_hit_miss_false_calls_verified=True,leave_one_report_out_rows=len(loo),leave_one_report_out_max_error=loo_error,large_CNB_departure_rows=len(large),capture_max_error=capture_error,bootstrap_calendar_support_rows=len(boot),literal_capture_fixtures=literal,reviewer_correction='The initial suspected capture sign issue was a reviewer misreading. realised_cnb_error is actual minus CNB; existing implementation is correct and no output changes were needed.')
(OUT/'diagnostics_output_review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
