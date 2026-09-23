# Retail/weekly food channel — scouting result + predeclared experiment

Declared 6 Sep 2026, before any implementation or data inspection beyond
source metadata. One experiment, one adoption rule.

## Scouting result
SZIF (State Agricultural Intervention Fund) publishes commodity market
reports with THREE price tiers per product: farmgate (CZV), processor
(CPV) and consumer incl. VAT (SC).
- The MONTHLY bulletins (e.g. dairy) publish ~10th-14th of M+1 — same
  timing as the CPI release itself ⇒ **no pre-release lead for h0**;
  useful only as validation/decomposition data.
- The WEEKLY market reports (milk, meat) carry farmgate/wholesale prices
  within ~1-2 weeks of observation ⇒ a genuine WITHIN-MONTH signal that
  our current farmgate basket (CEN0203B, published ~25th M+1, so only M−1
  enters) does not provide.
Conclusion: the valuable target is the WEEKLY FARMGATE/WHOLESALE tier —
an intra-month food signal — not a retail shelf-price feed (none with a
pre-release lead was found; the CZSO retail survey remains terminated).

## Predeclared experiment (to run once, when the scraper is built)
- Build: parser for SZIF weekly milk + pig + cattle price series (PDF
  bulletins), observation date + publication rule recorded per row;
  continuing-source check after 8 weeks of live pulls.
- Feature: within-month farmgate change for target month M = last weekly
  observation published by the forecast cutoff vs the prior month's
  average; enters ONLY the food block, as one additional ridge feature.
- Comparison: identical origins/cutoffs; food-block RMSE and headline
  effect, all/exJan/2024+, exactly as FOOD_EXPERIMENT_SPEC.md.
- **Adoption rule (frozen now)**: adopt only if food-block RMSE improves
  ≥5% on the full window AND 2024+, AND headline is not worse on either;
  otherwise record and close. No variant search; no weekly-series
  shopping beyond the three commodities named above.

Sources: szif.gov.cz market reports (weekly + monthly bulletins); CZSO
notes confirming the retail survey termination.

## Status (7 Sep 2026)
Executed as `FOOD_SZIF_SPEC.md` (predeclared 7 Sep, single run, two
decision times). That file records the source verification (SZIF listing
publication dates; numbers from the EU agri-food API mirror, verified exact
against the SZIF PDFs), the one declared amendment (month-mean of the
published weeks instead of the last observation) and the result.
