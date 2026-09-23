# CZK CPI Nowcasting Model — Research Note & Implementation

Fundamental, backtested nowcasting framework for Czech consumer price inflation. Phase 1 runs entirely on public data (CZSO, Eurostat, CNB ARAD, FRED); Phase 2 swaps in Bloomberg for the daily market inputs via `data/bloomberg_adapter.py` with an identical schema, so no model code changes.

---

## 1. What the literature says, and what this model takes from it

**CNB WP 9/2026 — Blaha, Botka, Švéda, Michl, "AI-Based Forecasting of Czech Inflation: Quantile Regression Forests with Dynamic Weights" (Apr 2026).** The CNB's own state of the art for the exact target we care about. Key facts this model inherits directly: (i) the target is *month-on-month* CPI plus the CNB's four analytical subcomponents — core, food, administered, fuel — forecast separately; (ii) 72 predictors in seven groups (real activity CZ, foreign influence esp. Germany, confidence/sentiment, PPI, financial, commodities/energy, inflation expectations), with the fuel predictor built as the first PC of four CZSO pump-price series (>93% of variance); (iii) point forecasts are a Time-Varying Weighted combination of QRF quantiles (five-quantile "TVW3" spec, 12-month validation window, 6-month exponential half-life) which beats QRF mean/median, AR(3), ARIMA(3,1,3), RW and an LQR ensemble at h=3/6/12 (headline RMSE 0.669 vs 0.710 for AR(3) at h=3); (iv) administered prices are close to unforecastable from history (RMSE ~3.2 across every model they try) — persistence-based modelling is pointless there; (v) tree models did not extrapolate into the 2021–23 surge until surge observations entered the training set. `models/horizon_models.py::TVWQRF` is a faithful reimplementation of their sections 3.2–3.4 (eqs. 2–7).

**Knotek & Zaman (2017 JMCB; 2023 IJF; Cleveland Fed daily nowcast).** The canonical component-based CPI nowcast: core extrapolated from recent trends, food modelled, gasoline *measured* from daily Brent and weekly retail pump prices. Their published track record beats SPF nowcasts on average. The h=0 layer here (`models/components.py`) is this design transplanted to Czech data — which is unusually well suited to it because CZSO itself publishes **weekly average pump prices** (open-data CSV, Mondays for the prior week) that map almost one-to-one into CPI item 0722.

**Bańbura et al., ECB WP 2930 "Nowcasting consumer price inflation" + ECB Statistics Paper 38 (PCCI).** Disaggregate modelling earns its keep for *inflation* (unlike GDP, where Bańbura–Modugno showed disaggregation adds little): energy caps, VAT changes and administrative measures hit narrow item sets, so component models absorb them cleanly while aggregate models mistake them for broad-based shocks. This is the core argument for the component architecture, doubly so in Czechia where administered prices are ~20% of the basket and the 2022 energy measures were exactly such item-specific shocks.

**Modugno, ECB WP 1324 "Nowcasting inflation using high-frequency data".** Daily/weekly price data in a mixed-frequency factor model materially improves the current-month HICP nowcast; commodity timeliness matters more than smoothness. Justifies the intramonth Brent-in-CZK tail projection for the unobserved remainder of the fuel month.

**Linzenich & Meunier, ECB WP 3004 "Nowcasting Made Easier" (+ GitHub toolbox).** The ECB's production stack combines DFM, bridge-equation combinations and pre-selection. Bridge combinations are competitive with DFMs at monthly frequency with far less machinery — hence `BridgeOLS` for food/core rather than a full DFM in v1. Their toolbox (MATLAB) is worth mining if you later want the DFM layer.

**Schnorrenberger & Schmidt, DNB WP 806 (Brazil).** Weekly ML nowcasts of monthly CPI using ~20 predictors that are either higher-frequency or released intramonth, plus the BCB's daily analyst survey. Template for the *weekly-updating* production loop: re-run on every data release, not on a monthly schedule. The CNB's monthly FM inflation-expectations survey plays the (weaker) role of the Focus survey.

**CNB WP 2/2025 (Benecká, disaggregated PPI ML), CNB WP 8/2025 (Franta & Vlček, Inflation at Risk), Adam et al. 2021 (Rushin weekly activity index), CNB WP 13/2025 (web reviews for nowcasting).** Domestic evidence that (a) tree ensembles + pipeline-pressure variables work at the sectoral PPI level feeding CPI cost pass-through, (b) the CNB itself frames risk via conditional quantiles — so keeping the QRF's 5th/95th quantiles as an upside-pressure indicator matches how the Board consumes forecasts, (c) the Rushin index is a ready-made weekly activity control available in ARAD.

**Benchmark discipline (Atkeson–Ohanian 2001; Stock–Watson 2007; Faust–Wright 2013).** Univariate benchmarks are brutally hard to beat in low-inflation regimes; every model here is Diebold–Mariano-tested against AR(3) with the Harvey small-sample correction, and the ensemble weights are inverse-RMSE so a fancy model that stops earning its complexity gets down-weighted automatically.

## 2. Architecture

```
                    ┌──────────── h = 0 (current month) ────────────┐
weekly pump prices ─► fuel: measured MTD mean vs prior-month mean,   │
Brent(CZK) daily  ─►       tail projected via pass-through beta      │
agri PPI, DE food ─► food: BridgeOLS + month dummies                 ├─► Σ wᵢπᵢ = CPI m/m nowcast
PPI, expectations ─► core: BridgeOLS + AR(1) + January dummy         │    + component contributions
ERÚ announcements ─► administered: ANNOUNCEMENT OVERRIDE (not model) │
                    └────────────────────────────────────────────────┘
                    ┌──────────── h = 1,3,6,12 ─────────────────────┐
predictor panel   ─► TVW-QRF (5-quantile, dynamic weights)           ├─► point + 5–95% band
                  ─► AR(3), ARIMA(3,1,3), RW benchmarks              │    + inverse-RMSE ensemble
                    └────────────────────────────────────────────────┘
                     expanding-window OOS backtest, RMSE / DM / z-score
```

Design decisions and why:
- **m/m NSA target with month dummies**, not y/y: y/y is 11/12 base effects; all news is in the m/m. y/y is reconstructed after the fact (chain the m/m path onto the realized index, as WP 9/2026 does in Table A4).
- **Administered prices are an input, not a forecast.** Energy tariffs (ERÚ decisions, usually effective 1 Jan), water, health fees are announced in advance. `admin_override` injects them. Modelling them costs RMSE ~3.2 for nothing.
- **Fuel is measured, not modelled**, for the observed part of the month. With 3 of ~4.3 weeks observed you already know ~70% of the monthly average mechanically.
- **QRF quantile band is a risk product, not decoration** — the (actual − 95th quantile) gap is the CNB's own "upside inflation pressure" read.

## 3. Data map (Phase 1, public)

| Input | Source | Frequency / lag | Role |
|---|---|---|---|
| CPI all-items + COICOP | CZSO 010063 / 010137 (open data) | M, ~10th of M+1 | target |
| CPI flash estimate | CZSO preliminary estimate (new since 2025 — pin exact schedule on first pull) | ~end of ref. month | early truth for evaluation |
| Core/food/admin/fuel split | CNB ARAD (free API key) | M | component targets |
| Weekly pump prices | CZSO "Average consumer fuel prices – weekly" CSV; cross-check EU Weekly Oil Bulletin | W (Mon, ~0 lag) | fuel h=0 |
| Brent, CZK/USD, EUR/CZK | FRED + CNB FX API (daily fixing 14:30) | D | fuel tail, pass-through |
| PPI (industry, agri) | Eurostat sts_inppd_m / CZSO | M, ~16th M+1 | pipeline pressures |
| DE food/energy HICP, DE surveys | Eurostat | M | foreign influence (dominant per BIS: ~85% of CZ inflation variance is global) |
| ESI, price-expectation balances | EC surveys via Eurostat | M, end of ref. month | expectations (dominant Shapley group in the surge) |
| FM inflation expectations 1y/3y | CNB survey | M | expectations |
| Rushin index, LUCI | CNB ARAD | W/M | real activity |

Phase 2 (Bloomberg): daily CO1, EURCZK/USDCZK, TTF, agri futures + CZCPMOM/CZCPYOY release history via the skill's `bopen()`/`pdblp` pattern with parquet cache (`data/bloomberg_adapter.py`). Keep the CNB component split from ARAD — Bloomberg's coverage of the CNB analytical breakdown is patchy.

## 4. Backtest protocol

Expanding window from `oos_start` (default 2015-01); at each origin the model sees data to *t−h* only, mimicking WP 9/2026. Metrics: RMSE (full + rolling 12m), MAE, direction correlation, DM vs AR(3) (HLN-corrected), residual 24m z-score as a surprise indicator. Known regime caveat: 2021–23 will dominate squared losses — report metrics ex-surge as well before drawing conclusions, and expect the QRF to have underpredicted the surge in real time exactly as the CNB documents.

## 5. Running it

```bash
pip install -r requirements.txt
python run_nowcast.py --synthetic         # end-to-end validation, no internet
FRED_API_KEY=... CNB_ARAD_KEY=... python run_nowcast.py   # live
QRF_TREES=500 HORIZONS=1,3,6,12 OOS_START=2015-01 python run_nowcast.py
```
Outputs to `./output/`: model-vs-actual chart, rolling RMSE, residual z-score, h=0 contribution bar, metrics + forecast CSVs.

## 6. Honest limitations / next steps

1. **Live endpoints must be pinned on first run.** CZSO open-data CSV URLs and stapro codes drift; ARAD indicator IDs must be resolved once in the ARAD UI (cnb.cz/arad/#/en/home). The fetchers fail loudly by design.
2. The backtest shipped here ran on **synthetic data** (structure-matched to Czech CPI) to validate the machinery — network in this environment is restricted to package registries. Numbers in `output/` prove the pipeline, not Czech-specific accuracy. First live milestone: reproduce WP 9/2026's Table 2 ordering (TVW3 < AR3 < ARIMA < RW at h=3) on the real panel.
3. Real-time vintages: CZSO CPI is essentially unrevised, but PPI and surveys are not; for a strict real-time evaluation store vintages from day one (parquet cache per pull date).
4. Missing v1 features worth adding, in order of expected payoff: (i) CNB component targets from ARAD so the h=0 bridges train on true components; (ii) the announcement file for administered prices (ERÚ tariff decisions, excise changes); (iii) scanner-data-based CZSO average monthly prices for the food bridge (the field survey was discontinued end-2025 — scanner data is now the primary source); (iv) Shapley decomposition for the QRF (shap.TreeExplainer, as in WP 9/2026 §3.5); (v) a DFM layer from the ECB toolbox if you want a daily-updating single number.

## 7. Key references

CNB WP 9/2026 (Blaha, Botka, Švéda, Michl); CNB WP 2/2025 (Benecká); CNB WP 8/2025 (Franta, Vlček); Adam, Michálek, Michl, Slezáková (CNB WP 4/2021, Rushin); Knotek & Zaman (2017 JMCB; 2023 IJF); Bańbura, Giannone, Modugno, Reichlin (Handbook 2013); Bańbura et al. (ECB WP 2930); Modugno (ECB WP 1324); Linzenich & Meunier (ECB WP 3004); Lenza, Moutachaker, Paredes (EER 2025); Meligkotsidou et al. (2014); Meinshausen (2006); Schnorrenberger & Schmidt (DNB WP 806); Atkeson & Ohanian (2001); Stock & Watson (2007); Faust & Wright (2013).

---
## Changelog
- **v0.2 (2026-08-20)**: pinned verified CZSO weekly-fuel endpoints (DataStat dataset `CENPHMT`, legacy `cenyphm.data` fallback, schema + docs links in config); encoded Monday-snapshot survey semantics (9 companies + 2 stores, ~1,515 stations, arithmetic average) — expected weekly observations per month now = count of Mondays; added heating-oil dataset `CEN0201F`; added `data/admin_announcements.csv` template for the administered-price override.
