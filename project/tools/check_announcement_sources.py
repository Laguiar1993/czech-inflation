"""Re-verification helper (ANNOUNCEMENT_PROTOCOL.md, section "Re-verification
routine"): fetch every source page in data/announcement_sources.csv, hash its
visible text, compare with the previous check and append one row per source
to data/announcement_source_checks.csv. A changed hash is a prompt for a
human read of the page, never an automatic ledger change; a fetch failure is
recorded as UNVERIFIED, never as "unchanged".

Usage:
  python tools/check_announcement_sources.py            # all sources
  python tools/check_announcement_sources.py --cadence every_call
  python tools/check_announcement_sources.py --note "pre-flash call Sep-2026"
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from datetime import datetime, timezone

import pandas as pd
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(HERE, "data", "announcement_sources.csv")
CHECKS = os.path.join(HERE, "data", "announcement_source_checks.csv")
UA = {"User-Agent": "Mozilla/5.0 (compatible; czk-cpi-nowcast announcement check)"}
_TAG = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I)
_HTML = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def visible_text(html: str) -> str:
    t = _TAG.sub(" ", html)
    t = _HTML.sub(" ", t)
    t = re.sub(r"&[a-z#0-9]+;", " ", t)
    return _WS.sub(" ", t).strip()


def check(url: str, timeout: int = 40):
    try:
        r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
    except Exception as e:  # noqa: BLE001
        return {"status": f"ERR {type(e).__name__}", "sha256": "", "last_modified": "", "etag": "", "n_chars": 0}
    txt = visible_text(r.text) if r.status_code == 200 else ""
    return {"status": str(r.status_code), "sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest() if txt else "",
            "last_modified": r.headers.get("Last-Modified", ""), "etag": r.headers.get("ETag", ""), "n_chars": len(txt)}


def last_hashes() -> dict:
    if not os.path.exists(CHECKS):
        return {}
    prev = pd.read_csv(CHECKS, dtype=str).fillna("")
    prev = prev[prev["sha256"] != ""]
    return prev.sort_values("check_ts").groupby("source_id")["sha256"].last().to_dict()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cadence", default=None, help="only sources with this cadence (every_call, monthly, quarterly)")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    src = pd.read_csv(SOURCES)
    if a.cadence:
        src = src[src["cadence"] == a.cadence]
    prev = last_hashes()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, changed, unverified = [], [], []
    for r in src.itertuples():
        res = check(r.url)
        if not res["sha256"]:
            verdict = "UNVERIFIED"
        elif res["n_chars"] < 200:
            verdict = "THIN"        # JS-rendered shell: the hash proves nothing, check by hand
        elif prev.get(r.source_id) not in (None, res["sha256"]):
            verdict = "CHANGED"
        else:
            verdict = "FIRST" if r.source_id not in prev else "UNCHANGED"
        if verdict == "CHANGED":
            changed.append(r.source_id)
        if verdict in ("UNVERIFIED", "THIN"):
            unverified.append(f"{r.source_id} ({verdict} {res['status']})")
        rows.append({"check_ts": now, "source_id": r.source_id, "url": r.url, "cadence": r.cadence, "verdict": verdict,
                     "status": res["status"], "sha256": res["sha256"], "last_modified": res["last_modified"],
                     "etag": res["etag"], "n_chars": res["n_chars"], "note": a.note})
        print(f"{verdict:10s} {r.source_id:28s} {res['status']:>6s} {res['n_chars']:>7d} chars  {res['last_modified']}")
    out = pd.DataFrame(rows)
    out.to_csv(CHECKS, mode="a", header=not os.path.exists(CHECKS), index=False)
    print(f"\n{len(rows)} sources checked at {now}; CHANGED: {changed or 'none'}; UNVERIFIED: {unverified or 'none'}")
    print("Changed pages need a human read; record any new event as a NEW ledger row (extension / amendment / void), never an edit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
