"""R15 frozen independent core trend/residual experiment. No downloads or promotion."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from joblib import Parallel,delayed

from models import core_trend_residual_r15 as engine
from data.core_trend_residual_r15 import features_at,feature_groups,HARD_ROWS
from core_split_experiment import publication_dates
from path_experiment import _eve
from data.core_split import load_frozen
from models.core_path_r13 import replace_core
from path_improvements_experiment_r12 import add_outcomes_and_compound,score_panel

ROOT=Path(__file__).resolve().parent
BASE='STABLE_PIPELINE_R14B'
CONTROLS=('INDEPENDENT_BRIDGE',BASE,'STABLE_LOCAL_CORE_R14B')
MODELS=('STATE_SLOW_R15','STATE_MID_R15','STATE_FAST_R15','STATE_ADAPT_R15',
        'ENET_DOMESTIC_R15','ENET_IMPORTED_R15','ENET_BOTH_R15','ENET_WIDE_R15',
        'RF_RESIDUAL_R15','BLEND_LINEAR_RF_R15','BLEND_WIDE_STATE_R15')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2,default=str)+'\n',encoding='utf-8')


def read_monthly(path):
    d=pd.read_csv(path,index_col=0,float_precision='round_trip')
    d.index=pd.PeriodIndex(d.index,freq='M')
    if not d.index.is_unique:raise ValueError('Duplicate monthly input')
    return d.sort_index()


def load_inputs():
    from tools.paper_replication import build_paper_panel as builder
    files=['tests/fixtures/cleanup/cnb_core_mm.csv','tests/fixtures/cleanup/core_features.csv',
           'data/core_split/broad_yoy.csv','data/core_split/manifest.json',
           'data/release_calendar_cz_cpi.csv','output/independent_nowcast_forecasts.csv',
           'output/independent_path_frozen_inputs.csv','output/research_r14b/integration/native_forecasts.csv',
           'data/paper_replication/paper_model_panel_20260912_luci/realtime_panel.csv',
           'data/paper_replication/paper_model_panel_20260912_luci/manifest.json',
           'data/paper_replication/a6_inputs_20260912/exact_inputs_long.csv',
           'data/paper_replication/a6_inputs_20260912/candidate_inputs_long.csv']
    hashes={p:sha(ROOT/p) for p in files}
    core=read_monthly(ROOT/files[0]).iloc[:,0]
    features=read_monthly(ROOT/files[1]);broad=load_frozen()['broad_yoy']
    panel_meta=json.loads((ROOT/files[9]).read_text())
    ulc_meta=panel_meta['realtime_convention']['rows']['17']
    if ulc_meta['source']!='bbg__nominal_ulc_quarterly__as_reported' or ulc_meta['transform']!='T0':
        raise ValueError('R15 ULC expects the frozen quarterly NSA per-person index level, not the exact-panel annual rate')
    panel=read_monthly(ROOT/files[8]);raws=builder.load_raw()
    eves=builder.release_eves(builder.CALENDAR,panel.index)
    future_audit=[]
    for n in (65,66):
        raw=raws[n];levels=builder.monthly_levels(raw)
        values,policy=builder.transform(levels,builder.BY_NUMBER[n].transform,number=n)
        aligned=builder._latest_available(values,raw.available,eves)
        panel[f'a6_{n:02}']=aligned
        for edge,cutoff in eves.items():
            eligible=raw.available[raw.available<=cutoff]
            source=eligible.index.max() if len(eligible) else None
            future_audit.append(dict(edge=str(edge),row=n,value=aligned.get(edge,np.nan),
                source_period=str(source),available_from=str(raw.available.get(source,pd.NaT)),
                cutoff=str(cutoff),source=raw.source,transform=policy,extra_shift_months=0))
    available=publication_dates(core.index)
    h0=read_monthly(ROOT/files[5]);clocks=pd.Series({t:_eve(t) for t in core.index})
    for t,row in h0.iterrows():clocks.loc[t]=pd.Timestamp(row.as_of_eve)
    base=pd.read_csv(ROOT/files[7],float_precision='round_trip')
    if base.duplicated(['origin','h','model']).any():raise ValueError('Duplicate baseline keys')
    if base.groupby('origin').as_of_utc.nunique().ne(1).any():raise ValueError('Inconsistent baseline clock')
    headline=read_monthly(ROOT/files[6]).headline_mm.dropna()
    return dict(core=core,features=features,broad=broad,panel=panel,available=available,
                h0=h0,clocks=clocks,base=base,headline=headline,hashes=hashes,futures=pd.DataFrame(future_audit))


def fit_band(b,states,design,core,available,clocks,outer):
    band=engine.BANDS[b];groups=feature_groups(design.columns)
    design=design.copy()
    design['destination_season']=pd.Series({t:np.mean([s['seasonal'][(t+h).month] for h in range(band[0],band[1]+1)]) for t,s in states.items()})
    groups={k:v+['destination_season'] for k,v in groups.items()}
    histories={k:[] for k in (*groups,'forest','state')}
    output=[];selections=[];fits=[]
    for i,(t,state) in enumerate(sorted(states.items())):
        clock=clocks[t];ts=str(t)
        y,labels=engine.residual_labels(core,available,states,t,clock,band)
        predictions={};diagnostics={}
        for family,columns in groups.items():
            predictions[family]={};diagnostics[family]={}
            for config in engine.ENET_CONFIGS:
                pred,info=engine.fit_residual(design[columns],y,design.loc[t,columns],'enet',config)
                predictions[family][config]=pred;diagnostics[family][config]=info
        predictions['forest']={};diagnostics['forest']={}
        for config in engine.RF_CONFIGS:
            pred,info=engine.fit_residual(design[groups['both']],y,design.loc[t,groups['both']],'rf',config)
            predictions['forest'][config]=pred;diagnostics['forest'][config]=info
        mid=np.mean([state['forecasts_log']['mid'][h] for h in range(band[0],band[1]+1)])
        predictions['state']={key:np.mean([state['forecasts_log'][key][h] for h in range(band[0],band[1]+1)])-mid for key in engine.FILTERS}
        selected={}
        for family,current in predictions.items():
            configs=tuple(engine.FILTERS) if family=='state' else engine.RF_CONFIGS if family=='forest' else engine.ENET_CONFIGS
            default='mid' if family=='state' else engine.RF_DEFAULT if family=='forest' else engine.ENET_DEFAULT
            stored=pd.DataFrame(histories[family],columns=['origin','config','prediction','n_train','last_training_target'])
            selection=engine.choose_config(stored,labels,t,clock,configs,default)
            selected[family]=selection['config']
            if t in outer:
                selections.append(dict(origin=ts,band=b,family=family,**selection))
                if family!='state':fits.append(dict(origin=ts,band=b,family=family,**diagnostics[family][selected[family]]))
            for config,pred in current.items():
                info=diagnostics[family][config] if family!='state' else dict(status='estimated',converged=True)
                histories[family].append(dict(origin=ts,config=config,prediction=pred,
                    n_train=min(len(y),120),last_training_target=str(labels.last_target.max()) if len(labels) else None,
                    status=info['status'],converged=info.get('converged',False),
                    n_iter=info.get('n_iter'),dual_gap=info.get('dual_gap')))
        if t in outer:
            for h in range(band[0],band[1]+1):
                base=state['forecasts_log']['mid'][h]
                levels={f'STATE_{k.upper()}_R15':state['forecasts_log'][k][h] for k in engine.FILTERS}
                levels['STATE_ADAPT_R15']=state['forecasts_log'][selected['state']][h]
                for family in groups:levels[f'ENET_{family.upper()}_R15']=base+predictions[family][selected[family]]
                levels['RF_RESIDUAL_R15']=base+predictions['forest'][selected['forest']]
                levels['BLEND_LINEAR_RF_R15']=(levels['ENET_BOTH_R15']+levels['RF_RESIDUAL_R15'])/2
                levels['BLEND_WIDE_STATE_R15']=(levels['ENET_WIDE_R15']+base)/2
                output.extend(dict(origin=ts,h=h,model=m,core_log=v,core_mm=100*np.expm1(v/100)) for m,v in levels.items())
        if i%30==0:print(f'band{b+1}: {i+1}/{len(states)} historical origins at {t}',flush=True)
    candidates=pd.concat([pd.DataFrame(v).assign(family=k,band=b) for k,v in histories.items()],ignore_index=True)
    return pd.DataFrame(output),selections,fits,candidates


def attach_components(core_predictions,baseline,origins):
    rows=[]
    for t in origins:
        ts=str(t);control=baseline[baseline.origin.eq(ts)&baseline.model.eq(BASE)].copy()
        if len(control)!=13:raise ValueError('Thirteen baseline horizons required')
        for model in MODELS:
            p=core_predictions[core_predictions.origin.eq(ts)&core_predictions.model.eq(model)]
            path=p.set_index('h').core_mm.reindex(range(1,13)).to_dict()
            changed=replace_core(control,path);changed['model']=model
            protected=[c for c in control if c.startswith('weight_') or c.startswith('contribution_') and c!='contribution_core']
            pd.testing.assert_frame_equal(control[protected],changed[protected],check_exact=True)
            assert control.loc[control.h.eq(0),'mm_forecast'].equals(changed.loc[changed.h.eq(0),'mm_forecast'])
            changed['status']=np.where(np.isfinite(changed.mm_forecast),'research_estimated','unavailable_core_or_noncore')
            changed['converged']=np.isfinite(changed.mm_forecast)
            changed['origin_status']=np.where(changed.groupby('origin').converged.transform('all'),'research_estimated','unavailable_component')
            changed['yy_exante']=np.nan;changed['yy_conditional']=np.nan
            rows.append(changed)
    return pd.concat(rows,ignore_index=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--jobs',type=int,default=4)
    parser.add_argument('--limit-origins',type=int);args=parser.parse_args(argv)
    if args.limit_origins is not None and args.limit_origins<1:parser.error('Positive origin limit required')
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    data=load_inputs();outer=data['h0'].index
    if args.limit_origins:outer=outer[:args.limit_origins]
    code=['path_trend_residual_r15.py','models/core_trend_residual_r15.py','data/core_trend_residual_r15.py',
          'models/core_path_r13.py','models/path_inputs.py','path_improvements_experiment_r12.py',
          'tools/paper_replication/build_paper_panel.py','tools/paper_replication/a6_catalog.py',
          'data/core_split.py','config.py','core_split_experiment.py','cz_struct.py','path_experiment.py',
          'docs/implementation/R15_TREND_RESIDUAL_SPEC_2026-09-14.md']
    hashes=data['hashes']|{p:sha(ROOT/p) for p in code}
    dump(out/'declaration.json',dict(started_at=datetime.now(timezone.utc).isoformat(),inputs=hashes,models=MODELS))
    states={};features={}
    for t in data['core'].index[data['core'].index<=outer.max()]:
        state=engine.state_at(data['core'],data['available'],t,data['clocks'][t])
        if state is not None:
            states[t]=state
            features[t]=features_at(state,data['panel'],data['broad'],data['features'].eurczk_mm,data['available'],t,data['clocks'][t])
    design=pd.DataFrame(features).T
    design.index=pd.PeriodIndex(design.index,freq='M')
    dump(out/'states.json',{str(t):s for t,s in states.items()});design.to_csv(out/'features_by_origin.csv',index_label='origin')
    data['futures'].to_csv(out/'futures_availability.csv',index=False)
    dump(out/'feature_groups.json',dict(groups=feature_groups(design.columns),hard_rows=HARD_ROWS,
        clock='origin t consumes realtime panel row t-1; detailed CPI through t-1 if published',
        futures='reconstructed current available year1 quotes; inherited12row shift removed',
        vintage='frozen current vintage; reconstructed availability; no expectations or sentiment inputs'))
    results=Parallel(n_jobs=args.jobs)(delayed(fit_band)(b,states,design,data['core'],data['available'],data['clocks'],set(outer)) for b in range(4))
    core_predictions=pd.concat([r[0] for r in results],ignore_index=True)
    core_predictions.to_csv(out/'core_predictions.csv',index=False)
    pd.concat([r[3] for r in results],ignore_index=True).to_csv(out/'sequential_candidates.csv',index=False)
    dump(out/'selections.json',[s for r in results for s in r[1]])
    dump(out/'fits.json',[s for r in results for s in r[2]])
    native=attach_components(core_predictions,data['base'],outer)
    native.to_csv(out/'native_forecasts.csv',index=False)
    base=data['base'][data['base'].origin.isin(outer.astype(str))&data['base'].model.isin(CONTROLS)]
    columns=['origin','h','target','as_of_utc','model','mm_forecast']
    forecasts,delta=add_outcomes_and_compound(pd.concat([native[columns],base[columns]],ignore_index=True),
        data['headline'],base[base.model.eq('INDEPENDENT_BRIDGE')])
    forecasts.to_csv(out/'forecasts.csv',index=False)
    scores=[score_panel(forecasts,[*CONTROLS,*MODELS],'primary_common')]
    for model in MODELS:scores.append(score_panel(forecasts,[BASE,model],f'paired_{model}'))
    pd.concat(scores,ignore_index=True).to_csv(out/'summary.csv',index=False)
    for name,digest in hashes.items():
        if sha(ROOT/name)!=digest:raise ValueError('Input/code changed during fitting: '+name)
    dump(out/'manifest.json',dict(completed_at=datetime.now(timezone.utc).isoformat(),inputs=hashes,
        packages={p:importlib.metadata.version(p) for p in ('numpy','pandas','scikit-learn','scipy')},
        origin_count=len(outer),state_count=len(states),models=MODELS,target_reconciliation_max=delta,
        outputs={p.name:sha(p) for p in out.iterdir() if p.suffix in ('.csv','.json') and p.name!='manifest.json'}))
    print('R15 finished:',out,flush=True)


if __name__=='__main__':main()
