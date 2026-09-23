"""
Public-data fetchers (Phase 1). All return tidy pandas objects indexed by
pandas.Period ('M') or Timestamp (weekly/daily) so models are source-agnostic.

Priority order (per em-macro-forecaster skill): free APIs first, Bloomberg later
via data/bloomberg_adapter.py with the SAME output schema.

Run these on your own machine — they need open internet. Every function fails
loudly (no silent NaN-filled frames) so a broken endpoint is visible.
"""
from __future__ import annotations
import io
import os
import requests
import pandas as pd

UA = {"User-Agent": "czk-cpi-nowcast/0.1 (research)"}

# ---------------------------------------------------------------------------
# CZSO — weekly fuel prices (the single most valuable HF input, Cleveland-Fed
# style: weekly pump prices map ~1:1 into CPI item 0722 'fuels & lubricants')
# ---------------------------------------------------------------------------
def fetch_czso_weekly_fuels(url: str | None = None) -> pd.DataFrame:
    """
    Weekly average consumer fuel prices (Natural 95, Diesel; LPG where present),
    CZK/l. CZSO publishes an open-data CSV under
    'Average prices survey of selected products - fuels and oil products'.

    Tries DataStat open-data CSV (dataset CENPHMT) first, then the legacy
    vdb.czso.cz endpoint. NOTE: each weekly value is a MONDAY-observed price
    snapshot (arithmetic avg over ~1,515 stations), not a weekly mean — the
    monthly CPI fuel price approximates the mean of the Mondays in the month.
    Returns DataFrame indexed by observation date, columns ['petrol95','diesel',...].
    Pin exact column names against CZSO_WEEKLY_FUELS_SCHEMA on first pull.
    """
    from config import CZSO_WEEKLY_FUELS_CSV, CZSO_WEEKLY_FUELS_CSV_FALLBACK
    urls = [url] if url else [CZSO_WEEKLY_FUELS_CSV, CZSO_WEEKLY_FUELS_CSV_FALLBACK]
    r = None
    for u in urls:
        try:
            r = requests.get(u, headers=UA, timeout=30)
            r.raise_for_status()
            break
        except Exception:
            r = None
    if r is None:
        raise RuntimeError(f"weekly fuels: all endpoints failed: {urls}")
    raw = pd.read_csv(io.BytesIO(r.content), sep=None, engine="python")
    # CZSO CSVs: columns typically include date ('obdobi'/'datum'), fuel type
    # ('pohonna_hmota'/text), value ('hodnota'). Normalise defensively:
    cols = {c.lower(): c for c in raw.columns}
    date_col = next(c for k, c in cols.items() if "datum" in k or "obdobi" in k or "date" in k)
    val_col = next(c for k, c in cols.items() if "hodnota" in k or "value" in k or "cena" in k)
    type_col = next((c for k, c in cols.items()
                     if "hmota" in k or "druh" in k or "typ" in k or "text" in k), None)
    raw[date_col] = pd.to_datetime(raw[date_col], errors="coerce", dayfirst=True)
    if type_col:
        out = raw.pivot_table(index=date_col, columns=type_col, values=val_col, aggfunc="mean")
    else:
        out = raw.set_index(date_col)[[val_col]]
    out = out.sort_index()
    ren = {}
    for c in out.columns:
        lc = str(c).lower()
        if "95" in lc or "natur" in lc:
            ren[c] = "petrol95"
        elif "naft" in lc or "diesel" in lc:
            ren[c] = "diesel"
        elif "lpg" in lc:
            ren[c] = "lpg"
    return out.rename(columns=ren)


def fetch_czso_table(dataset_id: str) -> pd.DataFrame:
    """CZSO open-data catalogue fetch (package_show -> CSV distribution)."""
    meta = requests.get("https://vdb.czso.cz/pll/eweb/package_show",
                        params={"id": dataset_id}, headers=UA, timeout=30).json()
    resources = meta.get("result", {}).get("resources", [])
    csvs = [r for r in resources if str(r.get("format", "")).upper() == "CSV"]
    if not csvs:
        raise ValueError(f"No CSV distribution for CZSO dataset {dataset_id}")
    return pd.read_csv(csvs[0]["url"], encoding="utf-8")


def czso_cpi_headline_mm(dataset_id: str = "010063") -> pd.Series:
    """
    Headline CPI m/m (%) NSA from CZSO dataset 010063.
    Filter: previous month = 100 index for households total, all-items.
    Column semantics: hodnota=value, casref_do=period end, stapro_kod=measure.
    """
    df = fetch_czso_table(dataset_id)
    dc = next(c for c in df.columns if "casref" in c.lower())
    df[dc] = pd.to_datetime(df[dc], errors="coerce")
    # keep the m/m index measure; exact stapro/typ codes verified on first pull:
    # print(df[['stapro_kod','stapro_txt']].drop_duplicates()) and pin the code.
    mm_mask = df.apply(lambda r: r.astype(str).str.contains("předchoz", case=False).any(), axis=1)
    sub = df[mm_mask]
    s = (sub.groupby(sub[dc].dt.to_period("M"))["hodnota"].mean() - 100.0)
    s.name = "cpi_mm"
    return s

# ---------------------------------------------------------------------------
# Eurostat SDMX 2.1 (no auth) — HICP components, surveys, PPI
# ---------------------------------------------------------------------------
def fetch_eurostat(dataset: str, filters: dict, start: str = "2000-01") -> pd.Series:
    """
    Eurostat REST: /sdmx/2.1/data/{dataset}?format=TSV + dimension filters.
    Uses the JSON API for robustness.
    """
    base = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
    params = {"format": "JSON", "lang": "EN", "sinceTimePeriod": start}
    params.update(filters)
    r = requests.get(f"{base}/{dataset}", params=params, headers=UA, timeout=60)
    r.raise_for_status()
    js = r.json()
    time_idx = js["dimension"]["time"]["category"]["index"]
    inv_time = {v: k for k, v in time_idx.items()}
    vals = {inv_time[int(k)]: v for k, v in js["value"].items()}
    s = pd.Series(vals).sort_index()
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s.astype(float)

# ---------------------------------------------------------------------------
# FRED anchors (Brent, CZK) — needs FRED_API_KEY
# ---------------------------------------------------------------------------
def fetch_fred(series_id: str, api_key: str | None = None) -> pd.Series:
    api_key = api_key or os.environ.get("FRED_API_KEY")
    if not api_key:
        raise ValueError("Set FRED_API_KEY (free at fred.stlouisfed.org)")
    r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                     params={"series_id": series_id, "api_key": api_key,
                             "file_type": "json"}, headers=UA, timeout=30)
    r.raise_for_status()
    obs = r.json()["observations"]
    s = pd.Series({o["date"]: o["value"] for o in obs}).replace(".", None).astype(float)
    s.index = pd.to_datetime(s.index)
    s.name = series_id
    return s

# ---------------------------------------------------------------------------
# CNB — ARAD (API key) and public FX API (no auth)
# ---------------------------------------------------------------------------
def fetch_cnb_arad(indicator_id: str, api_key: str | None = None) -> pd.DataFrame:
    api_key = api_key or os.environ.get("CNB_ARAD_KEY")
    if not api_key:
        raise ValueError("Set CNB_ARAD_KEY (free registration at cnb.cz/arad/)")
    r = requests.get(f"https://www.cnb.cz/arad/api/v1/indicators/{indicator_id}/data",
                     headers={"Authorization": f"Bearer {api_key}", **UA}, timeout=30)
    r.raise_for_status()
    return pd.DataFrame(r.json())


def fetch_cnb_fx_monthly(yyyymm_from: str, yyyymm_to: str, currency: str = "USD") -> pd.Series:
    r = requests.get("https://api.cnb.cz/cnbapi/exrates/monthly-averages",
                     params={"yearMonthFrom": yyyymm_from, "yearMonthTo": yyyymm_to,
                             "lang": "EN"}, headers=UA, timeout=30)
    r.raise_for_status()
    rows = [x for x in r.json().get("rates", []) if x.get("currencyCode") == currency]
    s = pd.Series({x["yearMonth"]: x["rate"] / x.get("amount", 1) for x in rows})
    s.index = pd.PeriodIndex(s.index, freq="M")
    s.name = f"CZK_{currency}"
    return s.sort_index()
