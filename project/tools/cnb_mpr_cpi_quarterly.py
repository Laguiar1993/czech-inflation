"""CNB Monetary Policy Report vintages: the QUARTERLY headline CPI y/y path
(actuals and forecasts) from each report's macro-indicator spreadsheet,
2022 winter .. latest. The spreadsheet lays out 9 years x 4 quarters; the
cnb.mpr_vintages puller stored the first quarterly column of each year as
if it were the annual value (found 8 Sep 2026), so this file is the
benchmark source for the path product, not that table.
Writes data/cnb_mpr_cpi_quarterly.csv: report_date, season, vintage_year,
quarter (YYYYQn), value, is_forecast, xlsx_url.
Usage: python tools/cnb_mpr_cpi_quarterly.py
"""
import io
import os
import sys

import openpyxl
import pandas as pd
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON_CS = {"winter": "zima", "spring": "jaro", "summer": "leto", "autumn": "podzim"}
UA = {"User-Agent": "Mozilla/5.0"}
# publication dates: CNB board meeting Thursdays (report published the following week) as recorded in cnb.mpr_vintages
# where the puller read them from the page; otherwise the report page date typed here from cnb.cz (verify when adding).
PUB = {("winter", 2022): "2022-02-10", ("spring", 2022): "2022-05-12", ("summer", 2022): "2022-08-11", ("autumn", 2022): "2022-11-10",
       ("winter", 2023): "2023-02-09", ("spring", 2023): "2023-05-11", ("summer", 2023): "2023-08-10", ("autumn", 2023): "2023-11-09",
       ("winter", 2024): "2024-02-15", ("spring", 2024): "2024-05-09", ("summer", 2024): "2024-08-08", ("autumn", 2024): "2024-11-14",
       ("winter", 2025): "2025-02-13", ("spring", 2025): "2025-05-15", ("summer", 2025): "2025-08-14", ("autumn", 2025): "2025-11-13",
       ("winter", 2026): "2026-02-12", ("spring", 2026): "2026-05-14", ("summer", 2026): "2026-08-13"}
# publication dates 2024-2026 read from the report pages on cnb.cz on 8 Sep 2026 (the 2025-26 entries had been placeholders on the 15th);
# 2022-2023 as first entered, confirmed against the report pages the same day.
# Data cut-off dates stated on the same pages (the forecast's information set ends here, about three weeks before publication):
CUTOFF = {("winter", 2022): "2022-01-21", ("spring", 2022): "2022-04-22", ("summer", 2022): "2022-07-22", ("autumn", 2022): "2022-10-21",
          ("winter", 2023): "2023-01-20", ("spring", 2023): "2023-04-21", ("summer", 2023): "2023-07-21", ("autumn", 2023): "2023-10-20",
          ("winter", 2024): "2024-01-26", ("spring", 2024): "2024-04-26", ("summer", 2024): "2024-07-26", ("autumn", 2024): "2024-10-31",
          ("winter", 2025): "2025-01-24", ("spring", 2025): "2025-04-25", ("summer", 2025): "2025-07-25", ("autumn", 2025): "2025-10-24",
          ("winter", 2026): "2026-01-23", ("spring", 2026): "2026-04-24", ("summer", 2026): "2026-07-24"}


def url(season, y):
    cs = SEASON_CS[season]
    return (f"https://www.cnb.cz/export/sites/cnb/cs/menova-politika/.galleries/zpravy_o_menove_politice/{y}/{cs}_{y}/download/zomp_{y}_{cs}_makroindikatory.xlsx")


def parse(content: bytes):
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb["English version"] if "English version" in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr = None
    for i, r in enumerate(rows):
        yrs = [v for v in r if isinstance(v, (int, float)) and 2000 <= v <= 2040]
        if len(yrs) >= 5:
            hdr = i; break
    if hdr is None:
        raise ValueError("no year header")
    years = rows[hdr]
    # forward-fill the year across its quarterly columns; the quarter number is the position within the year block
    colmap = {}
    cur, q = None, 0
    for j, v in enumerate(years):
        if isinstance(v, (int, float)) and 2000 <= v <= 2040:
            cur, q = int(v), 1
        elif cur is not None and j > 1:
            q += 1
        if cur is not None and 1 <= q <= 4 and j > 1:
            colmap[j] = (cur, q)
    # quarter header row, if present, to confirm the block layout
    target = None
    for r in rows[hdr + 1:]:
        lab = " ".join(str(v) for v in r[:2] if v is not None).lower()
        if "consumer price index" in lab and "y-o-y" in lab:
            target = r; break
    if target is None:
        for r in rows[hdr + 1:]:
            lab = " ".join(str(v) for v in r[:2] if v is not None).lower()
            if lab.startswith("consumer price index") or "index spotřebitelských cen" in lab:
                target = r; break
    if target is None:
        raise ValueError("no CPI row")
    out = {}
    for j, (yy, qq) in colmap.items():
        v = target[j] if j < len(target) else None
        if isinstance(v, (int, float)):
            out[f"{yy}Q{qq}"] = float(v)
    label = " ".join(str(v) for v in target[:2] if v is not None)
    return out, label


def main():
    rows = []
    for (season, y), d in sorted(PUB.items(), key=lambda kv: kv[1]):
        u = url(season, y)
        r = requests.get(u, headers=UA, timeout=60)
        if r.status_code != 200:
            print("missing", season, y, r.status_code); continue
        vals, label = parse(r.content)
        d = pd.Timestamp(d)
        for qp, v in vals.items():
            per = pd.Period(qp, freq="Q")
            q_end = per.asfreq("M", "e").to_timestamp(how="end")
            rows.append({"report_date": d.date(), "cutoff_date": CUTOFF.get((season, y)), "season": season, "vintage_year": y, "quarter": qp, "value": v,
                         "is_forecast": bool(q_end > d + pd.Timedelta(days=45)), "row_label": label, "xlsx_url": u})
        print(season, y, d.date(), label[:60], "| quarters", len(vals), "| e.g.", {k: vals[k] for k in list(vals)[-6:]})
    df = pd.DataFrame(rows)
    out = os.path.join(HERE, "data", "cnb_mpr_cpi_quarterly.csv")
    df.to_csv(out, index=False)
    print("written", out, len(df), "rows")


if __name__ == "__main__":
    main()
