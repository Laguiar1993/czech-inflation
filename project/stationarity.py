"""ADF/KPSS-driven transform selection, matching CNB WP 9/2026 Section 4.1:
"we tested the stationarity of all series using the Augmented Dickey-Fuller
test and the KPSS test... each series is transformed into: (i) no
transformation, (ii) log-difference, or (iii) simple difference."

This project had picked m/m% / YoY% / level by intuition instead. Applies
to predictors where a genuine LEVEL series is available locally (most of
this project's predictors are only available already-differenced at the
source -- m/m% or YoY% -- so there's nothing to re-test for those; ADF/KPSS
needs a level to decide FROM).

ADF null = unit root (non-stationary); reject (low p) => stationary.
KPSS null = stationary; reject (low p) => non-stationary.
Combined per standard practice (e.g. Enders): both tests must AGREE the
series is stationary before accepting "no transform" -- a single test can
mislead (ADF has low power against near-unit-root; KPSS over-rejects in
small samples). Disagreement defaults to differencing, the conservative
choice matching the paper's stated behaviour of never leaving a merely
plausibly-stationary series untransformed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, kpss


def is_stationary(s: pd.Series, alpha: float = 0.05) -> dict:
    s = s.dropna()
    adf_p = adfuller(s, autolag="AIC")[1]
    with np.errstate(all="ignore"):
        kpss_p = kpss(s, regression="c", nlags="auto")[1]
    adf_stationary = adf_p < alpha       # reject unit-root null -> stationary
    kpss_stationary = kpss_p >= alpha    # fail to reject stationary null -> stationary
    return {"adf_p": round(adf_p, 4), "kpss_p": round(kpss_p, 4),
            "adf_stationary": adf_stationary, "kpss_stationary": kpss_stationary,
            "agree_stationary": adf_stationary and kpss_stationary}


def select_transform(level: pd.Series, name: str = "") -> dict:
    """Try level -> log-diff (if strictly positive) -> diff, matching the
    paper's 3-way choice, stopping at the first the ADF+KPSS pair agrees
    is stationary. Returns the chosen transform, the resulting series, and
    the full diagnostic trail (so a disagreement is visible, not hidden)."""
    trail = []
    lvl_test = is_stationary(level)
    trail.append({"transform": "level", **lvl_test})
    if lvl_test["agree_stationary"]:
        return {"name": name, "chosen": "level", "series": level, "trail": trail}

    if (level.dropna() > 0).all():
        log_diff = 100 * np.log(level).diff()
        ld_test = is_stationary(log_diff)
        trail.append({"transform": "log_diff", **ld_test})
        if ld_test["agree_stationary"]:
            return {"name": name, "chosen": "log_diff", "series": log_diff, "trail": trail}

    diff = level.diff()
    d_test = is_stationary(diff)
    trail.append({"transform": "diff", **d_test})
    chosen = "diff" if d_test["agree_stationary"] else "diff (fallback, tests still disagree)"
    return {"name": name, "chosen": chosen, "series": diff, "trail": trail}


def transform_panel(X: pd.DataFrame, min_obs: int = 20, verbose: bool = True) -> pd.DataFrame:
    """Apply select_transform to every column of X independently, matching
    the paper's "we tested the stationarity of ALL series" rather than
    hand-picking which ones look like they need it. Most of this project's
    predictors are already published as an m/m or YoY rate and will
    short-circuit at the level-stationary check (a no-op, by construction --
    ADF/KPSS correctly finds an already-differenced series stationary). The
    genuine raw-level series among the CNB-inspired additions (credit
    balances, trade balance, the admin-price fixed-base index, survey
    balances) are exactly the ones this can actually change. Columns too
    short for a meaningful ADF/KPSS read (e.g. admin_core's 26 points) are
    passed through as level rather than tested — small-sample unit-root
    tests have unreliable power and a wrong verdict there is worse than none."""
    out, chosen = {}, {}
    for col in X.columns:
        s = X[col]
        n = s.dropna().shape[0]
        if n < min_obs:
            out[col], chosen[col] = s, f"level (n={n} < {min_obs}, not tested)"
            continue
        try:
            result = select_transform(s, name=col)
            out[col], chosen[col] = result["series"].rename(col), result["chosen"]
        except Exception as e:
            out[col], chosen[col] = s, f"level (test failed: {e})"
    if verbose:
        for col, c in chosen.items():
            print(f"  {col:28s} -> {c}")
    return pd.DataFrame(out).sort_index()
