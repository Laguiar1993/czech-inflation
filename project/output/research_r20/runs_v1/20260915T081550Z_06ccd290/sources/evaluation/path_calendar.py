"""Calendar aggregation for comparable inflation forecasts."""
import pandas as pd
import numpy as np


def complete_quarters(observed: pd.Series, forecast: pd.Series) -> pd.Series:
    """Average complete quarters intersecting the forecast, including known months.

    Values are monthly year-on-year rates, not monthly changes. Forecast rows
    replace overlapping observations explicitly; incomplete quarters are omitted.
    """
    for x in (observed, forecast):
        if not isinstance(x.index, pd.PeriodIndex) or x.index.freqstr != 'M' or x.index.has_duplicates:
            raise ValueError('unique monthly PeriodIndex required')
    joined = pd.concat([observed.loc[~observed.index.isin(forecast.index)], forecast]).sort_index()
    result = {}
    for q in forecast.index.asfreq('Q').unique():
        months = pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M')
        values = joined.reindex(months)
        if np.isfinite(values.to_numpy(dtype=float)).all():
            result[q] = float(values.mean())
    return pd.Series(result, index=pd.PeriodIndex(list(result), freq='Q'), dtype=float)
