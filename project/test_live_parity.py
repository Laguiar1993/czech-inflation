"""v2.4 live/backtest parity tests (offline, synthetic inputs).

Covers the Fable D1 / Codex R4 P0 defect class: lagged features must be
built on the full calendar index (so the live edge+1 / edge+2 rows receive
released lags and calendar gaps stay NaN), the state dummy must stay NaN
when the trailing y/y is unknown, the availability mask must cover the food
frame and the state interactions, and label / past-error eligibility must
depend on the decision clock, not only on origin-1.
Run: python -m pytest test_live_parity.py -q
"""
import numpy as np
import pandas as pd
import pytest

import cz_struct as S

EDGE = pd.Period("2026-07", "M")


def _series(start, end, fn=None):
    idx = pd.period_range(start, end, freq="M")
    vals = np.arange(len(idx), dtype=float) if fn is None else fn(idx)
    return pd.Series(vals, index=idx)


def _inputs(core=None, trailing=None):
    core = _series("2020-01", str(EDGE)) if core is None else core
    trailing = (_series("2020-01", str(EDGE), lambda i: np.full(len(i), 5.0))
                if trailing is None else trailing)
    in_month = _series("2020-01", str(EDGE + 1))            # FX/ESI/expectations exist for edge+1
    return dict(core=core, trailing_yoy=trailing, exp12=in_month, exp36=in_month,
                household_exp=in_month, esi=in_month, eurczk_mm=in_month,
                services=_series("2020-01", str(EDGE)),
                imports=_series("2020-01", str(EDGE - 1)),  # import(edge) not yet published
                food=_series("2020-01", str(EDGE)),
                agri_shifted=_series("2020-02", str(EDGE + 1)),  # label u holds agri(u-1)
                food_ppi=_series("2020-01", str(EDGE)))


def _frames(**over):
    inp = _inputs(**over)
    full_idx = pd.period_range("2020-01", str(EDGE + 2), freq="M")
    return S.assemble_feature_frames(full_idx, **inp), inp


def test_edge_plus_one_receives_released_lags():
    (feats, feats_st, food), inp = _frames()
    t = EDGE + 1
    assert feats.loc[t, "core_l1"] == inp["core"][EDGE]
    assert feats.loc[t, "core_l2"] == inp["core"][EDGE - 1]
    assert feats.loc[t, "core_l12"] == inp["core"][EDGE - 11]
    assert feats.loc[t, "services_l1"] == inp["services"][EDGE]
    assert feats.loc[t, "import_l2"] == inp["imports"][EDGE - 1]
    assert feats.loc[t, "state"] == 1.0
    assert np.isfinite(feats.loc[t, "import_l2_x_state"])
    assert 0 < feats_st.loc[t, "state"] <= 1
    assert food.loc[t, "food_l1"] == inp["food"][EDGE]
    assert food.loc[t, "food_l12"] == inp["food"][EDGE - 11]
    assert food.loc[t, "agri_l0"] == inp["agri_shifted"][EDGE + 1]
    assert food.loc[t, "agri_l1"] == inp["agri_shifted"][EDGE]
    assert food.loc[t, "food_ppi_l1"] == inp["food_ppi"][EDGE]


def test_edge_plus_two_keeps_unreleased_one_month_lag_missing():
    (feats, _, food), inp = _frames()
    t = EDGE + 2
    assert np.isnan(feats.loc[t, "core_l1"]), "core(edge+1) is not released"
    assert feats.loc[t, "core_l2"] == inp["core"][EDGE]
    assert np.isnan(feats.loc[t, "import_l2"]), "import(edge) is not published"
    assert np.isnan(food.loc[t, "food_l1"])
    assert food.loc[t, "food_l12"] == inp["food"][EDGE - 10]


def test_calendar_gap_stays_missing_not_previous_row():
    core = _series("2020-01", str(EDGE)).drop(pd.Period("2024-06", "M"))
    (feats, _, _), _ = _frames(core=core)
    assert np.isnan(feats.loc[pd.Period("2024-07", "M"), "core_l1"]), \
        "a positional shift would have handed May-2024 to July as 'core_l1'"
    assert feats.loc[pd.Period("2024-08", "M"), "core_l2"] is not None
    assert np.isnan(feats.loc[pd.Period("2024-08", "M"), "core_l2"])


def test_unknown_trailing_yoy_gives_nan_state_not_zero():
    trailing = _series("2020-01", str(EDGE), lambda i: np.full(len(i), 5.0))
    trailing[pd.Period("2023-03", "M")] = np.nan
    (feats, feats_st, _), _ = _frames(trailing=trailing)
    assert np.isnan(feats.loc[pd.Period("2023-04", "M"), "state"])
    assert np.isnan(feats.loc[pd.Period("2023-04", "M"), "exp12_x_state"])
    assert np.isnan(feats_st.loc[pd.Period("2023-04", "M"), "state"])
    assert feats.loc[pd.Period("2023-05", "M"), "state"] == 1.0


def test_cpi_family_release_clock_boundary():
    u = pd.Period("2026-07", "M")   # detailed release 2026-08-11 09:00 (release calendar, v2.5)
    assert not S._cpi_family_released_by(u, pd.Timestamp("2026-08-11 08:59"))
    assert S._cpi_family_released_by(u, pd.Timestamp("2026-08-11 09:00"))
    assert S._cpi_family_released_by(u, None), "no clock = no restriction (backtest passes EOM explicitly)"
    assert S._cpi_family_released_by(u, pd.NaT)


def test_mask_covers_food_frame_and_state_interactions():
    (feats, _, food), _ = _frames()
    t = EDGE + 1
    early = S._mask_row_by_availability(food, t, t.to_timestamp() + pd.Timedelta(days=19))  # day 20
    assert np.isnan(early.loc[t, "agri_l0"]), "agri PPI(t-1) publishes ~day 25"
    assert np.isfinite(early.loc[t, "food_l1"]), "food CPI(t-1) is out by day 11"
    late = S._mask_row_by_availability(food, t, t.to_timestamp() + pd.Timedelta(days=26))
    assert np.isfinite(late.loc[t, "agri_l0"])
    day5 = S._mask_row_by_availability(feats, t, t.to_timestamp() + pd.Timedelta(days=4))
    assert np.isnan(day5.loc[t, "state"])
    assert all(np.isnan(day5.loc[t, c]) for c in feats.columns if c.endswith("_x_state"))
    # a row outside the frame is a no-op, not a KeyError
    S._mask_row_by_availability(feats, EDGE + 9, pd.Timestamp("2027-06-01"))


def test_past_error_eligibility_reads_the_clock():
    core = pd.Series({pd.Period("2026-07", "M"): 1.0})
    origin = pd.Period("2026-08", "M")
    e_aug1 = S._eligible_error_history(core, origin, pd.Timestamp("2026-08-01"))
    e_aug31 = S._eligible_error_history(core, origin, pd.Timestamp("2026-08-31"))
    assert e_aug1.index.max() <= pd.Period("2026-06", "M"), "July core error admitted before its release"
    assert e_aug31.index.max() == pd.Period("2026-07", "M")
    assert len(e_aug31) == len(e_aug1) + 1


def test_ridge_training_labels_respect_the_clock():
    (feats, _, _), inp = _frames()
    origin = EDGE + 1
    y = inp["core"].reindex(feats.index)
    _, _, mats_early = S._ridge_predict(feats, y, origin, as_of=pd.Timestamp("2026-08-01"))
    _, _, mats_late = S._ridge_predict(feats, y, origin, as_of=pd.Timestamp("2026-08-31"))
    assert mats_early[2].max() == EDGE - 1
    assert mats_late[2].max() == EDGE
