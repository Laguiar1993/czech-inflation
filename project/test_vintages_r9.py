"""Release-vintage selection: never backdate revisions or mix adjustment concepts."""
import hashlib
import importlib
import json
from pathlib import Path

import pandas as pd
import pytest


def api():
    try:
        return importlib.import_module("data.vintages")
    except ModuleNotFoundError:
        pytest.fail("The explicit release-vintage selector has not been implemented")


def row(period="2024-01", when="2024-03-05T00:00:00+01:00", value=3.0,
        series="unemployment_sa"):
    return dict(series=series, reference_period=period, available_from=when,
                value=value, source="https://csu.gov.cz/archive/release.xlsx",
                sha256=hashlib.sha256(str(value).encode()).hexdigest(),
                adjustment="sa", vintage_kind="historical_release")


def test_future_revision_is_excluded():
    df = pd.DataFrame([row(), row(when="2026-09-01T00:00:00+02:00", value=9)])
    got = api().select_vintages(df, "2024-03-10T00:00:00Z")
    assert got["value"].tolist() == [3.0]


def test_latest_eligible_vintage_per_reference_is_selected_at_boundary():
    df = pd.DataFrame([row(value=3), row(when="2024-04-03T00:00:00+02:00", value=2.8),
                       row("2024-02", "2024-04-03T00:00:00+02:00", 3.1)])
    before = api().select_vintages(df, "2024-04-02T21:59:59Z")
    at = api().select_vintages(df, "2024-04-02T22:00:00Z")
    assert before["value"].tolist() == [3]
    assert at["value"].tolist() == [2.8, 3.1]


@pytest.mark.parametrize("field", ["series", "reference_period", "available_from", "value", "source", "sha256"])
def test_missing_metadata_rejected(field):
    df = pd.DataFrame([row()]).drop(columns=field)
    with pytest.raises(ValueError, match=field):
        api().select_vintages(df, "2024-04-10T00:00:00Z")


@pytest.mark.parametrize("field,value", [("available_from", "2024-03-05"),
    ("source", ""), ("sha256", "bad"), ("value", float("nan")),
    ("reference_period", "2024-01-05")])
def test_invalid_metadata_rejected(field, value):
    bad = row(); bad[field] = value
    with pytest.raises(ValueError):
        api().select_vintages(pd.DataFrame([bad]), "2024-04-10T00:00:00Z")


def test_ambiguous_duplicate_rejected_even_if_order_changes():
    for records in ([row(value=3), row(value=4)], [row(value=4), row(value=3)]):
        with pytest.raises(ValueError, match="[Dd]uplicate|[Aa]mbiguous"):
            api().select_vintages(pd.DataFrame(records), "2024-04-10T00:00:00Z")


def test_equivalent_timezone_duplicate_rejected():
    df = pd.DataFrame([row(), row(when="2024-03-04T23:00:00Z", value=4)])
    with pytest.raises(ValueError, match="[Dd]uplicate|[Aa]mbiguous"):
        api().select_vintages(df, "2024-04-10T00:00:00Z")


def test_naive_origin_is_rejected():
    with pytest.raises(ValueError, match="timezone|aware"):
        api().select_vintages(pd.DataFrame([row()]), "2024-04-10")


def test_old_values_in_recent_file_are_not_backdated():
    df = pd.DataFrame([row("2008-01", "2026-09-01T00:00:00+02:00", 5.3)])
    assert api().select_vintages(df, "2019-01-01T00:00:00Z").empty


def test_adjusted_policy_uses_each_origins_whole_published_history(tmp_path):
    records = [row("2008-01", value=4.5), row(value=3.0)]
    for period, val in [("2008-01", 4.7), ("2024-01", 2.9), ("2025-04", 2.7)]:
        r = row(period, "2025-06-03T00:00:00+02:00", val, "unemployment_trend_cycle")
        r["adjustment"] = "trend_cycle"; records.append(r)
    p = tmp_path / "unemployment.csv"; pd.DataFrame(records).to_csv(p, index=False)
    old = api().released_unemployment("2024-04-10T00:00:00Z", p)
    new = api().released_unemployment("2025-06-10T00:00:00Z", p)
    assert old.loc[pd.Period("2008-01", "M")] == 4.5
    assert new.loc[pd.Period("2008-01", "M")] == 4.7
    assert old.attrs["adjustments"] == ["sa"]
    assert new.attrs["adjustments"] == ["trend_cycle"]


def test_nsa_remains_separate_and_missing_origins_stay_empty(tmp_path):
    records = [row()]
    r = row("2024-01", "2025-06-03T00:00:00+02:00", 3.3, "unemployment_nsa")
    r["adjustment"] = "nsa"; records.append(r)
    p = tmp_path / "unemployment.csv"; pd.DataFrame(records).to_csv(p, index=False)
    assert api().released_unemployment("2024-04-10T00:00:00Z", p, adjustment="nsa").empty
    assert api().released_unemployment("2025-06-10T00:00:00Z", p, adjustment="nsa").iloc[0] == 3.3


def test_latest_vintage_snapshot_cannot_enter_historical_selector(tmp_path):
    r = row(); r["vintage_kind"] = "latest_vintage_snapshot"
    p = tmp_path / "unemployment.csv"; pd.DataFrame([r]).to_csv(p, index=False)
    with pytest.raises(ValueError, match="historical_release"):
        api().released_unemployment("2024-04-10T00:00:00Z", p)


def archive_api():
    try:
        return importlib.import_module("tools.archive_unemployment")
    except ModuleNotFoundError:
        pytest.fail("The archival release parser has not been implemented")


def test_archive_date_only_evidence_is_conservatively_available_next_prague_day():
    html = '<h1>Release</h1><p>Datum vydání: 02. 06. 2025</p>'
    got = archive_api().parse_release_page(html, "https://csu.gov.cz/release")
    assert got["release_date"] == "2025-06-02"
    assert got["available_from"] == "2025-06-02T22:00:00+00:00"
    assert got["availability_precision"] == "date_only_next_local_midnight"


def test_archive_does_not_infer_release_date_from_reference_month():
    with pytest.raises(ValueError, match="publication date"):
        archive_api().parse_release_page("<h1>January 2019</h1>", "https://csu.gov.cz/release")


def test_archive_identifies_adjustment_from_official_table_labels():
    html = '''Datum vydání: 02. 06. 2025
        <a href="/docs/table_1.xlsx">Tab. 1 Míra zaměstnanosti (trendcyklus)</a>
        <a href="/docs/table_2.xlsx">Tab. 2 Míra zaměstnanosti (neočištěná)</a>
        <a href="/docs/graph.xlsx">Graf</a>'''
    got = archive_api().parse_release_page(html, "https://csu.gov.cz/release")
    assert [x["adjustment"] for x in got["tables"]] == ["trend_cycle", "nsa"]


def test_table_parser_preserves_historical_values_and_months():
    fixture = pd.DataFrame([
        ["Tab. 1", "Rates seasonally adjusted", None, None, None, None],
        [None, None, "Employment", None, None, "General unemployment rate 15 to 64 years"],
        [None, None, "Total", None, None, "Total"],
        [2019, "M 01", 70, None, None, 2.062605],
        [None, "M 02", 71, None, None, 1.925868],
    ])
    got = archive_api().parse_rate_table(fixture, "2019-02")
    assert got == [{"reference_period": "2019-01", "value": 2.062605},
                   {"reference_period": "2019-02", "value": 1.925868}]


def test_table_parser_rejects_future_months_in_archival_attachment():
    fixture = pd.DataFrame([
        [None, None, None, None, None, "General unemployment rate 15 to 64 years"],
        [None, None, None, None, None, "Total"],
        [2026, "M 01", None, None, None, 3.0],
    ])
    with pytest.raises(ValueError, match="reference|future"):
        archive_api().parse_rate_table(fixture, "2019-02")


def test_delivered_archive_has_complete_declared_coverage_and_portable_hash_paths():
    directory = Path(__file__).parent / "data" / "vintages"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    expected = pd.period_range(manifest["requested_start"], manifest["requested_end"], freq="M")
    assert [r["reference_release"] for r in manifest["releases"]] == expected.astype(str).tolist()
    for release in manifest["releases"]:
        assert release["status"] == "ok"
        assert "\\" not in release["page_file"], "Archive paths must be portable across operating systems"
        assert hashlib.sha256((directory / release["page_file"]).read_bytes()).hexdigest() == release["page_sha256"]
        for table in release["tables"]:
            assert "\\" not in table["raw_file"]
            assert hashlib.sha256((directory / table["raw_file"]).read_bytes()).hexdigest() == table["sha256"]


def test_recovered_archive_actual_revision_and_methodology_boundary():
    old = api().released_unemployment("2019-03-10T23:00:00Z")
    current = api().released_unemployment("2026-09-09T00:00:00Z")
    january = pd.Period("2019-01", "M")
    assert old.loc[january] == pytest.approx(2.15696032979774)
    assert current.loc[january] == pytest.approx(2.0707790225766067)
    assert old.attrs["adjustments"] == ["sa"]
    assert current.attrs["adjustments"] == ["trend_cycle"]
    assert api().released_unemployment("2008-12-31T23:00:00Z").empty
    assert api().released_unemployment("2024-12-31T23:00:00Z", adjustment="nsa").empty
