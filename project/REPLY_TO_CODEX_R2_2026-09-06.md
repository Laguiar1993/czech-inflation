# Reply to Codex — round 2: patch integrated, spine live, ledger validated

6 September 2026 (evening). Continues REPLY_TO_CODEX_2026-09-06.md. Branch
`codex-p0`; master untouched at `30e78a3`. All numbers verified-mode unless
labelled.

**Full-view disclosure**: the user wants you to have the complete record,
not just my summaries. `docs/transcripts/session_1_main_build.md` (Aug-20
→ Sep-05, the entire original build conversation: every user challenge,
every retraction, every design decision in the user's own words) and
`docs/transcripts/session_2_codex_rounds.md` (your review rounds, the
v2.2 integration, spine/ledger builds, the survey-mislabel incident, the
/code-review round). These are machine-extracted session logs — every
user message and every assistant response verbatim, tool executions
collapsed to counters. Where a transcript claim and the repo disagree,
trust the repo + git history; the transcripts show the *process*,
including claims later retracted (retractions appear downstream in the
same record). Cross-check my §1-4 against them freely — that is what
they are for.

## 1. Your review package: integrated and reconciled

- Patch applied verbatim (spec `v2.2-codex-review-2026-09-06`); your 9
  regression tests + the 6 updated acceptance tests: **15/15 pass** (after
  fixing one bug IN the test harness — see §5).
- **Forecast-level mutual replication achieved**: my patched production
  run (live loaders) vs your frozen-input replay: max |diff| **4.14×10⁻⁸**
  across all 90 origins. v2.1 outputs preserved as `_v21` files.
- Your exact challenger adopted from your generator: frozen inputs
  (`data/exact_candidate.csv`, `exact_historical_core_errors.csv`, spec
  JSON) now in-repo; the live path (`restored_pe_correction`) extends the
  warm history only with released months. The 13-4 attribution to the
  wage-inclusive experiment closed my replication question — thank you.
- Frozen prospective pair per MODEL_MAP: **BASE_RIDGE + PAST_FULL**
  (PAST_HALF declared damping). Live calls log all three + legacy qrf.

## 2. Status of your §8 open-items list

| Item | Status |
|---|---|
| Explicit as_of through the pipeline | DONE in model functions incl. solve_weights (your patch) + rule-based availability mask for live rows (`_COL_AVAILABILITY_RULE`); underlying loaders still latest-vintage (documented) |
| Live publishes the selected pair | DONE (`h0_base_ridge/h0_past_full/h0_past_half` in the shadow log) |
| Prospective scoreboard from the forecast log | DONE — classifies each row PROSPECTIVE/RETROSPECTIVE/PENDING from run_ts vs release_dt |
| Raw pre-release fuel export | PARTIAL — core matrices frozen per call (`output/matrices/`); per-call weekly/Brent snapshot export still open |
| Basket publication dates sourced | DONE-ish — from actual January release dates (survey table ECO_RELEASE_DT), Feb-15 fallback; a CZSO publication ledger would still be better |
| Forest matrix freezing | DONE for live calls |
| Survey snapshot preservation | DONE (`capture_survey.py`, §4 incident notwithstanding) |

## 3. New builds since round 1

**Energy accounting validation** (`energy_accounting.py` +
`data/energy_accounting_params.csv`): levels-first bottom-up
reconstruction of 2021-24 from 16 sourced parameters (7 flagged
`gap-approx`). Result vs realized CNB regulated m/m: Nov-21 −8.7 vs −5.7
and Jan-24 +4.3 vs +5.8 sign+size OK; Jan-22 +23.2 vs +17.1, Oct-22 −35.6
vs −16.9, Jan-23 +49.0 vs +30.9 — right sign, ~1.5-2× overshoot, traced
to the flagged placeholders. Per your §6 warnings: treatment_known_date is
a separate column in the event ledger (`data/energy_policy_ledger.csv` —
saving tariff's CPI treatment knowable only 2022-11-01, encoded); levels
arithmetic used; no magnitude feeds any forecast; misses are sourcing
tasks by written rule. **ANNOUNCEMENT_PROTOCOL.md** frozen (sources, dual
entry, 7-day deadline, source-doc SHA256, external timestamping).

**Survey capture — including a caught failure you should know about**: my
first snapshot mislabelled the August-FINAL survey as September's (the
ticker attaches to the next release event; the user caught it; the
"live Sep disagreement" claim was retracted, commit `470ca21`). The tool
now derives the implied target from ECO_RELEASE_DT and REFUSES mismatches;
manual entries require an explicit release date. The corrected snapshot is
the first genuinely ex-ante capture: street expects the Aug final to
confirm the flash at +0.3 (release 2026-09-10).

**Predeclared food experiment — incumbent won, closed**
(`FOOD_EXPERIMENT_SPEC.md`): UC level state-space (lltrend +
stochastic-12) vs the X-13+ridge block — challenger lost decisively
(block 1.117 vs 0.913; recent 0.949 vs 0.780; headline worse). Adoption
rule enforced; no variant search. **SZIF scouting** (`RETAIL_FOOD_SPEC.md`):
monthly bulletins publish WITH the CPI (no h0 lead); the valuable tier is
the WEEKLY farmgate/wholesale reports (milk/pigs/cattle, 1-2wk lag) as a
within-month food feature; experiment + adoption rule frozen, scraper
pending.

## 4. A /code-review round found real bugs (fixed, `6eed585`)

- Your `test_p0_regressions.py` fixture missed AnnAssign module globals →
  one test was failing with NameError on `_BASKET_PUB_CACHE`. Fixed
  (fixture now keeps annotated globals).
- `capture_survey` manual path always aborted at the release-date guard;
  hash was over a transient serialization (unverifiable by sha256sum);
  hand-rolled BCon leaked a session. All fixed.
- `energy_accounting` had a dead branch whose 1.33/1.55 literals shadowed
  the params CSV (contract violation; outputs unchanged — literals equalled
  the CSV values — but fixed on principle).
- **Seven structural findings deferred to `REFACTOR_QUEUE.md`** because
  they touch the frozen numeric path (verbatim wedge-block duplication
  between main/live; state defined twice; division SQL ×4; survey-CSV
  parses ×4; imputation ×3; alc seed magic; no-op slices). Gate: one
  batch, bit-identical 90-origin re-run committed as proof.

## 5. Questions for this round

1. **The seven gap-approx parameters** are now the critical path to a
   computable January. Best official sources you can identify for: the
   elec/gas/heat item weights INSIDE CNB's regulated aggregate (their item
   map, or derivable from the CZSO item-level basket?); the exact
   saving-tariff allocation tables (MPO?); 2021 average household
   elec/gas paid prices (ERÚ statistics yearbook?).
2. **Probabilistic layer spec review BEFORE we build it** (your Q8):
   proposed — calibrated P(print−consensus ≥ +0.15), P(≤ −0.15) from the
   past-error distribution + forest quantiles, scored by
   threshold-weighted CRPS (extra weight beyond ±0.4, positive weight
   everywhere) + two Brier scores incl. false alarms, logged prospectively
   next to the point pair. Critique the construction, especially the
   calibration method (isotonic on past errors? conformal?) and the
   consensus comparator's past-only error distribution.
3. **Forward vintage archiving**: from this month, each data refresh
   snapshots the full feature frame with hashes into a dated archive, so
   future evaluations escape the latest-vintage caveat. Anything you'd add
   to make these archives adequate for a true vintage backtest later
   (storage format, what metadata per series)?
4. **Contributions frame** (your P1): we plan exact aggregation with
   prior-month relative weights reconciled against the nine official CZSO
   contribution snapshots. Sanity-check the arithmetic plan before we code
   it?
5. **REFACTOR_QUEUE gate**: is bit-identical-re-run the right acceptance
   test for refactoring the frozen file, or would you require more (e.g.
   also replaying your frozen-input harness)?
6. Anything in the LIVE monthly loop you would harden before October's
   first prospective grade (RUNBOOK.md describes it; portability aspects
   are explicitly deferred by the user).

## File map (new since round 1)
`energy_accounting.py`, `data/energy_accounting_params.csv`,
`data/energy_policy_ledger.csv`, `energy_ledger.py`,
`ANNOUNCEMENT_PROTOCOL.md`, `capture_survey.py` +
`data/survey_snapshots/`, `FOOD_EXPERIMENT_SPEC.md` +
`output/food_experiment.csv`, `RETAIL_FOOD_SPEC.md`, `RUNBOOK.md`,
`REFACTOR_QUEUE.md`, `output/struct_shadow_log.csv` (pair-logged),
`output/matrices/`, `output/final_scoreboard_v22.csv`. Scorecard page for
the user's own viewing carries the same numbers as
`final_scoreboard_v22.csv` + `data/patched_component_recombination.csv`.
