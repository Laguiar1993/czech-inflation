# Czech Inflation Monitor, M1 — 22 September 2026

**An analysis lane next to the models: a page and a note that say what is driving Czech headline and core inflation, which part of the coming moves is drop-out arithmetic, what the producer-price pipeline leads, and where the roster path sits against the CNB.** Built from the repo's own frozen inputs and the Bloomberg lane; no forecast model changed.

Artifact: **https://claude.ai/artifact/7QWKgLUtWoex31JV2dTACD** ("Czech Inflation Monitor", version 2) · [Specification](docs/implementation/M1_INFLATION_MONITOR_SPEC_2026-09-22.md) (`edfa38b`, before code; code `d0f02be`, `70e3a5f`, `bf71cef`, before the run) · Builder `tools/inflation_monitor/{build.py,template.html}` · Run `output/inflation_monitor_20260922/` (`contributions.csv`, `groups_latest.csv`, `base_effects.csv`, `pipeline_leadlag.csv`, `monitor_data.json`, `blocks.json`, `note.md`, `monitor.html`, `manifest.json`; log `output/inflation_monitor_20260922_build.log`).

## What the first build says (data through July 2026 groups, August flash headline)

- Headline 1.9% y/y (August flash; 1.7% in July), CNB core 3.0% (2.5% a year ago), regulated −1.2%. CZSO services 4.6%, goods 0.4%, food −3.1%. Peak: headline 18.0% and core 14.6% in September 2022.
- Holding headline up in July (contributions with 2026 weights): rents +0.89 pp (5.8% y/y, 15.4% of the basket), other services & mixed +0.81 pp (3.4%), vehicle operation incl. fuel +0.62 pp (12.4%), alcohol & tobacco +0.30 pp (3.6%), catering & accommodation +0.29 pp (4.3%); core goods +0.07 pp (0.5%). Holding it down: household energy −0.55 pp (−6.7%), food −0.52 pp (−3.1%). Residual of the fixed-weight sum against the published 1.7%: −0.22 pp.
- Since the peak: energy −4.5 pp of contribution, food −4.1, core goods −2.3, other services −1.7. The disinflation was goods and energy; services and rents are what is left.
- Base effects, last known m/m August 2026: with normal seasonal months headline y/y reads 2.2 (Sep), 2.1 (Oct), 2.5 (Nov), 2.9 (Dec), 2.8 (Jan-27), 3.1 (Feb-27); with the roster path's m/m 2.1, 1.9, 2.3, 2.5, 2.7, 2.9. November, December and February are flagged as drop-out arithmetic (the weak −0.3 / −0.3 / −0.1 prints of a year earlier leaving the window); March 2027 is the reverse (a +0.6 dropping out). The roster path sits 0.2–0.4 pp under the norm path through December because it expects m/m below the seasonal norm in September, November and December.
- Pipeline: farm prices −19.9% y/y, food PPI −5.8%, domestic PPI +4.0%, import prices +4.5%. Lead-lag on 2015–2026 twelve-month changes: farm → food CPI best at 3 months (corr .91; .85 excluding 2021–23), food PPI → food CPI at 1 month; domestic PPI → core goods at 3 months (.87) in the full sample and **no relation excluding 2021–2023** (.02); domestic PPI → core at 4 months (.94; .53 ex-surge); domestic PPI → services at 8 months (.93; .53 ex-surge, a common-driver correlation rather than pass-through).
- CNB Summer 2026 report (13 August) against the roster path from origin July: 2026Q3 1.9 vs 1.8, Q4 2.4 vs 2.1, 2027Q1 2.8 vs 2.5, Q2 2.4 vs 2.2 — the roster runs 0.1–0.3 below the CNB through mid-2027.
- Prints: June −0.3 (consensus 0.0, BASE −0.06), July 0.6 (0.6, 0.45), August 0.3 (0.3; no recorded BASE — the live Bloomberg-lane nowcast starts with the production loader switch).

## Method, in one paragraph

Eight blocks partition the 37 CZSO COICOP-2018 groups; contribution = 2026 basket weight ⁄ 1000 × group y/y with fixed weights for every month, and the residual against the published headline y/y is shown as its own line. Momentum = annualised three-month excess over the calendar-month median m/m of 2015–2019 and 2024–2025, plus the twelve monthly medians. Base effect for a month = its seasonal norm minus the m/m dropping out; momentum = the roster path's m/m minus the norm; implied y/y compounded exactly with published months where known. Core and regulated y/y are compounded from the CNB monthly series on Bloomberg; the group panel is the CZSO CEN0101E file the Category Raw challenger already uses. The lead-lag table is corr(x at t−k, y at t) on twelve-month changes.

## Limits, stated

Fixed 2026 weights (the earlier baskets are on other classifications; a concordance is future work); the block "other services & mixed" carries mixed goods/services groups (health, personal care, household services); the pipeline correlations are descriptive, not a model; the page refreshes only when the builder is re-run after a Bloomberg pull and a CZSO group file update.

## Next (declared)

M2: the wages → services regression (quarterly CZSO wages, 2–4 quarter lags; house prices and construction costs for rents; food costs for catering). M3: the demand block (retail sales, household credit, consumer confidence `EUA8CZ`, unemployment) and a demand-pressure index against services momentum. Then the live nowcast on the page once the loader switch is done.
