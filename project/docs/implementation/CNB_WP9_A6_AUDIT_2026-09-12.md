# CNB WP 9/2026 Table A6 audit — 12 September 2026

This continues `HANDOFF_TO_CLAUDE_2026-09-11.md`. The 11 September Bloomberg
capture was imported as a separate candidate panel and every candidate was
compared with official sources. The 72-row audit was then rebuilt with separate
exact and candidate input panels. The independent nowcast, the path lanes and
every tracked file are unchanged. The one edit to existing code is the row-38
transform in `paper_replication_experiment.py`.

**Revision, same day.** Extending the producer-price history exposed a loader
bug in the 20260910 runner: rows 46–48 read a sub-division row instead of the
section total. Rows 43–52 now come from longer official sources (details
below), and the audit and input panels were rebuilt. The model run built on
this audit is specified in `PAPER_TVWQRF_SPEC_2026-09-12.md`.

**Second revision, same day: LUCI located.** The data for rows 15–16 are on CNB
ARAD:
- `MLUCLUTXXINDQ` for the total;
- `MLUCLUWXXSTDQ` for the wages-and-costs contribution;
- snapshot 95, which is the Summer 2026 Monetary Policy Report baseline.

The downloads, with hashes, are in `data/paper_replication/official_cnb_luci_20260912/`.
`tools/paper_replication/cnb_luci.py` writes `luci_quarterly.csv`. It:
- checks all six ARAD LUCI series against the report's chart-data workbook (within 0.005);
- drops the CNB forecast quarters;
- declares an availability date for each quarter.

The model panels use this file. The audit CSV below was built before LUCI was
found and still lists rows 15–16 as unavailable. Per CNB WP 7/2024 Table 1, three
of LUCI's 28 inputs are EC labour-shortage survey balances.

**Third revision, same day: exact series for the remaining stand-ins.** Table A6's
note gives the paper's sources as "Eurostat, ARAD CNB, CZSO, Refinitiv".
`tools/paper_replication/build_exact_overrides.py` writes ARAD and CZSO series
matched to Table A6 into `data/paper_replication/a6_exact_overrides_20260912/`,
with download hashes and identity checks.
- **Row 13 (building permits).** CZSO Table 6 monthly counts equal Bloomberg
  `CZGRIDX` in all 295 months from 2002-01 to 2026-07, so the series is exact. The
  earlier failed validation was against a different CZSO release.
- **Row 25 (trade balance FOB/FOB).** ARAD `SVEVZM4`, from 1993. The local series
  used before is a different series (correlation 0.95).
- **Row 54 (PRIBOR 3M, end of month).** ARAD `SFTP04M2106`; its values equal Bloomberg.
- **Rows 60–63 (commodity prices).** ARAD `MEDACOM*`. Brent equals Bloomberg; gas,
  metals and food differ from the Bloomberg proxies.
- **Row 17 (nominal ULC).** ARAD y/y rate, which fits transform 0. ARAD has no
  values for 2001.
- **Longer histories.**
  - Row 26 (import prices): from 2000, identical to CZSO `CEN0303` from 2008.
  - Row 43 (agricultural PPI y/y): from 1996.
  - Rows 58–59 (client loans): from 1993.
  - Row 52 (agricultural PPI incl. fish): rebuilt before 2010 from ARAD y/y
    rates, tested to 0.05 pp.
- **Still short or substituted.** Rows 50–51 (animal and crop PPI) start in 2010:
  ARAD's older base years are empty, CZSO `CEN02031` starts in 2010, and ARAD's
  livestock and crop y/y are different aggregates. Rows 65–66 remain Bloomberg in
  place of Refinitiv.

The audit CSV has not been rebuilt with these statuses.

## Result

| Status | Rows | Count |
|---|---|---:|
| exact, full paper window | 1–12, 18–24, 27–42, 44–49, 53, 55–57, 64, 67–72 | 52 |
| exact, historical coverage gap | 14 (from 2008-07), 26 (2008-01), 43 (2011-01), 50–52 (2010-01), 58–59 (2005-01) | 8 |
| validated proxy | 17 (Bloomberg nominal ULC level, quarterly), 54 (Bloomberg PRIBOR month-end fixing) | 2 |
| candidate, not validated | 13, 25, 60, 61, 62, 63, 65, 66 | 8 |
| unavailable | 15, 16 (CNB LUCI) | 2 |

- **Exact** means an official series on disk whose identity matches the paper's wording. All inputs are current vintages, not original publication vintages.
- **Bloomberg series never count as exact**, even when they equal the official values. They stay in the candidate panel.
- **Historical coverage gap** means the series starts after 2002-05.
- **Commodity rows 60–63 and 65–66** remain candidates in the audit. The user decided on 12 September to use the Bloomberg series for them in model runs.

Files:

| Content | Location |
|---|---|
| Audit (one row per predictor) | `output/cnb_paper_a6_audit_20260912/a6_audit.csv`, `status_summary.csv` |
| Agreement of extended official sources with CZSO | `output/cnb_paper_a6_audit_20260912/exact_source_checks.csv` |
| Exact inputs (60 rows, each with a declared `available_from_assumed` rule) | `data/paper_replication/a6_inputs_20260912/exact_inputs_long.csv` |
| Candidate inputs (50 rows; `bbg__…` Bloomberg and `local__…` local columns) | `data/paper_replication/a6_inputs_20260912/candidate_inputs_long.csv` |
| Validation evidence | `output/cnb_paper_candidate_validation_20260912/` |
| Imported Bloomberg panel (65 of 66 tickers; 137 snapshot hashes verified) | `data/paper_replication/bloomberg_candidates_20260911_full_refresh/` |
| ECFIN archives, August 2026 vintage (12 ZIPs, HTTP headers and SHA-256) | `data/paper_replication/raw_bcs/nace2_ecfin_2608/` |
| Parsed ECFIN, Eurostat and CZSO downloads | `data/paper_replication/official_bcs_ecfin_2608/`, `official_eurostat_20260912/`, `official_eurostat_20260912_ppi/`, `official_czso_20260912/`, `official_czso_20260912_agri/` |

The snapshot folder under `data/market_snapshots/` was read, never written.

## Reproduce

```text
python tools/paper_replication/import_bloomberg_candidates.py
python tools/paper_replication/official_sources.py ecfin-long data/paper_replication/raw_bcs/nace2_ecfin_2608 --output data/paper_replication/official_bcs_ecfin_2608
python tools/paper_replication/official_sources.py eurostat --output data/paper_replication/official_eurostat_20260912
python tools/paper_replication/official_sources.py eurostat --set ppi --output data/paper_replication/official_eurostat_20260912_ppi
python tools/paper_replication/official_sources.py czso --output data/paper_replication/official_czso_20260912
python tools/paper_replication/official_sources.py czso --set agri --output data/paper_replication/official_czso_20260912_agri
python tools/paper_replication/validate_candidates.py
python tools/paper_replication/build_a6_audit.py
python -m pytest tests/test_paper_a6_catalog.py tests/test_official_sources.py tests/test_bloomberg_candidate_import.py tests/test_candidate_validation.py tests/test_a6_audit.py
```

- Each step writes a new folder and stops if the folder exists. The importer is the exception: it may replace its own earlier output.
- The ECFIN ZIPs were saved with `curl`. `official_sources.py ecfin-manifest` records their headers and hashes and refuses to describe a changed archive.

## How identity was established

1. **The table itself.** Table A6 was re-read from the paper, from both the PDF text layer and the rendered pages (printed pages 34–37). The transcription is `tools/paper_replication/a6_catalog.py`, and a test ties the runner's transforms to it.
2. **The survey codes.** The survey descriptions are Eurostat `ei_bs*` indicator labels, word for word; for example row 30 is BS-SAEM, "Expectation of the demand over the next 3 months". This fixes each survey row's official code. The paper's "13 months" is the 12-month consumer question.
3. **ECFIN against Eurostat.** The ECFIN archive equals those Eurostat series in every month for 33 of the 35 survey-coded rows. For rows 27–28 it equals Eurostat EA21 (the current euro-area composition) rather than EA20.
4. **Bloomberg survey tickers.** Each was compared with every monthly ECFIN series of its geography, adjusted and unadjusted (`bcs_match_matrix.csv`), so a ticker belonging to another question would be found. Thresholds were declared in `validate_candidates.py` before the first run.
5. **Extended official sources.** Each is checked against the CZSO series it replaces (`exact_source_checks.csv`):
   - Eurostat domestic producer prices match the CZSO CEN0201A section totals in monthly log change, with MAE 0.003–0.035 pp over 2015–2026.
   - Eurostat year-on-year PPI matches CZSO's published year-on-year rate (MAE 0.037 pp).
   - CZSO CEN02032 agricultural month-on-month indices equal CEN02A in every month from 2015.

## Seasonal adjustment

- **Survey tickers.** Of the 33 Bloomberg survey tickers mapped to A6 rows:
  - 25 hold the EC seasonally adjusted balance. They equal it in every month and sit 0.7–8.3 points from the unadjusted series.
  - 8 belong to questions where the EC publishes identical adjusted and unadjusted values: EUS2CZ (#4), EUB5F5CZ (#8), EUB5F7CZ (#9), EUA7EMU (#28), EUS5CZ (#31), EUA6CZ (#42), EUI5CZ (#67) and EUB4CZ (#68).
- **Bloomberg labels.** The five retail tickers EUR1CZ, EUR3CZ, EUR4CZ, EUR5CZ and EURTCZ are labelled NSA by Bloomberg, but their values equal the EC adjusted series in every month. They must not be adjusted again.
- **Hard data.**
  - CZIPITS tracks CZSO's seasonally and calendar-adjusted production level (monthly log change MAE 0.05 pp).
  - UMRTCZ and UMRTDE equal Eurostat's adjusted rates.
  - GRCPHCPI, CZEII, CZGRIDX and LONSCZNF are unadjusted as published.
  - LCTQCZI is unadjusted nominal ULC per person: year-on-year MAE 0.07 pp against Eurostat, versus 0.48 for the adjusted variant.

The audit's `seasonal_adjustment` column gives the treatment for each row.

## Findings that change earlier notes

- **Row 38 transform is 3, not 0.** The runner and the data request are corrected; the 20260910 scores used 0.
- **Rows 46–48 (PPI mining, manufacturing, energy).** The 20260910 runner's loader took the last classification row in each section (B08, C33, a D35 sub-group) instead of the section total. Its log-change correlation with the true section is 0.28–0.70.
  - Rows 45–49 now use Eurostat domestic producer prices (`sts_inppd_m`) from 1990. These equal the CZSO section totals in growth, so rows 45–49 no longer have a coverage gap.
  - Row 44 uses Eurostat's year-on-year rate from 1991.
- **Rows 50–52.** CZSO `CEN02032` gives the agricultural month-on-month indices from 2010-01, identical to CEN02A from 2015. The indices are for animal production (fish separate), crop production, and agriculture including fish.
- **Row 43.** CZSO's published year-on-year rate is used from 2015, and 2011–2014 is chained from CEN02032. Chaining one-decimal indices differs from the published rate by 0.28 pp on average.
- **Row 4.** `EUS2CZ` equals the official series for evolution of demand over the past 3 months in the August 2026 archive, which holds identical adjusted and unadjusted values for this question. Codex's transcription of the November 2025 annex (`output/bloomberg_bcs_ec_annex_spotcheck_20260911.csv`) shows different adjusted values. That is a vintage difference, so the paper's own input may differ.
- **Row 10.** `EUA2CZ` is the question on financial situation over the next 12 months. `EUA4CZ` is the question on general economic situation and is rejected.
- **Rows 27–28.** Bloomberg `EUA8EMU` and `EUA7EMU` equal the current-composition euro area (EA21). The paper period used EA20 (MAE 0.17 and 0.06 points). The exact panel uses Eurostat EA20, which ends 2025-12.
- **Rows 71–72.** The Czech price-trend balances are official downloads and count as exact. Czech geography is an interpretation: rows 27–28 print "in Eurozone" and these rows do not. The old panel column `household_price_expect` equals the Czech next-12-months balance exactly.
- **Row 64.**
  - CZSO `CEN0101J` has monthly prices of all four fuels, including Super plus 98, from 2001-01 to 2025-12, when the dataset ends.
  - The weekly `CENPHMT` open data carries only Natural 95, diesel and LPG.
  - The paper window is covered, but Petrol 98 is unavailable for live months after 2025.
- **Row 54.** Bloomberg daily PRIBOR fixings reproduce the ARAD monthly average (MAE 0.0005 pp). The month-end and monthly-average values differ by up to 0.92 pp in months when rates changed. The ARAD end-of-month series needs an API key.
- **Row 58.** `LONSCZNF` has to be converted with month-end EUR/CZK: growth correlation 0.96, against 0.71 using the monthly-average rate. The ARAD VST total remains the exact input.
- **Row 13.** `CZGRIDX` is a monthly count, not a cumulative series; treated as cumulative, its year-on-year MAE is 3.9–6.2. It stays a candidate because:
  - it matches the current CZSO release over only 9 months (MAE 0.16);
  - against the 2014–2023 release series it matches in 73% of months to one decimal (MAE 0.48, correlation 0.966), which is below the declared threshold.
- **Timing of the frozen `paper_predictor_panel.csv`.**
  - `ppi_mm_deep` and `agri_ppi_mm` hold year-on-year changes stored one month late.
  - `unemployment_rate` does not reproduce Eurostat `une_rt_m` at any shift, and `pl_retail_conf` is not the EC Polish retail confidence indicator.
  - `import_price_mm`, `rushin`, the FMIE columns and `household_price_expect` are aligned to their reference months.
- **Row 60.** It is no longer called exact. `CO1` differs from Europe Brent spot by 0.91 USD on average (growth correlation 0.97), and the paper does not identify its Brent series.

## Still open

- **Rows 15–16 (LUCI).** Found on ARAD; see the second revision note at the top. Rebuilding the audit CSV with these rows as exact is still to do. The tidy step is `python tools/paper_replication/cnb_luci.py`.
- **Row 13.** Resolved: CZSO Table 6 equals `CZGRIDX` (third revision).
- **Row 25.** Resolved: ARAD `SVEVZM4` (third revision).
- **Rows 50–51.** No monthly animal or crop producer price history before 2010 found.
- **Rows 15–17.** Quarterly series. The model run uses Chow–Lin in the paper convention and the latest published quarter in the real-time convention.
- **Row 14.** The paper imputes values before 2008 (Chen–Labonne). The model run uses factor imputation.
- **Vintages.** Every series is a current vintage. `available_from_assumed` values come from declared rules, not recorded publication times.

## Worktrees compared

- **Commits.** The Claude worktree `codex-p0` (47c0e6f) is the merge base of `codex/independent-cpi-20260909` and has no commits of its own.
- **Path step-5 files.** Its uncommitted `PATH_SPEC_v5.md`, `path_step5_backtest.py` and 24 `output/path_step5*` files are byte-identical to the versions Codex committed in 8eeda3b.
- **`models/gap_model.py`.** The Claude copy predates Codex's 3efc718 revision, which aligns the documented and simulated driver lags, adds input validation and adds a fitting fallback.
- **Docs.** `README.md` and `docs/MODELS.md` differ only by the step-5 status lines.
- **Neither worktree was reset, cleaned or committed.**
