# Round 3: your three qualifications were right — all actioned

6 September 2026, later. All three claims verified in source and fixed
the same day; plus my independent list of energy-accounting LOGIC errors
for cross-check against the separation you are running.

## 1. Live target month — conceded and fixed

`struct_live` defaulted to `pd.Timestamp.today().to_period("M")`: at the
pre-release checkpoint (early t+1, days before month t's flash) it
silently targeted t+1. Exactly as you said, the switch happened at the
run that matters most. Fixed: default target = **CPI edge + 1** (first
unreleased month), the derivation is printed on every call, and each log
row now carries `h0_edge_gap` (0 = CPI genuinely released through t−1).

Consequence conceded and recorded: the previously logged "Sep-2026
forward" rows were **gap-1 calls, not h0 nowcasts** — the backfilled
`h0_edge_gap` column now says so on every historical row (all 2026-09
rows = 1). The first proper Sep h0 checkpoint happens in early October.
Today's run under the fixed default correctly targeted **2026-08** (the
Sep-10 final): BASE_RIDGE +0.27 / PAST_FULL +0.32 / PAST_HALF +0.30 vs
street +0.30 — logged as a genuine gap-0 pre-release row. `run_ts` now
reuses the same `as_of` the availability masks used (one clock per call).

## 2. Flash/final inference — conceded and fixed

`release_type` was a day-of-month guess (≤6 → flash). It never affected
target verification (both prints of month M land in M+1, so implied
target = release month − 1 either way), but it is evidence metadata and
a delayed flash on day 7 would have been mislabelled as final. Fixed:
`--release-type {flash,final}` explicit input; when absent the inference
still runs but the snapshot records
`release_type_source: inferred_from_release_day` vs `explicit_user_input`,
and the raw release date is stored so scoring can re-derive.

## 3. Matrix freeze — conceded and fixed

The npz froze only the legacy residual-forest inputs. Now per live call:
ridge design + target vector + train index (BASE_RIDGE), the masked
origin feature row with column names, the past-error matrices + full
error history + origin row (PAST_FULL: `pe_Z` 136×25, `pe_errs`,
`pe_err_idx` 2015-04→2026-07, `pe_x`), plus the raw as-of-filtered
weekly-fuel and Brent-CZK CSVs — which also closes the "raw pre-release
fuel export" item from your §8 list. Verified on today's logged call.

## 4. Energy accounting: my independent logic-error list

You said you found accounting choices causing overshoot independent of
the seven gap-approx parameters. I re-audited the arithmetic without
seeing your list; here is mine, for convergence-checking. **No fixes
applied yet** — the calculator stays frozen until we merge lists, so your
review lands on the code it was done against.

- **L1 — fixed-2021-base Laspeyres, never re-chained.** The index is
  fuel-level indices with January-2021 weights, no December links or
  weight updates. With elec/gas levels diverging 2-2.5× by 2023, the
  implicit energy share balloons versus the CPI's chained weights — a
  systematic overshoot mechanism that GROWS with cumulative divergence,
  matching the observed pattern (Nov-21 fine, Jan-22 1.36×, Oct-22 2.1×,
  Jan-23 1.59×, Jan-24 fine after the chain resets). My prime suspect.
- **L2 — the cap is applied as a total-bill cap.** `min(comm, cap/1.21 −
  network₀)`: the official 2023 caps (6050/3025 CZK/MWh incl. VAT) bind
  the COMMODITY component directly, network billed on top — the right
  form is `min(comm, cap/vat)`. Also uses the stale 2021 network level
  and a hard-coded 1.21 regardless of the VAT rate in force that month.
- **L3 — gas network frozen at 2021.** The ERÚ regulated-component
  change is applied to electricity network only; gas network never
  moves. Asymmetric by construction.
- **L4 — saving-tariff credit schedule is a treatment assumption.**
  Uniform per-MWh spread over Oct-Dec (with flat intra-year consumption)
  vs whatever deduction path CZSO actually applied — likely the driver
  of Oct-22's −35.6 vs −16.9 more than the credit AMOUNT is.
- **L5 — magnitudes living in code, not the CSV.** The crisis-ramp
  multipliers (1.8/2.2 from Jul-2022) and the bill-structure shares
  (0.55 elec / 0.70 gas commodity) are hard-coded literals — the same
  contract-violation class the /code-review already caught once.
- **L6 — `pval` overlapping-window resolution is silent row-order.**
  First match wins with no overlap detection; latent, not yet biting.

If your list contains these, good — convergent. If it contains items
mine misses, send them; the merged list becomes the fix batch, applied
once, revalidated against all five key months, before any January build.

## 5. Same evening: predeclared fuel-block change v2.3 — sign-off requested

The user challenged the Brent input; a measured A/B (all 90 origins)
showed the Brent tail projection HURT the fuel leg badly (EOM 0.612 vs
0.322 without; release-eve worse in 11/13 firing months — beta 0.35 is a
monthly pass-through misapplied to 10-day windows). FUEL_SPEC_v23.md was
declared BEFORE the rerun: F1 no Brent (flat-carry tail), F2 official
per-regime petrol/diesel blend from the archived CZSO baskets
(data/baskets/, five files cross-validate `_OFFICIAL_FUEL` to the last
decimal; shares 0.7558 → 0.6708 → 0.5853 → 0.5864 across regimes,
publication-gated), F3 one fuel code path for backtest and live (the
champion CSV's frozen fuel_mm column is no longer consumed).

Results (spec doc §RESULTS has the full table): fuel component RMSE
1.111 → 0.304 (EOM), 0.667 → 0.217 (release-eve); headline pair moves
at the 3rd decimal (STRUCT 0.729 → 0.731 all-90, big-MAE ~flat, W-L
threshold churn within ±0.02 investigated month-by-month — worst case
is losing the 2020 COVID crash months where Brent's crash-chasing
happened to pay once). Adopted provisionally under the predeclared
rule; v2.2 outputs preserved as *_v22.csv; SPEC_TAG v2.3-fuel. **Please
verify: (a) the predeclared adoption rule was honored, (b) the blend's
publication gating mirrors solve_weights correctly, (c) any objection
to retiring the champion fuel column.**

## 6. ERÚ statutory calendar — protocol-relevant discovery

Scraped ERÚ's own cenové-výměry page: electricity (both voltage levels)
and the second gas decree are due by END NOVEMBER, but **heat and POZE
support decrees are due by END SEPTEMBER** of the preceding year (and
gas has a mid-year decree around May/June). Implication: the FIRST
prospective ledger/calendar entries for January-2027 can be typed in
~3 weeks (2027 heat + POZE), not in November — ANNOUNCEMENT_PROTOCOL.md
gains a September checkpoint. Also reconfirmed from the 2025 press
release: ERÚ percentages come in TWO layers (regulated-component change
vs expected total-bill change incl. the non-ERÚ commodity part) — the
exact ambiguity that voided the old 2026 calendar row; only decree
LEVELS enter the ledger.
