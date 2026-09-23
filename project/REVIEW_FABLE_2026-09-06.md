# Independent review of CZ-STRUCT v2.3-fuel (branch codex-p0 @ 1251fd8)

6 September 2026, evening. Fresh-session review on request ("analyse it, see
potential errors, give tips"). Scope: the forecast path (`cz_struct.py`,
`models/components.py`, `models/horizon_models.py`, `data/local_adapter.py`,
`backtest_h0_enriched.py` loaders), the calculators (`energy_accounting.py`,
`energy_ledger.py`), `capture_survey.py`, `scoreboards_codex_p0.py`, both test
files, the calendars/ledgers, the live shadow log and frozen matrices, the
v2.2/v2.3 backtest CSVs, and the Codex audit documents (REVIEW_FOR_CLAUDE,
MODEL_MAP, PAST_ERROR_QRF_SPEC, CONTINUATION_REPORT, JANUARY_RECONSTRUCTION_RISK).

Method: read everything above; ran the 15 tests (15 pass); re-derived the
scoreboard statistics with significance tests; probed suspected defects by
executing the production functions against the live loaders. **No code was
changed, nothing was committed, no logged row was touched.** Every number
below is reproducible from the repo as it stands.

---

## 0. Bottom line

1. **There is a live/backtest parity bug that invalidates every live call
   logged so far.** For the live target month (CPI edge + 1) all lagged
   features are NaN and get mean-imputed: core_l1/l2/l12, services_l1,
   import_l2, the state dummy and its three interactions, plus the entire
   food pipeline (food_l1, food_l12, agri_l0, agri_l1, food_ppi_l1). Cause:
   `Series.shift(n)` on a PeriodIndex moves values but never extends the
   index, so `core.shift(1).reindex(feats.index)` has no label for edge+1.
   Backtest origins sit inside the index and are fully populated, so the
   backtest never exercises this path. Verified from the frozen matrices of
   both v2.2 live calls and by re-running the live frame. On the August call
   the correction alone moves the core block from +0.05 to +0.35 and the food
   block from -0.12 to -0.36; net headline **+0.12 pp** (logged BASE_RIDGE
   +0.27 would have been roughly +0.40; street +0.30). The Sep-10 grade is
   therefore a grade of a degraded model, not of the backtested pair.
2. **The statistical case is weaker than the docs read.** No frame is
   Diebold-Mariano significant (2024+: p=0.19; flash era: p=0.12); ex-January
   the model is *worse* than consensus (0.405 vs 0.380). The big-surprise
   gain is real only ex-January (cumulative +1.40 pp over 19 events,
   bootstrap P>0 = 0.98) and is wiped out by four Januaries (-2.86 pp,
   2022-01 alone -2.59). When the model disagrees with the street by >=0.2
   ex-January it is closer to the print 7 times out of 16.
3. **Where the remaining error lives has shifted.** Over the whole sample
   ex-January the admin block is 61% of headline error variance (the 2022
   non-January energy months). In 2024+ ex-January it is food 45%, core 23%,
   alcohol/tobacco 18%, admin 4%, fuel ~0. Fuel is solved; food and a
   surprisingly noisy alcohol/tobacco block are the statistical targets now;
   admin is a policy-ledger problem, not a model problem.
4. **January is systematically under-forecast in 6 of 7 years, calm years
   included (about -0.5 pp in 2020/2021/2024).** Three legitimately ex-ante
   fixes exist (alcohol excise calendar, robust admin seasonal base, core
   January repricing term) before the energy ledger even enters.

---

## 1. Defects found, ranked

### D1 (critical): live origin row loses every lagged feature
- Where: `cz_struct.py:98,101,102-104,105` (feats) and `:122-130`
  (food_feats); same pattern inside `backtest_h0_enriched.py:78`
  (`mm.shift(1)` drops the newest agri month before it can ever be used).
- Evidence: `output/matrices/2026-08_20260906T14*.npz` -> `feats_row` NaN in
  12 of 25 columns (exp12, exp36, esi are DB staleness, see D2; the other
  nine are this bug). Live reproduction: CPI edge 2026-07, core(2026-07)=1.0
  released, yet `feats.loc[2026-08,"core_l1"]` is NaN; `food_feats.loc
  [2026-08]` NaN in all five columns. A backtest origin (2026-07) shows only
  `import_l2` NaN (same mechanism: the import series ends before t).
- Consequence: BASE_RIDGE, PAST_FULL/HALF and the h1 companion all run on a
  training-mean feature vector for the persistence and pipeline terms; the
  past-error forest sees an "average" row and returns a near-unconditional
  correction. All 16 rows in `output/struct_shadow_log.csv` came through
  this path.
- Fix (one rule): build every lag as `src.reindex(full_index).shift(k)` or
  `src.shift(k, freq="M")`, never `src.shift(k).reindex(...)`. Apply to
  feats, feats_st, food_feats, and inside `load_agri_price_mm`. Add a test:
  `feats.loc[edge+1,"core_l1"] == core[edge]` and `food_feats.loc[edge+1,
  "food_l1"] == food[edge]`. Add a live guard that prints the list of
  imputed columns per call and refuses when a column whose source is
  released is NaN. This is a spec-neutral bug fix for the backtest (rows
  unchanged except the last origin's import_l2) but it changes every live
  number, so tag it and flag the 16 existing log rows as
  `degraded_features=True` rather than deleting them.

### D2 (high, operational): the live call ran on a stale database
- Evidence: on Sep-6 the DB edges were ESI 2026-07 and FMIE 2026-07 although
  August ESI (~Aug 28) and August FMIE (~Aug 17) were public; both were
  imputed in the August call. The 6-month tripwire cannot see a 1-month gap.
- Fix: run `update_cz.py` immediately before each of the two monthly calls
  (RUNBOOK currently refreshes after the CPI release, i.e. after both
  calls); tighten the tripwire to 1 month for in-month series; write the
  count and names of imputed features into the log row.

### D3 (medium, operational): the backtest cannot grow
- `cz_struct.py:583-585` takes the origin list from the legacy
  `output/backtest_h0_hybrid.csv` (last row 2026-07). Once August CPI is in,
  `python cz_struct.py` will silently keep evaluating through July unless
  the retired Brent-dependent legacy script is re-run.
- Fix: origins from `y.index` (2018-02 .. CPI edge); keep the champion file
  as an optional benchmark column.

### D4 (medium, test integrity): the regression fixture tests the wrong path
- `test_p0_regressions.py:27` builds a namespace without `os` or `HERE`;
  `_basket_available_from` raises NameError inside its try/except and falls
  back to Feb-15. In the fixture `_basket_available_from(2026)` = 2026-02-15;
  in production it is 2026-02-05. `test_weights_use_actual_clock...` passes
  on the fallback and would not catch a regression in the survey-table
  lookup. Fix: import the module and monkeypatch loaders (as
  `test_struct_acceptance.py` already does), or inject `os`/`HERE` and
  assert the production date.

### D5 (medium, parity): the end-of-month live call and the backtest do not
see the same information set
- `_COL_AVAILABILITY_RULE["eurczk_mm"] = ("t+1", 1)` (`cz_struct.py:198`)
  nulls the month's FX at any EOM call; the backtest keeps the full-month
  average for every origin. FX is one of the three state-interacted
  variables, so the EOM live number and the backtest number are different
  models in high-inflation states. Fix: month-to-date average from daily
  CNB fixings in both paths (at day 30 it is 95% of the month), or mask it
  in the backtest as well and accept the accuracy cost.
- Same class: `household_exp` is pulled seasonally adjusted
  (`local_adapter.py:320`); Eurostat re-estimates the factors every month,
  so the historical values the backtest sees were not the values available
  at the time. The ridge has month dummies; use the NSA series, which is
  never revised.

### D6 (low, live only): basket publication date taken from the January flash
- `_basket_available_from` (`cz_struct.py:159`) keys on the survey table's
  January `release_dt`, which in the flash era is the flash date
  (2026-02-05). The new weights come with the full release (~Feb 10). Only
  the pre-release call for the January final can be affected. Fix: use the
  full-release date for January rows in the flash era.

### D7 (low): logging field is meaningless
- `panel_edge` (`cz_struct.py:957`) uses `dropna(how="all")` on a frame that
  contains month dummies, so it always reports the last index label
  (2026-09 today). Exclude deterministic columns.

### D8 (low, validation-only code): energy calculator L7
- `energy_accounting.py:94` looks up `eru_regulated_component_change_2022`
  at month `m`, but the parameter's window is 2022-01..2022-01, so the
  network uplift reverts in Feb-2022 (a spurious -2% x network share in the
  implied m/m). Same class as the L1-L6 list in REPLY_TO_CODEX_R3; add it.

### D9 (low): stale text and research code
- `local_adapter.py:158` still says "60/40 petrol/diesel blend";
  `late_info_tilt.py:73` still hard-codes 0.6; RUNBOOK line 31 still lists
  Brent under FRED; `data/admin_announcements.csv` is an unused template;
  `config.py` still carries Brent entries. None affect the frozen pair, but
  they contradict FUEL_SPEC_v23 and will mislead the next reader.

### Verified clean (so nobody re-audits them)
- Weekly fuel source: national rows only (3 per week, 529 weeks), so the
  pivot's `aggfunc="mean"` never averages regions. Cadence WEEKLY; the
  Aug-31 Monday was already in the file on Sep-6, so the true publication
  lag is <= 6 days. The +7d rule therefore discards the last Monday at every
  call; log fetch timestamp + latest week for a month to pin the weekday,
  then tighten (fuel RMSE is 0.264 EOM vs 0.187 pre-release, so the late
  Mondays carry information).
- Forest determinism: identical points over repeated fits under n_jobs=-1
  and n_jobs=1 (spread 0.00000). Codex's 0.003-0.02 pp cross-environment gap
  is not RNG. The TVW weights on the August call sit on their box bounds
  ({0.10: 0.00, 0.25: 0.35, 0.50: 0.376, 0.75: 0.15, 0.90: 0.124}); an
  active-set solution at a vertex flips with tiny numeric differences
  across SciPy builds, which is the likely mechanism. Freeze `w_` and the
  seven quantiles in the matrix export.
- Survey table: the 19 flash-era rows match the dedicated flash file
  exactly; the regular file's 2025+ rows are the contaminated final-survey
  ones (median == actual) and are correctly excluded.
- Both test suites pass (15/15).

---

## 2. What the evidence supports (recomputed)

Frame: 90 first releases 2019-02..2026-07, consensus and first-release actual
from the frozen survey table, model columns from `output/cz_struct_backtest.csv`.

Diebold-Mariano, squared loss, HAC(1), HLN correction (negative = model better):

| Column | all 90 | ex-Jan (83) | 2024+ (31) | flash 2025+ (19) |
|---|---|---|---|---|
| BASE_RIDGE (STRUCT) | 0.731 vs 0.382, p=0.16 | 0.405 vs 0.380, p=0.27 | 0.214 vs 0.241, p=0.19 | 0.166 vs 0.195, p=0.12 |
| cold PE (STRUCT_PE) | 0.734, p=0.18 | 0.389, p=0.57 | 0.229, p=0.67 | 0.165, p=0.13 |
| PE half | 0.731, p=0.17 | 0.394, p=0.44 | 0.219, p=0.34 | 0.163, p=0.08 |
| pre-release fuel | 0.729, p=0.16 | 0.404, p=0.28 | 0.215, p=0.20 | 0.165, p=0.10 |

Nothing clears 5%. Codex's block-bootstrap CI for the 2024+ ridge gain also
included zero. The honest status line: *recent frames lean model, the full
history and the ex-January history lean consensus, and none of it is
statistically resolved yet.*

Big-surprise panel (|s| >= 0.4, n=23), BASE_RIDGE: material W-L 6-3;
cumulative gain sum g = **-1.46 pp overall, +1.40 pp ex-January**;
bootstrap P(sum g > 0) = 0.35 overall, 0.98 ex-January. The four January
events contribute -2.86 pp (2022-01 alone -2.59). Ex-January the verified
model is worth about 0.07 pp per large surprise. The adopted warm PAST_FULL
(Codex's frozen column) is -0.48 pp overall on the same panel with 9-4.

Alerts (|model - street| >= 0.2), BASE_RIDGE: 19 total / 16 ex-January; closer
to the print 7 / 7; material 6 / 6; right direction 11 / 10. A raw
disagreement is a coin flip. Optimal ex-post shrinkage of the disagreement
ex-January: lambda* = 0.20 (ridge), 0.42 (cold PE); expanding-window
out-of-sample combination beats consensus only for PE and only marginally
(0.426 vs 0.435). Read: trust 20-40% of a disagreement, not 100%.

Per-block error budget (share of headline error variance, ex-January):

| Block | all 83 months | 2024+ (28 months) |
|---|---|---|
| core | 18% | 23% |
| food | 7% | **45%** |
| alcohol/tobacco | 4% | **18%** |
| admin | **61%** | 4% |
| fuel | 0.4% | ~0 |
| wedge + weights residual | 10% | 10% |

Headline ex-January RMSE 0.406 (all) / 0.190 (2024+). Raw block RMSEs
ex-January: core 0.306, food 0.782, alc 0.886, admin 2.187, fuel 0.264 EOM
and 0.187 pre-release.

January table (verified mode):

| Jan | STRUCT | actual | adm pred / actual | alc pred / actual |
|---|---|---|---|---|
| 2020 | 0.88 | 1.46 | 1.5 / 1.5 | 2.33 / 4.48 |
| 2021 | 0.81 | 1.34 | 1.4 / 0.5 | 2.76 / 3.16 |
| 2022 | 1.21 | 4.44 | 0.9 / 17.1 | 2.82 / 3.11 |
| 2023 | 1.17 | 6.01 | 0.9 / 30.9 | 2.86 / 4.01 |
| 2024 | 0.94 | 1.49 | 0.9 / 5.8 | 3.01 / 4.14 |
| 2025 | 1.20 | 1.32 | 1.4 / 0.8 | 3.13 / 4.14 |
| 2026 | 0.94 | 0.84 | 1.4 / -0.9 | 3.23 / 4.78 |

Alcohol/tobacco under-forecasts every January by 1.0-2.2 pp (-0.09 to -0.19
pp of headline). The verified admin seasonal base for 2025/2026 is 1.4
because the 2022/2023 prints sit inside the 10-year median window; the
scenario mode, which may exclude them, gives 0.9 / 0.65. Excluding a *past*
same-month print because of its own realized magnitude is not look-ahead;
the verified mode is paying a penalty it does not need to pay.

Two models share the name "past-error": the in-repo backtest column
STRUCT_PE is the cold-start version (first non-zero correction 2022-02;
0.734 / 0.229 / big-MAE 0.632 / 5-4), the adopted live challenger is Codex's
warm-history version (0.724 / 0.225 / 0.599 / 9-4). Their corrections
correlate 0.80 but differ by up to 0.36 pp in a month. The repo's own
backtest does not reproduce the adopted challenger's history; MODEL_CARD
describes the warm one, `scoreboards_codex_p0.py` scores the cold one.

Other evidence notes: the model targets the final print, scoring uses the
flash; 2 of 19 flash months were revised by 0.1 (2026-01, 2026-05). The
bands are computed for the legacy STRUCT_QRF only (coverage 83%). Threshold
counts flip on 0.0005 pp (Codex's example); report continuous g and
sum g / sum |s| next to any W-L. Setting `max_samples_leaf=None` in the
quantile forest (the library default of 1 keeps one random sample per leaf)
moves the August correction from 0.083 to 0.073 and is the textbook QRF; a
predeclared A/B candidate, not a silent change.

---

## 3. Tips, in the order I would do them

1. **Fix D1 before the Sep-30 EOM call** and re-log under a new tag. Do not
   backfill "corrected" August numbers as prospective evidence; they are
   retrospective by definition. The first clean prospective row is the
   September EOM call.
2. **Operational spine (D2, D3, D7):** refresh-before-call, imputed-feature
   list in every log row, 1-month tripwire, origins from `y.index`, and a
   fetch step for `data/cz_agri_prices_raw.csv` (today a one-off download
   with no writer in the repo). Run `capture_survey.py` in the same script
   as the call so the snapshot and the forecast share a clock.
3. **January package, all ex-ante legitimate:**
   - alcohol/tobacco block driven by the legislated excise calendar (the
     2024-2027 tobacco and alcohol schedule is in the consolidation
     package); at minimum a shorter same-month window;
   - admin seasonal base robust to past outliers by their own realized
     magnitude (e.g. drop past same-month prints beyond 3 MAD before the
     median), no calendar dependence, no provenance question;
   - a core January repricing term that scales with lagged inflation
     (mon_1 x trailing yoy), since the 4% dummy is off in calm years and
     January core still under-shoots (0.33 vs 0.8 in 2020, 0.37 vs 0.7 in
     2021).
   Then the energy ledger as already planned, with L1-L7 fixed first.
4. **Food block (45% of recent error):** use SA lags from the same
   one-sided X-13 run instead of NSA `food_l1`/`food_l12` (NSA lags mostly
   carry last month's seasonal into an SA target); wire the SZIF weekly
   farmgate reports as planned; keep the agri file fresh. Optional and
   flagged because you pushed back on German HICP earlier: the Destatis
   flash (day ~29 of t) and the GUS flash (day ~31) carry food components
   and are published *before* the EOM call, which is a timing advantage the
   consensus does not have at that point; continuity is via Destatis
   GENESIS, not Eurostat.
5. **Alcohol/tobacco block (18% of recent error):** replace the expanding
   same-month mean with a small ridge (own lags + excise dummies spread over
   Jan-Apr for old-stamp sell-through). Cheap, and it is the third-largest
   error source in the current regime.
6. **Surprise product as a calibrated tilt, not a binary alert:**
   f = consensus + lambda x (model - consensus), lambda estimated expanding
   out-of-sample and logged prospectively next to the point pair, plus
   P(|s| >= 0.15) from the past-error distribution (Codex Q2). The 44%
   alert hit rate is the argument for this.
7. **Reproducibility:** freeze `w_` and the quantile grid per call; record
   SciPy version; consider `max_samples_leaf=None` as a predeclared
   challenger setting.
8. **Vintage hygiene:** NSA household expectations (D5); the planned monthly
   feature-frame archive; pin the FX month-to-date rule.
9. **Evidence hygiene:** add DM p-values and bootstrap CIs to
   `scoreboards_codex_p0.py`; add a `STRUCT_PE_WARM` column in `main()` via
   `restored_pe_correction` so the adopted pair is backtested in-repo;
   compute bands for the adopted pair; decide flash vs final as the scoring
   target and say so once.
10. **Tests:** import-based fixture (D4); a live-row construction test (D1);
    an assertion that no released-source column is NaN at edge+1.

---

## 4. What is good and should not be touched

The component architecture with measured fuel; explicit `as_of` everywhere in
the model functions with fail-closed gates; the three provenance modes and
the refusal to score reconstructed Januaries as skill; predeclared adoption
rules with preserved prior outputs; the v2.3 fuel fix (component RMSE 1.11 ->
0.30 with one code path); the MODEL_CARD constant audit; the survey-capture
target check after the Sep-6 incident. The discipline is right. The gap is
that the discipline was applied to the backtest and the live path was assumed
to inherit it; D1 shows it did not.

## 5. Suggested items for the next Codex round

- D1 and its fix rule; ask Codex to re-run their frozen-input harness with
  an edge+1 origin to confirm the backtest is unaffected and the live path
  changes.
- D4 (their fixture) and D8 (add L7 to the energy list).
- Whether to declare the January package (3 items) as one predeclared
  experiment or three.
- Whether `max_samples_leaf=None` becomes a declared challenger setting.

## Errata and follow-up (7 September, after Codex round 4)

Codex reviewed this document against `1251fd8`
(`czech_cpi_fable_review/REVIEW_FOR_LUIS_AND_CLAUDE.md`). Corrections to
statements above, in the order they appear:

1. **§2 alcohol/tobacco January misses were overstated.** The seven
   misses are 2.15, 0.40, 0.29, 1.15, 1.13, 1.01 and 1.55 pp (2020-2026):
   under in 7 of 7 Januaries, by 0.3 to 2.2 pp, with five of seven above
   1 pp. "By 1.0-2.2 pp every January" was wrong for 2021 and 2022.
2. **§2 "Codex's block-bootstrap CI also included zero" was inaccurate**
   for the interval it referred to: the R2 six-month-block interval for
   the 2024+ ridge gain was [+0.00012, +0.02470] and excluded zero. The
   v2.3 recomputation (Codex R4) gives [-0.0011, +0.0250] with 6-month
   blocks, [-0.0063, +0.0322] with 3-month blocks and [+0.0013, +0.0225]
   with 9-month blocks: the sign of the lower bound depends on the block
   length, which is the honest way to state it.
3. **§0/D1 "+0.12 pp on the August call"** is a same-day recomputation
   with August ESI and FMIE stale in both variants, not an independently
   verified figure; Codex verified the defect, not the number. Under v2.4
   (same stale DB) the August dry run gives BASE_RIDGE +0.38 against the
   logged +0.27, consistent with it.
4. **Verified-clean, TVW weights.** The mechanism is now demonstrated,
   not only plausible: default SLSQP stops 1.2e-7 above the optimum (point
   +0.08323 vs +0.08349 on the frozen August matrices) and 1,789 weight
   vectors within 1e-4 of the optimum span 0.014 pp of point forecast.
   On this matrix the effect is smaller than the 0.003-0.02 pp
   cross-environment gap Codex measured, so it is a demonstrated
   contributor, not a proven sole cause.
5. **§2 error budget** used approximate weights summing to 1.0 (core
   .565, food .177, alc .085, admin .14, fuel .033) while MODEL_CARD's
   displayed weights summed to 104%; Codex's per-origin recomputation
   gives the same ordering for 2024+ ex-January (food 42.6%, core 20.0%,
   alc 17.9%, admin 4.5%, fuel -0.9%, remainder 15.7%). MODEL_CARD is
   corrected.
6. **D6 fix suggestion** ("use the full-release date") is itself an
   assumption; the basket publication date should come from a CZSO source
   (Codex).
7. **§2 shrinkage** recomputed with the warm challenger from Codex's
   frozen forecasts: expanding out-of-sample lambda 0.32-0.38, combined
   0.426 vs consensus 0.435, DM t = -1.1. Same conclusion; it remains a
   research product, not a trading rule.

Codex's additional findings accepted and acted on in v2.4
(`LIVE_PARITY_SPEC_v24.md`, `REPLY_TO_CODEX_R4_2026-09-07.md`): release
event vs database edge (the Sep-6 August call was post-flash), the unused
`as_of` in `restored_pe_correction`, the cold/warm naming, the fuel
blend's weight basis (<= 0.008 pp, deferred to the next batch), the fuel
adoption rule not literally met (recorded as an exception), the 104%
weights, the archive-failure path, the day-7 flash counterexamples, the
midnight release time in the prospective classifier, the ledger's
treatment-only clock and date errors, and three energy-calculator
arithmetic errors (cap netting network, POZE taxed twice, 2022 network
change vanishing in February).

## Appendix: how the checks were run

- Tests: `python -m pytest test_p0_regressions.py test_struct_acceptance.py -q`.
- D1: load `output/matrices/2026-08_20260906T141544.npz`, list
  `feats_cols` where `feats_row` is not finite; then `cz_struct.load_all()`
  and inspect `feats.loc["2026-08"]` / `food_feats.loc["2026-08"]`; rebuild
  the row from `core`, `load_services_cpi_mm()`, `fetch_import_prices_mm_live()`
  and `load_headline_cpi_mm_extended()` and call `_ridge_predict` /
  `food_forecast` on both frames.
- D4: replicate the fixture's AST extraction and call
  `_basket_available_from(2026)` inside it vs `cz_struct._basket_available_from(2026)`.
- Statistics: `output/cz_struct_backtest.csv` joined to
  `data/czcpmom_survey_history_extended.csv` (era != flash_survey_suspect),
  DM with HAC(1) + HLN, 20k-draw bootstrap on the 23 large-surprise gains,
  error budget with weights core .565 / food .177 / alc .085 / adm .14 /
  fuel .033 and fuel actuals from `cpi_czso.cpi_long` subgroup 0722.
