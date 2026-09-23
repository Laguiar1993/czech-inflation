"""Probe 5: robustness of the block gain. Leave-one-origin-year-out at h6 and h12; the share of the squared-loss
gain from 2021-22 origins; sign agreement of needed and applied per era and per year; the dependence structure
behind the bootstrap (contiguity, autocorrelation, Diebold-Mariano with Newey-West), and the interval when the
five largest origins are removed.
"""
import json

import numpy as np
import pandas as pd

import probe_common as pc

OUT = pc.HERE / 'probe_05_robustness'
OUT.mkdir(exist_ok=True)
native = pc.load_native(); actual = pc.load_actual(); support = pc.load_support()
paths = pc.food_log_paths(native, [pc.BASELINE, pc.CANDIDATE, pc.PPI_CANDIDATE])
table = pc.cumulative_table(paths, pc.actual_food_log(actual), support)
findings = {}


def nw_t(d, lag):
    d = np.asarray(d, float); n = len(d); m = d.mean(); u = d - m
    s = float(u @ u) / n
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1); s += 2 * w * float(u[l:] @ u[:-l]) / n
    return float(m / np.sqrt(s / n)), float(m), n


# leave one origin year out ---------------------------------------------------------------------------------------
loo = []
for H in (3, 6, 12):
    w = table[table.H == H].dropna().copy(); w['year'] = w.origin.str[:4]
    full_ratio = pc.rmse(w[pc.CANDIDATE] - w.actual) / pc.rmse(w[pc.BASELINE] - w.actual)
    for year in sorted(w.year.unique()):
        z = w[w.year != year]
        loo.append(dict(H=H, omitted=year, n=len(z), ratio=pc.rmse(z[pc.CANDIDATE] - z.actual) / pc.rmse(z[pc.BASELINE] - z.actual), full_ratio=full_ratio,
                        year_only_ratio=pc.rmse(w[w.year == year][pc.CANDIDATE] - w[w.year == year].actual) / pc.rmse(w[w.year == year][pc.BASELINE] - w[w.year == year].actual), n_year=int((w.year == year).sum())))
loo = pd.DataFrame(loo); loo.to_csv(OUT / 'leave_one_origin_year_out.csv', index=False)
findings['leave_one_year_out'] = {f'h{H}': dict(worst_ratio=round(float(loo[loo.H == H].ratio.max()), 4), worst_omitted=loo[loo.H == H].sort_values('ratio').omitted.iloc[-1],
                                              best_ratio=round(float(loo[loo.H == H].ratio.min()), 4), full=round(float(loo[loo.H == H].full_ratio.iloc[0]), 4)) for H in (3, 6, 12)}
findings['year_only_ratio'] = {f'h{H}': {r.omitted: (round(r.year_only_ratio, 3), r.n_year) for r in loo[loo.H == H].itertuples()} for H in (3, 6, 12)}

# share of the gain from 2021-22 --------------------------------------------------------------------------------------
share = {}
for H in (3, 6, 12):
    w = table[table.H == H].dropna().copy()
    w['dsq'] = (w[pc.CANDIDATE] - w.actual) ** 2 - (w[pc.BASELINE] - w.actual) ** 2; w['year'] = w.origin.str[:4]
    by_year = w.groupby('year').dsq.sum(); tot = w.dsq.sum()
    share[f'h{H}'] = dict(total=round(float(tot), 2), by_year_share={y: round(float(v / tot), 3) for y, v in by_year.items()},
                          share_2021_2022=round(float(by_year.reindex(['2021', '2022']).sum() / tot), 3),
                          share_2021_11_to_2022_04=round(float(w[(w.origin >= '2021-11') & (w.origin <= '2022-04')].dsq.sum() / tot), 3),
                          ratio_without_2021_2022=round(pc.rmse(w[~w.year.isin(['2021', '2022'])][pc.CANDIDATE] - w[~w.year.isin(['2021', '2022'])].actual) / pc.rmse(w[~w.year.isin(['2021', '2022'])][pc.BASELINE] - w[~w.year.isin(['2021', '2022'])].actual), 4),
                          ratio_without_2021_11_to_2022_04=round(pc.rmse(w[~((w.origin >= '2021-11') & (w.origin <= '2022-04'))][pc.CANDIDATE] - w[~((w.origin >= '2021-11') & (w.origin <= '2022-04'))].actual) / pc.rmse(w[~((w.origin >= '2021-11') & (w.origin <= '2022-04'))][pc.BASELINE] - w[~((w.origin >= '2021-11') & (w.origin <= '2022-04'))].actual), 4))
findings['gain_share'] = share

# sign agreement per era and per year -----------------------------------------------------------------------------------
sign = []
for H in (3, 6):
    w = table[table.H == H].dropna().copy(); w['year'] = w.origin.str[:4]
    needed = w.actual - w[pc.BASELINE]; applied = w[pc.CANDIDATE] - w[pc.BASELINE]; agree = np.sign(needed) == np.sign(applied)
    for era in pc.ERAS:
        m = pc.era_mask(w.origin, era)
        sign.append(dict(H=H, group=era, n=int(m.sum()), sign_agreement=float(agree[m].mean()), correlation=float(needed[m].corr(applied[m])), mean_needed=float(needed[m].mean()), mean_applied=float(applied[m].mean())))
    for year in sorted(w.year.unique()):
        m = (w.year == year).to_numpy()
        sign.append(dict(H=H, group=year, n=int(m.sum()), sign_agreement=float(agree[m].mean()), correlation=float(needed[m].corr(applied[m])) if m.sum() > 2 else np.nan, mean_needed=float(needed[m].mean()), mean_applied=float(applied[m].mean())))
sign = pd.DataFrame(sign); sign.to_csv(OUT / 'sign_agreement.csv', index=False)
findings['sign_agreement'] = {f'h{r.H}_{r.group}': dict(n=r.n, agree=round(r.sign_agreement, 3), corr=round(r.correlation, 3) if np.isfinite(r.correlation) else None) for r in sign.itertuples()}

# dependence and Diebold-Mariano -----------------------------------------------------------------------------------------
dm = {}
for H in (3, 6, 12):
    w = table[table.H == H].dropna().sort_values('origin'); d = ((w[pc.CANDIDATE] - w.actual) ** 2 - (w[pc.BASELINE] - w.actual) ** 2).to_numpy()
    ordinal = pd.PeriodIndex(w.origin, freq='M').asi8
    acf = [float(pd.Series(d).autocorr(l)) for l in (1, 3, 6, 12)]
    dm[f'h{H}'] = dict(n=len(d), contiguous=bool(np.all(np.diff(ordinal) == 1)), acf_1_3_6_12=[round(a, 3) for a in acf],
                       dm_t_nw_lag_Hminus1=round(nw_t(d, H - 1)[0], 2), dm_t_nw_lag_12=round(nw_t(d, 12)[0], 2), dm_t_nw_lag_18=round(nw_t(d, 18)[0], 2),
                       improved_share=float((d < 0).mean()), mean=round(float(d.mean()), 3), median=round(float(np.median(d)), 3))
    # interval with the five largest gains removed (the declared scheme needs contiguity; report a moving-block-free t instead and a resample of the rest)
    order = np.argsort(d); keep = np.ones(len(d), bool); keep[order[:5]] = False
    dm[f'h{H}']['without_top5'] = dict(mean=round(float(d[keep].mean()), 3), dm_t_nw_lag_12=round(nw_t(d[keep], 12)[0], 2), improved_share=float((d[keep] < 0).mean()),
                                       ratio=round(pc.rmse((w[pc.CANDIDATE] - w.actual)[keep]) / pc.rmse((w[pc.BASELINE] - w.actual)[keep]), 4))
    # block-mean t test on non-overlapping 12-month blocks, all 12 alignments (the R24 reviewer's check)
    ts = []
    for off in range(12):
        blocks = [d[i:i + 12].mean() for i in range(off, len(d) - 11, 12)]
        if len(blocks) >= 3:
            b = np.array(blocks); ts.append(float(b.mean() / (b.std(ddof=1) / np.sqrt(len(b)))))
    dm[f'h{H}']['block_mean_t_min_max'] = [round(min(ts), 2), round(max(ts), 2)]; dm[f'h{H}']['block_alignments_significant_5pct'] = int(sum(abs(t) > 2.2 for t in ts))
findings['dependence'] = dm

# monthly (non-cumulative) errors at each h: does the candidate improve h1, h2 monthly food rates? -------------------------
monthly = []
truth = pc.actual_food_log(actual)
for h in range(1, 13):
    rows = []
    for o in paths[pc.BASELINE].index:
        t = pd.Period(o, 'M') + h
        if t in truth.index and (o, h) in support:
            rows.append(dict(origin=o, actual=truth[t], base=paths[pc.BASELINE].loc[o, h], cand=paths[pc.CANDIDATE].loc[o, h]))
    r = pd.DataFrame(rows).dropna()
    for era in pc.ERAS:
        z = r[pc.era_mask(r.origin, era)]
        monthly.append(dict(h=h, sample=era, n=len(z), rmse_base=pc.rmse(z.base - z.actual), rmse_cand=pc.rmse(z.cand - z.actual), ratio=pc.rmse(z.cand - z.actual) / pc.rmse(z.base - z.actual),
                            bias_base=float((z.base - z.actual).mean()), bias_cand=float((z.cand - z.actual).mean())))
monthly = pd.DataFrame(monthly); monthly.to_csv(OUT / 'monthly_rate_errors.csv', index=False)
findings['monthly_rate_ratio'] = {f'h{h}': {era: round(float(monthly[(monthly.h == h) & (monthly['sample'] == era)].ratio.iloc[0]), 3) for era in pc.ERAS} for h in range(1, 8)}

(OUT / 'findings.json').write_text(json.dumps(findings, indent=1, default=str), encoding='utf-8')
print(json.dumps(findings, indent=1, default=str))
