**14 September 2026 independent audit evidence**

Entry point: `../../REVIEW_TO_CLAUDE_2026-09-14.md`.

All source references in the copied sub-reviews refer to the repository root unless explicitly referring to the surrounding workspace. The scripts now discover that root from this directory; their only modifications during packaging were to those root-discovery lines. Original detailed reports and computed values were preserved. Original evidence copies outside the repository remain untouched.

| File or directory | Purpose |
|---|---|
| `audit_paths.py` | Independently recompute yearly compounding, artifact quarterly errors, and CNB report/cutoff sensitivity from frozen outputs |
| `checks.json` | Arithmetic checks and direct R14B integration manifest comparison |
| `artifact_pairs.csv`, `artifact_summary.csv` | Scored artifact observations and summary by horizon/sample; HTML values have display rounding |
| `cutoff_matched_pairs.csv` | Identical model/report/quarter support for both clock rules, using full-precision archived model forecasts |
| `report_cutoff_clocks.csv` | Which origin each clock rule selects |
| `report_clock_summary.csv`, `cutoff_clock_summary.csv` | Full-precision matched comparisons, including horizons |
| `rebuilt_cnb_rounds.html` | Rebuilt local artifact, byte-identical to saved original; remote page was login-protected |
| `nowcast/` | Independent score recomputation, regression sensitivity, alerts, and AST-executed clock/training counterexamples |
| `forest/` | Forest timing/transform/imputation counterexamples, saved-quantile causal reweighting, monthly and path score comparisons |
| `verification_receipt.json` | Audit verification scope and limitations |

From the repository root, with the original model dependencies available:

```text
python work/review_20260914/audit_paths.py
python work/review_20260914/nowcast/audit_metrics.py
python work/review_20260914/nowcast/audit_clocks.py
python work/review_20260914/forest/audit_evidence.py
python work/review_20260914/forest/causal_reweight.py
```

These write audit evidence in their own directories. They do not run a live source fetch or overwrite the original model forecast files. The causal-reweight diagnostic changes TVW weights using saved prior-origin quantiles; it does not refit the full forest history. The paper-convention inputs retain their declared full-sample preprocessing limitations.

The CNB-cutoff sensitivity selects the latest existing snapshot strictly before the start of the stated cutoff date in Prague. It is not an exact-cutoff refit. Report and cutoff comparisons use the same quarters and full model roster; each model gets the same target observations. The pooled scores are descriptive: reports share realised quarters.

The runtime used for evidence differs from the original pinned Python3.14 environment. Refer to the detailed reviews for package versions and the exact scope of checks; source checksums and a close numerical rescore are not substitutes for a full model refit.
