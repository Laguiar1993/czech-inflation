"""Declared 2021-23 monetary energy scenarios; no CPI outcome fitting/scoring.

Run: python energy_ledger_experiment.py
Writes only output/energy_ledger_*; never feeds the production nowcast.
"""
from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re

import pandas as pd

from models.energy_ledger import (VERSION, BaselineEnergy, BasketWeights, Bill, Exposure,
    ExposurePortfolio, MissingExposureBounds, PolicyEvent, headline_increment,
    item_relative, paid_bill, policy_intervals)


ROOT = Path(__file__).resolve().parent
SELECTION = "No fitting, outcome scoring, or promotion; scenario diagnostics only."
GAPS = [
    "No historical household contract/product exposure panel or CPI sample weights.",
    "Supplier percentage denominator and pre-January-2022 commodity/network split unverified.",
    "No product-level fixed charges, distribution bands, or comparable dated household bills.",
    "2021 billed quantities are not the same as calendar consumption or the CPI spreading base.",
    "17.4bn CZK national expenditure allocation cannot identify household CPI credit incidence.",
    "Eurostat band averages are not September CPI sample bills; the 2022 half-year proxy is retrospective.",
    "VAT waiver CPI-treatment knowledge date remains absent in the existing public-event ledger.",
    "Published basket shares approximate contributions; exact chain-link price-update weights are missing.",
    "No archived vintage proves every bill/exposure assumption was available at a historical cutoff.",
]


def stamp(day):
    """Date-only archives are conservatively available at end of their UTC day."""
    return datetime.fromisoformat(day + "T23:59:59+00:00")


def load_inputs():
    snapshots = {}

    def read_csv(relative):
        raw = (ROOT / relative).read_bytes()
        snapshots[relative] = hashlib.sha256(raw).hexdigest()
        return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

    params = {r["param"]: r for r in read_csv("data/energy_accounting_params.csv")}
    history = read_csv("data/admin_announcements_history.csv")
    ledger = read_csv("data/energy_policy_ledger.csv")
    release_calendar = read_csv("data/release_calendar_cz_cpi.csv")

    def value(name, unit):
        row = params[name]
        if row["unit"] != unit:
            raise ValueError(f"{name}: incompatible source unit {row['unit']}; expected {unit}")
        return float(row["value"])

    notes = params["avg_household_elec_consumption"]["notes"]
    points = int(re.search(r"([0-9,]+) connection points", notes).group(1).replace(",", ""))
    jan23 = next(r for r in history if r["effective_month"] == "2023-01"
                 and r["provenance"] == "sourced_retrospective")
    proxy = float(re.search(r"/ ([0-9.]+) CZK/kWh", jan23["notes"]).group(1))*1000
    allocation = value("saving_tariff_credit_elec", "CZK_million_total_oct_dec")*1e6
    if not any(r["policy_id"] == "vat_waiver_2021" and not r["treatment_known_date"] for r in ledger):
        raise ValueError("VAT source gap changed; review the frozen scenario specification")
    return dict(evidence_status="scenario_only", source_gaps=GAPS, source_hashes=snapshots,
        points=points, allocation_czk=allocation, allocation_credit_month=allocation/points/3,
        annual_mwh=value("avg_household_elec_consumption", "MWh_per_year"),
        electricity_2021=value("avg_household_elec_price_2021", "CZK_per_MWh"),
        gas_2021=value("avg_household_gas_price_2021", "CZK_per_MWh"),
        electricity_2022_proxy=proxy, levy=value("poze_fee", "CZK_per_MWh"),
        supplier_electricity=value("supplier_elec_commodity_change", "pct")/100,
        supplier_gas=value("supplier_gas_commodity_change", "pct")/100,
        network_electricity=value("eru_regulated_component_change_2022", "pct")/100,
        network_gas=value("eru_regulated_gas_component_change_2022", "pct")/100,
        cap_electricity_ex_vat=value("cap_elec_incl_vat", "CZK_per_MWh")/1.21,
        release_calendar=release_calendar)


def basket(year, inputs):
    relative = f"data/baskets/spot_kos{year}.xlsx"
    raw = (ROOT/relative).read_bytes()
    inputs["source_hashes"][relative] = hashlib.sha256(raw).hexdigest()
    frame = pd.read_excel(io.BytesIO(raw), header=None)
    shares = {item: float(frame.loc[frame[0].eq(code), 4].iloc[0])/1000
              for item, code in (("electricity", "E04.510"), ("gas", "E04.521"))}
    day = next(r["detail_release_dt"] for r in inputs["release_calendar"] if r["target_month"] == f"{year}-01")
    return BasketWeights(shares, stamp(day), relative + "; publication from release_calendar_cz_cpi.csv")


def make_bill(item, product, quantity, total_per_mwh, commodity_share, levy=0, fixed=0):
    """Preserve the declared all-in bill while explicitly allocating its components."""
    pretax = total_per_mwh/1.21
    commodity = pretax*commodity_share
    distribution = pretax-commodity-levy-fixed/quantity
    return Bill(product, item, quantity, commodity, distribution, fixed, levy, .21,
        ("commodity", "distribution", "fixed", "levy"),
        "Scenario fixed monthly MWh; Eurostat band proxy allocated to commodity/network/fixed; split is unverified.")


def make_event(policy, action, month, item, kind, value, unit, public, known, source,
               assumption, products=()):
    pub = stamp(public)
    treatment = stamp(known) if known else None
    return PolicyEvent(f"{policy}:{action}", policy, action, month, item, products, kind,
        value, unit, pub, treatment, max(pub, treatment) if treatment else pub, source, assumption)


def vat_events(item, *, assume_mapping):
    note = ("Hypothetical CPI mapping at government announcement; not sourced treatment knowledge."
            if assume_mapping else "Treatment knowledge date missing in the source ledger: ineligible.")
    args = dict(policy=f"vat_{item}", item=item, kind="vat_rate", public="2021-10-20",
                known="2021-10-20" if assume_mapping else None, source="data/energy_policy_ledger.csv", assumption=note)
    return [make_event(action="start", month="2021-11", value=0, unit="fraction", **args),
            make_event(action="expiry", month="2022-01", value=None, unit=None, **args)]


def credit_events(credit, inputs):
    assumption = "Fixed CZK per household divided across Oct-Dec; household CPI mapping is an unverified scenario."
    args = dict(policy="saving_credit", item="electricity", kind="credit", public="2022-10-03",
        known="2022-11-10", source="data/energy_accounting_params.csv; decree 262/2022; CZSO October note", assumption=assumption)
    events = [make_event(action="start", month="2022-10", value=credit, unit="CZK/month", **args),
              make_event(action="expiry", month="2023-01", value=None, unit=None, **args)]
    poze = dict(policy="poze_waiver", item="electricity", kind="levy_waiver", public="2022-06-23",
        known="2022-11-10", source="data/announcement_sources/poze_waiver_2023/MPO_press_release_2022-06-23_valecny_balicek.md",
        assumption="POZE removed Oct-2022 through Dec-2023 as announced; Oct CPI treatment held unchanged.")
    events += [make_event(action="start", month="2022-10", value=1, unit="fraction", **poze),
               make_event(action="expiry", month="2024-01", value=None, unit=None, **poze)]
    return events


def product_mix(item, fraction, inputs, commodity_share, fixed=0):
    quantity = inputs["annual_mwh"]/12 if item == "electricity" else 1.0
    levy = inputs["levy"] if item == "electricity" else 0
    exposures = tuple(Exposure(make_bill(item, product, quantity, inputs[f"{item}_2021"],
        commodity_share, levy, fixed), share) for product, share in
        (("fixed_contract", 1-fraction), ("repricing_contract", fraction)) if share > 0)
    return ExposurePortfolio(exposures, "Scenario household repricing share; fixed quantities and no observed contract weights.")


def repricing_events(inputs, *, assume_mapping=True):
    events = []
    for item in ("electricity", "gas"):
        events += vat_events(item, assume_mapping=assume_mapping)
        for component, kind, factor, public, products in (
            ("supplier", "commodity_multiplier", 1+inputs[f"supplier_{item}"], "2021-11-01", ("repricing_contract",)),
            ("network", "distribution_multiplier", 1+inputs[f"network_{item}"], "2021-12-01", ())):
            events.append(make_event(f"{component}_{item}", "start", "2022-01", item, kind,
                factor, "factor", public, public if assume_mapping else "2022-02-10",
                "data/energy_accounting_params.csv", "Scenario treats supplier percentage as commodity; network fixed fees unchanged.", products))
    return events


def contribution_row(scenario, group, portfolios, prev, month, cutoff, events, weights, baseline=1.0):
    relatives = {item: item_relative(p, prev, month, cutoff, events) for item, p in portfolios.items()}
    base = BaselineEnergy(prev, month, {item: baseline for item in relatives},
        "Explicit flat energy counterfactual" if baseline == 1 else "Hypothetical 2% normal energy rise already in headline baseline")
    contribution = headline_increment(relatives, weights, base)
    return dict(scenario=scenario, group=group, status="ok", previous_month=prev, month=month,
        as_of=cutoff.isoformat(), headline_gross_pp=contribution.gross_pp.estimate,
        baseline_energy_pp=contribution.baseline_pp, headline_incremental_pp=contribution.incremental_pp.estimate,
        electricity_mm_pct=(relatives["electricity"].estimate-1)*100 if "electricity" in relatives else None,
        gas_mm_pct=(relatives["gas"].estimate-1)*100 if "gas" in relatives else None,
        evidence_status="scenario_only", assumption=base.assumption)


def build_results():
    inputs = load_inputs()
    weights20, weights22 = basket(2020, inputs), basket(2022, inputs)
    rows = []
    # 2021: distinguish hypothetical tax arithmetic from unavailable treatment evidence.
    portfolios = {i: product_mix(i, 1, inputs, .477 if i == "electricity" else .7) for i in ("electricity", "gas")}
    rows.append(dict(scenario="vat_source_gated", group="availability", status="mapping_unavailable",
        month="2021-11", as_of=stamp("2021-10-31").isoformat(), headline_gross_pp=None,
        assumption=GAPS[6], evidence_status="scenario_only"))
    rows.append(contribution_row("vat_assumed_full_pass_through", "vat", portfolios,
        "2021-10", "2021-11", stamp("2021-10-31"),
        vat_events("electricity", assume_mapping=True)+vat_events("gas", assume_mapping=True), weights20))
    # Repricing shares/splits are an a-priori grid; the ERU source does not identify December shares.
    for share in (0.0, .5, 1.0):
        for commodity_share in (.477, .594):
            for fixed in (0.0, 100.0):
                p = {i: product_mix(i, share, inputs, commodity_share if i == "electricity" else .7, fixed)
                     for i in ("electricity", "gas")}
                row = contribution_row(f"repricing_{share:g}_commodity_{commodity_share:g}_fixed_{fixed:g}",
                    "january_2022_exposure", p, "2021-12", "2022-01", stamp("2021-12-31"),
                    repricing_events(inputs), weights20, baseline=1.02)
                row.update(repricing_household_share=share, electricity_commodity_share=commodity_share,
                    monthly_fixed_ex_vat=fixed, assumption=row["assumption"] + "; hypothetical early CPI treatment and unresolved bill split")
                rows.append(row)
    # Credit mapping and the seasonal quantity base are varied independently.
    mappings = {"national_allocation_per_connection": inputs["allocation_credit_month"],
                "decree_3500_per_connection": 3500/3, "decree_2000_per_connection": 2000/3}
    saved_events = []
    for mapping, credit in mappings.items():
        for q4 in (.25, .28):
            quantity = inputs["annual_mwh"]*q4/3
            b = make_bill("electricity", "representative", quantity, inputs["electricity_2022_proxy"], .55, inputs["levy"])
            p = ExposurePortfolio((Exposure(b, 1),), "Representative connection, not actual household sample; Q4 quantity assumption.")
            events = credit_events(credit, inputs)
            saved_events = events if mapping == "national_allocation_per_connection" else saved_events
            cutoff = stamp("2022-12-01")
            row = contribution_row(f"{mapping}_q4_{q4:g}", "credit_mapping", {"electricity": p},
                "2022-09", "2022-10", cutoff, events, weights22)
            sep, oct_, jan = [paid_bill(b, m, cutoff, events) for m in ("2022-09", "2022-10", "2023-01")]
            row.update(credit_czk_per_household_month=credit, q4_annual_quantity_share=q4,
                september_paid_czk=sep, october_paid_czk=oct_, january_paid_czk=jan,
                october_item_mm_pct=(oct_/sep-1)*100, january_item_mm_pct=(jan/oct_-1)*100,
                january_headline_gross_pp=weights22.shares["electricity"]*(jan/oct_-1)*100,
                assumption="2022 H1 Eurostat proxy held flat; no Jan repricing; POZE stays waived; Q4 quantity held fixed across comparison months")
            rows.append(row)
    # The literal low-consumption tariff allocation fails positive-price accounting.
    low = make_bill("electricity", "D01d", (557279/719625)/12, inputs["electricity_2022_proxy"], .55, inputs["levy"])
    try:
        paid_bill(low, "2022-10", stamp("2022-12-01"), credit_events(3500/3, inputs))
    except ValueError as exc:
        if "positive" not in str(exc):
            raise
        rows.append(dict(scenario="D01d_literal_quarterly_credit", group="credit_mapping",
            status="rejected_negative_bill", month="2022-10", headline_gross_pp=None,
            assumption="ERU D01d 557279 MWh / 719625 points; 3500 CZK/3 exceeds this proxy bill. Requires actual CPI expenditure mapping, not clipping.",
            evidence_status="scenario_only"))
    # Exact treatment availability is separate from economic policy announcement.
    reference = make_bill("electricity", "representative", inputs["annual_mwh"]/12,
                          inputs["electricity_2022_proxy"], .55, inputs["levy"])
    p = ExposurePortfolio((Exposure(reference, 1),), "Representative proxy; not a historical CPI vintage.")
    events = credit_events(inputs["allocation_credit_month"], inputs)
    rows.append(dict(scenario="october_before_treatment_publication", group="availability",
        status="mapping_unavailable", month="2022-10", as_of=stamp("2022-10-31").isoformat(),
        headline_gross_pp=None, visible_policy_intervals=len(policy_intervals(events, stamp("2022-10-31"))),
        assumption="Economic announcement known, but official CPI treatment not published until 10 November.", evidence_status="scenario_only"))
    rows.append(contribution_row("october_after_treatment_publication", "availability", {"electricity": p},
        "2022-09", "2022-10", stamp("2022-11-10"), events, weights22))
    # Missing households: retain a range, never insert a spurious central estimate.
    partial = ExposurePortfolio((Exposure(reference, .5),), "Only half of household mass represented.", complete=False)
    bounds = MissingExposureBounds((1200, 2200), (500, 1800), "Illustrative unknown-household CZK/month bill envelope, not a confidence interval.")
    r = item_relative(partial, "2022-09", "2022-10", stamp("2022-12-01"), events, missing=bounds)
    c = headline_increment({"electricity": r}, weights22,
        BaselineEnergy("2022-09", "2022-10", {"electricity": 1}, "Flat embedded baseline explicitly replaced."))
    rows.append(dict(scenario="half_households_unobserved", group="missing_exposure", status="bounded_no_point",
        month="2022-10", headline_gross_pp=c.gross_pp.estimate, headline_lower_pp=c.gross_pp.lower,
        headline_upper_pp=c.gross_pp.upper, assumption=bounds.assumption, evidence_status="scenario_only"))
    # A constant-quantity monthly level path shows the separate October onset / January expiry.
    base_bill = paid_bill(reference, "2021-01", stamp("2023-12-31"), [])
    for month in pd.period_range("2021-01", "2023-12", freq="M"):
        prev = str(month-1)
        row = contribution_row("flat_proxy_policy_level_path", "monthly_path", {"electricity": p},
            prev, str(month), stamp("2023-12-31"), events, weights20 if month.year < 2022 else weights22)
        paid = paid_bill(reference, str(month), stamp("2023-12-31"), events)
        row.update(paid_bill_czk=paid, price_index=100*paid/base_bill,
            assumption="Retrospective constant 2022 proxy bill, no underlying repricing; isolates credit/POZE over 2021-23.")
        rows.append(row)
    # Hash every source actually carried by this scenario, plus its own implementation.
    for relative in ("energy_ledger_experiment.py", "models/energy_ledger.py",
                     "data/announcement_sources/poze_waiver_2023/MPO_press_release_2022-06-23_valecny_balicek.md"):
        inputs["source_hashes"][relative] = hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
    manifest = dict(version=VERSION, selection_rule=SELECTION, evidence_status="scenario_only",
        specification="2021 VAT arithmetic; 2022 repricing share {0,.5,1}, electricity commodity share {.477,.594}, fixed charges {0,100}; 2022-23 credits {national allocation/points,3500,2000}/3 and Q4 fractions {.25,.28}.",
        quantity_basis="Fixed comparison quantity within every relative; Q4 seasonal share is an allocation sensitivity, not a changing CPI quantity.",
        aggregation="Normalize households within item; ratio of expenditure levels; published item basket share times percent change; subtract explicit embedded baseline.",
        datetime_rule="Date-only public sources available at 23:59:59 UTC; exact intraday timing not verified.",
        inputs={k:v for k,v in inputs.items() if k != "release_calendar"},
        baskets={2020:asdict(weights20), 2022:asdict(weights22)},
        policy_intervals=[asdict(i) for i in policy_intervals(saved_events, stamp("2022-12-01"))],
        outcome_data_used=False, fitted_parameters=False, promoted=False)
    return rows, manifest


def main():
    rows, manifest = build_results()
    output = ROOT/"output"
    output.mkdir(exist_ok=True)
    columns = list(dict.fromkeys(k for row in rows for k in row))
    with (output/"energy_ledger_scenarios.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    (output/"energy_ledger_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    exposure = [r["headline_gross_pp"] for r in rows if r["group"] == "january_2022_exposure"]
    credits = [r for r in rows if r["group"] == "credit_mapping" and r["status"] == "ok"]
    summary = dict(rows=len(rows), january_2022_headline_gross_range_pp=[min(exposure), max(exposure)],
        october_credit_scenario_headline_range_pp=[min(r["headline_gross_pp"] for r in credits), max(r["headline_gross_pp"] for r in credits)],
        january_credit_expiry_headline_range_pp=[min(r["january_headline_gross_pp"] for r in credits), max(r["january_headline_gross_pp"] for r in credits)],
        rejected_negative_bill_scenarios=sum(r["status"] == "rejected_negative_bill" for r in rows), evidence_status="scenario_only")
    (output/"energy_ledger_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
