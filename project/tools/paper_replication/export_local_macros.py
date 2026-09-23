"""Export the local official macro inputs used by the CNB-paper audit.

The paper-comparison runner is intentionally file based: a future machine can
copy the small CSV bundle and rerun the experiment without a live DuckDB
connection.  This exporter is a convenience for refreshing that bundle from
the project's local Czechia database.  It does not fetch the web or alter the
database.  ``release_date`` is retained wherever the source table provides it;
the runner still treats the resulting panel as a reference-month comparison
unless a separate availability rule is declared.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd


DEFAULT_DB = Path.home() / "economic_db" / "czechia.duckdb"
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "data" / "paper_replication"

ARAD_IDS = (
    "SFTP04M2206",  # 3m PRIBOR monthly average (paper wants EOM; retained)
    "SFTP01M11",    # 2-week repo, month end
    "SVSDM12",      # 10-year government yield, monthly average
    "SREERM101",    # REER, PPI deflated
    "SREERM103",    # REER, CPI deflated
    "SUCM102211XXX101101",  # household client-loan balance
    "SUCM100311XXX101101",  # NFC client loans, total
    "SUCM200311XXX101101",  # NFC client loans, up to 1 year bucket
    "SUCM300311XXX101101",  # NFC client loans, 1–5 year bucket
    "SUCM400311XXX101101",  # NFC client loans, over 5 year bucket
    "SMV5M108",     # M3 balance
)


def _write(con: duckdb.DuckDBPyConnection, sql: str, path: Path) -> int:
    frame = con.sql(sql).df()
    frame.to_csv(path, index=False, encoding="utf-8")
    return len(frame)


def export(db_path: Path = DEFAULT_DB, output_dir: Path = DEFAULT_OUT) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=True)
    counts: dict[str, int] = {}
    ids = ",".join("'" + i + "'" for i in ARAD_IDS)
    counts["arad_selected"] = _write(
        con,
        f"""
        SELECT indicator_id, period, snapshot_id, value
        FROM monetary.arad_data
        WHERE indicator_id IN ({ids})
        ORDER BY indicator_id, period, snapshot_id
        """,
        output_dir / "arad_selected.csv",
    )
    counts["arad_metadata"] = _write(
        con,
        f"""
        SELECT indicator_id, indicator_name, frequency_code, frequency_name, unit,
               unit_mult_code, unit_mult_name, set_id, base_id
        FROM monetary.arad_indicators
        WHERE indicator_id IN ({ids})
        ORDER BY indicator_id
        """,
        output_dir / "arad_selected_metadata.csv",
    )
    counts["bcs_survey"] = _write(
        con,
        "SELECT year, month, indic_code, indic_label, value FROM eurostat.bcs_survey ORDER BY year, month, indic_code",
        output_dir / "bcs_aggregate_surveys.csv",
    )
    counts["ip_ri"] = _write(
        con,
        "SELECT release_date, data_month, nace_code, nace_label_en, yoy_index, source_url FROM czso.ip_ri ORDER BY data_month, nace_code, release_date",
        output_dir / "czso_ip_release.csv",
    )
    counts["retail_ri"] = _write(
        con,
        "SELECT release_date, data_month, code, label_en, yoy_index, source_url FROM czso.retail_ri ORDER BY data_month, code, release_date",
        output_dir / "czso_retail_release.csv",
    )
    counts["construction_ri"] = _write(
        con,
        "SELECT release_date, data_month, code, label_en, yoy_index, source_url FROM czso.construction_ri ORDER BY data_month, code, release_date",
        output_dir / "czso_construction_release.csv",
    )
    counts["unemployment_ri"] = _write(
        con,
        "SELECT release_date, data_month, adjusted, series, gender, rate_pct, source_url FROM czso.unemployment_ri ORDER BY data_month, adjusted, series, gender, release_date",
        output_dir / "czso_unemployment_release.csv",
    )
    con.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    counts = export(args.db, args.output_dir)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
