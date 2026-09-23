"""R30: calendar contributions, past-mean subtraction, availability gating, weight shares."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from models import excise_steps_r30 as m


def calendar(tmp_path):
    text = ('product,effective_month,landing_months,statutory_step_pct,step_basis,available_from,provenance,source,computation\n'
            'cigarettes,2024-02,2024-03|2024-04|2024-05,6.0,retail_price_pct,2023-12-19,sourced_primary,s,c\n'
            'cigarettes,2023-01,2023-02|2023-03|2023-04,3.0,retail_price_pct,2020-12-31,sourced_secondary,s,c\n'
            'spirits,2024-01,2024-01,10.0,excise_rate_pct,2023-12-19,sourced_secondary,s,c\n')
    p = tmp_path / 'cal.csv'; p.write_text(text, encoding='utf-8'); return m.load_calendar(p)


SHARES = {2014: dict(tobacco=.5, spirits=.2), 2022: dict(tobacco=.5, spirits=.2), 2024: dict(tobacco=.55, spirits=.16)}


def test_cigarette_step_spreads_in_thirds_over_the_landing_months(tmp_path):
    cal = calendar(tmp_path)
    assert m.contribution('2024-03', cal, SHARES) == pytest.approx(.55 * 6.0 / 3)
    assert m.contribution('2024-05', cal, SHARES) == pytest.approx(.55 * 6.0 / 3)
    assert m.contribution('2024-02', cal, SHARES) == 0. and m.contribution('2024-06', cal, SHARES) == 0.
    assert m.contribution('2024-03', cal, SHARES, timing='first') == pytest.approx(.55 * 6.0) and m.contribution('2024-04', cal, SHARES, timing='first') == 0.


def test_spirits_step_lands_in_january_scaled_by_theta_and_share(tmp_path):
    cal = calendar(tmp_path)
    assert m.contribution('2024-01', cal, SHARES) == pytest.approx(.16 * 10.0 * m.THETA)
    assert m.contribution('2024-01', cal, SHARES, theta=.35) == pytest.approx(.16 * 10.0 * .35)
    assert m.contribution('2024-02', cal, SHARES) == 0.


def test_basket_year_in_force_is_the_latest_at_or_before(tmp_path):
    cal = calendar(tmp_path)
    assert m.contribution('2023-02', cal, SHARES) == pytest.approx(.5 * 3.0 / 3)      # 2022 basket for 2023
    with pytest.raises(ValueError):
        m.shares_for(pd.Period('2013-01', 'M'), SHARES)


def test_rows_not_yet_available_are_excluded(tmp_path):
    cal = calendar(tmp_path)
    assert m.contribution('2024-03', cal, SHARES, clock=pd.Timestamp('2023-12-01')) == 0.
    assert m.contribution('2024-03', cal, SHARES, clock=pd.Timestamp('2024-03-31')) == pytest.approx(.55 * 2.0)


def test_provenance_filter(tmp_path):
    cal = calendar(tmp_path)
    assert m.contribution('2023-03', cal, SHARES, include=('sourced_primary',)) == 0.
    assert m.contribution('2024-03', cal, SHARES, include=('sourced_primary',)) == pytest.approx(.55 * 2.0)


def test_past_mean_averages_the_same_month_of_every_earlier_series_year(tmp_path):
    cal = calendar(tmp_path)
    # March 2024: earlier Marches 2015..2023; only March 2023 carries a step (0.5 * 3.0 / 3 = 0.5) -> mean over 9 years
    assert m.past_mean('2024-03', cal, SHARES) == pytest.approx(.5 / 9)
    # January 2024: earlier Januaries 2016..2023 (the series starts 2015-02): none carries a step
    assert m.past_mean('2024-01', cal, SHARES) == 0.
    assert m.candidate_block('2024-01', 3.0, cal, SHARES) == pytest.approx(3.0 + .16 * 10.0 * m.THETA)
    assert m.candidate_block('2024-03', 0.5, cal, SHARES) == pytest.approx(0.5 - .5 / 9 + .55 * 2.0)


def test_weight_shares_from_basket_rows():
    w = pd.DataFrame(dict(effective_year=[2024, 2024, 2024, 2026, 2026, 2026], basket_code=['2', '2.11', '2.2', '2', '2.11', '2.3'], weight_permille=[80., 16., 44., 90., 18., 45.]))
    s = m.weight_shares(w)
    assert s[2024] == dict(tobacco=pytest.approx(.55), spirits=pytest.approx(.2)) and s[2026]['tobacco'] == pytest.approx(.5)
