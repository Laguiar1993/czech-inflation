"""Probe A2: the estimator re-implemented from the specification text and compared with fits.jsonl.

Inputs are the delivered features.csv, band_targets.csv, target_available.csv and
feature_clocks.csv. No function from models.cost_pressure_r23b is called.
Own numerical routes: ridge through an augmented least-squares solve (lstsq), the bounded
variant through scipy.optimize.nnls (active set) instead of lsq_linear (trust region).
"""
import json
import numpy as np
import pandas as pd
from scipy.optimize import nnls

from _common import ROOT, FINAL, Report

R = Report('A2 estimation, nested validation, do-no-harm (independent rebuild)')
X = pd.read_csv(FINAL / 'features.csv', index_col=0, float_precision='round_trip'); X.index = pd.PeriodIndex(X.index, freq='M')
Y = pd.read_csv(FINAL / 'band_targets.csv', index_col=0, float_precision='round_trip'); Y.index = pd.PeriodIndex(Y.index, freq='M'); Y.columns = Y.columns.astype(int)
A = pd.read_csv(FINAL / 'target_available.csv', index_col=0); A.index = pd.PeriodIndex(A.index, freq='M'); A.columns = A.columns.astype(int)
A = A.apply(pd.to_datetime)
CLOCK = pd.read_csv(FINAL / 'feature_clocks.csv', index_col=0).iloc[:, 0].map(pd.Timestamp); CLOCK.index = pd.PeriodIndex(CLOCK.index, freq='M')
fits = [json.loads(line) for line in (FINAL / 'fits.jsonl').open()]

SPEC = {'PRESS_ULC_R23B': (['ulc_sameq'], False),
        'PRESS_DOMESTIC_R23B': (['ulc_sameq', 'tightening'], False),
        'PRESS_MOMENTUM_R23B': (['import_mom', 'ppi_mom', 'fx_news'], False),
        'PRESS_JOINT_R23B': (['ulc_sameq', 'tightening', 'import_mom', 'ppi_mom', 'fx_news'], False),
        'PRESS_SIGNED_R23B': (['ulc_sameq', 'tightening', 'import_mom', 'ppi_mom', 'fx_news'], True),
        'PRESS_LEVELS_R23B': (['ulc_sameq', 'tightening', 'import_gap', 'ppi_gap', 'fx_news'], False)}
GRID = [0.3, 1., 3., 10., 30.]
complete = X.notna().all(axis=1)


def rows_at(t, clock, band, minimum):
    keep = [s for s in X.index                                   # chronological by construction (checked below)
            if s.month in (3, 6, 9, 12) and s + 3 * band <= t - 1 and complete[s]
            and pd.notna(A.loc[s, band]) and A.loc[s, band] <= clock and np.isfinite(Y.loc[s, band])]
    keep = keep[-40:]
    return keep if len(keep) >= minimum else []


def solve(rows, band, columns, now, alpha, signed):
    x = X.loc[rows, columns].to_numpy(float); y = Y.loc[rows, band].to_numpy(float); n, p = x.shape
    scale = np.sqrt((x ** 2).mean(axis=0)); scale[scale <= 1e-8] = 1.
    z = x / scale; big = np.vstack([z / np.sqrt(n), np.sqrt(alpha) * np.eye(p)]); rhs = np.r_[y / np.sqrt(n), np.zeros(p)]
    beta = nnls(big, rhs, maxiter=10000)[0] if signed else np.linalg.lstsq(big, rhs, rcond=None)[0]
    return beta, (np.asarray(now, float) / scale) * beta


def band_means_to_months(bands):
    knots = [2, 5, 8, 11]; h = np.arange(1, 13)
    basis = np.column_stack([np.interp(h, knots, np.eye(4)[j]) for j in range(4)])
    means = np.vstack([basis[3 * k:3 * k + 3].mean(axis=0) for k in range(4)])
    return basis @ np.linalg.solve(means, np.asarray(bands, float))


R.check('feature index strictly chronological (the "latest 40" slice relies on order)', X.index.is_monotonic_increasing and X.index.is_unique)
worst = dict(coef=0., pred=0., score=0., zero=0., path=0., coef_free=0., pred_free=0.); bad = []; n_cells = 0; tie_cells = 0; equal_zero_cells = 0
bound_cells = []                                                  # signed fits: exact NNLS zero against the saved trust-region value
fold_counts = {}; train_counts = {}
for rec in fits:
    t = pd.Period(rec['origin'], 'M'); clock = CLOCK[t]
    if rec['status'] != 'estimated':
        bad.append((rec['origin'], 'status', rec['status'])); continue
    outer = {b: rows_at(t, clock, b, 24) for b in (1, 2)}
    for b in (1, 2):
        if [str(s) for s in outer[b]] != rec['train_dates'][str(b)]:
            bad.append((rec['origin'], b, 'outer rows'))
        train_counts[len(outer[b])] = train_counts.get(len(outer[b]), 0) + 1
    if not complete[t]:
        bad.append((rec['origin'], 'current features incomplete but estimated'))
    for model, (columns, signed) in SPEC.items():
        applied_bands = []
        for b in (1, 2):
            n_cells += 1
            sel = rec['selection'][model][str(b)]; fit = rec['fits'][model][str(b)]
            folds = [(v, rows_at(v, CLOCK[v], b, 16)) for v in outer[b]]
            folds = [(v, inner) for v, inner in folds if inner][-8:]
            fold_counts[len(folds)] = fold_counts.get(len(folds), 0) + 1
            if len(folds) < 4:
                if sel['status'] != 'no_correction_insufficient_validation' or sel['alpha'] is not None:
                    bad.append((rec['origin'], model, b, 'few folds but corrected'))
                choice = None
            else:
                zero = float(np.mean([Y.loc[v, b] ** 2 for v, _ in folds])); score = {}
                for alpha in GRID:
                    losses = []
                    for v, inner in folds:
                        beta, contrib = solve(inner, b, columns, X.loc[v, columns], alpha, signed)
                        losses.append((contrib.sum() - Y.loc[v, b]) ** 2)
                    score[alpha] = float(np.mean(losses))
                    worst['score'] = max(worst['score'], abs(score[alpha] - sel['scores'][str(alpha)]))
                worst['zero'] = max(worst['zero'], abs(zero - sel['zero_loss']))
                low = min(score.values()); tied = [a for a in GRID if score[a] == low]
                tie_cells += len(tied) > 1
                best = max(tied)                                      # ties favour the stronger penalty
                choice = best if score[best] < zero else None          # then no correction
                equal_zero_cells += score[best] == zero
                # validation-origin sets as saved
                saved_folds = sorted({r['validation_origin'] for r in sel['validation']})
                if saved_folds != [str(v) for v, _ in folds]:
                    bad.append((rec['origin'], model, b, 'fold set'))
                for r in sel['validation']:
                    inner = dict((str(v), i) for v, i in folds)[r['validation_origin']]
                    if r['n_train'] != len(inner) or r['first_training_origin'] != str(inner[0]) or r['last_training_origin'] != str(inner[-1]):
                        bad.append((rec['origin'], model, b, 'inner rows', r['validation_origin']))
                if choice != sel['alpha']:
                    bad.append((rec['origin'], model, b, 'alpha', choice, sel['alpha'], score, zero))
                expected_status = 'nested_selected' if choice is not None else 'no_correction_validated'
                if sel['status'] != expected_status:
                    bad.append((rec['origin'], model, b, 'status', sel['status']))
            use = choice if choice is not None else 3.0
            beta, contrib = solve(outer[b], b, columns, X.loc[t, columns], use, signed)
            worst['coef'] = max(worst['coef'], np.abs(beta - np.array(fit['coefficients'])).max())
            worst['pred'] = max(worst['pred'], abs(contrib.sum() - fit['prediction']))
            if not signed:
                worst['coef_free'] = max(worst['coef_free'], np.abs(beta - np.array(fit['coefficients'])).max())
                worst['pred_free'] = max(worst['pred_free'], abs(contrib.sum() - fit['prediction']))
            else:
                bound_cells.extend((rec['origin'], b, c, float(v)) for c, mine, v in zip(columns, beta, fit['coefficients']) if mine == 0.)
            if fit['applied'] != (choice is not None) or fit['alpha'] != use or fit['columns'] != columns:
                bad.append((rec['origin'], model, b, 'applied/alpha/columns'))
            applied_bands.append(contrib.sum() if choice is not None else 0.)
        path = band_means_to_months([*applied_bands, 0., 0.])
        worst['path'] = max(worst['path'], np.abs(path - np.array(rec['paths'][model])).max())

R.check('every origin estimated; outer training rows = latest 40 band-matured, released, 7-feature-complete quarter-ends (min 24)', not [b for b in bad if 'outer rows' in b or 'status' in b], str(bad[:3]))
R.check('fold sets and inner training rows equal the specification (latest 8 folds; >=16 inner rows at the fold clock; inner cap 40)', not [b for b in bad if 'fold set' in b or 'inner rows' in b])
R.check('validation scores reproduce', worst['score'] < 1e-9, f"max abs diff={worst['score']:.3e}")
R.check('no-correction loss reproduces', worst['zero'] < 1e-15, f"max abs diff={worst['zero']:.3e}")
R.check('alpha = argmin score, ties to the stronger penalty, applied only if strictly below the no-correction loss', not [b for b in bad if 'alpha' in b], str([b for b in bad if 'alpha' in b][:3]))
R.check('outer coefficients reproduce (ridge via lstsq, bounded via NNLS)', worst['coef'] < 1e-8, f"max abs diff={worst['coef']:.3e}")
R.check('unrestricted candidates: coefficients and predictions reproduce to rounding', worst['coef_free'] < 1e-12 and worst['pred_free'] < 1e-12,
        f"coef {worst['coef_free']:.3e}, prediction {worst['pred_free']:.3e}")
R.check('band predictions reproduce (bounded fit: trust-region tolerance against exact active set)', worst['pred'] < 1e-8, f"max abs diff={worst['pred']:.3e}")
saved_on_bound = pd.Series([v for *_, v in bound_cells])
R.check('gate tolerance 1e-10 recognises every coefficient that the exact active-set solution puts on the bound',
        (saved_on_bound.abs() < 1e-10).all(),
        f'exact zeros={len(saved_on_bound)}, saved |coef|<1e-10: {int((saved_on_bound.abs() < 1e-10).sum())}, missed: '
        + str([(o, b, c, v) for o, b, c, v in bound_cells if abs(v) >= 1e-10]))
R.check('monthly paths = band-mean-preserving map of [c1, c2, 0, 0]', worst['path'] < 1e-9, f"max abs diff={worst['path']:.3e}")
R.check('no other discrepancy', not bad, str(bad[:5]))
print(f'   cells checked: {n_cells}; exact score ties inside the grid: {tie_cells}; best score exactly equal to zero loss: {equal_zero_cells}')
print(f'   folds per cell: {dict(sorted(fold_counts.items()))}; outer rows per origin-band: {dict(sorted(train_counts.items()))}')
R.done()
