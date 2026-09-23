# Czech CPI forecasting

**Latest path research (R17, 14 September 2026):**
[Results and small model map](R17_RESULTS_2026-09-14.md),
[CNB Rounds Replayed](output/research_r17/path/evaluation/cnb_rounds_replayed_r17.html),
[specifications](docs/implementation/R17_IMPLEMENTATION_PLAN_2026-09-14.md).
All approved component, core-state, monthly-category, energy-scenario and whole-path
combination tests are complete: 30 models, 90 origins, h0–h12. Most additions do not
improve the reference. Category AR improves its pressure proxy; new macro mapping
does not improve core. Annual-index fuel conditioning has mixed results. Core and
headline gains still need separate interpretation. No consistent CNB or turn edge
is established; all 13 large-CNB-error pairs at the 1 pp threshold are from 2022.
Keep FAST/current-core/gentle-slope comparisons and an optional fuel scenario;
the all-components model and selectors are not promoted. The independent nowcast
is unchanged. July 2026 remains the final frozen origin. The dated policy audit
corrects source/accounting issues but leaves the national bill point forecast
unavailable until exposure and baseline data are supplied.

**Previous path research (R16, 14 September 2026):**
[Results, model map and economic assessment](R16_RESULTS_2026-09-14.md),
[interactive CNB round replay](output/research_r16/evaluation/cnb_rounds_replayed_r16.html),
and [frozen specification](docs/implementation/R16_SLOPE_TRANSMISSION_SPEC_2026-09-14.md).
Damped core slopes improve annual-headline path errors; the gentler .95/.001
setting is the more balanced headline research challenger. Exact accounting
finds weaker core forecasts whose errors interact more favourably with retained
block errors; this does not establish improved core dynamics or turn prediction.
Separately forecast services/goods signals and their fixed blend did not earn
promotion. CNB-relative RMSE gains remain dependent on the February 2022 round.
All 15 models use unchanged R15 scoring support and frozen current-vintage inputs,
ending at July 2026. The independent nowcast and operating models are unchanged.
This assessment supersedes earlier path research recommendations; the entries
below retain the development record.

**Previous path research (R15, 14 September 2026):**
[Results, economic assessment and model map](R15_RESULTS_2026-09-14.md),
[interactive CNB round replay](output/research_r15/evaluation/cnb_rounds_replayed_r15.html),
and [frozen specification](docs/implementation/R15_TREND_RESIDUAL_SPEC_2026-09-14.md).
Eleven trend/residual candidates and three controls were evaluated on 90 monthly
origins, h0–h12. FAST improves full-history path accuracy; current core remains
stronger recently. Elastic nets, the residual forest and fixed blends do not
establish a consistent advantage. CNB-relative squared-error gains are concentrated
in the February 2022 round; advance core-turn prediction remains unsolved.
These are frozen current-vintage historical experiments ending July 2026,
with reconstructed availability. The independent nowcast and operating models
are unchanged. This R15 assessment superseded earlier path research recommendations;
the older entries below remain the development record.

**Latest research (R13, 9 September 2026):**
[Model map and reproduction](RESEARCH_R13_START_HERE.md),
[results and economic assessment](docs/implementation/R13_RESULTS_2026-09-09.md).
BASE/Category Raw/Half/Full are now compared using each family's own past errors,
with matched-history controls. Category corrections and new whole-path models
are not promoted. CNB shared-error diagnostics and exact component-error
accounting separate plausibility from realised accuracy. Operating formulas stay
unchanged; historical sections below describe the preserved development record.

**Current implementation, 9 September 2026:** use `forecast_independent.py` for
the independent nowcast. Its main `HARD_BASE` excludes professional and household
inflation expectations and ESI; HALF/FULL are separately labelled challengers.
An expectations-conditioned comparison is opt-in. The new entry point archives
the exact inputs and supports offline replay. See
[`docs/implementation/OPERATING_GUIDE.md`](docs/implementation/OPERATING_GUIDE.md)
and [`docs/implementation/PLAN_2026-09-09.md`](docs/implementation/PLAN_2026-09-09.md).
The original checkout is preserved; this work is on the isolated
`codex/independent-cpi-20260909` branch. Historical path results below predate
the R9 timing, horizon and vintage corrections and do not certify the corrected
path models. New measurements have the `independent_` output prefix.

**Large paper-style challenger (10 September 2026):**
`big_model_experiment.py` builds a Bloomberg-independent official-data panel
and runs direct h1/h3/h6/h9/h12 TVW-QRF and BBIM challengers under independent,
sentiment and full input policies. The independent policy excludes all
inflation expectations and confidence balances; full is an optional diagnostic
line. Read [`docs/implementation/BIG_MODEL_SPEC_2026-09-10.md`](docs/implementation/BIG_MODEL_SPEC_2026-09-10.md)
before using its outputs. The latest bounded scorecard is in
[`docs/implementation/BIG_MODEL_RESULTS_2026-09-10.md`](docs/implementation/BIG_MODEL_RESULTS_2026-09-10.md)
and the reproducible files are under `output/big_model_all_20260910d/`. It is
research-only until common-window scores, clock checks and a prospective shadow
run are complete.

The paper-variable lane is separate from that operating challenger. Its exact
72-variable checklist, ECFIN question codes, source identifiers and download
script are in [`docs/implementation/CNB_WP9_A6_DATA_REQUEST_2026-09-10.md`](docs/implementation/CNB_WP9_A6_DATA_REQUEST_2026-09-10.md)
and [`tools/paper_replication/download_public_bcs.ps1`](tools/paper_replication/download_public_bcs.ps1).
The Bloomberg interpretation and remaining terminal/online pull list are in
[`docs/implementation/BCS_TICKER_AND_REMAINING_INPUTS_2026-09-10.md`](docs/implementation/BCS_TICKER_AND_REMAINING_INPUTS_2026-09-10.md).
Do not interpret the current closest-data run as a 72-variable replication:
it is a data-coverage audit until the missing inputs and their release clocks
are supplied.

The latest Bloomberg capture is
`data/market_snapshots/20260911_bloomberg_full_refresh/`. It contains the
consolidated candidate map, 65 successful histories and 65 BDP metadata records
through 10 September 2026. `CZIPITS Index` is the seasonally adjusted
industrial-production level; `CZIPITN Index` remains the raw NSA/X-13
challenger. `CZGRIDX Index` is labelled as the total granted-permit count; its
history behaves like a direct monthly count rather than a cumulative year-to-
date series, but its CZSO geography/revision clock still needs checking before
scoring. The snapshot also contains `LONSCZNF Index`, quarterly ULC,
`EUS3CZ`/`EUS5CZ`/`EUB3CZ`, German HICP and unemployment, Czech import prices,
all supplied BCS candidates, and the commodity/energy candidates. The invalid
`EEUR3CZ Index` diagnostic returned no data and has been removed from the active
pull map; `EUR3CZ Index` is the canonical retail-orders candidate. Adjustment
status and paper-lane admission rules remain documented in
[`docs/implementation/BLOOMBERG_PULL_2026-09-11.md`](docs/implementation/BLOOMBERG_PULL_2026-09-11.md).

The Bloomberg puller uses the consolidated map in
`tools/market_data/pull_bloomberg.py`, which now includes the earlier BCS
tickers (`EUI6CZ`, `EUI1CZ`, `EUS1CZ`, `EUS2CZ`, `EUR1CZ`, `EUB1CZ`, the
construction-factor series, `EUCCCZ`, `UMRTCZ` and `CZRUSHIN`) as well as the
new candidates (`EUICCZ`, `EUSCCZ`, `EUICDE`, `EUSCDE`, `EURTDE`, `EURTPL`,
`EUR3CZ`, `EUR4CZ`, `EUR5CZ`, `EURTCZ`, `EUA1CZ`, `EUA0CZ`, `EUAUCZ`,
`EUA6CZ`, `EUCOCZ`, `EUCODE`, `EUB4CZ`, `EUI5CZ`, `EUA2CZ`, `EUA4CZ`,
`EUA8EMU` and `EUA7EMU`). Existing dated snapshots remain
immutable. A direct
Commission-annex spot check supports `EUS1CZ` as the services business-
situation question but leaves `EUS2CZ` out of the paper lane until its
different “recent month” label is resolved; the row-level evidence is in
`output/bloomberg_bcs_ec_annex_spotcheck_20260911.csv`.

The paper's euro-area perceived/expected inflation inputs are the Commission
consumer balances `CONS_005`/`BS-PT-LY` (price trends over the last 12 months,
Bloomberg candidate `EUA7EMU`) and `CONS_006`/`BS-PT-NY` (price trends over the
next 12 months, Bloomberg candidate `EUA8EMU`). They are household survey
balances, not ZEW analyst forecasts or market-implied inflation. The source and
admission rules are documented in the BCS ticker note.

**Services/core follow-up (R10):** the category-split experiment, source audit,
seasonal category monitor and results are in
[`docs/CORE_SERVICES_REVIEW_2026-09-09.md`](docs/CORE_SERVICES_REVIEW_2026-09-09.md).
Replay it with `python core_split_experiment.py --verify`; no live database or
source connection is required. The five-category model improves core and recent
headline accuracy, but weakens large-surprise capture versus BASE/FULL. It stays
a research accuracy challenger. The legacy input named `services_l1` is a
six-division index proxy, **not official services CPI**; the review corrects that
description without rewriting R9 numerical history.

**Latest assessment (R11):** [nowcast roles and path priorities](docs/LATEST_MODEL_ASSESSMENT_2026-09-09.md).
Keep BASE as the operating reference, the simple category model as a research
accuracy challenger, and HALF/FULL as the existing error-correction comparisons.
Restoring economic predictors only to the category remainder did not justify a
replacement. The independent path review identifies long-horizon food bias and
all-month administered-event coverage as priorities. R11 adds diagnostics only;
the old point forecasts are unchanged. Replay with
`python core_remainder_experiment.py --verify`.

## Historical status and build record

Start here. The operating model is CZ-STRUCT: a component forecast of Czech
consumer-price inflation. BASE_RIDGE is the point-forecast reference;
PAST_FULL is the warm past-error challenger. Both run through cz_struct.py.

**Status on 7 September 2026 (night): v2.7.2-bands (points frozen at v2.7.1), live certification pending; first prospective call = the 30 September month-end call.** By user decision the January gate reads documented announcement entries (dated source documents, frozen rule; `ANNOUNCEMENT_ADOPTION_v27.md`), with the gate-closed reference kept as `STRUCT_NOANN` / `STRUCT_NOANN_EVE` on every board. v2.7.1 (Codex R8) stores the entries in economic units, corrects the January 2022 shares and the January 2023 credit-only reversal, fixes the wedge error in the contribution report and the food producer-price availability rule, and freezes the three nowcasts (BASE_RIDGE, PAST_FULL, PAST_HALF) for the prospective record. R6 timing fixes are in (v2.6). Latest reply to the reviewer: `REPLY_TO_CODEX_R8_2026-09-07.md`. 8 Sep: `path_live.py` produces the forward monthly path (m/m and y/y, twelve months) and logs it (`output/path_live_log.csv`); the step-2 path backtest (`PATH_SPEC_v2.md` RESULTS, `PATH_BACKTEST_H_SPEC.md`) set its engine to the component bridge F1b and added the trend-and-gap path as a second line; `SURVEY_ABLATION_SPEC.md` measured that the nowcast does not depend on its survey inputs while the twelve-month horizon does. Same night: `BANDS_SPEC_v1.md` (bands for the trio, uncalibrated under the frozen rule, published flagged), `PATH_SPEC_v2.md` (path step 2 declared, no run), the energy ledger's seven placeholders replaced by sourced values (`data/energy_accounting_params.csv`), the database refreshed and the September dry run clean (0 stale inputs). 8 Sep (day): `PATH_SPEC_v3.md` and `PATH_SPEC_v4.md` tried the path without surveys (trend anchored to the CNB target, hard-data drivers with sign checks, robust seasonal, wages, CZSO import prices): slack, the koruna's twelve-month change lagged three months and the real rate at twelve to eighteen months carry the right signs; wages do not; no survey-free line beats the survey-anchored one in 2024-26, so the product engine (F1b) and the survey second line are unchanged, and `path_live.py` shows the survey-free path as a third, flagged information line (E7 by the v4 rule; the RESULTS flag that E5 is better on the long span and ask the user to decide on the rule). The nowcast logs a no-survey reference column (`h0_base_ridge_ns`). 8 Sep (afternoon): the CNB comparison is made only at the bank's report dates with the path we had published before each report (`path_backtest_h_cnbq.py --match before`, forward-looking panels); `PATH_SPEC_v5.md` built the CNB's own architecture in miniature (nowcast and bridge for three months, then a semi-structural gap model with anchored or model-consistent expectations, an IS curve and the market rate path): the Phillips-curve signs hold, the monthly ex-post IS curve does not, nothing replaces the product; model-consistent expectations win the calm regimes and lose the long departures, which points to a time-varying credibility weight as the next declared step.
The R4 construction repairs, the cleanup and the v2.5 timing repairs
(sourced release calendar, clock-filtered food history, eligibility in every
component, two decision times, month-to-date FX, zone-aware clock) reproduce
on frozen inputs; see [TIMING_SPEC_v25.md](TIMING_SPEC_v25.md). The refresh
step and the complete live archive still require work. The first
ordinary-month improvement project (food, 7 Sep) tested two predeclared
challengers and closed both without adoption: the weekly SZIF farmgate
signal ([FOOD_SZIF_SPEC.md](FOOD_SZIF_SPEC.md), with the publication-timing
verification) and category-level pooled forecasts
([FOOD_CATEGORY_SPEC.md](FOOD_CATEGORY_SPEC.md)). Read
[live readiness](docs/LIVE_READINESS.md) before treating any historical or
shadow result as a trading signal.

## Read these four documents

- [Model roster and evaluation rules](docs/MODELS.md): what to use, what each
  column means, and which experiments remain research.
- [Runbook](RUNBOOK.md): installation, external data, verification and monthly commands.
- [Cleanup review](CLEANUP_REVIEW_2026-09-07.md): exact changes, evidence and R4 answers.
- [Live readiness](docs/LIVE_READINESS.md): the next repairs, separated from cleanup.

## Project layout

| Location | Purpose |
|---|---|
| cz_struct.py | Active five-component model, backtest and shadow forecast entry point |
| data/ | Data adapters, shared loaders, frozen inputs and source calendars |
| models/ | Forecast estimators and fuel measurement |
| evaluation/ | Evidence classification without model execution or file writes |
| scoreboards_codex_p0.py | Historical scores and explicitly unverified shadow diagnostics |
| output/ | Versioned forecasts, backtests and archived matrices; preserve history |
| test_*.py, tests/fixtures/ | Offline acceptance, regression and known-limitation tests |
| tools/replay_cleanup.py | Offline 90-origin regression replay |
| backtest_*.py, backtest/, food_experiment.py, late_info_tilt.py | Research comparisons |
| docs/ | Current guidance, evidence, historical notes and transcripts |

Earlier handoffs/replies remain in the root to preserve shared entry links.
They describe the evolution of the project; current status comes from the
documents above. The original pre-STRUCT README is archived in docs/history.

## Quick checks

```powershell
python -m pip install -r requirements-dev.txt
python -m pip install -r requirements-numerical-lock.txt
python -m pytest -q
python scoreboards_codex_p0.py
```

The tests are offline. Three strict expected failures explicitly represent
unfixed live-readiness defects; a green test run does not clear them. The
scoreboard recomputes its release table from existing files and never runs
the forecasting model. Running cz_struct.py without --live starts a full
backtest and replaces output/cz_struct_backtest.csv; use the offline replay
for cleanup verification instead.
