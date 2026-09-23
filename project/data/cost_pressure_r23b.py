"""R23B origin-frozen cost-pressure features. Zero means neutral; quarterly data stay quarterly.

Reuses R23's loaders, publication masks and core-level construction without editing them.
New here: a same-quarter ULC gap that carries no seasonal, and six-month momentum differentials
in place of R23's late-cycle level gaps. R23's level gaps are kept for the control candidate.
"""
import numpy as np
import pandas as pd

from data.cost_gaps_r23 import load_inputs as _load_r23, features_at as _features_r23, visible, chain, local

COLUMNS = ['ulc_sameq', 'tightening', 'import_mom', 'ppi_mom', 'fx_news', 'import_gap', 'ppi_gap']
_FROM_R23 = ['tightening', 'fx_news', 'import_gap', 'ppi_gap']
UNITS = {'ulc_sameq': 'real unit labour cost against the same quarter of the three previous years, log points',
         'import_mom': 'six-month import-price change less six-month core change, log points',
         'ppi_mom': 'six-month manufactured-PPI change less six-month core change, log points'}


def _latest(dates, clock):
    a = pd.to_datetime(pd.Series(list(dates))).dropna()
    last = a.max() if len(a) else pd.NaT
    if pd.notna(last) and last > clock:
        raise ValueError('Future source in provenance')
    return last.isoformat() if pd.notna(last) else None


def features_at(core, core_dates, raw, fx, origin, asof, seasonal):
    t = pd.Period(origin, 'M'); edge = t - 1; clock = local(asof)
    legacy, legacy_audit = _features_r23(core, core_dates, raw, fx, t, asof, seasonal)
    out = {k: np.nan for k in COLUMNS}; out.update({k: float(legacy[k]) for k in _FROM_R23})
    audit = [r for r in legacy_audit if r['feature'] in _FROM_R23]

    observed = visible(core, core_dates, edge, clock)
    logs = 100 * np.log1p(observed.where(observed > -100) / 100)
    logs -= np.array([seasonal.get(p.month, seasonal.get(str(p.month), np.nan)) for p in logs.index])
    level = chain(logs)

    def record(name, reference, dates):
        ok = np.isfinite(out[name])
        audit.append(dict(feature=name, reference=str(reference) if reference is not None else None,
                          last_publication=_latest(dates, clock) if ok else None, units=UNITS[name],
                          value=out[name] if ok else np.nan, status='available' if ok else 'missing_required_history'))

    # Real unit labour cost against the same quarter of the three previous years.
    q = raw[17]
    qv = visible(q.values, q.available, edge.asfreq('Q'), clock).where(lambda v: v > 0)
    coreq = level.groupby(level.index.asfreq('Q')).agg(['mean', 'count'])
    coreq = coreq['mean'].where(coreq['count'].eq(3))
    done = pd.PeriodIndex([p for p in qv.dropna().index if p.asfreq('M', 'end') <= edge], freq='Q')
    ref = done.max() if len(done) else None
    used = []
    if ref is not None:
        used = [ref - 12, ref - 8, ref - 4, ref]
        rel = (100 * np.log(qv) - coreq.reindex(qv.index)).reindex(used)
        if rel.notna().all():
            out['ulc_sameq'] = float(rel.iloc[-1] - rel.iloc[:-1].median())
    core_used = core_dates.loc[core_dates.index <= ref.asfreq('M', 'end')] if ref is not None else core_dates.iloc[:0]
    record('ulc_sameq', ref, [*q.available.reindex(used), *core_used])

    # Six-month upstream momentum less six-month core momentum, over the same months.
    for name, n in [('import_mom', 26), ('ppi_mom', 47)]:
        r = raw[n]; v = visible(r.values, r.available, edge, clock); ref = v.last_valid_index(); dates = []
        if ref is not None:
            window = pd.period_range(ref - 5, ref, freq='M')
            core_change = logs.reindex(window)
            if n == 26:
                changes = 100 * np.log1p(v.where(v > -100).reindex(window) / 100)
                upstream = changes.sum() if changes.notna().all() else np.nan
                dates = [*r.available.reindex(window)]
            else:
                ends = v.where(v > 0).reindex([ref - 6, ref])
                upstream = 100 * np.log(ends.iloc[1] / ends.iloc[0]) if ends.notna().all() else np.nan
                dates = [*r.available.reindex([ref - 6, ref])]
            if np.isfinite(upstream) and core_change.notna().all():
                out[name] = float(upstream - core_change.sum())
            dates = [*dates, *core_dates.reindex(window)]
        record(name, ref, dates)
    return pd.Series(out, dtype=float)[COLUMNS], audit


def load_inputs():
    """R23's frozen inputs and hashes, plus this module's own hash."""
    import r17_common as c
    core, dates, raw, fx, hashes = _load_r23()
    hashes['data/cost_pressure_r23b.py'] = c.sha(c.ROOT / 'data/cost_pressure_r23b.py')
    return core, dates, raw, fx, hashes
