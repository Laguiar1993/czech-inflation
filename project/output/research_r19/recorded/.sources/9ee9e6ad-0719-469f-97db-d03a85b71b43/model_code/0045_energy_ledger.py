"""ENERGY_LEDGER_R9: monetary household-bill scenario challenger, never fitted.

All quantities are fixed MWh/month, rates CZK/MWh ex VAT and fixed amounts
CZK/month. Household shares aggregate expenditure levels before taking ratios.
See docs/implementation/ENERGY_LEDGER.md for interpretation and limitations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isclose, isfinite
import re
from typing import Mapping, Sequence


VERSION = "ENERGY_LEDGER_R9"
COMPONENTS = ("commodity", "distribution", "fixed", "levy")
UNITS = {"credit": "CZK/month", "vat_rate": "fraction", "levy_waiver": "fraction",
         "commodity_cap": "CZK/MWh_ex_VAT", "commodity_multiplier": "factor",
         "distribution_multiplier": "factor"}


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be explicit and nonempty")


def _number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")


def _time(value, name):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} requires an explicit timezone and timestamp")


def _month(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("month must be YYYY-MM")


@dataclass(frozen=True)
class Bill:
    product_id: str
    item: str
    quantity_mwh: float
    commodity: float
    distribution: float
    fixed: float
    levy: float
    vat_rate: float
    taxable_components: tuple[str, ...]
    assumption: str
    unit: str = "CZK/MWh_ex_VAT;fixed=CZK/month;quantity=MWh/month"

    def __post_init__(self):
        for name in ("product_id", "item", "assumption"):
            _text(getattr(self, name), name)
        for name in (*COMPONENTS, "quantity_mwh", "vat_rate"):
            _number(getattr(self, name), name, positive=name == "quantity_mwh")
        if self.vat_rate > 1:
            raise ValueError("vat_rate uses fractional units, not percent")
        if self.unit != "CZK/MWh_ex_VAT;fixed=CZK/month;quantity=MWh/month":
            raise ValueError("bill unit is incompatible; convert explicitly before entry")
        if (len(set(self.taxable_components)) != len(self.taxable_components)
                or not set(self.taxable_components) <= set(COMPONENTS)):
            raise ValueError("invalid taxable_components")


@dataclass(frozen=True)
class PolicyEvent:
    event_id: str
    policy_id: str
    action: str
    effective_month: str
    item: str
    products: tuple[str, ...]
    kind: str
    value: float | None
    unit: str | None
    published_at: datetime
    treatment_known_at: datetime | None
    available_from: datetime
    source: str
    assumption: str

    def __post_init__(self):
        for name in ("event_id", "policy_id", "item", "source", "assumption"):
            _text(getattr(self, name), name)
        _month(self.effective_month)
        for name in ("published_at", "available_from"):
            _time(getattr(self, name), name)
        if self.treatment_known_at is not None:
            _time(self.treatment_known_at, "treatment_known_at")
        if (self.available_from < self.published_at or (self.treatment_known_at is not None
                and self.available_from < self.treatment_known_at)):
            raise ValueError("available_from cannot precede publication or treatment knowledge")
        if self.action not in ("start", "expiry") or self.kind not in UNITS:
            raise ValueError("unsupported policy action/kind")
        if len(set(self.products)) != len(self.products) or any(not p for p in self.products):
            raise ValueError("invalid product targets")
        if self.action == "expiry":
            if self.value is not None or self.unit is not None:
                raise ValueError("expiry removes a policy; value and unit must be None")
        else:
            if self.unit != UNITS[self.kind]:
                raise ValueError(f"unit must be {UNITS[self.kind]} for {self.kind}")
            _number(self.value, "event value", positive=self.kind.endswith("multiplier"))
            if self.kind in ("vat_rate", "levy_waiver") and self.value > 1:
                raise ValueError("fraction must be within [0, 1]")


@dataclass(frozen=True)
class PolicyInterval:
    policy_id: str
    effective_from: str
    effective_to: str | None
    start: PolicyEvent
    expiry: PolicyEvent | None


def policy_intervals(events: Sequence[PolicyEvent], as_of: datetime) -> tuple[PolicyInterval, ...]:
    """Visible [start, expiry) intervals; an unpublished expiry never leaks in."""
    _time(as_of, "as_of")
    if len({e.event_id for e in events}) != len(events):
        raise ValueError("duplicate event_id")
    known = [e for e in events if e.treatment_known_at is not None
             and max(e.published_at, e.treatment_known_at, e.available_from) <= as_of]
    grouped = {}
    for e in known:
        grouped.setdefault(e.policy_id, []).append(e)
    result = []
    for policy, group in sorted(grouped.items()):
        starts = [e for e in group if e.action == "start"]
        ends = [e for e in group if e.action == "expiry"]
        if len(starts) != 1 or len(ends) > 1:
            raise ValueError(f"policy {policy} needs one visible start and at most one expiry")
        start = starts[0]
        end = ends[0] if ends else None
        if end and (end.effective_month <= start.effective_month or
                    (end.item, end.products, end.kind) != (start.item, start.products, start.kind)):
            raise ValueError("expiry must follow and match its start")
        result.append(PolicyInterval(policy, start.effective_month,
                                     end.effective_month if end else None, start, end))
    return tuple(result)


def paid_bill(bill: Bill, month: str, as_of: datetime,
              events: Sequence[PolicyEvent]) -> float:
    """Price one constant-quantity bill in CZK/month; no clipping of net prices."""
    _month(month)
    active = [i.start for i in policy_intervals(events, as_of)
              if i.effective_from <= month and (i.effective_to is None or month < i.effective_to)
              and i.start.item == bill.item
              and (not i.start.products or bill.product_id in i.start.products)]
    commodity, distribution, levy, vat = bill.commodity, bill.distribution, bill.levy, bill.vat_rate
    credits = 0.0
    caps = []
    vat_events = [e for e in active if e.kind == "vat_rate"]
    if len(vat_events) > 1:
        raise ValueError("overlapping VAT overrides need an explicit resolution")
    for e in active:
        if e.kind == "commodity_multiplier":
            commodity *= e.value
        elif e.kind == "distribution_multiplier":
            distribution *= e.value
        elif e.kind == "commodity_cap":
            caps.append(e.value)
        elif e.kind == "levy_waiver":
            levy *= 1 - e.value
        elif e.kind == "vat_rate":
            vat = e.value
        elif e.kind == "credit":
            credits += e.value
    if caps:
        commodity = min(commodity, *caps)
    charges = {"commodity": commodity * bill.quantity_mwh,
               "distribution": distribution * bill.quantity_mwh,
               "fixed": bill.fixed, "levy": levy * bill.quantity_mwh}
    net = sum(charges.values()) + vat * sum(charges[c] for c in bill.taxable_components) - credits
    _number(net, "paid bill", positive=True)
    return net


@dataclass(frozen=True)
class Exposure:
    bill: Bill
    household_share: float

    def __post_init__(self):
        _number(self.household_share, "household_share", positive=True)
        if self.household_share > 1:
            raise ValueError("household_share must be <= 1")


@dataclass(frozen=True)
class ExposurePortfolio:
    exposures: tuple[Exposure, ...]
    assumption: str
    complete: bool = True

    def __post_init__(self):
        _text(self.assumption, "exposure assumption")
        if not self.exposures or len({e.bill.item for e in self.exposures}) != 1:
            raise ValueError("portfolio needs exposures for exactly one item")
        if len({e.bill.product_id for e in self.exposures}) != len(self.exposures):
            raise ValueError("duplicate product exposure")
        total = sum(e.household_share for e in self.exposures)
        if total > 1 + 1e-10 or (self.complete and not isclose(total, 1, abs_tol=1e-10)):
            raise ValueError("household exposures must normalize to 1; declare incomplete coverage")
        if not self.complete and total >= 1:
            raise ValueError("incomplete coverage must leave missing household mass")


@dataclass(frozen=True)
class MissingExposureBounds:
    previous_bill: tuple[float, float]
    current_bill: tuple[float, float]
    assumption: str

    def __post_init__(self):
        _text(self.assumption, "missing exposure assumption")
        for bounds in (self.previous_bill, self.current_bill):
            if len(bounds) != 2:
                raise ValueError("bill bounds require lower and upper CZK/month")
            for value in bounds:
                _number(value, "missing bill bound", positive=True)
            if bounds[0] > bounds[1]:
                raise ValueError("bill bounds are reversed")


@dataclass(frozen=True)
class Estimate:
    estimate: float | None
    lower: float | None
    upper: float | None


@dataclass(frozen=True)
class ItemRelative(Estimate):
    item: str
    previous_month: str
    month: str
    as_of: datetime
    coverage: float
    assumption: str


def item_relative(portfolio: ExposurePortfolio, previous_month: str, month: str,
                  as_of: datetime, events: Sequence[PolicyEvent], *,
                  missing: MissingExposureBounds | None = None) -> ItemRelative:
    """Ratio of weighted constant-quantity bills, with conservative missing-mass bounds."""
    _month(previous_month)
    _month(month)
    if previous_month >= month:
        raise ValueError("previous_month must precede month")
    previous = sum(e.household_share * paid_bill(e.bill, previous_month, as_of, events)
                   for e in portfolio.exposures)
    current = sum(e.household_share * paid_bill(e.bill, month, as_of, events)
                  for e in portfolio.exposures)
    coverage = sum(e.household_share for e in portfolio.exposures)
    assumption = portfolio.assumption
    if portfolio.complete:
        point = low = high = current / previous
    elif missing is None:
        point = low = high = None
    else:
        point = None
        low = (current + (1-coverage)*missing.current_bill[0]) / (previous + (1-coverage)*missing.previous_bill[1])
        high = (current + (1-coverage)*missing.current_bill[1]) / (previous + (1-coverage)*missing.previous_bill[0])
        assumption += "; " + missing.assumption
    return ItemRelative(point, low, high, portfolio.exposures[0].bill.item,
                        previous_month, month, as_of, coverage, assumption)


@dataclass(frozen=True)
class BasketWeights:
    shares: Mapping[str, float]
    available_from: datetime
    source: str

    def __post_init__(self):
        _text(self.source, "published basket source")
        _time(self.available_from, "basket available_from")
        if not self.shares:
            raise ValueError("basket must include item weights")
        for value in self.shares.values():
            _number(value, "published basket share")
        if sum(self.shares.values()) > 1:
            raise ValueError("published basket weights use fractions, not per mille")


@dataclass(frozen=True)
class BaselineEnergy:
    previous_month: str
    month: str
    item_relatives: Mapping[str, float]
    assumption: str

    def __post_init__(self):
        _text(self.assumption, "baseline assumption")
        _month(self.previous_month)
        _month(self.month)
        for value in self.item_relatives.values():
            _number(value, "baseline item relative", positive=True)


@dataclass(frozen=True)
class HeadlineContribution:
    gross_pp: Estimate
    baseline_pp: float
    incremental_pp: Estimate


def headline_increment(relatives: Mapping[str, ItemRelative], basket: BasketWeights,
                       baseline: BaselineEnergy) -> HeadlineContribution:
    """Published-weight contribution approximation minus embedded baseline energy.

    Returns percentage points. It is not the exact chain-linked official CPI
    contribution, which would require the official aggregation price-update weights.
    """
    if not isinstance(baseline, BaselineEnergy):
        raise ValueError("an explicit baseline energy mapping is required")
    if not relatives or set(relatives) != set(baseline.item_relatives):
        raise ValueError("baseline and scenario must cover exactly the same items")
    clocks = {r.as_of for r in relatives.values()}
    if len(clocks) != 1 or basket.available_from > next(iter(clocks)):
        raise ValueError("use one cutoff and basket weights published by that cutoff")
    for item, r in relatives.items():
        if item != r.item or item not in basket.shares:
            raise ValueError("item relative is missing a matching published basket weight")
        if (r.previous_month, r.month) != (baseline.previous_month, baseline.month):
            raise ValueError("baseline and scenario months must match")
    embedded = sum(basket.shares[k]*100*(v-1) for k, v in baseline.item_relatives.items())
    values = []
    for field in ("estimate", "lower", "upper"):
        values.append(None if any(getattr(r, field) is None for r in relatives.values()) else
                      sum(basket.shares[k]*100*(getattr(r, field)-1) for k, r in relatives.items()))
    gross = Estimate(*values)
    incremental = Estimate(*(None if v is None else v-embedded for v in values))
    return HeadlineContribution(gross, embedded, incremental)
