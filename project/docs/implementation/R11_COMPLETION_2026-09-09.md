# R11 completion record

The immutable pre-scoring declaration is CORE_REMAINDER_PLAN_2026-09-09.md,
committed as f1d9e0a before the first R11 forecasts. Its unchecked original plan
is preserved for provenance; completion is recorded here instead of rewriting
that hashed declaration after seeing results.

Completed: pure two-variant remainder experiment; 13 new tests; 90-origin exact
own-category replay; past-only label/expectations poisoning; common scoring and
up/down surprise panels; 12-file exact offline replay; independent code review;
independent non-core audit; all-horizon path review and omitted simple benchmark;
updated nowcast roles; report and portable delivery. No path model was fitted or
changed, and no operating forecast was replaced.

Independent review found no actionable correctness issue within the declared
R10-style API. It independently checked 900 unchanged category predictions,
90 macro-remainder matches, origin-weight reconstruction and unpublished-label
poisoning. The relevant R9/R10/R11 suite passed 262 tests with two existing X-13
warnings. The original R10 experiment remains exactly reproducible.

New model findings: full independent predictors in the remainder give overall
RMSE 0.413358 and big-event MAE 0.509313; own remainder dynamics plus macro inputs
give 0.414149 / 0.517520. Simple categories remain 0.408947 / 0.511988. Neither
diagnostic is adopted. BASE remains operating reference, categories research
accuracy challenger, HALF/FULL the existing correction comparisons.

Non-core and path evidence is reproducible with tools/r11_review/. All90 non-core
error sums close within6.32e-16; eight targeted food forecasts reproduce via X-13.
The path review reproduces84 saved scores within8.89e-16. It adds reporting
panels and an explicitly separate y/y random-walk benchmark, not an optimized
path candidate. The detailed latest assessment distinguishes present capability
from future food/category/energy experiments.
