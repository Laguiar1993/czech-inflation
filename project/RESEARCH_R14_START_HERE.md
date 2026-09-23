# CZK Cpi Forecasting - Latest models

R14 / R14B, 9 September 2026. Read
`docs/implementation/R14_RESULTS_2026-09-09.md` first. It records the current
assessment, successes, failures, benchmark definitions and next experiments.
Earlier nowcast and path results are retained. No operating model was replaced.

## Small working roster

- Independent next-release forecast: unchanged HARD_BASE and existing Half/Full
  challengers. No survey or expectations were added.
- Path reference: INDEPENDENT_BRIDGE.
- Conservative path challenger: STABLE_PIPELINE_R14B, stable food plus constant
  latest observed pump prices, original core.
- Current-regime challenger: STABLE_LOCAL_CORE_R14B, same food/fuel plus recent
  core trend. Strong recent results, poor 2023-to-2024 deceleration forecasts.
- Econometric challenger: STABLE_LONG_CORE_R14B, same food/fuel with longer-history
  core level ridge. Keep the gap model and other controls in research tables.
- FUEL_ECM_R14 is a near-term component challenger. Original food level VAR and
  all three original R14 combined paths are rejected for operating use.

## Frozen reproduction

Use Python and packages in `requirements-r9-lock.txt`. Where the original bridge
is refitted, Census X13 must be installed and `CZ_X13_PATH` must point to its
executable. The survey manifest records the expected X13 SHA256 and numerical
package versions. A different binary may change seasonal factors; do not claim
byte parity without matching that identity. No live DuckDB database is needed.

From this directory:

```text
python core_learning_experiment_r14.py --verify
python core_learning_experiment_r14.py --feature-extension data/research_r14b/imports --output-dir output/research_r14b/core --verify
python food_path_experiment_r14.py --verify
python food_stable_experiment_r14b.py --verify
python fuel_path_experiment_r14.py --verify
python core_history_comparison_r14b.py --verify
python path_integration_r14.py --verify
python path_stable_integration_r14b.py --verify
python survey_benchmark_r14.py --include-stable --include-extended --verify
python path_attribution_r14.py --verify
```

The core, food, fuel and survey commands re-estimate their models; the other
commands rebuild evaluations from frozen forecasts. `--verify` checks source
and output hashes and prevents network access. Original and extended core labels
are identical inside their separate directories; the joint integration tables
rename extended controls with `_EXT_R14B` to distinguish the data policy.

Important: `core_learning_experiment_r14.py` without `--verify` writes outputs;
the extended refit also needs `--declaration 709d4b3` to preserve its declaration
metadata. Prefer `--verify` when validating a delivered package.

## Files by purpose

| Purpose | Location |
|---|---|
| Model and timing declarations | `docs/implementation/R14*` |
| Source papers, official survey audit, independent core review | `docs/implementation/R14_PAPERS_AND_BENCHMARKS.md` |
| Public fuel, food and benchmark source snapshots | `data/research_r14/` |
| Independently matched older import history | `data/research_r14b/imports/` |
| Original core / failed level-food / fuel experiments | `output/research_r14/core/`, `food/`, `fuel/` |
| Stable food and longer-history core | `output/research_r14b/food/`, `core/` |
| Original/extended core paired data-policy comparison | `output/research_r14b/core_history_comparison/` |
| Complete combined paths and CNB scoreboards | `output/research_r14b/integration/` |
| Independently refitted dated FMIE comparisons | `output/research_r14/survey/` |
| Component errors and perfect-future diagnostic replacements | `output/research_r14b/attribution/` |
| Regression and independent-review receipts | `output/research_r14/review/` |

The stable integration native file includes the reference and all four combined
challengers, with each component, its weight, contribution, as-of clock and
exact annual result. The latest archived path is a July 2026-origin research
forecast, not a freshly run September nowcast. FMIE is an external one-year
benchmark here; the stored series does not provide a six-month CPI forecast.

The delivery ZIP contains all tracked code, data and research evidence plus Git
history. Its external receipt records checks on a fresh extracted copy. It is a
portable research package; live refresh, historical vintage certification and
production trading readiness remain separate work.

## Bloomberg refresh on 9 September 2026

The new market-data snapshot is `data/market_snapshots/20260909_bloomberg_y1/`.
It holds the user-selected FSBTY1 Index and TTFGCY1 Index, Brent reference
generics, USD/CZK, EUR/CZK, PRIBOR and seven existing FRA tenors through
8 September. Both annual energy series begin in 2013. The folder README and
MANIFEST describe the raw data, derived monthly panels and availability limits;
`tools/market_data/README.md` explains refreshing and offline preparation.

This is a new input archive for the forthcoming path comparisons. It does not
change the frozen R14/R14B forecasts or the independent nowcast specification.
Do not read the refreshed data as evidence that a futures-conditioned model
already outperforms the baseline. No inflation survey was added as an input.
