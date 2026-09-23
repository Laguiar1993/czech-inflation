# CZ-STRUCT model card: what it is, what it eats, every constant it contains

Current status and operating roster: see docs/MODELS.md and
docs/LIVE_READINESS.md. The September 7 cleanup preserves this numerical
inventory; it does not certify the provisional live pipeline.

Written 2026-09-06 on the user's request for a full hard-coded-number
review. This is the honest inventory: every number in the forecast path,
classified by where it came from, plus the definitive list of data the
model needs going forward. Scope = the forecast path (`cz_struct.py`,
`models/components.py`, `data/local_adapter.py`). The energy calculator
is validation-only, never feeds a forecast, and has its own audit list
(REPLY_TO_CODEX_R3 §4).

---

## 1. The model in plain terms

Headline CPI m/m is forecast as five components + a wedge:

| Block | Weight at the 2026-07 origin | Method | Key inputs |
|---|---|---|---|
| CORE | 53.9% (residual) | Expanding ridge on CNB core m/m; hard high-inflation state dummy (trailing yoy > 4%) interacting FX/expectations/imports | CNB core, FMIE exp 12/36m, household exp, ESI, EURCZK, services l1, imports l2, core lags |
| ADMIN | 17.9% (solved coefficient) | Seasonal median of released CNB regulated m/m + a January announcement gate (see §3B — no magnitude enters the primary mode) | CNB regulated series, announcement calendar |
| FOOD | 16.9% (official basket) | Per-origin ONE-SIDED X-13 seasonal adjustment + ridge on the pipeline | food CPI lags, agri producer prices l1, food-products PPI (CPA-10) l1 |
| ALC/TOB | 8.3% (official basket) | Expanding same-calendar-month mean | division 02 m/m |
| FUEL | 3.1% (official basket) | Measured: weekly pump prices averaged into the month, official basket blend; missing weeks carried flat (v2.3 — the Brent tail was removed after a measured A/B showed it hurt) | CZSO weekly petrol/diesel |
| WEDGE | — | Expanding same-month mean of the historical aggregation residual under the solved weights | all of the above |

Weights are per-origin OUTPUTS of `solve_weights` (the column above is the
2026-07 origin; earlier origins differ, see Codex `per_origin_weights.csv`):
food/fuel/alc pinned to the **official CZSO basket** per even-year regime
(publication-gated); the admin share is a solved projection coefficient
(clipped 0.08–0.30), NOT the official CNB regulated-price expenditure
share; core = 1 − rest, so weights sum to 1 exactly. (Corrected 2026-09-07:
the earlier rounded "~62/17/3/14/8" summed to 104% and mixed the official
core concept with the fitted coefficient — Codex R4.)

Two models are live (the frozen pair): **BASE_RIDGE** (the above) and
**PAST_FULL** (same + a quantile-forest correction learned from the ridge's
own past errors, only errors released by the call date). PAST_HALF = half
that correction. Everything else in the backtest CSV is benchmark or
labelled scenario.

## 2. Data needed going forward (the complete live dependency list)

Monthly refresh = `python update_cz.py` (fills `~/economic_db/czechia.duckdb`),
then `python cz_struct.py` sanity backtest, then `struct_live()` per RUNBOOK.

| # | Input | Official source | Cadence, availability | Feeds |
|---|---|---|---|---|
| 1 | CPI by division (headline, 01 food, 02 alc, 0722 fuel, services) | CZSO (Rychlé informace + open data) | monthly, ~10th for prior month (flash ~day 4-6 since 2025) | targets, lags, weights |
| 2 | CNB core inflation m/m (`SCPIMZM09MOMPECNA`) | CNB ARAD api.cnb.cz | monthly, with CPI | CORE target |
| 3 | CNB regulated prices m/m (`SCPIMZM02MOMPECNA`) | CNB ARAD | monthly, with CPI | ADMIN target |
| 4 | Inflation expectations 12m/36m (FMIE mean) | CNB FMIE via consensus schema | monthly, ~16th | CORE features |
| 5 | Household price expectations (BS-PT-NY, SA) | Eurostat `ei_bsco_m` | monthly, ~28th | CORE feature |
| 6 | ESI Czech Republic | Eurostat BCS | monthly, ~28th | CORE feature |
| 7 | EURCZK monthly average m/m | CNB FX fixings | daily; full-month avg usable from day 1 of t+1 | CORE feature |
| 8 | Import price index m/m (CEN0301) | CZSO open data | monthly, ~16th, used at lag 2 | CORE feature |
| 9 | Agricultural producer prices (CEN0203B, national rows) | CZSO open data | monthly, ~16th, used at lag 1 | FOOD feature |
| 10 | Food-products PPI, CZ-CPA 10 (CEN0201B IZ2015) | CZSO open data | monthly, ~16th — publishes AFTER the flash, so only lag 1 is ever used (user-verified timing) | FOOD feature |
| 11 | Weekly pump prices petrol95/diesel (CENPHMT) | CZSO weekly | Mondays, public ~+7d | FUEL |
| 12 | ~~Brent daily + USDCZK~~ | — | — | REMOVED in v2.3 (FUEL_SPEC_v23.md): the tail projection hurt measurably; no forecast consumes Brent |
| 13 | Consensus snapshot (CZCPMOM median/mean + ECO_RELEASE_DT) | Bloomberg via `capture_survey.py` | before each release | scoring ONLY — never a model input |
| 14 | Basket weights (c_basket spreadsheet) | CZSO, with the January release of each even year | biennial | `_OFFICIAL_*` anchors |
| 15 | ERÚ price decisions + government energy decrees | eru.gov.cz, zakonyprolidi.cz | annually ~Nov 28 + ad hoc | admin calendar + energy ledger, prospective rows only, per ANNOUNCEMENT_PROTOCOL.md |
| 16 | M3, house prices, construction PPI | CNB/CZSO (already availability-shifted) | monthly/quarterly | h6/h12 horizons ONLY |

Also required on the machine: the X-13ARIMA-SEATS binary (path in
`local_adapter._X13_PATH` — hard-coded, a portability item, deferred per
user) and DuckDB `czechia.duckdb`. The consensus survey is used ONLY for
scoring and for release-date metadata (basket publication dates, fuel
pre-release cutoffs) — **no forecast consumes the survey value**.

## 3. Every constant in the forecast path, classified

### A. OFFICIAL, SOURCED (verified against source documents)

- `_OFFICIAL_FOOD/FUEL/ALC` per even-year regime — CZSO archived baskets.
  Cross-validated again today: the 2026 basket PDF (`data/czso_spot_kos2026.pdf`)
  shows 07.22 = 30.630713‰ = the dict's 0.030630713 exactly.
- `OFFICIAL_PETROL_SHARE` per even-year regime (v2.3/F2) — petrol/(petrol+
  diesel) item weights from the archived basket XLSX files in
  `data/baskets/` (0.7558 / 0.6708 / 0.5853 / 0.5864 across regimes);
  each file's 07.22 total independently reproduces `_OFFICIAL_FUEL`.
- Basket publication dates — actual January release dates from the survey
  table's ECO_RELEASE_DT (Feb-15 fallback for pre-2019, declared).

### B0. v2.7 (7 Sep 2026, user decision): documented announcement entries ARE in the primary forecast

`ANNOUNCEMENT_ADOPTION_v27.md`. The administered block's January gate now
reads provenance `documented` = {`sourced_retrospective`, `prospective`}:
entries built by the frozen rule from documents dated before the January
they price (ERÚ decisions, supplier price lists, VAT decisions, cap
decrees, CZSO treatment notes), each with its publication date; the row
with the latest date on or before the decision clock governs. v2.7.1
(Codex R8, same day): each row stores the per-fuel January change in
percent (`elec_pct`, `gas_pct`, `heat_pct`); the headline contribution is
sum(basket item weight / 1000 x change) with the electricity / network-gas /
heat weights of the basket PUBLISHED at the clock, the gate fires when that
contribution is at least 1.1 pp in absolute value, and the block value is
the contribution divided by the administered weight of the same call, so
no fitted coefficient is stored as data and the headline effect is
weight-independent. In the 90-origin history this fires twice, January
2022 (+3.13 pp; electricity +42.4% with the ERÚ regulated / commodity
shares 52.3 / 47.7, gas +68.5%) and January 2023 (+3.66 pp; electricity
+92.3% as a credit-only additive reversal, the POZE waiver continuing
through 2023), and nowhere else. The rule was written in 2026 with the
outcomes known; the "gate closed" reference is kept as `STRUCT_NOANN` /
`STRUCT_NOANN_EVE` on every board so the effect is never hidden, and from
January 2027 the entries are prospective. Section B below describes the
older `reconstructed` rows, which still enter only the scenario column in
their original block units.

### B. SCENARIO-ONLY numbers (reconstructed rows; never in the primary forecast)

The user's specific doubt — "the stuff for admin" — lands here, and the
answer is clean: **in `verified_only` mode (the primary, and the only mode
scored on the headline boards) the admin block contains NO hard-coded
magnitudes at all.** It is a seasonal median of released CNB regulated
prints, full stop. The announcement calendar's numbers:

- 16.5 = announced ~30% bill change × 0.55 energy-share mapping, for
  Jan-2022 and Jan-2023 — `provenance=reconstructed`, typed AFTER the fact,
  admitted only into columns suffixed `_R` which are labelled scenario
  evidence and kept apart from verified results everywhere.
- 2024/2025 rows (+3.0 / −5.0) never fire (gate needs |a| ≥ 8).
- The 2026 row is VOIDED (Codex audit: magnitude misdated).
- The ×0.55 mapping itself is flagged crude; the November-2026 prospective
  entry will come from the bottom-up energy ledger under
  ANNOUNCEMENT_PROTOCOL.md (typed before the January it prices, externally
  timestamped) — not from this multiplier.

### C. DECLARED RULES (documented choices, not data)

- Availability calendar (`_COL_AVAILABILITY_RULE`): expectations day 16,
  EC surveys day 28, EURCZK day 1 of t+1, imports day 16 — publication
  RULES, not recorded vintages (stated in code); to re-verify against
  actual calendars once a year. CPI-family lags (core_l1, food_l1,
  services_l1, state) follow the sourced release calendar in BOTH the live
  row mask and the missing-input classifier (v2.6, Codex R6 blocker 1; the
  day-11 rule is gone for them).
- Fuel publication lag: Monday observation + 7 days. Brent cutoff = as_of.
- Announcement gate threshold |a| ≥ 8 pp; admin weight clip 0.08–0.30
  (sanity bounds around CNB's historical ~0.13–0.20 share).
- Minimum-observation floors: ridge 48, PE warm 40, PE cold 36, legacy
  forest 60, band pool 24, seasonal same-month 3, wedge 2, regime rows 4.
- Windows: admin seasonal median last 10 same-months (fallback last 24
  months), X-13 seasonal factor last 3 same-months, h≥1 fuel same-month
  median last 8, feature frame extended 2 months past the CPI edge,
  freshness tripwire at 6 months.

### D. HYPERPARAMETERS (dev-selected; the honest selection-bias residue)

- `RIDGE_ALPHA = 3.0`, `TVWQRF n_estimators = 200`, band quantiles 5/95.
- `STATE_THRESHOLD = 4.0` (trailing compounded yoy) — economic anchor:
  the top of the CNB tolerance band (2% ± 1) is decisively breached at 4;
  the smooth-transition alternative was predeclared, tested, and REJECTED
  on untouched frames. But the value itself was chosen knowing the
  2021-23 episode existed — disclosed, not eliminable retroactively.

These were all chosen during development by someone (me) who could see
backtest results across iterations. That is ordinary model development,
not target-leaking, but it means **there is no untouched holdout**; the
cure is the prospective shadow ledger, which is why it exists.

### E. APPROXIMATIONS THAT SHOULD BECOME OFFICIAL NUMBERS (the real findings)

1. ~~`petrol_share = 0.6`~~ **RESOLVED (v2.3/F2, same day)**: replaced by
   `OFFICIAL_PETROL_SHARE` per regime from the basket archive,
   publication-gated. See FUEL_SPEC_v23.md.
2. ~~Brent pass-through `beta = 0.35`~~ **RESOLVED (v2.3/F1)**: the tail
   projection was removed entirely after the measured A/B showed it hurt
   (EOM fuel RMSE 0.612 with vs 0.322 without); `_brent_signal` and
   `calibrate_fuel_beta` deleted.
3. ~~Daily Brent-CZK FX kludge~~ **MOOT (v2.3/F1)**: no forecast consumes
   Brent anymore.
4. ~~`alc` weight seed 0.087~~ **replaced (v2.6)** by the sourced ECOICOP 02
   share of the 2014 basket, 0.09498 (`_ALC_TOBACCO_WEIGHT_PREANCHOR`);
   pre-anchor fallback only, no evaluated origin uses it (frozen replay
   identical).
5. **Feb-15 basket-publication fallback** for years before the survey
   table — replace with a sourced CZSO release ledger when found.
6. `COMPONENT_WEIGHTS_FALLBACK` (0.575/0.188/0.202/0.035, config.py) —
   legacy four-block scaffold; in the current model it only seeds
   `solve_weights.prev` before the first official anchor and the
   diagnostic wedge index in `load_all`. Retire it in the same batch as
   REFACTOR_QUEUE #1.

### F. Note on the OTHER files

`backtest_h0_enriched.py` and the champion/benchmark scripts contain their
own constants; they produce comparison columns, not the frozen pair.
`energy_accounting.py` (validation-only) has known in-code literals —
already on the merge list with Codex (R3 §4, L5).

## 4. No-cheating status (what protects the forecast path)

- Explicit `as_of` on weights, admin, announcements, fuel; fail-closed on
  undated/NaT/unknown-mode; oracle paths require `allow_oracle=True`.
- Provenance modes keep verified / reconstructed-scenario / prospective
  evidence in separate columns; scenario numbers cannot reach the primary.
- Past-error learners train only on errors of months released by the call
  date (u ≤ t−1 sequential registration; warm history is frozen input).
- Survey is never a feature. PPI enters only at the lag its publication
  calendar allows. Basket anchors wait for their publication date.
- Live target month derives from the data edge (`h0_edge_gap` logged);
  live rows are masked by the availability rules at the actual timestamp.
- Remaining known gaps, disclosed: underlying loaders serve latest
  vintages (revisions to non-CPI features are not replayed — vintage
  archiving starts this month); backtest as_of = end-of-month assumption;
  availability days are rules, not recorded timestamps.

## 5. Standing verdict

The model's numbers divide into: official (A, sourced and re-verified),
scenario-only (B, quarantined by provenance), declared rules (C), dev
hyperparameters (D, disclosed residue, cured only by the prospective
ledger), and five approximations to upgrade (E). Nothing in the primary
path is a tuned magnitude pretending to be data. The E-list plus
REFACTOR_QUEUE.md are the entire cleanup backlog; each item goes through
predeclare → re-run → adopt, never a silent edit to the frozen spec.
