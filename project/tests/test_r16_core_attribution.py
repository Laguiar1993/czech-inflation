"""Oracle accounting fixtures; these outcomes never select a forecast."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("r16_core_attribution", ROOT / "tools/review/r16_core_attribution.py")
ev = importlib.util.module_from_spec(SPEC)
if SPEC.origin and Path(SPEC.origin).exists():
    SPEC.loader.exec_module(ev)


def fixture(models=("STATE_FAST_R15", "DAMPED_P95_Q001_R16"), origins=("2024-01",)):
    headline = pd.Series(.7, index=pd.period_range("2022-01", "2026-12", freq="M"))
    core = headline * 0 + .4
    rows = []
    for origin in origins:
        for model in models:
            core_pred = .8 if model == "STATE_FAST_R15" else .4
            for h in range(13):
                mm = .9 if h == 0 else .3+.5*core_pred
                count = min(h+1, 12)
                logs = (12-count)*np.log1p(.7/100)+(count-int(h<12))*np.log1p((.3+.5*core_pred)/100)+int(h<12)*np.log1p(.9/100)
                rows.append(dict(origin=origin, h=h, target=str(pd.Period(origin, "M")+h), model=model,
                    mm_forecast=mm, value_core=core_pred if h else np.nan, weight_core=.5 if h else np.nan,
                    contribution_core=.5*core_pred if h else np.nan, contribution_food=.3 if h else np.nan,
                    yy_exante=100*np.expm1(logs), yy_actual=100*np.expm1(12*np.log1p(.7/100))))
    native = pd.DataFrame(rows)
    return native, native[["origin", "h", "target", "model", "mm_forecast", "yy_exante", "yy_actual"]].copy(), headline, core


def test_exact_oracle_accounting_exposes_core_error_cancellation_and_h0_window():
    native, raw, headline, core = fixture()
    paths, checks = ev.oracle_monthly(native, core, tuple(native.model.unique()))
    result = ev.decompose(paths, raw, headline, tuple(native.model.unique()), tuple(native.model.unique()))
    late = result[result.h.eq(12)]
    fast = late[late.model.eq("STATE_FAST_R15")].iloc[0]
    new = late[late.model.eq("DAMPED_P95_Q001_R16")].iloc[0]
    assert fast.total_error_log == pytest.approx(0., abs=1e-12)
    assert fast.core_effect_log > 0 and fast.retained_error_log < 0
    assert fast.core_effect_log == pytest.approx(-fast.retained_error_log)
    assert new.core_effect_log == pytest.approx(0.)
    assert new.core_cumulative_error_log == pytest.approx(0.)
    assert abs(new.total_error_log) > abs(fast.total_error_log)
    assert fast.retained_error_log == pytest.approx(new.retained_error_log)
    assert not fast.h0_in_annual_window
    early = result[result.h.eq(3) & result.model.eq("STATE_FAST_R15")].iloc[0]
    expected = 100*np.log(1.009/1.007)+300*np.log(1.005/1.007)
    assert early.retained_error_log == pytest.approx(expected)
    assert early.h0_in_annual_window
    scores, paired, summary = ev.score_attribution(result)
    assert np.allclose(scores.total_mse_log, scores.core_effect_mse_log+scores.retained_mse_log+scores.twice_core_retained_cross_moment)
    assert np.allclose(paired.total_squared_loss_difference, paired.core_effect_squared_loss_difference+paired.cross_moment_difference)


def test_oracle_never_fills_missing_intermediate_core_or_monthly_inputs():
    native, raw, headline, core = fixture()
    models = tuple(native.model.unique())
    core.loc["2024-03"] = np.nan
    paths, _ = ev.oracle_monthly(native, core, models)
    assert paths.loc[paths.h.eq(2), "oracle_mm"].isna().all()
    with pytest.raises(ValueError, match="intermediate"):
        ev.decompose(paths, raw, headline, models, models)
    native, raw, headline, core = fixture()
    native = native[~(native.h.eq(2) & native.model.eq(models[1]))]
    paths, _ = ev.oracle_monthly(native, core, models)
    with pytest.raises(ValueError, match="intermediate"):
        ev.decompose(paths, raw, headline, models, models)


def test_oracle_rejects_different_weights_retained_blocks_and_bad_core_accounting():
    native, _, _, core = fixture(); models = tuple(native.model.unique())
    bad = native.copy(); bad.loc[bad.model.eq(models[1]) & bad.h.eq(1), "weight_core"] = .7
    with pytest.raises(ValueError, match="weight"):
        ev.oracle_monthly(bad, core, models)
    bad = native.copy(); bad.loc[bad.model.eq(models[1]) & bad.h.eq(1), "contribution_food"] = .5
    with pytest.raises(ValueError, match="retained"):
        ev.oracle_monthly(bad, core, models)
    bad = native.copy(); bad.loc[bad.model.eq(models[1]) & bad.h.eq(1), "contribution_core"] = .5
    with pytest.raises(ValueError, match="core contribution"):
        ev.oracle_monthly(bad, core, models)


def test_original_roster_headline_support_is_fixed_before_attribution():
    native, raw, headline, core = fixture(models=("STATE_FAST_R15", "DAMPED_P95_Q001_R16", "other"))
    raw.loc[raw.model.eq("other") & raw.h.eq(12), "yy_exante"] = np.nan
    models = ("STATE_FAST_R15", "DAMPED_P95_Q001_R16")
    paths, _ = ev.oracle_monthly(native[native.model.isin(models)], core, models)
    result = ev.decompose(paths, raw, headline, models, (*models, "other"))
    assert not result.h.eq(12).any()
    assert result.groupby("h").model.nunique().eq(2).all()


def test_full_attribution_exports_manifest_and_keeps_every_input_unchanged(tmp_path):
    root = tmp_path / "repo"; experiment = root / "output/research_r16"
    for folder in (experiment, root / "output/research_r15", root / "output/research_r14b/integration", root / "tests/fixtures/cleanup"):
        folder.mkdir(parents=True, exist_ok=True)
    native, raw, headline, core = fixture(models=ev.ROSTER, origins=("2023-12", "2024-01"))
    raw.to_csv(experiment / "forecasts.csv", index=False)
    native[native.model.isin(ev.NEW_MODELS)].to_csv(experiment / "native_forecasts.csv", index=False)
    native[native.model.eq(ev.FAST)].to_csv(root / "output/research_r15/native_forecasts.csv", index=False)
    native[native.model.eq(ev.CURRENT)].to_csv(root / "output/research_r14b/integration/native_forecasts.csv", index=False)
    pd.DataFrame({"period": headline.index.astype(str), "headline_mm": headline.values}).to_csv(root / "output/independent_path_frozen_inputs.csv", index=False)
    pd.DataFrame({"period": core.index.astype(str), "core": core.values}).to_csv(root / "tests/fixtures/cleanup/cnb_core_mm.csv", index=False)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    out = ev.evaluate(experiment, root)
    assert all(p.read_bytes() == value for p, value in before.items())
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["models"] == list(ev.MODELS)
    data = pd.read_csv(out / "attribution.csv")
    assert len(data) == 2*12*len(ev.MODELS)
    assert data.groupby(["origin", "h"]).retained_error_log.apply(lambda x: x.max()-x.min()).max() < 1e-12
    scores = pd.read_csv(out / "scoreboard.csv")
    assert set(scores["sample"]) == {"full", "origins_2024plus"}
    assert (out / "paired_vs_fast_summary.csv").exists()
