"""Weekly SZIF farmgate/processor price signal for the food block
(FOOD_SZIF_SPEC.md).

Numbers: the EU agri-food data portal API -- the Commission's publication of
the weekly reports Czechia files through SZIF (Reg. (EU) 2017/1184 and
2017/1185) -- in EUR at the ECB weekly average rate printed on each SZIF
report. Converted back to CZK with the ECB daily reference rate (mean over
the report week). Verified exact against the SZIF PDFs (spec section 1).

Publication dates: the SZIF listing pages ("Cenovy a informacni servis"),
one date per ISO week and folder, in data/szif_publication_dates.csv. A week
without a recorded date is stamped week end + FALLBACK_LAG_DAYS.

Cached inputs live in data/eu_agrifood/; `refresh()` re-pulls the current and
previous year from the API and the ECB rate (live use).
"""
from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "eu_agrifood")
PUB_PATH = os.path.join(HERE, "data", "szif_publication_dates.csv")
FX_PATH = os.path.join(DATA, "ecb_czk_eur_daily.csv")
API = "https://www.ec.europa.eu/agrifood/api/{ep}/prices?memberStateCodes=CZ&years={years}"
ECB = ("https://data-api.ecb.europa.eu/service/data/EXR/D.CZK.EUR.SP00.A"
       "?format=csvdata&startPeriod=2004-01-01")

# commodity -> (API endpoint, code column, codes kept)   [spec section 2]
SERIES = {
    "pigs": ("pigmeat", "pigClass", ["E"]),
    "cattle": ("beef", "productCode", ["AU2", "AR2", "AO2", "DR3", "DO3"]),
    "dairy": ("dairy", "product", ["BUTTER", "EDAM", "EMMENTAL"]),
}
FOLDER = {"pigs": "04", "cattle": "05", "dairy": "01"}   # SZIF listing folders
FALLBACK_LAG_DAYS = 4
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def _price(s: pd.Series) -> pd.Series:
    return (s.astype(str).str.replace("€", "", regex=False)
            .str.replace(",", "", regex=False).astype(float))


def _raw_path(ep: str) -> str:
    return os.path.join(DATA, f"{ep}_CZ.csv")


def load_raw(commodity: str) -> pd.DataFrame:
    """Weekly EUR prices of the commodity's declared codes, one row per
    (product, week): duplicated API rows collapsed, two distinct values for
    one week averaged."""
    ep, key, codes = SERIES[commodity]
    raw = pd.read_csv(_raw_path(ep))
    raw = raw[raw[key].isin(codes)].copy()
    raw["begin"] = pd.to_datetime(raw["beginDate"], format="%d/%m/%Y")
    raw["end"] = pd.to_datetime(raw["endDate"], format="%d/%m/%Y")
    raw["price_eur"] = _price(raw["price"])
    raw = raw.drop_duplicates(subset=[key, "end", "price_eur"])
    g = raw.groupby([key, "begin", "end"], as_index=False)["price_eur"].mean()
    g = g.rename(columns={key: "product"})
    g["commodity"] = commodity
    return g[["commodity", "product", "begin", "end", "price_eur"]]


def load_fx() -> pd.Series:
    fx = pd.read_csv(FX_PATH, parse_dates=["date"]).dropna()
    return pd.Series(fx["czk_per_eur"].values, index=fx["date"]).sort_index()


def _week_rates(fx: pd.Series, begins: pd.Series, ends: pd.Series) -> np.ndarray:
    out = np.empty(len(begins))
    for i, (b, e) in enumerate(zip(begins, ends)):
        w = fx[(fx.index >= b) & (fx.index <= e)]
        if len(w):
            out[i] = w.mean()
        else:  # no ECB fixing in the week (never observed); last available
            prev = fx[fx.index < b]
            out[i] = prev.iloc[-1] if len(prev) else np.nan
    return out


def load_pubdates() -> pd.DataFrame:
    """Recorded SZIF publication dates: folder, iso_year, iso_week, published."""
    if not os.path.exists(PUB_PATH):
        return pd.DataFrame(columns=["folder", "iso_year", "iso_week", "published"])
    p = pd.read_csv(PUB_PATH, dtype={"folder": str})
    p["published"] = pd.to_datetime(p["published"]).dt.normalize()
    # one report per folder-week: keep the earliest recorded date (a later
    # duplicate would be a re-upload; the first is when it became public)
    p = p.sort_values("published").drop_duplicates(["folder", "iso_year", "iso_week"])
    return p[["folder", "iso_year", "iso_week", "published"]]


def load_weekly_czk() -> pd.DataFrame:
    """Long weekly panel: commodity, product, begin, end, month (Period by the
    ISO week's Thursday), price_czk, published (Timestamp, 00:00 of the
    publication day), pub_recorded (bool)."""
    fx = load_fx()
    pub = load_pubdates()
    frames = []
    for c in SERIES:
        d = load_raw(c)
        d["rate"] = _week_rates(fx, d["begin"], d["end"])
        d["price_czk"] = d["price_eur"] * d["rate"]
        iso = d["end"].dt.isocalendar()
        d["iso_year"], d["iso_week"] = iso["year"].astype(int), iso["week"].astype(int)
        d["month"] = (d["end"] - pd.Timedelta(days=3)).dt.to_period("M")
        pf = pub[pub["folder"] == FOLDER[c]]
        d = d.merge(pf[["iso_year", "iso_week", "published"]], on=["iso_year", "iso_week"], how="left")
        d["pub_recorded"] = d["published"].notna()
        d["published"] = d["published"].fillna(d["end"] + pd.Timedelta(days=FALLBACK_LAG_DAYS))
        frames.append(d)
    w = pd.concat(frames, ignore_index=True)
    w = w[np.isfinite(w["price_czk"]) & (w["price_czk"] > 0)]
    return w.sort_values(["commodity", "product", "end"]).reset_index(drop=True)


def month_signal(weekly: pd.DataFrame, clock: pd.Series):
    """`szif_mm` per month for a clock (Series: Period -> as_of Timestamp).
    Returns (signal Series, diagnostics DataFrame with n_weeks_used,
    n_weeks_month, n_commodities). Spec section 3."""
    w = weekly.copy()
    w["logp"] = np.log(w["price_czk"])
    sig, diag = {}, {}
    for m, as_of in clock.items():
        if pd.isna(as_of):
            continue
        cutoff = pd.Timestamp(as_of).normalize()
        cur_all = w[w["month"] == m]
        cur = cur_all[cur_all["published"] <= cutoff]
        prev = w[(w["month"] == m - 1) & (w["published"] <= cutoff)]
        if cur.empty or prev.empty:
            sig[m] = np.nan
            diag[m] = (int(cur["end"].nunique()), int(cur_all["end"].nunique()), 0)
            continue
        mc = cur.groupby(["commodity", "product"])["logp"].mean()
        mp = prev.groupby(["commodity", "product"])["logp"].mean()
        d = (100.0 * (mc - mp)).dropna()
        if d.empty:
            sig[m] = np.nan
            diag[m] = (int(cur["end"].nunique()), int(cur_all["end"].nunique()), 0)
            continue
        by_c = d.groupby(level="commodity").mean()
        sig[m] = float(by_c.mean())
        diag[m] = (int(cur["end"].nunique()), int(cur_all["end"].nunique()), int(len(by_c)))
    s = pd.Series(sig, name="szif_mm")
    s.index = pd.PeriodIndex(s.index, freq="M")
    dg = pd.DataFrame(diag, index=["n_weeks_used", "n_weeks_month", "n_commodities"]).T
    dg.index = pd.PeriodIndex(dg.index, freq="M")
    return s.sort_index(), dg.sort_index()


def refresh(years=None) -> None:
    """Live use: re-pull the given years (default current and previous) from
    the API into the cached CSVs and refresh the ECB rate file."""
    import io
    import requests
    today = dt.date.today()
    years = years or [today.year - 1, today.year]
    ys = ",".join(str(y) for y in years)
    for ep in {v[0] for v in SERIES.values()}:
        r = requests.get(API.format(ep=ep, years=ys), headers=UA, timeout=180)
        r.raise_for_status()
        new = pd.DataFrame(r.json())
        path = _raw_path(ep)
        old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
        if len(old):
            end_year = pd.to_datetime(old["endDate"], format="%d/%m/%Y").dt.year
            old = old[~end_year.isin(years)]
        pd.concat([old, new], ignore_index=True).to_csv(path, index=False)
    r = requests.get(ECB, headers={"User-Agent": "Mozilla/5.0"}, timeout=180)
    r.raise_for_status()
    fx = pd.read_csv(io.BytesIO(r.content))[["TIME_PERIOD", "OBS_VALUE"]]
    fx.columns = ["date", "czk_per_eur"]
    fx.to_csv(FX_PATH, index=False)
