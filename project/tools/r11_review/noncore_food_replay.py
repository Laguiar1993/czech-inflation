"""Replay eight frozen food forecasts; write only review evidence, not model forecasts."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/review_r11/noncore'
FIX=ROOT/'tests/fixtures/cleanup'
sys.path.insert(0,str(ROOT))
import requests
def offline(*args,**kwargs):
    raise AssertionError('No network permitted')
requests.sessions.Session.request=offline
import cz_struct as s
def read(name):
    d=pd.read_csv(name,index_col=0,float_precision='round_trip')
    d.index=pd.PeriodIndex(d.index,freq='M')
    return d
bt=read(ROOT/'output/cz_struct_backtest.csv')
ff=read(FIX/'food_block_features.csv')
comp=read(FIX/'component_food_fuel_mm.csv')
reg=read(FIX/'cnb_regulated_mm.csv').iloc[:,0]
alc=read(FIX/'alcohol_tobacco.csv').iloc[:,0]
d=read(OUT/'exact_attribution_all90.csv')
focus=['2020-06','2022-02','2022-04','2022-05','2022-09','2022-10','2022-11','2024-04']
rows=[]
for ts in focus:
    t=pd.Period(ts,freq='M')
    clock=pd.Timestamp(bt.loc[t,'as_of_eve'])
    fp=s.food_forecast(comp.food,ff,t,as_of=clock)
    row=dict(period=ts,food_replayed=fp,food_reference=bt.loc[t,'food_pred_eve'],food_replay_delta=fp-bt.loc[t,'food_pred_eve'],**s.FOOD_DIAG)
    masked=s._mask_row_by_availability(ff,t,clock)
    row['unavailable_food_features']=[k for k in ff if pd.notna(ff.loc[t,k]) and pd.isna(masked.loc[t,k])]
    row['missing_food_features']=[k for k in ff if pd.isna(ff.loc[t,k])]
    row['food_features']={k:float(v) if pd.notna(v) else None for k,v in ff.loc[t].items()}
    row['admin_forecast']=bt.loc[t,'adm_pred_eve']
    row['admin_actual']=reg.loc[t]
    rh=reg[(reg.index<=t-1)&s._released_index(reg.index,clock)].dropna()
    row['admin_history_used']={str(k):float(v) for k,v in rh[rh.index.month==t.month].tail(10).items()}
    row['alc_forecast']=bt.loc[t,'alc_pred_eve']
    row['alc_actual']=alc.loc[t]
    ah=alc[(alc.index<=t-1)&s._released_index(alc.index,clock)].dropna()
    row['alc_history_same_month']={str(k):float(v) for k,v in ah[ah.index.month==t.month].items()}
    rows.append(row)
    print(ts,s.FOOD_DIAG['method'],'delta',row['food_replay_delta'],flush=True)
(OUT/'targeted_replay.json').write_text(json.dumps(rows,indent=2))
assert max(abs(r['food_replay_delta']) for r in rows)<1e-10
assert not any(r['unavailable_food_features'] for r in rows)
cols=['period','food_replayed','food_reference','food_replay_delta','method','history_end','n_obs','x13_error','admin_forecast','admin_actual','alc_forecast','alc_actual']
pd.DataFrame(rows)[cols].to_csv(OUT/'targeted_replay.csv',index=False,float_format='%.17g')
rmse=lambda x:float(np.sqrt(np.square(x).mean()))
extra={}
for name,z in [('all',d),('big',d[d.big]),('ex_oct2022',d.drop(pd.Period('2022-10'))),('four_offset_cases',d.loc[pd.PeriodIndex(['2022-02','2022-05','2022-11','2024-04'],freq='M')])]:
    extra[name]=dict(n=len(z),headline_rmse=rmse(z.headline_error),noncore_rmse=rmse(z.noncore_error),admin_rmse=rmse(z.error_admin),food_rmse=rmse(z.error_food),alcohol_rmse=rmse(z.error_alc),wedge_forecast_rms=rmse(z.wedge_forecast),wedge_error_rms=rmse(z.error_wedge),realised_reconciliation_rms=rmse(z.realised_reconciliation_first_release),forecast_without_predicted_wedge_rmse=rmse(z.headline_error-z.wedge_forecast),predicted_wedge_reduces_absolute_error_count=int(((z.headline_error-z.wedge_forecast).abs()>z.headline_error.abs()).sum()),mean_absolute_error_reduction_from_predicted_wedge=float(((z.headline_error-z.wedge_forecast).abs()-z.headline_error.abs()).mean()),core_noncore_offset_count=int(z.core_noncore_cancel.sum()),reconciliation_error_reduces_absolute_error_count=int((z.wedge_abs_error_reduction>1e-12).sum()),sum_headline_squared_error=float(np.square(z.headline_error).sum()),admin_share_of_headline_sse_covariance=float((z.error_admin*z.headline_error).sum()/np.square(z.headline_error).sum()))
(OUT/'extra_stats.json').write_text(json.dumps(extra,indent=2))
manifest=json.loads((OUT/'manifest.json').read_text())
manifest['inputs'][str(Path(__file__))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
xp=Path(s.la._X13_PATH)
manifest['x13']={'path':str(xp),'exists':xp.exists(),'sha256':hashlib.sha256(xp.read_bytes()).hexdigest() if xp.exists() else None}
manifest['targeted_food_replay_max_abs_delta']=max(abs(r['food_replay_delta']) for r in rows)
manifest['targeted_food_methods']={r['period']:r['method'] for r in rows}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(extra,indent=2))
