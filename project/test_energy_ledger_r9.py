"""Acceptance contracts for the independent energy bill accounting challenger."""
from datetime import datetime, timezone
from importlib import import_module, util
from dataclasses import replace

import pytest


def api():
    assert util.find_spec("models.energy_ledger") is not None, "bill ledger API is missing"
    return import_module("models.energy_ledger")


def at(day):
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


def bill(**changes):
    m = api()
    values = dict(product_id="standard", item="electricity", quantity_mwh=1.0,
                  commodity=600.0, distribution=200.0, fixed=100.0, levy=100.0,
                  vat_rate=0.21, taxable_components=("commodity", "distribution", "fixed", "levy"),
                  assumption="Fixed monthly comparison quantities; CZK ex VAT charges.")
    return m.Bill(**(values | changes))


def event(policy="credit", action="start", month="2022-10", kind="credit", value=300.0,
          unit="CZK/month", available="2022-09-01", **changes):
    m = api()
    return m.PolicyEvent(**(dict(event_id=f"{policy}:{action}", policy_id=policy,
        action=action, effective_month=month, item="electricity", products=(),
        kind=kind, value=value, unit=unit, published_at=at("2022-08-01"),
        treatment_known_at=at("2022-08-02"), available_from=at(available),
        source="archived-public-source", assumption="Declared test policy mapping.") | changes))


def portfolio(shares=(1.0,), **changes):
    m = api()
    return m.ExposurePortfolio(tuple(m.Exposure(replace(bill(), product_id=f"p{i}"), s)
        for i, s in enumerate(shares)), assumption="Household counts normalized within item.", **changes)


def test_fixed_money_credit_is_additive_after_tax():
    m = api()
    assert m.paid_bill(bill(), "2022-10", at("2022-10-31"), [event()]) == pytest.approx(910)


def test_vat_is_multiplicative_on_explicit_scope_only():
    m = api()
    waiver = event(policy="vat", kind="vat_rate", value=0.0, unit="fraction")
    assert m.paid_bill(bill(), "2022-10", at("2022-10-31"), [waiver]) == 1000
    assert m.paid_bill(bill(taxable_components=("commodity",)), "2022-09", at("2022-10-31"), []) == 1126


def test_publication_treatment_and_availability_all_gate_exact_cutoff():
    m = api()
    e = event(available="2022-11-10", treatment_known_at=at("2022-11-10"))
    assert m.paid_bill(bill(), "2022-10", at("2022-11-09T23:59:59"), [e]) == 1210
    assert m.paid_bill(bill(), "2022-10", at("2022-11-10"), [e]) == 910
    unknown = replace(e, treatment_known_at=None)
    assert m.paid_bill(bill(), "2022-10", at("2023-01-31"), [unknown]) == 1210
    with pytest.raises(ValueError, match="available_from"):
        replace(e, published_at=at("2022-11-11"))


def test_credit_onset_expiry_have_opposite_sign_while_poze_persists():
    m = api()
    events = [event(), event(action="expiry", month="2023-01", value=None, unit=None),
              event(policy="poze", kind="levy_waiver", value=1, unit="fraction")]
    p = portfolio()
    oct_r = m.item_relative(p, "2022-09", "2022-10", at("2022-12-01"), events)
    jan_r = m.item_relative(p, "2022-12", "2023-01", at("2022-12-01"), events)
    assert oct_r.estimate == pytest.approx(789 / 1210)
    assert jan_r.estimate == pytest.approx(1089 / 789)
    assert m.paid_bill(bill(), "2023-02", at("2022-12-01"), events) == 1089
    intervals = m.policy_intervals(events, at("2022-12-01"))
    assert [(x.policy_id, x.effective_from, x.effective_to) for x in intervals] == [
        ("credit", "2022-10", "2023-01"), ("poze", "2022-10", None)]


def test_late_expiry_does_not_leak_through_start_interval():
    m = api()
    events = [event(), event(action="expiry", month="2023-01", value=None,
        unit=None, available="2023-01-02")]
    assert m.paid_bill(bill(), "2023-01", at("2023-01-01"), events) == 910
    assert m.paid_bill(bill(), "2023-01", at("2023-01-02"), events) == 1210


def test_product_exposure_uses_normalized_households_and_bill_denominator():
    m = api()
    p = m.ExposurePortfolio((m.Exposure(bill(product_id="fixed"), .75),
        m.Exposure(bill(product_id="variable", commodity=1600), .25)), assumption="Known mix")
    e = event(kind="commodity_multiplier", value=2, unit="factor", products=("variable",))
    r = m.item_relative(p, "2022-09", "2022-10", at("2022-10-31"), [e])
    assert r.estimate == pytest.approx((.75 * 1210 + .25 * 4356) / (.75 * 1210 + .25 * 2420))


def test_cap_applies_to_commodity_before_vat_and_keeps_network_and_fixed():
    m = api()
    cap = event(kind="commodity_cap", value=500, unit="CZK/MWh_ex_VAT")
    assert m.paid_bill(bill(), "2022-10", at("2022-10-31"), [cap]) == pytest.approx(900*1.21)


def test_headline_replaces_embedded_energy_baseline_incrementally():
    m = api()
    r = m.item_relative(portfolio(), "2022-09", "2022-10", at("2022-10-31"), [event()])
    basket = m.BasketWeights({"electricity": .04}, at("2022-01-01"), "published basket")
    base = m.BaselineEnergy("2022-09", "2022-10", {"electricity": 1.02}, "normal energy repricing already embedded")
    result = m.headline_increment({"electricity": r}, basket, base)
    assert result.gross_pp.estimate == pytest.approx(4*(910/1210-1))
    assert result.incremental_pp.estimate == pytest.approx(4*(910/1210-1.02))
    assert result.baseline_pp == pytest.approx(.08)
    with pytest.raises(ValueError, match="baseline"):
        m.headline_increment({"electricity": r}, basket, None)
    with pytest.raises(ValueError, match="published"):
        m.headline_increment({"electricity": r}, replace(basket, available_from=at("2022-11-01")), base)


def test_incomplete_exposures_have_no_fabricated_point_or_implicit_renormalization():
    m = api()
    p = portfolio(shares=(.5,), complete=False)
    r = m.item_relative(p, "2022-09", "2022-10", at("2022-10-31"), [event()])
    assert r.estimate is None and r.lower is None and r.upper is None
    bounds = m.MissingExposureBounds(previous_bill=(1000, 1400), current_bill=(700, 1100),
        assumption="Unobserved households scenario envelope in CZK/month")
    bounded = m.item_relative(p, "2022-09", "2022-10", at("2022-10-31"), [event()], missing=bounds)
    assert bounded.estimate is None
    assert bounded.lower == pytest.approx((.5*910+.5*700)/(.5*1210+.5*1400))
    assert bounded.upper == pytest.approx((.5*910+.5*1100)/(.5*1210+.5*1000))


@pytest.mark.parametrize("changes", [{"quantity_mwh": -1}, {"commodity": -1},
    {"distribution": float("nan")}, {"unit": "CZK/kWh"}, {"assumption": ""},
    {"taxable_components": ("unknown",)}, {"vat_rate": 21}])
def test_bill_rejects_negative_nonfinite_mixed_units_and_missing_assumptions(changes):
    with pytest.raises(ValueError):
        bill(**changes)


@pytest.mark.parametrize("shares", [(1.2,), (-.1, 1.1), (.5,), (float("nan"),)])
def test_invalid_or_unnormalized_exposures_rejected(shares):
    with pytest.raises(ValueError):
        portfolio(shares=shares)


def test_total_credit_allocation_cannot_be_used_as_per_household_money():
    with pytest.raises(ValueError, match="unit"):
        event(value=17400, unit="CZK_million_total_oct_dec")


def test_negative_net_bill_is_rejected_not_clipped():
    m = api()
    with pytest.raises(ValueError, match="positive"):
        m.paid_bill(bill(), "2022-10", at("2022-10-31"), [event(value=2000)])


def test_duplicate_event_and_expiry_without_start_rejected():
    m = api()
    with pytest.raises(ValueError, match="duplicate"):
        m.policy_intervals([event(), event()], at("2022-10-31"))
    with pytest.raises(ValueError, match="start"):
        m.policy_intervals([event(action="expiry", value=None, unit=None)], at("2022-10-31"))


def experiment():
    assert util.find_spec("energy_ledger_experiment") is not None, "declared scenario experiment is missing"
    return import_module("energy_ledger_experiment")


def test_experiment_converts_total_allocation_to_household_month_explicitly():
    inputs = experiment().load_inputs()
    assert inputs["allocation_credit_month"] == pytest.approx(17400e6 / 5363859 / 3)
    assert inputs["source_gaps"] and inputs["evidence_status"] == "scenario_only"


def test_scenario_reports_ineligible_mapping_instead_of_zero_policy_effect():
    rows, manifest = experiment().build_results()
    gated = [r for r in rows if r["group"] == "availability"]
    assert any(r["status"] == "mapping_unavailable" and r["headline_gross_pp"] is None for r in gated)
    assert any(r["scenario"] == "october_after_treatment_publication" and r["headline_gross_pp"] < 0 for r in gated)
    assert manifest["selection_rule"] == "No fitting, outcome scoring, or promotion; scenario diagnostics only."


def test_credit_sensitivity_reverses_only_credit_and_records_rejected_tariff_mapping():
    rows, _ = experiment().build_results()
    group = [r for r in rows if r["group"] == "credit_mapping" and r["status"] == "ok"]
    for r in group:
        assert r["october_item_mm_pct"] < 0 < r["january_item_mm_pct"]
        assert r["january_paid_czk"] < r["september_paid_czk"]
    rejected = [r for r in rows if r["status"] == "rejected_negative_bill"]
    assert rejected and all(r["headline_gross_pp"] is None for r in rejected)
