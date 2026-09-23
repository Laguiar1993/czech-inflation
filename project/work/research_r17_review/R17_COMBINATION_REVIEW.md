# R17 path combination and evaluator independent review

Reviewed 2026-09-14. Writes are confined to `work/research_r17_review`; existing source, child outputs and scoring artifacts remain unchanged by the reviewer.

## Final disposition

**PASS. No remaining actionable P1/P2 findings.** The completed integrated run and evaluator were independently checked. The following receipts contain the numerical evidence: `integrated_output_review.json`, `diagnostics_output_review.json`, and `COMBINATION_FINAL_REVIEW_RECEIPT.json`.

| Check | Verified result |
|---|---:|
| Integrated/evaluator source and output hashes | 412 |
| Models / origins / selector records | 30 / 90 / 180 |
| Fixed and candidate mixtures / selection objectives | Exact |
| h0, basket weights and decision clocks | Exact |
| Independent ordinary-product annual CPI maximum error | 1.32e-13 pp |
| Original fifteen-model primary calendar | Exact 969 keys |
| Five-block monthly/cumulative component rows | 162,000 |
| Independently recomputed full common-support score rows | 3,960, exact statistics |
| Both-clock CNB matched rows | 4,092; quarter error <= 3.91e-14 pp |
| Own-origin seasonally adjusted core bands | 10,800, exact |
| Strict-turn rows / common origin-band keys | 5,400 / 159 |
| Every-report omission rows | 3,472, exact |
| Large-CNB-departure rows | 2,280, exact capture/gain summaries |
| Bootstrap calendar-support rows | 1,740, correct eligibility and suppression |
| Current combination/evaluator tests | 8 passed |

Sustained movement and strict-turn common-support counts preserve hits, missed events and false calls. The bootstrap check independently reconstructs twelve consecutive calendar-origin windows and verifies that intervals are suppressed when eligible windows cannot cover all matched support. It does not claim that a block bootstrap creates independent observations from overlapping forecast paths.

The parent's `replay_behavior_receipt.json` records Node DOM-contract and SVG-string checks for all 19 rounds on both clocks, roster checkboxes, reset, tooltip and score restoration. Its hash matches the final artifact. Those checks are not visual browser layout or pixel verification.

Two review clarifications are retained explicitly. The parent fixed a loudly failing evaluator-only empty-frame dtype issue and added a regression test before the successful final evaluation; forecasts and selector outputs were unaffected. Separately, the reviewer initially suspected a sign error in the large-departure capture ratio, then **withdrew that finding** after checking the actual convention: `realised_cnb_error` equals actual minus CNB. Literal CNB=5/actual=3/model=4 gives capture +0.5; model=3 gives +1; model=0 gives +2.5; model=6 gives -0.5. The existing implementation is correct and no output change was needed. All corresponding saved capture rows were independently verified.

## Prefit disposition

**No substantive blocker to the declared combined selector run.** The constrained pool, selection calendar, complete-path loss and monthly accounting match the frozen combination specification. Independent fixtures verify the contracts below; final output verification is recorded separately when the integrated evaluator manifest is complete.

- Independently enumerated all integer-quarter weight vectors summing to one with FAST >= 0.5 and each alternative <= 0.25: the implementation contains exactly the seven admissible vectors. Its declaration order begins with all FAST.
- Independently reconstructed validation membership and objectives using synthetic paths with over a decade of origins. Only origins s with s+12<t, all twelve detailed-label releases at or before the decision clock, and finite complete forecasts for every candidate enter. Missing one candidate horizon excludes the entire origin. A delayed single label also excludes all origins whose validation path includes it. The latest 36 complete common origins and all recorded maximum release dates match exactly.
- The objective is the equal-origin mean of twelve annual-headline squared errors plus 0.05 times the sum of squared nonFAST weights. The independent objective agrees exactly. Fewer than twelve valid origins selects the allFAST default; future, unreleased and incomplete-origin label poisoning leaves the mature selection unchanged. Candidate weights remain fixed across h1..h12; no horizon-specific selection occurs.
- Fixed combinations and constrained candidate mixtures operate on monthly component rates and their frozen-weight contributions. h0 is preserved exactly. Independent component contribution identities differ by at most 1.11e-16 percentage points. A nonlinear fixture confirms that compounding the monthly mixture is distinct from averaging annual forecasts.
- Independently reconstructed the original R16 finite annual-headline intersection over all fifteen original models. The saved primary calendar is exactly those 969 origin/horizon keys. This primary calendar is distinct from the more inclusive monthly-only component support.
- The additional sustained signal uses core bands one through three; all roster members must have finite predicted and actual bands for common-support summaries. An unavailable member removes the origin for every model. Independent fixtures preserve hit, missed-event and false-call counts.

Receipt: `combination_prefit_review.json`; reproducible check: `independent_combination_review.py`. Four combination unit tests passed in 0.74s.

## Completed integration output

The frozen `output/research_r17/path` output independently passes all 372 source/output hash checks across 30 models and 90 origins. All fixed mixtures and all saved candidate mixtures match exactly. All 180 selector objectives, training-origin/release lists, chosen weights and selected complete paths agree with an independent reconstruction; 48 records correctly default to FAST because fewer than twelve complete validation origins exist. h0, origin basket weights and decision clocks are exact. Ordinary-product annual compounding differs by at most 1.32e-13 percentage points, and cumulative log paths match exactly. Receipt: `integration_selector_review.json`. The later final evaluation checks are recorded above.

## Resolved evaluator finding

**P2 — missing native food/fuel component score tables, resolved before integrated evaluation.** The initial evaluator inherited R15 metrics, which cover headline and core only. This omitted the promised monthly/cumulative food and fuel errors from the integrated report, and energy had no separate own-fuel scoring export. The parent added `component_outcomes`, a frozen `actual_component_targets.csv` input hash, and full-roster plus paired FAST/pipeline monthly and cumulative-log tables for core, food, fuel, administered and alcohol/tobacco. No child forecast or source helper changed. The new outcome function propagates a missing intermediate month through cumulative values rather than summing around it. Three evaluator/component tests passed independently in 1.55s, including missing-month propagation, common-support false calls and explicit replay roster labels.

## Interpretation and verification boundaries

The procedure is chronological historical research using current-vintage source histories and reconstructed availability. Earlier R15/R16 and standalone food findings were already known when this follow-up was declared. Correct historical information gates do not turn that sample into an untouched holdout. The selector minimizes headline path error, not CNB proximity or component turning scores.

The additional underlying-core movement diagnostic must be read with its actual-event counts, calls, misses and false alarms. Correct conditional direction or a high hit rate alone does not establish useful forecasts. Exact core turns retain their prior four-band definition and are separate from headline base-effect direction.

`independent_integrated_review.py` verified final source/output hashes, all fixed mixtures and candidate paths, all 180 saved selector decisions, exact h0/weights/clocks, ordinary-product annual compounding, the unchanged primary 969 keys, five component blocks and their finite common scores, both CNB clock choices and material gains, and sustained common-support false-alarm counts. `independent_diagnostics_review.py` checked the additional core-band, strict-turn, omission, capture and bootstrap-support calculations. Both read frozen outputs only and write review receipts here.
