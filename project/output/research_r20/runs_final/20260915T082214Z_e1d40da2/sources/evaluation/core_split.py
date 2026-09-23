"""Pure R10 forecast evaluation; no fitting, file access, or model selection.

Forecasts and survey outcomes are monthly rates in percentage points. This
module retains the R9 event conventions while reporting both each model's own
finite sample and the finite intersection of every submitted model. Practical
gates and descriptive bootstrap intervals are exploratory, not selection-
adjusted evidence from an untouched holdout.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


REFERENCE = 'R9_BASE'
EVENT_TOLERANCE = 1e-9
BOOTSTRAP_DRAWS = 5000
BOOTSTRAP_SEED = 42
BLOCK_LENGTHS = (3, 6, 12)
SELECTION_STATUS = (
    'exploratory; no untouched historical holdout; multiple comparisons are '
    'not selection-adjusted'
)
BOOTSTRAP_COLUMNS = [
    'candidate', 'reference', 'frame', 'block', 'n', 'delta', 'lower', 'upper',
    'draws', 'seed', 'coverage', 'selection_status',
]


def _monthly_index(frame: pd.DataFrame, name: str) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError(f'{name} must be a DataFrame')
    index = frame.index
    if not isinstance(index, pd.PeriodIndex) or index.freqstr != 'M':
        raise ValueError(f'{name} requires a monthly PeriodIndex')
    if not index.is_unique or index.hasnans:
        raise ValueError(f'{name} requires unique, nonmissing monthly labels')
    if not frame.columns.is_unique:
        raise ValueError(f'{name} requires unique columns')


def _numeric(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in frame.dtypes):
        raise ValueError(f'{name} must contain numeric values only')
    if any(pd.api.types.is_complex_dtype(dtype) for dtype in frame.dtypes):
        raise ValueError(f'{name} must contain real numeric values only')
    values = frame.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(values).any():
        raise ValueError(f'{name} contains infinity; only finite values or missing values are allowed')
    return pd.DataFrame(values, index=frame.index.copy(), columns=frame.columns.copy())


def _inputs(predictions: pd.DataFrame, survey: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    _monthly_index(predictions, 'predictions')
    if predictions.empty:
        raise ValueError('predictions must contain a nonempty contiguous monthly sample')
    expected = pd.period_range(predictions.index[0], periods=len(predictions), freq='M')
    if not predictions.index.equals(expected):
        raise ValueError('predictions must have ascending contiguous monthly labels')
    if REFERENCE not in predictions:
        raise ValueError(f'predictions must include reference {REFERENCE}')
    if 'CONSENSUS' in predictions:
        raise ValueError('CONSENSUS is reserved and added from survey_median')
    if any(not isinstance(c, str) or not c for c in predictions.columns):
        raise ValueError('predictions must contain named model columns only')
    _monthly_index(survey, 'survey')
    if not {'actual', 'survey_median'}.issubset(survey.columns):
        raise ValueError('survey must include actual and survey_median')
    if (len(survey) != len(predictions)
            or not survey.index.sort_values().equals(predictions.index)):
        raise ValueError('survey requires the same unique monthly labels as predictions')
    return (_numeric(predictions, 'predictions'),
            _numeric(survey.reindex(predictions.index)[['actual', 'survey_median']], 'survey'))


def _events(model: str, forecast: pd.Series, survey: pd.DataFrame,
            common: pd.Series) -> pd.DataFrame:
    valid = forecast.notna() & survey.notna().all(axis=1)
    error = (forecast - survey.actual).where(valid)
    surprise = (survey.actual - survey.survey_median).where(valid)
    deviation = (forecast - survey.survey_median).where(valid)
    gain = surprise.abs() - error.abs()
    big = valid & (surprise.abs() >= .4 - EVENT_TOLERANCE)
    alert = valid & (deviation.abs() >= .2 - EVENT_TOLERANCE)
    result = pd.DataFrame({
        'model': model, 'actual': survey.actual, 'survey_median': survey.survey_median,
        'consensus': survey.survey_median, 'forecast': forecast,
        'valid': valid, 'common_valid': common, 'error': error, 'surprise': surprise,
        'deviation': deviation, 'gain': gain, 'big': big, 'alert': alert,
        'capture_ratio': deviation.div(surprise.where(big)),
        'closer': valid & (gain > EVENT_TOLERANCE),
        'material_win': valid & (gain >= .15 - EVENT_TOLERANCE),
        'material_loss': valid & (gain <= -.15 + EVENT_TOLERANCE),
        'direction': valid & (deviation * surprise > 0),
        'false_alarm': valid & alert & ~big,
    })
    result.index.name = 'period'
    return result


def _score(events: pd.DataFrame, model: str, frame: str, coverage: str) -> dict:
    n = len(events)
    alerts = int(events.alert.sum())
    big = int(events.big.sum())
    alerted_big = int((events.alert & events.big).sum())
    return {
        'model': model, 'frame': frame, 'coverage': coverage, 'n': n,
        'rmse': float(np.sqrt(np.mean(events.error.to_numpy() ** 2))) if n else np.nan,
        'mae': float(events.error.abs().mean()) if n else np.nan,
        'bias': float(events.error.mean()) if n else np.nan,
        'mean_gain': float(events.gain.mean()) if n else np.nan,
        'total_gain': float(events.gain.sum()),
        'closer': int(events.closer.sum()),
        'material_win': int(events.material_win.sum()),
        'material_loss': int(events.material_loss.sum()),
        'direction': int(events.direction.sum()),
        'alerts': alerts, 'alerted_big': alerted_big,
        'false_alarm': int(events.false_alarm.sum()),
        'missed_big': int((~events.alert & events.big).sum()),
        'big_precision': alerted_big / alerts if alerts else np.nan,
        'big_recall': alerted_big / big if big else np.nan,
    }


def _bootstrap(predictions: pd.DataFrame, survey: pd.DataFrame) -> pd.DataFrame:
    """Circular blocks of consecutive eligible paired releases, including wraparound.

    Missing pairs are removed before drawing, following the R9 convention;
    blocks therefore count observed releases and can span missing calendar months.
    A negative delta is lower candidate RMSE. Intervals are percentile 95% and
    descriptive only. The same indices are applied to both forecast errors.
    """
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    reference_error = predictions[REFERENCE] - survey.actual
    rows = []
    for candidate in predictions.columns.drop(REFERENCE):
        candidate_error = predictions[candidate] - survey.actual
        paired = (candidate_error.notna() & reference_error.notna()
                  & survey.survey_median.notna())
        for frame, calendar in (
            ('all', np.ones(len(predictions), dtype=bool)),
            ('2024+', predictions.index >= pd.Period('2024-01', freq='M')),
        ):
            mask = paired & calendar
            ae = candidate_error[mask].to_numpy()
            be = reference_error[mask].to_numpy()
            n = len(ae)
            observed = float(np.sqrt(np.mean(ae ** 2)) - np.sqrt(np.mean(be ** 2))) if n else np.nan
            for block in BLOCK_LENGTHS:
                lower = upper = np.nan
                if n:
                    starts = rng.integers(0, n, (BOOTSTRAP_DRAWS, int(np.ceil(n / block))))
                    indices = ((starts[:, :, None] + np.arange(block)) % n).reshape(BOOTSTRAP_DRAWS, -1)[:, :n]
                    deltas = np.sqrt(np.mean(ae[indices] ** 2, axis=1)) - np.sqrt(np.mean(be[indices] ** 2, axis=1))
                    lower, upper = map(float, np.quantile(deltas, [.025, .975]))
                rows.append({
                    'candidate': candidate, 'reference': REFERENCE, 'frame': frame,
                    'block': block, 'n': n, 'delta': observed, 'lower': lower, 'upper': upper,
                    'draws': BOOTSTRAP_DRAWS, 'seed': BOOTSTRAP_SEED,
                    'coverage': 'pairwise', 'selection_status': SELECTION_STATUS,
                })
    return pd.DataFrame(rows, columns=BOOTSTRAP_COLUMNS)


def _relative_change(candidate: float, reference: float) -> float:
    if not np.isfinite(candidate) or not np.isfinite(reference):
        return np.nan
    if reference == 0:
        return 0. if candidate == 0 else np.nan
    return float(candidate / reference - 1)


def _gates(scores: pd.DataFrame, candidates: pd.Index) -> dict:
    common = scores[scores.coverage.eq('common')].set_index(['model', 'frame'])
    reference = common.loc[(REFERENCE, 'all')]
    recent_reference = common.loc[(REFERENCE, '2024+')]
    gates = {}
    for candidate in candidates:
        current = common.loc[(candidate, 'all')]
        recent = common.loc[(candidate, '2024+')]
        rmse_pass = bool(current.n > 0 and reference.rmse > 0
                         and current.rmse <= .98 * reference.rmse + 1e-12)
        mae_pass = bool(current.n > 0 and current.mae <= 1.02 * reference.mae + 1e-12)
        recent_pass = bool(recent.n > 0 and recent.rmse <= 1.05 * recent_reference.rmse + 1e-12)
        gates[candidate] = {
            'candidate': candidate, 'reference': REFERENCE, 'coverage': 'common',
            'pass': rmse_pass and mae_pass and recent_pass,
            'rmse_gain_pass': rmse_pass, 'mae_pass': mae_pass, 'recent_rmse_pass': recent_pass,
            'rmse_gain_all': -_relative_change(current.rmse, reference.rmse),
            'mae_deterioration_all': _relative_change(current.mae, reference.mae),
            'rmse_deterioration_recent': _relative_change(recent.rmse, recent_reference.rmse),
            'n_all': int(current.n), 'n_recent': int(recent.n),
            'rule': 'All RMSE gain >=2%; all MAE deterioration <=2%; 2024+ RMSE deterioration <=5%',
            'selection_status': SELECTION_STATUS,
        }
    return gates


def evaluate(predictions: pd.DataFrame, survey: pd.DataFrame) -> dict:
    """Evaluate submitted model columns without modifying inputs or any files.

    ``predictions`` must have a unique ascending contiguous monthly PeriodIndex,
    unique numeric model columns, and an ``R9_BASE`` reference. Include R9_HALF
    and R9_FULL as ordinary model columns when evaluating those alternatives.
    ``survey`` must uniquely match the same months and contain numeric ``actual``
    and ``survey_median`` columns. NaNs represent unavailable observations;
    infinity is rejected. Survey rows may arrive in a different order.

    Returns ``scores`` (model/frame/coverage rows), ``release_rows`` (long monthly
    diagnostics, including invalid observations for audit), ``bootstrap``
    (paired candidate-minus-R9_BASE RMSE differences), and ``gates`` (one dict per
    submitted candidate). Own/common scores both require finite actual, median,
    and forecast. The common sample requires every submitted forecast, and is
    fixed before CONSENSUS is appended. Gates use only common coverage.
    """
    forecasts, outcomes = _inputs(predictions, survey)
    candidates = forecasts.columns.drop(REFERENCE)
    common = forecasts.notna().all(axis=1) & outcomes.notna().all(axis=1)
    with_consensus = forecasts.assign(CONSENSUS=outcomes.survey_median)
    events, rows = [], []
    for model, forecast in with_consensus.items():
        release = _events(model, forecast, outcomes, common)
        events.append(release)
        frames = {
            'all': np.ones(len(forecasts), dtype=bool),
            'ex_jan': forecasts.index.month != 1,
            '2024+': forecasts.index >= pd.Period('2024-01', freq='M'),
            'flash2025+': forecasts.index >= pd.Period('2025-01', freq='M'),
            'big': release.big,
            'big_ex_jan': release.big & (forecasts.index.month != 1),
            'alerts': release.alert,
        }
        for coverage, eligible in (('own', release.valid), ('common', common)):
            for frame, mask in frames.items():
                rows.append(_score(release.loc[eligible & mask], model, frame, coverage))
    scores = pd.DataFrame(rows)
    return {
        'scores': scores,
        'release_rows': pd.concat(events),
        'bootstrap': _bootstrap(forecasts, outcomes),
        'gates': _gates(scores, candidates),
    }
