"""capture_survey.py -- pre-release consensus snapshot with hash+timestamp.

Closes the review item "preserve the exact survey snapshot": every future
score should compare against a consensus captured BEFORE the release, not a
settled value pulled afterwards (the documented 2025+ contamination mode).

Run on release-eve (or any time before the flash). Tries Bloomberg
(CZCPMOM Index BN_SURVEY_MEDIAN/AVERAGE via pdblp; terminal required);
falls back to manual entry via --median/--mean. Never overwrites: one JSON
per capture under data/survey_snapshots/, content-hashed.

Usage:
  python capture_survey.py --target 2026-09
  python capture_survey.py --target 2026-09 --median 0.2 --mean 0.21  (manual)
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPDIR = os.path.join(HERE, "data", "survey_snapshots")


def fetch_bbg():
    # bopen() context manager guarantees con.stop() (repo BBG convention;
    # /code-review: the hand-rolled BCon leaked a session per capture)
    from data.bloomberg_adapter import bopen
    with bopen() as con:
        ref = con.ref("CZCPMOM Index", ["BN_SURVEY_MEDIAN", "BN_SURVEY_AVERAGE",
                                        "BN_SURVEY_HIGH", "BN_SURVEY_LOW",
                                        "BN_SURVEY_NUMBER_OBSERVATIONS",
                                        "ECO_RELEASE_DT"])
    vals = {r["field"]: r["value"] for _, r in ref.iterrows()}
    return {"median": vals.get("BN_SURVEY_MEDIAN"),
            "mean": vals.get("BN_SURVEY_AVERAGE"),
            "high": vals.get("BN_SURVEY_HIGH"),
            "low": vals.get("BN_SURVEY_LOW"),
            "n_respondents": vals.get("BN_SURVEY_NUMBER_OBSERVATIONS"),
            "eco_release_dt": str(vals.get("ECO_RELEASE_DT")),
            "source": "bloomberg_ref_snapshot"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="YYYY-MM target month")
    ap.add_argument("--median", type=float, default=None)
    ap.add_argument("--mean", type=float, default=None)
    ap.add_argument("--release-dt", default=None,
                    help="YYYY-MM-DD scheduled release the survey refers to "
                         "(REQUIRED for manual entry; the same target check "
                         "applies -- /code-review: the manual path previously "
                         "always aborted at the ECO_RELEASE_DT guard)")
    ap.add_argument("--release-type", choices=["flash", "final"], default=None,
                    help="which print the scheduled release is. If omitted it "
                         "is INFERRED from the release day-of-month (<=6 -> "
                         "flash) and the snapshot records that provenance -- "
                         "the inference is a heuristic, not knowledge (Codex "
                         "round-2 qualification). Pass it explicitly whenever "
                         "you know (CZSO calendar).")
    a = ap.parse_args()

    if a.median is not None:
        if a.release_dt is None:
            raise SystemExit("manual entry requires --release-dt (fail-closed: "
                             "an undated snapshot cannot be target-verified)")
        if a.release_type is None:
            # v2.4 (Codex R4): the day-of-month inference is UNSAFE -- the
            # 2025-12, 2026-03 and 2026-06 flashes landed on day 7 -- so a
            # manual entry must state the stage explicitly.
            raise SystemExit("manual entry requires --release-type flash|final "
                             "(fail-closed: day-7 flashes exist, e.g. 2026-01-07 "
                             "and 2026-04-07, so the day-of-month rule cannot "
                             "be trusted)")
        snap = {"median": a.median, "mean": a.mean, "source": "manual_entry",
                "eco_release_dt": a.release_dt}
    else:
        snap = fetch_bbg()
    # reject non-finite survey values (argparse accepts 'nan'/'inf' as floats)
    for k in ("median", "mean"):
        v = snap.get(k)
        if v is not None and not (isinstance(v, (int, float)) and np.isfinite(v)):
            raise SystemExit(f"non-finite survey {k}={v!r}: refusing to write a snapshot")
    if snap.get("median") is None:
        raise SystemExit("no survey median available: refusing to write a snapshot")

    # TARGET VERIFICATION (added after a real mislabeling on 2026-09-06,
    # caught by the user): Bloomberg's survey fields attach to the NEXT
    # scheduled release event, which in the flash+final era may be the
    # PREVIOUS month's final print. Derive the implied target from
    # eco_release_dt and refuse a mismatch instead of trusting the caller.
    rd = pd.Timestamp(str(snap.get("eco_release_dt", "NaT")))
    if pd.isna(rd):
        raise SystemExit("no ECO_RELEASE_DT on the ticker -- cannot verify "
                         "which release this survey refers to; aborting")
    # flash era (2025+): flash for month M lands ~day 1-6 of M+1; the FULL
    # print for M lands ~day 8-14 of M+1. Either way the survey's target
    # month is the month BEFORE the release month -- so the flash/final
    # label does NOT affect target verification. It IS evidence metadata,
    # though, and the day-of-month rule is a heuristic (a delayed flash on
    # day 7 would be mislabelled): prefer the explicit flag, and record
    # provenance either way so scoring can re-derive from the raw date.
    implied_target = (rd.to_period("M") - 1).strftime("%Y-%m")
    inferred = "flash" if rd.day <= 6 else "final"
    if a.release_type is not None:
        release_type, rt_src = a.release_type, "explicit_user_input"
        if a.release_type != inferred:
            print(f"note: explicit --release-type {a.release_type} overrides "
                  f"the day-of-month inference ({inferred} from day {rd.day})")
    else:
        release_type = inferred
        rt_src = ("inferred_from_release_day (UNSAFE: day-7 flashes exist, e.g. "
                  "2026-01-07, 2026-04-07 -- validate against the CZSO calendar)")
        print(f"WARNING: release type '{inferred}' inferred from day {rd.day}; the "
              f"rule is known to mislabel day-7 flashes -- pass --release-type")
    snap["implied_target_month"] = implied_target
    snap["release_type"] = release_type
    snap["release_type_source"] = rt_src
    if implied_target != a.target:
        raise SystemExit(
            f"REFUSED: you asked for target {a.target}, but the ticker's "
            f"next release ({rd.date()}) implies target {implied_target} "
            f"({release_type}). The {a.target} consensus does not exist "
            f"yet -- capture it in the days before ITS release.")

    snap["target_month"] = a.target
    snap["captured_at"] = datetime.now().isoformat(timespec="seconds")
    # write EXACTLY the hashed bytes so `sha256sum <file>` verifies with
    # off-the-shelf tools (/code-review: the old scheme hashed a transient
    # serialization different from the file's bytes -- unverifiable)
    payload = json.dumps(snap, sort_keys=True, indent=1).encode()
    digest = hashlib.sha256(payload).hexdigest()

    os.makedirs(SNAPDIR, exist_ok=True)
    fn = os.path.join(SNAPDIR,
                      f"{a.target}_{snap['captured_at'].replace(':', '')}.json")
    open(fn, "wb").write(payload)
    open(fn + ".sha256", "w").write(digest + "  " + os.path.basename(fn) + "\n")
    print(f"captured consensus for {a.target}: median={snap.get('median')} "
          f"mean={snap.get('mean')} ({snap['source']}, {snap.get('release_type')})")
    print(f"-> {fn}\n   sha256={digest} (sidecar written; file bytes verify)")
    print("Scoring rule: a target month's score uses the LATEST snapshot "
          "captured BEFORE its release; afterwards-captured values are "
          "settled-suspect (documented contamination mode).")


if __name__ == "__main__":
    main()
