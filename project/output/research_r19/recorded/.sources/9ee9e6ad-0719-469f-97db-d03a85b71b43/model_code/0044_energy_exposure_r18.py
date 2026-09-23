"""Explicit cohort bill scenarios and evidence gates; never a national CPI forecast.

Counts weight fixed-quantity bills, not price relatives. Intervals are conservative
marginal bounds conditional on declared inputs, not statistical confidence bands.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from math import isclose, isfinite
import re
from typing import Mapping, Sequence

from models.energy_ledger import Bill, PolicyEvent, paid_bill


NATIONAL_FIELDS = ('cohort_shares', 'reset_schedule', 'fixed_quantities',
                   'tariff_components', 'cpi_mapping', 'item_weights', 'baseline_energy')


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('explicit timezone-aware availability timestamp required')


def _number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f'{name} must be finite')
    if value < 0 or (positive and value == 0):
        raise ValueError(f'{name} must be positive' if positive else f'{name} must be nonnegative')


def _month(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value):
        raise ValueError('month must be YYYY-MM')


def eru_reporting_period(value: str) -> tuple[str, str]:
    """ERU manual pp. 3/13: YYYY-01/02 encodes semesters, not months."""
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-0[12]', value):
        raise ValueError('ERU reporting period requires YYYY-01 or YYYY-02')
    year = value[:4]
    return (year + '-01', year + '-06') if value.endswith('01') else (year + '-07', year + '-12')


@dataclass(frozen=True)
class Evidence:
    source_id: str
    status: str
    available_from: datetime | None
    reference_period: str
    population: str
    comparable: bool
    archived_vintage: bool

    def __post_init__(self):
        if self.status not in ('observed', 'assumption', 'unavailable'):
            raise ValueError('evidence status must separate observations and assumptions')
        if not all(isinstance(v, str) and v.strip() for v in
                   (self.source_id, self.reference_period, self.population)):
            raise ValueError('explicit source, period and population required')
        if self.available_from is not None:
            _time(self.available_from)
        if type(self.comparable) is not bool or type(self.archived_vintage) is not bool:
            raise ValueError('comparability and archived vintage must be explicit booleans')


@dataclass(frozen=True)
class Gate:
    eligible: bool
    reasons: tuple[str, ...]


def national_gate(evidence: Mapping[str, Evidence], as_of: datetime, *,
                  historical: bool = True, aggregate_credit: bool = False) -> Gate:
    """Missing, current/revised or assumed evidence cannot certify a national path."""
    _time(as_of)
    fields = NATIONAL_FIELDS + (('credit_denominator',) if aggregate_credit else ())
    reasons = []
    for key in fields:
        e = evidence.get(key)
        if e is None:
            reasons.append(key + ':missing')
            continue
        reasons.extend(_evidence_reasons(key, e, as_of, historical))
    return Gate(not reasons, tuple(reasons))


def _evidence_reasons(key, evidence, as_of, historical):
    reasons = []
    if evidence.status != 'observed':
        reasons.append(key + ':' + evidence.status)
    if evidence.available_from is None or evidence.available_from > as_of:
        reasons.append(key + ':unavailable_at_cutoff')
    if not evidence.comparable:
        reasons.append(key + ':population_or_measure_not_comparable')
    if historical and not evidence.archived_vintage:
        reasons.append(key + ':unarchived_vintage')
    return reasons


@dataclass(frozen=True)
class Cohort:
    cohort_id: str
    household_mass: float
    base_bill: Bill
    new_commodity: float
    reset_window: tuple[str, str] | None
    available_from: datetime
    exposure_status: str
    assumption: str
    regulated_includes_poze: bool = False

    def __post_init__(self):
        _number(self.household_mass, 'household mass', positive=True)
        if self.household_mass > 1:
            raise ValueError('household mass cannot exceed one')
        _number(self.new_commodity, 'replacement commodity')
        _time(self.available_from)
        if self.exposure_status not in ('observed', 'assumption'):
            raise ValueError('cohort exposure must be observed or an explicit assumption')
        if not self.cohort_id or not self.assumption:
            raise ValueError('cohort ID and assumption/source explanation required')
        if self.reset_window is not None:
            if len(self.reset_window) != 2:
                raise ValueError('reset window needs earliest and latest month')
            for month in self.reset_window:
                _month(month)
            if self.reset_window[0] > self.reset_window[1]:
                raise ValueError('reset window is reversed')


@dataclass(frozen=True)
class MissingBills:
    previous: tuple[float, float]
    current: tuple[float, float]
    assumption: str

    def __post_init__(self):
        if not self.assumption:
            raise ValueError('explicit missing household bill assumption required')
        for bounds in (self.previous, self.current):
            if len(bounds) != 2:
                raise ValueError('missing household bounds need low/high bills')
            for value in bounds:
                _number(value, 'missing household bill', positive=True)
            if bounds[0] > bounds[1]:
                raise ValueError('missing household bill bounds reversed')


@dataclass(frozen=True)
class CohortRelative:
    item: str
    previous_month: str
    month: str
    conditional_point: float | None
    lower: float | None
    upper: float | None
    modeled_mass: float
    observed_mass: float
    status: str
    national_point: None = None


def _bill_bounds(cohort, month, as_of, events):
    early, late = cohort.reset_window
    prices = ([cohort.base_bill.commodity] if month < early else
              [cohort.new_commodity] if month >= late else
              [cohort.base_bill.commodity, cohort.new_commodity])
    bills = [paid_bill(replace(cohort.base_bill, commodity=p), month, as_of, events) for p in prices]
    return min(bills), max(bills)


def cohort_relative(cohorts: Sequence[Cohort], previous_month: str, month: str,
                    as_of: datetime, events: Sequence[PolicyEvent] = (), *,
                    missing: MissingBills | None = None) -> CohortRelative:
    _month(previous_month)
    _month(month)
    _time(as_of)
    if previous_month >= month:
        raise ValueError('base month must precede target month')
    if not cohorts or len({c.base_bill.item for c in cohorts}) != 1:
        raise ValueError('cohorts must cover exactly one item')
    if (len({c.cohort_id for c in cohorts}) != len(cohorts) or
            len({c.base_bill.product_id for c in cohorts}) != len(cohorts)):
        raise ValueError('cohort IDs and products must be unique')
    mass = sum(c.household_mass for c in cohorts)
    if mass > 1 + 1e-10:
        raise ValueError('household mass cannot exceed one')
    mass = min(mass, 1.)
    observed = sum(c.household_mass for c in cohorts if c.exposure_status == 'observed')
    item = cohorts[0].base_bill.item

    def result(point=None, lower=None, upper=None, status='unavailable'):
        return CohortRelative(item, previous_month, month, point, lower, upper, mass, observed, status)

    for c in cohorts:
        if c.regulated_includes_poze and (c.base_bill.levy != 0 or any(
                e.kind == 'levy_waiver' and e.item == item and
                (not e.products or c.base_bill.product_id in e.products) for e in events)):
            raise ValueError('POZE already included in supplied regulated bill')
    relevant = [e for e in events if e.item == item and e.effective_month <= month
                and e.published_at <= as_of and
                (not e.products or any(c.base_bill.product_id in e.products for c in cohorts))]
    if any(e.kind == 'credit' for e in relevant):
        raise ValueError('saving credits require comparable aggregate expenditure accounting')
    if any(e.treatment_known_at is None or e.treatment_known_at > as_of or e.available_from > as_of
           for e in relevant):
        return result(status='unavailable_CPI_treatment')
    if any(c.available_from > as_of for c in cohorts):
        return result(status='unavailable_input_at_cutoff')
    if any(c.reset_window is None for c in cohorts):
        return result(status='unavailable_reset_timing')
    if mass < 1 - 1e-10 and missing is None:
        return result(status='unavailable_missing_household_mass')
    previous = [0., 0.]
    current = [0., 0.]
    for c in cohorts:
        for aggregate, target in ((previous, previous_month), (current, month)):
            bounds = _bill_bounds(c, target, as_of, events)
            for side in (0, 1):
                aggregate[side] += c.household_mass * bounds[side]
    if mass < 1 - 1e-10:
        for side in (0, 1):
            previous[side] += (1 - mass) * missing.previous[side]
            current[side] += (1 - mass) * missing.current[side]
    lower, upper = current[0] / previous[1], current[1] / previous[0]
    point = lower if mass >= 1 - 1e-10 and isclose(lower, upper, abs_tol=1e-12) else None
    status = 'conditional_complete_assumed_or_observed_portfolio' if point is not None else 'conditional_bounds'
    return result(point, lower, upper, status)


def aggregate_credit_relative(previous_expenditure, current_expenditure,
                              previous_credit, current_credit, denominator_evidence,
                              as_of, *, historical=True):
    """One aggregate subtraction each month from comparable pre-credit expenditure."""
    _time(as_of)
    if denominator_evidence is None or _evidence_reasons(
            'denominator', denominator_evidence, as_of, historical):
        raise ValueError('observed comparable expenditure denominator required')
    for value in (previous_expenditure, current_expenditure):
        _number(value, 'pre-credit expenditure', positive=True)
    for value in (previous_credit, current_credit):
        _number(value, 'credit')
    if previous_credit >= previous_expenditure or current_credit >= current_expenditure:
        raise ValueError('aggregate net expenditure must be positive; no clipping')
    return (current_expenditure - current_credit) / (previous_expenditure - previous_credit)


def replace_baseline_contribution(scenario_relative, baseline_relative, item_weight,
                                  baseline_evidence, as_of, *, historical=True,
                                  scenario_scope=None, baseline_scope=None):
    """Same-item/period published-weight approximation; no automatic forecast mutation.

    Scope is (item, previous_month, target_month). Evidence must establish the
    comparable baseline; matching scope alone never substitutes for evidence.
    """
    _time(as_of)
    if baseline_relative is None or baseline_evidence is None or _evidence_reasons(
            'baseline', baseline_evidence, as_of, historical):
        raise ValueError('identified baseline energy mapping required')
    if scenario_scope is None or baseline_scope is None or scenario_scope != baseline_scope:
        raise ValueError('baseline and scenario scope must match explicitly')
    if len(scenario_scope) != 3 or not scenario_scope[0]:
        raise ValueError('scope needs item, previous month and target month')
    _month(scenario_scope[1])
    _month(scenario_scope[2])
    if scenario_scope[1] >= scenario_scope[2]:
        raise ValueError('scope months must be ordered')
    for value in (scenario_relative, baseline_relative):
        _number(value, 'relative', positive=True)
    _number(item_weight, 'item weight')
    if item_weight > 1:
        raise ValueError('item weight must use fractions')
    return 100 * item_weight * (scenario_relative - baseline_relative)
