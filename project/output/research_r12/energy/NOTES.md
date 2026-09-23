# R12 energy/admin: all-month accounting works; strict historical additions unavailable

The new evidence wrapper is implemented and tested, but **no historical forecast
changes**. None of the 15 inventory rows supplies a complete, dated event-to-CPI
payload. All 90 strict-addition forecasts retain HARD_BASE. This measures the
fallback decision, not the predictive value of a fully populated event model.

The frozen specification was committed as `abd1342` before the first run. No
parameters were fitted, no numerical scenario was selected, and none of the frozen
baseline code, energy inputs or existing numerical outputs was changed.

## Comparison and replay

All units below are percentage points of monthly headline inflation. The 90
administered forecasts and solved release-eve core weights reproduce exactly
(maximum absolute difference zero). Other baseline components are reused from their
frozen forecasts rather than refitted. Current and future fixture values are removed
before the administered forecast or weight routine is called.

| Frame | n | BASE / strict MAE | BASE / strict RMSE | Direction correct |
|---|---:|---:|---:|---:|
| All | 90 | 0.262516 | 0.417952 | 50 / 78 nonzero surprises |
| Target >= 2024-01 | 31 | 0.169039 | 0.218978 | 20 / 25 |
| Ex-January | 83 | 0.248251 | 0.403333 | 46 / 71 |
| Flash era >= 2025-01 | 19 | 0.139296 | 0.173002 | 12 / 15 |
| Large surprises | 23 | 0.484583 | 0.698570 | 17 / 23 |

BASE and strict both have bias -0.025226. The unchanged references have all-sample
RMSE/MAE: category TARGET_OWN 0.408947/0.256505, HARD_HALF 0.413696/0.264373,
HARD_FULL 0.413931/0.269627. These reference differences are not energy results.

Of 13 upward large surprises, BASE/strict get direction right in 9; of 10 downward
ones, 8. Across all releases they issue 20 alerts at the declared 0.2pp threshold:
7 large surprises alerted, 13 other releases alerted, and 16 large surprises missed.
There are zero material wins/losses against BASE. Paired strict-minus-BASE MAE and
RMSE differences and their block-bootstrap intervals are identically zero in every
frame, mechanically because forecasts coincide. Full directions, alerts, material
gains/losses versus both BASE and consensus and the category/HALF/FULL references
are retained in the CSVs.

Status counts: 79 origins have no complete evidenced event payload, four have an
explicit incomplete mapping (November 2021; September, October and November 2022),
and seven Januaries preserve the existing baseline treatment. Every unavailable
candidate effect is null; only the explicitly applied *fallback adjustment* is zero.
The existing January mappings remain a comparator, not a newly certified strict
historical input set.

## What the evidence actually establishes

The [CZSO October-2022 methodology](https://csu.gov.cz/note-to-consumer-prices-of-energy-october-2022)
deducts the saving subsidy at the total-household electricity-expenditure level,
dividing the credit equally across October-December. It uses constant CPI quantities
derived from relative weights. A proxy annual bill or national credit divided by
connection points does not supply that denominator. The current page footer says
updated 9 November 2022; the [October-2023 note](https://csu.gov.cz/note-to-consumer-prices-of-energy-october-2023)
explicitly says methodology was published with the October-2022 release. R12 retains
10 November as the conservative treatment-confirmation date. The 9 November footer
does not prove earlier public availability. At the historical 9 November release-eve
cutoff, economic policy publication and treatment availability are therefore different.

The [Czech VAT note](https://csu.gov.cz/poznamka-ke-spotrebitelskym-cenam-energii-listopad-2021)
does supply methodology content missing from the old ledger: the temporary waiver
is treated as a tax-rate change, using currently applicable tariffs independently
of advance-payment timing. Its footer says updated 9 December 2021, without an
original-publication timestamp. The [dated 10 December release](https://csu.gov.cz/rychle-informace/consumer-price-indices-inflation-november-2021)
links the treatment note. R12 records 10 December as a conservative confirmation,
not an inferred first-publication date. This does not qualify the November release-eve
forecast. The original CSV remains untouched, and none of the realised CPI numbers
in these documents is used as an R12 magnitude input.

The archived 23 June 2022 MPO announcement establishes that POZE relief continues
through 2023; the archived January-2023 CZSO note separately confirms credit expiry
and levy-waiver persistence. Ending the credit must not also end POZE relief. The
local inventory does not supply comparable dated household bills or contract
exposure for September/November 2022 repricing. This bounded check does not claim
that no supplier announcements existed.

`sources/source_index.json` states exactly what each source supports. New captures
are present-day web-tool extracts, not archived historical HTTP responses. Their
hashes document the evidence inspected; they do not establish vintage availability.

## Scenario sensitivities kept separate

All **60 existing R9 scenario rows reproduce byte-for-byte**. No scenario is scored
against CPI outcomes. The unchanged grid spans January-2022 gross contribution
+1.315 to +3.267pp, October-2022 credit/levy scenarios -3.058 to -1.753pp and
January-2023 credit-expiry scenarios +2.436 to +11.649pp. The literal low-consumption
D01d credit mapping still fails the positive-bill check; it is not clipped into a
usable price. Partial-exposure bounds retain no central estimate.

These are assumption envelopes. Wide dispersion reflects missing exposure,
comparable quantities and subsidy allocation. Closeness to the known release is
not evidence for choosing a mapping. The frozen replay's old source-gap strings
describe its unchanged input ledger; the new R12 audit separately records newly
verified methodology content and remaining publication ambiguity.

## Operational handoff and minimum missing inputs

`models/admin_events_r12.py` wraps the existing R9 engine, without a month or
magnitude gate. An evidence record must name its subject, source, SHA-256 snapshot,
availability timestamp and verified/scenario status. Required subjects cover each
bill, each household-exposure portfolio, policy-source and treatment records,
weights and the energy baseline being replaced. A hash is a reviewed evidence
reference; callers remain responsible for checking that its contents support the
named input. The pure wrapper does not download or automatically authenticate sources.

The wrapper rejects missing/late evidence, unknown treatment, partial household
coverage, unavailable weights and missing energy-baseline decomposition. It computes
ratios from household expenditure levels. Replacement subtracts the evidenced energy
contribution already embedded in the forecast. Incremental mode compares with/without
policy on the same bills, quantities, exposure and weights; it does not subtract the
seasonal mapping again. The runner forces each payload to the historical target and
cutoff, and January integration deliberately preserves existing overlapping treatment.

The next useful collection consists of:

1. Dated supplier/product charges, fixed fees, tariff bands, quantities and tax scope
   for comparable pre/post-policy household bills.
2. Historically available household shares by fixed/variable/last-resort contract
   and actual repricing month, with a documented CPI population/aggregation mapping.
3. The saving-credit national CPI expenditure and constant-quantity allocation base,
   or an independently dated equivalent mapping; per-connection allocation is insufficient.
4. Independently published treatment clocks and linked start/expiry/amendment sources.
5. Item-level energy seasonality already embedded in the aggregate baseline, or
   evidenced with/without-policy counterfactuals that isolate the incremental effect.

Published basket contributions remain an approximation; exact chain-link replication
would additionally need the price-updated aggregation weights. The source request
above is sufficient to build a reviewed payload but cannot guarantee accuracy gains.

## Reproduction and tests

Run `python -m pytest test_admin_events_r12.py test_energy_ledger_r9.py -q`, then
`python admin_events_experiment_r12.py` from any working directory with the repository
available. Git is optional: a portable snapshot without its own `.git` records
`git_head: null` and `portable_snapshot_no_local_git`; it never discovers an
enclosing repository. A local checkout with missing, failed or timed-out Git records
unavailable provenance without affecting forecasts. The runner is offline, writes
only this output directory, and saves all
forecasts before opening the first-release outcome/survey file. The manifest uses
repository-relative paths for source hashes and records output hashes.

Test-first evidence: 37 wrapper contracts failed for the missing API, six experiment
contracts then failed for the missing runner, and the per-origin clock-audit contract
failed for its missing function. Five portability contracts additionally failed
before optional Git provenance was implemented. Final suite: **50 R12 plus 26
unchanged R9 tests**.
Tests cover all evidence clocks, exact availability boundaries, future-event and
future-input poisoning, strict payload integration, unknown-vs-zero outputs, start/
expiry arithmetic, continuing POZE, baseline subtraction, incomplete exposure,
all-90 baseline replay and byte-identical scenarios.

No live model is promoted. History is repeatedly inspected pseudo-OOS using frozen
latest-vintage component data and publication rules, not an untouched or fully
vintage-certified holdout.
