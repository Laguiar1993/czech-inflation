"""v2.5-timing tests (TIMING_SPEC_v25.md), offline.

Release calendar lookups, eligibility applied to weights / admin / alcohol /
wedge, the STALE-vs-NOT_DUE classification, the month-to-date FX helper,
and the zone-aware live clock under the evaluation classifier.
"""
import numpy as np
import pandas as pd
import pytest

import cz_struct as S
from evaluation.prospective import classify_shadow_row


def test_calendar_dates_come_from_the_sourced_file():
    assert S._detail_release_dt(pd.Period('2026-01', 'M')) == pd.Timestamp('2026-02-13 09:00')
    assert S._first_release_dt(pd.Period('2026-01', 'M')) == pd.Timestamp('2026-02-05 09:00')
    assert S._detail_release_dt(pd.Period('2026-08', 'M')) == pd.Timestamp('2026-09-10 09:00')
    # before the flash era the first release IS the detailed release
    p = pd.Period('2019-03', 'M')
    assert S._first_release_dt(p) == S._detail_release_dt(p)
    assert S._first_release_dt(p).hour == 9


def test_fallback_outside_calendar_is_conservative():
    u = pd.Period('2008-05', 'M')   # calendar starts 2010-01
    assert not S._cpi_family_released_by(u, pd.Timestamp('2008-06-15'))
    assert S._cpi_family_released_by(u, pd.Timestamp('2008-06-20 09:00'))


def test_basket_publication_uses_the_january_detail_release():
    assert S._basket_available_from(2026) == pd.Timestamp('2026-02-13')   # not the 5 Feb flash
    assert S._basket_available_from(2024) == pd.Timestamp('2024-02-15')
    assert S._basket_available_from(2008) == pd.Timestamp('2008-02-15')   # fallback


def _synthetic(last='2026-07'):
    idx = pd.period_range('2016-01', last, freq='M')
    rng = np.random.default_rng(1)
    y = pd.Series(0.2 + 0.1 * rng.standard_normal(len(idx)), index=idx, name='cpi_mm')
    core = (y * 0.9).rename('core')
    reg = (y * 1.2).rename('reg')
    reg.iloc[-1] = 25.0        # an outlier in the last month moves anything that uses it
    comp = pd.DataFrame({'food': y * 1.1, 'fuel': y * 0.7})
    alc = y.copy().rename('alc')
    alc.iloc[-1] = 9.0
    return y, comp, core, reg, alc


def test_solve_weights_excludes_unreleased_months():
    y, comp, core, reg, alc = _synthetic()
    known = pd.Period('2026-07', 'M')          # July detail release: 2026-08-11 09:00
    early = S.solve_weights(y, comp, core, reg, known, as_of=pd.Timestamp('2026-08-05'), alc=alc)[2026]
    late = S.solve_weights(y, comp, core, reg, known, as_of=pd.Timestamp('2026-08-12'), alc=alc)[2026]
    assert early['administered'] != late['administered'], "July's outlier must only enter once released"
    assert abs(sum(early.values()) - 1) < 1e-12 and abs(sum(late.values()) - 1) < 1e-12


def test_admin_alcohol_and_wedge_use_the_clock():
    y, comp, core, reg, alc = _synthetic()
    t = pd.Period('2026-08', 'M')
    # short-history fallback branches, where the last month participates
    short_reg = reg.iloc[-3:]
    a_early = S.admin_forecast(short_reg, t, as_of=pd.Timestamp('2026-08-05'))
    a_late = S.admin_forecast(short_reg, t, as_of=pd.Timestamp('2026-08-12'))
    assert a_early != a_late
    short_alc = alc.iloc[-3:]
    b_early = S.alc_forecast(short_alc, t, t - 1, as_of=pd.Timestamp('2026-08-05'))
    b_late = S.alc_forecast(short_alc, t, t - 1, as_of=pd.Timestamp('2026-08-12'))
    assert b_early != b_late
    wmap = S.solve_weights(y, comp, core, reg, t - 1, as_of=pd.Timestamp('2026-08-12'), alc=alc)
    wedge = (y - 0.2 * comp['food']).rename('wedge')
    w_early = S._weighted_wedge(y, comp, alc, core, reg, wedge, wmap, as_of=pd.Timestamp('2026-08-05'))
    w_late = S._weighted_wedge(y, comp, alc, core, reg, wedge, wmap, as_of=pd.Timestamp('2026-08-12'))
    assert w_early.index.max() == pd.Period('2026-06', 'M')
    assert w_late.index.max() == pd.Period('2026-07', 'M')


def test_eligible_edge_fingerprint():
    idx = pd.period_range('2020-01', '2026-07', freq='M')
    t = pd.Period('2026-08', 'M')
    assert S._eligible_edge(idx, t - 1, pd.Timestamp('2026-08-05')) == pd.Period('2026-06', 'M')
    assert S._eligible_edge(idx, t - 1, pd.Timestamp('2026-08-31 23:59')) == pd.Period('2026-07', 'M')


def test_missing_feature_classification():
    t = pd.Period('2026-08', 'M')
    assert S._classify_missing('exp12', t, pd.Timestamp('2026-08-10')) == 'NOT_DUE'
    assert S._classify_missing('exp12', t, pd.Timestamp('2026-08-20')) == 'STALE'
    assert S._classify_missing('core_l1', t, pd.Timestamp('2026-08-10')) == 'NOT_DUE'   # July detail 11 Aug
    assert S._classify_missing('core_l1', t, pd.Timestamp('2026-08-12')) == 'STALE'
    assert S._classify_missing('agri_l0', t, pd.Timestamp('2026-08-20')) == 'NOT_DUE'
    assert S._classify_missing('agri_l0', t, pd.Timestamp('2026-08-27')) == 'STALE'
    # an interaction inherits NOT_DUE from either factor
    assert S._classify_missing('exp12_x_state', t, pd.Timestamp('2026-08-10')) == 'NOT_DUE'
    t9 = pd.Period('2026-09', 'M')   # state needs August CPI (detail 10 Sep)
    assert S._classify_missing('eurczk_mm_x_state', t9, pd.Timestamp('2026-09-07')) == 'NOT_DUE'
    assert S._classify_missing('exp12_x_state', t, pd.Timestamp('2026-08-20')) == 'STALE'


def test_months_missing_from_the_calendar_fail_closed():
    # inside the calendar's span (2010-01 onward) but not recorded -> never released
    assert not S._cpi_family_released_by(pd.Period('2027-05', 'M'), pd.Timestamp('2027-09-01'))
    assert S._cpi_family_released_by(pd.Period('2026-08', 'M'), pd.Timestamp('2026-09-10 09:00'))


def test_month_to_date_fx(monkeypatch):
    fix = pd.Series([24.0, 24.2, 24.4, 24.6],
                    index=pd.to_datetime(['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04']))
    monkeypatch.setattr(S.la, 'fetch_cnb_daily_eur_fixings', lambda year: fix if year == 2026 else fix.iloc[:0])
    monthly = pd.Series({pd.Period('2026-08', 'M'): 24.0})
    # v2.6 (Codex R6 / user decision): fixings dated before the call day only,
    # so a 3 September call sees the 1 and 2 September fixings
    v, n = S._eurczk_mtd_mm(pd.Period('2026-09', 'M'), pd.Timestamp('2026-09-03 15:00'), monthly)
    assert n == 2 and abs(v - (100 * (24.1 / 24.0 - 1))) < 1e-9
    v0, n0 = S._eurczk_mtd_mm(pd.Period('2026-09', 'M'), pd.Timestamp('2026-08-31 15:00'), monthly)
    assert n0 == 0 and np.isnan(v0)


def test_live_clock_is_zone_aware_and_classifiable():
    aware, wall = S._now_prague()
    assert aware.tzinfo is not None and wall.tzinfo is None
    row = {'archive_ok': True, 'n_imputed': 0, 'release_stage': 'pre_flash',
           'spec': S.SPEC_TAG, 'run_ts': aware.isoformat(timespec='seconds'),
           'release_ts': (aware + pd.Timedelta(days=3)).isoformat()}
    # v2.5 or any later construction tag (v2.6-r6 ...): the classifier's timeliness
    # verdict is keyed on the aware clock, not on the tag text
    assert tuple(int(x) for x in S.SPEC_TAG[1:].split('-')[0].split('.')) >= (2, 5)
    assert classify_shadow_row(row) == 'TIMELY_UNVERIFIED'
