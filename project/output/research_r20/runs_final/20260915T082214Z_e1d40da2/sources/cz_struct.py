"""CZ-STRUCT: a five-component Czech CPI forecasting model.

Ridge forecasts CNB core inflation with no wage input by default. Food uses
one-sided per-origin X-13 and ridge. Fuel uses weekly pump observations.
Alcohol/tobacco uses an expanding seasonal mean. Admin uses seasonal history
and optional provenance/availability-gated announcements. Aggregation is a
statistical projection with a seasonal wedge, not an exact official identity.

Modes separate no-announcement historical forecasts, reconstructed scenarios,
and prospectively recorded announcements. Explicit decision clocks are
required by weights, admin and the shared live/pre-release fuel selector.
Underlying feature vintages and basket publication dates still include
documented approximations; these functions do not certify the live loaders.

STRUCT_PE is the cold-start past-error research column. The ADOPTED warm-
history challenger (PAST_FULL, PAST_ERROR_QRF_SPEC.md) is computed in-repo
since v2.4 as STRUCT_PE_WARM by the same `restored_pe_correction` the live
call uses; do not confuse the two specifications.

v2.4 (LIVE_PARITY_SPEC_v24.md): lagged features are built by calendar
label shift on the full index (the live edge+1 row previously lost every
CPI-family and food-pipeline lag), the decision clock gates training labels
and past-error eligibility, both frames are availability-masked live, and
each live row carries its release stage and its imputed-feature list.

Usage: python cz_struct.py (backtest) | python cz_struct.py --live
       [--target YYYY-MM] [--release-stage pre_flash|pre_final]
       [--release-dt YYYY-MM-DD] [--no-log]
"""
from __future__ import annotations
import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import COMPONENT_WEIGHTS_FALLBACK as W
from models.horizon_models import TVWQRF
from data.struct_inputs import load_services_cpi_mm, load_agri_price_mm
from data import local_adapter as la

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
warnings.filterwarnings("ignore")

RIDGE_ALPHA = 3.0
STATE_THRESHOLD = 4.0  # trailing-12m headline yoy, %
_ALC_TOBACCO_WEIGHT_PREANCHOR = 0.09498  # ECOICOP 02 share, 2014 basket (see solve_weights)
INCLUDE_WAGE = False   # audit P1: Chow-Lin uses the FULL history before the
                       # shift -- a global-interpolation leak; the no-wage
                       # core is the clean default (recent RMSE also better).
                       # Set True only for the labelled comparison variant.


def load_food_ppi_mm() -> pd.Series:
    """Food-products PPI m/m (CZ-CPA division 10, CEN0201B IZ2015 index) --
    the farmgate->shelf pipeline's processor stage. Live fetch with local
    cache fallback (data/cz_ppi_product_raw.csv)."""
    import io
    import requests
    path = os.path.join(HERE, "data", "cz_ppi_product_raw.csv")
    try:
        r = requests.get("https://data.csu.gov.cz/opendata/sady/CEN0201B/distribuce/csv",
                         headers=la.UA, timeout=120)
        r.raise_for_status()
        open(path, "wb").write(r.content)
        raw = pd.read_csv(io.BytesIO(r.content), low_memory=False)
    except Exception:
        raw = pd.read_csv(path, low_memory=False)
    u2, u3 = "CZCPA3.CZCPA_U2", "CZCPA3.CZCPA_U3"
    sub = raw[(raw[u2].astype(str).str.replace(".0", "", regex=False) == "10")
              & raw[u3].isna() & (raw["TYPUDAJE5A"] == "IZ2015")]
    m = sub[sub["CASMKMQRM12"].astype(str).str.match(r"^\d{4}-\d{2}$")]
    s = pd.Series(m["Hodnota"].values,
                  index=pd.PeriodIndex(m["CASMKMQRM12"], freq="M")).groupby(level=0).last().sort_index()
    return (100.0 * s.pct_change()).rename("food_ppi_mm")


# ---------------------------------------------------------------------------
# data assembly (all series full-history; per-origin views slice them)
# ---------------------------------------------------------------------------
def _lag(s: pd.Series, k: int, idx: pd.PeriodIndex) -> pd.Series:
    """Calendar lag: move the LABELS of `s` forward by k months, then align
    to the frame index.

    v2.4 (Fable D1 / Codex R4 P0): `Series.shift(k)` on a PeriodIndex moves
    values within the source's own index and never extends it, so the live
    edge+1 row could never receive core(edge); and a positional shift across
    a gap in the source hands the previous ROW to the previous MONTH. A
    label shift (`shift(k, freq="M")`) fixes both: gaps stay NaN, the edge
    rows receive released values, and history older than the frame index
    still feeds the first rows (reindex-then-shift lost it -- caught by the
    pre/post frame diff)."""
    if not isinstance(s.index, pd.PeriodIndex):
        raise TypeError(f"_lag expects a monthly PeriodIndex, got {type(s.index).__name__}")
    return s.shift(k, freq="M").reindex(idx)


def assemble_feature_frames(full_idx: pd.PeriodIndex, *, core: pd.Series,
                            trailing_yoy: pd.Series, exp12: pd.Series,
                            exp36: pd.Series, household_exp: pd.Series,
                            esi: pd.Series, eurczk_mm: pd.Series,
                            services: pd.Series, imports: pd.Series,
                            food: pd.Series, agri_shifted: pd.Series,
                            food_ppi: pd.Series, wage: pd.Series | None = None):
    """Build (feats, feats_st, food_feats) on `full_idx` from raw monthly
    series. Pure function of its inputs (no loaders), so the edge+1/edge+2
    row construction is unit-testable offline (test_live_parity.py).
    `agri_shifted` follows the loader convention: label u holds agri(u-1)."""
    feats = pd.DataFrame(index=full_idx)
    feats["exp12"] = exp12.reindex(full_idx)
    feats["exp36"] = exp36.reindex(full_idx)
    feats["household_exp"] = household_exp.reindex(full_idx)
    feats["esi"] = esi.reindex(full_idx)
    feats["eurczk_mm"] = eurczk_mm.reindex(full_idx)
    feats["services_l1"] = _lag(services, 1, full_idx)
    if wage is not None:
        feats["wage_l3"] = _lag(wage, 3, full_idx)
    feats["import_l2"] = _lag(imports, 2, full_idx)
    feats["core_l1"] = _lag(core, 1, full_idx)
    feats["core_l2"] = _lag(core, 2, full_idx)
    feats["core_l12"] = _lag(core, 12, full_idx)
    # an UNKNOWN trailing y/y must stay NaN: `(NaN > 4)` is False, which
    # would silently declare a low-inflation state (Codex R4)
    ty_l1 = _lag(trailing_yoy, 1, full_idx)
    feats["state"] = (ty_l1 > STATE_THRESHOLD).astype(float).where(ty_l1.notna())
    for c in ["eurczk_mm", "exp12", "import_l2"]:
        feats[f"{c}_x_state"] = feats[c] * feats["state"]
    for m in range(2, 13):
        feats[f"mon_{m}"] = (feats.index.month == m).astype(float)

    # smooth-transition variant of the same frame: logistic weight around
    # the 4% threshold (width 1pp) replaces the hard dummy -- tested as
    # STRUCT_ST, adopted only if it wins the untouched frames.
    feats_st = feats.copy()
    st = 1.0 / (1.0 + np.exp(-(ty_l1 - STATE_THRESHOLD)))
    feats_st["state"] = st
    for c in ["eurczk_mm", "exp12", "import_l2"]:
        feats_st[f"{c}_x_state"] = feats_st[c] * st

    food_feats = pd.DataFrame(index=full_idx)
    food_feats["food_l1"] = _lag(food, 1, full_idx)
    food_feats["food_l12"] = _lag(food, 12, full_idx)
    food_feats["agri_l0"] = agri_shifted.reindex(full_idx)      # = agri(M-1)
    food_feats["agri_l1"] = _lag(agri_shifted, 1, full_idx)     # = agri(M-2)
    # v1.5 processor stage: food-products PPI (CZ-CPA 10, CEN0201B, monthly
    # 2015+, CONTINUING). PPI(M) publishes ~16th M+1 -- after both the flash
    # (~day 4-6 M+1) and the full print (~day 10), so only PPI(M-1),
    # published mid-M, is ever usable at h0 (user-verified timing).
    food_feats["food_ppi_l1"] = _lag(food_ppi, 1, full_idx)
    # de_food_l1 REMOVED (v1.4, user rule "only variables that continue"):
    # DE food HICP died at 2025-12 in the Eurostat EU-2016/792 re-cut -- it
    # was silently mean-imputed for every 2026 row. LIVE-CONTINUITY RULE:
    # every input must have a publishing source; the freshness tripwire in
    # struct_live() enforces it (>6m lag behind the CPI edge = hard warn).
    # month dummies intentionally absent: the food block deseasonalizes its
    # TARGET with per-origin one-sided X-13 instead (v1.1 -- the treatment
    # that cut the 4-way food RMSE 26%); see food_forecast().
    return feats, feats_st, food_feats


def _trailing_yoy(monthly_mm: pd.Series) -> pd.Series:
    """Compound twelve monthly percent changes; incomplete windows remain NaN."""
    return 100.0 * ((1 + monthly_mm / 100.0).rolling(12)
                    .apply(np.prod, raw=True) - 1)


def load_all():
    y = la.load_headline_cpi_mm()
    comp = la.load_component_targets()          # food, fuel (official), core_admin
    core = la.fetch_cnb_core_inflation_mm_live().rename("core")
    reg = la.fetch_cnb_regulated_prices_mm_live().rename("reg")
    ext = la.load_headline_cpi_mm_extended()
    # audit fix: COMPOUND the monthly rates for a true y/y (summing them
    # understated the state variable at high inflation)
    trailing_yoy = _trailing_yoy(ext).rename("trail_yoy")

    base_idx = y.index.union(core.index)
    # extend two months past the CPI edge so LIVE origins (the just-closed
    # month = edge+1, and the current calendar month = edge+2) have feature
    # rows: in-month series (FX/ESI/expectations) fill from their own
    # publications, CPI-family lags from the released months (v2.4: built
    # on this FULL index, see _lag), and anything unpublished stays NaN ->
    # training-mean imputation inside _ridge_predict.
    full_idx = base_idx.union(
        pd.period_range(base_idx.max() + 1, base_idx.max() + 2, freq="M"))
    feats, feats_st, food_feats = assemble_feature_frames(
        full_idx, core=core, trailing_yoy=trailing_yoy,
        exp12=la.load_inflation_expectations(12),
        exp36=la.load_inflation_expectations(36),
        household_exp=la.fetch_household_price_expectations_live(),
        esi=la.load_esi(),
        eurczk_mm=la.load_fx_monthly_mm()["eurczk_mm"],
        services=load_services_cpi_mm(),
        imports=la.fetch_import_prices_mm_live(),
        food=comp["food"],
        agri_shifted=load_agri_price_mm(),   # label u holds agri(u-1)
        food_ppi=load_food_ppi_mm(),
        wage=la.load_wage_mm_chowlin() if INCLUDE_WAGE else None)

    recon = (W["food"] * comp["food"] + W["fuel"] * comp["fuel"]
             + W["core"] * core + W["administered"] * reg)
    wedge = (y - recon).rename("wedge")
    return y, comp, core, reg, feats, feats_st, food_feats, wedge


def _regime(p: pd.Period) -> int:
    """Weight-regime key, CORRECTED per the Codex audit (P0 #3): official
    effective windows are EVEN-year pairs -- basis-2022 weights are in force
    in 2024/2025, basis-2024 in 2026 (CZSO basket archive; the odd-year
    basis+1..+2 assumption applied the wrong basket in several years).
    Regime = even start year of the two-year window."""
    yr = p.year
    return yr - (yr % 2)  # 2024-25 -> 2024, 2026-27 -> 2026, ...


_RELEASE_HOUR = 9  # CZSO publishes at 09:00 Prague local time
_CAL_PATH = os.path.join(HERE, "data", "release_calendar_cz_cpi.csv")
_CAL = None
_FALLBACK_DETAIL_DAY = 20  # months outside the calendar (pre-2010): conservative


def _release_calendar() -> pd.DataFrame:
    """Sourced release calendar (TIMING_SPEC_v25 T1): per target month the
    FIRST release (regular before 2025, flash from 2025) and the DETAILED
    release, both at 09:00 Prague wall time. Built by
    tools/build_release_calendar.py from the Bloomberg release-event tables
    and the CZSO release pages; future months are typed by the operator."""
    global _CAL
    if _CAL is None:
        c = pd.read_csv(_CAL_PATH)
        c["p"] = pd.PeriodIndex(c["target_month"], freq="M")
        for col in ("first_release_dt", "detail_release_dt"):
            c[col] = (pd.to_datetime(c[col], errors="coerce").dt.normalize()
                      + pd.Timedelta(hours=_RELEASE_HOUR))
        _CAL = c.set_index("p")
    return _CAL


def _first_release_dt(target: pd.Period):
    cal = _release_calendar()
    return cal.loc[target, "first_release_dt"] if target in cal.index else pd.NaT


def _detail_release_dt(target: pd.Period):
    cal = _release_calendar()
    return cal.loc[target, "detail_release_dt"] if target in cal.index else pd.NaT


def _basket_available_from(regime_start: int) -> pd.Timestamp:
    """Publication date of a basket, kept SEPARATE from its effective year
    (audit P0 #3). The new basket is published with the January DETAILED
    CPI release of the effective year (v2.5 / D6: no longer the January
    flash date). Fallback for years outside the calendar: Feb-15."""
    d = _detail_release_dt(pd.Period(f"{regime_start}-01", "M"))
    return pd.Timestamp(d).normalize() if pd.notna(d) else pd.Timestamp(regime_start, 2, 15)


def _petrol_share(t: pd.Period, as_of: pd.Timestamp) -> float:
    """Publication-gated official petrol/diesel blend (v2.3/F2): the target
    regime's basket share applies only from its publication date; before it
    the previous regime's share is used (mirrors solve_weights anchors)."""
    from models.components import petrol_share_for_regime
    rg = _regime(t)
    src = rg if _basket_available_from(rg) <= pd.Timestamp(as_of) else rg - 2
    return petrol_share_for_regime(src)


# Rule-based availability calendar for the live as-of mask (review sec. 3:
# "feature builders still lack a unified per-observation as-of selector").
# These are DOCUMENTED PUBLICATION RULES, not recorded vintages: day of the
# month (of period t or t+1) from which the column's value for row t is
# public. None = available from the start of t (market/administrative data).
_COL_AVAILABILITY_RULE = {
    "exp12": ("t", 16), "exp36": ("t", 16),          # CNB FMIE ~mid-month
    "household_exp": ("t", 28), "esi": ("t", 28),    # EC surveys ~month-end
    "eurczk_mm": ("t+1", 1),                          # full-month average (D5: MTD
                                                      # average is the next-batch item)
    "services_l1": ("t", 11), "core_l1": ("t", 11),  # CPI family for t-1 ~10th of t
    "core_l2": ("t", 1), "core_l12": ("t", 1),
    "state": ("t", 11),                               # trailing y/y through t-1 needs CPI(t-1)
    "import_l2": ("t", 16),
    # food frame (v2.4: the live mask covers BOTH frames)
    "food_l1": ("t", 11), "food_l12": ("t", 1),
    "agri_l0": ("t", 26),                             # agri PPI(t-1) publishes ~25 days into t
    "agri_l1": ("t", 1), "food_ppi_l1": ("t", 16),   # food PPI(t-1): CZSO rule
                                                      # 16th day after the month
                                                      # + month exceptions below
}
# CZSO "Indexy cen vyrobcu" (011047): 16th calendar day after the reference
# month, with the annual list's exceptions by REFERENCE month -- January +9
# (25 February), March and April +4, June and December +1
# (data/czso_release_rules_2026.csv). v2.7.1, Codex R8 timing probe: the flat
# day-16 rule admitted the January-2026 food PPI on 20 February although CZSO
# published it on the 25th. The agricultural average-price table (agri_l0)
# is a different CZSO product and keeps its later day-26 rule.
_PPI_MONTH_EXCEPTIONS = {1: 9, 3: 4, 4: 4, 6: 1, 12: 1}
_PPI_RULE_COLS = {"food_ppi_l1"}


def _availability_rule(col: str, t: pd.Period):
    """(reference month, day) from which column `col` of row t is public."""
    ref, day = _COL_AVAILABILITY_RULE[col]
    if col in _PPI_RULE_COLS:
        day = day + _PPI_MONTH_EXCEPTIONS.get((t - 1).month, 0)
    return ref, day


def _mask_row_by_availability(frame: pd.DataFrame, t: pd.Period,
                              as_of: pd.Timestamp) -> pd.DataFrame:
    """Return a copy of `frame` with row t's columns nulled wherever the
    rule says the value is not yet public at `as_of` (imputation then
    treats them as missing). Works for the core AND the food frame (v2.4);
    masking `state` also masks every interaction. Live-call guard only;
    backtest rows keep the documented end-of-month assumption."""
    out = frame.copy()
    if t not in out.index:
        return out
    for col in _COL_AVAILABILITY_RULE:
        if col not in out.columns:
            continue
        ref, day = _availability_rule(col, t)
        if col in _CPI_LAG1_COLS:
            # v2.6 (Codex R6 blocker 1): CPI-family lags follow the sourced
            # release calendar, the same lookup _classify_missing uses -- the
            # day-11 rule admitted January-2026 inputs on 12 February although
            # CZSO published on the 13th
            hidden = not _cpi_family_released_by(t - 1, as_of)
        else:
            base = t.to_timestamp() if ref == "t" else (t + 1).to_timestamp()
            hidden = as_of < base + pd.Timedelta(days=day - 1)
        if hidden:
            out.loc[t, col] = np.nan
            if f"{col}_x_state" in out.columns:
                out.loc[t, f"{col}_x_state"] = np.nan
            if col == "state":
                for c in [c for c in out.columns if c.endswith("_x_state")]:
                    out.loc[t, c] = np.nan
    return out


def _cpi_family_released_by(u: pd.Period, as_of) -> bool:
    """The CPI-family value for month u (headline, divisions, CNB core and
    regulated) is public from the DETAILED release of u at 09:00 Prague,
    looked up in the sourced release calendar (v2.5 / TIMING_SPEC T1; the
    v2.4 day-11 rule admitted January-2026 two days early -- CZSO published
    on 13 February). Months outside the calendar fall back to the 20th of
    the following month. A missing clock means 'no restriction' (the
    backtest passes its checkpoint clocks explicitly)."""
    if as_of is None or pd.isna(as_of):
        return True
    d = _detail_release_dt(u)
    if pd.isna(d):
        if u >= _release_calendar().index.min():
            return False   # inside/after the calendar's span but not recorded:
                           # FAIL CLOSED until the operator adds the CZSO date
        d = (u + 1).to_timestamp() + pd.Timedelta(days=_FALLBACK_DETAIL_DAY - 1,
                                                  hours=_RELEASE_HOUR)
    return pd.Timestamp(as_of) >= d


def _released_index(idx: pd.PeriodIndex, as_of) -> np.ndarray:
    """Boolean mask over a monthly index: released by `as_of` per the calendar."""
    if as_of is None or pd.isna(as_of):
        return np.ones(len(idx), dtype=bool)
    return np.array([_cpi_family_released_by(u, as_of) for u in idx], dtype=bool)


def _eligible_edge(idx: pd.PeriodIndex, known_through: pd.Period, as_of):
    """Latest month <= known_through whose CPI-family value is released at
    `as_of` (the information-set fingerprint used to reuse fits between the
    month-end and release-eve checkpoints)."""
    ok = [u for u in idx if u <= known_through and _cpi_family_released_by(u, as_of)]
    return max(ok) if ok else None


def _eligible_error_history(core: pd.Series, origin: pd.Period, as_of,
                            feats: pd.DataFrame | None = None) -> pd.Series:
    """Warm past-error history eligible at (origin, as_of): the frozen file
    (data/exact_historical_core_errors.csv, Codex generator, 136 errors from
    2015-04) extended with sequential ridge errors of any newer month, then
    restricted to months u <= origin-1 whose core(u) is RELEASED by `as_of`
    (v2.4: the clock is enforced; before, `as_of` was accepted and ignored)."""
    hist = pd.read_csv(os.path.join(HERE, "data",
                                    "exact_historical_core_errors.csv"),
                       index_col=0)
    errs = pd.Series(hist.iloc[:, 0].values,
                     index=pd.PeriodIndex(hist.index, freq="M")).sort_index()
    # extend past the frozen edge with newly released months
    for u in pd.period_range(errs.index.max() + 1, origin - 1, freq="M"):
        cu = core.get(u, np.nan)
        if np.isnan(cu) or feats is None or not _cpi_family_released_by(u, as_of):
            continue
        p_u, _, _ = _ridge_predict(feats, core, u)   # sequential: labels <= u-1
        if not np.isnan(p_u):
            errs[u] = cu - p_u
    errs = errs[errs.index <= origin - 1]
    errs = errs[[_cpi_family_released_by(u, as_of) for u in errs.index]]
    return errs.dropna()


def restored_pe_correction(feats: pd.DataFrame, core: pd.Series,
                           origin: pd.Period, as_of: pd.Timestamp,
                           return_details: bool = False):
    """The restored past-error challenger (PAST_FULL), per
    PAST_ERROR_QRF_SPEC.md: frozen warm error history extended on the fly
    with newer released months' sequential ridge errors; second
    standardization (impute training means, ddof=1 std); TVWQRF with the
    spec's exact settings (this repo's class IS the spec). Used by BOTH the
    live call and, since v2.4, the backtest (`STRUCT_PE_WARM`), with the
    error eligibility clock enforced by _eligible_error_history."""
    errs = _eligible_error_history(core, origin, as_of, feats)
    if len(errs) < 40:
        return (0.0, {}) if return_details else 0.0
    Xp = feats.loc[errs.index].values.astype(float)
    mu = np.nanmean(Xp, axis=0)
    mu = np.where(np.isfinite(mu), mu, 0.0)
    Xp = np.where(np.isfinite(Xp), Xp, mu)
    sd = Xp.std(axis=0, ddof=1)
    sd = np.where(sd > 0, sd, 1.0)
    Z = (Xp - mu) / sd
    xr = feats.loc[origin].values.astype(float)
    xr = (np.where(np.isfinite(xr), xr, mu) - mu) / sd
    try:
        corr = float(TVWQRF(n_estimators=200).fit_predict(
            Z, errs.values, xr)["point"])
    except Exception:
        corr = 0.0
    if return_details:
        return corr, {"pe_Z": Z, "pe_errs": errs.values,
                      "pe_err_idx": [str(i) for i in errs.index], "pe_x": xr}
    return corr


def load_alc_tobacco_mm() -> pd.Series:
    """Division 02 (alcohol & tobacco) m/m from cpi_czso.cpi_long -- the
    fifth explicit component (audit P0 #4). Matches Codex's frozen
    component_mm.csv to floating point on the overlap."""
    con = la._con()
    df = con.sql("""
        SELECT date, value FROM cpi_czso.cpi_long
        WHERE coicop_code = '02' AND base = 'base_2015_eq_100'
          AND hh_group_code = '0' AND subgroup_code = ''
        ORDER BY date
    """).df()
    con.close()
    s = pd.Series(df["value"].values,
                  index=pd.PeriodIndex(pd.to_datetime(df["date"]), freq="M")).groupby(level=0).last()
    return (100.0 * s.pct_change()).rename("alc_tobacco_mm")


def alc_forecast(alc: pd.Series, target: pd.Period, known_through: pd.Period,
                 as_of=None) -> float:
    """Per Codex's declared spec: expanding average for the target's
    calendar month using only prior observations; historical overall
    average until three same-month observations exist. v2.5: observations
    must also be RELEASED at `as_of` (calendar), not merely <= known_through."""
    hist = alc.dropna()
    hist = hist[hist.index <= known_through]
    hist = hist[_released_index(hist.index, as_of)]
    if not len(hist):
        return 0.0
    same = hist[hist.index.month == target.month]
    return float(same.mean()) if len(same) >= 3 else float(hist.mean())


def solve_weights(y: pd.Series, comp: pd.DataFrame, core: pd.Series,
                  reg: pd.Series, known_through: pd.Period, *,
                  as_of: pd.Timestamp, alc: pd.Series | None = None) -> dict:
    """Five-component statistical projection using prior released outcomes.

    Food/fuel/alcohol anchors use effective-year baskets with a separate
    publication rule. Admin is an estimated projection coefficient, not
    the official CNB regulated-price share; sum-to-one is a constraint,
    not proof of an exact CPI accounting identity. The February-15 basket
    dates remain documented assumptions pending sourced release dates.
    """
    if pd.isna(as_of):
        raise ValueError("solve_weights requires a valid decision timestamp")
    as_of = pd.Timestamp(as_of)
    if alc is None:
        alc = load_alc_tobacco_mm()
    j = pd.concat([y.rename("y"), comp["food"], comp["fuel"],
                   alc.rename("alc"), core.rename("core"),
                   reg.rename("adm")], axis=1).dropna()
    j = j[j.index <= known_through]
    j = j[_released_index(j.index, as_of)]   # v2.5: released at the clock, not just <= known_through
    regimes = sorted({_regime(p) for p in j.index} | {_regime(known_through + 1),
                                                     _regime(known_through + 12)})
    # pre-anchor fallback for the first regime only (Codex R6: every one of
    # the 90 evaluated origins uses a sourced basket anchor, so this value
    # never enters the scored window). Alcohol+tobacco = ECOICOP 02 share of
    # the 2014 basket, 94.98 per mille (data/baskets/spot_kos2014.xlsx),
    # replacing the earlier undocumented 0.087.
    out, prev = {}, {"food": W["food"], "fuel": W["fuel"], "alc": _ALC_TOBACCO_WEIGHT_PREANCHOR,
                     "administered": W["administered"]}
    for rg in regimes:
        rows = j[[_regime(p) == rg for p in j.index]]
        # basket ANCHORS are available only from their publication date
        # (audit P0 #3: effective year != availability); before it, the
        # previous window's anchors apply to real-time calls.
        src = rg if _basket_available_from(rg) <= as_of else rg - 2
        wf = _OFFICIAL_FOOD.get(src, prev["food"])
        wu = _OFFICIAL_FUEL.get(src, prev["fuel"])
        wa2 = _OFFICIAL_ALC.get(src, prev["alc"])
        wadm = prev["administered"]
        if len(rows) >= 4:
            # only the admin share is unobserved -> single-unknown OLS:
            # y - wf*food - wu*fuel - wa2*alc - (1-wf-wu-wa2)*core
            #   = w_adm * (adm - core)
            lhs = (rows["y"] - wf * rows["food"] - wu * rows["fuel"]
                   - wa2 * rows["alc"]
                   - (1 - wf - wu - wa2) * rows["core"]).values
            x = (rows["adm"] - rows["core"]).values
            if float(x @ x) > 1e-9:
                wadm = float(np.clip((x @ lhs) / (x @ x), 0.08, 0.30))
        # audit P0 #3 carryover fix: core is ALWAYS the residual of the
        # current anchors -- never a stale carried share (the old code left
        # weight sums at 0.98683 in Jan-Apr 2025, 15/90 origins).
        cand = {"food": wf, "fuel": wu, "alc": wa2, "administered": wadm,
                "core": 1.0 - wf - wu - wa2 - wadm}
        out[rg] = cand
        prev = cand
    return out  # regime -> 5-component weights, sum exactly 1 by construction


# Official anchors, CORRECTED (audit P0 #3): values from the CZSO basket
# archive per EFFECTIVE even-year window (audit table, verified against
# archived c_basket spreadsheets incl. c_basket2025.xlsx). Alcohol/tobacco
# (division 02, audit P0 #4) from cpi_czso.cpi_weights with the corrected
# basis->effective mapping (basis+2): CNB's analytical food aggregate
# includes div-02 while CNB core excludes it, so a four-block split hid
# ~8.3% of the basket inside solved core/wedge terms.
_OFFICIAL_FOOD = {2014: 0.170824417, 2016: 0.180607978, 2018: 0.177627679,
                  2020: 0.177174296, 2022: 0.178075443, 2024: 0.177431636,
                  2026: 0.168584131}
_OFFICIAL_FUEL = {2014: 0.036468729, 2016: 0.033423797, 2018: 0.029072694,
                  2020: 0.034251810, 2022: 0.031772263, 2024: 0.035444108,
                  2026: 0.030630713}
_OFFICIAL_ALC = {2014: 0.094979744, 2016: 0.093386880, 2018: 0.092144617,
                 2020: 0.086973141, 2022: 0.086948337, 2024: 0.084622084,
                 2026: 0.082870815}  # archived official baskets, effective windows


def _ridge_predict(Xdf: pd.DataFrame, ydf: pd.Series, origin: pd.Period,
                   alpha: float = RIDGE_ALPHA, h: int = 0, as_of=None):
    """Expanding ridge, direct h-step: fit rows feats(t) -> y(t+h) using
    only targets released before the origin's own decision date, predict
    the origin row (i.e. y(origin+h)). h=0 is the nowcast alignment; h=1
    trains feats(t)->y(t+1) on t <= origin-2 and forecasts next month from
    the origin row. Mean-impute on the training slice. `as_of` (v2.4)
    additionally drops labels y(t+h) not yet released at the decision clock
    (no-op for the backtest's end-of-month clock)."""
    if h:
        ydf = ydf.shift(-h)
    train_idx = ydf.dropna().index
    train_idx = train_idx[train_idx <= origin - 1 - h]
    if as_of is not None and not pd.isna(as_of):
        train_idx = train_idx[[_cpi_family_released_by(u + h, as_of) for u in train_idx]]
    if len(train_idx) < 48:
        return np.nan, None, None
    Xt = Xdf.loc[train_idx]
    mu = Xt.mean()
    Xt = Xt.fillna(mu)
    if origin not in Xdf.index:
        return np.nan, None, None
    xrow = Xdf.loc[[origin]].fillna(mu)
    ys = ydf.loc[train_idx].values
    m, s = Xt.mean().values, Xt.std().replace(0, 1.0).values
    Z = (Xt.values - m) / s
    z0 = (xrow.values - m) / s
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (ys - ys.mean()))
    pred = float(ys.mean() + (z0 @ beta)[0])
    fitted = ys.mean() + Z @ beta
    resid = pd.Series(ys - fitted, index=train_idx)
    return pred, resid, (Z, z0, train_idx)


_X13_CACHE: dict = {}
FOOD_DIAG: dict = {"method": "", "history_end": "", "n_obs": 0, "x13_error": ""}  # last food_forecast call


def food_forecast(food: pd.Series, food_feats: pd.DataFrame,
                  origin: pd.Period, h: int = 0, as_of=None) -> float:
    """v1.1 food block: per-origin ONE-SIDED X-13 on the food target (fit
    only on history through origin-1), ridge on the SA series with the
    pipeline features, then add back the target month's seasonal factor
    (mean of that calendar month's fitted factor, last 3 years). Falls back
    to plain ridge (with an expanding same-month mean feature) on X13Error
    at short histories."""
    from statsmodels.tsa.x13 import x13_arima_analysis
    import hashlib
    hist = food.dropna()
    hist = hist[hist.index <= origin - 1]
    # v2.5 (TIMING_SPEC T2): the history entering X-13 must itself be
    # RELEASED at the decision clock -- filtering only the ridge labels left
    # the seasonal factors exposed to an unpublished last observation.
    hist = hist[_released_index(hist.index, as_of)]
    # v2.5 (T3): content-keyed cache -- a changed vintage or cutoff refits
    key = (str(origin), str(hist.index.max()) if len(hist) else "", len(hist),
           hashlib.sha1(np.ascontiguousarray(hist.values, dtype=float).tobytes()).hexdigest())
    # v2.6 (Codex R6): the fallback is no longer silent -- every call leaves
    # its method, history end, observation count and any X-13 error here,
    # and the live row records them
    FOOD_DIAG.update(method="", history_end=str(hist.index.max()) if len(hist) else "",
                     n_obs=int(len(hist)), x13_error="")
    try:
        if key in _X13_CACHE:
            sa, seas = _X13_CACHE[key]
        else:
            ts = hist.copy()
            ts.index = ts.index.to_timestamp()
            sa = x13_arima_analysis(ts, x12path=la._X13_PATH, prefer_x13=True).seasadj
            sa.index = hist.index
            seas = (hist - sa).dropna()
            _X13_CACHE[key] = (sa, seas)
        s_m = seas[seas.index.month == (origin + h).month]
        s_add = float(s_m.iloc[-3:].mean()) if len(s_m) else 0.0
        pred_sa, _, _ = _ridge_predict(food_feats, sa, origin, h=h, as_of=as_of)
        if np.isnan(pred_sa):
            raise ValueError("ridge returned nan")
        FOOD_DIAG["method"] = "x13"
        return pred_sa + s_add
    except Exception as e:
        FOOD_DIAG["method"] = "fallback"
        FOOD_DIAG["x13_error"] = f"{type(e).__name__}: {str(e)[:160]}"
        ff = food_feats.copy()
        # the fallback seasonal feature uses the same released history; the
        # origin row gets the mean of its calendar month's released values
        ff["seas_mean"] = hist.groupby(hist.index.month).transform(
            lambda s: s.expanding().mean().shift(1)).reindex(ff.index)
        same = hist[hist.index.month == origin.month]
        if origin in ff.index and len(same):
            ff.loc[origin, "seas_mean"] = float(same.mean())
        pred, _, _ = _ridge_predict(ff, food, origin, h=h, as_of=as_of)
        return pred


_ANN_PATH = os.path.join(HERE, "data", "admin_announcements_history.csv")
_ANN = None


def _announcements() -> pd.DataFrame:
    global _ANN
    if _ANN is None:
        cal = pd.read_csv(_ANN_PATH)
        cal["p"] = pd.PeriodIndex(cal["effective_month"], freq="M")
        cal["available_from"] = pd.to_datetime(cal["available_from"], errors="coerce")
        if "provenance" not in cal.columns:
            cal["provenance"] = "reconstructed"
        for c in ("elec_pct", "gas_pct", "heat_pct"):
            # v2.7.1: documented rows carry the per-fuel January change in
            # percent; the headline contribution is computed at call time
            # from the basket item weights AVAILABLE at the clock and the
            # block value from the CALL's administered weight (Codex R8:
            # no fitted coefficient is ever stored as historical data)
            cal[c] = pd.to_numeric(cal[c], errors="coerce") if c in cal.columns else np.nan
        _ANN = cal.set_index("p")[["announced_regulated_mm_est_pct",
                                   "available_from", "provenance",
                                   "elec_pct", "gas_pct", "heat_pct"]]
    return _ANN


# CPI basket item weights per mille (data/baskets/spot_kos{year}.xlsx):
# electricity 04.510, NETWORK gas 04.521 (bottled gas does not follow the
# tariff), heat and hot water 04.550. Keyed by even-year regime; a regime is
# usable only from its publication date (_basket_available_from), so the
# January-2022 call prices its announcement with the 2020 basket.
_ENERGY_ITEM_WEIGHTS = {2018: (42.691506, 24.364113, 18.258486),
                        2020: (38.545494, 21.844207, 15.840397),
                        2022: (39.641749, 18.954230, 13.662301),
                        2024: (44.265709, 19.084379, 14.680841),
                        2026: (43.034809, 17.985589, 12.003732)}
# v2.7.1 gate threshold in ECONOMIC units: |headline contribution| >= 1.1 pp
# of the monthly CPI (= the frozen |a| >= 8 block units at the 2019-2026
# mean solved administered weight of about 0.14; the firing set 2022-01 and
# 2023-01 is unchanged, the calm Januaries stay below 0.75 pp in absolute
# value). Legacy reconstructed rows keep their block-unit threshold.
_GATE_HEADLINE_PP = 1.1
_GATE_BLOCK_UNITS_LEGACY = 8.0


def _energy_item_weights_at(target: pd.Period, as_of: pd.Timestamp) -> tuple:
    """(electricity, gas, heat) per-mille weights of the latest basket
    regime not after the target's regime AND published by `as_of`."""
    rg = _regime(target)
    usable = [r for r in _ENERGY_ITEM_WEIGHTS
              if r <= rg and _basket_available_from(r) <= pd.Timestamp(as_of)]
    if not usable:
        return _ENERGY_ITEM_WEIGHTS[min(_ENERGY_ITEM_WEIGHTS)]
    return _ENERGY_ITEM_WEIGHTS[max(usable)]


def _gate_event(target: pd.Period, as_of: pd.Timestamp, announce_mode: str):
    """The governing admitted announcement row for `target` at `as_of`
    (latest publication on or before the clock among the provenances the
    mode allows), or None. FAIL-CLOSED on undated rows."""
    if pd.isna(as_of):
        return None
    as_of = pd.Timestamp(as_of)
    ann = _announcements()
    if target not in ann.index:
        return None
    allowed = {"verified_only": set(),
               "reconstructed_scenario": {"reconstructed", "prospective"},
               "prospective_announced": {"prospective"},
               # v2.7 (ANNOUNCEMENT_ADOPTION_v27, user decision): documented
               # entries -- sourced from dated documents by the frozen rule --
               # enter the scored block; reconstructed magnitudes never do
               "documented": {"sourced_retrospective", "prospective"}}[announce_mode]
    rows = ann.loc[[target]]
    rows = rows[rows["provenance"].astype(str).isin(allowed)]
    rows = rows[rows["available_from"].notna() & (rows["available_from"] <= as_of)]
    if rows.empty:
        return None
    return rows.sort_values("available_from").iloc[-1]


def _gate_headline_pp(target: pd.Period, as_of: pd.Timestamp,
                      announce_mode: str = "documented") -> float:
    """Headline contribution (pp of monthly CPI) of the governing documented
    row: sum(item weight / 1000 x per-fuel change), with the item weights
    of the basket available at the clock. NaN when no row governs, when the
    row has no per-fuel changes (legacy block-unit rows), or when it is
    below the economic threshold."""
    row = _gate_event(target, as_of, announce_mode)
    if row is None:
        return np.nan
    pcts = [row.get("elec_pct", np.nan), row.get("gas_pct", np.nan), row.get("heat_pct", np.nan)]
    if not all(np.isfinite(p) for p in pcts):
        return np.nan
    we, wg, wh = _energy_item_weights_at(target, as_of)
    pp = (we * pcts[0] + wg * pcts[1] + wh * pcts[2]) / 1000.0
    return float(pp) if abs(pp) >= _GATE_HEADLINE_PP else np.nan


def _gate_fires(target: pd.Period, as_of: pd.Timestamp, announce_mode: str) -> bool:
    """True when an admitted row for `target` passes its threshold (economic
    units for documented rows, block units for legacy reconstructed rows)."""
    row = _gate_event(target, as_of, announce_mode)
    if row is None:
        return False
    if np.isfinite(_gate_headline_pp(target, as_of, announce_mode)):
        return True
    a = row.get("announced_regulated_mm_est_pct", np.nan)
    return bool(announce_mode == "reconstructed_scenario"
                and row.get("provenance") == "reconstructed"
                and np.isfinite(a) and abs(a) >= _GATE_BLOCK_UNITS_LEGACY
                and not all(np.isfinite(row.get(c, np.nan)) for c in ("elec_pct", "gas_pct", "heat_pct")))


def _gate_value(target: pd.Period, as_of: pd.Timestamp,
                announce_mode: str = "verified_only",
                w_adm: float | None = None) -> float:
    """Announced regulated-block shock for `target` in BLOCK units (regulated
    m/m percent) under an explicit as_of timestamp and provenance mode.

    v2.7.1 (Codex R8): documented rows are stored as per-fuel changes; the
    headline contribution sum(weight/1000 x change) is weight-independent and
    the block value is headline_pp / w_adm with the CALL's administered
    weight -- the same weight the recombination multiplies it by, so the
    headline effect never depends on a coefficient fitted at another time.
    Legacy reconstructed rows (scenario column only) keep their stored block
    units and the |a| >= 8 threshold.

    FAIL-CLOSED: undated or not-yet-public rows are rejected; the availability
    test is available_from <= as_of with the ACTUAL decision timestamp.

    announce_mode: 'verified_only' (nothing), 'reconstructed_scenario'
    (reconstructed + prospective), 'prospective_announced' (prospective),
    'documented' (sourced_retrospective + prospective; v2.7 scored mode).
    """
    row = _gate_event(target, as_of, announce_mode)
    if row is None:
        return np.nan
    pp = _gate_headline_pp(target, as_of, announce_mode)
    if np.isfinite(pp):
        if w_adm is None or not np.isfinite(w_adm) or w_adm <= 0:
            raise ValueError("documented announcement rows are priced in headline units; "
                             "pass the call's administered weight (w_adm)")
        return float(pp / w_adm)
    if all(np.isfinite(row.get(c, np.nan)) for c in ("elec_pct", "gas_pct", "heat_pct")):
        return np.nan   # documented row below the economic threshold
    if announce_mode != "reconstructed_scenario" or row.get("provenance") != "reconstructed":
        return np.nan  # incomplete economic rows never inherit legacy units
    a = row.get("announced_regulated_mm_est_pct", np.nan)
    if not np.isfinite(a) or abs(a) < _GATE_BLOCK_UNITS_LEGACY:
        return np.nan
    return float(a)


def admin_forecast(reg: pd.Series, origin: pd.Period,
                   mode: str = "announced",
                   known_through: pd.Period | None = None,
                   as_of: pd.Timestamp | None = None,
                   announce_mode: str = "verified_only",
                   allow_oracle: bool = False,
                   w_adm: float | None = None) -> float:
    """Sticky seasonal path + January announcement gate.

    `w_adm` (v2.7.1): the administered weight of THIS call, required whenever
    a documented row fires (its stored per-fuel changes are converted to
    block units with the same weight the recombination applies).

    mode='announced' (default, PROXY-FREE): January override comes from
    data/admin_announcements_history.csv -- sourced ERU/government/supplier
    announcements with available_from dates all preceding the January they
    price (see the CSV's notes for the bill->regulated mapping). Fires when
    |announced regulated m/m estimate| >= 8 (only 2022/2023 in history).
    mode='proxy': the earlier realized-January-regulated stand-in, kept for
    comparison; overstates ex-ante information.
    """
    if mode not in {"announced", "proxy"}:
        raise ValueError(f"Unknown admin mode: {mode}")
    if mode == "proxy" and not allow_oracle:
        raise ValueError("Realized-target proxy is an oracle; explicit allow_oracle=True required")
    if pd.isna(as_of):
        raise ValueError("admin_forecast requires an explicit decision timestamp")
    as_of = pd.Timestamp(as_of)
    hist = reg.dropna()
    hist = hist[hist.index <= (known_through if known_through is not None else origin - 1)]
    hist = hist[_released_index(hist.index, as_of)]   # v2.5: calendar eligibility
    same_m = hist[hist.index.month == origin.month]
    kt = known_through if known_through is not None else origin - 1
    if origin.month == 1:
        # v1.1: announcement-shock Januaries are announcement events, not
        # seasonality -- exclude calendar-fired years from the seasonal base
        # (their 17-31% prints were poisoning the median: Jan-2024 forecast
        # was -1.04 off from a base contaminated by 2022/2023).
        ann = _announcements()
        # Classification changes the seasonal baseline too: apply exactly
        # the same clock/provenance gate to this indirect calendar channel.
        # verified_only therefore uses all prior seasonal observations.
        fired = {p for p in ann.index if _gate_fires(p, as_of, announce_mode)}
        same_m = same_m[~same_m.index.isin(fired)]
    base = float(same_m.tail(10).median()) if len(same_m) >= 3 else float(hist.tail(24).median())
    if origin.month != 1:
        return base
    if mode == "announced":
        a = _gate_value(origin, as_of, announce_mode, w_adm=w_adm)
        if not np.isnan(a):
            # additive decomposition (v1.2), with the audit's caveat on
            # gross-vs-incremental double counting recorded in the calendar
            # notes. Exclusions and additions share the provenance gate.
            return a + base
        return base
    if len(same_m) >= 3 and origin in reg.index:
        r = reg.loc[origin]
        if abs(r - same_m.mean()) > 2 * same_m.std():
            return float(r)
    return base


def _wedge_at(wedge: pd.Series, target: pd.Period, known_through: pd.Period) -> float:
    wh = wedge.dropna()
    wh = wh[wh.index <= known_through]
    wm = wh[wh.index.month == target.month]
    return float(wm.mean()) if len(wm) >= 2 else (float(wh.mean()) if len(wh) else 0.0)


def _fuel_inputs_as_of(weekly: pd.DataFrame, brent: pd.Series | None,
                       as_of: pd.Timestamp):
    """Shared replay/live cutoff under the declared pump observation+7d rule.

    This is a lag-rule approximation, not a record of historical vintages.
    Brent observation dates likewise do not certify publication timestamps.
    """
    if pd.isna(as_of):
        raise ValueError("Fuel inputs require a valid decision timestamp")
    cutoff = pd.Timestamp(as_of)
    wk = weekly.loc[weekly.index <= cutoff - pd.Timedelta(days=7)].copy()
    br = brent.loc[brent.index <= cutoff].copy() if brent is not None else None
    return wk, br


def _weighted_wedge(y, comp, alc, core, reg, wedge, wmap, as_of=None):
    """Shared live/backtest reconciliation; preserve index and operation
    order. v2.5: months not released at `as_of` are excluded (calendar)."""
    widx = [m for m in wedge.dropna().index if _regime(m) in wmap]
    wser = pd.DataFrame({m: wmap[_regime(m)] for m in widx}).T
    jm = pd.concat([y, comp[["food", "fuel"]], alc.rename("alc"),
                    core, reg], axis=1).dropna()
    jm = jm.loc[jm.index.intersection(wser.index)]
    jm = jm[_released_index(jm.index, as_of)]
    wedge_tv = (jm.iloc[:, 0]
                - wser.loc[jm.index, "food"] * jm["food"]
                - wser.loc[jm.index, "fuel"] * jm["fuel"]
                - wser.loc[jm.index, "alc"] * jm["alc"]
                - wser.loc[jm.index, "core"] * jm["core"]
                - wser.loc[jm.index, "administered"] * jm["reg"]).rename("wedge")
    return wedge_tv


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = load_all()
    # slow-transmission block for h>=6 ONLY (its literature home; measurably
    # harmful at h0 per backtest_h0_enriched): M3, house prices, construction
    # PPI -- loaders already availability-shifted, all continuing sources.
    from data.struct_inputs import load_m3_yoy, load_housing_channel
    slow = pd.concat([load_m3_yoy(), load_housing_channel()], axis=1)
    feats_slow = pd.concat([feats, slow.reindex(feats.index)], axis=1)
    # v2.4 (D3): origins are every released month from BACKTEST_START, so the
    # backtest grows with the data; the retired champion CSV is optional and
    # used only for the benchmark print.
    origins = [p for p in y.dropna().index if p >= BACKTEST_START]
    champ = None
    cpath = os.path.join(OUT, "backtest_h0_hybrid.csv")
    if os.path.exists(cpath):
        champ = pd.read_csv(cpath, index_col="period")
        champ.index = pd.PeriodIndex(champ.index, freq="M")
    print(f"CZ-STRUCT backtest: {len(origins)} origins {origins[0]}..{origins[-1]}")
    fuel_official = comp["fuel"].dropna()

    alc = load_alc_tobacco_mm()

    # -- item 4 (Codex P2/candidates): sequential PAST-ERROR correction.
    # Each origin's ridge core forecast is made with data <= t-1; its
    # realized error becomes known when core(t) is released (~10th of t+1),
    # i.e. it is trainable at any later origin s >= t+1. The forest below
    # therefore trains ONLY on errors of genuinely sequential out-of-sample
    # forecasts -- the audit's fix for the in-sample-residual forest.
    # Declared before results: min 36 past errors; full and 0.5x variants.
    pe_rows, pe_errs = [], []          # feature rows / realized errors, in origin order

    # -- item 3 + v2.3/F3: ONE fuel code path for backtest and live. The EOM
    # leg is computed internally from the weekly file (end-of-month cutoff,
    # 7-day publication rule) under the v2.3 spec -- flat-carry tail, gated
    # official blend -- replacing the champion CSV's frozen fuel_mm column
    # (old spec: Brent tail + 0.6 blend). The pre-release call may use every
    # Monday published by (release date - 1 day) under the 7-day publication
    # rule. Release dates from the survey table (schedules are known ahead).
    weekly_full = la.fetch_weekly_fuels_live()
    relmap = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv"))
    relmap["p"] = pd.PeriodIndex(relmap["target_month"], freq="M")
    relmap = relmap.set_index("p")["release_dt"].map(pd.Timestamp)
    from models.components import fuel_mm_from_weekly

    rows = []

    def components_at(t, as_of, reuse=None):
        """Every clock-dependent block at (t, as_of) -- TIMING_SPEC_v25 T5.
        Cheap blocks are always re-evaluated at the clock; the two forests
        are reused from `reuse` (the month-end evaluation) ONLY when their
        fitted inputs are provably identical (same design matrix / same
        eligible error history), which is checked, not assumed."""
        c = {"as_of": as_of,
             "elig_edge": _eligible_edge(core.dropna().index, t - 1, as_of)}
        c["core_pred"], c["core_resid"], c["core_mats"] = _ridge_predict(feats, core, t, as_of=as_of)
        c["core_st"], _, _ = _ridge_predict(feats_st, core, t, as_of=as_of)
        c["food_pred"] = food_forecast(comp["food"], food_feats, t, as_of=as_of)
        c["alc_pred"] = alc_forecast(alc, t, t - 1, as_of=as_of)
        c["wmap"] = solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc)
        c["wedge_tv"] = _weighted_wedge(y, comp, alc, core, reg, wedge, c["wmap"], as_of=as_of)
        c["wedge_t"] = _wedge_at(c["wedge_tv"], t, t - 1)
        c["wt"] = c["wmap"][_regime(t)]
        assert abs(sum(c["wt"].values()) - 1.0) < 1e-9, f"weights !=1 at {t}"
        # v2.7: documented announcement entries feed the scored block; the
        # gate-closed value is kept as the permanent comparison (STRUCT_NOANN).
        # v2.7.1: the block value is priced with THIS call's administered weight
        w_adm = c["wt"]["administered"]
        c["adm_V"] = admin_forecast(reg, t, as_of=as_of, announce_mode="documented", w_adm=w_adm)
        c["adm_N"] = admin_forecast(reg, t, as_of=as_of, announce_mode="verified_only", w_adm=w_adm)
        c["adm_R"] = admin_forecast(reg, t, as_of=as_of, announce_mode="reconstructed_scenario", w_adm=w_adm)
        wk, _ = _fuel_inputs_as_of(weekly_full, None, as_of)
        try:
            c["fuel"], _ = fuel_mm_from_weekly(wk, t, petrol_share=_petrol_share(t, as_of))
        except Exception:
            c["fuel"] = np.nan
        # legacy residual forest (reference variant): reuse iff the design is identical
        c["q_point"] = np.nan
        if c["core_mats"] is not None and c["core_resid"] is not None and len(c["core_resid"]) >= 60:
            Z, z0, tri = c["core_mats"]
            same = (reuse is not None and reuse["core_mats"] is not None
                    and tri.equals(reuse["core_mats"][2])
                    and np.array_equal(Z, reuse["core_mats"][0])
                    and np.array_equal(z0, reuse["core_mats"][1]))
            if same:
                c["q_point"] = reuse["q_point"]
            else:
                try:
                    c["q_point"] = TVWQRF(n_estimators=200).fit_predict(
                        Z, c["core_resid"].values, z0[0])["point"]
                except Exception:
                    pass
        # warm challenger (PAST_FULL): reuse iff the eligible error history is identical
        errs = _eligible_error_history(core, t, as_of, feats)
        c["pe_err_index"] = errs.index
        if reuse is not None and errs.index.equals(reuse["pe_err_index"]):
            c["pe_corr_warm"] = reuse["pe_corr_warm"]
        else:
            c["pe_corr_warm"] = restored_pe_correction(feats, core, t, as_of)
        return c

    def recombine(c, core_c, adm_c, fuel_c=None):
        ww = c["wt"]
        fuel_c = c["fuel"] if fuel_c is None else fuel_c
        return (ww["fuel"] * fuel_c + ww["administered"] * adm_c
                + ww["alc"] * c["alc_pred"]
                + ww["food"] * c["food_pred"] + ww["core"] * core_c + c["wedge_t"])

    for t in origins:
        # decision time A: month-end (documented backtest assumption since v1)
        as_of = t.to_timestamp(how="end")
        # decision time B: the day before the FIRST release (regular CPI before
        # 2025, flash from 2025), 23:59 Prague wall time, from the calendar
        fr = _first_release_dt(t)
        as_of_eve = (fr.normalize() - pd.Timedelta(days=1)
                     + pd.Timedelta(hours=23, minutes=59)) if pd.notna(fr) else pd.NaT

        A = components_at(t, as_of)
        if np.isnan(A["core_pred"]) or np.isnan(A["food_pred"]):
            continue
        core_pred, core_resid, core_mats = A["core_pred"], A["core_resid"], A["core_mats"]
        food_pred, alc_pred, adm_V, adm_R = A["food_pred"], A["alc_pred"], A["adm_V"], A["adm_R"]
        fuel_meas, wmap, wedge_tv, wedge_t, wt = A["fuel"], A["wmap"], A["wedge_tv"], A["wedge_t"], A["wt"]

        struct_v = recombine(A, core_pred, adm_V)
        struct_r = recombine(A, core_pred, adm_R)
        struct_noann = recombine(A, core_pred, A["adm_N"])   # v2.7: gate closed
        struct_st = recombine(A, A["core_st"], adm_V) if not np.isnan(A["core_st"]) else np.nan
        qrf_v = recombine(A, core_pred + A["q_point"], adm_V) if np.isfinite(A["q_point"]) else np.nan
        qrf_r = recombine(A, core_pred + A["q_point"], adm_R) if np.isfinite(A["q_point"]) else np.nan

        # cold past-error correction: forest on sequential past forecast errors
        # (registry built in origin order; identical at both decision times
        # because core(t-1) is released before month-end of t)
        x_now_raw = feats.loc[t].values.astype(float)
        pe_corr = 0.0
        if len(pe_errs) >= 36:
            Xp = np.vstack(pe_rows)
            mu = np.nanmean(Xp, axis=0)
            mu = np.where(np.isfinite(mu), mu, 0.0)
            Xp = np.where(np.isfinite(Xp), Xp, mu)
            xr = np.where(np.isfinite(x_now_raw), x_now_raw, mu)
            try:
                pe_corr = TVWQRF(n_estimators=200).fit_predict(
                    Xp, np.asarray(pe_errs), xr)["point"]
            except Exception:
                pe_corr = 0.0
        pe_v = recombine(A, core_pred + pe_corr, adm_V)
        pe_r = recombine(A, core_pred + pe_corr, adm_R)
        peh_v = recombine(A, core_pred + 0.5 * pe_corr, adm_V)
        peh_r = recombine(A, core_pred + 0.5 * pe_corr, adm_R)
        pe_corr_warm = A["pe_corr_warm"]
        pew_v = recombine(A, core_pred + pe_corr_warm, adm_V)
        pewh_v = recombine(A, core_pred + 0.5 * pe_corr_warm, adm_V)
        # v2.7.1 (Codex R8 E): gate-closed equivalents of the challengers
        pew_noann = recombine(A, core_pred + pe_corr_warm, A["adm_N"])
        pewh_noann = recombine(A, core_pred + 0.5 * pe_corr_warm, A["adm_N"])

        # legacy pre-release fuel update (v2.1): A's blocks with release-eve
        # fuel only -- retained as the self-check for the full B evaluation
        fuel_pre, struct_pre_v, pe_pre_v = np.nan, np.nan, np.nan
        rdt = relmap.get(t, pd.NaT)
        if pd.notna(rdt):
            cutoff = rdt - pd.Timedelta(days=1)
            wk, _ = _fuel_inputs_as_of(weekly_full, None, cutoff)
            try:
                fuel_pre, _ = fuel_mm_from_weekly(wk, t, petrol_share=_petrol_share(t, cutoff))
                struct_pre_v = recombine(A, core_pred, adm_V, fuel_c=fuel_pre)
                pe_pre_v = recombine(A, core_pred + pe_corr, adm_V, fuel_c=fuel_pre)
            except Exception:
                pass

        # decision time B: the FULL pipeline at release eve
        B = components_at(t, as_of_eve, reuse=A) if pd.notna(as_of_eve) else None
        if B is not None and not (np.isnan(B["core_pred"]) or np.isnan(B["food_pred"])):
            struct_eve = recombine(B, B["core_pred"], B["adm_V"])
            qrf_eve = recombine(B, B["core_pred"] + B["q_point"], B["adm_V"]) if np.isfinite(B["q_point"]) else np.nan
            pe_eve = recombine(B, B["core_pred"] + pe_corr, B["adm_V"])
            pew_eve = recombine(B, B["core_pred"] + B["pe_corr_warm"], B["adm_V"])
            pewh_eve = recombine(B, B["core_pred"] + 0.5 * B["pe_corr_warm"], B["adm_V"])
            # v2.7.1: release-eve gate-closed columns (the scenario script's
            # base; every comparison on the same clock)
            struct_noann_eve = recombine(B, B["core_pred"], B["adm_N"])
            pew_noann_eve = recombine(B, B["core_pred"] + B["pe_corr_warm"], B["adm_N"])
            pewh_noann_eve = recombine(B, B["core_pred"] + 0.5 * B["pe_corr_warm"], B["adm_N"])
            eve = {"STRUCT_EVE": struct_eve, "STRUCT_QRF_EVE": qrf_eve, "STRUCT_PE_EVE": pe_eve,
                   "STRUCT_PE_WARM_EVE": pew_eve, "STRUCT_PEH_WARM_EVE": pewh_eve,
                   "fuel_eve": B["fuel"], "core_pred_eve": B["core_pred"],
                   "food_pred_eve": B["food_pred"], "adm_pred_eve": B["adm_V"], "adm_pred_N_eve": B["adm_N"],
                   "STRUCT_NOANN_EVE": struct_noann_eve, "STRUCT_PE_WARM_NOANN_EVE": pew_noann_eve,
                   "STRUCT_PEH_WARM_NOANN_EVE": pewh_noann_eve,
                   "alc_pred_eve": B["alc_pred"], "wedge_eve": B["wedge_t"],
                   "elig_edge_eve": str(B["elig_edge"]), "as_of_eve": as_of_eve.isoformat()}
        else:
            eve = {k: np.nan for k in ["STRUCT_EVE", "STRUCT_QRF_EVE", "STRUCT_PE_EVE",
                                       "STRUCT_PE_WARM_EVE", "STRUCT_PEH_WARM_EVE", "fuel_eve",
                                       "core_pred_eve", "food_pred_eve", "adm_pred_eve",
                                       "alc_pred_eve", "wedge_eve"]}
            eve.update({"elig_edge_eve": "", "as_of_eve": ""})

        # register this origin's ridge error for FUTURE origins (release lag
        # honoured by ordering: usable only from origin t+1 onward)
        ca = core.get(t, np.nan)
        if not np.isnan(core_pred) and not np.isnan(ca):
            pe_rows.append(x_now_raw)
            pe_errs.append(float(ca - core_pred))

        struct, struct_qrf, adm_pred = struct_v, qrf_v, adm_V  # verified = primary

        # ---- h>=1: forecast month t+h with CPI-family known through t-1;
        # verified_only announcements (audit: reconstructed magnitudes never
        # enter the primary path); decision time A ----
        def horizon_call(h, core_frame=feats):
            core_h, _, _ = _ridge_predict(core_frame, core, t, h=h, as_of=as_of)
            food_h = food_forecast(comp["food"], food_feats, t, h=h, as_of=as_of)
            wh_ = wmap.get(_regime(t + h), wt)
            adm_h = admin_forecast(reg, t + h, known_through=t - 1,
                                   as_of=as_of, announce_mode="documented",
                                   w_adm=wh_["administered"])
            alc_h = alc_forecast(alc, t + h, t - 1, as_of=as_of)
            fh = fuel_official[fuel_official.index <= t - 1]
            fm = fh[fh.index.month == (t + h).month]
            fuel_h = float(fm.tail(8).median()) if len(fm) >= 3 else float(fh.tail(24).median())
            wdg = _wedge_at(wedge_tv, t + h, t - 1)
            if np.isnan(core_h) or np.isnan(food_h):
                return np.nan
            return (wh_["fuel"] * fuel_h + wh_["administered"] * adm_h
                    + wh_["alc"] * alc_h
                    + wh_["food"] * food_h + wh_["core"] * core_h + wdg)

        struct_h1 = horizon_call(1)
        struct_h3 = horizon_call(3)
        struct_h6 = horizon_call(6, feats_slow)
        struct_h12 = horizon_call(12, feats_slow)

        row = {"period": t, "actual": y.loc[t], "STRUCT": struct,
               "STRUCT_QRF": struct_qrf, "STRUCT_ST": struct_st,
               "STRUCT_R": struct_r, "STRUCT_QRF_R": qrf_r,
               "STRUCT_PE": pe_v, "STRUCT_PE_R": pe_r,
               "STRUCT_PEH": peh_v, "STRUCT_PEH_R": peh_r,
               "pe_corr": pe_corr, "fuel_pre": fuel_pre,
               "STRUCT_PE_WARM": pew_v, "STRUCT_PEH_WARM": pewh_v,
               "pe_corr_warm": pe_corr_warm,
               "STRUCT_PRE": struct_pre_v, "STRUCT_PE_PRE": pe_pre_v,
               "adm_pred_R": adm_R, "adm_pred_N": A["adm_N"], "STRUCT_NOANN": struct_noann,
               "STRUCT_PE_WARM_NOANN": pew_noann, "STRUCT_PEH_WARM_NOANN": pewh_noann,
               "alc_pred": alc_pred,
               "alc_actual": alc.get(t, np.nan),
               "core_pred": core_pred, "core_actual": core.get(t, np.nan),
               "food_pred": food_pred, "food_actual": comp["food"].get(t, np.nan),
               "adm_pred": adm_pred, "adm_actual": reg.get(t, np.nan),
               "fuel_mm": fuel_meas, "wedge": wedge_t,
               "target_h1": t + 1, "STRUCT_H1": struct_h1,
               "actual_h1": y.get(t + 1, np.nan),
               "target_h3": t + 3, "STRUCT_H3": struct_h3,
               "actual_h3": y.get(t + 3, np.nan),
               "target_h6": t + 6, "STRUCT_H6": struct_h6,
               "actual_h6": y.get(t + 6, np.nan),
               "target_h12": t + 12, "STRUCT_H12": struct_h12,
               "actual_h12": y.get(t + 12, np.nan),
               "elig_edge_eom": str(A["elig_edge"])}
        row.update(eve)
        rows.append(row)

    bt = pd.DataFrame(rows).set_index("period").sort_index()

    # ---- v1.4 uncertainty bands: REGIME-CONDITIONAL expanding empirical
    # quantiles of own past h0 errors (state = trailing yoy > 4%, the same
    # regime line as the core block). Calm months draw calm-pool quantiles,
    # shock months the shock pool; global pool until a regime pool has >=24
    # errors. Strictly past errors only.
    ext_mm = la.load_headline_cpi_mm_extended()
    state_full = _trailing_yoy(ext_mm).shift(1) > STATE_THRESHOLD
    # audit P0 #5, both fixes: (a) error = forecast - actual, so the band
    # for the ACTUAL is [f - q95(e), f - q05(e)] -- the old code added the
    # quantiles, shifting a biased model's band the wrong way; (b) a regime
    # pool is used only when it alone has >= 24 observations (the old 16-
    # switch/24-issue mismatch silently dropped Jan-Aug 2023).
    errs = (bt["STRUCT_QRF"] - bt["actual"])
    lo, hi = [], []
    pools = {False: [], True: []}
    for t in bt.index:
        st = bool(state_full.get(t, False))
        pool = pools[st] if len(pools[st]) >= 24 else pools[False] + pools[True]
        if len(pool) >= 24:
            q = np.quantile(pool, [0.05, 0.95])
            lo.append(bt.loc[t, "STRUCT_QRF"] - q[1])
            hi.append(bt.loc[t, "STRUCT_QRF"] - q[0])
        else:
            lo.append(np.nan)
            hi.append(np.nan)
        if not np.isnan(errs.loc[t]):
            pools[st].append(errs.loc[t])
    bt["band_lo"], bt["band_hi"] = lo, hi
    bt.to_csv(os.path.join(OUT, "cz_struct_backtest.csv"))
    inb = ((bt["actual"] >= bt["band_lo"]) & (bt["actual"] <= bt["band_hi"]))
    nb = bt["band_lo"].notna()
    print(f"  band 5-95%% coverage: {100*inb[nb].mean():.0f}%% (target ~90%%, n={int(nb.sum())})")

    print(f"\nn={len(bt)}  {bt.index.min()}..{bt.index.max()}")
    for blk in ["core", "food", "adm"]:
        r = bt[f"{blk}_pred"] - bt[f"{blk}_actual"]
        print(f"  {blk:5s} block RMSE={np.sqrt(np.nanmean(r**2)):.3f}  MAE={np.nanmean(np.abs(r)):.3f}")
    for col in ["STRUCT", "STRUCT_QRF", "STRUCT_ST", "STRUCT_PE", "STRUCT_PE_WARM"]:
        r = bt[col] - bt["actual"]
        print(f"  {col:14s} h0 RMSE={np.sqrt(np.nanmean(r**2)):.3f}  MAE={np.nanmean(np.abs(r)):.3f}")
    # v2.5 (TIMING_SPEC T5): decision time B, and the self-check that the full
    # release-eve evaluation equals the legacy fuel-only update (only the fuel
    # Mondays differ between the two clocks in the backtest)
    for col in ["STRUCT_EVE", "STRUCT_PE_WARM_EVE", "STRUCT_PEH_WARM_EVE"]:
        r = bt[col] - bt["actual"]
        print(f"  {col:18s} release-eve RMSE={np.sqrt(np.nanmean(r**2)):.3f}  "
              f"MAE={np.nanmean(np.abs(r)):.3f}  (n={int(r.notna().sum())})")
    for a, b in [("STRUCT_PRE", "STRUCT_EVE"), ("STRUCT_PE_PRE", "STRUCT_PE_EVE")]:
        d = (bt[a] - bt[b]).abs()
        print(f"  self-check max|{a} - {b}| = {np.nanmax(d.values):.2e}")
    if champ is not None:
        r = champ["h0_hybrid"].reindex(bt.index) - bt["actual"]
        print(f"  champion   h0 RMSE={np.sqrt(np.nanmean(r**2)):.3f}  (same {len(bt)} months)")

    for h, col in [(1, "STRUCT_H1"), (3, "STRUCT_H3"), (6, "STRUCT_H6"), (12, "STRUCT_H12")]:
        rh = bt[col] - bt[f"actual_h{h}"]
        print(f"  {col}  RMSE={np.sqrt(np.nanmean(rh**2)):.3f}  MAE={np.nanmean(np.abs(rh)):.3f}  (n={rh.notna().sum()})")
        hp = os.path.join(OUT, f"backtest_forecasts_h{h}.csv")
        if os.path.exists(hp):
            hh = pd.read_csv(hp, index_col="period")
            hh.index = pd.PeriodIndex(hh.index, freq="M")
            sh = bt.set_index(pd.PeriodIndex(bt[f"target_h{h}"].astype(str), freq="M"))[col]
            common = sh.dropna().index.intersection(hh.index)
            rc = hh.loc[common, "TVW_QRF"] - hh.loc[common, "actual"]
            rs = sh.loc[common] - hh.loc[common, "actual"]
            print(f"  h{h} head-to-head on {len(common)} common target months: "
                  f"champion {np.sqrt(np.nanmean(rc**2)):.3f} vs {col} {np.sqrt(np.nanmean(rs**2)):.3f}")
    return bt


SPEC_TAG = "v2.7.3-nosurvey-column-2026-09-08"
# survey-based core columns (SURVEY_ABLATION_SPEC): removed in the fourth logged nowcast column
SURVEY_COLS = ["exp12", "exp36", "exp12_x_state", "household_exp", "esi"]   # v2.7: documented announcement entries in the scored admin block (ANNOUNCEMENT_ADOPTION_v27)  # TIMING_SPEC_v25.md: sourced release
                                      # calendar, clock-filtered food history,
                                      # content-keyed X-13 cache, eligibility in
                                      # every component, two decision times,
                                      # month-to-date FX, aware clock, refresh
                                      # report. PROVISIONAL pending Codex.
BACKTEST_START = pd.Period("2018-02", "M")  # first origin of the historical frame
_TZ = "Europe/Prague"


def _now_prague():
    """Zone-aware 'now' in Prague plus its naive wall time. Every rule and
    calendar comparison uses the wall time (the calendar carries Prague wall
    times); the log records the aware stamp, which the evaluation
    classifier requires (a naive clock is UNVERIFIED_CLOCK)."""
    aware = pd.Timestamp.now(tz=_TZ)
    return aware, aware.tz_localize(None)


def _flash_release_dt(target: pd.Period):
    """Compatibility alias: first-release timestamp from the calendar."""
    return _first_release_dt(target)


_DETERMINISTIC = lambda c: c.startswith("mon_") or c.endswith("_x_state") or c == "state"  # noqa: E731
_CPI_LAG1_COLS = {"core_l1", "services_l1", "food_l1", "state"}
_CHECKS_PATH = os.path.join(HERE, "data", "announcement_source_checks.csv")


def _announcement_check_status(as_of: pd.Timestamp, path: str | None = None) -> dict:
    """Age (days) of the last announcement-source check before `as_of` and
    the CHANGED / UNVERIFIED counts of that last batch (ANNOUNCEMENT_PROTOCOL
    re-verification routine). NaN age when no check exists: the row then
    shows that the routine was never run, rather than hiding it."""
    p = path or _CHECKS_PATH
    out = {"announcement_check_age_days": np.nan, "announcement_changed": np.nan, "announcement_unverified": np.nan}
    if not os.path.exists(p):
        return out
    c = pd.read_csv(p, dtype=str).fillna("")
    if c.empty:
        return out
    ts = pd.to_datetime(c["check_ts"], utc=True, errors="coerce").dt.tz_convert(None)
    wall = pd.Timestamp(as_of)
    wall = wall.tz_localize(None) if wall.tzinfo is not None else wall
    c = c[ts.notna() & (ts <= wall)]
    ts = ts[ts.notna() & (ts <= wall)]
    if c.empty:
        return out
    last = ts.max()
    batch = c[ts == last]
    out["announcement_check_age_days"] = round(float((wall - last).total_seconds() / 86400.0), 2)
    out["announcement_changed"] = int((batch["verdict"] == "CHANGED").sum())
    out["announcement_unverified"] = int(batch["verdict"].isin(["UNVERIFIED", "THIN"]).sum())
    return out


def _classify_missing(col: str, t: pd.Period, as_of: pd.Timestamp) -> str:
    """For a NaN feature in the origin row: STALE when its publication rule
    (or the release calendar for CPI-family lags) says the value should be
    public at `as_of`, i.e. the source was not refreshed; NOT_DUE when it is
    legitimately unpublished. Closes the D2 ambiguity of a bare count."""
    if col.endswith("_x_state"):
        # an interaction is missing whenever either factor is; it is only
        # STALE if both factors were due
        base_col = col[:-len("_x_state")]
        if (_classify_missing(base_col, t, as_of) == "NOT_DUE"
                or _classify_missing("state", t, as_of) == "NOT_DUE"):
            return "NOT_DUE"
        return "STALE"
    if col in _CPI_LAG1_COLS:
        return "STALE" if _cpi_family_released_by(t - 1, as_of) else "NOT_DUE"
    if col not in _COL_AVAILABILITY_RULE:
        return "STALE"   # no rule = market/administrative data, always due
    ref, day = _availability_rule(col, t)
    base = t.to_timestamp() if ref == "t" else (t + 1).to_timestamp()
    return "STALE" if as_of >= base + pd.Timedelta(days=day - 1) else "NOT_DUE"


def _eurczk_mtd_mm(t: pd.Period, as_of: pd.Timestamp, fx_monthly_eur: pd.Series):
    """Month-to-date EUR/CZK m/m for month t: mean of the CNB daily fixings
    dated BEFORE the call day within t, over the previous month's average
    (the monthly table when it has t-1, else the mean of t-1's fixings).
    Returns (value, n_fixings); value is NaN when no fixing of t is
    available. v2.6 (Codex R6 blocker 3, user decision): the fixing is
    published at 14:30, so the call day's own fixing is never used -- the
    day-before rule needs no intraday timestamp."""
    daily = la.fetch_cnb_daily_eur_fixings(t.year)
    if t.month <= 2:
        daily = pd.concat([la.fetch_cnb_daily_eur_fixings(t.year - 1), daily]).sort_index()
    cur = daily[(daily.index.to_period("M") == t) & (daily.index < pd.Timestamp(as_of).normalize())]
    if cur.empty:
        return np.nan, 0
    prev = float(fx_monthly_eur.get(t - 1, np.nan))
    if not np.isfinite(prev):
        pm = daily[daily.index.to_period("M") == t - 1]
        prev = float(pm.mean()) if len(pm) else np.nan
    if not np.isfinite(prev):
        return np.nan, int(len(cur))
    return 100.0 * (float(cur.mean()) / prev - 1.0), int(len(cur))



def _live_trio_bands(t: pd.Period, as_of: pd.Timestamp, points: dict) -> dict:
    """BANDS_SPEC_v1 RESULTS: V1 bands (January / non-January pools of the
    model's own release-eve first-release errors), status 'uncalibrated'
    (no variant met the coverage rule), for the frozen trio at the call's
    clock. The pool = backtest origins u < t whose FIRST release was public
    at `as_of` (release calendar), errors against the first-release actuals
    file; graded prospective rows extend it once the scoreboard certifies
    them. Never touches a point forecast."""
    from models.bands import build_pool, band
    cols = {"base_ridge": "STRUCT_EVE", "past_full": "STRUCT_PE_WARM_EVE", "past_half": "STRUCT_PEH_WARM_EVE"}
    out = {"band_variant": "V1", "band_status": "uncalibrated", "band_n_pool": 0}
    for k in cols:
        for lv in (80, 90):
            out[f"h0_{k}_lo{lv}"] = np.nan
            out[f"h0_{k}_hi{lv}"] = np.nan
    try:
        bt = pd.read_csv(os.path.join(OUT, "cz_struct_backtest.csv"), index_col="period")
        bt.index = pd.PeriodIndex(bt.index, freq="M")
        ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv"))
        ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
        ext = ext[ext["era"] != "flash_survey_suspect"].set_index("p")
        act = ext["actual"].astype(float)
        clock = pd.Timestamp(as_of)
        ok = []
        for u in bt.index:
            if u >= t:
                continue
            fr = _first_release_dt(u)
            if pd.notna(fr) and pd.Timestamp(fr) <= clock:
                ok.append(u)
        for k, c in cols.items():
            e = (bt.loc[ok, c].astype(float) - act.reindex(ok)).dropna()
            hist = pd.DataFrame({"e": e.values, "month": [u.month for u in e.index],
                                 "state": np.nan, "age_months": [(t - u).n for u in e.index]}, index=e.index)
            pool, _note = build_pool(hist, "V1", t.month, None)
            if pool is None:
                out["band_status"] = "unavailable: insufficient history"
                continue
            out["band_n_pool"] = len(pool)
            for lv in (80, 90):
                lo, hi = band(float(points[k]), pool, lv)
                out[f"h0_{k}_lo{lv}"] = round(lo, 3)
                out[f"h0_{k}_hi{lv}"] = round(hi, 3)
    except Exception as ex:  # noqa: BLE001
        out["band_status"] = f"unavailable: {str(ex)[:60]}"
    return out


def struct_live(target: pd.Period | None = None, log: bool = True,
                release_stage: str | None = None,
                release_dt: str | None = None) -> dict:
    """Live CZ-STRUCT call for `target` (default: CPI edge + 1, the first
    month without a detailed release), built from exactly the backtest's
    per-origin machinery plus measured fuel from the live weekly file.
    Appends one row to output/struct_shadow_log.csv.

    Identity (v2.4/v2.5): `release_stage` says WHICH release the call
    precedes -- pre_flash (before the target's first release) or pre_final
    (first release out, detailed release pending) -- derived from the
    sourced release calendar unless given explicitly; `scheduled_release`
    is the timestamp the stage refers to. post_release / unknown rows are
    not evidence of forecasting the first release. The row carries the
    imputed features split into STALE (source not refreshed) and NOT_DUE
    (legitimately unpublished), the FX source (monthly table or month-to-
    date fixings), the eligible CPI-family edge, and a zone-aware clock.
    """
    from models.components import fuel_mm_from_weekly
    y, comp, core, reg, feats, _feats_st, food_feats, wedge = load_all()
    cpi_edge = y.dropna().index.max()
    t = target or (cpi_edge + 1)
    edge_gap = (t - cpi_edge).n - 1  # 0 = CPI released through t-1
    run_aware, as_of = _now_prague()  # ONE clock per call: rules use the wall time

    # ---- release-event identity from the calendar ----
    first_dt, detail_dt = _first_release_dt(t), _detail_release_dt(t)
    if release_dt is not None:
        sched = pd.Timestamp(release_dt).normalize() + pd.Timedelta(hours=_RELEASE_HOUR)
        if release_stage:
            stage, stage_src = release_stage, "explicit"
        else:
            stage = "pre_flash" if (pd.isna(first_dt) or sched <= first_dt) else "pre_final"
            stage_src = "explicit_release_dt+inferred_stage"
    elif release_stage == "pre_final" and pd.notna(detail_dt):
        sched, stage, stage_src = detail_dt, "pre_final", "explicit_stage+calendar_detail_date"
    elif pd.notna(first_dt):
        if as_of < first_dt:
            sched, stage = first_dt, "pre_flash"
        elif pd.notna(detail_dt) and as_of < detail_dt:
            sched, stage = detail_dt, "pre_final"
        else:
            sched, stage = (detail_dt if pd.notna(detail_dt) else first_dt), "post_release"
        stage_src = "explicit_stage+calendar" if release_stage else "inferred_from_calendar"
        if release_stage:
            stage = release_stage
    else:
        sched = pd.NaT
        stage, stage_src = (release_stage or "unknown"), ("explicit_stage" if release_stage else "no_schedule_known")
    if pd.notna(sched) and as_of >= sched and stage in ("pre_flash", "pre_final"):
        stage, stage_src = "post_release", stage_src + " (as_of after scheduled release)"
    hours_to_release = (sched - as_of).total_seconds() / 3600.0 if pd.notna(sched) else np.nan
    print(f"target {t} (CPI released through {cpi_edge}, h0_edge_gap {edge_gap}); "
          f"clock {run_aware.isoformat(timespec='seconds')}; release stage {stage} "
          f"[{stage_src}]; first release {first_dt}, detailed {detail_dt}; scheduled {sched}"
          + (f"; {hours_to_release:+.1f}h to release" if np.isfinite(hours_to_release) else ""))
    if edge_gap != 0:
        print(f"!! h0_edge_gap={edge_gap}: CPI is not released through {t - 1}; "
              f"the log row carries the gap so scoring can exclude it")
    if stage in ("post_flash", "post_release", "unknown"):
        print(f"!! release stage '{stage}': this row is NOT evidence of forecasting the first release")

    # ---- availability masks on BOTH frames ----
    feats = _mask_row_by_availability(feats, t, as_of)
    food_feats = _mask_row_by_availability(food_feats, t, as_of)
    # month-to-date FX for an incomplete or not-yet-tabulated month (T6)
    fx_source, n_fix = "monthly_table", 0
    if t in feats.index and not np.isfinite(feats.loc[t, "eurczk_mm"]):
        try:
            v, n_fix = _eurczk_mtd_mm(t, as_of, la.load_fx_monthly_levels()["EUR"])
        except Exception as e:
            v, n_fix = np.nan, 0
            print(f"!! month-to-date FX unavailable ({e})")
        if np.isfinite(v):
            feats.loc[t, "eurczk_mm"] = v
            if np.isfinite(feats.loc[t, "state"]):
                feats.loc[t, "eurczk_mm_x_state"] = v * feats.loc[t, "state"]
            fx_source = f"mtd_daily({n_fix} fixings)"
    # ---- imputation report: STALE vs NOT_DUE ----
    imputed, stale, not_due = [], [], []
    for name, frame in (("core", feats), ("food", food_feats)):
        for c in frame.columns:
            if c.startswith("mon_"):
                continue
            if not np.isfinite(frame.loc[t, c]):
                lv = frame[c].dropna().index.max() if frame[c].notna().any() else None
                tag = f"{name}:{c}(last={lv})"
                imputed.append(tag)
                (stale if _classify_missing(c, t, as_of) == "STALE" else not_due).append(tag)
    if stale:
        print(f"!! {len(stale)} STALE input(s) -- published per rule/calendar but absent, "
              f"refresh before logging: " + "; ".join(stale))
    if not_due:
        print(f"   {len(not_due)} not-yet-due input(s), imputed by design: " + "; ".join(not_due))
    # freshness tripwire (live-continuity rule): any input lagging the CPI
    # edge by >6 months is presumed structurally dead, not late.
    for frame in (feats, food_feats):
        for c in frame.columns:
            if _DETERMINISTIC(c):
                continue
            lv = frame[c].dropna().index.max() if frame[c].notna().any() else None
            if lv is None or (cpi_edge - lv).n > 6:
                print(f"!! FRESHNESS TRIPWIRE: {c} last={lv} -- source likely dead, replace it")

    elig_edge = _eligible_edge(core.dropna().index, t - 1, as_of)
    core_pred, core_resid, core_mats = _ridge_predict(feats, core, t, as_of=as_of)
    core_q = core_pred
    if core_mats is not None and core_resid is not None and len(core_resid) >= 60:
        Z, z0, _ = core_mats
        try:
            core_q = core_pred + TVWQRF(n_estimators=200).fit_predict(
                Z, core_resid.values, z0[0])["point"]
        except Exception:
            pass
    # the frozen challenger, live (PAST_ERROR_QRF_SPEC.md), clock-enforced
    pe_corr, pe_mats = restored_pe_correction(feats, core, t, as_of,
                                              return_details=True)
    food_pred = food_forecast(comp["food"], food_feats, t, as_of=as_of)
    food_diag = dict(FOOD_DIAG)   # captured before the h1 call overwrites it
    alc = load_alc_tobacco_mm()
    alc_pred = alc_forecast(alc, t, t - 1, as_of=as_of)
    wmap = solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc)
    wt = wmap[_regime(t)]
    adm_pred = admin_forecast(reg, t, as_of=as_of,
                              announce_mode="documented",
                              w_adm=wt["administered"])
    weekly = la.fetch_weekly_fuels_live()
    weekly, _ = _fuel_inputs_as_of(weekly, None, as_of)
    fuel_mm, fdiag = fuel_mm_from_weekly(weekly, t,
                                         petrol_share=_petrol_share(t, as_of))

    wedge_tv = _weighted_wedge(y, comp, alc, core, reg, wedge, wmap, as_of=as_of)
    wedge_t = _wedge_at(wedge_tv, t, t - 1)

    def _recombine_live(core_c):
        return (wt["fuel"] * fuel_mm + wt["administered"] * adm_pred
                + wt["alc"] * alc_pred
                + wt["food"] * food_pred + wt["core"] * core_c + wedge_t)

    h0_ridge = _recombine_live(core_pred)          # BASE_RIDGE (baseline)
    # PATH_SPEC_v3 section 1: the reference without the survey columns, logged beside the frozen trio
    core_pred_ns, _, _ = _ridge_predict(feats.drop(columns=[c for c in SURVEY_COLS if c in feats.columns]), core, t, as_of=as_of)
    h0_ridge_ns = _recombine_live(core_pred_ns) if np.isfinite(core_pred_ns) else np.nan
    h0_full = _recombine_live(core_pred + pe_corr)  # PAST_FULL (challenger)
    h0_half = _recombine_live(core_pred + 0.5 * pe_corr)
    h0 = _recombine_live(core_q)                    # legacy residual-QRF, continuity
    # v2.7.2: flagged V1 bands for the trio (BANDS_SPEC_v1 RESULTS); points untouched
    bands_row = _live_trio_bands(t, as_of, {"base_ridge": h0_ridge, "past_full": h0_full, "past_half": h0_half})

    # freeze the exact fitted inputs for reproducibility (review sec. 8). A
    # failed archive is recorded in the row (archive_ok=False) -- such a row
    # is NOT eligible as prospective evidence (Codex R4). Dry runs archive
    # nothing.
    archive_ok = True if log else None
    try:
        if not log:
            raise StopIteration
        mdir = os.path.join(OUT, "matrices")
        os.makedirs(mdir, exist_ok=True)
        stamp = f"{t}_{as_of:%Y%m%dT%H%M%S}"
        if core_mats is None:
            raise RuntimeError("no ridge matrices to freeze")
        Zc, z0c, tri = core_mats
        np.savez_compressed(
            os.path.join(mdir, f"{stamp}.npz"),
            core_Z=Zc, core_x=z0c, core_resid=core_resid.values,
            ridge_y=core.loc[tri].values,
            ridge_train_idx=np.array([str(i) for i in tri]),
            feats_row=feats.loc[t].values.astype(float),
            feats_cols=np.array([str(c) for c in feats.columns]),
            food_row=food_feats.loc[t].values.astype(float),
            food_cols=np.array([str(c) for c in food_feats.columns]),
            weights=np.array([wt[k] for k in ("food", "fuel", "alc", "administered", "core")]),
            weight_names=np.array(["food", "fuel", "alc", "administered", "core"]),
            spec=np.array([SPEC_TAG]), as_of=np.array([run_aware.isoformat()]),
            release_stage=np.array([stage]),
            **{k: np.asarray(v) for k, v in (pe_mats or {}).items()})
        weekly.to_csv(os.path.join(mdir, f"{stamp}_fuel_weekly.csv"))
    except StopIteration:
        pass
    except Exception as e:
        archive_ok = False
        print(f"!! ARCHIVE FAILED ({e}): row is logged with archive_ok=False and "
              f"is NOT eligible as prospective evidence")

    # h=1 companion call (next month), CPI-family known through t-1
    core_h1, _, _ = _ridge_predict(feats, core, t, h=1, as_of=as_of)
    food_h1 = food_forecast(comp["food"], food_feats, t, h=1, as_of=as_of)
    w1 = wmap.get(_regime(t + 1), wt)
    adm_h1 = admin_forecast(reg, t + 1, known_through=t - 1, as_of=as_of,
                            announce_mode="documented",
                            w_adm=w1["administered"])
    alc_h1 = alc_forecast(alc, t + 1, t - 1, as_of=as_of)
    fo = comp["fuel"].dropna()
    fo = fo[fo.index <= t - 1]
    fo = fo[_released_index(fo.index, as_of)]
    fm1 = fo[fo.index.month == (t + 1).month]
    fuel_h1 = float(fm1.tail(8).median()) if len(fm1) >= 3 else float(fo.tail(24).median())
    h1 = (np.nan if np.isnan(core_h1) or np.isnan(food_h1) else
          (w1["fuel"] * fuel_h1 + w1["administered"] * adm_h1
           + w1["alc"] * alc_h1
           + w1["food"] * food_h1 + w1["core"] * core_h1 + _wedge_at(wedge_tv, t + 1, t - 1)))

    obs_cols = [c for c in feats.columns if not _DETERMINISTIC(c)]
    row = {"run_ts": run_aware.isoformat(timespec="seconds"),   # zone-aware (Europe/Prague)
           "as_of_wall": as_of.isoformat(timespec="seconds"),   # the clock the rules used
           "spec": SPEC_TAG, "target": str(t), "h0_edge_gap": edge_gap,
           "release_stage": stage, "release_stage_source": stage_src,
           "scheduled_release": sched.isoformat() if pd.notna(sched) else "",
           "first_release_dt": first_dt.isoformat() if pd.notna(first_dt) else "",
           "detail_release_dt": detail_dt.isoformat() if pd.notna(detail_dt) else "",
           "hours_to_release": round(hours_to_release, 1) if np.isfinite(hours_to_release) else np.nan,
           "h0_base_ridge": round(h0_ridge, 3),
           "h0_past_full": round(h0_full, 3),
           "h0_past_half": round(h0_half, 3),
           "h0_base_ridge_ns": round(h0_ridge_ns, 3) if np.isfinite(h0_ridge_ns) else np.nan,
           "core_ridge_ns": round(core_pred_ns, 3) if np.isfinite(core_pred_ns) else np.nan,
           "pe_corr": round(pe_corr, 4),
           "h0_struct_qrf": round(h0, 3),
           **bands_row,
           "h1_target": str(t + 1), "h1_struct": round(h1, 3) if not np.isnan(h1) else np.nan,
           "core": round(core_q, 3), "core_ridge": round(core_pred, 3),
           "food": round(food_pred, 3),
           "adm": round(adm_pred, 3), "fuel": round(fuel_mm, 3),
           "wedge": round(wedge_t, 3),
           "fuel_weeks_observed": fdiag.get("weeks_observed"),
           "fx_source": fx_source,
           "elig_edge": str(elig_edge),
           "n_imputed": len(imputed), "imputed_cols": "; ".join(imputed),
           "food_method": food_diag["method"], "food_hist_end": food_diag["history_end"],
           "food_n_obs": food_diag["n_obs"], "food_x13_error": food_diag["x13_error"],
           **_announcement_check_status(as_of),
           "n_stale": len(stale), "stale_cols": "; ".join(stale),
           "not_due_cols": "; ".join(not_due),
           "archive_ok": archive_ok,
           "core_edge": str(core.dropna().index.max()),
           "panel_any_edge": str(feats[obs_cols].dropna(how="all").index.max()),
           "panel_all_edge": str(feats[obs_cols].dropna(how="any").index.max())}
    print(f"LIVE CZ-STRUCT {t} [{stage}]  BASE_RIDGE={h0_ridge:+.2f}%  PAST_FULL={h0_full:+.2f}%  "
          f"PAST_HALF={h0_half:+.2f}%  (legacy qrf {h0:+.2f}%; no-survey reference {h0_ridge_ns:+.2f}%)")
    print(f"  bands ({bands_row['band_variant']}, {bands_row['band_status']}, pool {bands_row['band_n_pool']}): "
          f"BASE_RIDGE 80% [{bands_row['h0_base_ridge_lo80']:+.2f}, {bands_row['h0_base_ridge_hi80']:+.2f}] "
          f"90% [{bands_row['h0_base_ridge_lo90']:+.2f}, {bands_row['h0_base_ridge_hi90']:+.2f}]; "
          f"PAST_HALF 80% [{bands_row['h0_past_half_lo80']:+.2f}, {bands_row['h0_past_half_hi80']:+.2f}]")
    print(f"  blocks: core={core_pred:+.2f} (pe_corr {pe_corr:+.3f}) food={food_pred:+.2f} "
          f"alc={alc_pred:+.2f} adm={adm_pred:+.2f} fuel={fuel_mm:+.2f} wedge={wedge_t:+.2f} "
          f"(fuel weeks obs: {fdiag.get('weeks_observed')}; fx {fx_source}; eligible CPI edge "
          f"{elig_edge}; imputed {len(imputed)} = stale {len(stale)} + not due {len(not_due)}; "
          f"archive_ok {archive_ok})")
    if log:
        path = os.path.join(OUT, "struct_shadow_log.csv")
        hist = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
        hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
        hist.to_csv(path, index=False)
        print(f"logged -> {path}")
    else:
        print("dry run: NOT logged")
    return row


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="log a live call for the first unreleased month (CPI edge + 1)")
    ap.add_argument("--target", type=str, default=None,
                    help="YYYY-MM to call instead of the default target")
    ap.add_argument("--release-stage", choices=["pre_flash", "pre_final"], default=None,
                    help="which release this call precedes (defaults to the calendar's inference)")
    ap.add_argument("--release-dt", default=None,
                    help="YYYY-MM-DD of the scheduled release the call precedes (09:00 Prague assumed); "
                         "defaults to the release calendar")
    ap.add_argument("--no-log", action="store_true",
                    help="dry run: compute, print, archive nothing to the shadow log")
    args = ap.parse_args()
    if args.live or args.target:
        struct_live(pd.Period(args.target, "M") if args.target else None,
                    log=not args.no_log, release_stage=args.release_stage,
                    release_dt=args.release_dt)
    else:
        main()
