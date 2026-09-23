# R14B import-price history audit and missing-only extension

9 September 2026. Data audit only; no model estimation or forecast scoring.

## Decision and exact extension contract

The official national import-price total supports extending the existing core
predictor back to January 2008 source months. Preserve every original finite
feature cell and every other column. Fill only the 84 missing import_l2 cells at
fixture periods March 2008 through February 2015, representing source months
January 2008 through December 2014. Do not append rows, overwrite overlap,
recompute interactions, or add June 2026 to the frozen feature history.

The existing 137 finite import_l2 observations represent January 2015 through
May 2026. Their values match the independently selected official SITC total to
floating precision. Thus current-origin predictor values remain identical; only
the usable historical training information becomes longer. Estimated parameters
and forecasts can consequently change. The 12-month import feature can first
become complete at a March 2009 pseudo-origin, subject to other inputs.

The source contract for the new extension is
`data/research_r14b/imports/core_feature_extension.csv`: exactly the columns
period, import_l2, available_from; period is the original fixture month, uniquely
sorted. available_from is source month plus three, first day at 00:00 in
Europe/Prague, serialized with its historical UTC offset. The full copied
`core_features_extended.csv` is supporting evidence; integration should replay
the old inputs first and then merge only the 84 explicitly permitted cells.

## Provenance and independent comparison

The prior cache `data/czso_import_prices_sitc_monthly.csv` entered the repository
in commit d6e7017 on 8 September 2026 with `path_step4_backtest.py` and
PATH_SPEC_v4 amendment 2. Its 222 observations run January 2008 to June 2026.
The old downloader used heuristic classification selection. This audit does
not rely on that heuristic: it freshly saves both official datasets, reads all
code fields as strings and requires the explicit national total and plain
monthly period codes. Duplicate selected months fail rather than being dropped.

- [Official SITC raw CEN0303](https://data.csu.gov.cz/opendata/sady/CEN0303/distribuce/csv):
  IndicatorType 614703, TYPUDAJE5B IM, SITCVAD 00890001, Uz0 CZ,
  CASMKMQRM12 matching exactly YYYY-MM. Hodnota minus 100 is arithmetic m/m
  percentage change. Export prices, sections, annual/quarterly indices and
  cumulative YYYY-MMK records are excluded.
- [Official CPA raw CEN0301](https://data.csu.gov.cz/opendata/sady/CEN0301/distribuce/csv):
  same indicator, index type, country and plain month rules, with explicit
  CZ-CPA aggregate label Úhrn celkem. This is the total used by the original
  `data/local_adapter.py:fetch_import_prices_mm_live` core loader.
- [Official CEN0303 catalog](https://data.csu.gov.cz/api/katalog/v1/sady/CEN0303/vybery)
  identifies monthly SITC price indices unadjusted for exchange-rate effects.

The reproducible comparison aligns core feature period minus two with source
month. `overlap_comparison.csv` retains every source-month value and difference;
`overlap_summary.csv` reports counts and exact maximum differences. Acceptance
is stricter than the requested 0.1 percentage-point rounding tolerance: every
overlap must differ by no more than 1e-10. No rescaling or fitted splice is used.
Expected coverage is 222 official SITC versus prior-cache months, 138 versus
official CPA total months, and all 137 existing finite core observations.

## Source definition, weights and methodological limits

The measured prices are Czech-koruna transaction prices including exchange-rate
effects; they exclude customs duty, VAT and excise. This is not an import unit
value, an exchange-rate-adjusted series or a manufacturing-only price proxy.
CZSO constructs the national index in CPA and also publishes SITC groupings.
The total has exact numerical parity across these classifications in the
available overlap. [CZSO price methodology](https://csu.gov.cz/indexy_cen_dovozu_a_vyvozu)

Weights and representative products change at official revisions. January 2024
introduced 2021 foreign-trade weights, linked into the existing 2015-base series;
CZSO says the previously published indices remain valid. The official revision
note is archived with this audit. We use the published total directly and do
not reconstruct older totals with current weights or infer section-level
continuity from total parity. [2024 revision note](https://csu.gov.cz/docs/107516/cb4c358c-276c-6fef-997d-246c47e2a14d/standardni_revize_indexu_vyvoznich_a_dovoznich_cen.pdf?version=1.2)

The statistical methodology describes the series as comparable over time,
unadjusted for seasonality, and final without ordinary subsequent revisions.
This supports a research extension of the same aggregate concept, not a claim
of constant baskets or a complete historical vintage audit. Downloaded files
are latest-vintage extracts frozen today; every raw file, source URL, completion
timestamp and hash is retained. [Statistical methodology](https://csu.gov.cz/metodika-statistiky-za-oblast-indexy-cen-vyvozu-a-dovozu)

## Publication clock: a verified exception and conservative rule

Do not claim that the old day16-of-source+2 convention is universally safe.
January 2008's flash was released 14 March 2008 and reports -0.6% m/m, matching
the new source. [January 2008 release](https://csu.gov.cz/rychle-informace/indexy-cen-vyvozu-a-dovozu-leden-2008-ac9y0iu5ch)
January 2014's flash was released **17 March 2014**, reports -0.4%, and announces
the next flash for 16 April. [January 2014 release](https://csu.gov.cz/rychle-informace/indexy-cen-vyvozu-a-dovozu-leden-2014-1xh613weya)
The current official release for June 2026 is dated 11 August 2026.
[Current release page](https://csu.gov.cz/ceny-vyvozu-a-dovozu)

For all 84 new cells use source+3 month start as an explicit conservative
availability reconstruction, at least as late as the old day16 rule. This
avoids the verified March 2014 exception. It is not a collected 84-month release
calendar. Existing finite input cells and their legacy clock convention are
untouched. R14 uses import source r-3 at pseudo-origin r; the new bound is the
start of r, before its normal CPI decision clock. This makes the richer history
usable without pulling forward any additional current-month source information.

## Reproduction and boundary checks

`tools/r14b_imports/prepare.py` performs no network access and no fits. It checks
official selectors, contiguous coverage, exact overlaps and the 84-cell change
mask, then writes five CSV artifacts plus a hashed manifest. `--verify` checks
all frozen inputs and reconstructs every output in a temporary directory,
requiring the full manifest to match. Tests were written and observed failing
before the preparer existed; they cover source selection, duplicate rejection,
the late publication example and preservation of finite, unrelated and newest
cells. Preparation leaves the original core fixture and old cache untouched.

This audit proposes data for a separately declared model rerun. It authorizes
no new features, parameter changes, empirical selection or model promotion.
