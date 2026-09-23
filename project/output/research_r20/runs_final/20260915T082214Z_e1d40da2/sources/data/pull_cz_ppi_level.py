"""Refresh data/cz_ppi_level_raw.csv from CZSO's CEN0201B open-data sada.

CEN0201B carries the PPI as a genuine fixed-base LEVEL index (2015=100),
unlike the YoY-ratio-only series czso.ppi_ri holds locally -- needed as
X-13 input, which requires a chainable level series, not something already
differenced into a growth rate (X-13 does its own differencing internally).

Usage: python data/pull_cz_ppi_level.py
"""
from __future__ import annotations
from pathlib import Path

import duckdb

URL = "https://data.csu.gov.cz/opendata/sady/CEN0201B/distribuce/csv"
OUT = Path(__file__).parent / "cz_ppi_level_raw.csv"


def main():
    con = duckdb.connect()
    df = con.sql(f"""
        SELECT "Měsíce, měsíční kumulace, měsíce klouzavých průměrů, čtvrtletí, roky" as label,
               "CASMKMQRM12" as code, Hodnota
        FROM read_csv_auto('{URL}')
        WHERE "Klasifikace produkce-Agregace" = 'ÚHRN' AND "Typ indexu" = 'Bazický index (2015 = 100)'
          AND "Klasifikace produkce-Sekce" IS NULL AND "Klasifikace produkce-Oddíl" IS NULL
          AND "Klasifikace produkce-Skupina" IS NULL
        ORDER BY code
    """).df()
    df.to_csv(OUT, index=False)
    print(f"wrote {len(df)} rows -> {OUT}")


if __name__ == "__main__":
    main()
