"""Run the three prespecified R12 category equations, or --verify offline replay."""
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

from core_split_experiment import digest,read_frame,publication_dates,ROOT,FIX
from core_remainder_experiment import assess,diagnostics,dependency_hashes as reference_hashes
from data.core_split import load_frozen,monthly_rates,weights_at
from models.core_pooling_r12 import forecast_origin,VARIANTS
from models.core_remainder import forecast_origin as replay_origin
from models.core_tuning import hard_features

OUTPUT = ROOT/'output/research_r12/pooling'
REFERENCES = ('R9_BASE','R9_HALF','R9_FULL','TARGET_OWN')


def dependency_hashes():
    hashes = reference_hashes()
    for name in ('core_pooling_experiment_r12.py','models/core_pooling_r12.py',
                 'docs/implementation/R12_POOLING_SPEC.md','evaluation/core_split.py'):
        hashes[name] = digest(ROOT/name)
    return hashes


def paired_controls(pred,survey):
    rows = []
    for model in VARIANTS:
        for reference in ('TARGET_OWN','POOL_SEPARATE'):
            if model==reference:
                continue
            for frame,mask in [('all',np.ones(len(pred),bool)),
                               ('2024+',pred.index>=pd.Period('2024-01')),
                               ('big',(survey.actual-survey.survey_median).abs()>=.4-1e-9)]:
                a = (pred[model]-survey.actual).loc[mask]
                b = (pred[reference]-survey.actual).loc[mask]
                rows.append(dict(model=model,reference=reference,frame=frame,n=len(a),
                    delta_rmse=np.sqrt(np.mean(a**2))-np.sqrt(np.mean(b**2)),
                    delta_mae=a.abs().mean()-b.abs().mean(),
                    direction='negative is improvement'))
    return pd.DataFrame(rows)


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
    old = read_frame(ROOT/'output/core_split_forecasts.csv')
    own = pd.read_csv(ROOT/'output/core_split_core_predictions.csv',float_precision='round_trip')
    own = own[own.model=='TARGET_OWN'].set_index('period')
    expected = pd.period_range('2019-02','2026-07',freq='M')
    if not reference.index.equals(expected) or not old.index.equals(expected):
        raise ValueError('the declared 90 reference origins are required')
    dates = publication_dates(core.index)
    predictions,fits,contributions,coefficients,checks = [],[],[],[],[]
    for i,(t,ref) in enumerate(reference.iterrows()):
        clock = pd.Timestamp(ref.as_of_eve)
        if not clock<s._first_release_dt(t) or not clock<dates.loc[t]:
            raise ValueError(f'forecast clock is not pre-release: {t}')
        weights = weights_at(source['weights'],t,clock)
        x = s._mask_row_by_availability(hard_features(features),t,clock)
        replay = replay_origin(core,categories,x,dates,t,clock,weights,core_weight=ref.coreweight)
        diff = abs(replay['own_core']-own.loc[str(t),'core_forecast'])
        if not np.isfinite(diff) or diff>1e-12:
            raise AssertionError(f'R10 replay changed at {t}: {diff}')
        result = forecast_origin(core,categories,dates,t,clock,weights,core_weight=ref.coreweight)
        fixed = own.loc[str(t),'fixed_noncore']
        row = dict(period=str(t),**old.loc[t,list(REFERENCES)].to_dict())
        for name,cp in result['predictions'].items():
            row[name] = fixed+ref.coreweight*cp
        predictions.append(row)
        for bucket,key in ((fits,'fits'),(contributions,'contributions'),(coefficients,'coefficients')):
            bucket.extend(dict(period=str(t),**r) for r in result[key])
        checks.append(dict(period=str(t),as_of=clock,own_replay_difference=diff,
            target_reconciliation_difference=result['max_reconciliation_error']))
        if i%15==0:
            print(f'Completed {i+1}/90: {t}',flush=True)
    pred = pd.DataFrame(predictions).set_index('period')
    pred.index = pd.PeriodIndex(pred.index,freq='M')
    if not np.isfinite(pred.to_numpy()).all():
        raise AssertionError('a declared forecast is missing')
    audit = pd.DataFrame(fits)
    if not audit.fit_status.eq('estimated').all():
        raise AssertionError('a declared fit failed')
    if ((pd.PeriodIndex(audit.train_end,freq='M')>=pd.PeriodIndex(audit.period,freq='M')).any()
        or (pd.to_datetime(audit.training_last_release)>pd.to_datetime(audit.as_of)).any()):
        raise AssertionError('unavailable training labels used')
    # Save predictions before reading evaluation-only outcomes and consensus.
    pred.to_csv(destination/'forecasts.csv',index_label='period')
    survey = pd.read_csv(ROOT/'data/czcpmom_survey_history_extended.csv')
    survey = survey[survey.era!='flash_survey_suspect'].copy()
    survey.index = pd.PeriodIndex(survey.target_month,freq='M')
    if not survey.index.is_unique:
        raise ValueError('duplicate first-release survey')
    survey = survey.reindex(pred.index)
    assessment = assess(pred,survey)
    fixed = own.fixed_noncore.copy()
    fixed.index = pd.PeriodIndex(fixed.index,freq='M')
    tables = diagnostics(pred,survey,core.reindex(pred.index),reference.coreweight,fixed)
    tables.update(fit_audit=audit,contributions=pd.DataFrame(contributions),
        dynamic_coefficients=pd.DataFrame(coefficients),origin_checks=pd.DataFrame(checks),
        paired_controls=paired_controls(pred,survey))
    for name,table in tables.items():
        table.to_csv(destination/f'{name}.csv',index=False)
    for key in ('scores','release_rows','bootstrap'):
        assessment[key].to_csv(destination/f'{key}.csv',index=(key=='release_rows'),index_label='period')
    spec = dict(variants=list(VARIANTS),feature_columns=result['feature_columns'],
        gates=assessment['gates'],fallbacks=int((audit.fit_status!='estimated').sum()),
        status='Prespecified research comparison, no automatic operating promotion.',
        vintage_status='Latest-vintage R10 sources plus reconstructed release rules; reused history.')
    (destination/'specification.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
    outputs = {p.name:digest(p) for p in sorted(destination.glob('*.csv'))}
    outputs['specification.json'] = digest(destination/'specification.json')
    manifest = dict(created_at_utc=datetime.now(timezone.utc).isoformat(),inputs=hashes,outputs=outputs,
                    maximum_own_replay_difference=max(r['own_replay_difference'] for r in checks))
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(assessment['scores'].query("coverage=='common' and frame in ['all','2024+','big','big_up','big_down']")
        [['model','frame','n','rmse','mae','direction','material_win','material_loss']].to_string(index=False))
    return manifest


def verify():
    frozen = json.loads((OUTPUT/'manifest.json').read_text())
    for name,expected in frozen['inputs'].items():
        if digest(ROOT/name)!=expected:
            raise ValueError(f'dependency changed: {name}')
    for name,expected in frozen['outputs'].items():
        if digest(OUTPUT/name)!=expected:
            raise ValueError(f'output changed: {name}')
    def forbidden(*args,**kwargs):
        raise AssertionError('offline replay attempted network or database access')
    with tempfile.TemporaryDirectory(prefix='cz_pooling_') as temporary, ExitStack() as stack:
        for target in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(target,side_effect=forbidden))
        replay = run(Path(temporary))
    if replay['outputs']!=frozen['outputs']:
        raise AssertionError('R12 output replay mismatch')
    print(f"Offline replay: {len(frozen['outputs'])} output files byte-identical.")


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    args = parser.parse_args()
    verify() if args.verify else run()
