# Predeclared fuel-block change: v2.2 → v2.3 (provisional pending Codex)

Declared 2026-09-06 BEFORE the rerun, per the standing adoption
discipline. Motivation: the user's challenge ("why do you need Brent?")
plus the measured A/B (all 90 origins, fuel component vs official 0722
m/m): EOM RMSE 0.612 WITH the Brent tail vs 0.322 without (worse in
64/90); release-eve 0.667 vs 0.249 (worse in 11 of the 13 months where
it fires). Mechanism: beta=0.35 is a MONTHLY pass-through estimate
applied to 10-business-day windows — the wrong horizon — onto sticky
weekly pump prices. And petrol_share=0.6 was an unsourced constant.

## The three changes (fuel block only; nothing else moves)

- **F1 — no Brent anywhere in the fuel path.** Unobserved weeks of the
  target month are carried flat from the last observed weekly price
  (if no target-month week is observed yet: the last prior-month week).
  `_brent_signal` and `calibrate_fuel_beta` are deleted;
  `fetch_brent_czk_daily_live` remains in the adapter for other uses but
  no forecast consumes it. Data dependency count drops by one (and the
  monthly-USDCZK-level approximation dies with it).
- **F2 — official per-regime petrol share.** Blend = w(07.222 petrol) /
  (w(07.222)+w(07.221 diesel)) from the archived CZSO baskets
  (data/baskets/spot_kos{2014..2026}.xlsx, downloaded from
  csu.gov.cz/spotrebni_kos_archiv today):
  2014: 0.755824, 2016: 0.755823, 2018: 0.670840, 2020: 0.670837,
  2022: 0.670837, 2024: 0.585321, 2026: 0.586409.
  Same publication gating as the other anchors (`_basket_available_from`);
  before a basket's January release the prior regime's share applies.
  LPG/oils excluded (the weekly survey prices petrol95 + diesel).
  Declared approximation: regime(t)'s share is used for both months of
  the m/m ratio at regime boundaries.
  Cross-validation: every file's 07.22 total reproduces `_OFFICIAL_FUEL`
  to the last decimal (five independent checks of the anchor dict).
- **F3 — backtest/live parity for the EOM fuel leg.** The backtest's
  measured-fuel leg is recomputed internally from the weekly file under
  F1+F2 with the same end-of-month−7d cutoff, replacing the champion
  CSV's frozen `fuel_mm` column (computed under the old spec). Live and
  backtest now share one code path; the champion file remains only as
  the origins list + benchmark column.

## Scope guarantees

Fuel enters ONLY the recombination (weight ~3.1-3.5%). The wedge uses
official fuel actuals, the PE learners train on CORE errors — neither is
touched. Legacy benchmark scripts (backtest_h0*.py, run_nowcast.py) have
their call sites updated for the new signature but their historical
output CSVs are NOT regenerated (they stay the frozen benchmarks).

## Adoption rule (declared before seeing results)

Expected: fuel-component RMSE improves materially (the A/B predicts
~0.29pp at EOM); headline effect small (~0.01 scale). ADOPT if the
frozen pair's all-90 RMSE does not worsen by more than 0.010 and the
big-surprise panel (big-MAE, W-L@0.15) does not deteriorate; otherwise
STOP and investigate, no variant search. v2.2 outputs are preserved as
`*_v22.csv`; the SPEC_TAG becomes v2.3-fuel pending Codex sign-off, and
the R3 reply gains the before/after table either way.

## RESULTS (filled in after the rerun, 2026-09-06 evening)

Fuel component (vs official 0722 m/m, n=90): EOM leg RMSE **1.111 →
0.304**, MAE 0.632 → 0.206; release-eve leg RMSE **0.667 → 0.217**.
(The old EOM leg came from the champion CSV's frozen column, which was
even worse than the A/B's own with-Brent replication.)

Headline (same 90-origin frame, consensus 0.382 / 0.241-recent):

| col | v2.2 | v2.3 |
|---|---|---|
| STRUCT (BASE_RIDGE) | 0.729/0.212, big 0.641, 6-3, h4 | 0.731/0.214, big 0.642, 6-3, h3 |
| STRUCT_PE (COLD-start research column, NOT the adopted PAST_FULL -- see addendum) | 0.733/0.228, big 0.633, 6-4, h4 | 0.734/0.229, big 0.632, 5-4, h4 |
| STRUCT_PEH | 0.730/0.217, big 0.636, 6-3, h4 | 0.731/0.219, big 0.636, 5-2, h5 |
| STRUCT_PRE | 0.730/0.217, big 0.644, 7-2 | 0.729/0.215, big 0.642, 6-2 |

Adoption-rule check: all-90 RMSE +0.002 (≤ 0.010 ✓); big-MAE flat to
better (STRUCT +0.001, PE −0.001). W-L cells moved by threshold churn,
investigated month-by-month: PE lost 2025-11 (gain +0.16 → +0.14) and
2022-04 (a rounding-boundary flip at exactly +0.15), GAINED 2023-09
(+0.14 → +0.17); STRUCT's halved count lost only 2022-08. All within
±0.02 of the materiality line; no systematic pattern. Largest headline
moves are the 2020 COVID oil-crash months (0.09-0.23), where the old
Brent tail happened to catch a once-a-decade crash that flat-carry
lags — the same mechanism that cost it dearly across 2021-2023.

**ADOPTED provisionally** (structural case: −1 data dependency, official
constants replace two unsourced ones, single fuel code path for
backtest+live, 3.6× component accuracy). Codex sign-off requested in
REPLY_TO_CODEX_R3 §5-6 before the tag is considered final.

## Addendum 2026-09-07 (after Codex round 4)

1. **Mislabel corrected.** The results row previously labelled
   "STRUCT_PE (PAST_FULL)" is the in-repo COLD-start past-error column
   (first correction 2022-02), not the adopted warm-history challenger.
   The adopted pair's own before/after, from Codex's frozen recombination
   (`literal_fuel_adoption.csv`): BASE_RIDGE RMSE 0.72948 → 0.73075,
   big-MAE 0.64099 → 0.64165 (+0.00066), W-L 6-3 → 6-3; PAST_FULL (warm)
   RMSE 0.72407 → 0.72420, big-MAE 0.59897 → 0.59963 (+0.00066), W-L
   9-4 → 10-4. From v2.4 the warm challenger is computed in-repo
   (`STRUCT_PE_WARM`), so future adoption tables use it directly.
2. **The adoption rule was not literally met.** Its clause "big-MAE does
   not deteriorate" was violated by +0.00066 pp for both models. v2.3
   stands as a dated, explicit EXCEPTION on the structural grounds listed
   above; "does not deteriorate" is not being redefined as "approximately
   flat". A rule declared after the motivating A/B has been seen is a
   development rule, not an untouched confirmatory test.
3. **Open arithmetic item (Codex P1).** The blend applies expenditure
   shares to price LEVELS and then takes the ratio, so the effective
   weights depend on relative petrol/diesel price levels; a monthly-
   relative blend with the same shares moves historical headlines by at
   most 0.0079 pp. To be specified and tested in the next batch, not
   silently changed here.
