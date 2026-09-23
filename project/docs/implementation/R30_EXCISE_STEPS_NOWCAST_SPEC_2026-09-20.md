# R30 specification: scheduled excise steps in the alcohol-and-tobacco block of the nowcast

20 September 2026, Claude. Declared before any code or evaluation on outcomes; committed before the code, the code before the single run. The first nowcast-lane round since R18; it changes one block's forecast by adding published tax decisions and nothing else.

## Why

The nowcast's alcohol-and-tobacco block is an expanding same-calendar-month mean (`cz_struct.alc_forecast`). It has no skill against that mean (block RMSE ratio 0.98 over 90 prints) and since 2024 it is 20% of the headline error variance; the largest misses are the months in which statutory excise steps enter the index (April 2024: forecast −0.06, print +2.16; January 2024 and 2026: 3.0 against 4.1 and 3.2 against 4.8). The CPI category data in the tree (`data/research_r18/categories/monthly_levels.csv`, classes 02.1 and 02.3) show the mechanism: tobacco prices rise in the three months after each rate change (the statutory sell-off window for cigarettes carrying the previous rate) and again in a manufacturer round in August–September; spirits reprice in January when their rate changes. The steps are published law, known months ahead. This round puts them in.

## Sources opened on 20 September 2026 (cite only these)

| Fact | Source | Provenance |
|---|---|---|
| Traditional tobacco excise +10% effective 1 February 2024, old-rate stock sold off through end-April (three months); +5% a year in 2025–2027; heated tobacco +15% a year with six-month sell-off | Ministry of Finance press release, 27 March 2024, "Spotřební daň z tabáku – co se mění od 1. dubna 2024" | sourced, primary |
| 2025–2027 rates take effect on 1 January of each year; 2026 minimum cigarette excise 4.66 Kč/piece | Customs Administration pages opened via search (WebKTV, "Aktuální sazby"); finance.cz calculator 2026 | sourced, secondary |
| Cigarette rates by year: fixed part / 30% / minimum, Kč per piece — 2021 1.79 / 3.20; 2022 1.88 / 3.36; 2023 1.97 / 3.52; 2024 2.17 / 4.22; 2025 2.28 / 4.44; 2026 2.39 / 4.66 | finance.cz cigarette taxation calculator (2026 page listing 2021–2026); finance.cz article on 2023 rates (1.97 / 3.52 against 1.88 / 3.36) | sourced, secondary |
| Rates before 2021: 1.46 / 27% / 2.63 from 2018; 1.61 / 30% / 2.90 from 1 March 2020 | cs.wikipedia "Spotřební daň" | secondary, reconstructed |
| Weighted average cigarette price per pack of 20 (MF, per year): 2021 102.38; 2022 114.98; 2023 125.24; 2024 135.14; 2025 144.94 Kč | Customs Administration, tobacco products page (WebKTV) | sourced, primary |
| Sell-off of old-rate cigarettes ends three months after a rate change (the 2017 example: until 31 March 2017 for the 1 January 2017 change) | Customs Administration, South Moravian office notice on rates and sell-off | sourced, primary |
| Spirits excise +10% in 2024, +10% in 2025, +5% in 2026 (consolidation package) | kurzy.cz, "Zvýšení daně z lihu – změny s účinností od 1. 1. 2024", 19 December 2023 | sourced, secondary |
| Tobacco excise plan for 2021–2023 (about +5% a year; +10% in 2021 implied by the 2020→2021 minimum 2.90→3.20) | aktualne.cz, 27 May 2020 (the 2021 tax package proposal) | secondary; the act (609/2020 Sb.) was not opened |
| Spirits excise unchanged 2010–2019 at 28,500 Kč/hl and raised to 32,250 Kč/hl from 1 January 2020 | not opened | reconstructed |
| Basket weights (per mille of CPI): tobacco 48.49 (2020), 47.82 (2022), 45.95 (2024), 46.15 (2026); spirits 14.39 / 14.15 / 13.47 / 13.17; the block 86.97 / 86.95 / 84.62 / 82.87 | `data/research_r18/categories/basket_weights_long.csv` (CZSO basket files in the tree) | sourced, in tree |

Act 349/2023 Sb. (the consolidation package) was opened at zakonyprolidi.cz only as far as its table of contents (Částka 163/2023, effective 1 January 2024); its rate paragraphs were not readable there. Every row of the calendar carries its provenance; reconstructed rows are used but flagged, and a variant without them is scored.

## The calendar (`data/excise_calendar_cz_r30.csv`)

One row per step: product (cigarettes, spirits), effective month, the statutory size as a percentage of the retail price, the months over which it lands, `available_from`, source, provenance.

- **Cigarettes.** Effective excise per piece at the year's weighted average price, `E_y = max(fixed_y + 0.30 × WAP_y/20, minimum_y)`; the statutory retail step is `(E_y − E_{y−1}) × 20 × 1.21 / WAP_{y−1}` (VAT 21%, no margin change). With the numbers above: 2021 +4.3% (E_2020 taken as 1.61 + 0.30 × WAP_2021/20 because WAP_2020 is not on the opened page; reconstructed), 2022 +6.6%, 2023 +5.1%, 2024 +7.2%, 2025 +4.2%, 2026 +3.4% (E_2026 at WAP_2025: the minimum binds). 2020 (1 March): the minimum rose 2.63 → 2.90; step 0.27 × 24.2 / 102.38 = +6.4% (reconstructed, WAP_2021 as denominator). Steps before 2020 are set to zero (the 2018 change moved the minimum by 2.3%; documented approximation).
- **Timing of the cigarette step.** One third in each of the three months after the effective month (the sell-off window): February–April for a 1 January change, March–May for the 1 February 2024 change, April–June for the 1 March 2020 change. Declared, not tuned; the category data show the mass in the first two of the three months, so this rule is conservative on the second month and generous on the third.
- **Spirits.** Rate change 1 January: 2020 +13.2%, 2024 +10%, 2025 +10%, 2026 +5%; retail step = rate change × θ with θ = 0.45, the assumed excise share of the retail price of spirits (no source opened for retail prices; θ is a declared assumption with a sensitivity grid 0.35 / 0.55). Lands entirely in January.
- **Block contribution.** `S(m) = w_tob(m)/w_block(m) × cigarette step × share(m) + w_spirits(m)/w_block(m) × spirits step × [January]`, with the basket weights of the year in force.
- `available_from`: 2024–2027 rows 19 December 2023 (the opened article; the act was promulgated earlier); 2021–2023 rows 31 December 2020 (reconstructed; the 2021 tax package); 2020 rows 31 December 2019 (reconstructed). Every scored month's clock (release eve) is later than the row it uses.

## Candidates (block level, h0)

Let `M(m)` be the recorded same-month expanding mean (`alc_pred_eve` in `output/cz_struct_backtest.csv`) and `S̄(m)` the mean of the calendar's contributions over the same past months that the expanding mean averaged (same-month observations released by the clock, from 2016).

| Candidate | Block forecast |
|---|---|
| `ALC_STEPS_R30` | `M(m) − S̄(m) + S(m)` (the seasonal mean of the ex-step series plus this year's statutory step) |
| `ALC_STEPS_SOURCED_R30` | the same with reconstructed rows (2020, 2021) set to zero, to show what the opened documents alone give |
| grid for condition 3 | θ ∈ {0.35, 0.55}; timing "all in the first month after the effective month" |

Headline candidate: `BASE + w_alc × (candidate − M)`, with `w_alc` the recorded weight of the release; the same increment is reported on FULL and Category Raw. Nothing else in the nowcast changes.

## Gates, read before any score

- The calendar against the category data: for each step, the realised class change over its landing months against the statutory size (tobacco: Feb–Apr sums 2021–2026 are 5.2, 3.8, 3.2, 3.4, 3.4, 2.6 in the class data; statutory 4.3, 6.6, 5.1, 7.2, 4.2, 3.4). If realised is below statutory in most years the pass-through is partial and the results say so; no pass-through fraction is fitted.
- Availability: every used row's `available_from` precedes the release-eve clock of the month it enters.
- Needed-against-applied: sign agreement of `S(m) − S̄(m)` with the block's error under `M` on the months where it is non-zero.

## Promotion rule (nowcast reading of R26)

1. Block RMSE at or below the recorded block's on all 90 prints, on prints from 2024 and on the flash era.
2. Headline RMSE (BASE + candidate) at or below BASE on the same three samples, and the large-surprise record (material wins / losses on the 23 prints with |surprise| ≥ 0.40) not worse.
3. Specificity: the candidate beats the best member of the grid on the full sample by a circular block bootstrap interval excluding zero *and* by at least 1% of the block RMSE; otherwise the promoted object is the simplest equivalent member.
4. In phase: sign agreement at least one half on the non-zero months.
5. Interval: the block's h0 squared-loss difference against `M` over the 90 prints with a circular block bootstrap interval excluding zero.
6. No condition on the path (h0 only).

## Expectations, written before running

- The block RMSE falls from 0.92 to 0.75–0.85 on the full sample and from 0.85 to 0.55–0.70 from 2024; the months that improve are the Januaries of 2020, 2024–2026 and the spring windows of 2021–2026; the August–September manufacturer rounds are untouched.
- Headline BASE RMSE improves by 0.005–0.015 on the full sample and 0.01–0.03 from 2024; April 2024 and January 2024/2026 become the clearest gains; no large surprise changes side.
- The sourced-only variant scores between BASE and the full candidate.
- θ = 0.45 is not distinguishable from 0.35 or 0.55; the timing alternative is worse.
- Condition 5's interval excludes zero on the full sample only if the 2024–2026 months carry it; I expect it to hold narrowly.

## Rules kept

Specification committed before code; code committed before the single run; rehearsal on a scratch copy; no hash-frozen file edited (the recorded backtest, the category data and the nowcast code are read only; the calendar is a new file); every figure in the results document reproduced by an exported file; no survey or consensus enters the forecast (consensus is used only to score it).
