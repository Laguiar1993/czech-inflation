# Migration notes — branch codex-p0 (v1.6.1 `552a9e3` → v2.0)

Every changed equation, availability rule and source definition, implementing
the Codex audit's P0 list (CLAUDE_HANDOFF.md) plus accepted P1 items. The
original repository state is preserved on `master` at `30e78a3`.

## 1. Availability clock (P0 #1)
- BEFORE: decision time implicitly inferred as end of the last-known-CPI
  month + 1; announcements with missing dates were admitted.
- AFTER: `_gate_value(target, as_of, announce_mode)` takes an explicit
  timestamp everywhere; `admin_forecast(..., as_of=...)`; backtest passes
  `as_of = origin.to_timestamp('end')` as a DOCUMENTED ASSUMPTION;
  `struct_live` passes `pd.Timestamp.now()`. Missing `available_from` ⇒
  input rejected (fail closed). Acceptance tests reproduce and block both
  audit counterexamples (undated row; 1-Dec call vs 15-Dec announcement).

## 2. January announcement quarantine (P0 #2)
- Calendar gains a `provenance` column; all current rows = `reconstructed`.
- Three modes: `verified_only` (primary; no reconstructed magnitudes ever),
  `reconstructed_scenario` (labelled scenario columns `*_R`),
  `prospective_announced` (live default; empty until entries are typed from
  source documents before their declared cutoff — Nov-2026 ERÚ onward).
- The 2026 row's magnitude is VOIDED per the audit's date-content finding
  (ERÚ initially approved +1.1% low-voltage; the −15.1% was conditional and
  later). Its note records this.
- No threshold/share/baseline retuning was performed (8%, ×0.55, base
  medians and shock-exclusions unchanged, per the audit's instruction).

## 3. Basket calendar & carryover (P0 #3)
- BEFORE: `_regime` odd-year windows, basis+1..+2; fuel hardcoded 0.035 for
  all pre-2025 regimes; carried weights could sum to 0.98683 (15/90 origins).
- AFTER: EVEN-year effective windows; official archived values per window
  (food & fuel for 2014–2026, from the audit's archive verification incl.
  c_basket2025.xlsx); separate `_basket_available_from` (publication ≈
  Feb-15 of effective year, documented assumption) so early-window origins
  use the previous basket; `core = 1 − food − fuel − alc − admin` at every
  origin — sums to 1 by construction (asserted per origin, tested).

## 4. Five components (P0 #4)
- Division 02 (alcohol/tobacco, 8.29% of the 2026 basket) added as an
  explicit block: `load_alc_tobacco_mm()` (cpi_long div 02; matches Codex's
  frozen series), forecast per Codex's declared spec (expanding same-month
  mean, ≥3 obs, else expanding overall mean; prior observations only).
- `solve_weights` identity is now 5-component; the admin share remains a
  single-unknown OLS projection coefficient and is NOT claimed to be an
  official basket share. Wedge recomputed under the 5-component weights.
- The recombination is explicitly NOT claimed to be an exact official CPI
  aggregation (chain-linking / prior-month relative weights / tax treatment
  unresolved — audit P1).

## 5. Uncertainty bands (P0 #5)
- BEFORE: `lo = f + q05(e)`, `hi = f + q95(e)` (reversed shift for a biased
  model); regime pool switched at 16 obs but issued at 24 (dropped months).
- AFTER: `lo = f − q95(e)`, `hi = f − q05(e)`; a regime pool is used only
  when it alone holds ≥24 errors, else the global pool.

## 6. Accepted P1 items in this pass
- Wage feature REMOVED from the default core frame (`INCLUDE_WAGE=False`):
  the Chow-Lin interpolation is fitted on the full history before shifting
  (global-interpolation leak). The wage variant remains available, labelled.
- Trailing y/y state now COMPOUNDS monthly rates (was a sum).
- Horizon calls (h1–h12) run under `verified_only`.

## Not changed (deliberately)
- 4% state threshold, hard dummy, ST variant: kept as-is pending the
  audit's predeclared-design comparison; no threshold search performed.
- QRF residual forest: kept (with the audit's reproducibility caveat);
  ridge remains the reproducibility anchor. The past-error-target
  correction (audit's strongest candidate) is NOT implemented here — it
  changes the training-target concept and belongs to the next declared
  experiment round, not a corrections pass.
- Fuel leg's third-Monday cutoff; LateInfo; slow-block design: unchanged,
  queued per audit P1/P2.

## Outputs
- `output/cz_struct_backtest.csv` now carries verified (`STRUCT`,
  `STRUCT_QRF`) and reconstructed-scenario (`STRUCT_R`, `STRUCT_QRF_R`)
  columns, plus `alc_pred/alc_actual` and `adm_pred_R`.
- `scoreboards_codex_p0.py` produces the three scoreboards + release-by-
  release table with every alert (false calls included) and separate
  January / ex-January panels.
