"""Independent R18 output arithmetic audit; imports no project evaluator/model.

Run from repository root with --experiment output/research_r18/path_v2.
All writes remain in this review directory. Assertions fail closed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CONTROLS = ['INDEPENDENT_BRIDGE', 'STATE_FAST_R15', 'STABLE_LOCAL_CORE_R14B',
            'DAMPED_P95_Q001_R16', 'FUEL_ANNUAL_R17']
NEW = ['MCT_SLOW_R18', 'MCT_FAST_R18', 'MCT_SIGNALS_R18',
       'FOOD_H0_FAST_R18', 'FOOD_H0_SLOW_R18', 'FOOD_H0_SELECT_R18']
KEYS = ['origin', 'h', 'model']


def read(path):
    return pd.read_csv(path, float_precision='round_trip', low_memory=False)


def same(a, b, label, atol=2e-11):
    a, b = np.asarray(a, float), np.asarray(b, float)
    assert a.shape == b.shape, (label, a.shape, b.shape)
    assert np.allclose(a, b, rtol=0, atol=atol, equal_nan=True), label
    ok = np.isfinite(a) & np.isfinite(b)
    return float(np.max(np.abs(a[ok] - b[ok]))) if ok.any() else 0.


def stats(error):
    e = np.asarray(error, float)
    e = e[np.isfinite(e)]
    return dict(n=len(e), mae=float(np.abs(e).mean()) if len(e) else np.nan,
                rmse=float(np.sqrt((e*e).mean())) if len(e) else np.nan,
                bias=float(e.mean()) if len(e) else np.nan)


def sample_mask(frame, sample):
    if sample == 'full': return np.ones(len(frame), bool)
    if sample == 'origins_2019_2021': return frame.origin.between('2019-01', '2021-12')
    if sample == 'origins_2022_2023': return frame.origin.between('2022-01', '2023-12')
    if sample == 'origins_2024plus': return frame.origin.ge('2024-01')
    if sample == 'recent_targets': return frame.target.ge('2024-01')
    raise AssertionError(sample)


def month_series(path, col):
    data = read(ROOT/path)
    return pd.Series(data[col].to_numpy(), index=pd.PeriodIndex(data.period, freq='M'))


def annual_from_monthly(history, origin, path, h):
    months = pd.period_range(origin+h-11, origin+h, freq='M')
    values = np.array([history.get(t, np.nan) if t < origin else path[t.ordinal-origin.ordinal]
                       for t in months], float)
    return 100*(np.prod(1+values/100)-1) if np.isfinite(values).all() else np.nan


def run(experiment):
    out = ROOT/experiment
    evaluation = out/'evaluation'
    manifest = json.loads((out/'manifest.json').read_text())
    roster = CONTROLS+NEW
    assert set(manifest['controls']) == set(CONTROLS)
    assert set(manifest['models']) == set(NEW)
    native, forecasts = [read(out/name) for name in ['native_forecasts.csv', 'forecasts.csv']]
    calendar = [str(x) for x in pd.period_range('2019-02', '2026-07', freq='M')]
    expected = set((o, h, m) for o in calendar for h in range(13) for m in roster)
    for frame in [native, forecasts]:
        assert not frame.duplicated(KEYS).any()
        assert set(frame[KEYS].itertuples(index=False, name=None)) == expected
        assert (pd.PeriodIndex(frame.target, freq='M').asi8 ==
                pd.PeriodIndex(frame.origin, freq='M').asi8 + frame.h.to_numpy()).all()
        assert frame.groupby('origin').as_of_utc.nunique().eq(1).all()
    checks = dict(models=len(roster), origins=len(calendar), rows_per_model=1170)
    frozen = read(ROOT/'output/research_r17/path/native_forecasts.csv')
    overlap = native[native.model.isin(CONTROLS)].merge(frozen[frozen.model.isin(CONTROLS)],
                on=KEYS, validate='one_to_one', suffixes=('', '_old'), how='outer', indicator=True)
    assert overlap._merge.eq('both').all()
    protected_numeric = [x for x in frozen if x.startswith(('weight_', 'value_', 'contribution_'))]
    control_columns = ['mm_forecast', 'h0_exante', 'yy_exante', 'mm_actual', 'yy_actual'] + protected_numeric
    checks['controls_exact_max'] = max(same(overlap[c], overlap[c+'_old'], c, 0) for c in control_columns)
    assert overlap.as_of_utc.equals(overlap.as_of_utc_old)
    old_forecasts = read(ROOT/'output/research_r17/path/forecasts.csv')
    merged = forecasts[forecasts.model.isin(CONTROLS)].merge(old_forecasts[old_forecasts.model.isin(CONTROLS)],
                on=KEYS, validate='one_to_one', suffixes=('', '_old'))
    checks['control_compounding_max'] = max(same(merged[c], merged[c+'_old'], c)
        for c in ['mm_forecast', 'yy_exante', 'cumulative_log_forecast', 'yy_actual'])
    fast = native[native.model.eq('STATE_FAST_R15')]
    candidates = native[native.model.isin(NEW)].merge(fast, on=['origin','h'],
                     suffixes=('', '_fast'), validate='many_to_one')
    assert candidates.as_of_utc.equals(candidates.as_of_utc_fast)
    checks['candidate_h0_max'] = same(candidates.loc[candidates.h.eq(0), 'mm_forecast'],
                                          candidates.loc[candidates.h.eq(0), 'mm_forecast_fast'], 'h0', 0)
    invariant_checks = []
    for model, g in candidates.groupby('model'):
        changed = 'core' if model.startswith('MCT') else 'food'
        for col in protected_numeric:
            if col in ['value_'+changed, 'contribution_'+changed]: continue
            invariant_checks.append(same(g[col], g[col+'_fast'], model+' '+col, 0))
        f = g[g.h.gt(0)]
        delta = f['contribution_'+changed] - f['contribution_'+changed+'_fast']
        invariant_checks.append(same(f.mm_forecast-f.mm_forecast_fast, delta, model+' additive change'))
    checks['candidate_protected_max'] = max(invariant_checks)
    history = month_series('output/independent_path_frozen_inputs.csv', 'headline_mm')
    actual_yy = pd.Series([100*(np.prod(1+history.iloc[i-11:i+1].to_numpy()/100)-1)
                          if i >= 11 and np.isfinite(history.iloc[i-11:i+1]).all() else np.nan
                          for i in range(len(history))], index=history.index)
    core = month_series('tests/fixtures/cleanup/cnb_core_mm.csv', 'core')
    computed = []
    native_lookup = native.set_index(KEYS)
    for (origin, model), g in forecasts.groupby(['origin','model']):
        g = g.sort_values('h'); o = pd.Period(origin, 'M')
        monthly = g.mm_forecast.to_numpy()
        corepred = np.array([native_lookup.loc[(origin,h,model),'value_core'] for h in range(13)])
        for h in range(13):
            t = o+h
            predicted_core = corepred[1:h+1]
            actual_core = core.reindex(pd.period_range(o+1, t, freq='M')).to_numpy() if h else np.array([])
            cum = lambda a: float(np.log1p(a/100).sum()*100) if np.isfinite(a).all() else np.nan
            computed.append(dict(origin=origin,h=h,model=model,target=str(t),
                mm_forecast=monthly[h],mm_actual=history.get(t,np.nan),
                yy_exante=annual_from_monthly(history,o,monthly,h),yy_actual=actual_yy.get(t,np.nan),
                cumulative_log_forecast=cum(monthly[1:h+1]),
                cumulative_log_actual=cum(history.reindex(pd.period_range(o+1,t,freq='M')).to_numpy()) if h else 0.,
                core_mm_forecast=corepred[h],core_mm_actual=core.get(t,np.nan),
                core_cumulative_log_forecast=cum(predicted_core) if h else np.nan,
                core_cumulative_log_actual=cum(actual_core) if h else np.nan))
    computed = pd.DataFrame(computed)
    check = forecasts.merge(computed,on=KEYS,suffixes=('', '_independent'),validate='one_to_one')
    checks['independent_annual_max'] = same(check.yy_exante,check.yy_exante_independent,'annual product')
    for col in ['yy_actual','mm_actual','cumulative_log_forecast','cumulative_log_actual']:
        checks[col+'_max'] = same(check[col],check[col+'_independent'],col)
    support = read(ROOT/'output/research_r17/attribution/primary_support.csv')
    assert len(support)==969 and not support.duplicated(['origin','h']).any()
    primary = computed.merge(support,on=['origin','h'],validate='many_to_one')
    saved_primary = read(evaluation/'primary_rows.csv')
    assert set(saved_primary[KEYS].itertuples(index=False,name=None)) == set(primary[KEYS].itertuples(index=False,name=None))
    assert len(saved_primary)==969*len(roster)
    checks['primary_keys_per_model']=969
    checks['primary_counts_by_h']={str(k):int(v) for k,v in support.groupby('h').size().items()}
    metrics={'headline_yy':('yy_exante','yy_actual'), 'headline_mm':('mm_forecast','mm_actual'),
      'headline_cumulative_log':('cumulative_log_forecast','cumulative_log_actual'),
      'core_mm':('core_mm_forecast','core_mm_actual'),
      'core_cumulative_log':('core_cumulative_log_forecast','core_cumulative_log_actual')}
    saved_scores=read(evaluation/'primary_scoreboard.csv'); recomputed=[]
    for r in saved_scores.itertuples():
        own=primary[primary.model.eq(r.model)&primary.h.eq(r.h)]
        own=own.loc[sample_mask(own,r.sample)]; pred,truth=metrics[r.metric]
        values=stats(own[pred]-own[truth])
        assert r.n_intended==len(own)
        assert r.n_missing_forecasts==int((~np.isfinite(own[pred])).sum())
        for k,v in values.items(): same([getattr(r,k)],[v],'primary '+k)
        recomputed.append(dict(model=r.model,h=r.h,metric=r.metric,sample=r.sample,
                              n_intended=len(own),**values))
    pd.DataFrame(recomputed).to_csv(OUT/'independent_primary_scores.csv',index=False)
    checks['primary_metric_rows_verified']=len(recomputed)
    component_actual=read(ROOT/'output/research_r14b/attribution/actual_component_targets.csv').set_index('period')
    component_rows=[]
    for (origin,model),g in native[native.h.gt(0)].groupby(['origin','model']):
        g=g.sort_values('h')
        for block in ['core','food','fuel','administered','alcohol_tobacco']:
            pred=g['value_'+block].to_numpy(float)
            truth=component_actual[block].reindex(g.target).to_numpy(float)
            p_cum=np.cumsum(100*np.log1p(pred/100));a_cum=np.cumsum(100*np.log1p(truth/100))
            for i,r in enumerate(g.itertuples()):
                component_rows.append(dict(origin=origin,model=model,h=r.h,target=r.target,block=block,
                    mm_forecast=pred[i],mm_actual=truth[i],cumulative_log_forecast=p_cum[i],cumulative_log_actual=a_cum[i]))
    components=pd.DataFrame(component_rows)
    saved_components=read(evaluation/'component_outcomes.csv')
    merged=saved_components.merge(components,on=KEYS+['block'],suffixes=('','_ind'),validate='one_to_one')
    assert len(merged)==len(components)==len(saved_components)
    checks['component_raw_rows_verified']=len(merged)
    for col in ['mm_forecast','mm_actual','cumulative_log_forecast','cumulative_log_actual']:
        same(merged[col],merged[col+'_ind'],'component '+col)
    cscores=read(evaluation/'component_scoreboard.csv')
    chosen=cscores[cscores.scope.eq('all_models_common')&cscores.h.isin([1,6,12])&cscores['sample'].isin(['full','origins_2024plus'])]
    count=0
    for r in chosen.itertuples():
        pred,truth=('mm_forecast','mm_actual') if r.metric=='monthly' else ('cumulative_log_forecast','cumulative_log_actual')
        own=components[components.block.eq(r.block)&components.h.eq(r.h)]
        own=own[np.isfinite(own[pred])&np.isfinite(own[truth])]
        commonkeys=set(own.groupby('origin').model.nunique().loc[lambda x:x.eq(len(roster))].index)
        own=own[own.origin.isin(commonkeys)&own.model.eq(r.model)]
        own=own.loc[sample_mask(own,r.sample)]
        for k,v in stats(own[pred]-own[truth]).items():same([getattr(r,k)],[v],'component score '+k)
        count+=1
    checks['selected_component_score_rows_verified']=count
    revisions=read(out/'monthly_component_revisions.csv')
    contributions=['contribution_'+x for x in ['core','food','administered','alcohol_tobacco','fuel','wedge']]
    max_revision=0.; missing=0; annual_not_additive=0
    for r in revisions.itertuples():
        old=native_lookup.loc[(r.old_origin,r.old_h,r.model)]; new=native_lookup.loc[(r.new_origin,r.new_h,r.model)]
        assert pd.Period(r.new_origin,'M').ordinal-pd.Period(r.old_origin,'M').ordinal==1
        assert r.old_h==r.new_h+1 and r.new_h>=1
        delta=new[contributions].to_numpy(float)-old[contributions].to_numpy(float)
        same([getattr(r,x) for x in contributions],delta,'revision component')
        same([r.monthly_revision],[new.mm_forecast-old.mm_forecast],'revision monthly')
        same([r.annual_revision],[new.yy_exante-old.yy_exante],'revision annual')
        if np.isfinite(delta).all() and np.isfinite(r.monthly_revision):
            assert r.revision_status=='reconciled'
            max_revision=max(max_revision, same([delta.sum()],[r.monthly_revision],'revision additive'))
            annual_not_additive+=int(np.isfinite(r.annual_revision) and abs(delta.sum()-r.annual_revision)>1e-10)
        else:
            missing+=1; assert r.revision_status=='unavailable_component_or_total'
    checks.update(revision_rows=len(revisions),revision_missing=missing,revision_additive_max=max_revision,
                  annual_revision_not_component_sum_rows=annual_not_additive)
    # CNB report and cutoff clocks are reconstructed from frozen native timestamps.
    saved_clocks=read(evaluation/'cnb_clocks.csv')
    clocks=pd.to_datetime(forecasts.drop_duplicates('origin').set_index('origin').as_of_utc,utc=True)
    for r in saved_clocks.itertuples():
        day=r.report_date if r.clock=='report' else r.cutoff_date
        boundary=(pd.Timestamp(day)+pd.Timedelta(days=int(r.clock=='cutoff'))).tz_localize('Europe/Prague').tz_convert('UTC')
        eligible=clocks[clocks<boundary].sort_values()
        assert r.origin==eligible.index[-1]
        assert pd.Timestamp(r.as_of_utc)==eligible.iloc[-1]
    cnbs=read(ROOT/'data/cnb_mpr_cpi_quarterly.csv').set_index(['report_date','quarter'])
    pairs=read(evaluation/'cnb_pairs.csv')
    cindex=computed.set_index(['origin','model','target'])
    for r in pairs.itertuples():
        q=pd.Period(r.quarter,'Q'); months=pd.period_range(q.asfreq('M','start'),q.asfreq('M','end'),freq='M')
        truth=actual_yy.reindex(months).mean() if np.isfinite(actual_yy.reindex(months)).all() else np.nan
        cnb=float(cnbs.loc[(r.report_date,r.quarter),'value'])
        values=[actual_yy.get(t,np.nan) if t<pd.Period(r.origin,'M') else
                cindex.loc[(r.origin,r.model,str(t)),'yy_exante'] for t in months] if r.model!='cnb' else [cnb]
        pred=float(np.mean(values));same([r.forecast,r.realised,r.error],[pred,truth,pred-truth],'CNB raw arithmetic')
        same([r.abs_error_gain_vs_cnb],[abs(cnb-truth)-abs(pred-truth)],'CNB gain')
    groupcounts=pairs.groupby(['clock','report_date','quarter']).model.nunique()
    assert groupcounts.eq(len(roster)+1).all()
    cnbsummary=read(evaluation/'cnb_summary.csv'); summary_count=0
    crosskeys=pairs.groupby(['report_date','quarter']).clock.nunique()
    crosskeys=set(crosskeys[crosskeys.eq(2)].index)
    for r in cnbsummary.itertuples():
        own=pairs[pairs.clock.eq(r.clock)&pairs.model.eq(r.model)]
        if r.scope=='cross_clock_common': own=own[[k in crosskeys for k in zip(own.report_date,own.quarter)]]
        if r.sample=='reports_2024plus':own=own[own.report_date.ge('2024-01-01')]
        if str(r.quarters_ahead)!='all':own=own[own.quarters_ahead.eq(int(r.quarters_ahead))]
        for k,v in stats(own.error).items():same([getattr(r,k)],[v],'CNB summary '+k)
        summary_count+=1
    checks.update(cnb_pairs_verified=len(pairs),cnb_summary_rows_verified=summary_count,
                  cnb_clocks_verified=len(saved_clocks),cnb_pairs_per_clock=groupcounts.groupby('clock').size().to_dict())
    payload=json.loads((evaluation/'replay_data.json').read_text(encoding='utf-8'))
    html=(evaluation/'cnb_rounds_replayed_r18.html').read_text(encoding='utf-8')
    match=re.search(r'const DATA = (.*?);\s*const SERIES =',html,re.S)
    assert match, 'Cannot find embedded payload'
    embedded=json.loads(match.group(1))
    assert embedded.pop('reports')==payload['reportsByClock']['report'], 'Legacy reports alias differs'
    assert embedded==payload,'HTML payload differs from replay JSON'
    assert {x['id'] for x in payload['series'] if x['kind']=='model'}==set(roster)
    assert 'R18' in payload['title'] and 'constrained pool' not in ' '.join(payload['method'])
    assert 'Path selectors use only earlier fully matured' not in html
    checks['replay_payload_matches_json']=True
    # Food training ledgers must use past, released outcomes at the fit clock.
    food=read(ROOT/'output/research_r18_food/training_rows.csv')
    assert (food.target<food.fit_origin).all()
    fitclock=pd.to_datetime(food.fit_as_of,utc=True)
    for col in ['previous_release','current_release','feature_as_of']:
        assert (pd.to_datetime(food[col],utc=True)<=fitclock).all(),col
    for (_,_,origin),g in food.groupby(['fit_origin','model','origin']):
        assert set(g.h)==set(range(1,13))
        assert str(pd.Period(origin,'M')+12)<g.fit_origin.iloc[0]
    checks['food_training_rows_chronological']=len(food)
    signal_updates=json.loads((ROOT/'output/research_r18_category_verified/signal_updates.json').read_text())
    n_signal_labels=0
    for update in signal_updates:
        if update['status']!='estimated':
            assert np.asarray(update['correction']).shape==(12,)
            assert (np.asarray(update['correction'])==0).all()
            continue
        origin=update['origin'];clock=clocks.loc[origin].tz_convert('Europe/Prague').tz_localize(None)
        used=pd.DataFrame({k:update['training_'+k] for k in ['origins','targets','h','releases']})
        assert (used.targets<origin).all() and (used.origins<origin).all()
        assert (pd.PeriodIndex(used.targets,freq='M').asi8==pd.PeriodIndex(used.origins,freq='M').asi8+used.h).all()
        assert (pd.to_datetime(used.releases)<=clock).all()
        assert not used.duplicated(['origins','h']).any()
        assert used.groupby('h').size().between(24,96).all()
        n_signal_labels+=len(used)
    checks['category_signal_training_rows_chronological']=n_signal_labels
    checks['integration_has_no_model_fit']=True
    sources=[out/'manifest.json',evaluation/'input_manifest.json',Path(__file__),
             ROOT/'tools/research_r18/evaluate.py']
    checks['review_input_hashes']={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in sources}
    (OUT/'integration_verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps(checks,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--experiment',default='output/research_r18/path_v2')
    run(p.parse_args().experiment)
