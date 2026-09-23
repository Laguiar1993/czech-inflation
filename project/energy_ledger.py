"""energy_ledger.py -- event-level energy-policy ledger (Codex review sec. 6).

INFRASTRUCTURE + DIAGNOSTIC ONLY in this version: the ledger records dated
policy events (start/expiry/extension per policy_id) with THREE timestamps
each -- source publication, CPI-treatment knowledge, effective month -- and
an attribution diagnostic mapping months to active events. It deliberately
carries NO fitted magnitudes and does NOT feed the forecast yet: wiring
bottom-up contributions requires the levels-first arithmetic and per-item
weights the review specifies, and doing that against known history would be
another reconstruction. The first forecast-feeding entries will be the
prospective Nov-2026 rows.

Design rules encoded (review sec. 6):
- separate policy IDs; amendments are EVENTS, never overwrites;
- treatment_known_date is distinct from source_pub_date (the saving tariff's
  CPI treatment was only published 2022-11-01, with the October release --
  an end-October forecast could not have known it);
- levels-first arithmetic reminder lives in the CSV notes (-16.9% reverses
  as +20.3%, and Jan-2023's +30.9% is caps+POZE+tariff interacting, not one
  inverse);
- replace-vs-incremental vs the seasonal baseline must be declared per
  entry before any magnitude is wired.

Usage: python energy_ledger.py   (prints the attribution diagnostic)
"""
from __future__ import annotations
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


_LEDGER = None  # module cache, mirroring cz_struct._announcements()


def load_ledger() -> pd.DataFrame:
    global _LEDGER
    if _LEDGER is None:
        df = pd.read_csv(os.path.join(HERE, "data", "energy_policy_ledger.csv"))
        df["effective_month"] = pd.PeriodIndex(df["effective_month"], freq="M")
        for c in ["source_pub_date", "treatment_known_date"]:
            df[c] = pd.to_datetime(df[c], errors="coerce")
        _LEDGER = df
    return _LEDGER


def active_events(month: pd.Period, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Events whose effective month is `month`, restricted (if as_of given)
    to those whose SOURCE was published AND whose CPI TREATMENT was knowable
    by as_of -- BOTH clocks, fail-closed on a missing date (Codex R4: the
    treatment-only test admitted a source published after the cutoff).
    Still an event LISTING, not an active-policy-state calculator."""
    df = load_ledger()
    hit = df[df["effective_month"] == month]
    if as_of is not None:
        hit = hit[hit["treatment_known_date"].notna()
                  & (hit["treatment_known_date"] <= as_of)
                  & hit["source_pub_date"].notna()
                  & (hit["source_pub_date"] <= as_of)]
    return hit


def attribution_table() -> pd.DataFrame:
    """Month -> active policy events; the diagnostic that turns the three
    worst forecast months into named accounting entries."""
    df = load_ledger()
    rows = []
    for m, g in df.groupby("effective_month"):
        rows.append({"month": m,
                     "events": "; ".join(f"{r.policy_id}:{r.event}" for r in g.itertuples()),
                     "treatment_knowable_by": g["treatment_known_date"].max()})
    return pd.DataFrame(rows).set_index("month").sort_index()


if __name__ == "__main__":
    t = attribution_table()
    print(t.to_string())
    print("\nThe three months carrying 82.8% of squared forecast error:")
    for m in [pd.Period("2022-01", "M"), pd.Period("2022-10", "M"), pd.Period("2023-01", "M")]:
        ev = active_events(m)
        print(f"  {m}: {len(ev)} ledger events -> "
              + "; ".join(f"{r.policy_id}:{r.event}" for r in ev.itertuples()))
