# Prospective announcement protocol — frozen 6 September 2026

Written BEFORE the November 2026 announcements exist. Changes after
2026-11-01 require a new dated section here; the original stays.

## Sources watched (October–December each year)
1. ERÚ price decisions (cenová rozhodnutí / výměry) — eru.gov.cz, usually
   ~Nov 25-30. Record the INITIALLY APPROVED numbers; conditional or
   later-amended figures are separate events with their own dates (lesson
   of the voided 2026 row).
2. Government decrees on caps/subsidies/VAT — zakonyprolidi.cz, vlada.gov.cz.
3. Supplier price lists: ČEZ, PRE, E.ON / innogy announcements (ceníky).
4. MPO/MF support programs (credits, waivers) INCLUDING their expiry dates.
5. CZSO methodological notes on CPI treatment — the treatment-knowledge
   clock, recorded separately from the policy announcement.

## Entry format
Every event goes into BOTH files at entry time:
- `data/admin_announcements_history.csv` row with `provenance=prospective`,
  real `available_from` (source publication date), magnitude from the
  frozen formula below;
- `data/energy_policy_ledger.csv` events (start/expiry/extension per
  policy_id) with `source_pub_date` and `treatment_known_date`.

## Frozen conversion formula (v1, from energy_accounting.py)
Per-fuel household paid-price LEVELS: commodity (capped if a cap is in
force) + network + levies, VAT applied, credits subtracted over their
months; regulated m/m = weighted fuel index change with the parameter
table `data/energy_accounting_params.csv` (each value sourced; gap-approx
entries must be replaced by sourced values BEFORE the November entry — the
seven currently flagged are the to-do list). The January gate then uses
the additive convention (announced shock + shock-excluded seasonal base)
unchanged from v2.2. No threshold changes (≥8% firing stays).

## Deadline and immutability
- Entry deadline: 7 calendar days after each source publication, and in
  any case before December 31.
- At entry: save the source document (PDF/HTML) under
  `data/announcement_sources/<policy_id>/`, record its SHA256 in the
  ledger notes, commit, and EXTERNALLY timestamp the commit hash (e-mail
  the hash to yourself and/or push to a remote) — a local git date alone
  is editable and does not prove priority (Codex review).
- Logged forecasts using these entries are never edited; corrections are
  new rows.

## What would count as success in January 2027
Not one good forecast — the test is operational: the entry existed before
January, its magnitude came from the frozen formula with sourced inputs,
and the resulting January forecast was logged before the release. Skill
is judged only after several such Januaries and the monthly prospective
record in between.

## Addendum 2026-09-06: ERÚ statutory calendar (sourced from eru.gov.cz/cenova-rozhodnuti)

ERÚ issues its cenové výměry on a statutory schedule: electricity (low
voltage + HV/VHV decrees) and the second gas decree by END NOVEMBER of
the preceding year; a first gas decree around May/June; **heat and POZE
support decrees by END SEPTEMBER**. Consequence: the first prospective
entries for January-2027 (heat + POZE components) become typeable around
2026-09-30 — a SEPTEMBER checkpoint is added ahead of the November one.
Unchanged rule: only decree LEVELS enter the ledger; press-release
percentages (which mix regulated-component and total-bill layers — the
ambiguity that voided the old 2026 row) are cross-checks only.

## Addendum 2026-09-07: re-verification routine (nothing recorded is assumed to still hold)

Announced measures change: a cap is extended, a credit ends early, a
decision is amended or replaced, a levy is reinstated. Every entry in the
ledger and the announcement file is therefore a claim with a date, and it
is re-verified at fixed moments. The evidence that a check happened is a
log row, not memory.

### When
1. Before EVERY live call (pre_flash and pre_final): all sources with
   cadence `every_call`.
2. Monthly, after the CPI detailed release: sources with cadence `monthly`
   (supplier price lists, the amended acts, the finance ministry).
3. Quarterly: the `quarterly` sources (broadcasting fee, health fees, water,
   transport fares).
4. Fixed checkpoints regardless of cadence: end of September (POZE and
   heat decisions), end of November (electricity and gas decisions),
   mid-December (supplier price lists, budget-related acts), and whenever
   the press reports a change to an energy or tax measure.

### How
- Run `python tools/check_announcement_sources.py [--cadence every_call]`.
  It fetches each page in `data/announcement_sources.csv`, hashes the
  visible text and appends one row per source to
  `data/announcement_source_checks.csv` with verdict UNCHANGED, CHANGED,
  FIRST or UNVERIFIED (fetch failed; a failure is never "unchanged").
- Every CHANGED page is read by a person. The question is always the
  same three: has an effective date moved (extension or early end), has a
  level or magnitude changed (amendment), has a measure been withdrawn or
  replaced (void)?
- Every finding becomes a NEW row, never an edit:
  - `data/energy_policy_ledger.csv`: `event` = `extension` (new expiry),
    `amendment` (new level; notes name the superseded row), or `void`;
    with `source_pub_date`, the new `effective_month`, blank
    `treatment_known_date` until CZSO's note exists, `provenance`
    prospective, the source URL and the SHA256 of the saved document under
    `data/announcement_sources/<policy_id>/`.
  - `data/admin_announcements_history.csv`: a new row for the same
    effective month with the recomputed magnitude from the frozen formula
    and a note "supersedes row of <date>"; the older row stays and is
    marked superseded in its notes only.
  - `data/energy_accounting_params.csv`: a new parameter row with the new
    `applies_from` / `applies_to`; the old row keeps its window.
- Precedence: the row with the latest `source_pub_date` that is on or
  before the decision clock governs. A row published after the clock is
  invisible to that call, even if it is already known when the call is
  logged.
- The live row records `announcement_check_age_days` (days since the last
  check of any source), `announcement_changed` and
  `announcement_unverified` (counts in that last check). A pre-release call
  with an age above 7 days, or with CHANGED pages not yet read, is logged
  with that fact visible; the evaluation classifier may treat it as
  incomplete inputs.
- THIN pages (JS-rendered shells with almost no visible text; the ČEZ press
  page is one) are always read by hand or through Firecrawl; their hash is
  recorded but proves nothing.
- UNVERIFIED sources (blocked, timed out) are re-tried once; if still
  unverified the check is completed by hand from a browser and the log
  row's note says so.

### What does not change
The conversion formula, the January gate threshold and the additive
convention stay frozen; re-verification changes inputs and dates, never
rules. If a rule has to change it gets a dated section here first.

## Addendum 2026-09-07 (v2.7.1, Codex R8): entries are stored in economic units

Supersedes the magnitude part of "Entry format" and the threshold sentence
of the frozen formula. Nothing else in the protocol changes.

- **What a row stores.** The per-fuel January change in percent of the
  household paid price, `elec_pct`, `gas_pct`, `heat_pct`, each derived
  from the dated documents by the frozen formula and written into the
  notes with its arithmetic. The column `announced_regulated_mm_est_pct`
  stays EMPTY for documented and prospective rows: a block-unit value is a
  headline effect divided by a fitted administered weight, and a fitted
  coefficient is never stored as historical data.
- **How the code prices it.** Headline contribution = sum over the three
  fuels of (CPI basket item weight per mille / 1000) x change, with the
  weights of the latest basket PUBLISHED at the decision clock
  (electricity 04.510, network gas 04.521, heat 04.550; table
  `_ENERGY_ITEM_WEIGHTS` in `cz_struct.py`, one line per even-year basket
  from `data/baskets/spot_kos{year}.xlsx`). The gate fires when that
  contribution is at least 1.1 pp of monthly CPI in absolute value
  (equal to the old 8 block units at the mean administered weight; firing
  set unchanged). The block receives contribution / administered weight
  OF THE SAME CALL, so the headline effect equals the contribution exactly
  at every clock and under every basket.
- **Maintenance.** When CZSO publishes a new basket (with the January
  detailed release of even years), add its three item weights to
  `_ENERGY_ITEM_WEIGHTS` in the same commit that adds the basket file; the
  regime becomes usable from the publication date recorded by
  `_basket_available_from`, never earlier.
- **Two policies, two rows of the ledger.** A credit and a levy waiver with
  different expiry dates are separate ledger events; the January reversal
  only reverses what expires (the 2023 correction: the saving tariff ended,
  the POZE waiver continued). Fixed CZK amounts reverse additively.
- **Cross-check before the deadline.** For the November entry, compute the
  contribution once by hand from the documents and once by the code from
  the CSV row; they must agree to 0.01 pp, and the number in the notes must
  be the hand computation.
