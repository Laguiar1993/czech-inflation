"""R11 bounded remainder diagnostic, preserving all frozen R9/R10 results.

Run this file to regenerate output/core_remainder, or --verify for an exact
offline replay. Survey values are read for scoring only after all fits finish.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from core_split_experiment import digest, read_frame, publication_dates, component_evidence, ROOT, FIX
from data.core_split import load_frozen, monthly_rates, weights_at
from evaluation.core_split import evaluate, _score
from models.core_remainder import forecast_origin
from models.core_tuning import hard_features

OUTPUT = ROOT/'output/core_remainder'
REFERENCES = ('R9_BASE','R9_HALF','R9_FULL','TARGET_OWN','TARGET_OWN_HALF','TARGET_CHANNEL')


def assess(pred, survey):
    result = evaluate(pred, survey)
    events = result['release_rows']
    rows = []
    for model, group in events.groupby('model', sort=False):
        for coverage, eligible in [('own',group.valid),('common',group.common_valid)]:
            for frame, sign in [('big_up',group.surprise>0),('big_down',group.surprise<0)]:
                rows.append(_score(group.loc[eligible & group.big & sign], model, frame, coverage))
    result['scores'] = pd.concat([result['scores'],pd.DataFrame(rows)], ignore_index=True)
    return result


def diagnostics(pred, survey, core_actual, weights, fixed):
    core_rows, errors, scores, influence = [], [], [], []
    reference_core = (pred.R9_BASE-fixed)/weights
    big = (survey.actual-survey.survey_median).abs()>=.4-1e-9
    frames = {'all':np.ones(len(pred),bool), '2024+':pred.index>=pd.Period('2024-01'),
              'ex_jan':pred.index.month!=1, 'flash2025+':pred.index>=pd.Period('2025-01'),
              'big':big, 'big_up':big & (survey.actual>survey.survey_median),
              'big_down':big & (survey.actual<survey.survey_median)}
    for model in pred:
        cp = (pred[model]-fixed)/weights
        ev = component_evidence(reference_core,cp,core_actual,weights,fixed,survey.actual)
        error = pred[model]-survey.actual
        if (error-ev['weighted_core_error']-ev['noncore_reconciliation_error']).abs().max()>1e-10:
            raise AssertionError('headline error decomposition failed')
        if (ev['headline_squared_gain']-ev['weighted_core_squared_gain']-ev['cross_term_gain']).abs().max()>1e-10:
            raise AssertionError('squared error decomposition failed')
        core_rows.append(pd.DataFrame(dict(period=pred.index.astype(str),model=model,
            core_forecast=cp.to_numpy(),core_actual=core_actual.to_numpy(),core_weight=weights.to_numpy())))
        errors.append(pd.DataFrame(dict(period=pred.index.astype(str),model=model,error=error.to_numpy(),
                                       **{k:v.to_numpy() for k,v in ev.items()})))
        for frame, mask in frames.items():
            e = (cp-core_actual).loc[mask].dropna()
            scores.append(dict(model=model,frame=frame,n=len(e),
                rmse=float(np.sqrt(np.mean(e**2))) if len(e) else np.nan,
                mae=float(e.abs().mean()) if len(e) else np.nan))
        for omitted in pred.index:
            mask = pred.index!=omitted
            base_rmse = np.sqrt(np.mean((pred.R9_BASE-survey.actual).loc[mask]**2))
            candidate_rmse = np.sqrt(np.mean(error.loc[mask]**2))
            influence.append(dict(model=model,omitted_period=str(omitted),reference_rmse=base_rmse,
                                  candidate_rmse=candidate_rmse,relative_rmse_gain=1-candidate_rmse/base_rmse))
    return dict(core_predictions=pd.concat(core_rows,ignore_index=True),
                component_errors=pd.concat(errors,ignore_index=True),core_scores=pd.DataFrame(scores),
                leave_one_out=pd.DataFrame(influence))


def dependency_hashes():
    old = json.loads((ROOT/'output/core_split_manifest.json').read_text())
    hashes = dict(old['inputs'])
    hashes.update({f'output/{k}':v for k,v in old['outputs'].items()})
    hashes['output/core_split_gates.json'] = old['gates_sha256']
    for name in ('output/core_split_manifest.json','core_remainder_experiment.py','models/core_remainder.py',
                 'docs/implementation/CORE_REMAINDER_PLAN_2026-09-09.md'):
        hashes[name] = digest(ROOT/name)
    for name, expected in hashes.items():
        if digest(ROOT/name)!=expected:
            raise ValueError(f'frozen dependency changed: {name}')
    return hashes


def run(destination=OUTPUT):
    import cz_struct as s
    hashes = dependency_hashes()
    destination = Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    source = load_frozen()
    categories = monthly_rates(source['levels'])
    core = read_frame(FIX/'cnb_core_mm.csv').iloc[:,0]
    features = read_frame(FIX/'core_features.csv')
    reference = read_frame(ROOT/'output/independent_nowcast_forecasts.csv')
    old_forecasts = read_frame(ROOT/'output/core_split_forecasts.csv')
    old_core = pd.read_csv(ROOT/'output/core_split_core_predictions.csv',float_precision='round_trip')
    old_core = old_core[old_core.model=='TARGET_OWN'].set_index('period')
    expected_periods = pd.period_range('2019-02','2026-07',freq='M')
    if not reference.index.equals(expected_periods) or not old_forecasts.index.equals(expected_periods):
        raise ValueError('experiment requires the declared 90 matching origins')
    dates = publication_dates(core.index)
    predictions, fits, contributions, checks = [], [], [], []
    for i,(t,ref) in enumerate(reference.iterrows()):
        clock = pd.Timestamp(ref.as_of_eve)
        if not clock<s._first_release_dt(t) or not clock<dates.loc[t]:
            raise ValueError(f'origin no longer before its first/detail release: {t}')
        x = s._mask_row_by_availability(hard_features(features),t,clock)
        weights = weights_at(source['weights'],t,clock)
        result = forecast_origin(core,categories,x,dates,t,clock,weights,core_weight=ref.coreweight)
        own_difference = abs(result['own_core']-old_core.loc[str(t),'core_forecast'])
        if own_difference>1e-12 or not np.isfinite(own_difference):
            raise AssertionError(f'R10 own-category replay changed: {t} {own_difference}')
        fixed = old_core.loc[str(t),'fixed_noncore']
        row = dict(period=str(t),**old_forecasts.loc[t,list(REFERENCES)].to_dict())
        for name,cp in result['predictions'].items():
            row[name] = fixed+ref.coreweight*cp
            row[name+'_HALF'] = .5*ref.HARD_BASE+.5*row[name]
        predictions.append(row)
        fits.extend(dict(period=str(t),as_of=clock,**entry) for entry in result['fits'])
        contributions.extend(dict(period=str(t),as_of=clock,**entry) for entry in result['contributions'])
        checks.append(dict(period=str(t),as_of=clock,own_replay_difference=own_difference,
                           reconciliation_difference=result['max_reconciliation_error']))
        if i%15==0:
            print(f'Completed {i+1}/{len(reference)}: {t}',flush=True)
    pred = pd.DataFrame(predictions).set_index('period')
    pred.index = pd.PeriodIndex(pred.index,freq='M')
    if not np.isfinite(pred.to_numpy()).all():
        raise AssertionError('a declared forecast is missing')
    audit = pd.DataFrame(fits)
    if not audit.fit_status.eq('estimated').all():
        raise AssertionError('a declared fit failed')
    if ((pd.PeriodIndex(audit.train_end,freq='M')>=pd.PeriodIndex(audit.period,freq='M')).any()
            or (pd.to_datetime(audit.training_last_release)>pd.to_datetime(audit.as_of)).any()):
        raise AssertionError('unavailable training label')
    # Only now parse the scoring survey/outcomes; none enters a predictor or fit.
    survey = pd.read_csv(ROOT/'data/czcpmom_survey_history_extended.csv')
    survey = survey[survey.era!='flash_survey_suspect'].copy()
    survey.index = pd.PeriodIndex(survey.target_month,freq='M')
    if not survey.index.is_unique:
        raise ValueError('duplicate first-release survey')
    survey = survey.reindex(pred.index)
    assessment = assess(pred,survey)
    fixed = old_core.fixed_noncore.copy()
    fixed.index = pd.PeriodIndex(fixed.index,freq='M')
    aux = diagnostics(pred,survey,core.reindex(pred.index),reference.coreweight,fixed)
    pred.to_csv(destination/'forecasts.csv',index_label='period')
    audit.to_csv(destination/'fit_audit.csv',index=False)
    pd.DataFrame(contributions).to_csv(destination/'contributions.csv',index=False)
    pd.DataFrame(checks).to_csv(destination/'origin_checks.csv',index=False)
    for name,table in aux.items():
        table.to_csv(destination/f'{name}.csv',index=False)
    for key in ('scores','release_rows','bootstrap'):
        assessment[key].to_csv(destination/f'{key}.csv',index=(key=='release_rows'),index_label='period')
    details = dict(feature_columns=result['feature_columns'],gates=assessment['gates'],
        status='Diagnostic experiment only; no automatic operating-model promotion.',
        vintage_status='R10 latest-vintage inputs plus reconstructed release rules; no untouched holdout.')
    (destination/'specification.json').write_text(json.dumps(details,indent=2),encoding='utf-8')
    outputs = {p.name:digest(p) for p in sorted(destination.glob('*.csv'))}
    outputs['specification.json'] = digest(destination/'specification.json')
    manifest = dict(created_at_utc=datetime.now(timezone.utc).isoformat(),inputs=hashes,outputs=outputs,
                    maximum_own_replay_difference=max(r['own_replay_difference'] for r in checks))
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(assessment['scores'].query("coverage=='common' and frame in ['all','big','big_up','big_down']")
          [['model','frame','n','rmse','mae','direction','material_win','material_loss']].to_string(index=False))
    return manifest


def verify():
    frozen = json.loads((OUTPUT/'manifest.json').read_text())
    for name,expected in frozen['inputs'].items():
        if digest(ROOT/name)!=expected:
            raise ValueError(f'R11 dependency changed: {name}')
    for name,expected in frozen['outputs'].items():
        if digest(OUTPUT/name)!=expected:
            raise ValueError(f'R11 output changed: {name}')
    def forbidden(*args,**kwargs):
        raise AssertionError('offline replay attempted network/database access')
    with tempfile.TemporaryDirectory(prefix='cz_remainder_') as temporary, ExitStack() as stack:
        for target in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(target,side_effect=forbidden))
        replay = run(Path(temporary))
    if replay['outputs']!=frozen['outputs']:
        raise AssertionError('R11 frozen output replay mismatch')
    print(f"Offline replay: {len(frozen['outputs'])} output files byte-identical; R9/R10 unchanged.")


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    args = parser.parse_args()
    verify() if args.verify else run()
