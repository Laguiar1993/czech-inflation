"""Independently replay R16 artifacts without importing its engine or runner."""
from pathlib import Path
import argparse
import json
import hashlib
import numpy as np
import pandas as pd
from reference_helpers import labels, ridge, slope_paths, choose, release_dates, BANDS, CONFIGS

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('experiment');args=p.parse_args()
EXP=ROOT/args.experiment
OUT=HERE/EXP.name;OUT.mkdir(exist_ok=True)

def read(name,base=EXP):return pd.read_csv(base/name,float_precision='round_trip')
def monthly(path):
    d=read(path,ROOT).set_index(read(path,ROOT).columns[0]);d.index=pd.PeriodIndex(d.index,freq='M');return d
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def maxdiff(a,b):
    av=np.asarray(a,dtype=float);bv=np.asarray(b,dtype=float)
    assert av.shape==bv.shape and np.array_equal(np.isnan(av),np.isnan(bv)),(av.shape,bv.shape)
    assert np.allclose(av,bv,atol=2e-12,rtol=1e-11,equal_nan=True)
    return float(np.nanmax(np.abs(av-bv))) if np.isfinite(av).any() else 0.

manifest=json.loads((EXP/'manifest.json').read_text());checks=[]
for section,base in [('inputs',ROOT),('outputs',EXP)]:
    for name,digest in manifest[section].items():
        actual=sha(base/name);assert actual==digest,(section,name)
        checks.append(dict(section=section,name=name,sha256=actual))
pd.DataFrame(checks).to_csv(OUT/'integrity.csv',index=False)
clocks=read('clocks.csv').set_index('origin'); end=pd.Period(clocks.index.max(),'M');lastclock=pd.Timestamp(clocks.loc[str(end),'as_of'])
states=json.loads((EXP/'states.json').read_text());r15states=json.loads((ROOT/'output/research_r15/states.json').read_text())
assert states=={t:s for t,s in r15states.items() if t<=str(end)}
reference=read('first_stage_predictor_reference.csv',HERE)
designs={};feature_error=0.
for signal in ['services','goods']:
    actual=read('signal_features_'+signal+'.csv').set_index('origin')
    expected=reference[reference.group.eq(signal)&reference.origin.le(str(end))].set_index('origin').rename(columns={'z':'level','z_change3':'change3','z_change12':'change12'})
    assert actual.index.equals(expected.index)
    feature_error=max(feature_error,maxdiff(actual,expected[actual.columns]))
    actual.index=pd.PeriodIndex(actual.index,freq='M');designs[signal]=actual
    assert all(pd.Timestamp(clocks.loc[t,'as_of'])==pd.Timestamp(expected.loc[t,'clock']) for t in expected.index)

core=100*np.log1p(monthly('tests/fixtures/cleanup/cnb_core_mm.csv').iloc[:,0]/100)
broad=100*np.log1p(monthly('data/core_split/broad_yoy.csv')/100)
calendar=read('data/release_calendar_cz_cpi.csv',ROOT);calendar.index=pd.PeriodIndex(calendar.target_month,freq='M')
core_dates=release_dates(core.index,calendar);broad_dates=release_dates(broad.index,calendar)
projections=read('signal_projections.csv');stage2=read('stage2_features.csv');candidates=read('sequential_candidates.csv')
selections=json.loads((EXP/'selections.json').read_text());fits=json.loads((EXP/'fits.json').read_text())
savedlabels=read('labels.csv');independent_labels={};stage2designs={};lineage_error=0.;label_error=0.
for b,band in enumerate(BANDS):
    for signal in ['services','goods']:
        expected=labels(broad[signal],broad_dates,designs[signal].index,end,lastclock,band,designs[signal].level)
        independent_labels[('signal',signal,b)]=expected
    baseline=pd.Series({pd.Period(t,'M'):np.mean([s['forecasts_log']['fast'][str(h)] for h in range(band[0],band[1]+1)]) for t,s in states.items()})
    expected=labels(core,core_dates,baseline.index,end,lastclock,band,baseline)
    for family in ['own','services','goods','both']:
        independent_labels[('core',family,b)]=expected
        dd=pd.DataFrame({'core_acceleration':{pd.Period(t,'M'):s['x']['core_acceleration'] for t,s in states.items()}})
        required=['services','goods'] if family=='both' else [] if family=='own' else [family]
        for signal in required:
            pp=projections[projections.band.eq(b)&projections.signal.eq(signal)].set_index('origin').predicted_change
            pp.index=pd.PeriodIndex(pp.index,freq='M')
            dd[signal+'_projection']=pp.reindex(dd.index)/12
        if required:dd=dd.dropna(subset=[s+'_projection' for s in required])
        actual=stage2[stage2.family.eq(family)&stage2.band.eq(b)].set_index('origin')[dd.columns]
        actual.index=pd.PeriodIndex(actual.index,freq='M')
        assert actual.index.equals(dd.index)
        lineage_error=max(lineage_error,maxdiff(actual,dd));stage2designs[(family,b)]=dd
for key,expected in independent_labels.items():
    stage,family,b=key
    actual=savedlabels[savedlabels.stage.eq(stage)&savedlabels.family.eq(family)&savedlabels.band.eq(b)].reset_index(drop=True)
    assert list(actual.origin)==list(expected.origin)
    assert list(actual.last_target)==list(expected.last_target)
    assert list(pd.to_datetime(actual.available_from))==list(pd.to_datetime(expected.available_from))
    label_error=max(label_error,maxdiff(actual.actual,expected.actual))

for fit in fits:
    key=(fit['stage'],fit['family'],fit['band']);t=fit['origin']
    truth=independent_labels[key]
    eligible=truth[truth.last_target.lt(t)&pd.to_datetime(truth.available_from).le(pd.Timestamp(clocks.loc[t,'as_of']))]
    dd=designs[key[1]] if key[0]=='signal' else stage2designs[(key[1],key[2])]
    keys=dd.index.intersection(pd.PeriodIndex(eligible.origin,freq='M')).sort_values()[-120:]
    assert fit['training_origins']==[str(k) for k in keys],(key,t)
    assert fit['n_train']==len(keys),(key,t)
    if len(keys):
        assert fit['last_training_target']==eligible[eligible.origin.isin(keys.astype(str))].last_target.max()

selection_errors=[];selection_count=0;max_loss_diff=0.
for choice in selections:
    if choice['stage']=='slope':continue
    key=(choice['stage'],choice['family'],choice['band']);t=choice['origin']
    group=candidates[candidates.stage.eq(key[0])&candidates.family.eq(key[1])&candidates.band.eq(key[2])]
    config,dates,loss=choose(group,independent_labels[key],t,clocks.loc[t,'as_of'],('l0.1','l1','l10'),'l1')
    assert config==choice['config'] and dates==choice['validation_origins'],(key,t,config,choice)
    assert set(loss)==set(choice['losses'])
    if loss:max_loss_diff=max(max_loss_diff,maxdiff(list(loss.values()),[choice['losses'][c] for c in loss]))
    selection_count+=1
for row in projections.itertuples():
    actual=candidates[candidates.origin.eq(row.origin)&candidates.stage.eq('signal')&candidates.family.eq(row.signal)&candidates.band.eq(row.band)&candidates.config.eq(row.config)]
    assert len(actual)==1
    maxdiff([row.predicted_change],[actual.prediction.iloc[0]])
    maxdiff([row.current_z],[designs[row.signal].loc[pd.Period(row.origin,'M'),'level']])
    maxdiff([row.projected_z],[row.current_z+row.predicted_change])

savedslopes=json.loads((EXP/'slope_states.json').read_text());slope_error=0.;slope_ref={}
for t,s in states.items():
    tp=pd.Period(t,'M');hh=core.loc[:tp-1]
    assert core_dates.reindex(hh.index).le(pd.Timestamp(clocks.loc[t,'as_of'])).all()
    rebuilt=slope_paths(hh,s['seasonal'],tp);slope_ref[t]=rebuilt
    for config,path in rebuilt.items():
        slope_error=max(slope_error,maxdiff(list(path.values()),[savedslopes[t]['forecasts_log'][config][str(h)] for h in path]))
slope_selection_count=0
for choice in [c for c in selections if c['stage']=='slope']:
    t=pd.Period(choice['origin'],'M');clock=pd.Timestamp(clocks.loc[str(t),'as_of']);lossrows=[]
    for r,paths in slope_ref.items():
        rp=pd.Period(r,'M');months=pd.period_range(rp+1,rp+12,freq='M')
        yy=core.reindex(months);pub=core_dates.reindex(months)
        if months[-1]>=t or pub.isna().any() or pub.gt(clock).any() or not np.isfinite(yy).all():continue
        losses={c:float(np.mean((np.array(list(paths[c].values()))-yy.to_numpy())**2)) for c in CONFIGS}
        lossrows.append({'origin':r,**losses})
    valid=pd.DataFrame(lossrows).set_index('origin').tail(36)
    assert list(valid.index)==choice['validation_origins']
    if len(valid)<24:win=CONFIGS[0];loss={}
    else:
        loss=valid.mean().to_dict();minimum=min(loss.values());ties=[c for c in CONFIGS if np.isclose(loss[c],minimum,rtol=1e-10,atol=1e-12)]
        win=CONFIGS[0] if CONFIGS[0] in ties else ties[0]
    assert win==choice['config']
    if loss:max_loss_diff=max(max_loss_diff,maxdiff(list(loss.values()),[choice['losses'][c] for c in loss]))
    slope_selection_count+=1

# Four complete stage1 -> stage2 lineage replays. For full runs spread these
# across eras. Also refit each first-stage forecast used by the last training
# row of every chosen second-stage fit, at that row's historical clock.
outer=sorted(read('core_predictions.csv').origin.unique())
targets=['2019-02','2022-06','2024-06','2026-07']
refits=[]
fitlookup={(f['stage'],f['family'],f['band'],f['origin']):f for f in fits}
def refit(stage,family,b,t):
    key=(stage,family,b,t);fit=fitlookup[key]
    dd=designs[family] if stage=='signal' else stage2designs[(family,b)]
    tp=pd.Period(t,'M');truth=independent_labels[(stage,family,b)]
    truth=truth[truth.last_target.lt(t)&pd.to_datetime(truth.available_from).le(pd.Timestamp(clocks.loc[t,'as_of']))]
    pred,info=ridge(dd,truth,dd.loc[tp],float(fit['config'][1:]))
    saved=candidates[candidates.stage.eq(stage)&candidates.family.eq(family)&candidates.band.eq(b)&candidates.origin.eq(t)&candidates.config.eq(fit['config'])].prediction.iloc[0]
    error=maxdiff([pred],[saved]);assert info['keys']==fit['training_origins']
    if np.isfinite(pred):
        maxdiff([info['intercept']],[fit['intercept']]);assert info['columns']==fit['columns']
        for field in ['means','scales','coefficients']:
            maxdiff(list(info[field].values()),[fit[field][c] for c in info[field]])
    refits.append(dict(stage=stage,family=family,band=b,origin=t,config=fit['config'],prediction=saved,
        reference=pred,absolute_difference=error,n_train=info['n_train'],train_first=info['keys'][0],train_last=info['keys'][-1]))
    return info
for b,wanted in enumerate(targets):
    t=wanted if wanted in outer else outer[0]
    info=refit('core','both',b,t)
    for signal in ['services','goods']:
        refit('signal',signal,b,t)
        refit('signal',signal,b,info['keys'][-1])
pd.DataFrame(refits).to_csv(OUT/'independent_refits.csv',index=False)

native=read('native_forecasts.csv');base=read('output/research_r14b/integration/native_forecasts.csv',ROOT)
base=base[base.model.eq('STABLE_PIPELINE_R14B')]
joined=native.merge(base,on=['origin','h'],suffixes=('','_baseline'),validate='many_to_one')
protected=[c for c in base if c.startswith('weight_') or c.startswith('value_') and c!='value_core' or c.startswith('contribution_') and c!='contribution_core']
for col in protected:
    aa=joined[col].to_numpy();bb=joined[col+'_baseline'].to_numpy()
    assert np.array_equal(aa,bb,equal_nan=True),col
assert np.array_equal(joined.loc[joined.h.eq(0),'mm_forecast'],joined.loc[joined.h.eq(0),'mm_forecast_baseline'],equal_nan=True)
corepred=read('core_predictions.csv');pp=corepred.pivot(index=['origin','h'],columns='model',values='core_log')
blend_error=maxdiff(pp.BLEND_DAMPED_TRANSMISSION_R16,(pp.DAMPED_ADAPT_R16+pp.TRANSMISSION_BOTH_R16)/2)
monthly_boundary_error=maxdiff(corepred.core_mm,100*np.expm1(corepred.core_log/100))
selectionlookup={(c['stage'],c['family'],c['band'],c['origin']):c['config'] for c in selections}
candidatelookup=candidates.set_index(['stage','family','band','origin','config']).prediction
native_path_error=0.
for row in corepred.itertuples():
    if row.model.startswith('TRANSMISSION_'):
        family=row.model[len('TRANSMISSION_'):-len('_R16')].lower();b=(row.h-1)//3
        config=selectionlookup[('core',family,b,row.origin)]
        residual=candidatelookup[('core',family,b,row.origin,config)]
        expected=states[row.origin]['forecasts_log']['fast'][str(row.h)]+residual
    elif row.model=='DAMPED_ADAPT_R16':
        config=selectionlookup[('slope','whole_path','all',row.origin)]
        expected=slope_ref[row.origin][config][row.h]
    elif row.model.startswith('DAMPED_'):
        config=row.model[len('DAMPED_'):-len('_R16')].lower()
        expected=slope_ref[row.origin][config][row.h]
    else:continue
    native_path_error=max(native_path_error,maxdiff([row.core_log],[expected]))
native_core=native[native.h.gt(0)].merge(corepred,on=['origin','h','model'],validate='one_to_one')
maxdiff(native_core.value_core,native_core.core_mm)
smoke_rows_checked=0
smoke=ROOT/'output/research_r16_smoke'
if EXP.name=='research_r16' and (smoke/'manifest.json').exists():
    for name,keys in [('core_predictions.csv',['origin','h','model']),
                      ('signal_projections.csv',['origin','band','signal']),
                      ('sequential_candidates.csv',['origin','stage','family','band','config'])]:
        old=read(name,smoke).set_index(keys).sort_index();new=read(name).set_index(keys).reindex(old.index)
        pd.testing.assert_frame_equal(old,new,check_exact=True,check_dtype=False)
        smoke_rows_checked+=len(old)
    old=json.loads((smoke/'slope_states.json').read_text())
    assert old=={t:savedslopes[t] for t in old}
summary=dict(experiment=str(EXP),verified_hashes=len(checks),feature_max_error=feature_error,
    generated_design_max_error=lineage_error,label_max_error=label_error,ridge_selections_replayed=selection_count,
    slope_selections_replayed=slope_selection_count,selection_max_loss_error=max_loss_diff,
    slope_paths_replayed=len(slope_ref)*4,slope_max_error=slope_error,independent_ridge_refits=len(refits),
    ridge_max_error=max(r['absolute_difference'] for r in refits),all_fit_calendars_replayed=len(fits),
    native_rows_protected=len(native),blend_max_error=blend_error,monthly_boundary_max_error=monthly_boundary_error,
    saved_path_reconstruction_max_error=native_path_error,smoke_rows_unchanged=smoke_rows_checked)
(OUT/'summary.json').write_text(json.dumps(summary,indent=2,default=str)+'\n')
print(json.dumps(summary,indent=2,default=str))
