"""Recompose frozen R17 components and chronologically select entire paths."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import r17_common as c
from models import path_components_r17 as e

ROOT=c.ROOT
CONTROLS=('INDEPENDENT_BRIDGE','STABLE_PIPELINE_R14B','STABLE_LOCAL_CORE_R14B',c.FAST,
          'RF_RESIDUAL_R15','DAMPED_P95_Q001_R16')
CHILDREN=('research_r17_core','research_r17_food','research_r17_monthly','research_r17_energy')
CORE_PAIR=('CORE_NEWS_H0_R17','MONTHLY_BOTH_CORE_R17')


def load():
    hashes=c.preserved_hashes();parts=[]
    for child in CHILDREN:
        folder=ROOT/'output'/child;manifest=json.loads((folder/'manifest.json').read_text())
        for name,digest in manifest['inputs'].items():
            if c.sha(ROOT/name)!=digest:raise ValueError('Child input changed '+name)
            hashes[name]=digest
        for name,digest in manifest['outputs'].items():
            p=folder/name
            if c.sha(p)!=digest:raise ValueError('Child output changed '+str(p))
            hashes[p.relative_to(ROOT).as_posix()]=digest
        native=c.read('output/'+child+'/native_forecasts.csv')
        # Endpoint stress scenarios are sensitivities, never model-selection candidates.
        parts.append(native[~native.model.isin(['FUEL_ANNUAL_LOW_R17','FUEL_ANNUAL_HIGH_R17'])])
    for filename,names in [('output/research_r14b/integration/native_forecasts.csv',CONTROLS[:3]),
                            ('output/research_r15/native_forecasts.csv',CONTROLS[3:5]),
                            ('output/research_r16/native_forecasts.csv',CONTROLS[5:])]:
        frame=c.read(filename);parts.append(frame[frame.model.isin(names)])
    native=pd.concat(parts,ignore_index=True)
    if native.duplicated(['origin','h','model']).any():raise ValueError('Duplicate integration keys')
    return native,hashes


def fixed_combinations(native):
    get=lambda model:native[native.model.eq(model)].sort_values(['origin','h']).reset_index(drop=True)
    fast=get(c.FAST)
    core=e.blend_native([get(m) for m in CORE_PAIR],[.5,.5],'COMBO_CORE_R17')
    # Each single-block candidate contains FAST's other components. Adding its
    # incremental monthly contribution replaces that component exactly once.
    merged=[]
    for name,parent in [('COMBO_FOOD_FUEL_R17',fast),('COMBO_ALL_R17',core)]:
        out=parent.copy()
        for block,model in [('food','FOOD_SYMMETRIC_R17'),('fuel','FUEL_ANNUAL_R17')]:
            candidate=get(model);future=out.h.gt(0)
            out.loc[future,'mm_forecast']+=candidate.loc[future,'contribution_'+block].to_numpy()-out.loc[future,'contribution_'+block].to_numpy()
            for col in ('value_'+block,'contribution_'+block):out.loc[future,col]=candidate.loc[future,col].to_numpy()
        out['model']=name;merged.append(out)
    all_path=merged[-1]
    half=e.blend_native([fast,all_path],[.5,.5],'PATH_COMPONENT_HALF_R17')
    currenthalf=e.blend_native([fast,get('STABLE_LOCAL_CORE_R14B')],[.5,.5],'PATH_FAST_CURRENT_HALF_R17')
    return pd.concat([core,*merged,half,currenthalf],ignore_index=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'output/research_r17/path')
    args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    native,hashes=load()
    for name in ('path_component_experiment_r17.py','models/path_components_r17.py','docs/implementation/R17_COMBINATION_SPEC_2026-09-14.md'):
        hashes[name]=c.sha(ROOT/name)
    c.dump(out/'declaration.json',dict(inputs=hashes,controls=CONTROLS,selection='fullymaturedwholeheadlinepath',pool_grid=e.pool_grid()))
    native=pd.concat([native,fixed_combinations(native)],ignore_index=True)
    get=lambda m:native[native.model.eq(m)]
    definitions={'component':{'ALPHA_0':(1.,0.),'ALPHA_25':(.75,.25),'ALPHA_50':(.5,.5)},'pool':e.pool_grid()}
    sources={'component':[get(c.FAST),get('COMBO_ALL_R17')],
             'pool':[get(c.FAST),get('STABLE_LOCAL_CORE_R14B'),get('DAMPED_P95_Q001_R16'),get('COMBO_ALL_R17')]}
    candidates=[];candidate_native=[];selected=[];selections=[]
    headline=c.monthly('output/independent_path_frozen_inputs.csv','headline_mm');available=c.publication_dates(headline.index)
    clocks=get(c.FAST).drop_duplicates('origin').set_index('origin').as_of_utc
    for family,configs in definitions.items():
        parts=[e.blend_native(sources[family],weights,name) for name,weights in configs.items()]
        cn=pd.concat(parts,ignore_index=True);cf=c.compound(cn)
        candidate_native.append(cn.assign(family=family));candidates.append(cf.assign(family=family))
        default=next(iter(configs))
        for origin,clock in clocks.sort_index().items():
            chosen,meta=e.choose_path(cf,available,origin,clock,configs,default)
            rows=cn[cn.origin.eq(origin)&cn.model.eq(chosen)].copy()
            rows['model']='PATH_COMPONENT_SELECT_R17' if family=='component' else 'PATH_POOL_R17'
            selected.append(rows);selections.append(dict(origin=origin,as_of=str(clock),family=family,chosen=chosen,**meta))
    native=pd.concat([native,*selected],ignore_index=True);forecasts=c.compound(native)
    preserved=c.read('output/research_r16/forecasts.csv');preserved=preserved[preserved.model.isin(CONTROLS)]
    keys=['origin','h','model'];check=forecasts[forecasts.model.isin(CONTROLS)].merge(preserved,on=keys,validate='one_to_one',suffixes=('','_old'))
    for col in ('mm_forecast','yy_exante','mm_actual','yy_actual','cumulative_log_forecast'):
        if not np.allclose(check[col],check[col+'_old'],atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Control drift '+col)
    forecasts=pd.concat([forecasts[~forecasts.model.isin(CONTROLS)],preserved],ignore_index=True)
    derived=['yy_exante','cumulative_log_forecast','cumulative_log_actual']
    native=native.drop(columns=derived).merge(forecasts[keys+derived],on=keys,validate='one_to_one')
    # Conditional forecasts are not part of this independent product.
    native.loc[native.h.gt(0),'yy_conditional']=np.nan
    for name,frame in [('forecasts',forecasts),('native_forecasts',native),('selection_candidate_forecasts',pd.concat(candidates)),
                       ('selection_candidate_native',pd.concat(candidate_native))]:frame.to_csv(out/(name+'.csv'),index=False)
    c.dump(out/'selections.json',selections)
    c.finish(out,hashes,controls=CONTROLS,models=sorted(set(forecasts.model)-set(CONTROLS)),origin_count=forecasts.origin.nunique())
    print('Completed',out,'models',forecasts.model.nunique(),flush=True)


if __name__=='__main__':main()
