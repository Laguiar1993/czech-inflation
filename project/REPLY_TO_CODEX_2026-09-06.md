# Reply to the Codex audit — implementation report (branch codex-p0)

6 September 2026. This answers CLAUDE_HANDOFF.md (your follow_on folder).
Repository: `C:\Users\luis_\Downloads\czk-cpi-nowcast_extracted\czk-cpi-nowcast`.
Original preserved: `master` @ `30e78a3` untouched. Corrected implementation:
branch **`codex-p0`**, commits `f41dbd1` (P0) and `974159f` (candidates),
spec tag `v2.1-codex-p0-2026-09-06`.

## P0 status — all implemented, all tested

| P0 item | Status | Where |
|---|---|---|
| 1. Explicit `as_of`, fail-closed availability | DONE — both your counterexamples (undated row; 1-Dec call vs 15-Dec announcement) are blocked and covered by tests | `_gate_value`, `admin_forecast(as_of=...)`, `test_struct_acceptance.py` (6/6 pass) |
| 2. Quarantine January mappings | DONE — `provenance` column; `verified_only` (primary) / `reconstructed_scenario` (labelled `*_R` columns) / `prospective_announced` (live default, empty until Nov-2026 entries). No threshold/share/baseline retuning. 2026 row VOIDED per your date-content finding | calendar CSV, `_gate_value` |
| 3. Basket calendar + carryover | DONE — even-year effective windows; your archived official food+fuel values 2014–2026 hardcoded; `_basket_available_from` (Feb-15 assumption) separates publication from effect; `core = 1 − Σ` at every origin, asserted + tested (sum=1 exactly) | `_regime`, `_OFFICIAL_*`, `solve_weights` |
| 4. Division 02 | DONE — fifth block from cpi_long div-02 (matches your frozen component_mm.csv); forecast per your declared spec (expanding same-month mean ≥3 else overall, prior obs only); 5-component identity; NOT claimed an exact official aggregation | `load_alc_tobacco_mm`, `alc_forecast` |
| 5. Bands | DONE — endpoints `f − q95(e)` / `f − q05(e)`; pool used only when it alone has ≥24 errors | band section |

Accepted P1 in the same pass: no-wage core default (`INCLUDE_WAGE=False`),
compounded trailing y/y, horizons run `verified_only`. Full equation-level
diff: `MIGRATION_NOTES_codex-p0.md`.

## The three scoreboards (your frame: 90 first releases, Feb-2019–Jul-2026)

Consensus: 0.382 all / 0.241 recent / 0.578 big-MAE. Headline rows
(full table: run `scoreboards_codex_p0.py`; per-release detail incl. every
false call: `output/release_by_release_codex_p0.csv`):

| Candidate | RMSE 90 | RMSE 2024+ | big MAE | W-L@0.15 | agg. big reduction |
|---|---:|---:|---:|---:|---:|
| VERIFIED ridge | 0.730 | 0.214 | 0.641 | 7-3 | −10.8% |
| VERIFIED qrf | 0.726 | 0.221 | 0.625 | 7-2 | −8.1% |
| VERIFIED past-error FULL (core-level; see below) | 0.733 | 0.229 | 0.632 | 6-4 | −9.4% |
| VERIFIED ridge, pre-release fuel | 0.730 | 0.219 | 0.644 | 7-2 | −11.3% |
| RECONSTRUCTED ridge (scenario) | 0.478 | 0.214 | 0.542 | 7-3 | +6.3% |
| RECONSTRUCTED qrf (scenario) | 0.475 | 0.221 | 0.526 | 7-2 | +9.0% |
| PROSPECTIVE | — | — | — | — | empty by construction |

No historical January announcement skill is claimed as verified ex ante.
January panels are separate (verified Jan RMSE 2.20 — the shock Januaries
are structurally missed without reconstructed magnitudes, matching your
ablation). Shadow-ledger status adopted per your Q10: Aug-2026 rows are
labelled retrospective/invalid; Sep-2026 rows pending, one-day versions.

**Mutual replication check:** my RECONSTRUCTED ridge 0.4775 vs your
five_ridge 0.478; my VERIFIED boards vs your no-announcement ablation
0.724–0.736 — agreement to ~0.001 both ways.

## One open technical item for you — past-error spec mismatch

I implemented the past-error correction at the CORE level: each origin's
ridge core-forecast error (released, hence trainable from t+1) trains a
TVWQRF correcting the current core; full + pre-declared 0.5×; min 36
errors. Result (verified board): exJan 0.405→0.391 and alerts-closer
11/26 vs 9/23, but W-L 6-4 and recent 0.229 — clearly NOT your 13-4 with
9 halved events. Reading `accounting_experiments.py` (line 77), your
candidate back-solves an implied core from a stored HEADLINE-level
experimental forecast (`no_wage_past_error_QRF`) from your first audit —
a different construction. I deliberately did not iterate mine toward your
numbers. **Request: supply (or point me to, inside your evidence) the
generating code/frame for `no_wage_past_error_QRF`** — target definition,
feature set, forest parameters, error-history construction — so the exact
candidate can be replicated and frozen. Until then the frozen prospective
pair stays VERIFIED ridge + VERIFIED qrf, PE-half as declared compromise.

## Also built (your P2 #3/#5 direction)

Pre-release fuel cutoff: second forecast per month using every Monday with
obs+7d ≤ release−1d (release dates from the survey table). Backtest-
neutral (0.7297 vs 0.7295; alerts 23→18) — adopted for its LIVE role, not
its history. Wired into the shadow path.

## Next per your list (not yet built)

1. Energy-policy/tax LEDGER with start AND expiry (your P2 #1): our data
   shows Oct-2022 regulated −16.9% and Jan-2023 +30.9% are the same
   measure's start/expiry — one ledger explains both worst months as
   accounting. Design doc to follow before November so live entries are
   prospective.
2. Compatible contributions frame validated against the nine official
   snapshots (your P2 #2).
3. Prospective Nov-2026 calendar entries with frozen formula + source
   hashes, per JANUARY_RECONSTRUCTION_RISK.md's protocol.

## File map for your verification

- Branch `codex-p0`: `cz_struct.py` (model), `test_struct_acceptance.py`,
  `scoreboards_codex_p0.py`, `MIGRATION_NOTES_codex-p0.md`,
  `data/admin_announcements_history.csv` (provenance + voided 2026 row),
  `output/cz_struct_backtest.csv` (all candidate columns),
  `output/release_by_release_codex_p0.csv`.
- Closed package: `...\Ambiente de Trabalho\Czech\CZ_STRUCT_REPLICATION_v2\`
  (code, outputs, calendar, RUNTIME.json with package versions, MANIFEST
  hashes). Inputs unchanged from the v1 19-file package you already hold;
  the div-02 series matches your frozen component_mm.csv.
- Your QRF-reproducibility caveat stands; ridge remains the anchor
  (reproduces to 4e-8 in your rerun).
