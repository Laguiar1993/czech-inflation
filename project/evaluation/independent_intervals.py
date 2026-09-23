"""Sequential empirical error bands; diagnostic, not guaranteed coverage."""
from pathlib import Path
import numpy as np
import pandas as pd


def interval_radius(errors, release_dates, as_of, *, minimum=24, window=60, coverage=.9):
    if not 0 < coverage < 1 or minimum < 1 or window < minimum:
        raise ValueError('invalid interval settings')
    past=errors.loc[(release_dates.reindex(errors.index)<=as_of)].dropna().sort_index().iloc[-window:]
    n=len(past)
    if n<minimum:return np.nan,n
    rank=int(np.ceil((n+1)*coverage))
    if rank>n:return np.inf,n
    return float(np.sort(np.abs(past.to_numpy()))[rank-1]),n


def main():
    import cz_struct as s
    root=Path(__file__).resolve().parents[1]
    pred=pd.read_csv(root/'output/independent_nowcast_forecasts.csv',index_col='period')
    pred.index=pd.PeriodIndex(pred.index,freq='M')
    actual=pd.read_csv(root/'data/czcpmom_survey_history_extended.csv')
    actual=actual[actual.era.ne('flash_survey_suspect')].copy()
    actual.index=pd.PeriodIndex(actual.target_month,freq='M')
    actual=actual.actual.reindex(pred.index)
    release=pd.Series([s._first_release_dt(t) for t in pred.index],index=pred.index)
    records=[]
    for name in ('HARD_BASE','HARD_HALF','HARD_FULL','SENTIMENT_BASE'):
        error=actual-pred[name]
        for t in pred.index:
            radius,n=interval_radius(error,release,pd.Timestamp(pred.loc[t,'as_of_eve']))
            point=pred.loc[t,name]
            lo,hi=point-radius,point+radius
            real=actual.loc[t]
            records.append(dict(model=name,period=str(t),n_errors=n,lower=lo,upper=hi,
                actual=real,covered=bool(lo<=real<=hi) if np.isfinite(radius) else np.nan,
                width=2*radius,interval_score=2*radius+20*max(lo-real,0)+20*max(real-hi,0)))
    rows=pd.DataFrame(records)
    rows.to_csv(root/'output/independent_nowcast_intervals.csv',index=False)
    score=rows.dropna(subset=['covered']).groupby('model').agg(n=('covered','size'),coverage=('covered','mean'),
        mean_width=('width','mean'),mean_interval_score=('interval_score','mean'))
    score.to_csv(root/'output/independent_nowcast_interval_scores.csv')
    print(score.to_string())
    print('Nominal90%; empirical sequential diagnostic. Serial dependence/repeated selection preclude a coverage guarantee.')


if __name__=='__main__':main()
