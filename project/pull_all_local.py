"""
pull_all_local.py — run this on YOUR machine (needs open internet).
Dumps every raw input into ./czech_raw/, which you then zip and upload to the chat.

Windows PowerShell:
    cd "C:\\Users\\luis_\\OneDrive\\Ambiente de Trabalho\\Czech"
    $env:CNB_ARAD_KEY = "<your ARAD key>"
    pip install requests pandas
    python pull_all_local.py
    Compress-Archive -Path czech_raw -DestinationPath czech_raw.zip -Force
Then upload czech_raw.zip here.

What it pulls (each saved raw, untouched — I do the parsing):
  1. CZSO weekly fuels        (CENPHMT DataStat CSV, legacy fallback)
  2. CZSO heating oil         (CEN0201F)
  3. CZSO CPI dataset 010063  (metadata JSON + CSV distribution)
  4. CZSO CPI-COICOP 010137   (metadata JSON + CSV distribution)
  5. CNB FX monthly averages  (USD + EUR, 2004->now, JSON)
  6. Brent daily              (FRED public csv, no key)
  7. Eurostat: CZ PPI, CZ+DE food HICP, CZ ESI (SDMX JSON)
  8. CNB ARAD: dataset/indicator discovery dump + any indicators you list in
     ARAD_INDICATORS below (fill after browsing cnb.cz/arad/#/en/home)

If any single pull fails it prints the error and CONTINUES — upload whatever
lands in the folder and report the failures back.
"""
import json
import os
import sys
import traceback

import requests

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "czech_raw")
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "czk-cpi-nowcast/0.2 (research pull)"}

# Fill these after browsing the ARAD UI (inflation dataset -> indicator codes).
# Leave empty on first run — the discovery dump below helps find them.
ARAD_INDICATORS = {
    # "cpi_core_mm": "PUT_ID_HERE",
    # "cpi_food_mm": "PUT_ID_HERE",
    # "cpi_admin_mm": "PUT_ID_HERE",
    # "cpi_fuel_mm": "PUT_ID_HERE",
}

RESULTS = []


def save(name: str, content: bytes):
    p = os.path.join(OUT, name)
    with open(p, "wb") as fh:
        fh.write(content)
    print(f"  OK  {name}  ({len(content):,} bytes)")


def step(label):
    def deco(fn):
        def wrapped():
            print(f"[{label}]")
            try:
                fn()
                RESULTS.append((label, "OK"))
            except Exception as e:
                traceback.print_exc(limit=1)
                RESULTS.append((label, f"FAIL: {e}"))
        return wrapped
    return deco


@step("1. CZSO weekly fuels")
def pull_fuels():
    for url, name in [
        ("https://data.csu.gov.cz/opendata/sady/CENPHMT/distribuce/csv", "fuels_weekly_CENPHMT.csv"),
        ("https://vdb.czso.cz/pll/eweb/cenyphm.data", "fuels_weekly_legacy.csv"),
        ("https://data.csu.gov.cz/opendata/sady/CENPHMT/schema/csv", "fuels_weekly_schema.json"),
    ]:
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            save(name, r.content)
        except Exception as e:
            print(f"  skip {name}: {e}")


@step("2. CZSO heating oil")
def pull_heating():
    r = requests.get("https://data.csu.gov.cz/opendata/sady/CEN0201F/distribuce/csv",
                     headers=UA, timeout=60)
    r.raise_for_status()
    save("heating_oil_CEN0201F.csv", r.content)


@step("3-4. CZSO CPI datasets 010063 + 010137")
def pull_cpi():
    for ds in ("010063", "010137"):
        meta = requests.get("https://vdb.czso.cz/pll/eweb/package_show",
                            params={"id": ds}, headers=UA, timeout=60).json()
        save(f"czso_{ds}_meta.json", json.dumps(meta, ensure_ascii=False).encode())
        res = meta.get("result", {}).get("resources", [])
        csvs = [x for x in res if str(x.get("format", "")).upper() == "CSV"]
        for i, c in enumerate(csvs[:3]):
            r = requests.get(c["url"], headers=UA, timeout=300)
            r.raise_for_status()
            save(f"czso_{ds}_{i}.csv", r.content)


@step("5. CNB FX monthly averages")
def pull_fx():
    r = requests.get("https://api.cnb.cz/cnbapi/exrates/monthly-averages",
                     params={"yearMonthFrom": "2004-01", "yearMonthTo": "2026-08",
                             "lang": "EN"}, headers=UA, timeout=60)
    r.raise_for_status()
    save("cnb_fx_monthly.json", r.content)


@step("6. Brent daily (FRED public csv)")
def pull_brent():
    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU",
                     headers=UA, timeout=60)
    r.raise_for_status()
    save("brent_daily_fred.csv", r.content)


@step("7. Eurostat SDMX")
def pull_eurostat():
    base = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
    jobs = {
        "eurostat_ppi_cz.json": ("sts_inppd_m", {"nace_r2": "B-E36", "geo": "CZ", "unit": "I21"}),
        "eurostat_hicp_food_cz.json": ("prc_hicp_midx", {"coicop": "CP01", "geo": "CZ", "unit": "I15"}),
        "eurostat_hicp_food_de.json": ("prc_hicp_midx", {"coicop": "CP01", "geo": "DE", "unit": "I15"}),
        "eurostat_hicp_all_cz.json": ("prc_hicp_midx", {"coicop": "CP00", "geo": "CZ", "unit": "I15"}),
        "eurostat_esi_cz.json": ("ei_bssi_m_r2", {"indic": "BS-ESI-I", "geo": "CZ"}),
    }
    for name, (ds, filt) in jobs.items():
        params = {"format": "JSON", "lang": "EN", "sinceTimePeriod": "2000-01", **filt}
        r = requests.get(f"{base}/{ds}", params=params, headers=UA, timeout=120)
        if r.ok:
            save(name, r.content)
        else:
            print(f"  skip {name}: HTTP {r.status_code} — {r.text[:200]}")


@step("8. CNB ARAD")
def pull_arad():
    key = os.environ.get("CNB_ARAD_KEY")
    if not key:
        raise ValueError("set CNB_ARAD_KEY env var first")
    H = {"Authorization": f"Bearer {key}", **UA}
    base = "https://www.cnb.cz/arad/api/v1"
    # discovery: try common listing endpoints; save whatever answers
    for ep, name in [("/sets", "arad_sets.json"),
                     ("/datasets", "arad_datasets.json"),
                     ("/indicators", "arad_indicators_all.json")]:
        try:
            r = requests.get(base + ep, headers=H, timeout=60)
            if r.ok:
                save(name, r.content)
            else:
                print(f"  discovery {ep}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  discovery {ep}: {e}")
    for label, iid in ARAD_INDICATORS.items():
        r = requests.get(f"{base}/indicators/{iid}/data", headers=H, timeout=60)
        if r.ok:
            save(f"arad_{label}_{iid}.json", r.content)
        else:
            print(f"  {label} ({iid}): HTTP {r.status_code} — {r.text[:200]}")


if __name__ == "__main__":
    for fn in (pull_fuels, pull_heating, pull_cpi, pull_fx, pull_brent,
               pull_eurostat, pull_arad):
        fn()
    print("\n=== summary ===")
    for label, status in RESULTS:
        print(f"{label:40s} {status}")
    print(f"\nAll files in: {OUT}\nZip that folder and upload it to the chat.")
    sys.exit(0)
