# Live readiness after v2.5-timing

Status: research checkpoint with the timing repairs done (TIMING_SPEC_v25.md).
v2.5 is provisional pending Codex sign-off and is not certified first-release
performance: no prospective row has been scored yet.

## Closed by v2.5 (7 September 2026)

1. **Food history filtered before seasonal adjustment.** `food_forecast`
   restricts the history to months released at the clock before X-13, in
   the primary and the fallback path; the cache is keyed by origin, last
   eligible month, length and a content hash (a changed vintage refits).
2. **Actual release events.** `data/release_calendar_cz_cpi.csv` (Bloomberg
   release events cross-checked with CZSO pages) replaces the day-11 rule;
   the January-2026 counterexample now passes; the same calendar gates
   ridge labels, past errors, weights, administered prices, alcohol/tobacco
   and the wedge. Months inside the calendar's span that are not recorded
   fail closed. The former strict expected failures in
   `test_known_limitations.py` are now required to pass.
3. **Clock and event identity.** The live clock is Europe/Prague, logged
   zone-aware; stage and scheduled release come from the calendar; each row
   records the eligible CPI-family edge, the FX source, and its imputed
   inputs split into STALE and NOT_DUE.

## Closed by v2.6 (Codex R6, 7 September 2026)

1. **Live row mask on the release calendar.** `_mask_row_by_availability`
   used the day-11 rule for core_l1/food_l1/services_l1/state while
   `_classify_missing` used the calendar; a 12-Feb-2026 call saw January
   inputs published on the 13th. Both now share `_cpi_family_released_by`
   (poison test in `test_timing_r6.py`).
2. **Month-to-date FX uses fixings dated before the call day.** The CNB
   fixing is published at 14:30; instead of an intraday timestamp the rule
   simply excludes the call day (user decision).
3. **Food block diagnostics.** `food_forecast` records method (x13 /
   fallback), history end, observation count and the X-13 error text; the
   live row carries them.
4. **Alcohol pre-anchor** is the sourced 2014 basket share (0.09498), not
   an undocumented constant; no evaluated origin is affected.
5. **Not changed by decision:** basket publication at the calendar DATE
   (00:00) rather than 09:00 -- a once-per-two-years event where the hour is
   immaterial (user).

## v2.7 (user decision, 7 September 2026)

Documented announcement entries (provenance `sourced_retrospective` and
`prospective`, dated by their source documents) feed the scored
administered block; the gate-closed reference is kept as `STRUCT_NOANN`.
See `ANNOUNCEMENT_ADOPTION_v27.md` for the reasoning and the caveat. Live
calls use the same `documented` mode; for a future target only
prospective rows exist.

v2.7.1 (same day, Codex R8): rows store per-fuel changes in percent; the
headline contribution is computed at call time with the basket item
weights published at the clock and the block value with the call's own
administered weight (no fitted coefficient stored as data); the gate
threshold is 1.1 pp of headline; the January-2022 shares and the
January-2023 credit-only reversal are corrected (the 2023 forecast moves
away from the print, accepted); release-eve gate-closed columns exist for
all three nowcasts; the food producer-price column follows the CZSO month
exceptions. Before a live January call the operator adds any new basket's
electricity / gas / heat weights to `_ENERGY_ITEM_WEIGHTS` (protocol
addendum of 7 September).

v2.7.2 (same night): the live row carries V1 bands for the trio flagged
`uncalibrated` (BANDS_SPEC_v1: no variant met the coverage rule; read as
the historical error spread). Points unchanged. Database refreshed and
the September dry run clean; the calendar row for the September releases
is the one open operator step before the 30 September call (RUNBOOK
checklist).

## Still open

- **Refresh acceptance (operator).** The August dry run under v2.5 still
  reports exp12, exp36 and esi as STALE: published, absent from the
  database. The zero-STALE gate is met by running the updater before each
  call; the updater itself still needs the disposable-database audit before
  routine use.
- **Archive completeness.** The per-call archive now includes both masked
  origin rows, the weights and the zone-aware clock, but not yet the X-13
  inputs and factors, the forest quantile grids and weights, or a survey
  receipt. `archive_ok` remains a write-success flag.
- **CNB availability record.** The calendar records CZSO release dates; the
  CNB core and regulated series are assumed public with the detailed
  release. A separate receipt-based record would remove that assumption.
- **Calendar maintenance.** Future months must be typed from the CZSO
  "Next News Release" line (RUNBOOK); an untyped month blocks eligibility.

The scoreboard now rejects invalid/unknown archive flags, incomplete input
rows and unknown stages, keeps pre-final rows separate, and refuses to turn
naive timestamps into certified clocks. Even TIMELY_UNVERIFIED remains
unverified: no prospective certification is implemented yet. Displayed
shadow errors are diagnostic only; the three historical scoreboards still
use their original calculations. Survey-history uniqueness is checked to
prevent duplicate event joins.

## Additional model work, not mechanical cleanup

- Gapped direct-h target alignment is still positional. Require a calendar
  alignment test before using incomplete monthly histories for path research.
- Preserve ridge normalization, warm-forest normalization and cold-forest
  normalization as distinct specifications. The old refactor queue's advice
  to retain standardization only in the warm correction was incomplete.
- The alcohol pre-anchor is now the sourced 2014 basket share (v2.6); it
  matters only for origins before the first official anchor, none of which
  are in the evaluated window.
- Fuel price aggregation (blend on relatives), revised seasonal survey
  inputs (NSA household expectations), and the January package remain
  separate numeric changes. v2.5 added month-to-date FX for incomplete
  months and moved the basket publication date to the January detailed
  release; both are timing changes declared in TIMING_SPEC_v25.md.
- Crisis energy overshoot is observed; attributing it specifically to a
  fixed-base Laspeyres calculation has not been established. Fixed-base
  indexing can be legitimate within a chain segment. Audit the item mapping,
  base normalization, coverage, tax/credit treatment and household mix before
  attributing the error or changing the index formula.

Official release-date counterexample:
https://csu.gov.cz/rychle-informace/consumer-price-indices-inflation-january-2026

See CLEANUP_REVIEW_2026-09-07.md for acceptance evidence and R4 answers. Earlier
reply documents are historical records and may contain superseded claims.
