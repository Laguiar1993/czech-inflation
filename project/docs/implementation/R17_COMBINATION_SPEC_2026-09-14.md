# R17 coherent path combinations — declared before integrated scoring

This follow-up is exploratory. Earlier R15/R16 findings and the negative standalone R17 food result are already known; there is no untouched holdout. Do not reinterpret chronological fitting as a preregistered discovery sample. No CNB or survey forecast selects parameters.

Fixed combinations retain the exact HARD_BASE h0 and all original origin weights. Combine monthly component percentage rates before recomputing headline monthly contributions and annual rates. Do not average annual forecasts or select a separate winner for each horizon.

- COMBO_CORE_R17: half CORE_NEWS_H0_R17 plus half monthly-transmission BOTH core; other components from FAST.
- COMBO_FOOD_FUEL_R17: symmetric-food replacement and annual-index fuel replacement; FAST core.
- COMBO_ALL_R17: those two blocks plus COMBO_CORE. Symmetric food is the parsimonious cost model, not an assertion it won the component experiment; asymmetric/own/seasonal remain visible single-block candidates.
- PATH_FAST_CURRENT_HALF_R17: equal monthly-path combination of FAST and current-core. This is a path combination, unrelated to the nowcast HALF correction.
- PATH_COMPONENT_HALF_R17: equal monthly-path combination of FAST and COMBO_ALL.

Two bounded chronological selectors:

1. PATH_COMPONENT_SELECT_R17 uses alpha in[0,.25,.5] for FAST+alpha*(COMBO_ALL−FAST). Defaultalpha0. Each alpha defines a complete own-origin monthly path and its annual-CPI forecast at h1..12.
2. PATH_POOL_R17 uses fixed quarter-step weights over(FAST,current-core,gentleR16,COMBO_ALL), with FAST>=.5, each other weight<=.25, weights sum1. Default allFAST. This yields seven allowed mixtures. It cannot replace FAST completely.

For both, at origin t only earlier origins s with s+12<t and every h1..12 detailed CPI label published by the t decision clock can enter. Require all candidate paths to be finite on the same validation origins. Use latest36 complete origins, minimum12. Objective=mean over origins/h1..12 of squared annual-headline errors+.05*sum(nonFASTweights²). The .05pp² penalty is an explicit conservative fixed research assumption, not optimized. Ties prefer more FAST and then deterministic declaration order. Save every candidate own-origin path, validation origin/release dates, objective and selected weight. Early insufficient history is an explicit FAST default.

Primary calendar is the original R16 all15-model annual-headline support; predictions and failures are retained for every90origin/h1..12 pair. Publish full-roster finite-common and paired comparisons in addition to this unchanged primary calendar. All single-block experiments stay in component tables even if not selected by a combined path.

Direction diagnostics retain the original strict four-core-band peak/trough definition. Add sustained movement using bands1,2,3: annualizedband3−band1>=.5pp and no adjacent decline of at least.5pp implies acceleration; <=−.5pp and no adjacent increase of at least.5pp implies deceleration; otherwise no signal. Missing bands are unavailable. Report hits, missed events and false alarms on one common support; do not convert conditional hit rate into unconditional usefulness. Headline base-effect direction and underlying core are reported separately.

Both original CNB clocks, .15pp material gain/loss threshold, every-report omission and12-calendar-origin block uncertainty remain. Retrospective latest-vintage inputs and reconstructed publication assumptions remain limitations. The original self-contained CNB replay layout is reused with model checkboxes and fixed-score sample independent of visibility. No change to the nowcast or production roster is authorized by a favorable research row alone.
