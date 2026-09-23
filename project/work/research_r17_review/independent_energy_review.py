"""Independent energy arithmetic/timing review; writes review receipts only."""
from pathlib import Path
import argparse,hashlib,json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from models import energy_path_r17 as e
from models.energy_ledger import Bill,paid_bill
from energy_path_experiment_r17 import policy_scenarios
from tools.r14_fuel.prepare import load
parser=argparse.ArgumentParser();parser.add_argument('--run',default='work/research_r17_energy/smoke2');args=parser.parse_args()
OUT=ROOT/'work/research_r17_review';folder=ROOT/args.run
read=lambda p:pd.read_csv(p,float_precision='round_trip')
manifest=json.loads((folder/'manifest.json').read_text());checks={}
for p,h in manifest['inputs'].items():checks[p]=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
for p,h in manifest['outputs'].items():checks[str(folder.relative_to(ROOT)/p)]=hashlib.sha256((folder/p).read_bytes()).hexdigest()==h
assert all(checks.values()),[k for k,v in checks.items() if not v]
data=load();params=read(ROOT/'output/research_r14/fuel/parameters.csv');audit=read(ROOT/'output/research_r14/fuel/origin_audit.csv').set_index('origin')
baseline=read(ROOT/'output/research_r15/native_forecasts.csv').query("model=='STATE_FAST_R15'")
market=read(ROOT/'data/market_snapshots/20260911_bloomberg_full_refresh/daily.csv').set_index('observation_date');market.index=pd.to_datetime(market.index)
native=read(folder/'native_forecasts.csv');weekly_saved=read(folder/'weekly_paths.csv');quotes=read(folder/'quote_audit.csv')
quote_n=0;quotes_max=0.;all_clocks={}
for origin,base in baseline.groupby('origin'):
 clock=pd.Timestamp(base.as_of_utc.iloc[0]);all_clocks[origin]=clock
 local=clock.tz_convert('Europe/Prague').tz_localize(None)
 for ticker in ['FSBTY1 Index','TTFGCY1 Index','TTFGDAHD BCFV Index']:
  s=market[ticker];eligible=s[(s.index+pd.Timedelta(days=1)<=local)&np.isfinite(s)&s.gt(0)].sort_index()
  expected=float(eligible.iloc[-1]) if len(eligible) and (local.normalize()-eligible.index[-1]).days<=31 else np.nan
  actual,meta=e.quote(s,clock)
  assert np.isfinite(expected)==np.isfinite(actual)
  if np.isfinite(actual):quotes_max=max(quotes_max,abs(actual-expected))
  poisoned=s.copy();poisoned.loc[s.index+pd.Timedelta(days=1)>local]=999999.
  same,_=e.quote(poisoned,clock);assert same==actual or np.isnan(same) and np.isnan(actual)
  quote_n+=1

weekly_error=0.;monthly_error=0.;predecision_error=0.;parity_error=0.;tax_error=0.;fallback_error=0.;poison_error=0.
ref=read(ROOT/'output/research_r14/fuel/native_forecasts.csv').query("model=='FUEL_ECM_R14' and h>0")
for origin in sorted(native.origin.unique()):
 clock=all_clocks[origin];cutoff=clock.tz_convert('Europe/Prague').tz_localize(None);t=pd.Period(origin,'M');end=(t+12).end_time.normalize()
 p=params[params.origin.eq(origin)].copy();assert len(p)==2 and pd.to_datetime(p.last_training_available).le(cutoff).all()
 q=e.quote(market['FSBTY1 Index'],clock)[0];share=float(audit.loc[origin,'petrol_share'])
 paths,diag,weekly,curve=e.fuel_paths(data,origin,clock,share,p,q)
 pump=data['pump'].reindex(pd.date_range(data['pump'].index.min(),data['pump'].index.max(),freq='W-MON'))
 visible=pump.loc[pump.index+pd.Timedelta(days=7)<=cutoff].dropna(subset=[f'{k}_{prod}' for prod in ['petrol95','diesel'] for k in ['net','gross']])
 last=visible.index[-1];prior=last-pd.Timedelta(days=7);grid=pd.date_range(pump.index.min(),end,freq='W-MON')
 oil=data['oil'].brent_usd.loc[data['oil'].index+pd.Timedelta(days=14)<=cutoff]
 fx=data['fx'].usdczk.loc[data['fx'].index+pd.Timedelta(hours=14,minutes=30)<=cutoff]
 assert oil.index[-1]==pd.Timestamp(audit.loc[origin,'oil_observation_end'])
 assert fx.index[-1]==pd.Timestamp(audit.loc[origin,'fx_observation_end'])
 assert last==pd.Timestamp(audit.loc[origin,'pump_observation_end'])
 days=pd.date_range(min(oil.index.min(),fx.index.min(),grid.min()-pd.Timedelta(days=14)),end,freq='D')
 observed_oil=oil.reindex(days).ffill();daily_fx=fx.reindex(days).ffill()
 for model,endpoint in [('FUEL_SPOT_ECM_R17',float(oil.iloc[-1])),('FUEL_ANNUAL_R17',q),('FUEL_ANNUAL_LOW_R17',.8*q),('FUEL_ANNUAL_HIGH_R17',1.2*q)]:
  daily_oil=observed_oil.copy()
  if model!='FUEL_SPOT_ECM_R17' and np.isfinite(endpoint):
   for date in days[days>cutoff.normalize()]:
    fraction=(date-cutoff.normalize()).days/(end-cutoff.normalize()).days
    daily_oil.loc[date]=float(oil.iloc[-1])**(1-fraction)*endpoint**fraction
  predecision_error=max(predecision_error,float(abs(daily_oil.loc[days<=cutoff.normalize()]-observed_oil.loc[days<=cutoff.normalize()]).max()))
  dollar_cost=daily_oil*daily_fx/158.987294928
  costs=pd.Series([dollar_cost.loc[w-pd.Timedelta(days=7):w-pd.Timedelta(days=1)].mean() if len(dollar_cost.loc[w-pd.Timedelta(days=7):w-pd.Timedelta(days=1)].dropna())==7 else np.nan for w in grid],index=grid)
  predicted=visible[['gross_petrol95','gross_diesel']].rename(columns={'gross_petrol95':'petrol95','gross_diesel':'diesel'}).reindex(grid).ffill()
  for prod in ['petrol95','diesel']:
   pp=p[p['product'].eq(prod)].iloc[0];net=float(visible.loc[last,'net_'+prod]);dnet=net-float(pump.loc[prior,'net_'+prod]);prev_cost=float(costs[last]);dcost=prev_cost-float(costs[prior]);vat=float(visible.loc[last,'vat_'+prod]);wedge=float(visible.loc[last,'gross_'+prod])/(1+vat)-net
   tax_error=max(tax_error,abs(wedge-audit.loc[origin,'effective_tax_reconciliation_'+prod]),abs(vat-audit.loc[origin,'vat_'+prod]))
   for week in grid[grid>last]:
    cost=float(costs[week]);delta=cost-prev_cost
    change=float(pp.lam)*(float(pp.a)+float(pp.b)*prev_cost-net)+float(pp.beta0)*delta+float(pp.beta1)*dcost+float(pp.phi)*dnet
    net+=change;predicted.loc[week,prod]=(net+wedge)*(1+vat);dnet=change;dcost=delta;prev_cost=cost
  actual=weekly_saved.loc[weekly_saved.origin.eq(origin)&weekly_saved.model.eq(model)].set_index('week')[['petrol95','diesel']];actual.index=pd.to_datetime(actual.index)
  weekly_error=max(weekly_error,float(np.max(abs(predicted.loc[actual.index].to_numpy()-actual.to_numpy()))))
  monthly=predicted.groupby(predicted.index.to_period('M')).mean();expected=[]
  for h in range(1,13):
   relatives=monthly.loc[t+h]/monthly.loc[t+h-1]-1
   expected.append(100*(share*relatives.petrol95+(1-share)*relatives.diesel))
  monthly_error=max(monthly_error,float(np.max(abs(np.array(expected)-paths[model]))))
  export=native.query('origin==@origin and model==@model and h>0').sort_values('h').value_fuel.to_numpy();assert np.max(abs(export-paths[model]))<1e-12
 parity_error=max(parity_error,float(np.max(abs(paths['FUEL_SPOT_ECM_R17']-ref[ref.origin.eq(origin)].sort_values('h').value_fuel.to_numpy()))))
 missing=e.fuel_paths(data,origin,clock,share,p,np.nan)[0]
 for model in missing:fallback_error=max(fallback_error,float(np.max(abs(missing[model]-paths['FUEL_SPOT_ECM_R17']))))
 poisoned={k:v.copy() for k,v in data.items()}
 poisoned['oil'].loc[poisoned['oil'].index+pd.Timedelta(days=14)>cutoff,'brent_usd']=99999.
 poisoned['fx'].loc[poisoned['fx'].index+pd.Timedelta(hours=14,minutes=30)>cutoff,'usdczk']=99999.
 poisoned['pump'].loc[poisoned['pump'].index+pd.Timedelta(days=7)>cutoff,:]=99999.
 changed=e.fuel_paths(poisoned,origin,clock,share,p,q)[0]
 for model in paths:poison_error=max(poison_error,float(np.max(abs(paths[model]-changed[model]))))
 assert p.equals(params[params.origin.eq(origin)])
assert max(weekly_error,monthly_error,parity_error,tax_error,fallback_error,poison_error)<1e-10
assert predecision_error==0.

x=native.merge(baseline,on=['origin','h'],suffixes=('','_base'),validate='many_to_one')
preserve=[s for s in native if s.startswith(('value_','weight_','contribution_')) and s not in ['value_fuel','contribution_fuel']]
for col in preserve:assert np.array_equal(x[col],x[col+'_base'],equal_nan=True),col
assert np.array_equal(x.loc[x.h.eq(0),'mm_forecast'],x.loc[x.h.eq(0),'mm_forecast_base'],equal_nan=True)
assert x.as_of_utc.eq(x.as_of_utc_base).all()
future=x.h.gt(0);expected=x.mm_forecast_base+x.weight_fuel*(x.value_fuel-x.value_fuel_base)
replace_error=float(abs(x.loc[future,'mm_forecast']-expected[future]).max());assert replace_error<1e-12
forecasts=read(folder/'forecasts.csv');merged=native.merge(forecasts,on=['origin','model','h'],suffixes=('','_computed'),validate='one_to_one')
for col in ['yy_exante','cumulative_log_forecast','cumulative_log_actual']:assert np.array_equal(merged[col],merged[col+'_computed'],equal_nan=True),col
facts,eligibility,vat,bills=policy_scenarios(sorted(all_clocks),all_clocks)
assert len(facts)==34 and len(eligibility)==34*90 and not eligibility.national_candidate_eligible.any() and not bills.national_candidate_eligible.any()
facts=facts.set_index('event_id')
for row in eligibility.itertuples():
 f=facts.loc[row.event_id];clk=all_clocks[row.origin]
 legal=pd.Timestamp(f.policy_available_from)<=clk;tr=pd.to_datetime(f.cpi_application_available_from,utc=True)
 known=legal and pd.notna(tr) and tr<=clk
 assert row.legal_known==legal and row.treatment_known==known
 assert row.h_effective==pd.Period(f.effective_from,'M').ordinal-pd.Period(row.origin,'M').ordinal
assert facts.loc['POZE24_EXPIRY','effective_from']=='2024-01' and facts.loc['SAVING22_EXPIRY','effective_from']=='2023-01'
assert facts.loc['POZE26_ADOPT','policy_available_from']=='2025-12-29T23:59:59Z' and pd.isna(facts.loc['POZE26_ADOPT','effective_to_exclusive_if_known'])
bill=Bill('review','electricity',1.,100.,20.,5.,10.,.21,('commodity','distribution','fixed','levy'),'review')
normal=paid_bill(bill,'2021-11',pd.Timestamp('2021-12-10T23:59:58Z').to_pydatetime(),e.vat_events())
waived=paid_bill(bill,'2021-11',pd.Timestamp('2021-12-10T23:59:59Z').to_pydatetime(),e.vat_events())
restored=paid_bill(bill,'2022-01',pd.Timestamp('2021-12-10T23:59:59Z').to_pydatetime(),e.vat_events())
assert abs(waived/normal-1/1.21)<1e-14 and abs(restored/waived-1.21)<1e-14
for row in bills.itertuples():
 before=((3430+1500+495)*row.annual_mwh/12+row.supplier_fixed_czk)*1.21
 after=((3430-row.commodity_reset_share*240+1500)*row.annual_mwh/12+row.supplier_fixed_czk)*1.21
 assert abs(row.previous_bill_czk-before)<1e-10 and abs(row.current_bill_czk-after)<1e-10
assert e.poze_charge(1.,1.2,1,12,100,495)==24
assert e.aggregate_credit_relative(1000,200)==.8
result=dict(reviewed_run=args.run,hashes_valid=len(checks),smoke_or_full_origins=native.origin.nunique(),all_origin_quote_checks=quote_n,quote_max_error=quotes_max,future_data_poison_max_error=poison_error,independent_weekly_czk_litre_max_error=weekly_error,independent_monthly_fuel_pp_max_error=monthly_error,predecision_oil_max_error=predecision_error,R14_spot_parity_error=parity_error,tax_and_vat_reconciliation_max_error=tax_error,missing_quote_constant_spot_max_error=fallback_error,h0_untouched_components_and_clocks_exact=True,fuel_replacement_error=replace_error,native_derived_fields_match=True,policy_eligibility_rows=len(eligibility),policy_facts=len(facts),national_policy_candidate_eligible=False,illustrative_bill_rows=len(bills),review_status='pass_with_documentation_caveat_2025_capacity_rate_assumption')
(OUT/('energy_'+folder.name+'_review.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
