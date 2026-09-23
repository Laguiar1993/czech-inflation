"""Refresh data/cz_ip_sa_level.csv from CZSO's PRU01C open-data sada.

CZSO publishes industrial production 3 ways: PRU01A (unadjusted), PRU01B
(calendar-adjusted only), PRU01C (seasonally + calendar adjusted) -- this
pulls PRU01C directly rather than re-deriving SA ourselves, and it goes
back to 2000, 15 years deeper than the YoY-only series (czso.ip_ri) this
project had been using locally.

Usage: python data/pull_cz_ip_sa.py
"""
from __future__ import annotations
from pathlib import Path

import duckdb

URL = "https://data.csu.gov.cz/opendata/sady/PRU01C/distribuce/csv"
OUT = Path(__file__).parent / "cz_ip_sa_level.csv"


def main():
    con = duckdb.connect()
    df = con.sql(f"""
        SELECT "CASMQ" as ym, Hodnota FROM read_csv_auto('{URL}')
        WHERE "CZ-NACE-Sekce" = 'Průmysl celkem' AND "CZ-NACE-Oddíl" IS NULL
          AND "Typ indexu" = 'Bazický index (2021 = 100)'
        ORDER BY ym
    """).df()
    monthly = df[df["ym"].str.match(r"^\d{4}-\d{2}$")].drop_duplicates(subset="ym")
    monthly.to_csv(OUT, index=False)
    print(f"wrote {len(monthly)} rows -> {OUT}  ({monthly['ym'].min()}..{monthly['ym'].max()})")


if __name__ == "__main__":
    main()
