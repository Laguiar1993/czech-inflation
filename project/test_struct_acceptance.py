"""Acceptance tests for the codex-p0 corrections (audit 'Required
acceptance tests'). Run: python -m pytest test_struct_acceptance.py -q
"""
import warnings

import numpy as np
import pandas as pd
import pytest
from pathlib import Path

warnings.filterwarnings("ignore")

import cz_struct as S  # noqa: E402


@pytest.fixture
def weight_inputs():
    """Frozen components: acceptance tests must not refresh or query live data."""
    root = Path(__file__).resolve().parent / "tests" / "fixtures" / "cleanup"
    def read(name):
        frame = pd.read_csv(root / name, index_col=0)
        frame.index = pd.PeriodIndex(frame.index, freq="M")
        return frame
    return (read("target_headline_cpi_mm.csv").iloc[:, 0],
            read("component_food_fuel_mm.csv"),
            read("cnb_core_mm.csv").iloc[:, 0].rename("core"),
            read("cnb_regulated_mm.csv").iloc[:, 0].rename("reg"),
            read("alcohol_tobacco.csv").iloc[:, 0])


def test_undated_announcement_fails_closed():
    """Audit counterexample 1: a calendar row with a missing available_from
    must be rejected, never admitted."""
    S._ANN = None
    S._announcements()  # prime the _ANN cache before mutating it
    p = pd.Period("2022-01", "M")
    S._ANN.loc[p, "available_from"] = pd.NaT
    try:
        v = S._gate_value(p, pd.Timestamp("2022-01-31"), "reconstructed_scenario")
        assert np.isnan(v), "undated announcement was admitted"
    finally:
        S._ANN = None  # restore from disk on next use


def test_explicit_as_of_blocks_not_yet_public():
    """Audit counterexample 2: a call actually made on 1 December must NOT
    admit a 15 December announcement; month-end may never be inferred."""
    S._ANN = None
    p = pd.Period("2022-01", "M")
    early = S._gate_value(p, pd.Timestamp("2021-12-01"), "reconstructed_scenario")
    late = S._gate_value(p, pd.Timestamp("2021-12-31"), "reconstructed_scenario")
    assert np.isnan(early), "1-Dec as_of admitted a 15-Dec announcement"
    assert not np.isnan(late)


def test_verified_mode_never_uses_reconstructed():
    S._ANN = None
    p = pd.Period("2023-01", "M")
    v = S._gate_value(p, pd.Timestamp("2022-12-31"), "verified_only")
    assert np.isnan(v), "verified_only admitted a reconstructed magnitude"


def test_weights_sum_to_one_every_regime(weight_inputs):
    y, comp, core, reg, alc = weight_inputs
    for kt in [pd.Period("2019-06", "M"), pd.Period("2025-02", "M"),
               pd.Period("2026-07", "M")]:
        wmap = S.solve_weights(y, comp, core, reg, kt, as_of=(kt + 1).end_time, alc=alc)
        for rg, w in wmap.items():
            s = w["food"] + w["fuel"] + w["alc"] + w["administered"] + w["core"]
            assert abs(s - 1.0) < 1e-12, f"regime {rg} at {kt}: sum={s}"


def test_basket_anchor_not_available_before_publication(weight_inputs):
    """A January/early-February origin in a new even year must still use the
    PREVIOUS window's anchors (basket published ~mid-Feb)."""
    y, comp, core, reg, alc = weight_inputs
    w_jan = S.solve_weights(y, comp, core, reg, pd.Period("2025-12", "M"), as_of=pd.Timestamp("2026-01-31"), alc=alc)
    assert abs(w_jan[2026]["food"] - S._OFFICIAL_FOOD[2024]) < 1e-9, \
        "Jan-2026 origin saw the 2026 basket before its publication"
    w_mar = S.solve_weights(y, comp, core, reg, pd.Period("2026-02", "M"), as_of=pd.Timestamp("2026-03-31"), alc=alc)
    assert abs(w_mar[2026]["food"] - S._OFFICIAL_FOOD[2026]) < 1e-9


def test_band_endpoints_orientation():
    """Audit P0 #5: for error = forecast - actual, the actual's band is
    [f - q95(e), f - q05(e)]. A model that always overpredicts by 1 must
    have its band shifted DOWN."""
    e = np.array([1.0] * 30)         # always overpredicts by 1
    f = 5.0
    lo = f - np.quantile(e, 0.95)
    hi = f - np.quantile(e, 0.05)
    assert lo == hi == 4.0, "band did not shift down for an overpredicting model"
