# R21B: a policy target as a long-run reference, not a borrowed forecast

Declared after R21 first-batch results, before anchor fits or scores. This is an explicitly adaptive second research hypothesis, not part of an untouched pre-registration.

Motivation: the FAST filter allows its persistent core trend to remain elevated indefinitely. A credible nominal policy objective can help define a long-run reference even in a survey-independent model. It cannot guarantee convergence or justify forcing headline CPI to 2% at h12. The CNB has had a 2% headline inflation target since 2010: https://www.cnb.cz/en/monetary-policy/inflation-target/index.html . Our scored origins all postdate 2010.

Two fixed candidates, no tuned winner: ANCHOR_HL12_R21 and ANCHOR_HL24_R21. At origin t compute monthly log anchor = [100 log(1.02) + shrunk past median annual-log(core)-annual-log(headline) spread]/12. Each annual spread uses 12 contiguous, published months strictly before t. Use latest120 eligible annual spreads, minimum60; shrink their median by n/(n+120). The correction acknowledges that core and headline are different concepts, but is a statistical approximation to equilibrium, not an identity or estimated policy reaction function.

For FAST's saved persistent state mu from t-1, replace future trend at t+h with anchor + (mu-anchor)*2^[-(h+1)/HL], for HL12 or24. Preserve saved cycle .8^(h+1), own-origin seasonal factors, non-core blocks and basket weights. Independent HARD_BASE h0 is untouched. The h+1 transition count is necessary because the latest core observation is t-1.

Evaluate both on the identical full/recent 969 keys and both CNB clocks alongside every R21 candidate; no clipping or forcing the h12 headline number to target. Record anchor estimate, sample dates and latest release. Test missing publication/future poisoning; verify the infinite-half-life limit recovers FAST; verify exact contribution arithmetic. Report whether any apparent gain depends on pandemic/war observations or loses recent accuracy. Score improvement cannot be called causal evidence of credible policy or advance turn identification.
