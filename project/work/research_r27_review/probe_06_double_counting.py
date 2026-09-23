"""Probe 6: does the level correction double-count what the R14B rate VAR already uses?

Regress the baseline's food forecast error (realised minus FOOD_NORM_SHIFT_R24, log points) at each monthly
horizon and cumulatively at h3/h6 on gap_last from ecm_audit.csv across origins; compare the slope with the
coefficient the candidate applies (alpha (1+alpha)^h with alpha = -0.25, L = t-1). Then the same on the
candidate's own error (is anything left?), on FAST's error (before the R24 drift), and an encompassing
regression of the outcome on the baseline forecast and the gap.
"""
import json

import numpy as np
import pandas as pd

import probe_common as pc

OUT = pc.HERE / 'probe_06_double_counting'
OUT.mkdir(exist_ok=True)
native = pc.load_native(); actual = pc.load_actual(); support = pc.load_support(); audit = pc.load_audit()
paths = pc.food_log_paths(native, [pc.FAST, pc.BASELINE, pc.CANDIDATE]); truth = pc.actual_food_log(actual)
gap = audit[audit.model == pc.CANDIDATE].set_index('origin').gap_last
ALPHA = -.25
findings = {}


def ols(y, x, lag=0):
    """Slope, intercept, OLS t and Newey-West t (lag) for y on a constant and x."""
    X = np.column_stack([np.ones(len(x)), x]); beta = np.linalg.lstsq(X, y, rcond=None)[0]; u = y - X @ beta; n = len(y)
    XtX_inv = np.linalg.inv(X.T @ X)
    s2 = float(u @ u) / (n - 2); se_ols = float(np.sqrt(s2 * XtX_inv[1, 1]))
    S = (X * u[:, None]).T @ (X * u[:, None])
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1); G = (X[l:] * u[l:, None]).T @ (X[:-l] * u[:-l, None]); S += w * (G + G.T)
    V = XtX_inv @ S @ XtX_inv; se_nw = float(np.sqrt(V[1, 1]))
    r2 = 1 - float(u @ u) / float(((y - y.mean()) ** 2).sum())
    return dict(slope=float(beta[1]), intercept=float(beta[0]), t_ols=float(beta[1] / se_ols), t_nw=float(beta[1] / se_nw), n=n, r2=r2)


rows = []
for h in range(1, 13):
    applied = ALPHA * (1 + ALPHA) ** h if h <= 6 else 0.
    recs = []
    for o in paths[pc.BASELINE].index:
        t = pd.Period(o, 'M') + h
        if t in truth.index and (o, h) in support and o in gap.index:
            recs.append(dict(origin=o, gap=gap[o], e_base=truth[t] - paths[pc.BASELINE].loc[o, h], e_cand=truth[t] - paths[pc.CANDIDATE].loc[o, h], e_fast=truth[t] - paths[pc.FAST].loc[o, h],
                             actual=truth[t], base=paths[pc.BASELINE].loc[o, h]))
    r = pd.DataFrame(recs).dropna().sort_values('origin')
    for era in ('full', 'origins_2024plus'):
        z = r[pc.era_mask(r.origin, era)]
        if len(z) < 10:
            continue
        b = ols(z.e_base.to_numpy(), z.gap.to_numpy(), lag=max(h - 1, 6)); c = ols(z.e_cand.to_numpy(), z.gap.to_numpy(), lag=max(h - 1, 6)); f = ols(z.e_fast.to_numpy(), z.gap.to_numpy(), lag=max(h - 1, 6))
        rows.append(dict(h=h, sample=era, n=len(z), applied_coefficient=applied, slope_baseline_error=b['slope'], t_ols=b['t_ols'], t_nw=b['t_nw'], r2=b['r2'],
                         slope_candidate_error=c['slope'], t_nw_candidate=c['t_nw'], slope_fast_error=f['slope'], t_nw_fast=f['t_nw'], ratio_slope_to_applied=b['slope'] / applied if applied else np.nan))
monthly = pd.DataFrame(rows); monthly.to_csv(OUT / 'monthly_error_on_gap.csv', index=False)
findings['monthly'] = {f'h{r.h}_{r["sample"]}': dict(n=int(r.n), applied=round(r.applied_coefficient, 4), slope=round(r.slope_baseline_error, 4), t_ols=round(r.t_ols, 2), t_nw=round(r.t_nw, 2),
                                                    ratio=round(r.ratio_slope_to_applied, 2) if np.isfinite(r.ratio_slope_to_applied) else None, slope_after=round(r.slope_candidate_error, 4), t_after=round(r.t_nw_candidate, 2),
                                                    slope_fast=round(r.slope_fast_error, 4)) for _, r in monthly.iterrows()}

# cumulative h3 / h6 / h12 errors on gap_last
table = pc.cumulative_table(paths, truth, support)
cum = {}
for H in (3, 6, 12):
    applied = float(sum(ALPHA * (1 + ALPHA) ** k for k in range(1, min(H, 6) + 1)))
    w = table[table.H == H].dropna().copy(); w['gap'] = w.origin.map(gap); w = w.dropna().sort_values('origin')
    for era in ('full', 'origins_2019_2021', 'origins_2022_2023', 'origins_2024plus'):
        z = w[pc.era_mask(w.origin, era)]
        b = ols((z.actual - z[pc.BASELINE]).to_numpy(), z.gap.to_numpy(), lag=12); c = ols((z.actual - z[pc.CANDIDATE]).to_numpy(), z.gap.to_numpy(), lag=12)
        cum[f'h{H}_{era}'] = dict(n=len(z), applied=round(applied, 3), slope=round(b['slope'], 3), t_nw=round(b['t_nw'], 2), r2=round(b['r2'], 3), implied_multiplier_of_applied=round(b['slope'] / applied, 2),
                                  slope_after=round(c['slope'], 3), t_after=round(c['t_nw'], 2))
findings['cumulative'] = cum

# encompassing regression at h1 and cumulative h6: actual = a + b*baseline + c*gap
enc = {}
for H, key in ((1, 'h1'), (6, 'h6')):
    if H == 1:
        recs = [dict(origin=o, actual=truth[pd.Period(o, 'M') + 1], base=paths[pc.BASELINE].loc[o, 1], gap=gap[o]) for o in paths[pc.BASELINE].index if (pd.Period(o, 'M') + 1) in truth.index and (o, 1) in support]
        z = pd.DataFrame(recs).dropna().sort_values('origin')
    else:
        z = table[table.H == 6].dropna().copy(); z['gap'] = z.origin.map(gap); z['base'] = z[pc.BASELINE]; z = z.dropna().sort_values('origin')
    X = np.column_stack([np.ones(len(z)), z.base, z.gap]); y = z.actual.to_numpy(); beta = np.linalg.lstsq(X, y, rcond=None)[0]; u = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X); S = (X * u[:, None]).T @ (X * u[:, None]); lag = 12
    for l in range(1, lag + 1):
        w_ = 1 - l / (lag + 1); G = (X[l:] * u[l:, None]).T @ (X[:-l] * u[:-l, None]); S += w_ * (G + G.T)
    V = XtX_inv @ S @ XtX_inv
    enc[key] = dict(n=len(z), coef_baseline=round(float(beta[1]), 3), t_baseline=round(float(beta[1] / np.sqrt(V[1, 1])), 2), coef_gap=round(float(beta[2]), 3), t_gap=round(float(beta[2] / np.sqrt(V[2, 2])), 2))
findings['encompassing'] = enc

# the optimal scaling of the candidate's own correction: regress the baseline cumulative h6 error on the applied cumulative correction
w = table[table.H == 6].dropna().sort_values('origin'); applied6 = (w[pc.CANDIDATE] - w[pc.BASELINE]).to_numpy(); need6 = (w.actual - w[pc.BASELINE]).to_numpy()
k = float(applied6 @ need6) / float(applied6 @ applied6)
scale = {}
for kk in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
    e = need6 - kk * applied6; scale[str(kk)] = round(float(np.sqrt(np.mean(e ** 2))), 4)
findings['scaling_of_applied_correction_h6'] = dict(ls_multiplier_through_origin=round(k, 3), rmse_by_multiplier=scale, baseline_rmse=round(float(np.sqrt(np.mean(need6 ** 2))), 4))
for era in ('origins_2019_2021', 'origins_2022_2023', 'origins_2024plus'):
    m = pc.era_mask(w.origin, era); a = applied6[m]; nd = need6[m]
    findings['scaling_of_applied_correction_h6'][f'ls_multiplier_{era}'] = round(float(a @ nd) / float(a @ a), 3)

(OUT / 'findings.json').write_text(json.dumps(findings, indent=1, default=str), encoding='utf-8')
print(json.dumps(findings, indent=1, default=str))
