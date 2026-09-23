"""Frozen R16 slope/signal experiment; offline, no h0 changes or promotion."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import json
import numpy as np
import pandas as pd
from joblib import Parallel,delayed

import path_trend_residual_r15 as prior
from models import core_trend_residual_r15 as selection_engine
from models import core_slope_transmission_r16 as engine
from models.core_path_r13 import replace_core
from data.core_slope_transmission_r16 import signal_features_at,stage2_design,SIGNALS,FAMILIES
from core_split_experiment import publication_dates
from path_improvements_experiment_r12 import add_outcomes_and_compound,score_panel

ROOT=Path(__file__).resolve().parent
BASE=prior.BASE
CONTROLS=(*prior.CONTROLS,'STATE_FAST_R15','RF_RESIDUAL_R15')
MODELS=tuple('DAMPED_'+c.upper()+'_R16' for c in ('p80_q001','p80_q010','p95_q001','p95_q010'))+(
    'DAMPED_ADAPT_R16',)+tuple('TRANSMISSION_'+f.upper()+'_R16' for f in FAMILIES)+('BLEND_DAMPED_TRANSMISSION_R16',)
CONFIGS=('l0.1','l1','l10')
BANDS=selection_engine.BANDS


def eligible_targets(cache,origin,clock):
    t=pd.Period(origin,'M');limit=selection_engine.local_clock(clock)
    dates=cache.available_from.map(selection_engine.local_clock)
    rows=cache.loc[cache.last_target.lt(str(t)) & dates.le(limit) & cache.origin.lt(str(t))].copy()
    if rows.origin.duplicated().any():raise ValueError('Duplicate cached target origin')
    y=pd.Series(rows.actual.to_numpy(float),index=pd.PeriodIndex(rows.origin,freq='M'))
    return y,rows


def center_targets(cache,baseline):
    result=cache.copy();keys=pd.PeriodIndex(result.origin,freq='M')
    result['actual']=result.actual.to_numpy(float)-baseline.reindex(keys).to_numpy(float)
    return result[np.isfinite(result.actual)].copy()


def sequential_ridge(design,cache,clocks,origins,stage,family,band):
    histories=[];selected=[];selections=[];fits=[]
    for t in origins:
        clock=clocks[t];y,labels=eligible_targets(cache,t,clock)
        chosen=selection_engine.choose_config(pd.DataFrame(histories,columns=['origin','config','prediction']),
            labels,t,clock,CONFIGS,'l1')
        current={};diagnostics={}
        train_keys=design.index.intersection(y.dropna().index).sort_values()[-120:]
        for config in CONFIGS:
            current_available=t in design.index and (stage!='signal' or np.isfinite(design.loc[t,'level']))
            if current_available:
                prediction,info=engine.ridge_fit(design,y,design.loc[t],float(config[1:]))
            else:
                prediction,info=np.nan,dict(status='unavailable_current_signal' if stage=='signal' else 'unavailable_generated_forecast',n_train=len(train_keys),converged=False)
            current[config]=prediction;diagnostics[config]=info
        config=chosen['config'];info=diagnostics[config]
        metadata=dict(origin=str(t),stage=stage,family=family,band=band)
        selected.append(dict(**metadata,signal=family,config=config,predicted_change=current[config],
                             status=info['status'],as_of=str(clock)))
        selections.append(dict(**metadata,**chosen))
        fits.append(dict(**metadata,config=config,**info,training_origins=[str(k) for k in train_keys],
                         last_training_target=str(labels[labels.origin.isin(train_keys.astype(str))].last_target.max()) if len(train_keys) else None))
        histories.extend(dict(origin=str(t),config=c,prediction=v,status=diagnostics[c]['status'],
            n_train=diagnostics[c]['n_train']) for c,v in current.items())
    return pd.DataFrame(selected),selections,fits,pd.DataFrame(histories).assign(stage=stage,family=family,band=band)


def build_band(b,data):
    band=BANDS[b];end=data['outer'].max();clock=data['clocks'][end]
    projections=[];selections=[];fits=[];candidates=[];labels=[];designs=[];predictions=[]
    for signal in SIGNALS:
        _,cache=engine.released_band_means(data['broad_log'][signal],data['broad_available'],
            data['signal_origins'],end,clock,band)
        design=data['signal_design'][signal]
        cache=center_targets(cache,design.level)
        result,sel,fit,cand=sequential_ridge(design,cache,data['clocks'],data['signal_origins'],'signal',signal,b)
        result['current_z']=design.level.reindex(pd.PeriodIndex(result.origin,freq='M')).to_numpy()
        result['projected_z']=result.current_z+result.predicted_change
        projections.append(result);selections+=sel;fits+=fit;candidates.append(cand)
        labels.append(cache.assign(stage='signal',family=signal,band=b))
    projections=pd.concat(projections,ignore_index=True)
    _,cache=engine.released_band_means(data['core_log'],data['available'],data['states'],end,clock,band)
    baseline=pd.Series({t:np.mean([state['forecasts_log']['fast'][str(h)] for h in range(band[0],band[1]+1)])
                        for t,state in data['states'].items()})
    cache=center_targets(cache,baseline)
    acceleration=pd.Series({t:s['x']['core_acceleration'] for t,s in data['states'].items()})
    for family in FAMILIES:
        design=stage2_design(projections,acceleration,b,family)
        designs.append(design.rename_axis('origin').reset_index().assign(family=family,band=b))
        result,sel,fit,cand=sequential_ridge(design,cache,data['clocks'],list(data['states']),'core',family,b)
        selections+=sel;fits+=fit;candidates.append(cand)
        labels.append(cache.assign(stage='core',family=family,band=b))
        for row in result[result.origin.isin(data['outer'].astype(str))].itertuples():
            t=pd.Period(row.origin,'M');state=data['states'][t]
            for h in range(band[0],band[1]+1):
                value=state['forecasts_log']['fast'][str(h)]+row.predicted_change
                predictions.append(dict(origin=str(t),h=h,model='TRANSMISSION_'+family.upper()+'_R16',core_log=value,core_mm=100*np.expm1(value/100)))
    print('R16 completed signal/core band',b+1,flush=True)
    return pd.DataFrame(predictions),projections,selections,fits,pd.concat(candidates,ignore_index=True),pd.concat(labels,ignore_index=True),pd.concat(designs,ignore_index=True)


def slope_paths(data):
    states={};paths={};predictions=[];selections=[]
    for t,reference in data['states'].items():
        known=data['core_log'].loc[:t-1]
        release=data['available'].reindex(known.index)
        if release.isna().any() or (release>selection_engine.local_clock(data['clocks'][t])).any():raise ValueError('Unreleased core in slope state')
        seasonal={int(k):v for k,v in reference['seasonal'].items()}
        adjusted=known-np.array([seasonal[m.month] for m in known.index])
        state=engine.slope_state(adjusted,t,seasonal)
        if state is None:raise ValueError('R15 state exists but R16 slope unavailable')
        states[t]=state;paths[t]=state['forecasts_log']
    for t in data['outer']:
        chosen=engine.choose_slope(paths,data['core_log'],data['available'],t,data['clocks'][t])
        selections.append(dict(origin=str(t),stage='slope',family='whole_path',band='all',**chosen))
        for h in range(1,13):
            values={f'DAMPED_{c.upper()}_R16':p[h] for c,p in paths[t].items()}
            values['DAMPED_ADAPT_R16']=paths[t][chosen['config']][h]
            predictions.extend(dict(origin=str(t),h=h,model=m,core_log=v,core_mm=100*np.expm1(v/100)) for m,v in values.items())
    return pd.DataFrame(predictions),states,selections


def attach_components(core_predictions,baseline,origins):
    rows=[]
    for t in origins:
        control=baseline[baseline.origin.eq(str(t)) & baseline.model.eq(BASE)].copy()
        if len(control)!=13:raise ValueError('Thirteen baseline horizons required')
        for model in MODELS:
            pred=core_predictions[core_predictions.origin.eq(str(t)) & core_predictions.model.eq(model)]
            changed=replace_core(control,pred.set_index('h').core_mm.reindex(range(1,13)).to_dict())
            protected=[c for c in control if c.startswith('weight_') or c.startswith('value_') and c!='value_core'
                       or c.startswith('contribution_') and c!='contribution_core']
            pd.testing.assert_frame_equal(control[protected],changed[protected],check_exact=True)
            assert control.loc[control.h.eq(0),'mm_forecast'].equals(changed.loc[changed.h.eq(0),'mm_forecast'])
            changed['model']=model;changed['yy_exante']=np.nan;changed['yy_conditional']=np.nan
            changed['status']=np.where(np.isfinite(changed.mm_forecast),'research_estimated','unavailable_component')
            changed['converged']=np.isfinite(changed.mm_forecast)
            rows.append(changed)
    return pd.concat(rows,ignore_index=True)


def load_inputs(limit=None):
    archive=ROOT/'output/research_r15';manifest=json.loads((archive/'manifest.json').read_text())
    hashes={}
    for name,digest in manifest['inputs'].items():
        if prior.sha(ROOT/name)!=digest:raise ValueError('R15 input changed: '+name)
        hashes[name]=digest
    for name,digest in manifest['outputs'].items():
        path=archive/name
        if prior.sha(path)!=digest:raise ValueError('R15 output changed: '+name)
        hashes[path.relative_to(ROOT).as_posix()]=digest
    data=prior.load_inputs();outer=data['h0'].index
    if limit:outer=outer[:limit]
    data['outer']=outer;end=outer.max()
    states=json.loads((archive/'states.json').read_text())
    data['states']={pd.Period(k,'M'):s for k,s in states.items() if pd.Period(k,'M')<=end}
    data['core_log']=100*np.log1p(data['core']/100)
    data['broad_log']=100*np.log1p(data['broad']/100)
    data['broad_available']=publication_dates(data['broad'].index)
    from tools.paper_replication import build_paper_panel as builder
    panel_clocks=builder.release_eves(builder.CALENDAR,data['panel'].index)
    signal_origins=pd.period_range('2006-01',end,freq='M');design={s:{} for s in SIGNALS};clocks={};clock_rows=[]
    first_state=min(data['states'])
    for t in signal_origins:
        pclock=panel_clocks[t-1]
        clock=pclock if t<first_state else pd.Timestamp(data['states'][t]['as_of'])
        if selection_engine.local_clock(pclock)>selection_engine.local_clock(clock):raise ValueError('Panel newer than decision clock')
        clocks[t]=clock
        rows=signal_features_at(data['panel'],data['broad'],data['features'].eurczk_mm,data['broad_available'],t,clock)
        for s in SIGNALS:design[s][t]=rows[s]
        clock_rows.append(dict(origin=str(t),as_of=str(clock),panel_edge=str(t-1),panel_cutoff=str(pclock),
                               rule='A6_warmup_clock' if t<pd.Period('2010-01','M') else 'frozen_R15_clock'))
    data['signal_origins']=signal_origins;data['clocks']=clocks
    data['signal_design']={s:pd.DataFrame.from_dict(v,orient='index') for s,v in design.items()}
    for frame in data['signal_design'].values():frame.index=pd.PeriodIndex(frame.index,freq='M')
    data['clock_ledger']=pd.DataFrame(clock_rows);data['hashes']=hashes
    data['frozen_controls']=pd.read_csv(archive/'forecasts.csv',float_precision='round_trip').query('model in @CONTROLS')
    return data


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--jobs',type=int,default=4);parser.add_argument('--limit-origins',type=int)
    args=parser.parse_args(argv)
    if args.limit_origins is not None and args.limit_origins<1:parser.error('Positive origin limit required')
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    data=load_inputs(args.limit_origins)
    files=['path_slope_transmission_r16.py','data/core_slope_transmission_r16.py','models/core_slope_transmission_r16.py',
           'docs/implementation/R16_SLOPE_TRANSMISSION_SPEC_2026-09-14.md','output/research_r15/manifest.json']
    hashes=data['hashes']|{p:prior.sha(ROOT/p) for p in files}
    prior.dump(out/'declaration.json',dict(started_at=datetime.now(timezone.utc).isoformat(),inputs=hashes,models=MODELS,controls=CONTROLS))
    data['clock_ledger'].to_csv(out/'clocks.csv',index=False)
    for signal,frame in data['signal_design'].items():frame.to_csv(out/f'signal_features_{signal}.csv',index_label='origin')
    prior.dump(out/'states.json',{str(t):s for t,s in data['states'].items()})
    parts=Parallel(n_jobs=args.jobs)(delayed(build_band)(b,data) for b in range(4))
    slope,slope_states,slope_selections=slope_paths(data)
    predictions=pd.concat([slope,*[p[0] for p in parts]],ignore_index=True)
    blend=predictions[predictions.model.isin(['DAMPED_ADAPT_R16','TRANSMISSION_BOTH_R16'])].pivot(index=['origin','h'],columns='model',values='core_log')
    blend['core_log']=(blend.DAMPED_ADAPT_R16+blend.TRANSMISSION_BOTH_R16)/2
    blend['core_mm']=100*np.expm1(blend.core_log/100);blend['model']='BLEND_DAMPED_TRANSMISSION_R16'
    predictions=pd.concat([predictions,blend.reset_index()[['origin','h','model','core_log','core_mm']]],ignore_index=True)
    predictions.to_csv(out/'core_predictions.csv',index=False)
    prior.dump(out/'slope_states.json',{str(t):s for t,s in slope_states.items()})
    prior.dump(out/'selections.json',slope_selections+[s for p in parts for s in p[2]])
    prior.dump(out/'fits.json',[s for p in parts for s in p[3]])
    for name,n in [('signal_projections',1),('sequential_candidates',4),('labels',5),('stage2_features',6)]:
        pd.concat([p[n] for p in parts],ignore_index=True).to_csv(out/(name+'.csv'),index=False)
    native=attach_components(predictions,data['base'],data['outer']);native.to_csv(out/'native_forecasts.csv',index=False)
    controls=data['frozen_controls'][data['frozen_controls'].origin.isin(data['outer'].astype(str))]
    columns=['origin','h','target','as_of_utc','model','mm_forecast']
    forecasts,delta=add_outcomes_and_compound(pd.concat([native[columns],controls[columns]],ignore_index=True),data['headline'],controls[controls.model.eq('INDEPENDENT_BRIDGE')])
    check=forecasts[forecasts.model.isin(CONTROLS)].merge(controls,on=['origin','h','model'],suffixes=('','_frozen'),validate='one_to_one')
    for col in ('mm_forecast','yy_exante','mm_actual','yy_actual'):
        if not np.allclose(check[col],check[col+'_frozen'],atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Control drift')
    forecasts.to_csv(out/'forecasts.csv',index=False)
    score_panel(forecasts,[*CONTROLS,*MODELS],'primary_common').to_csv(out/'summary.csv',index=False)
    for p,digest in hashes.items():
        if prior.sha(ROOT/p)!=digest:raise ValueError('Input changed during R16: '+p)
    prior.dump(out/'manifest.json',dict(completed_at=datetime.now(timezone.utc).isoformat(),inputs=hashes,
        origin_count=len(data['outer']),models=MODELS,controls=CONTROLS,target_reconciliation_max=delta,
        packages={p:prior.importlib.metadata.version(p) for p in ('numpy','pandas','scikit-learn','scipy')},
        outputs={p.name:prior.sha(p) for p in out.iterdir() if p.suffix in ('.csv','.json') and p.name!='manifest.json'}))
    print('R16 completed:',out,flush=True)


if __name__=='__main__':main()
