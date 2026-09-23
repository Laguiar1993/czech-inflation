"""
Phase 2 — Bloomberg adapter. Same output schema as data/fetchers.py so models
don't change when you flip the source. Follows the em-macro-forecaster skill's
`bopen()` context-manager + pdblp.bdh() pattern with incremental parquet cache.

VERIFY every ticker on your terminal before trusting it (SECF <GO> / ECST CZ).
Candidate economic-release tickers (standard Bloomberg conventions):

  CZCPMOM Index    CPI m/m %                       (release ~10th, 09:00 CET)
  CZCPYOY Index    CPI y/y %
  CZCPCYOY Index   CPI ex-food/fuel/admin (CNB core) — confirm code on ECST
  CZPPYOY Index    PPI y/y
  CZIPYOY Index    Industrial production y/y
  CZKEUR Curncy / EURCZK Curncy    FX
  CO1 Comdty       Brent front future
  TZT1 Comdty      TTF gas front (check)
  CKSW2/5 BGN Curncy  CZK IRS (from skill's bloomberg_infrastructure.md)
  PRIB03M Index    3M PRIBOR

For CNB analytical subcomponents (core/food/admin/fuel m/m) Bloomberg coverage
is patchy — keep pulling those from ARAD/CZSO even in Phase 2, and use
Bloomberg for daily market inputs (Brent, FX, gas, agri futures) where its
timeliness genuinely adds value to the intramonth nowcast.
"""
from __future__ import annotations
import contextlib
import os
import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "bbg_cache")

DAILY_TICKERS = {
    "brent": ("CO1 Comdty", "PX_LAST"),
    "eurczk": ("EURCZK Curncy", "PX_LAST"),
    "usdczk": ("USDCZK Curncy", "PX_LAST"),
    "ttf_gas": ("TZT1 Comdty", "PX_LAST"),
    "wheat": ("W 1 Comdty", "PX_LAST"),
}
MONTHLY_TICKERS = {
    "cpi_mm": ("CZCPMOM Index", "PX_LAST"),
    "cpi_yy": ("CZCPYOY Index", "PX_LAST"),
    "ppi_yy": ("CZPPYOY Index", "PX_LAST"),
}


@contextlib.contextmanager
def bopen(port: int = 8194):
    import pdblp
    con = pdblp.BCon(port=port, timeout=10000)
    con.start()
    try:
        yield con
    finally:
        con.stop()


def pull_daily(start: str = "20050101", tickers: dict = DAILY_TICKERS) -> pd.DataFrame:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, "daily.parquet")
    old = pd.read_parquet(cache) if os.path.exists(cache) else None
    fetch_start = (old.index.max().strftime("%Y%m%d") if old is not None else start)
    with bopen() as con:
        raw = con.bdh([t for t, _ in tickers.values()], "PX_LAST",
                      fetch_start, pd.Timestamp.today().strftime("%Y%m%d"))
    raw.columns = raw.columns.droplevel(1)
    inv = {t: k for k, (t, _) in tickers.items()}
    new = raw.rename(columns=inv)
    out = pd.concat([old, new]).loc[lambda d: ~d.index.duplicated(keep="last")].sort_index() \
        if old is not None else new
    out.to_parquet(cache)
    return out


def brent_in_czk(daily: pd.DataFrame) -> pd.Series:
    return (daily["brent"] * daily["usdczk"]).rename("brent_czk")
