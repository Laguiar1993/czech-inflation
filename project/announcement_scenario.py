"""Sourced retrospective scenario for the January energy gate (7 Sep 2026).

Question: had the announcement entries existed before each January, built
ONLY from documents dated before that January and run through the protocol's
formula with no free parameter, what would the January forecasts have been?

This is a SCENARIO, provenance sourced_retrospective: the author knows the
outcomes. Bias is limited by construction, not removed:
  - inputs are numbers printed in dated documents (table below, URLs);
  - one fixed rule for the per-fuel change: the regulator's stated total
    household bill change when the ERU release states one, otherwise
    regulated change x pre-change regulated share + dominant-supplier
    commodity change x (1 - share); VAT changes and the CZSO-booked credit
    reversal are multiplicative on top; heat is 0 (no document);
  - fuel weights = CPI basket item weights of the basket PUBLISHED at the
    clock (the January basket is published mid-February; network gas only),
    the same table cz_struct uses (_ENERGY_ITEM_WEIGHTS); the headline
    effect is exactly sum(weight/1000 x change) and never depends on the
    solved administered coefficient (v2.7.1, Codex R8);
  - the gate is the coded one: fires when |headline effect| >= 1.1 pp;
  - the base is the RELEASE-EVE GATE-CLOSED column STRUCT_NOANN_EVE (v2.7.1;
    reading STRUCT_EVE under v2.7+ would add the effect twice), so the
    scenario forecast equals the scored v2.7.1 forecast up to the January
    base exclusion;
  - single pass; the calm Januaries are the false-alarm test.
v2.7.1 corrections to the document table (see ANNOUNCEMENT_ADOPTION_v27.md,
declared correction): 2022-01 shares (regulated 52.3% / commodity 47.7%),
2023-01 credit-only additive reversal with the POZE waiver continuing.
The v2.7 table is preserved as data/announcement_scenario_inputs_2019_2026_v27_superseded.csv.
Usage: python announcement_scenario.py
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cz_struct as S  # noqa: E402

GATE_PP = S._GATE_HEADLINE_PP
# CPI basket weights per mille: electricity 04.510, network gas 04.521, heat 04.550 (data/baskets), shared with cz_struct
BASKET = S._ENERGY_ITEM_WEIGHTS


def _elec_2023_additive():
    sept, dec = 170.6, 82.7
    oct_with, oct_without = 46.1, 100.8                 # CZSO note 10 Nov 2022, Sept = 100
    poze_share = 0.599 / 6.0269                         # 599 CZK/MWh incl VAT / Eurostat H1-2022 CZ band DC price
    credit_points = (oct_without - oct_with) / 100.0 - poze_share
    return 100 * ((dec + credit_points * sept) / dec - 1)

# Document table: per event month, the per-fuel change in percent and its derivation
DOCS = [
    dict(month="2019-01", elec=0.55 * 2.1 + 0.45 * 8.0, gas=0.0, heat=0.0, basket=2018,
         how="elec: ERU LV regulated +2.1% (30 Nov 2018, eru.gov.cz/regulovane_ceny_2019) x share 55% (ERU) + CEZ +8% non-fixed (Jan 2019, aktualne.cz) x 45%; gas: no document -> 0"),
    dict(month="2020-01", elec=0.55 * 1.3, gas=0.20 * 0.53, heat=0.0, basket=2018,
         how="elec: ERU households regulated +1.3% (26 Nov 2019) x 55%; CEZ commodity rise only from March 2020 -> 0 in January; gas: ERU +0.53% x 20%"),
    dict(month="2021-01", elec=0.477 * -1.7, gas=0.30 * -1.6, heat=0.0, basket=2020,
         how="elec: ERU LV regulated -1.7% (30 Nov 2020, eru.gov.cz/eru-oznamuje-regulovane-ceny-elektriny-a-plynu-pro-rok-2021-0) x 47.7% share; gas: ERU -1.6% x 30%; no January commodity change"),
    dict(month="2021-11", elec=100 * (1 / 1.21 - 1), gas=100 * (1 / 1.21 - 1), heat=0.0, basket=2020,
         how="VAT waived on electricity and gas for Nov-Dec 2021 (government decision 20 Oct 2021, mfcr.cz): factor 1/1.21 on both"),
    dict(month="2022-01", elec=100 * (1.21 * (1 + 0.523 * 0.037 + 0.477 * 0.33) - 1), gas=100 * (1.21 * (1 + 0.30 * 0.024 + 0.70 * 0.55) - 1), heat=0.0, basket=2020,
         how="v2.7.1: VAT back to 21% x [ERU regulated +3.7% elec / +2.4% gas (1 Dec 2021, eru.gov.cz/regulovane-slozky-cen-energii-neprekroci-inflaci) on the PRE-CHANGE REGULATED shares 52.3% elec (the release: unregulated 47.7% at the end of the previous year, 59.4% after) / 30% gas + CEZ commodity +33% elec / +55% gas (1 Nov 2021, zscr.cz) on the unregulated rest]; v2.7 had the electricity shares transposed (+44.0%)"),
    dict(month="2023-01", elec=_elec_2023_additive(), gas=0.11 * 1.7, heat=0.0, basket=2022,
         how="v2.7.1: credit-only reversal, POZE waiver continuing. CZSO note 10 Nov 2022: October electricity index 46.1 vs 100.8 without the saving tariff and the POZE waiver (Sept = 100); the saving tariff ends 31 Dec 2022, the POZE waiver (599 CZK/MWh incl VAT) continues through 2023 (ERU price decision 13/2022 of 14 Nov 2022, point 5.1: component 0 CZK/A/month for 2023; announced by the government 23 Jun 2022 for Oct 2022 - Dec 2023). Additive: POZE share 0.599 / 6.0269 CZK/kWh (Eurostat H1-2022) = 9.9%; credit = 54.7% - 9.9% = 44.8% of the September level 170.6 = 76.4 points; January = December index 82.7 (released 11 Jan 2023) + 76.4 = 159.1 -> +92.3% (v2.7: +106.3%, full return to September, which also reversed the waiver; multiplicative sensitivity +85.8%); X = 1 (cap 5,000 CZK/MWh ex VAT, decree 298/2022, taken as prevailing); gas: cap at prevailing -> 0, plus ERU regulated +1.7% (16 Nov 2022) x 11% share"),
    dict(month="2024-01", elec=0.0, gas=-4.0, heat=0.0, basket=2022,
         how="ERU 30 Nov 2023 (eru.gov.cz/eru-zverejnil-regulovane-ceny-elektriny-plynu-na-rok-2024): electricity total 'practically offsets' -> 0; gas total 'expected to decline ~4%' -> -4"),
    dict(month="2025-01", elec=-10.0, gas=-8.0, heat=0.0, basket=2024,
         how="ERU 29 Nov 2024 (eru.gov.cz/eru-zverejnil-regulovane-slozky-cen-elektriny-plynu-na-rok-2025): electricity bills 'over a tenth' lower -> -10; gas 'more than 8%' lower -> -8"),
    dict(month="2026-01", elec=100 * ((3430 / 0.608 - 840) / (3430 / 0.608) - 1), gas=0.80 * (-70 / 1359 * 100), heat=0.0, basket=2024,
         how="CEZ 30 Dec 2025 (cez.cz press 230772): D02 commodity 3,430 -> 3,190 ex VAT and the government-approved regulated cut of 599 CZK/MWh, total -840 CZK/MWh on a bill whose commodity share is 60.8% (ERU 2024 statement); gas: commodity -70 CZK/MWh on 1,359 x 80% share"),
]


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    if "STRUCT_NOANN_EVE" not in bt.columns:
        raise SystemExit("output/cz_struct_backtest.csv has no STRUCT_NOANN_EVE column: rerun the backtest under v2.7.1 or later "
                         "(reading STRUCT_EVE as the base under v2.7+ would add the announcement effect twice)")
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv")); ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext = ext.set_index("p"); ext = ext[ext["era"] != "flash_survey_suspect"]
    rows = []
    for d in DOCS:
        t = pd.Period(d["month"], freq="M")
        if t not in bt.index:
            continue
        as_of = t.to_timestamp(how="end")
        we, wg, wh = S._energy_item_weights_at(t, as_of)
        assert (we, wg, wh) == BASKET[d["basket"]], (t, d["basket"])
        w_adm = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc)[S._regime(t)]["administered"]
        headline_add = (we * d["elec"] + wg * d["gas"] + wh * d["heat"]) / 1000.0   # pp of headline
        a = headline_add / w_adm                                                     # block units AT THIS CALL (information only)
        fires = abs(headline_add) >= GATE_PP and (t.month == 1)
        fires_any = abs(headline_add) >= GATE_PP
        base = float(bt.loc[t, "STRUCT_NOANN_EVE"])
        rows.append({"month": str(t), "elec_pct": round(d["elec"], 1), "gas_pct": round(d["gas"], 1), "heat_pct": d["heat"], "w_adm": round(w_adm, 3),
                     "a_regulated_mm": round(a, 1), "headline_add_pp": round(headline_add, 2), "gate_fires_jan_rule": fires, "gate_fires_any_month": fires_any,
                     "actual": float(ext.loc[t, "actual"]), "survey": float(ext.loc[t, "survey_median"]), "BASE_gate_closed": round(base, 2),
                     "scenario_jan_rule": round(base + headline_add, 2) if fires else round(base, 2),
                     "scenario_any_month": round(base + headline_add, 2) if fires_any else round(base, 2),
                     "STRUCT_EVE_scored": round(float(bt.loc[t, "STRUCT_EVE"]), 2),
                     "regulated_actual": float(bt.loc[t, "adm_actual"]), "how": d["how"]})
    sc = pd.DataFrame(rows).set_index("month")
    sc.to_csv(os.path.join(HERE, "data", "announcement_scenario_inputs_2019_2026.csv"))
    pd.set_option("display.width", 250)
    print(sc.drop(columns=["how"]).to_string())
    # effect on the 90-origin board (release-eve clock)
    d = ext[["actual", "survey_median"]].join(bt[["STRUCT_NOANN_EVE"]], how="inner")
    for label, col in (("January-only gate (as coded)", "scenario_jan_rule"), ("gate on any announced month", "scenario_any_month")):
        s = d["STRUCT_NOANN_EVE"].copy()
        for m, r in sc.iterrows():
            s.loc[pd.Period(m, freq="M")] = r[col]
        e = s - d["actual"]; e0 = d["STRUCT_NOANN_EVE"] - d["actual"]; es = d["survey_median"] - d["actual"]
        jan = d.index.month == 1
        print(f"\n{label}: RMSE all 90  base {np.sqrt((e0**2).mean()):.3f} -> scenario {np.sqrt((e**2).mean()):.3f}  (survey {np.sqrt((es**2).mean()):.3f}); "
              f"January only  base {np.sqrt((e0[jan]**2).mean()):.3f} -> {np.sqrt((e[jan]**2).mean()):.3f} (survey {np.sqrt((es[jan]**2).mean()):.3f}); "
              f"ex-January unchanged {np.sqrt((e[~jan]**2).mean()):.3f}")
        big = (d["actual"] - d["survey_median"]).abs() >= 0.4 - 1e-9
        g = es.abs() - e.abs(); g0 = es.abs() - e0.abs()
        print(f"   big-surprise MAE base {e0[big].abs().mean():.3f} -> {e[big].abs().mean():.3f} (survey {es[big].abs().mean():.3f}); W-L@0.15 base {int((g0[big]>=0.15).sum())}-{int((g0[big]<=-0.15).sum())} -> {int((g[big]>=0.15).sum())}-{int((g[big]<=-0.15).sum())}")
    fired = sc[sc["gate_fires_jan_rule"]]
    print(f"\nJanuaries where the gate fires: {list(fired.index)}; false alarms (fires with |regulated actual| < 8): {[m for m, r in fired.iterrows() if abs(r['regulated_actual']) < 8]}")
    print("scenario vs scored v2.7.1 STRUCT_EVE at the firing months (they differ only by the January base exclusion):")
    for m, r in fired.iterrows():
        print(f"  {m}: scenario {r['scenario_jan_rule']:.2f}  scored {r['STRUCT_EVE_scored']:.2f}  print {r['actual']:.1f}  survey {r['survey']:.1f}")


if __name__ == "__main__":
    main()
