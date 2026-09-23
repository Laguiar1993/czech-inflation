# Independent R21 / R21B correctness review

Reviewed 2026-09-15. Assessment: **suitable for research reporting, with one nonblocking timestamp metadata finding. No critical or important timing, target, pooling, or accounting defect found in the reviewed implementation.** This assessment does not recommend model promotion.

Scope: R21 and R21B specifications; `models/released_error_research_r21.py`, `models/policy_anchor_r21.py`; the nowcast, path, and anchor runners; their two test modules; generated predictions, training records, and primary scoreboards. Existing dependency functions were traced where necessary. The later publication script and inherited CNB/bootstrap/turn evaluators were not independently reviewed in full.

## Finding and interpretation

**P3 — nowcast release timestamps are recorded at midnight.** `tools/research_r21/nowcast.py:30` converts date-only first/detail releases directly, whereas the sourced calendar contract in `cz_struct.py` publishes at 09:00 Prague. Consequently nowcast `last_release` diagnostics are nine hours earlier than the release event. This would also permit an early label on a same-day pre-09:00 custom clock. All 90 frozen clocks are release eves; independently rebuilding every training key with 09:00 publication times produced identical eligibility and predictions. This is nonblocking for the delivered historical scores. Normalize dates and add nine hours when the runner is next revised; retain a release-eve scope note for the frozen artifact.

**Forest interpretation:** archived FULL uses `qrf_min_leaf=3` (`config.py:106`, inherited by `TVWQRF`); both R21 forests use leaf 8. Therefore FULL versus R21 is a comparison with simpler, larger-leaf forests, and cannot isolate the causal benefit or cost of quantile weighting. Mean versus median within R21 holds the declared forest settings fixed. Historical runtime differences also preclude attributing every small FULL comparison difference to the model design alone.

## Independent checks

- Combined implementation suite: **9 passed**. Added audit scripts live only in this review directory.
- Verified 15 nowcast, 72 path, and 78 anchor input/output hashes against their manifests.
- Checked all **630 nowcast release rows** against the underlying first-release actual/survey source; checked **360 training records**. Headline labels are actual first headline release minus saved HARD_BASE; core forests use the separate sequential hard-core errors. The headline offset has exactly **66 estimated origins** after its 24-label warmup.
- Rebuilt headline lag features separately at every historical decision, all eligible error histories, and all **2,720 historical feature cells**. None of these frozen release-eve cells needs masking; synthetic delayed-label and training-feature poisoning also leaves the estimate unchanged.
- Refit mean and median forests at **2019-02, 2024-01, 2026-07** with one worker; all six corrections reproduce their saved two-worker results within 1e-10.
- Independently rebuilt all **50,792 pool training ledger rows** using strict earlier origins/targets, every constituent publication in each prefix, the 36-month scored-target window, and the complete-path restriction. A missing-publication hole correctly excludes all following prefixes, even when their individual outcomes are released; poisoning those outcomes has no effect.
- Recomputed all **10,530 first-batch path rows** with product-based cumulative/annual compounding. Every learned mixture has the required shared weights, sum-one constraint, FAST floor, and unchanged h0. Component conservation maximum absolute error is **8.88e-16**.
- At three dates for both learned pools, independently minimized the declared exact compounded objective using differential evolution and product-based compounding. Its objective agrees with the saved SLSQP solution within **8.1e-12**. Horizon balancing, recency weighting, prior MSE floor, and the prior penalty agree.
- Rebuilt all **180 component errors** and **360 bias diagnostics**, including shrinkage, eligibility, decay, and contribution accounting.
- Independently rebuilt all **180 anchor diagnostics and 2,340 anchor path rows**, computing annual core/headline spreads through explicit contiguous 12-month product ratios. Each origin uses 120 eligible spreads; publication timestamps and sample endpoints agree. Verified h+1 transitions, own-origin seasonality and cycle, the infinite-half-life FAST limit, h0, non-core blocks, basket weights, and contribution arithmetic. Delayed historical publication, a missing historical month, and future-value poisoning are invariant.
- Recomputed **35 nowcast scoreboard rows**, all **2,700 R21 and 3,300 R21B primary scoreboard rows**, and checked every model retains the same **969 archived primary keys**. Counts, RMSE, MAE, bias, and the checked surprise/materiality statistics agree.

## Model result check

Independent full-90 nowcast RMSE / MAE: HARD_BASE **0.417952 / 0.262516**; RF mean **0.413656 / 0.258875**; RF median **0.413786 / 0.259131**; headline mean **0.423791 / 0.264405**; headline ENET **0.495386 / 0.318043**. Thus the direct headline candidates fail this comparison. The forest gains are small; recent RMSE is worse than BASE (mean **0.223688**, median **0.224557**, BASE **0.218978**), and big-surprise MAE is also slightly worse. These checks support reporting the compromises without selecting an unqualified winner.

## Reproduction

From the repository root in PowerShell, set `PYTHONPATH='../pythonlibs'` and `PYTHONDONTWRITEBYTECODE='1'`. Use `C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe` for:

```text
-m pytest tests/test_released_error_research_r21.py tests/test_policy_anchor_r21.py -q -p no:cacheprovider
work/research_r21_review/audit_r21.py
work/research_r21_review/audit_r21b_and_forests.py
work/research_r21_review/audit_scoreboards.py
```

Machine-readable evidence: `audit_results.json`, `anchor_and_forest_results.json`, `scoreboard_results.json`, and `independent_nowcast_scores.csv`. The scoreboard audit initially referenced a nonexistent archive filename; after tracing the evaluator to the persisted `output/research_r17/attribution/primary_support.csv`, the complete rerun passed. That was an audit-script error, not an implementation failure.
