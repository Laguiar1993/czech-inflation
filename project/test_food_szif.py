"""Offline tests for the weekly SZIF signal (FOOD_SZIF_SPEC.md section 3):
publication-date eligibility at the clock, the Thursday month rule, the
both-months requirement per product, and the commodity averaging."""
import numpy as np
import pandas as pd

from data import szif_weekly as sw


def _week(commodity, product, end, price, published):
    end = pd.Timestamp(end)
    return dict(commodity=commodity, product=product, begin=end - pd.Timedelta(days=6), end=end,
                month=(end - pd.Timedelta(days=3)).to_period("M"), price_czk=price,
                published=pd.Timestamp(published), pub_recorded=True)


def _panel():
    rows = []
    # pigs: March 2024 weeks (Sundays 3, 10, 17, 24, 31 Mar) all at 100; April weeks
    # rising 100, 102, 104, 106 ending Apr 7, 14, 21, 28; published the Wednesday after
    for d in ["2024-03-03", "2024-03-10", "2024-03-17", "2024-03-24", "2024-03-31"]:
        rows.append(_week("pigs", "E", d, 100.0, pd.Timestamp(d) + pd.Timedelta(days=3)))
    for d, p in zip(["2024-04-07", "2024-04-14", "2024-04-21", "2024-04-28"], [100.0, 102.0, 104.0, 106.0]):
        rows.append(_week("pigs", "E", d, p, pd.Timestamp(d) + pd.Timedelta(days=3)))
    return pd.DataFrame(rows)


def test_last_week_excluded_at_month_end_and_included_at_release_eve():
    w = _panel()
    apr = pd.Period("2024-04", "M")
    clock_a = pd.Series({apr: pd.Timestamp("2024-04-30 23:59")})
    clock_b = pd.Series({apr: pd.Timestamp("2024-05-09 23:59")})
    sa, da = sw.month_signal(w, clock_a)
    sb, db = sw.month_signal(w, clock_b)
    # week ending 28 Apr is published 1 May -> not in A, in B
    assert da.loc[apr, "n_weeks_used"] == 3 and da.loc[apr, "n_weeks_month"] == 4
    assert db.loc[apr, "n_weeks_used"] == 4
    exp_a = 100 * (np.mean(np.log([100, 102, 104])) - np.log(100))
    exp_b = 100 * (np.mean(np.log([100, 102, 104, 106])) - np.log(100))
    assert abs(sa.loc[apr] - exp_a) < 1e-9 and abs(sb.loc[apr] - exp_b) < 1e-9


def test_thursday_rule_assigns_cross_month_week():
    # week Mon 29 Apr .. Sun 5 May 2024: Thursday 2 May -> May
    r = _week("pigs", "E", "2024-05-05", 110.0, "2024-05-08")
    assert r["month"] == pd.Period("2024-05", "M")
    # week Mon 27 May .. Sun 2 Jun: Thursday 30 May -> May
    r2 = _week("pigs", "E", "2024-06-02", 110.0, "2024-06-05")
    assert r2["month"] == pd.Period("2024-05", "M")


def test_product_without_previous_month_contributes_nothing_and_commodities_average():
    w = _panel()
    # dairy: only April weeks (no March) -> excluded; cattle: March 200 -> April 210
    extra = [_week("dairy", "EDAM", "2024-04-07", 50.0, "2024-04-10"),
             _week("cattle", "AR2", "2024-03-10", 200.0, "2024-03-13"),
             _week("cattle", "AR2", "2024-04-14", 210.0, "2024-04-17")]
    w = pd.concat([w, pd.DataFrame(extra)], ignore_index=True)
    apr = pd.Period("2024-04", "M")
    s, d = sw.month_signal(w, pd.Series({apr: pd.Timestamp("2024-05-09 23:59")}))
    pigs = 100 * (np.mean(np.log([100, 102, 104, 106])) - np.log(100))
    cattle = 100 * (np.log(210) - np.log(200))
    assert d.loc[apr, "n_commodities"] == 2
    assert abs(s.loc[apr] - (pigs + cattle) / 2) < 1e-9


def test_month_without_previous_month_gives_nan():
    w = _panel()
    # the week ending Sunday 3 March has its Thursday (29 Feb) in February, so
    # February exists in the panel; January does not -> February has no
    # previous month and must be NaN, while March (vs that February week) is defined
    feb, mar = pd.Period("2024-02", "M"), pd.Period("2024-03", "M")
    s, d = sw.month_signal(w, pd.Series({feb: pd.Timestamp("2024-02-29 23:59"),
                                         mar: pd.Timestamp("2024-03-31 23:59")}))
    assert np.isnan(s.loc[feb]) and d.loc[feb, "n_commodities"] == 0
    assert np.isfinite(s.loc[mar]) and d.loc[mar, "n_weeks_month"] == 4


def test_recorded_publication_dates_are_plausible():
    p = sw.load_pubdates()
    if p.empty:
        return
    assert set(p["folder"].unique()) <= {"01", "04", "05"}
    assert p.duplicated(["folder", "iso_year", "iso_week"]).sum() == 0
    # ISO-week end reconstructed from the label must precede publication
    ends = [pd.Timestamp.fromisocalendar(int(y), int(wk), 7) for y, wk in zip(p["iso_year"], p["iso_week"])]
    lag = (p["published"].values - pd.DatetimeIndex(ends).values) / np.timedelta64(1, "D")
    assert (lag >= 0).all() and (lag <= 40).all()
