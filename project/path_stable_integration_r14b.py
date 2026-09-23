"""Frozen R14B exploratory stable combinations and professional benchmarks."""
import argparse
from contextlib import ExitStack
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np
import pandas as pd

from path_integration_r14 import combine_components,bootstrap
from path_improvements_experiment_r12 import read,sha,dump,score_panel,add_outcomes_and_compound
from independent_bridge_experiment import match_cnb_quarters,_quarter_metrics

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/research_r14b/integration'
BASE='INDEPENDENT_BRIDGE'
PRIMARY=('STABLE_PIPELINE_R14B','STABLE_LOCAL_CORE_R14B','STABLE_LONG_CORE_R14B','STABLE_LONG_GAP_R14B')


def dependencies():
    names=['path_stable_integration_r14b.py','path_integration_r14.py','test_path_integration_r14.py',
      'path_improvements_experiment_r12.py','independent_bridge_experiment.py','models/path_inputs.py',
      'docs/implementation/R14B_COMBINATIONS.md','docs/implementation/R14B_CORE_HISTORY_DESIGN.md',
      'data/cnb_mpr_cpi_quarterly.csv','output/independent_bridge_forecasts.csv','output/independent_path_frozen_inputs.csv']
    for folder in ('research_r14/core','research_r14/fuel','research_r14b/food','research_r14b/core'):
        meta=ROOT/'output'/folder/'manifest.json';manifest=json.loads(meta.read_text())
        for name,digest in manifest.get('outputs',manifest.get('output_hashes',{})).items():
            file=meta.parent/name
            if not file.is_file():file=ROOT/name
            if sha(file)!=digest:raise AssertionError('Changed frozen component: '+str(file))
        names.extend([meta.relative_to(ROOT).as_posix(),f'output/{folder}/native_forecasts.csv'])
    return {n:sha(ROOT/n) for n in names}


def generate(folder=OUT):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);inputs=dependencies()
    def load(name):return pd.read_csv(ROOT/name,float_precision='round_trip')
    base=load('output/independent_bridge_forecasts.csv')
    oldcore=load('output/research_r14/core/native_forecasts.csv')
    newcore=load('output/research_r14b/core/native_forecasts.csv')
    food=load('output/research_r14b/food/native_forecasts.csv');food=food[food.model.eq('FOOD_STABLE_PIPELINE_R14B')]
    fuel=load('output/research_r14/fuel/native_forecasts.csv');fuel=fuel[fuel.model.eq('FUEL_CONSTANT_PUMP_R14')]
    shortlocal=oldcore[oldcore.model.eq('CORE_LOCAL_R14')].sort_values(['origin','h'])
    longlocal=newcore[newcore.model.eq('CORE_LOCAL_R14')].sort_values(['origin','h'])
    if not np.array_equal(shortlocal.mm_forecast.to_numpy(),longlocal.mm_forecast.to_numpy(),equal_nan=True):
        raise AssertionError('Core local control changed under historical import extension')
    choices={PRIMARY[0]:None,PRIMARY[1]:shortlocal,
             PRIMARY[2]:newcore[newcore.model.eq('CORE_LEVEL_RIDGE_R14')],
             PRIMARY[3]:newcore[newcore.model.eq('CORE_GAP_RIDGE_R14')]}
    native=pd.concat([combine_components(base,food,fuel,c,name) for name,c in choices.items()],ignore_index=True)
    native.to_csv(folder/'component_predictions.csv',index=False)
    headline=read(ROOT/'output/independent_path_frozen_inputs.csv').headline_mm.dropna()
    native,_=add_outcomes_and_compound(pd.concat([base,native],ignore_index=True),headline,base)
    native.to_csv(folder/'native_forecasts.csv',index=False)
    # Extended recipe labels describe the different data policy in this joint table.
    newcore=newcore.copy();newcore['model']=newcore.model.str.replace('_R14','_EXT_R14B',regex=False)
    controls=pd.concat([food,fuel,shortlocal,newcore],ignore_index=True)
    keep=['origin','h','target','as_of_utc','model','mm_forecast']
    frame,delta=add_outcomes_and_compound(pd.concat([native[keep],controls[keep]],ignore_index=True),headline,base)
    if frame.duplicated(['origin','model','h']).any():raise AssertionError('Duplicate model keys')
    frame.to_csv(folder/'forecasts.csv',index=False)
    models=[BASE]+sorted(set(frame.model)-{BASE});scores=[score_panel(frame,[BASE,*PRIMARY],'combined_common')]
    for m in models:
        scores.append(score_panel(frame,[m],'own_coverage'))
        if m!=BASE:scores.append(score_panel(frame,[BASE,m],f'paired_{m}'))
    summary=pd.concat(scores,ignore_index=True);summary.to_csv(folder/'summary.csv',index=False)
    bootstrap(frame,models).to_csv(folder/'paired_uncertainty.csv',index=False)
    quarters=match_cnb_quarters(frame,pd.read_csv(ROOT/'data/cnb_mpr_cpi_quarterly.csv'),headline,models)
    quarters.to_csv(folder/'cnb_quarters.csv',index=False);cnb=[]
    for sample,g in [('all_reports',quarters),('recent_reports',quarters[quarters.report_date>='2024-01-01'])]:
        cnb.append(_quarter_metrics(g,[BASE,*PRIMARY,'CNB'],'combined_common',sample))
        for m in models:cnb.append(_quarter_metrics(g,list(dict.fromkeys([BASE,m,'CNB'])),f'paired_{m}',sample))
    pd.concat(cnb,ignore_index=True).to_csv(folder/'cnb_summary.csv',index=False)
    frame[frame.origin.eq(frame.origin.max())].to_csv(folder/'latest_archived_paths.csv',index=False)
    frame.groupby(['model','h']).agg(n_intended=('origin','size'),n_forecast=('yy_exante','count'),n_actual=('yy_actual','count')).reset_index().to_csv(folder/'coverage.csv',index=False)
    dump(folder/'validation.json',dict(unique_model_keys=True,n_origins=frame.origin.nunique(),n_models=len(models),
       target_difference=delta,local_control_identical=True,history_policy='84 missing historical import values, all original cells unchanged',
       interpretation='Exploratory follow-up motivated by R14 outcomes; no new untouched holdout'))
    if inputs!=dependencies():raise AssertionError('Inputs changed during stable integration')
    outputs={p.name:sha(p) for p in sorted(folder.iterdir()) if p.suffix in ('.csv','.json') and p.name not in ('manifest.json','verification_receipt.json')}
    manifest=dict(inputs=inputs,outputs=outputs,created_at=datetime.now(timezone.utc).isoformat(),declarations=['a3740fe','709d4b3'])
    dump(folder/'manifest.json',manifest)
    print(summary.loc[summary.scope.eq('combined_common')&summary.h.isin([6,12]),['sample','h','model','n_common','yy_rmse','yy_bias']].to_string(index=False),flush=True)
    return manifest


def verify():
    frozen=json.loads((OUT/'manifest.json').read_text())
    if dependencies()!=frozen['inputs']:raise AssertionError('Stable integration dependency changed')
    with tempfile.TemporaryDirectory(prefix='r14b_integration_') as tmp,ExitStack() as stack:
        for name in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(name,side_effect=AssertionError('Offline stable integration attempted network')))
        replay=generate(Path(tmp))
        if replay['outputs']!=frozen['outputs']:raise AssertionError('Stable integration replay mismatch')
    for name,digest in frozen['outputs'].items():
        if sha(OUT/name)!=digest:raise AssertionError('Saved integration payload changed')
    dump(OUT/'verification_receipt.json',dict(status='passed',payloads=len(frozen['outputs']),checked_at=datetime.now(timezone.utc).isoformat()))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify',action='store_true');a=p.parse_args();verify() if a.verify else generate()
