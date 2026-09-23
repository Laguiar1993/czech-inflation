# Operating and moving CZ-STRUCT

Read docs/MODELS.md and docs/LIVE_READINESS.md first. The active pair is
BASE_RIDGE and PAST_FULL; the model remains in shadow/research while the
listed timing and archive repairs are open.

## Copy and configure

Copy this repository, including data/, output/ and tests/fixtures/. The
live database and its updater are external: copy czechia.duckdb from
~/economic_db and separately preserve the updater and its dependencies.
The repo alone supports the frozen test/replay exercise; it does not include
the complete live data maintenance system. The updater requires a separate
disposable-database audit before use on the real database.

Install Python and requirements-dev.txt. For numerical reproduction also
install requirements-numerical-lock.txt; this records the audited Windows
Python 3.14.3 numerical environment, not all transitive dependencies.
The exact versions are in tests/fixtures/cleanup/RUNTIME.json.
Install the Census X-13 executable separately. Configure paths explicitly:

```powershell
$env:CZ_CPI_DB = 'D:\CzechData\czechia.duckdb'
$env:CZ_X13_PATH = 'D:\Tools\x13as.exe'
```

The defaults remain ~/economic_db/czechia.duckdb and
~/x13as/x13as/x13as.exe. Do not edit Python source to move computers.
The audited X13 SHA256 is
2e43194361ee096797f0431765193c316196ea6776f11535e76281a413d49669.

## Verify before a live run

```powershell
python -m pytest -q
python tools/replay_cleanup.py . tests/fixtures/cleanup output/cleanup_check
```

The first command uses no database or network. The second uses frozen
inputs, real X13 and real model fitting; all network access is blocked.
The replay compares its output with tests/fixtures/cleanup/expected_backtest.csv
(the v2.4 reference): every reference column must reproduce exactly; columns a
later spec added (the v2.5 release-eve checkpoint, suffix `_EVE`) are reported
as new, never silently accepted. The audited runtime reproduces the reference
exactly. A discrepancy on another runtime must be explained and recorded
before freezing a new reference; correlation or unchanged ranking is not a
reproducibility test. The fixture preserves v2.4 conventions and does not
certify historical vintages.

## Data responsibilities

The database covers much of the input panel. Some loaders also contact
CZSO/CNB/FRED and may update caches. FRED needs FRED_API_KEY where used;
the frozen replay does not. The agri CSV is a local download with no complete
in-repo updater. Refresh it when a new observation is published. Bloomberg
is optional for survey capture and is not a predictor in the active pair.
Keep survey observation/capture timestamps and explicit flash/final identity.

Before any shadow call, verify that expected published sources are fresh.
An imputed feature may be legitimately unpublished, or it may be stale;
the imputation count alone cannot distinguish them. R4's stale August
ESI/expectations remain an unmet refresh acceptance gate.

## September 2026 checklist (the first prospective calls of the frozen trio)

1. Done 7 Sep: database refreshed (`update_cz.py`, pipeline OK), dry run of
   `--target 2026-09` clean (0 STALE, 14 NOT_DUE), tag v2.7.2-bands.
2. On or after 10 Sep (August detailed release): open the CZSO page, copy
   the two "Next News Release" dates (September flash, September
   detailed) into `MANUAL` of `tools/build_release_calendar.py`, rebuild
   the CSV, commit. Without the row the September call logs with
   `release_stage = unknown` and is not first-release evidence. The CZSO
   annual list (`data/czso_release_rules_2026.csv`) gives rules only; the
   flash has no rule; the iCal feed on csu.gov.cz is not machine-reachable
   (checked 7 Sep).
3. 10 Sep: grade the August rows (`scoreboards_codex_p0.py`).
4. 30 Sep after the fuel Monday and the FX fixing: `python cz_struct.py
   --live --target 2026-09` (decision time A). The row carries the trio,
   the flagged V1 bands (`band_status = uncalibrated`), the archive, and
   from v2.7.3 a fourth column `h0_base_ridge_ns`: the reference without
   the survey inputs (PATH_SPEC_v3 section 1), logged for a prospective
   comparison; the frozen trio itself is unchanged.
5. Eve of the October flash (per the calendar row): capture the survey
   (`capture_survey.py`, release type flash), then `--live` again
   (decision time B). Never edit a logged row; corrections are new rows.
6. ERU heat and POZE decisions (end September): enter under the protocol
   in per-fuel percent, archive the source with its hash.
7. After each live call: `python path_live.py` (add `--flash YYYY-MM=VALUE`
   when a flash has printed but the detailed release has not) writes the
   forward twelve months to `output/path_live_latest.csv` and appends them
   to `output/path_live_log.csv`. Engine F1b by default (PATH_SPEC_v2
   RESULTS); `--engine F1a|F1b|F2|F1b+F2` for comparison runs; the trend
   line (F2) is always computed and shown next to the product. Caveats are
   printed with every run. Known bad rows in `output/path_live_log.csv`:
   the runs of 2026-09-08 07:22 (engine F1a, before the step-2 decision)
   and 08:44 and 08:45 (trend columns misaligned by one month: first the
   August flash was missing from the trend history, then the model's own
   horizon count started at the nowcast month; both fixed the same morning). Rows are
   never edited; the 08:5x run of the same day supersedes them.
   Before the month-end run, refresh the two step-4 driver caches: delete
   `data/eurostat_lci_cz_quarterly.csv` and `data/czso_import_prices_sitc_monthly.csv`;
   the loaders in `path_step4_backtest.py` re-download them (Eurostat LCI; CZSO
   open data CEN0303). The target line (E7) uses import prices of month t - 2
   and the koruna / real-rate lags; the product path does not use either cache.
   After each CNB Monetary Policy Report (February, May, August, November): add its publication and
   cut-off dates to `PUB` / `CUTOFF` in `tools/cnb_mpr_cpi_quarterly.py` (read them from the report page
   on cnb.cz), rerun that tool, then `path_backtest_h_cnbq.py --file output/path_step2.csv --col-a yy_a_F1b --col-b yy_b_F1b --out output/path_step2_cnbq_F1b.csv`
   (and the F2_D1_fixed pair) and `path_step2_charts.py`; the comparison is made only at report dates, with the path we had
   published before the report (user rule, 8 Sep 2026). `path_live.py` keeps printing the latest report's quarters with flags.
   Log rows of 8 Sep 2026 before 10:50 carry target_variant E1_ML; the 10:50 row
   (target E7_ML, PATH_SPEC_v4 rule) supersedes them for the target line only;
   product and trend columns are identical.

## Release calendar (v2.5, TIMING_SPEC_v25.md T1)

`data/release_calendar_cz_cpi.csv` is the only source of release timing:
per target month the FIRST release (regular CPI before 2025, flash from
2025) and the DETAILED release, both at 09:00 Prague. Every eligibility
decision in the model reads it; months inside its span that are missing
are treated as NOT released (fail closed), so it must be kept current:

1. After each detailed release, open the CZSO release page and copy the two
   "Next News Release" dates (flash estimate, inflation) into the `MANUAL`
   dict of `tools/build_release_calendar.py`, with the page URL.
2. Run `python tools/build_release_calendar.py`; it rebuilds the CSV from the
   Bloomberg release-event tables plus the CZSO overrides and prints any
   disagreement (CZSO wins).
3. Commit the CSV. A target whose first-release date is missing is logged
   with stage `unknown` and is not evidence of anything.

## Shadow operating loop

Stage and scheduled release are derived from the calendar; pass
`--release-stage` / `--release-dt` only to override. Never infer which
release is being forecast from the database edge.

```powershell
python capture_survey.py --target YYYY-MM --release-type flash --median VALUE --release-dt YYYY-MM-DD
python cz_struct.py --live --target YYYY-MM --no-log
```

The second command is a dry run: it does not append a forecast or archive
matrices, but its data loaders may fetch data and update raw caches. It is
not an offline or read-only mode. Read the printed report before logging:

- **STALE** inputs are published per rule or calendar but absent from the
  database: refresh (`update_cz.py`, agri file) and re-run. Do not log a row
  with STALE inputs; the evaluation classifier marks it INCOMPLETE_INPUTS.
- **not-yet-due** inputs are legitimately unpublished and imputed by design.
- `fx monthly_table` vs `fx mtd_daily(n fixings)`: for a month the monthly
  table does not yet carry, EUR/CZK is the month-to-date mean of CNB daily
  fixings dated BEFORE the call day (v2.6: the 14:30 fixing of the call day
  is never used; complete months always use the table).
- `food_method` / `food_hist_end` / `food_n_obs` / `food_x13_error` (v2.6):
  the food block's seasonal-adjustment method for the call; `fallback` with
  an error text means X-13 did not run and must be investigated before the
  row is treated as a normal forecast.
- `eligible CPI edge`: the latest CPI-family month the clock admits.

The clock is taken in Europe/Prague and logged zone-aware (`run_ts`); the
wall time used for every rule is logged as `as_of_wall`. Only omit `--no-log`
when intentionally recording a shadow forecast. Two decision times are the
official checkpoints: month-end (last working day of the target month,
stage pre_flash) and the day before the first release (stage pre_flash,
later fuel Mondays and complete-month FX enter automatically). A call
between the flash and the detailed release is stage pre_final: a separate
final-release product that the scoreboard never scores against the earlier
flash. After a release, run `python contribution_report.py --origin YYYY-MM` for
the block decomposition of that call (contributions, deviations from the
neutral seasonal baseline, wedge separately, block uncertainty), then
`python scoreboards_codex_p0.py`; it reports
the historical boards at BOTH decision times (A month-end, B release eve)
and the shadow rows as diagnostics. Never rewrite old log rows after a
construction/spec change.

## Annual events and separate model changes

Before every live call run `python tools/check_announcement_sources.py
--cadence every_call` (monthly and quarterly cadences after each detailed
release / quarter): it hashes the announcement source pages and logs
UNCHANGED / CHANGED / UNVERIFIED per source; CHANGED pages are read by a
person and any moved date, level or withdrawal becomes a NEW ledger row
(ANNOUNCEMENT_PROTOCOL.md, re-verification routine). The live row carries
the age of the last check and its CHANGED / UNVERIFIED counts.

Archive November tariff announcements when published, before the outcome is
known. Store policy start/expiry as linked events with source, availability,
effective date and CPI-treatment date. Freeze the national aggregation and
conversion rule before seeing January; an illustrative household bill is not
a national CPI calibration. Add basket weights only with their own publication
evidence. These actions are separate from the completed structural cleanup.
