# Independent R14B integration and survey review

Review completed against saved, hash-checked results on 9 September 2026. No model,
shared runner, parameter, benchmark clock or scoring rule was changed during
these final reviews. The arithmetic oracles import no production model/scorer.

## Stable integration

`stable_integration_oracle.py` independently verifies all 16,380 forecast/target
rows, 4,320 future component recombinations, 360 fixed h0 values, 4,680 observations
per component/value/weight column, and 7,020 extended-policy control rows.
All component overlays and monthly recombinations are exact. Direct annual
products differ by at most 1.31e-13 from the log-compounding implementation.

All 1,620 score rows, 468 bootstrap intervals, 2,415 CNB report-quarter rows and
1,034 quarter-score rows reproduce. Point metrics and bootstrap intervals match
exactly. The primary common panel is bridge plus four fixed combinations;
controls retain separate own and paired panels. New core labels use EXT_R14B
and exactly copy the extended source outputs, while CORE_LOCAL_R14 uses the
original source and is numerically identical under either history policy.

The additional source audit checks 22 extension hashes, exactly 84 previously missing
cells, dates at next fixture-month start, all 199 extended historical-state clocks,
and 125 overlapping states' identical features, trend and seasonal values. Initial
state moves from March 2016 to January 2010. It does not change existing predictor
values or the current local-trend control.

## Survey benchmark

`survey_results_oracle.py` verifies 160 manifest hashes, all 192 annual predictions,
2,304 monthly sums, all 24 official-published-value joins/targets, all 28 summary rows,
192 core band-clock checks and 24 component source-clock checks. Direct annual
product differences are at most 9.64e-14. The benchmark uses the published
one-decimal FMIE values, not the extra unverified database digits. Every report
is retained; current states use the reconstructed issue clock. Monthly targets
are survey_month+h; the annual endpoint is survey_month+12, compounded exactly
from h1..12. The placeholder h0 invariance checks cover every report.

Earlier review caught the serialized seasonal-key loader bug and stale combined
status metadata. Parent corrected both before these final runs. Dependency and
runtime checks were completed before empirical survey scoring. No actionable
correctness issue remains in the reviewed completed outputs.

## Scientific interpretation

The stable local-core combination has recent-origin h12 RMSE 0.707685 versus bridge
1.347309, on 19 common origins. Recent-target h12 RMSE is 2.618622 versus 1.892132 on 31
targets. These windows answer different questions; the favorable origin window
does not establish broad historical superiority. R14B was explicitly designed
after inspecting R14 failures and remains exploratory.

On the 24 matched FMIE document-date clocks, FMIE RMSE is 0.410277, bridge 1.324886,
stable local core 0.976371 and stable extended-level core 0.986057. The professional
survey remains materially more accurate in this window. Respondents' information
cutoff and actual website publication instant are unknown; this is the declared
document-date convention, not proof of identical information sets. Neither CNB
nor FMIE errors identify unforeseen structural shocks, and no survey values enter
model inputs. The reviewed evidence supports careful prospective comparison,
not a claim that the independent path now dominates the professional benchmark.

Receipts: `stable_integration_receipt.json`, `survey_results_receipt.json`, and
`extended_policy_receipt.json`, all in this directory.
