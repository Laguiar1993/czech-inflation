"""Build data/release_calendar_cz_cpi.csv (TIMING_SPEC_v25 T1).

One row per target month with the FIRST release (regular CPI before 2025-01,
flash estimate from 2025-01) and the DETAILED release (the full CPI report
that carries divisions, weights and the CNB analytical breakdown), each with
a source tag:

  bbg_eco_release_dt  Bloomberg CZCPMOM release events already stored in
                      data/czcpmom_survey_history_extended.csv (first release)
                      and data/czcpmom_survey_history.csv (detailed release in
                      the flash era; identical to the first release before it)
  czso_release_page   the "Publication Date" / "Next News Release" lines of
                      csu.gov.cz release pages, typed into MANUAL below; they
                      override a Bloomberg date when the two disagree
  manual_next_release future dates typed from the latest CZSO release page

Operator step (RUNBOOK): after each detailed release, open its CZSO page,
copy the two "Next News Release" dates into MANUAL, rerun this script, and
commit the CSV. Nothing in the model infers a release date from the day of
the month any more.

Usage: python tools/build_release_calendar.py
"""
from __future__ import annotations
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "release_calendar_cz_cpi.csv")

# target_month -> (first_release_dt, detail_release_dt), from CZSO pages.
# None = not asserted by the page. Keep the page URL in the comment.
MANUAL = {
    # https://csu.gov.cz/rychle-informace/consumer-price-indices-inflation-january-2026
    "2026-01": (None, "2026-02-13"),
    # .../consumer-price-indices-inflation-june-2026  (published 10.07.2026;
    # next: flash 5 August 2026, inflation 11 August 2026)
    "2026-06": (None, "2026-07-10"),
    # .../flash-estimate-of-cpi-july-2026 (05.08.2026) and
    # .../consumer-price-indices-inflation-july-2026 (11.08.2026; next: flash
    # 4 September 2026, inflation 10 September 2026)
    "2026-07": ("2026-08-05", "2026-08-11"),
    # .../flash-estimate-of-cpi-august-2026 (04.09.2026); detail per the
    # July page's "Next News Release"
    "2026-08": ("2026-09-04", "2026-09-10"),
}
MANUAL_SOURCE = {"2026-08": ("czso_release_page", "manual_next_release")}
FLASH_ERA_START = pd.Period("2025-01", "M")


def main() -> pd.DataFrame:
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv"))
    ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext["first"] = pd.to_datetime(ext["release_dt"], format="mixed").dt.normalize()
    reg = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history.csv"))
    reg["p"] = pd.to_datetime(reg["target_month"]).dt.to_period("M")
    reg["detail"] = pd.to_datetime(reg["release_dt"].astype("Int64").astype(str),
                                   format="%Y%m%d", errors="coerce").dt.normalize()

    cal = ext.set_index("p")[["first"]].join(reg.set_index("p")[["detail"]], how="outer").sort_index()
    cal["first_source"] = "bbg_eco_release_dt"
    cal["detail_source"] = "bbg_eco_release_dt"
    # before the flash era the first release IS the detailed release
    pre = cal.index < FLASH_ERA_START
    cal.loc[pre, "detail"] = cal.loc[pre, "detail"].fillna(cal.loc[pre, "first"])
    mism = cal[pre & cal["detail"].notna() & (cal["detail"] != cal["first"])]
    if len(mism):
        print("pre-2025 months where the two Bloomberg tables disagree (extended table wins):")
        print(mism[["first", "detail"]].to_string())
        cal.loc[mism.index, "detail"] = cal.loc[mism.index, "first"]
    cal["first_kind"] = ["flash" if p >= FLASH_ERA_START else "regular" for p in cal.index]

    for ym, (f, d) in MANUAL.items():
        p = pd.Period(ym, "M")
        if p not in cal.index:
            cal.loc[p] = pd.Series(dtype=object)
        fs, ds = MANUAL_SOURCE.get(ym, ("czso_release_page", "czso_release_page"))
        for col, val, src_col, src in (("first", f, "first_source", fs), ("detail", d, "detail_source", ds)):
            if val is None:
                continue
            new = pd.Timestamp(val)
            old = cal.loc[p, col]
            if pd.notna(old) and old != new:
                print(f"{ym} {col}: Bloomberg {old.date()} vs CZSO {new.date()} -> CZSO wins")
            cal.loc[p, col] = new
            cal.loc[p, src_col] = src
        cal.loc[p, "first_kind"] = "flash" if p >= FLASH_ERA_START else "regular"
    cal = cal.sort_index()

    out = pd.DataFrame({
        "target_month": [str(p) for p in cal.index],
        "first_release_dt": cal["first"].dt.strftime("%Y-%m-%d"),
        "first_release_kind": cal["first_kind"],
        "first_release_source": cal["first_source"],
        "detail_release_dt": cal["detail"].dt.strftime("%Y-%m-%d"),
        "detail_release_source": cal["detail_source"],
    })
    out.to_csv(OUT, index=False)
    print(f"wrote {OUT}: {len(out)} months {out.target_month.iloc[0]}..{out.target_month.iloc[-1]}; "
          f"missing detail dates: {int(out.detail_release_dt.isna().sum())}, "
          f"missing first dates: {int(out.first_release_dt.isna().sum())}")
    flash = out[out.first_release_kind == "flash"]
    print("flash era rows:")
    print(flash.to_string(index=False))
    return out


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
