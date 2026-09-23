"""Declared R13 own-error family experiment; --verify freshly refits offline."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from core_split_experiment import ROOT,FIX,digest,read_frame,publication_dates
from core_remainder_experiment import assess,diagnostics,dependency_hashes as frozen_hashes
from data.core_split import load_frozen,monthly_rates,weights_at
from models.independent_nowcast import sequential_errors,policy_frame
from models.nowcast_family_r13 import category_history,base_history,matched_histories,correct,family_forecasts
from evaluation.core_split import _score

OUTPUT=ROOT/'output/research_r13/nowcast'
SPEC='docs/implementation/R13_NOWCAST_SPEC.md'


def dependency_hashes():
    hashes=frozen_hashes()
    paths=['nowcast_family_experiment_r13.py','models/nowcast_family_r13.py',SPEC,
        'models/independent_nowcast.py','models/horizon_models.py','config.py',
        'output/independent_nowcast_hard_errors.csv','requirements-r9-lock.txt']
    fixture_manifest=json.loads((FIX/'MANIFEST.json').read_text())
    for name,expected in fixture_manifest.items():
        if digest(FIX/name)!=expected:
            raise ValueError(f'frozen fixture changed: {name}')
        paths.append((FIX/name).relative_to(ROOT).as_posix())
    for name in paths:
        hashes[name]=digest(ROOT/name)
    return hashes


def pairs(pred):
    result=[(c,'R9_BASE') for c in pred if c!='R9_BASE']
    result += [
        ('CATEGORY_HALF_CORRECTION','CATEGORY_RAW'),
        ('CATEGORY_FULL_CORRECTION','CATEGORY_RAW'),
        ('CATEGORY_HALF_CORRECTION','BASE_MATCHED_HALF'),
        ('CATEGORY_FULL_CORRECTION','BASE_MATCHED_FULL'),
        ('BASE_MATCHED_HALF','R9_HALF'),('BASE_MATCHED_FULL','R9_FULL')]
    return [(a,b) for a,b in result if a in pred and b in pred]


def category_decisions(index):
    import cz_struct as s
    return pd.Series({t:s._first_release_dt(t).normalize()-pd.Timedelta(minutes=1)
                      if pd.notna(s._first_release_dt(t)) else pd.NaT for t in index})


def bootstrap(pred,survey,warm):
    rng=np.random.default_rng(42); rows=[]
    masks={'all':np.ones(len(pred),bool),'2024+':pred.index>=pd.Period('2024-01'),
           'post_warmup':warm.to_numpy()}
    for candidate,reference in pairs(pred):
        for frame,mask in masks.items():
            a=(pred[candidate]-survey.actual).loc[mask].to_numpy()
            b=(pred[reference]-survey.actual).loc[mask].to_numpy()
            valid=np.isfinite(a)&np.isfinite(b); a,b=a[valid],b[valid]; n=len(a)
            for block in (12,6,18):
                if n:
                    starts=rng.integers(0,n,(5000,int(np.ceil(n/block))))
                    ix=((starts[:,:,None]+np.arange(block))%n).reshape(5000,-1)[:,:n]
                for metric in ('rmse','mae'):
                    if n:
                        if metric=='rmse':
                            observed=np.sqrt(np.mean(a*a))-np.sqrt(np.mean(b*b))
                            delta=np.sqrt(np.mean(a[ix]**2,axis=1))-np.sqrt(np.mean(b[ix]**2,axis=1))
                        else:
                            observed=np.mean(abs(a))-np.mean(abs(b))
                            delta=np.mean(abs(a[ix]),axis=1)-np.mean(abs(b[ix]),axis=1)
                        lo,hi=np.quantile(delta,[.025,.975])
                    else: observed=lo=hi=np.nan
                    rows.append(dict(candidate=candidate,reference=reference,frame=frame,
                        metric=metric,block=block,n=n,delta=observed,lower=lo,upper=hi,
                        draws=5000,seed=42,primary=block==12,
                        limitation='reused data; descriptive, not selection-adjusted'))
    return pd.DataFrame(rows)


def score(pred,survey,warm):
    result=assess(pred,survey)
    rows=[]
    for model,events in result['release_rows'].groupby('model',sort=False):
        for coverage,valid in [('own',events.valid),('common',events.common_valid)]:
            eligible=valid&warm.reindex(events.index)
            for frame,mask in [('post_warmup',eligible),('post_warmup_big',eligible&events.big),
                               ('post_warmup_alerts',eligible&events.alert)]:
                rows.append(_score(events.loc[mask],model,frame,coverage))
    result['scores']=pd.concat([result['scores'],pd.DataFrame(rows)],ignore_index=True)
    result['bootstrap']=bootstrap(pred,survey,warm)
    return result


def pair_diagnostics(pred,survey,core,weights,fixed,warm):
    attribution=[]; omissions=[]; summary=[]
    actual=survey.actual
    noncore=fixed+weights*core-actual
    masks={'all':np.ones(len(pred),bool),'2024+':pred.index>=pd.Period('2024-01'),
           'post_warmup':warm.to_numpy()}
    for candidate,reference in pairs(pred):
        a=pred[candidate]-actual; b=pred[reference]-actual
        ac=a-noncore; bc=b-noncore
        core_gain=bc**2-ac**2; cross=2*noncore*(bc-ac); headline=b**2-a**2
        if abs(headline-core_gain-cross).max()>1e-10:
            raise AssertionError('pairwise core/noncore identity failed')
        attribution.append(pd.DataFrame(dict(period=pred.index.astype(str),candidate=candidate,
            reference=reference,weighted_core_squared_gain=core_gain.to_numpy(),
            cross_term_gain=cross.to_numpy(),headline_squared_gain=headline.to_numpy())))
        for frame,mask in masks.items():
            summary.append(dict(candidate=candidate,reference=reference,frame=frame,n=int(np.sum(mask)),
                weighted_core_squared_gain=core_gain.loc[mask].mean(),cross_term_gain=cross.loc[mask].mean(),
                headline_squared_gain=headline.loc[mask].mean()))
        for omitted in pred.index:
            mask=pred.index!=omitted
            omissions.append(dict(candidate=candidate,reference=reference,omitted_period=str(omitted),
                delta_rmse=np.sqrt(np.mean(a.loc[mask]**2))-np.sqrt(np.mean(b.loc[mask]**2)),
                delta_mae=abs(a.loc[mask]).mean()-abs(b.loc[mask]).mean()))
    return dict(pairwise_attribution=pd.concat(attribution,ignore_index=True),
        pairwise_attribution_summary=pd.DataFrame(summary),pairwise_leave_one_out=pd.DataFrame(omissions))


def run(destination=OUTPUT):
    import cz_struct as s
    hashes=dependency_hashes()
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    source=load_frozen(); cats=monthly_rates(source['levels'])
    core=read_frame(FIX/'cnb_core_mm.csv').iloc[:,0]
    features=read_frame(FIX/'core_features.csv')
    headline=read_frame(FIX/'target_headline_cpi_mm.csv').iloc[:,0]
    comp=read_frame(FIX/'component_food_fuel_mm.csv')
    reg=read_frame(FIX/'cnb_regulated_mm.csv').iloc[:,0]
    alc=read_frame(FIX/'alcohol_tobacco.csv').iloc[:,0]
    reference=read_frame(ROOT/'output/independent_nowcast_forecasts.csv')
    old=read_frame(ROOT/'output/core_split_forecasts.csv')
    expected=pd.period_range('2019-02','2026-07',freq='M')
    if not reference.index.equals(expected) or not old.index.equals(expected):
        raise ValueError('the exact declared 90 monthly origins are required')
    dates=publication_dates(core.index)
    attempts=core.index[(core.index>=cats.index.min()+1)&(core.index<=expected.max())]
    decisions=category_decisions(attempts)
    def origin_weights(t,clock):
        cw=s.solve_weights(headline,comp,core,reg,t-1,as_of=clock,alc=alc)[s._regime(t)]['core']
        return cw,weights_at(source['weights'],t,clock)
    history,fits=category_history(core,cats,dates,decisions,origin_weights)
    history.to_csv(destination/'category_history.csv',index=False)
    fits.to_csv(destination/'raw_fit_audit.csv',index=False)
    category_errors=pd.Series(history.error.to_numpy(),index=pd.PeriodIndex(history.period,freq='M')).dropna()
    raw_history=history.set_index('period')
    print(f"Category history: {len(category_errors)} finite forecasts; first {category_errors.index.min()}",flush=True)
    base_errors=sequential_errors(features,core,'hard',through=expected.max())
    saved_errors=read_frame(ROOT/'output/independent_nowcast_hard_errors.csv').iloc[:,0]
    replay_errors=base_errors.loc[base_errors.index<expected.max()]
    if not replay_errors.index.equals(saved_errors.index) or not np.allclose(replay_errors,saved_errors,atol=1e-12,rtol=0):
        raise AssertionError('legacy BASE sequential error replay changed')
    matched_raw_errors,base_raw_audit=base_history(features,core,decisions.reindex(category_errors.index))
    base_raw_audit.to_csv(destination/'matched_base_history.csv',index=False)
    base_matched,category_matched=matched_histories(matched_raw_errors,category_errors)
    if not category_matched.index.equals(category_errors.index):
        raise AssertionError('category history does not have matched BASE forecast dates')
    pd.DataFrame({'legacy_base_error':base_errors,'matched_base_error':base_matched,
                  'category_error':category_errors}).to_csv(destination/'sequential_errors.csv',index_label='period')
    old_diag=pd.DataFrame(json.loads((ROOT/'output/independent_nowcast_diagnostics.json').read_text()))
    old_diag=old_diag[old_diag.policy=='hard'].set_index('period')
    predictions=[]; corrections=[]; checks=[]; fixed_rows=[]; warm_rows=[]
    for i,(t,ref) in enumerate(reference.iterrows()):
        clock=pd.Timestamp(ref.as_of_eve)
        if not clock<s._first_release_dt(t) or not clock<dates.loc[t] or clock!=decisions.loc[t]:
            raise AssertionError(f'invalid historical decision clock {t}')
        cr=raw_history.loc[str(t)]; cw=float(cr.core_weight)
        base_core=float(core.loc[t]-matched_raw_errors.loc[t])
        fixed=float(ref.HARD_BASE-ref.coreweight*old_diag.loc[str(t),'core_forecast'])
        cat_raw=float(fixed+cw*cr.raw_core)
        differences=dict(weight=abs(cw-ref.coreweight),
            base_core=abs(base_core-old_diag.loc[str(t),'core_forecast']),
            category_raw=abs(cat_raw-old.loc[t,'TARGET_OWN']))
        if max(differences.values())>1e-12:
            raise AssertionError(f'fixed raw model parity failed at {t}: {differences}')
        x=s._mask_row_by_availability(policy_frame(features,'hard'),t,clock)
        corr={}; infos={}
        for family,errors in [('BASE_LEGACY',base_errors),('BASE_MATCHED',base_matched),('CATEGORY',category_matched)]:
            value,info=correct(x,errors,t,clock,dates)
            corr[family]=value; infos[family]=info
            corrections.append(dict(period=str(t),as_of=clock,family=family,core_correction=value,**info))
        if infos['BASE_MATCHED']['eligible_error_months']!=infos['CATEGORY']['eligible_error_months']:
            raise AssertionError('matched-family error training calendars differ')
        _,legacy_half,legacy_full=family_forecasts(ref.HARD_BASE,corr['BASE_LEGACY'],cw)
        differences['legacy_half']=abs(legacy_half-ref.HARD_HALF)
        differences['legacy_full']=abs(legacy_full-ref.HARD_FULL)
        if max(differences.values())>1e-12:
            raise AssertionError(f'legacy correction parity failed at {t}: {differences}')
        _,bh,bf=family_forecasts(ref.HARD_BASE,corr['BASE_MATCHED'],cw)
        _,ch,cf=family_forecasts(cat_raw,corr['CATEGORY'],cw)
        predictions.append(dict(period=str(t),R9_BASE=ref.HARD_BASE,R9_HALF=ref.HARD_HALF,R9_FULL=ref.HARD_FULL,
            CATEGORY_RAW=cat_raw,CATEGORY_HALF_CORRECTION=ch,CATEGORY_FULL_CORRECTION=cf,
            BASE_MATCHED_HALF=bh,BASE_MATCHED_FULL=bf))
        checks.append(dict(period=str(t),as_of=clock,**{name+'_difference':v for name,v in differences.items()}))
        fixed_rows.append(fixed)
        warm_rows.append(all(infos[f]['status']=='ok' and infos[f]['n_errors']>=40 for f in ('BASE_MATCHED','CATEGORY')))
        if i%10==0: print(f'Completed corrections {i+1}/90: {t}',flush=True)
    pred=pd.DataFrame(predictions).set_index('period'); pred.index=pd.PeriodIndex(pred.index,freq='M')
    if not np.isfinite(pred.to_numpy()).all(): raise AssertionError('missing declared forecast')
    pred.to_csv(destination/'forecasts.csv',index_label='period')
    # First evaluation-only read occurs after every forecast is fixed and saved.
    survey=pd.read_csv(ROOT/'data/czcpmom_survey_history_extended.csv')
    survey=survey[survey.era!='flash_survey_suspect'].copy()
    survey.index=pd.PeriodIndex(survey.target_month,freq='M')
    if not survey.index.is_unique: raise ValueError('duplicate first-release survey dates')
    survey=survey.reindex(pred.index)
    warm=pd.Series(warm_rows,index=pred.index)
    assessment=score(pred,survey,warm)
    fixed=pd.Series(fixed_rows,index=pred.index)
    tables=diagnostics(pred,survey,core.reindex(pred.index),reference.coreweight,fixed)
    tables.update(pair_diagnostics(pred,survey,core.reindex(pred.index),reference.coreweight,fixed,warm))
    tables.update(correction_audit=pd.DataFrame(corrections),origin_checks=pd.DataFrame(checks),
        scoring_calendar=pd.DataFrame(dict(period=pred.index.astype(str),post_warmup=warm.to_numpy(),
            big=(survey.actual-survey.survey_median).abs().ge(.4-1e-9).to_numpy())))
    for name,table in tables.items(): table.to_csv(destination/f'{name}.csv',index=False)
    for name in ('scores','release_rows','bootstrap'):
        assessment[name].to_csv(destination/f'{name}.csv',index=(name=='release_rows'),index_label='period')
    audit=tables['correction_audit']
    specification=dict(models=list(pred),gates=assessment['gates'],
        forest=dict(n_estimators=200,min_samples_leaf=3,max_features=1.,seed=42,val_window_cap=12,
                    validation_rule='min(12,max(n_errors//5,4))',half_life=6),
        first_category_forecast=str(category_errors.index.min()),n_category_forecasts=len(category_errors),
        raw_history_status_counts=history.status.value_counts().to_dict(),
        correction_status_counts={family:group.status.value_counts().to_dict() for family,group in audit.groupby('family')},
        post_warmup_dates=pred.index[warm].astype(str).tolist(),post_warmup_n=int(warm.sum()),
        post_warmup_big=int((warm&((survey.actual-survey.survey_median).abs()>=.4-1e-9)).sum()),
        maximum_parity_difference=max(max(v for k,v in row.items() if k.endswith('_difference')) for row in checks),
        status='Research only, no model promotion; latest-vintage inputs and reconstructed availability; reused sample.',
        correction_target='own sequential actual core minus raw core forecast; admitted only after detail release')
    (destination/'specification.json').write_text(json.dumps(specification,indent=2),encoding='utf-8')
    for name,expected_hash in hashes.items():
        if digest(ROOT/name)!=expected_hash: raise AssertionError(f'dependency changed during run: {name}')
    outputs={p.name:digest(p) for p in sorted(destination.glob('*.csv'))}
    outputs['specification.json']=digest(destination/'specification.json')
    manifest=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),inputs=hashes,outputs=outputs)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(assessment['scores'].query("coverage=='common' and frame in ['all','2024+','big','post_warmup']")
          [['model','frame','n','rmse','mae','direction','material_win','material_loss']].to_string(index=False),flush=True)
    return manifest


def verify():
    frozen=json.loads((OUTPUT/'manifest.json').read_text())
    for name,expected in frozen['inputs'].items():
        if digest(ROOT/name)!=expected: raise ValueError(f'dependency changed: {name}')
    for name,expected in frozen['outputs'].items():
        if digest(OUTPUT/name)!=expected: raise ValueError(f'output changed: {name}')
    def forbidden(*args,**kwargs): raise AssertionError('offline replay attempted network/database access')
    with tempfile.TemporaryDirectory(prefix='cz_nowcast_r13_') as temporary,ExitStack() as stack:
        for target in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(target,side_effect=forbidden))
        replay=run(Path(temporary))
    if replay['outputs']!=frozen['outputs']:
        changed=[name for name in frozen['outputs'] if replay['outputs'].get(name)!=frozen['outputs'][name]]
        raise AssertionError(f'R13 freshly fitted output mismatch: {changed}')
    print(f"Offline fresh refit: {len(frozen['outputs'])} output files byte-identical.",flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    verify() if args.verify else run()
