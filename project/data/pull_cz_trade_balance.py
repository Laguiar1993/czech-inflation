"""Refresh data/cz_trade_balance.csv from CZSO's VZOOM open-data sada.

VZOOM (foreign trade in goods, monthly) is a ~570MB CSV with no server-side
filtering support over HTTP -- duckdb's read_csv_auto times out scanning it
remotely. Download once to a temp file, filter locally, discard the temp
file. Re-run this monthly (or whenever the trade-balance predictor looks
stale) rather than on every model run.

Usage: python data/pull_cz_trade_balance.py
"""
from __future__ import annotations
import tempfile
from pathlib import Path

import duckdb
import requests

VZOOM_URL = "https://data.csu.gov.cz/opendata/sady/VZOOM/distribuce/csv"
OUT = Path(__file__).parent / "cz_trade_balance.csv"


def main():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        print(f"downloading VZOOM to {tmp_path} ...")
        with requests.get(VZOOM_URL, stream=True, timeout=300) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=1 << 20):
                tmp.write(chunk)

    try:
        con = duckdb.connect()
        df = con.sql(f"""
            SELECT "CasM" as ym, Hodnota FROM read_csv_auto('{tmp_path.as_posix()}')
            WHERE Ukazatel = 'Bilance (v mil. Kč)' AND "Země" = 'Svět celkem'
              AND "Očištění" = 'Bez očištění' AND "Komodity SITC" = 'Celkem'
              AND "Typ ceny" = 'Běžné ceny' AND "CZCPA" = 'Celkem'
            ORDER BY ym
        """).df()
        df.to_csv(OUT, index=False)
        print(f"wrote {len(df)} rows -> {OUT}  ({df['ym'].min()}..{df['ym'].max()})")
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
