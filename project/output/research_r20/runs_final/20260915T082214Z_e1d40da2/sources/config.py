"""
CZK CPI Nowcast — configuration.

Design references:
- CNB WP 9/2026 (Blaha, Botka, Švéda, Michl): TVW-QRF for Czech CPI, 72-predictor set,
  subcomponent targets (core, food, administered, fuel), h in {3,6,9,12}.
- CNB WP 2/2025 (Benecká): disaggregated PPI forecasting, ML + econometric fusion.
- Knotek & Zaman (2017 JMCB; 2023 IJF; Cleveland Fed nowcast): component-based CPI
  nowcast, fuel component from daily crude + weekly retail gasoline.
- Bańbura et al. (ECB WP 2930): disaggregate consumer-price nowcasting; policy measures
  hit only a subset of items -> model components, not just the aggregate.
- Modugno (ECB WP 1324): daily/weekly price data in a mixed-frequency factor model.
- Linzenich & Meunier (ECB WP 3004): nowcasting toolbox — DFM, bridge combinations.
- Schnorrenberger & Schmidt (DNB WP 806): weekly ML nowcasts of Brazilian CPI.
"""
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 1. Target decomposition (CNB analytical breakdown of CZSO CPI)
#    CPI m/m = sum_i w_i * pi_i(m/m). Weights = CPI basket shares, updated
#    annually by CZSO in January. Values below are APPROXIMATE 2024-25 shares
#    used as fallback; run_nowcast pulls the current weights when available.
# ---------------------------------------------------------------------------
COMPONENT_WEIGHTS_FALLBACK = {
    "core":         0.575,   # CPI ex food, fuel, administered, indirect-tax effects (incl. imputed rent)
    "food":         0.188,   # food and non-alcoholic beverages
    "administered": 0.202,   # regulated/administered prices (energy tariffs, health, transport...)
    "fuel":         0.035,   # fuels and lubricants (CPI item 0722)
}

# ---------------------------------------------------------------------------
# 2. Public data sources (Phase 1). Bloomberg mapping lives in
#    data/bloomberg_adapter.py (Phase 2) with identical output schema.
# ---------------------------------------------------------------------------
# "Average consumer fuel prices in CR - weekly" — VERIFIED endpoints (Aug 2026)
# Product page: csu.gov.cz/produkty/average-prices-survey-of-selected-products-
#               fuels-and-oil-products-time-series
# Survey method (EU Oil Bulletin metadata): prices observed on MONDAYS, arithmetic
# average over 9 oil companies + 2 large stores (~1,515 stations, >40% of CZ
# public stations). So each weekly point = Monday snapshot, not a weekly mean.
CZSO_WEEKLY_FUELS_CSV = "https://data.csu.gov.cz/opendata/sady/CENPHMT/distribuce/csv"   # DataStat (primary)
CZSO_WEEKLY_FUELS_CSV_FALLBACK = "https://vdb.czso.cz/pll/eweb/cenyphm.data"             # legacy (fallback)
CZSO_WEEKLY_FUELS_SCHEMA = "https://data.csu.gov.cz/opendata/sady/CENPHMT/schema/csv"
CZSO_WEEKLY_FUELS_DOCS = "https://data.csu.gov.cz/datastat/info/SADA/CENPHMT"
CZSO_HEATING_OIL_CSV = "https://data.csu.gov.cz/opendata/sady/CEN0201F/distribuce/csv"   # CPI item 0453, minor
CZSO_DATASETS = {          # vdb.czso.cz open-data catalogue IDs (verify at data.gov.cz)
    "cpi":            "010063",
    "cpi_coicop":     "010137",
    "industrial_prod": "150004",
    "retail_trade":   "150030",
}
EUROSTAT = {  # Eurostat SDMX 2.1 REST, dataset codes for CZ
    "hicp_all":      ("prc_hicp_midx", {"coicop": "CP00",  "geo": "CZ", "unit": "I15"}),
    "hicp_food":     ("prc_hicp_midx", {"coicop": "CP01",  "geo": "CZ", "unit": "I15"}),
    "hicp_energy":   ("prc_hicp_midx", {"coicop": "NRG",   "geo": "CZ", "unit": "I15"}),
    "hicp_core":     ("prc_hicp_midx", {"coicop": "TOT_X_NRG_FOOD", "geo": "CZ", "unit": "I15"}),
    "hicp_de_food":  ("prc_hicp_midx", {"coicop": "CP01",  "geo": "DE", "unit": "I15"}),
    "esi_cz":        ("ei_bssi_m_r2",  {"indic": "BS-ESI-I", "geo": "CZ"}),
    "ppi_cz":        ("sts_inppd_m",   {"nace_r2": "B-E36", "geo": "CZ", "unit": "I21"}),
}
FRED = {  # anchors (needs FRED_API_KEY)
    "brent_usd":   "DCOILBRENTEU",
    "czk_usd":     "DEXCZUS" if False else "CCUSMA02CZM618N",  # monthly avg CZK/USD
    "eur_czk_ref": "CCEUSSP02CZM650N",
}
CNB_ARAD = {  # requires free API key (CNB_ARAD_KEY env var)
    "repo_rate":  "SFTP01M01",     # placeholder-style IDs — resolve via cnb.cz/arad/#/en/home
    "cpi_core":   "RESOLVE_IN_ARAD_UI",
}
EU_OIL_BULLETIN = "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"

# ---------------------------------------------------------------------------
# 3. Release calendar (encodes the intramonth information set)
# ---------------------------------------------------------------------------
RELEASE_CALENDAR = {
    "czso_weekly_fuels":   "weekly; Monday-observed snapshot published within days; 0-lag proxy for CPI item 0722",
    "czso_cpi_flash":      "preliminary estimate, ~last working day of reference month (introduced 2025; verify exact schedule)",
    "czso_cpi_full":       "~10th of M+1, 09:00 CET (Rychlé informace)",
    "eurostat_hicp_cz":    "~17th of M+1 (full); EA flash end of reference month (CZ not in flash)",
    "ec_surveys":          "~end of reference month (ESI, price expectations)",
    "czso_ppi":            "~16th of M+1",
    "cnb_fx":              "daily 14:30 CET fixing",
    "commodities":         "daily (Brent, TTF gas, agri futures)",
}

# ---------------------------------------------------------------------------
# 4. Model settings
# ---------------------------------------------------------------------------
@dataclass
class ModelConfig:
    target: str = "cpi_mm"                 # month-on-month %, NSA
    horizons: tuple = (0, 1, 3, 6, 12)     # 0 = current-month nowcast
    train_start: str = "2005-01"
    oos_start: str = "2012-01"             # expanding-window OOS evaluation start (h>=1 only,
                                            # via y_h1plus/load_headline_cpi_mm_extended -- validated
                                            # 2026-08-21: closes most of the gap to CNB WP 9/2026's own
                                            # numbers, h=3 0.872->0.715 vs their 0.669. h=0's nowcast
                                            # doesn't consume this and is unaffected.
    val_window: int = 12                   # TVW validation window (CNB WP 9/2026)
    tvw_half_life: int = 6                 # exponential kernel half-life, months
    # TVW3 five-quantile spec of CNB WP 9/2026 (Judge et al. 1988)
    tvw_quantiles: tuple = (0.10, 0.25, 0.50, 0.75, 0.90)
    tvw_lower: tuple = (0.00, 0.15, 0.30, 0.15, 0.00)
    tvw_upper: tuple = (0.15, 0.35, 0.50, 0.35, 0.15)
    qrf_trees: int = 500
    qrf_min_leaf: int = 3
    # quantile_forest's RandomForestQuantileRegressor defaults max_features to
    # 1.0 (verified via inspect.signature, 2026-09-05) -- every tree considers
    # ALL columns at every split, i.e. no Breiman-style random-subspace
    # selection at all, only bootstrap row sampling. That's the exact
    # mechanism Medeiros/Montes Schutte/Soussi's "Global Inflation
    # Forecasting" credits for RF's embedded-selection edge over EN/NN/XGB in
    # their 91-country panel. 1/3 is Breiman (2001)'s own regression
    # recommendation (sqrt(p) is the classification convention).
    # DEFAULT KEPT AT 1.0 (2026-09-05 PM): the 1/3 setting was adopted on the
    # strength of an h1 backtest whose regenerated target series does not
    # match published CPI prints (std 0.31 vs 0.73 -- looks seasonally
    # adjusted; see output/backtest_forecasts_h1.csv actuals vs commit
    # 7840f70's), so that validation is void. Re-tested on the h0-hybrid
    # (true NSA target, corrected ex-fuel construction): 1/3 is WORSE than
    # 1.0 at every sample split (own-window RMSE 0.793 vs 0.738; survey-
    # window all60 0.969 vs 0.908).
    # RESOLUTION (2026-09-05, later same day): the mid-run std-0.31 actuals
    # were the --synthetic smoke test transiently overwriting output/ (its
    # y really does have std ~0.31); once the live run finished, its actuals
    # matched commit 7840f70's byte-for-byte (max diff 0.0, n=175) AND
    # published prints, so the h1 target was never corrupted. The clean-
    # target re-validation then confirmed THIS note's conclusion anyway:
    # mf=1/3 on the point forecast costs +3-5% RMSE at h=1/h=3 (never
    # DM-significant), ~wash at h=6, -3-4% at h=12 -- 1.0 stays the point
    # default, agreeing with the h0-hybrid numbers above. Where 1/3 DOES
    # earn its keep is the distributional output: see qrf_band_max_features.
    qrf_max_features: float | str = 1.0
    # Second forest for the band/PIT/CRPS only (TVWQRF.band_max_features).
    # Random-subspace tree diversity widens the quantile spread the
    # all-features forest understates: measured same-origin 2026-09-05,
    # 5-95% coverage h=1 79%->93%, h=6 85%->89%, PIT/KS calibrated at all 4
    # horizons, point forecast untouched by construction. None = single
    # forest (old behaviour). Costs one extra forest fit per fit_predict.
    qrf_band_max_features: float | None = 1 / 3
    seed: int = 42

CFG = ModelConfig()
