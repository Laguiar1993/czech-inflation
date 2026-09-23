"""Pure, dated R34 statistical context; never fit or promote a forecast model."""
from datetime import datetime, timedelta, timezone
import math
import re

COMPONENTS = ('core', 'food', 'alcohol_tobacco', 'administered', 'fuel', 'wedge')
WEIGHT_KEYS = dict(core='core', food='food', alcohol_tobacco='alc', administered='administered', fuel='fuel')
ERROR_LIMITATIONS = (
    'Fixed central 80% empirical historical-error offsets (actual minus forecast), not '
    'calibrated prospective probabilities or confidence intervals for a mean. '
    'Historical release-eve nowcasts differ from the current mid-month decision clock. '
    'Overlapping path errors are dependent. Outcomes and reconstructed inputs use the '
    'retained latest vintage; receipt gating does not recreate historical data vintages.'
)


def month_number(value):
    value = str(value)
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value):
        raise ValueError('Expected canonical YYYY-MM: ' + value)
    return int(value[:4])*12 + int(value[5:])-1


def month_offset(value, offset):
    n = month_number(value)+offset
    return f'{n//12:04d}-{n%12+1:02d}'


def clock(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('as_of/receipt timestamp must include a timezone')
    return result.astimezone(timezone.utc)


def number(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a rate')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Rate must be finite')
    return value


def monthly_pairs(values, *, finite=True):
    """Mapping, pandas Series, or pair sequence; reject duplicates before dict coercion."""
    pairs = values.items() if hasattr(values, 'items') else values
    result = {}
    for key, value in pairs:
        key = str(key)
        month_number(key)
        if key in result:
            raise ValueError('Duplicate month: ' + key)
        result[key] = number(value) if finite else float(value)
    return dict(sorted(result.items()))


def base_effect_ledger(history_mm, forecast_mm):
    """Exact y/y recurrence for 1..13 contiguous forecast months (h0..h12).

    History must contain the prior 12 monthly rates, with no rows on/after h0.
    At h12 the outgoing print is forecast h0, never a future realised value.
    Units are percent for rates and percentage points for additive effects.
    """
    history = monthly_pairs(history_mm)
    forecast = monthly_pairs(forecast_mm)
    if not 1 <= len(forecast) <= 13:
        raise ValueError('Forecast must contain 1..13 months (through h12)')
    origin = next(iter(forecast))
    if any(m >= origin for m in history):
        raise ValueError('Realised history must end before forecast origin')
    if list(forecast) != [month_offset(origin, i) for i in range(len(forecast))]:
        raise ValueError('Forecast contains a month gap')
    prior = [month_offset(origin, i) for i in range(-12, 0)]
    if any(m not in history for m in prior):
        raise ValueError('Missing monthly print in initial annual window')
    if any(v <= -100 for v in [*history.values(), *forecast.values()]):
        raise ValueError('Monthly gross price factor must be positive')
    previous = 100*(math.prod(1+history[m]/100 for m in prior)-1)
    combined = dict(history)
    rows = []
    for h, (month, mm) in enumerate(forecast.items()):
        old = combined[month_offset(month, -12)]
        removed = (100+previous)/(1+old/100)-100
        annual = (100+removed)*(1+mm/100)-100
        if not math.isfinite(annual):
            raise ValueError('Non-finite compounded annual rate')
        rows.append(dict(month=month, h=h, mm=mm, dropout_mm=old,
                         previous_yy=previous, base_effect_pp=removed-previous,
                         new_price_pp=annual-removed, change_pp=annual-previous, yy=annual))
        combined[month] = mm
        previous = annual
    return rows


def receipt(target, release_calendar=None):
    """Date-only records are usable after their UTC date completes, not at midnight start."""
    raw = (release_calendar or {}).get(target)
    if isinstance(raw, dict):
        raw = raw.get('detail_release_dt') or raw.get('available_at')
    if raw:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(raw)):
            available = datetime.fromisoformat(str(raw)).replace(tzinfo=timezone.utc)+timedelta(days=1)
            rule = 'calendar_date_end'
        else:
            available, rule = clock(raw), 'calendar_timestamp'
        target_end = datetime.fromisoformat(month_offset(target, 1)+'-01T00:00:00+00:00')
        if available < target_end:
            raise ValueError('Outcome receipt precedes completion of its target month')
        return available, rule
    # End of target+1 month: never assume a release on its first day.
    return datetime.fromisoformat(month_offset(target, 2)+'-01T00:00:00+00:00'), 'following_month_end'


def quantile(values, probability):
    values = sorted(values)
    index = (len(values)-1)*probability
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo]+(values[hi]-values[lo])*(index-lo)


def empirical_ranges(errors, *, as_of, release_calendar=None):
    """Rows: origin,target,h,forecast,actual. One fixed model per horizon, no pooling.

    Return all h0..h12 for full and 2024plus; <20 finite, released outcomes are
    unavailable. Offset bounds are added to a like-unit point forecast by the UI.
    """
    decision = clock(as_of)
    if hasattr(errors, 'to_dict'):
        errors = errors.to_dict('records')
    seen, eligible = set(), []
    excluded = dict(nonfinite=0, not_yet_released=0)
    receipt_rules = dict(calendar_date_end=0, calendar_timestamp=0, following_month_end=0)
    for row in errors:
        origin, target, h = str(row['origin']), str(row['target']), row['h']
        month_number(origin); month_number(target)
        if isinstance(h, bool) or int(h) != h or not 0 <= int(h) <= 12:
            raise ValueError('h must be an integer in 0..12')
        h = int(h)
        if target != month_offset(origin, h):
            raise ValueError('Target does not match origin+h')
        key = (origin, h)
        if key in seen:
            raise ValueError('Duplicate origin/horizon: ' + str(key))
        seen.add(key)
        available, rule = receipt(target, release_calendar)
        receipt_rules[rule] += 1
        if available > decision or origin > decision.strftime('%Y-%m'):
            excluded['not_yet_released'] += 1
            continue
        try:
            error = number(row['actual'])-number(row['forecast'])
            error = number(error)
        except (ValueError, TypeError):
            excluded['nonfinite'] += 1
            continue
        eligible.append(dict(origin=origin, target=target, h=h, error=error, available_at=available.isoformat()))
    samples = {}
    for sample in ('full', '2024plus'):
        samples[sample] = {}
        for h in range(13):
            rows = [r for r in eligible if r['h'] == h and (sample == 'full' or r['origin'] >= '2024-01')]
            values = [r['error'] for r in rows]
            n = len(rows)
            samples[sample][str(h)] = dict(
                h=h, status='available' if n >= 20 else 'unavailable', n=n,
                lower_offset_pp=quantile(values,.1) if n >= 20 else None,
                upper_offset_pp=quantile(values,.9) if n >= 20 else None,
                reason=None if n >= 20 else 'Fewer than 20 finite errors with released outcomes',
                origin_start=min((r['origin'] for r in rows),default=None),
                origin_end=max((r['origin'] for r in rows),default=None),
                target_start=min((r['target'] for r in rows),default=None),
                target_end=max((r['target'] for r in rows),default=None),
                units='mm_percentage_points' if h == 0 else 'yy_percentage_points',
                model='R31C HARD_BASE' if h == 0 else 'R31B accepted path',
                observations=sorted(rows,key=lambda r:r['origin']))
    return dict(as_of=decision.isoformat(), quantiles=[.1,.9], min_n=20,
                quantile_method='linear interpolation at (n-1)*p', error_definition='actual - forecast',
                application='forecast + lower_offset_pp, forecast + upper_offset_pp; match m/m or y/y units',
                samples=samples, input_rows=len(seen), excluded=excluded, receipt_rules=receipt_rules,
                receipt_policy='Detailed release calendar; date-only usable after UTC date end; missing dates after following month end',
                limitations=ERROR_LIMITATIONS)


def seasonal_from_frames(frames, forecast, *, target, as_of):
    """Descriptive mean of every complete pre-origin same-month observation.

    Uses recorded/current coefficients for all years, including a consistently
    constructed residual wedge. Not the model's fitted seasonal contribution.
    """
    month_number(target); decision = clock(as_of)
    if target > decision.strftime('%Y-%m'):
        raise ValueError('Seasonal target is after the recorded decision month')
    raw_weights = forecast['weights']
    weights = {k:number(raw_weights[v]) for k,v in WEIGHT_KEYS.items()}
    if any(w < 0 for w in weights.values()) or abs(math.fsum(weights.values())-1)>1e-8:
        raise ValueError('Recorded weights must be nonnegative and sum to one')
    if set(forecast['main_contributions_pp']) != set(COMPONENTS):
        raise ValueError('Exactly six recorded contributions required')
    contributions = {k:number(forecast['main_contributions_pp'][k]) for k in COMPONENTS}
    point = number(forecast['points_mm_pct']['HARD_BASE'])
    if abs(math.fsum(contributions.values())-point)>1e-10:
        raise ValueError('Recorded contributions do not sum to HARD_BASE')
    columns = dict(headline=('headline','cpi_mm'), core=('core','core'),
                   food=('components','food'), fuel=('components','fuel'),
                   administered=('regulated','regulated'), alcohol_tobacco=('alcohol','alcohol_tobacco'))
    series = {k:monthly_pairs(frames[f][col],finite=False) for k,(f,col) in columns.items()}
    candidates = sorted({m for s in series.values() for m in s if m < target and m[-2:] == target[-2:]})
    months, skipped = [], []
    histories = {k:[] for k in COMPONENTS}
    for m in candidates:
        if any(m not in s or not math.isfinite(s[m]) for s in series.values()):
            skipped.append(m); continue
        months.append(m)
        for k in weights: histories[k].append(series[k][m])
        histories['wedge'].append(series['headline'][m]-math.fsum(weights[k]*series[k][m] for k in weights))
    rows = []
    for k in COMPONENTS:
        mean = math.fsum(histories[k])/len(months) if months else None
        coefficient = weights.get(k, 1.)
        baseline = coefficient*mean if mean is not None else None
        rows.append(dict(component=k, recorded_contribution_pp=contributions[k],
                         weight=coefficient, seasonal_mean_mm=mean,
                         baseline_contribution_pp=baseline,
                         deviation_pp=contributions[k]-baseline if baseline is not None else None))
    base_total = math.fsum(r['baseline_contribution_pp'] for r in rows) if months else None
    return dict(status='available' if months else 'unavailable', target=target, as_of=decision.isoformat(),
                point_mm=point, components=rows, baseline_total_pp=base_total,
                deviation_total_pp=point-base_total if base_total is not None else None,
                sample=dict(n=len(months), months=months, start=months[0] if months else None,
                            end=months[-1] if months else None, excluded_incomplete=skipped,
                            window='All finite common-support pre-origin observations of the same calendar month'),
                definition='Historical arithmetic mean of NSA component m/m, multiplied by recorded origin weights; wedge = headline minus the five weighted components at those same weights',
                exact_model_seasonal_terms=dict(status='unavailable', reason='Fitted seasonal coefficients were not archived in the adapter; no model refit is performed'),
                limitations='Descriptive seasonal normal, not an exact model decomposition or causal attribution. Negative NSA September core inflation is not automatically disinflation. The deviation also contains model, pipeline and accounting effects. Historical weights are held at the recorded current values for this benchmark.')


def seasonal_context(bundle, record):
    """Validated path API; returns descriptive context for the immutable recorded h0."""
    from .sources import load_seasonal
    return load_seasonal(bundle, record)
