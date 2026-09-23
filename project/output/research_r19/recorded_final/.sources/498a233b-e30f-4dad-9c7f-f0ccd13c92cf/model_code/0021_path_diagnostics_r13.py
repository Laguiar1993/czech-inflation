"""Descriptive professional-benchmark diagnostics; no fitting or shock identification."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _clock(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError('valid timezone-aware clock required')
    return stamp.tz_convert('UTC')


def prepare_rows(source):
    required = {'model','report_date','report_clock_utc','origin','as_of_utc',
                'quarter','quarters_ahead','forecast','cnb','realised','complete'}
    if not required.issubset(source.columns):
        raise ValueError(f'missing columns: {sorted(required-set(source.columns))}')
    rows = source.loc[source.model.eq('INDEPENDENT_BRIDGE')].copy()
    if rows.empty:
        raise ValueError('no independent bridge rows')
    if rows.duplicated(['report_date','quarter']).any():
        raise ValueError('duplicate report/quarter forecasts')
    for col in ('report_clock_utc','as_of_utc'):
        rows[col] = pd.to_datetime(rows[col].map(_clock), utc=True)
    if not (rows.as_of_utc < rows.report_clock_utc).all():
        raise ValueError('model clock must be before report publication')
    if rows.groupby('origin').as_of_utc.nunique().gt(1).any():
        raise ValueError('archived origin has conflicting clocks')
    report_days = rows.report_clock_utc.dt.tz_convert('Europe/Prague').dt.strftime('%Y-%m-%d')
    if not report_days.eq(rows.report_date).all():
        raise ValueError('report clock does not match local report date')
    rows['report_year'] = pd.to_datetime(rows.report_date).dt.year
    rows['target_year'] = pd.PeriodIndex(rows.quarter, freq='Q').year
    for col in ('forecast','cnb','realised'):
        rows[col] = pd.to_numeric(rows[col], errors='raise')
        if np.isinf(rows[col]).any():
            raise ValueError('infinite forecasts or outcomes')
    for _, group in rows.groupby('quarter'):
        outcomes = group.realised.dropna().to_numpy()
        if len(outcomes) and not np.allclose(outcomes, outcomes[0], rtol=0, atol=1e-10):
            raise ValueError('inconsistent realised outcomes for same quarter')
    complete = rows.complete.map(lambda x: str(x).lower())
    if not complete.isin(['true','false']).all():
        raise ValueError('complete must be boolean')
    rows['forecast_available'] = complete.eq('true') & rows[['forecast','cnb']].notna().all(axis=1)
    rows['scored'] = rows.forecast_available & rows.realised.notna()
    rows['age_days'] = (rows.report_clock_utc-rows.as_of_utc).dt.total_seconds()/86400
    rows['disagreement'] = (rows.forecast-rows.cnb).where(rows.forecast_available)
    rows['model_error'] = (rows.forecast-rows.realised).where(rows.scored)
    rows['cnb_error'] = (rows.cnb-rows.realised).where(rows.scored)
    rows['model_squared_error'] = rows.model_error**2
    rows['cnb_squared_error'] = rows.cnb_error**2
    rows['disagreement_squared'] = rows.disagreement**2
    rows['cross_term'] = 2*rows.cnb_error*rows.disagreement
    rows['abs_error_gain'] = rows.cnb_error.abs()-rows.model_error.abs()
    rows['squared_error_gain'] = rows.cnb_squared_error-rows.model_squared_error
    rows['same_error_direction'] = rows.scored & (rows.model_error*rows.cnb_error > 0)
    rows['shared_large_miss'] = rows.same_error_direction & rows.model_error.abs().ge(.5-1e-9) & rows.cnb_error.abs().ge(.5-1e-9)
    rows['close_agreement'] = rows.forecast_available & rows.disagreement.abs().le(.25+1e-9)
    scored = rows.loc[rows.scored]
    if not np.allclose(scored.model_error, scored.cnb_error+scored.disagreement, rtol=0, atol=1e-10):
        raise AssertionError('error identity failed')
    if not np.allclose(scored.model_squared_error,
                       scored.cnb_squared_error+scored.disagreement_squared+scored.cross_term,
                       rtol=0, atol=1e-10):
        raise AssertionError('squared error identity failed')
    return rows.sort_values(['report_date','quarter']).reset_index(drop=True)


def _mean(values):
    return float(values.mean()) if len(values) else np.nan


def _summary(group, panel, horizon):
    agreement = group.loc[group.forecast_available]
    scored = group.loc[group.scored]
    result = dict(panel=panel,horizon=str(horizon),n_source=len(group),
                  n_agreement=len(agreement),n_scored=len(scored),
                  n_unique_quarters=scored.quarter.nunique(),
                  n_reports=scored.report_date.nunique(),n_model_origins=scored.origin.nunique(),
                  same_error_direction=int(scored.same_error_direction.sum()),
                  shared_large_miss=int(scored.shared_large_miss.sum()),
                  close_agreement=int(agreement.close_agreement.sum()),
                  model_closer=int((scored.abs_error_gain>1e-9).sum()),
                  cnb_closer=int((scored.abs_error_gain < -1e-9).sum()),
                  mean_abs_error_gain=_mean(scored.abs_error_gain),
                  model_mse=_mean(scored.model_squared_error),cnb_mse=_mean(scored.cnb_squared_error),
                  disagreement_mse=_mean(scored.disagreement_squared),
                  mean_cross_term=_mean(scored.cross_term),
                  disagreement_rmse=float(np.sqrt(_mean(agreement.disagreement_squared))),
                  disagreement_mae=_mean(agreement.disagreement.abs()))
    for family in ('model','cnb'):
        err = scored[f'{family}_error']
        result.update({family+'_rmse':float(np.sqrt(_mean(err**2))),
                       family+'_mae':_mean(err.abs()),family+'_bias':_mean(err)})
    for label, q in [('min',0),('median',.5),('p90',.9),('max',1)]:
        result['age_days_'+label] = float(agreement.age_days.quantile(q)) if len(agreement) else np.nan
    return result


def summarise(rows):
    panels = [('all_reports',rows),('recent_reports',rows.loc[rows.report_date>='2024-01-01'])]
    for key in ('report_year','target_year'):
        panels.extend((f'{key}_{year}',group) for year,group in rows.groupby(key,sort=True))
    out = []
    for label, group in panels:
        out.append(_summary(group,label,'all'))
        for h in (1,2,3,4):
            out.append(_summary(group.loc[group.quarters_ahead.eq(h)],label,h))
    return pd.DataFrame(out)


def revision_rows(rows):
    result = []
    for quarter, group in rows.groupby('quarter',sort=True):
        ordered = group.sort_values('report_date').reset_index(drop=True)
        for i in range(1,len(ordered)):
            old,new = ordered.iloc[i-1],ordered.iloc[i]
            available = bool(old.forecast_available and new.forecast_available)
            scored = bool(old.scored and new.scored)
            mr = new.forecast-old.forecast if available else np.nan
            cr = new.cnb-old.cnb
            result.append(dict(quarter=quarter,previous_report=old.report_date,report_date=new.report_date,
                previous_model_origin=old.origin,model_origin=new.origin,
                previous_model_clock=old.as_of_utc,model_clock=new.as_of_utc,
                model_origin_changed=bool(old.origin != new.origin),revision_available=available,
                model_revision=mr,cnb_revision=cr,same_revision_direction=bool(mr*cr>0),
                previous_disagreement=old.disagreement,disagreement=new.disagreement,
                model_abs_error_improvement=abs(old.model_error)-abs(new.model_error) if scored else np.nan,
                cnb_abs_error_improvement=abs(old.cnb_error)-abs(new.cnb_error) if scored else np.nan,
                scored=scored))
    return pd.DataFrame(result,columns=['quarter','previous_report','report_date',
        'previous_model_origin','model_origin','previous_model_clock','model_clock',
        'model_origin_changed','revision_available','model_revision','cnb_revision','same_revision_direction',
        'previous_disagreement','disagreement','model_abs_error_improvement',
        'cnb_abs_error_improvement','scored'])
