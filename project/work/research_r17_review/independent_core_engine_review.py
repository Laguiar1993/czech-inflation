from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from models.core_adaptation_r17 import filter_state,condition_h0,h0_coefficient,fast_state
from models.core_slope_transmission_r16 import slope_state
OUT=ROOT/'work/research_r17_review'
dates=pd.period_range('2000-01',periods=120,freq='M'); origin=dates[-1]+1
raw=pd.Series(.8+np.sin(np.arange(120)/3)*1.1,index=dates);raw.iloc[61:64]=[8.,10.,12.]
seasonal={m:(m-6.5)/20 for m in range(1,13)}
adjusted=100*np.log1p(raw/100)-[seasonal[m.month] for m in raw.index]
fixed=filter_state(adjusted,origin,seasonal,'fixed')
r16=slope_state(adjusted,origin,seasonal)
fixed_error=max(abs(fixed['path'][h]-r16['forecasts_log']['p95_q001'][h]) for h in range(1,13))
assert fixed_error<1e-12
probes={}
for mode in ['fixed','robust','news']:
 state=filter_state(adjusted,origin,seasonal,mode)
 F=np.array([[1.,.95,0],[0,.95,0],[0,0,.8]]); H=np.array([1.,0.,1.]); mean=np.array(state['mean'])
 expected={h:float(H@np.linalg.matrix_power(F,h+1)@mean+seasonal[(origin+h).month]) for h in range(1,13)}
 transition_error=max(abs(expected[h]-state['path'][h]) for h in expected);assert transition_error<1e-12
 p=np.array(state['covariance']);p0=F@p@F.T+np.array(state['process']);w=p0@H/(H@p0@H)
 delta=.7
 conditional=condition_h0(state,delta)
 conditional_expected={h:state['path'][h]+float(H@np.linalg.matrix_power(F,h)@w*delta) for h in range(1,13)}
 conditional_error=max(abs(conditional[h]-conditional_expected[h]) for h in expected);assert conditional_error<1e-12
 trace=state['trace']; errors=[]
 for row in trace:
  x=np.array(errors[-36:] if len(errors)>=12 else adjusted.iloc[:12])
  expected_scale=max(.05,1.4826*np.median(abs(x-np.median(x))))
  assert abs(row['prior_scale']-expected_scale)<1e-12
  assert abs(row['z']-row['innovation']/expected_scale)<1e-12
  errors.append(row['innovation'])
 earlier=filter_state(adjusted.iloc[:100],dates[99]+1,seasonal,mode)
 assert trace[:88]==earlier['trace']
 probes[mode]={'transition_h1_two_steps_max_error':transition_error,'conditional_h0_mapping_max_error':conditional_error,'normalization':float(H@w),'trace_prior_scale_verified':len(trace),'prefix_trace_invariance':True}
dates2=pd.period_range('2016-01',periods=80,freq='M')
rows=pd.DataFrame(dict(origin=dates2.astype(str),signal=np.cos(np.arange(80)/9),error=.8*np.cos(np.arange(80)/9)+.1,available_from=[str((m+1).start_time+pd.Timedelta(days=15,hours=9)) for m in dates2]))
target=pd.Period('2022-03');clock=pd.Timestamp('2022-03-10 12:00')
beta,meta=h0_coefficient(rows,target,clock)
eligible=rows[(rows.origin<str(target))&(pd.to_datetime(rows.available_from)<=clock)].tail(60)
expected_beta=np.clip((eligible.signal@eligible.error)/(eligible.signal@eligible.signal)*len(eligible)/(len(eligible)+24),0,1)
assert beta==float(expected_beta);assert meta['training_origins']==eligible.origin.tolist()
poison=rows.copy();late=(poison.origin>=str(target))|(pd.to_datetime(poison.available_from)>clock);poison.loc[late,['signal','error']]=1000000
assert h0_coefficient(poison,target,clock)==(beta,meta)
result={'fixed_r16_transformed_nonzero_seasonal_max_error':fixed_error,'filter_probes':probes,'h0_beta_independent':beta,'h0_n':meta['n_train'],'h0_selected_origins_exact':True,'h0_future_unreleased_poison_invariance':True}
(OUT/'core_engine_review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))

