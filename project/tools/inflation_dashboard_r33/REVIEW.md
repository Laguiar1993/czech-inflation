# Independent R33 dashboard review

Reviewed the uncommitted R33 dashboard against HEAD `a7aaca818ffd38cb906a7443722de9e5515084c1` and `docs/implementation/dashboard_r33/PLAN.md` on 2026-09-22. This review is read-only except for this file. No worker, frozen input, model, or backtest was changed or rerun.

## Finding

### [P2] Resolve validated run directories before collecting manifest inputs

Location: `tools/inflation_dashboard_r33/build.py:28-29`, with failure at `build.py:44-46`.

Passing repository-relative `--old-run` and `--new-run` arguments successfully validates the saved pair through `compare_runs`, but `extra_inputs` retains relative `Path` objects. Manifest construction calls `p.relative_to(ROOT)` with an absolute `ROOT`, raising `ValueError`. The builder has already created its immutable output directory and written `.gitattributes`, `index.html`, and `dashboard_data.json`; `manifest.json` is never written and a retry at the same output path is rejected as existing.

Reproduced with the real, validated July replay pair:

- `output/forecast_updates_r33/runs/20260922T172954590002Z_c92d2a1fc7d0`
- `output/forecast_updates_r33/runs/20260922T173009883888Z_cce84a741ef9`

`compare_runs` returns `status=ok`, target `2026-07`, model `HARD_BASE`, and delta `0.027398504637736354`. Calling the actual R33 builder with those relative paths reproduces the exception. For the review, `Path.mkdir` and `Path.write_text` were intercepted in memory; the three preceding write calls were captured without creating files.

Resolve both run directories before validation/enumeration, and prepare/validate manifest keys before creating the output directory. Also explicitly handle or reject valid absolute run directories outside the repository before any output writes. Add a build integration check covering relative run paths and complete manifest creation.

## Checks and strengths

- The 10 R33 analysis unit tests passed using Python `-B -m unittest tools.inflation_dashboard_r33.test_analysis -v`.
- The real scenario support is September 2026 through July 2027. Food increments affect September-November; core September-February; energy January 2027. Seasonal fallback August 2027 is excluded. Neutrality, exact compounding and annual-window expiry are covered by the tests.
- The rent split and remaining blocks total 1,000 permille without retaining the combined rents row.
- All complete headline gap entries among the 760 report/model/quarter rows match quarterly averages of the displayed model paths. Residuals reconcile, and report and cutoff clocks select distinct data. The UI identifies the selected model and older R27 lane and retains h0 caveats.
- Source-scope assessment corrected in the addendum below: the saved ARAD series are other tradables excluding food/fuel and nontradables excluding regulated prices, not broad CZSO goods/services. The earlier withholding rationale is withdrawn; the current UI restores the series with their correct definitions. External official release contents were not independently re-fetched in this code review.
- Visit-message logic distinguishes first visit, identical data fingerprint, and a different snapshot without calling monthly changes changes since the previous visit. Browser interaction testing remains with the main task.
- The existing saved revision pair passed public archive validation without recomputing models. Its component deltas reconcile with a numerical residual near zero.
- Git comparison showed no tracked changes to R32 or its frozen input directories.

## Assessment

Ready with the P2 build fix. No additional concrete financial-semantics finding was identified in the reviewed snapshot. This is not a claim that a complete revision-enabled build passed; that path fails as described above.


## Follow-up resolution - 2026-09-22

**P2 resolved. This supersedes the original finding and assessment above.**

Verified the latest `build.py`: both run directories are resolved before validation/enumeration (lines 23-25), and all input/code manifest keys and hashes are prepared before `out.mkdir` (lines 41-47).

Independent verification used the same real July replay pair with repository-relative paths and intercepted all output creation/writes in memory. The build completed, produced a complete manifest, and its generated output hashes matched. All 39 input and 27 code hashes were prepared before directory creation. A targeted failure injected specifically while hashing `build.py` also produced no directory or write calls.

Preview3 independently verified all 39 input hashes and all 3 output hashes. Its revision is the July HARD_BASE historical replay (+0.0273985046 pp), while the September live forecast remains unavailable. Both the preview and latest renderer explicitly label the collapsed July working example as historical/not prospective and state that no current prospective pair exists. The services heading reads "Services inflation edged lower". Current source edits postdate preview3; the snapshot was not represented as containing every subsequent source change.

The 10 analysis checks passed again. The two new build regression tests were inspected; their disk-writing suite was not rerun under this review's read-only scope. The real-pair in-memory build and targeted pre-write failure probe independently verified the relevant fix without creating test artifacts.

No further broad review was undertaken, as requested. No remaining issue identified in the reviewed P2 fix. Only REVIEW.md was written; no worker/frozen files, model backtests, or commits were touched.


## Source-definition correction and August core scope - 2026-09-22

**The earlier broad-series withholding assessment is superseded.** Frozen `data/core_split/canonical_metadata.json` explicitly maps:

- `SCPICLEM02YOYPECNA` / saved `goods`: other tradables excluding food and fuel prices.
- `SCPICLEM03YOYPECNA` / saved `services`: nontradables excluding regulated prices.

These ARAD CPI_CLE series retain first-round tax effects and are not an exact partition of tax-corrected CNB core. Their July values (+0.4% / +4.6%) and CZSO broad goods/services (-0.2% / +4.7%) describe different concepts; the difference is not evidence of numerical corruption. The previous description of these values as a conflicting broad-series source issue was incorrect.

Verified the current renderer restores both histories with the labels "Other tradables excl. food/fuel" and "Nontradables excl. regulated". The trend footnote and Source definitions panel explain their scope and tax treatment. `analysis.assemble()` verifies the canonical metadata against its frozen manifest, embeds the definitions, and clears `source_issues`. The builder includes both the metadata and its manifest as inputs.

Verified the new `Core (CNB)` card uses the separate `official_release.cnb_august.core` value of 3.0%, dated August 2026 and labeled "August observed · y/y". Its local source record links to the official CNB August commentary and marks it as an observed actual, not a CNB forecast or independent model input. The external webpage was not re-fetched by this review. The 37-group panel and model origin remain July; this observation does not constitute a current model refresh or resolve the blocked prospective forecast.

All 11 current analysis tests passed independently, including the new definition/core test; the main task reports 13 total checks including its two build tests. No additional finding arose from this focused source-scope check. The P2 build resolution remains in force. Only REVIEW.md was modified.
