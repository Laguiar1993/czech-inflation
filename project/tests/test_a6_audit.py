"""The rebuilt Table A6 audit keeps exact and candidate inputs apart."""
import pandas as pd
import pytest

from tools.paper_replication import build_a6_audit as audit

REQUIRED = [audit.VALIDATION_DIR / "bcs_candidate_verdicts.csv", audit.CANDIDATE_DIR / "candidate_periods_long.csv",
            audit.ECFIN_LONG, audit.CZSO_DIR / "CEN02A.csv", audit.EUROSTAT_DIR / "ei_bsco_m.csv", audit.OLD_AUDIT]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    if not all(path.exists() for path in REQUIRED):
        pytest.skip("audit inputs not present")
    base = tmp_path_factory.mktemp("a6")
    manifest = audit.build(base / "out", base / "inputs")
    table = pd.read_csv(base / "out" / "a6_audit.csv")
    exact = pd.read_csv(base / "inputs" / "exact_inputs_long.csv", dtype={"period": str})
    candidates = pd.read_csv(base / "inputs" / "candidate_inputs_long.csv", dtype={"period": str})
    return manifest, table, exact, candidates


def test_every_row_has_one_declared_status(built):
    _, table, _, _ = built
    assert table.number.tolist() == list(range(1, 73))
    assert table.a6_status.isin(audit.STATUSES).all()


def test_bloomberg_never_enters_the_exact_panel(built):
    _, table, exact, candidates = built
    assert not exact.source_id.str.contains("bloomberg|bbg", case=False).any()
    assert set(exact.a6_number) == set(table.loc[table.a6_status.eq("exact"), "number"])
    assert candidates.column.str.match(r"^(bbg|local)__").all()
    assert not set(candidates.column) & set(exact.source_id)


def test_transforms_follow_the_paper(built):
    _, table, _, _ = built
    assert (table.transform_paper == table.transform_runner_now).all()
    assert table.set_index("number").loc[38, "transform_runner_20260910"] == 0


def test_coverage_gap_flag_matches_the_first_period(built):
    _, table, _, _ = built
    exact = table[table.a6_status.eq("exact")]
    late = pd.PeriodIndex(exact.status_first_period.astype(str), freq="M") > pd.Period("2002-05", freq="M")
    assert (late == exact.historical_coverage_gap.to_numpy()).all()


def test_assumed_availability_follows_the_reference_period(built):
    _, _, exact, _ = built
    period_end = pd.PeriodIndex(exact.period, freq="M").end_time.normalize()
    assert (pd.to_datetime(exact.available_from_assumed) > period_end).all()


def test_resolved_rows(built):
    _, table, _, _ = built
    rows = table.set_index("number")
    assert rows.loc[[15, 16], "a6_status"].eq("unavailable").all()
    assert rows.loc[[54, 17], "a6_status"].eq("validated_proxy").all()
    assert rows.loc[64, "a6_status"] == "exact"
    assert rows.loc[[50, 51, 52], "historical_coverage_gap"].all()
    assert "EUA4CZ Index (rejected)" in rows.loc[10, "bloomberg_candidates"]
