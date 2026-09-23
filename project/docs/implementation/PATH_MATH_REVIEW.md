# R9 path mathematics: independent review

Reviewed 9 September 2026 against `PLAN_2026-09-09.md` and audit sections 4A/4C/4D/4G. Scope: `models/trend_gap.py`, `models/gap_model.py`, `models/bvar.py`, their focused tests and the existing path wrappers. The review began read-only. Root subsequently authorized only the two finite-input/projection fixes identified below, plus their regression tests. No legacy wrapper or BVAR code was changed during this review.

Verdict: the requested core transition and BVAR mathematical corrections are implemented and the focused tests pass. Two newly exposed finite-input/projection defects were corrected test-first. The legacy historical wrappers still need to remain demoted/guarded; their old outputs are not corrected historical results merely because the imported mathematical functions changed. The new independent path pipeline must construct the complete known-driver scenario and preserve fit/projection diagnostics.

## Stage 1: specification compliance

| Requirement | Evidence | Assessment |
| --- | --- | --- |
| Statsmodels source-to-destination lag | `TrendGap.update` places source-month `x[t]` directly in transition `t → t+1`; no extra shift remains | Pass |
| Changing target timing | Intercept uses `mu[t+1] − rho*mu[t]`; the final unused target is held flat | Pass |
| Shared filtering/projection equation | `transition_intercept` / `transition_state` are shared; gap simulation and handover use the same state equation | Pass for the declared fixed conditional driver scenario |
| Known last driver crosses the forecast boundary | The origin driver reaches h1; explicit future driver month `T+1` reaches h2 | Pass in model API |
| All known multi-month lags propagate | Extended `x_hist` or `x_future` are retained by the API; old wrappers still truncate already-lagged columns at the CPI origin | Incomplete in legacy integration; assigned separately to the new pipeline |
| BVAR public horizon | Training row `t` uses regressors at `t−1` and response `y[t−1+h]`; prediction uses last observed month `T` | Pass: requested target is `T+h` |
| Minnesota penalty and unit invariance | Raw-SSE penalty is source innovation variance times lag penalty divided by prior tightness squared, with cross-variable factor four | Pass |
| Calendar gaps do not shift horizons | Contiguous monthly indexes required; interior missing CPI observations are rejected after edge trimming | Pass |
| Failed ML estimates remain visible | Fixed LBFGS → Powell → start-parameter filter rule; retry, fallback and failure states reported | Pass at API boundary |
| Failed model-consistent expectations remain visible | Failure to converge within 60 iterations falls back to geometric A with an explicit flag | Pass |
| Finite forecast status | Review reproduced nonfinite projections incorrectly labelled successful; scoped fixes below now reject infinities and flag numerical projection failure | Pass after review fixes |
| Re-estimated common-row historical comparison and proper vintage evidence | Outside these mathematical files; no old scoreboard can supply this evidence | Pending independent pipeline, not certified here |

The BVAR caller's existing `h+1` is correct: its path horizon counts from the nowcast month `t`, while the supplied training history ends at `t−1`. Removing that adjustment would introduce a new off-by-one error. The API correction is the training response shift inside `models/bvar.py`.

## Stage 2: correctness findings and dispositions

### P1 — known lagged drivers still disappear in legacy wrappers (remaining integration issue)

Locations at review: `path_step3_backtest.py:53–58`, `path_step4_backtest.py:116–117`; supported API in `models/trend_gap.py:313–321`.

The wrappers truncate `X_all` at `t−1` and reindex it to the CPI history before calling the corrected model. Several columns already contain six-, twelve-, eighteen- or three-month lags. Their next rows can therefore be completely determined by raw observations already known at the cutoff. Once the wrapper deletes those rows, the model's declared zero assumption treats them as unknown future drivers.

Deterministic probe: place a unit raw pulse in `T−2`, use a three-month lagged driver, coefficient one and gap persistence zero. Keeping the known lagged rows changes h2 by exactly **1.0**, while truncating at `T` loses that effect. Forecast differences for h1–h4 were `{1: 0.0, 2: 1.0, 3: 0.0, 4: 0.0}`.

Required integration behavior: build future lagged/rolling columns from source series masked at the information cutoff, then pass those known rows as extended `x_hist` or an explicit scenario. Do not pass unrestricted full-history future observations. Root has assigned this construction to the new independent path pipeline and intends to demote/guard the legacy wrappers. This review did not mutate them.

### P1 — gap missing-driver treatment differed between estimation and projection (fixed)

Locations after fix: `models/gap_model.py:129`, `models/gap_model.py:164`.

Before the fix, estimation filled missing `X_hist` entries with the declared zero, but `_simulate` overwrote its generated driver row with the raw NaN from `driver_history`. A single NaN in final `ugap` yielded **24 NaN forecasts**, while reporting `converged=True`, `fallback_used=False`.

The overlay now applies the same zero treatment used by estimation. A regression compares a missing origin driver with an explicitly zero driver and verifies equality of the entire forecast path. No observed driver is silently replaced with another estimate, and the caller's frame is not mutated.

### P1 — infinite extended inputs and nonfinite projections were reported as successful (fixed)

Locations after fix: `models/trend_gap.py:47–62` and its forecast loop; input and projection validation in `models/gap_model.py`.

Before the fix, TrendGap validated only the portion of `x_hist` aligned with the estimation sample. An infinity in a supplied row after the CPI origin produced `h2=inf`, `h3=NaN` with `converged=True`, `fallback_used=False`. Gap inputs likewise did not reject infinities before optimization.

Both APIs now reject infinities throughout supplied series before estimation, including known-driver rows beyond the CPI origin. NaN still has its documented missing-data interpretation; explicit `x_future` retains its stronger complete-finite scenario contract. Gap input checks cover its unemployment, FX, real-rate and rate-path series as well as `X_hist`.

Finite but extreme values can still overflow during arithmetic. Such projections now return an all-NaN `mm` path with `converged=False` and `projection_diagnostics.status='nonfinite'`, identifying the stage. Optimizer diagnostics are preserved separately: a converged likelihood fit is not evidence that its numerical forecast succeeded. Valid outputs carry `projection_diagnostics.status='finite'`. A pipeline must record and account for these failed forecasts, not silently improve common-row scores by deleting them.

The additional ten regression cases failed before these changes, then passed. They cover the missing/zero equivalence, both infinity signs beyond the TrendGap origin, five gap-input series, and finite-input arithmetic overflow in both models.

### P2 — old wrappers discard the new diagnostic detail (remaining integration issue)

Locations at review: `path_step2_backtest.py:92–98`, `path_step3_backtest.py` parameter export, and `path_step5_backtest.py:101–102`.

The BVAR wrapper still drops incomplete rows, catches every exception and substitutes NaN. The corrected BVAR correctly rejects resulting calendar gaps, but that wrapper hides why a forecast disappeared and does not request the new `return_diagnostics=True` information. Other historical parameter exports retain mainly `converged`, losing method, retry, fallback reason, fixed-point status and projection failure detail.

The new runner needs explicit status columns and common-origin/fallback counts. Under the root's stated demotion of old wrappers, this is an outstanding compatibility limit, not a request to refresh their old labelled results in place.

### P2 — the model-consistent terminal extension is flat, despite the old prose's geometric-A wording (unresolved specification detail)

Location after review fixes: `models/gap_model.py:187`; old `PATH_SPEC_v5.md` projection description says the tail beyond the 24-month window uses variant A.

The current fixed point extends the last monthly trend as a constant for the next twelve months. That is generally different from continuing geometric reversion to the target, and it can feed back into the solved 24-month M path. This review did not alter that historical modelling choice or estimate its scoreboard effect. Before a new M experiment is called faithful to the old specification, either declare the flat terminal condition explicitly or implement and test the stated geometric tail as a newly labelled specification. No inference about comparative performance follows from this code-level observation.

## Positive mathematical checks

- Raw source-month pulses reach the next state in the actual statsmodels filter, not merely in a separately coded helper.
- Target changes, gap simulation and filter projection agree on the controlled no-shock path.
- Conditioning handover on its own predicted observations preserves continuation for both A and M. This validates a zero-innovation boundary; it does not claim that M is re-solved after arbitrary handover news. The implementation explicitly labels its handover scenario as fixed conditional drivers.
- A geometric series with effectively unpenalized one-lag regression forecasts the exact requested h1/h3/h12 value.
- Predictor and target measurement-unit transformations leave BVAR forecasts invariant; the constant-first-difference scale fallback is tested too.
- The posterior uses augmented least squares rather than squaring the condition number through normal equations. The displayed prior derivation matches that solver.
- Tests cover optimizer exceptions, nonconvergence, nonfinite nominally converged fits, successful retry and deterministic fallback. They also test nonconverged M expectations returning the already computed A path.

No blocking error was found in the corrected BVAR target alignment or prior arithmetic. The tests are deterministic mathematical checks; they are not statistical identification, vintage validation or evidence of predictive superiority.

## Verification and energy manifest check

Commands used:

```
python -m pytest test_path_math_r9.py test_path_step4.py -q
```

Initial independent review: **31 passed**. After ten test-first scoped fixes: **41 passed**, no warnings in the final focused run. Read-only probes independently reproduced the wrapper lag loss and the pre-fix NaN/infinity failures above.

The energy script's manifest was rechecked after this review began: **no source/code SHA256 mismatches**. Its manifest hashes `energy_ledger_experiment.py` and `models/energy_ledger.py`, not the separate path modules, so the scoped path fixes do not stale its recorded computation. Energy outputs remain scenario diagnostics with no fitting or promotion. Their `completed_at` changes on a new run and the current files are overwriteable outputs, so root's final immutable evidence bundle must preserve the chosen run; a source hash alone does not turn a mutable output directory into an immutable archive.
