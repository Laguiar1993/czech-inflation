"""Table A6 of CNB Working Paper 9/2026, transcribed, with official source identities.

Source: Blaha, Botka, Švéda and Michl (2026), *AI-Based Forecasting of Czech
Inflation: Quantile Regression Forests with Dynamic Weights*, CNB WP 9/2026,
Table A6 on printed pages 34-37 (PDF pages 36-39).  The rows below were
checked against both the PDF text layer and the rendered pages on
12 September 2026.

``description`` is the paper's wording.  ``transform`` is the printed code:
0 level, 2 ``ln(X_t) - ln(X_{t-1})``, 3 ``X_t - X_{t-1}``.  The paper also
states (Section 4.1) that every series was X-13 seasonally adjusted before the
stationarity tests and transforms.

Survey rows reproduce Eurostat ``ei_bs*`` indicator labels word for word (for
example ``BS-SAEM`` "Expectation of the demand over the next 3 months"), and
the paper lists Eurostat among its sources; that is how the official codes
were assigned.  The paper's "13 months" is the 12-month consumer question.
Geography comes from the paper where printed (the G1/G3 headers, "(DE)",
"(PL)", "in Eurozone") and is flagged as an interpretation otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass

EC = "EC business and consumer surveys - "
X13_NOTE = "paper X-13 adjusts all series before transforming"


@dataclass(frozen=True)
class A6Row:
    number: int
    group: str
    description: str
    transform: int
    kind: str                     # hard, survey, expectation (runner policy semantics)
    geo: str
    geo_basis: str                # printed or interpretation
    official_source: str
    eurostat: str | None = None   # dataset:indicator for Eurostat BCS labels (SA)
    ecfin: str | None = None      # ECFIN seasonally adjusted series code
    local_source: str | None = None
    issues: tuple[str, ...] = ()


def _bcs(n, group, text, tr, kind, geo, basis, dataset, indic, ecfin, issues=()):
    return A6Row(n, group, EC + text, tr, kind, geo, basis, "European Commission BCS via Eurostat",
                 f"{dataset}:{indic}", ecfin, None, tuple(issues))


G1, G2, G3 = "G1: Real Activity CZ", "G2: Foreign influence", "G3: Confidence/Sentiment CZ"
G4, G5, G6, G7 = "G4: PPI", "G5: Financial", "G6: Commodities/Energy", "G7: Inflation Expectations"
M13 = "paper prints 13 months; the EC question is 12 months"
SIGNED_LOG = "transform 2 is a log difference but the series can be zero or negative"

ROWS: tuple[A6Row, ...] = (
    _bcs(1, G1, "Production development observed over the past 3 months", 0, "survey", "CZ", "printed",
         "ei_bsin_m_r2", "BS-IPT", "INDU.CZ.TOT.1.BS.M"),
    _bcs(2, G1, "Production expectations over the next 3 months", 0, "survey", "CZ", "printed",
         "ei_bsin_m_r2", "BS-IPE", "INDU.CZ.TOT.5.BS.M"),
    _bcs(3, G1, "Business situation development over the past 3 months", 3, "survey", "CZ", "printed",
         "ei_bsse_m_r2", "BS-SABC", "SERV.CZ.TOT.1.BS.M"),
    _bcs(4, G1, "Evolution of demand over the past 3 months", 3, "survey", "CZ", "printed",
         "ei_bsse_m_r2", "BS-SARM", "SERV.CZ.TOT.2.BS.M"),
    _bcs(5, G1, "Business activity (sales) development over the past 3 months", 3, "survey", "CZ", "printed",
         "ei_bsrt_m_r2", "BS-RPBS", "RETA.CZ.TOT.1.BS.M"),
    _bcs(6, G1, "Building activity development over the past 3 months", 3, "survey", "CZ", "printed",
         "ei_bsbu_m_r2", "BS-CTA-BAL", "BUIL.CZ.TOT.1.BS.M"),
    _bcs(7, G1, "Factors limiting building activity: shortage of labour", 3, "survey", "CZ", "printed",
         "ei_bsbu_m_r2", "BS-FLBA4-PC", "BUIL.CZ.TOT.2.F4S.M"),
    _bcs(8, G1, "Factors limiting building activity: shortage of material/equipment", 3, "survey", "CZ", "printed",
         "ei_bsbu_m_r2", "BS-FLBA5-PC", "BUIL.CZ.TOT.2.F5S.M"),
    _bcs(9, G1, "Factors limiting building activity: financial constraints", 3, "survey", "CZ", "printed",
         "ei_bsbu_m_r2", "BS-FLBA7-PC", "BUIL.CZ.TOT.2.F7S.M"),
    _bcs(10, G1, "Financial situation over the next 13 months", 3, "survey", "CZ", "printed",
         "ei_bsco_m", "BS-FS-NY", "CONS.CZ.TOT.2.BS.M", [M13]),
    A6Row(11, G1, "Unemployment", 0, "hard", "CZ", "printed", "CZSO/Eurostat LFS unemployment rate",
          local_source="data/paper_replication/czso_unemployment_release.csv; Eurostat une_rt_m",
          issues=("paper does not name the unemployment concept; LFS rate assumed from the listed sources",)),
    A6Row(12, G1, "Index of industrial production", 0, "hard", "CZ", "printed", "CZSO industrial production index",
          local_source="data/cz_ip_sa_level.csv (CZSO PRU01C, seasonally and calendar adjusted)",
          issues=(X13_NOTE + "; the CZSO level is already adjusted",)),
    A6Row(13, G1, "Building permits - CZSO", 0, "hard", "CZ", "printed", "CZSO number of building permits",
          local_source="data/paper_replication/czso_construction_release.csv (year-on-year index only)",
          issues=("paper converts the cumulative CZSO series into monthly counts (footnote 11)",)),
    A6Row(14, G1, "Rushin Index", 0, "hard", "CZ", "printed", "CNB Rushin index",
          local_source="data/paper_replication/paper_predictor_panel.csv:rushin (CNB XLS snapshot)",
          issues=("series starts in 2008; the paper imputes missing initial observations with the "
                  "Chen-Labonne (2023) factor procedure",)),
    A6Row(15, G1, "LUCI (Labour Utilisation Composite Index): Total", 0, "hard", "CZ", "printed", "CNB LUCI",
          issues=("quarterly; the paper interpolates to monthly with Chow-Lin (1971)",)),
    A6Row(16, G1, "LUCI (Labour Utilisation Composite Index): Wages and Labour costs", 0, "hard", "CZ", "printed",
          "CNB LUCI component", issues=("quarterly; the paper interpolates to monthly with Chow-Lin (1971)",)),
    A6Row(17, G1, "Unit labor costs: Nominal unit labor costs", 0, "hard", "CZ", "printed",
          "Eurostat namq_10_lp_ulc (nominal ULC, quarterly)",
          local_source="Eurostat namq_10_lp_ulc",
          issues=("quarterly; the paper interpolates to monthly with Chow-Lin (1971)",
                  "per-person versus per-hour and adjustment variant not stated")),
    _bcs(18, G2, "Industrial confidence indicator (DE)", 0, "survey", "DE", "printed",
         "ei_bsin_m_r2", "BS-ICI", "INDU.DE.TOT.COF.BS.M"),
    _bcs(19, G2, "Services confidence indicator (DE)", 3, "survey", "DE", "printed",
         "ei_bsse_m_r2", "BS-SCI", "SERV.DE.TOT.COF.BS.M"),
    _bcs(20, G2, "Retail confidence indicator (DE)", 3, "survey", "DE", "printed",
         "ei_bsrt_m_r2", "BS-RCI", "RETA.DE.TOT.COF.BS.M"),
    _bcs(21, G2, "Construction confidence indicator (DE)", 3, "survey", "DE", "printed",
         "ei_bsbu_m_r2", "BS-CCI-BAL", "BUIL.DE.TOT.COF.BS.M"),
    _bcs(22, G2, "Retail confidence indicator (PL)", 2, "survey", "PL", "printed",
         "ei_bsrt_m_r2", "BS-RCI", "RETA.PL.TOT.COF.BS.M", [SIGNED_LOG]),
    A6Row(23, G2, "Harmonised index of consumer prices (DE)", 2, "hard", "DE", "printed",
          "Eurostat HICP all items, Germany", local_source="Eurostat prc_hicp_midx (I15) / prc_hicp_minr (I25)"),
    A6Row(24, G2, "Unemployment (DE)", 0, "hard", "DE", "printed", "Eurostat une_rt_m, Germany",
          local_source="Eurostat une_rt_m"),
    A6Row(25, G2, "External economic relations: Balance of trade (FOB/FOB)", 2, "hard", "CZ", "interpretation",
          "Czech trade balance (label format suggests CNB ARAD)",
          local_source="data/paper_replication/paper_predictor_panel.csv:trade_balance", issues=(SIGNED_LOG,)),
    A6Row(26, G2, "Import prices", 2, "hard", "CZ", "interpretation", "CZSO import price index",
          local_source="data/czso_import_prices_sitc_monthly.csv (CEN0303 month-on-month, 2008+)"),
    A6Row(27, G2, "Inflation expectations: Domestic inflation expectations in Eurozone - balance of answers", 0,
          "expectation", "EA", "printed", "EC consumer survey price trends over the next 12 months, euro area",
          "ei_bsco_m:BS-PT-NY", "CONS.EA.TOT.6.BS.M",
          issues=("label format suggests a CNB ARAD series built from the EC consumer survey",)),
    A6Row(28, G2, "Inflation expectations: Perceived inflation in Eurozone - balance of answers", 0,
          "expectation", "EA", "printed", "EC consumer survey price trends over the last 12 months, euro area",
          "ei_bsco_m:BS-PT-LY", "CONS.EA.TOT.5.BS.M",
          issues=("label format suggests a CNB ARAD series built from the EC consumer survey",)),
    _bcs(29, G3, "Industrial confidence indicator", 3, "survey", "CZ", "printed",
         "ei_bsin_m_r2", "BS-ICI", "INDU.CZ.TOT.COF.BS.M"),
    _bcs(30, G3, "Expectation of the demand over the next 3 months", 3, "survey", "CZ", "printed",
         "ei_bsse_m_r2", "BS-SAEM", "SERV.CZ.TOT.3.BS.M"),
    _bcs(31, G3, "Expectation of the employment over the next 3 months", 3, "survey", "CZ", "printed",
         "ei_bsse_m_r2", "BS-SEEM", "SERV.CZ.TOT.5.BS.M"),
    _bcs(32, G3, "Services confidence indicator", 0, "survey", "CZ", "printed",
         "ei_bsse_m_r2", "BS-SCI", "SERV.CZ.TOT.COF.BS.M"),
    _bcs(33, G3, "Expectations of the number of orders placed with suppliers over the next 3 months", 3, "survey",
         "CZ", "printed", "ei_bsrt_m_r2", "BS-ROP", "RETA.CZ.TOT.3.BS.M"),
    _bcs(34, G3, "Business activity expectations over the next 3 months", 3, "survey", "CZ", "printed",
         "ei_bsrt_m_r2", "BS-REBS", "RETA.CZ.TOT.4.BS.M"),
    _bcs(35, G3, "Employment expectations over the next 3 months", 3, "survey", "CZ", "printed",
         "ei_bsrt_m_r2", "BS-REM", "RETA.CZ.TOT.5.BS.M"),
    _bcs(36, G3, "Retail confidence indicator", 3, "survey", "CZ", "printed",
         "ei_bsrt_m_r2", "BS-RCI", "RETA.CZ.TOT.COF.BS.M"),
    _bcs(37, G3, "Employment expectations over the next 3 months - construction", 3, "survey", "CZ", "printed",
         "ei_bsbu_m_r2", "BS-CEME-BAL", "BUIL.CZ.TOT.4.BS.M"),
    _bcs(38, G3, "Construction confidence indicator", 3, "survey", "CZ", "printed",
         "ei_bsbu_m_r2", "BS-CCI-BAL", "BUIL.CZ.TOT.COF.BS.M"),
    _bcs(39, G3, "Financial situation over the last 13 months", 3, "survey", "CZ", "printed",
         "ei_bsco_m", "BS-FS-LY", "CONS.CZ.TOT.1.BS.M", [M13]),
    _bcs(40, G3, "Savings over the next 13 months", 3, "survey", "CZ", "printed",
         "ei_bsco_m", "BS-SV-NY", "CONS.CZ.TOT.11.BS.M", [M13]),
    _bcs(41, G3, "Unemployment expectations over the next 13 months", 3, "survey", "CZ", "printed",
         "ei_bsco_m", "BS-UE-NY", "CONS.CZ.TOT.7.BS.M", [M13]),
    _bcs(42, G3, "Major purchases over the next 13 months", 3, "survey", "CZ", "printed",
         "ei_bsco_m", "BS-MP-NY", "CONS.CZ.TOT.9.BS.M", [M13]),
    A6Row(43, G4, "YoY change in Producer prices of agricultural products", 0, "hard", "CZ", "interpretation",
          "CZSO agricultural producer price index, year-on-year"),
    A6Row(44, G4, "YoY change in Producer prices of industrial products", 0, "hard", "CZ", "interpretation",
          "CZSO industrial producer price index, year-on-year"),
    A6Row(45, G4, "Producer prices of industrial products - Total", 2, "hard", "CZ", "interpretation",
          "CZSO CEN0201A industrial PPI level", local_source="data/cz_ppi_product_raw.csv"),
    A6Row(46, G4, "Producer prices of industrial products - Mineral resources", 2, "hard", "CZ", "interpretation",
          "CZSO CEN0201A industrial PPI level, section B", local_source="data/cz_ppi_product_raw.csv"),
    A6Row(47, G4, "Producer prices of industrial products - Manufactured goods", 2, "hard", "CZ", "interpretation",
          "CZSO CEN0201A industrial PPI level, section C", local_source="data/cz_ppi_product_raw.csv"),
    A6Row(48, G4, "Producer prices of industrial products - Electricity, gas, and steam", 2, "hard", "CZ",
          "interpretation", "CZSO CEN0201A industrial PPI level, section D", local_source="data/cz_ppi_product_raw.csv"),
    A6Row(49, G4, "Producer prices of industrial products - Water", 2, "hard", "CZ", "interpretation",
          "CZSO CEN0201A industrial PPI level, section E", local_source="data/cz_ppi_product_raw.csv"),
    A6Row(50, G4, "Producer prices of agricultural products - Animal based products", 2, "hard", "CZ",
          "interpretation", "CZSO agricultural producer price index, livestock products"),
    A6Row(51, G4, "Producer prices of agricultural products - Plant based products", 2, "hard", "CZ",
          "interpretation", "CZSO agricultural producer price index, crop products"),
    A6Row(52, G4, "Producer prices of agricultural products - Agricultural production and fish", 2, "hard", "CZ",
          "interpretation", "CZSO agricultural producer price index, agriculture and fish total"),
    A6Row(53, G5, "Yield of 10-year gov. debt, monthly average", 0, "hard", "CZ", "interpretation",
          "CNB ARAD SVSDM12", local_source="data/paper_replication/arad_selected.csv:SVSDM12"),
    A6Row(54, G5, "PRIBOR: Domestic interbank deposit market rate - 3 months, value at the end of the month", 0,
          "hard", "CZ", "interpretation", "CNB ARAD PRIBOR 3M end-of-month",
          issues=("local ARAD extract holds the monthly average SFTP04M2206, not the end-of-month value",)),
    A6Row(55, G5, "2 Week repo rate, value at the end of the month", 0, "hard", "CZ", "interpretation",
          "CNB ARAD SFTP01M11", local_source="data/paper_replication/arad_selected.csv:SFTP01M11"),
    A6Row(56, G5, "Real effective exchange rate: Deflated by PPI", 2, "hard", "CZ", "interpretation",
          "CNB ARAD SREERM101", local_source="data/paper_replication/arad_selected.csv:SREERM101"),
    A6Row(57, G5, "Real effective exchange rate: Deflated by CPI", 2, "hard", "CZ", "interpretation",
          "CNB ARAD SREERM103", local_source="data/paper_replication/arad_selected.csv:SREERM103"),
    A6Row(58, G5, "Client loans: Residents - Non-financial corporations, balance", 2, "hard", "CZ", "interpretation",
          "CNB ARAD SUCM100311XXX101101 (VST client loans, NFC total)",
          local_source="data/paper_replication/arad_selected.csv:SUCM100311XXX101101"),
    A6Row(59, G5, "Client loans: Residents - Households, balance", 2, "hard", "CZ", "interpretation",
          "CNB ARAD SUCM102211XXX101101", local_source="data/paper_replication/arad_selected.csv:SUCM102211XXX101101"),
    A6Row(60, G6, "Commodity prices: Brent Crude Oil, USD/barrel", 0, "hard", "WORLD", "printed",
          "commodity price series (label format suggests CNB ARAD); exact identity not stated"),
    A6Row(61, G6, "Commodity prices: Average natural gas price in Europe", 2, "hard", "EU", "printed",
          "commodity price series (label format suggests CNB ARAD); exact identity not stated"),
    A6Row(62, G6, "Commodity prices: Industrial metals price index", 2, "hard", "WORLD", "printed",
          "commodity price index (label format suggests CNB ARAD); exact identity not stated"),
    A6Row(63, G6, "Commodity prices: Food commodity price index", 2, "hard", "WORLD", "printed",
          "commodity price index (label format suggests CNB ARAD); exact identity not stated"),
    A6Row(64, G6, "Principal Components of Fuel prices - CZSO", 2, "hard", "CZ", "printed",
          "first principal component of CZSO weekly Petrol 95, Petrol 98 Super plus, diesel and LPG prices",
          local_source="data/paper_replication/cz_fuel_weekly_source.csv (Petrol 95, diesel, LPG)",
          issues=("footnote 14: four standardised fuel prices, first component explains over 93%",)),
    A6Row(65, G6, "Refinitiv - TRPC Natural Gas", 0, "hard", "EU", "printed", "Refinitiv natural-gas future",
          issues=("contract for delivery in 12 months, shifted forward 12 periods (Section 4.1)",)),
    A6Row(66, G6, "Refinitiv - ICE Europe Brent Crude Electronic Energy Future", 0, "hard", "WORLD", "printed",
          "Refinitiv ICE Brent future", issues=("contract for delivery in 12 months, shifted forward 12 periods",)),
    A6Row(67, G7, "Selling price expectations over the next 3 months", 3, "expectation", "CZ", "interpretation",
          "European Commission BCS via Eurostat", "ei_bsin_m_r2:BS-ISPE", "INDU.CZ.TOT.6.BS.M",
          issues=("paper prints no geography for G7; Czechia assumed",)),
    A6Row(68, G7, "Price expectations over the next 3 months - construction", 3, "expectation", "CZ",
          "interpretation", "European Commission BCS via Eurostat", "ei_bsbu_m_r2:BS-CPE-BAL", "BUIL.CZ.TOT.5.BS.M",
          issues=("paper prints no geography for G7; Czechia assumed",)),
    A6Row(69, G7, "Inflation expectations: Inflation expectations in the horizon 3 years by financial markets - "
          "in percentage points", 0, "expectation", "CZ", "interpretation", "CNB financial market inflation expectations",
          local_source="data/paper_replication/paper_predictor_panel.csv:price_expect_survey_36m"),
    A6Row(70, G7, "Inflation expectations: Inflation expectations in the horizon 1 year by financial markets in "
          "percentage points", 0, "expectation", "CZ", "interpretation", "CNB financial market inflation expectations",
          local_source="data/paper_replication/paper_predictor_panel.csv:price_expect_survey"),
    A6Row(71, G7, "Inflation expectations: Perceived inflation - balance of answers", 0, "expectation", "CZ",
          "interpretation", "EC consumer survey price trends over the last 12 months",
          "ei_bsco_m:BS-PT-LY", "CONS.CZ.TOT.5.BS.M",
          issues=("rows 27-28 print 'in Eurozone' and these do not; Czechia assumed",)),
    A6Row(72, G7, "Inflation expectations: Expected domestic inflation - balance of answers", 0, "expectation", "CZ",
          "interpretation", "EC consumer survey price trends over the next 12 months",
          "ei_bsco_m:BS-PT-NY", "CONS.CZ.TOT.6.BS.M",
          issues=("rows 27-28 print 'in Eurozone' and these do not; Czechia assumed",)),
)

BY_NUMBER = {row.number: row for row in ROWS}
PAPER_TRANSFORMS = {row.number: row.transform for row in ROWS}
PAPER_SAMPLE = ("2002-05", "2025-09")


def ecfin_nsa_code(code: str | None) -> str | None:
    """The unadjusted ECFIN code for a seasonally adjusted one (BS -> B, F4S -> F4)."""
    if code is None:
        return None
    parts = code.split(".")
    answer = parts[4]
    parts[4] = "B" if answer == "BS" else answer[:-1] if answer.endswith("S") else answer
    return ".".join(parts)
