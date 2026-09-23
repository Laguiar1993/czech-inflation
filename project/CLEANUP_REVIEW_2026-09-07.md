# R4 review and structural cleanup — 7 September 2026

**Verdict: a reproducible research checkpoint; live certification remains open.**
Luis approved cleaning and stabilizing the existing models while preserving
forecast calculations and historical results. The cleanup implements that
scope. It does not promote another model, change the specification, run the
database updater, log a live forecast, or create a commit.

The starting point was codex-p0 HEAD 1251fd8 plus the uncommitted R4/v2.4
files, including REPLY_TO_CODEX_R4_2026-09-07.md and LIVE_PARITY_SPEC_v24.md.
All 212 tracked/untracked source files were snapshotted before editing.
The private Claude artifact could not be opened; the review uses the local
files and reproducible evidence, not an assumed copy of that page.

## What changed

- Shared services, agri, heating-oil, housing and M3 loaders now live in
  data/struct_inputs.py. The research driver re-exports them for compatibility.
  Importing cz_struct no longer imports the old backtest drivers.
- The repeated live/backtest weighted wedge and compounded trailing-year
  calculation each have one implementation. Subtraction order, alignment,
  missing values and state logic are preserved. The unused CFG import and
  redundant cold-error slices were removed.
- The unused root components.py and fetchers.py copies were removed after
  checking all Python imports. Their active implementations remain under
  models/ and data/. The deleted copies remain recoverable in git history.
- The scoreboard is import-safe and resolves files relative to its repository.
  Historical metrics and release-table values are unchanged. It now calls
  historical results historical rather than generically VERIFIED. Shadow
  rows cannot earn prospective certification merely by having an early run_ts.
  False/missing archive flags, incomplete input rows, unknown stages and naive
  clocks are identified; pre-final calls never receive a flash error score.
- DB and X13 locations are configurable without editing source. Defaults are
  preserved on Luis's computer. DuckDB was added to requirements; development
  dependencies and the audited numerical version pins are recorded separately.
- The obsolete front page and refactor queue were archived and replaced.
  README, RUNBOOK, docs/MODELS.md and docs/LIVE_READINESS.md define the active
  roster, commands, research status and next repairs. Acceptance tests now use
  local frozen components instead of external database/live loaders.
- A small frozen fixture, expected result and offline replay tool make this
  cleanup repeatable on another machine.

## Verification

| Check | Result |
|---|---|
| Existing R4 tests on frozen inputs | 24 passed before cleanup |
| Complete cleaned repository suite | 35 passed, 3 strict expected failures |
| Full before/after replay | 90 origins x 42 columns; every value and CSV byte identical |
| Dense and gapped load_all fixtures | All eight outputs identical, including live edge+1/edge+2 |
| Moved loader function bodies | All five ASTs identical |
| Historical release-by-release table | Byte-identical |
| Existing data/output files excluding the edited adapter | 123 files unchanged |
| Independent replay versus supplied R4 ridge/warm | Maximum absolute difference 4.14e-8 pp each |

The expected replay CSV has SHA256
`d0c2ce6584347c29449923ea1c66dd3a033d3f1dae045890b81545461f7c93d8`.
The frozen-data comparison uses Python 3.14.3, NumPy 2.4.4, pandas 3.0.2,
SciPy 1.17.1, sklearn 1.8.0, quantile-forest 1.4.2 and statsmodels 0.14.6.
X13 is a separately hashed executable. See docs/review_evidence/cleanup_2026-09-07
and tests/fixtures/cleanup. This validates refactor equivalence and the
supplied forecasts on fixed inputs; it does not certify historical vintages.

Do not extend the ridge/warm replication claim to every research column:
relative to the supplied R4 CSV, this rounded frozen-input replay differs
by up to 0.00859 pp for the legacy residual QRF, 0.02996 pp for the cold
past-error variant, and 0.01019 pp for the legacy bands. Those differences
exist in the unmodified baseline replay and are exactly unchanged by the
cleanup. Their cause has not been isolated; it is not automatically a
runtime explanation. Per-column differences are supplied in
replay_vs_supplied.csv. Historical production outputs are preserved intact.

The three expected failures are deliberate live-readiness requirements,
not waived checks: an actual publication-date counterexample, food history
entering X13 before its cutoff, and cache reuse after an input vintage changes.
Fixing them requires the separately evaluated numerical/timing batch Luis
asked us to keep apart from this cleanup.

## Answers to Fable's four R4 questions

**1. Refactor acceptance.** Yes to unchanged matrices and complete before/after
output identity, but also retain independent edge+1/edge+2, missing-month and
release-boundary checks. Historical identity cannot find a live-edge defect.
This cleanup runs both the full replay and independent load_all comparisons.
Do not implement the old alcohol-seed change as a no-op, or remove ridge
standardization when deduplicating the forest path. Those original queue
entries were not safe mechanical instructions.

**2. Pre-final scoring.** Keep it and eventually score it against the detailed
release and a separately captured final consensus, conditional on the known
flash. That is a distinct useful product. It must never count toward flash
surprise prediction. For now the scoreboard displays the row and leaves its
first-release diagnostic errors blank; a valid final-event score needs its own
event identity and target/consensus data.

**3. The 11th-day CPI rule.** I have not established a specific CNB-after-CZSO
lag from archived receipt evidence. It is unnecessary to establish that lag
to reject the current rule: CZSO's January 2026 detailed CPI was published
on **13 February**, whereas the helper admits it on 11 February. See the
[official release](https://csu.gov.cz/rychle-informace/consumer-price-indices-inflation-january-2026).
Use the actual source calendar/timestamp and retain a separate CNB availability
record. A detail-release timestamp is not automatically a basket-publication
timestamp either. Clock selection needs to precede preprocessing, weights,
seasonal estimates and past-error construction across the whole pipeline.

**4. Which warm reference to freeze.** Use the in-repo live function under a
fully recorded runtime as the next prospective reference; keep the earlier
frozen column as an immutable historical anchor. Do not splice either series
to improve scores. I reproduced R4's warm column within 4.14e-8 pp using the
same runtime and frozen inputs. That supports R4's reproducibility. It does
not prove that every difference versus the older Python 3.12 result is caused
by library versions. For causal diagnosis, hold matrices/error histories
fixed, then compare fitted quantiles, unrounded weights, optimizer status and
point outputs across runtimes. 0.727 and 0.724 are different RMSEs even if the
ranking is unchanged.

## Assessment against Luis's goals

These are statistics recalculated from the supplied R4 output and the same
first-release survey table. All changes in this cleanup preserve them.

| Frame / metric | Consensus | BASE_RIDGE | PAST_FULL |
|---|---:|---:|---:|
| All 90 releases, RMSE | 0.382 | 0.731 | 0.727 |
| 2024 onward, 31 releases, RMSE | 0.241 | 0.214 | 0.227 |
| All 23 large surprises, MAE | 0.578 | 0.642 | 0.600 |
| Ex-January 19 large surprises, MAE | 0.595 | 0.521 | 0.485 |
| All large surprises, material wins-losses | — | 6-3 | 10-4 |
| Ex-January large surprises, material wins-losses | — | 6-2 | 10-2 |

The logic is defensible: measure fuel, model food/core, account separately for
administered prices and tobacco, and learn persistent sequential core errors.
The operating pair is enough for the next stage. Ridge leads on recent
overall accuracy; PAST_FULL is useful for investigating material deviations
and has the stronger ex-January surprise record. Neither has demonstrated a
full-sample unconditional consensus advantage.

The distinction between hit count and money-sized error improvement matters:
PAST_FULL wins materially on 10 big surprises and loses on four, but its
total absolute-error improvement over those 23 events is **-0.490 pp**.
Across ex-January big surprises it is **+2.077 pp**. Those January losses
cannot be argued away or replaced by a reconstructed announcement result.
The recent window contains only five large surprises, so it cannot support
a claim of a stable high hit rate. These scores are research selection evidence,
not a locked prospective test or a rates-trading return backtest.

Keep BASE_RIDGE and PAST_FULL side by side; retain PAST_HALF as sensitivity.
Next work should improve the information set and accounting before adding
more model variants: correct the clocks/X13/archive, complete the refresh
pipeline, improve food signals and national energy/tax mapping, then freeze a
live evaluation rule. Path forecasts deserve a separate horizon-specific
model selection and coherent monthly-to-yearly aggregation. Trading decisions
need their own event-to-rates relationship, transaction costs and risk model;
the current point forecasts and legacy bands do not supply that layer.

## Commit boundary

This cleanup can be reviewed as a research checkpoint on top of Fable's R4
WIP. Do not describe it as completed live certification. SPEC_TAG remains
v2.4 and provisional. No historical input, forecast, shadow row or prior
review transcript was rewritten to improve a score. Use the next separately
versioned change for the blockers in docs/LIVE_READINESS.md.
