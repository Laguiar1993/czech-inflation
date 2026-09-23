"""Execute exact pure clock/training/weight functions extracted by AST.

Extraction avoids optional model dependencies and all live loaders/network.
This does not replay the numerical forecasting engine or its pinned environment.
"""
from pathlib import Path
import ast
import json
import os
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
REPO=next(p for p in OUT.parents if (p/'cz_struct.py').exists())
functions={'_regime','_release_calendar','_detail_release_dt','_first_release_dt',
           '_basket_available_from','_cpi_family_released_by','_released_index',
           '_eligible_edge','_availability_rule','_mask_row_by_availability',
           '_ridge_predict','solve_weights','_fuel_inputs_as_of'}
constants={'_RELEASE_HOUR','_CAL_PATH','_CAL','_FALLBACK_DETAIL_DAY',
           '_COL_AVAILABILITY_RULE','_PPI_MONTH_EXCEPTIONS','_PPI_RULE_COLS',
           '_CPI_LAG1_COLS','RIDGE_ALPHA','_ALC_TOBACCO_WEIGHT_PREANCHOR',
           '_OFFICIAL_FOOD','_OFFICIAL_FUEL','_OFFICIAL_ALC'}
tree=ast.parse((REPO/'cz_struct.py').read_text(encoding='utf-8-sig'))
keep=[]
for n in tree.body:
    if isinstance(n,ast.FunctionDef) and n.name in functions:keep.append(n)
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in constants for t in n.targets):keep.append(n)
source='from __future__ import annotations\n'+'\n'.join(ast.unparse(n) for n in keep)
cfg=ast.parse((REPO/'config.py').read_text(encoding='utf-8-sig'))
w=next(ast.literal_eval(n.value) for n in cfg.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='COMPONENT_WEIGHTS_FALLBACK' for t in n.targets))
ns={'pd':pd,'np':np,'os':os,'HERE':str(REPO),'W':w}
exec(compile(source,str(REPO/'cz_struct.py')+' [AST extracted]','exec'),ns)

def read(name):
    z=pd.read_csv(REPO/'tests/fixtures/cleanup'/name,index_col=0,float_precision='round_trip')
    z.index=pd.PeriodIndex(z.index,freq='M');return z

core=read('cnb_core_mm.csv').iloc[:,0]
x=read('core_features.csv').drop(columns=['exp12','exp36','exp12_x_state','household_exp','esi'])
y=read('target_headline_cpi_mm.csv').iloc[:,0]
comp=read('component_food_fuel_mm.csv')
reg=read('cnb_regulated_mm.csv').iloc[:,0]
alc=read('alcohol_tobacco.csv').iloc[:,0]
t=pd.Period('2024-04','M');clock=pd.Timestamp('2024-05-09 23:59')
base=ns['_ridge_predict'](x,core,t,as_of=clock)[0]
poison=core.copy();poison.loc[poison.index>=t]=999.
pbase=ns['_ridge_predict'](x,poison,t,as_of=clock)[0]
assert base==pbase
weight=ns['solve_weights'](y,comp,core,reg,t-1,as_of=clock,alc=alc)
yp=y.copy();yp.loc[yp.index>=t]=999.
cp=comp.copy();cp.loc[cp.index>=t]=999.
rp=reg.copy();rp.loc[rp.index>=t]=999.
ap=alc.copy();ap.loc[ap.index>=t]=999.
pweight=ns['solve_weights'](yp,cp,poison,rp,t-1,as_of=clock,alc=ap)
assert weight==pweight
assert not ns['_cpi_family_released_by'](pd.Period('2026-09'),pd.Timestamp('2026-10-10'))
assert not ns['_cpi_family_released_by'](pd.Period('2026-01'),pd.Timestamp('2026-02-13 08:59'))
assert ns['_cpi_family_released_by'](pd.Period('2026-01'),pd.Timestamp('2026-02-13 09:00'))
detail=ns['_detail_release_dt'](pd.Period('2026-01'))
basket=ns['_basket_available_from'](2026)
before=ns['solve_weights'](y,comp,core,reg,pd.Period('2026-01'),as_of=pd.Timestamp('2026-02-12 23:59'),alc=alc)[2026]
premature=ns['solve_weights'](y,comp,core,reg,pd.Period('2026-01'),as_of=pd.Timestamp('2026-02-13 08:00'),alc=alc)[2026]
result={'ridge_future_label_poison_unchanged':True,'weights_future_label_poison_unchanged':True,
        'unrecorded_modern_cpi_fails_closed':True,'cpi_clock_0859_false_0900_true':True,
        '2026_january_detail_release':str(detail),'2026_basket_available_from':str(basket),
        'basket_admitted_nine_hours_early':basket==detail-pd.Timedelta(hours=9),
        '2026_feb12_2359_weights':before,'2026_feb13_0800_weights':premature,
        'functions_source':'cz_struct.py AST, actual function bodies executed; no live loaders',
        'scope':'pure functions only; no pinned-runtime full forecast replay'}
print(json.dumps(result,indent=2))
(OUT/'clock_checks.json').write_text(json.dumps(result,indent=2))
