"""Strict evidence wrapper around the unchanged R9 all-month monetary engine.

Evidence is a reviewed claim about a named input, not automatic source validation.
Callers must verify that each hashed snapshot supports the bound input and clock.
Unavailable effects are None. The caller can explicitly retain its baseline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Mapping, Sequence

from models.energy_ledger import (BaselineEnergy, BasketWeights, ExposurePortfolio,
    PolicyEvent, headline_increment, item_relative, policy_intervals)

VERSION = 'ADMIN_EVENTS_R12'


def _timestamp(value, label):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{label} needs an aware timestamp')


@dataclass(frozen=True)
class Evidence:
    subject: str
    source: str
    snapshot_sha256: str
    available_at: datetime | None
    status: str

    def __post_init__(self):
        if not self.subject.strip() or not self.source.strip():
            raise ValueError('subject and source are required')
        if not re.fullmatch('[a-f0-9]{64}', self.snapshot_sha256):
            raise ValueError('snapshot hash must be SHA-256 hex')
        if self.available_at is not None:
            _timestamp(self.available_at, 'available_at')
        if self.status not in ('verified', 'scenario_only'):
            raise ValueError('unsupported evidence status')


@dataclass(frozen=True)
class Assessment:
    status: str
    gross_pp: float | None = None
    embedded_pp: float | None = None
    incremental_pp: float | None = None
    reasons: tuple[str, ...] = ()
    visible_event_ids: tuple[str, ...] = ()
    weight_interpretation: str = 'Published basket contribution approximation; not exact chain-linked CPI.'


def _visible(events, month, as_of):
    # Filter on publication before reading future economic values or methodology.
    return tuple(e for e in events if e.published_at <= as_of and e.effective_month <= month)


def assess(*, portfolios: Mapping[str, ExposurePortfolio], previous_month: str,
           month: str, as_of: datetime, events: Sequence[PolicyEvent],
           basket: BasketWeights, baseline: BaselineEnergy | None,
           evidence: Mapping[str, Evidence], mode: str = 'replacement',
           counterfactual_events: Sequence[PolicyEvent] = ()) -> Assessment:
    """Return a strict usable increment only when every required input is evidenced.

    replacement: subtract the energy contribution explicitly embedded in headline.
    incremental: subtract a with/without-policy counterfactual computed on exactly
    the same quantities/exposures/weights. The baseline evidence record certifies
    that counterfactual; its numeric BaselineEnergy mapping is not also subtracted.
    """
    _timestamp(as_of, 'as_of')
    if mode not in ('replacement', 'incremental'):
        raise ValueError('mode must be replacement or incremental')
    if not all(re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', x)
               for x in (previous_month, month)):
        raise ValueError('months must be YYYY-MM')
    number = lambda x: int(x[:4])*12 + int(x[5:])
    if number(month)-number(previous_month) != 1:
        raise ValueError('comparison months must be adjacent')
    visible = _visible(events, month, as_of)
    counter = _visible(counterfactual_events, month, as_of) if mode == 'incremental' else ()
    ids = tuple(sorted(e.event_id for e in visible))
    if not any(e.effective_month == month for e in (*visible, *counter)):
        return Assessment('no_visible_transition', visible_event_ids=ids)
    required = {'weights', 'baseline'}
    reasons = []
    if not portfolios:
        reasons.append('missing_portfolios')
    for item, portfolio in portfolios.items():
        if not portfolio.complete:
            reasons.append(f'incomplete_exposure:{item}')
        if any(x.bill.item != item for x in portfolio.exposures):
            raise ValueError('portfolio item mismatch')
        required.add(f'exposure:{item}')
        required.update(f'bill:{item}:{x.bill.product_id}' for x in portfolio.exposures)
    for event in (*visible, *counter):
        required.update((f'event:{event.event_id}:source', f'event:{event.event_id}:methodology'))
        if event.treatment_known_at is None:
            reasons.append(f'unknown_methodology:{event.event_id}')
        elif max(event.available_from, event.treatment_known_at) > as_of:
            reasons.append(f'late_methodology_or_event_input:{event.event_id}')
    for key in sorted(required):
        record = evidence.get(key)
        if record is None:
            reasons.append(f'missing_evidence:{key}')
            continue
        if record.subject != key:
            raise ValueError(f'evidence subject mismatch: {key}')
        if record.available_at is None:
            reasons.append(f'unknown_availability:{key}')
        elif record.available_at > as_of:
            reasons.append(f'late_availability:{key}')
        if record.status != 'verified':
            reasons.append(f'scenario_only:{key}')
    if basket.available_from > as_of:
        reasons.append('late_basket_weights')
    if baseline is None:
        reasons.append('missing_embedded_baseline')
    if reasons:
        return Assessment('mapping_unavailable', reasons=tuple(sorted(set(reasons))), visible_event_ids=ids)
    policy_intervals(visible, as_of)  # Validate links, duplicates and orphan expiry.
    relatives = {i: item_relative(p, previous_month, month, as_of, visible)
                 for i, p in portfolios.items()}
    if mode == 'incremental':
        without = {i: item_relative(p, previous_month, month, as_of, counter)
                   for i, p in portfolios.items()}
        baseline = BaselineEnergy(previous_month, month,
            {i: r.estimate for i, r in without.items()},
            'Evidenced same-bill without-policy counterfactual; seasonal component not subtracted twice.')
    result = headline_increment(relatives, basket, baseline)
    return Assessment('strict_eligible', result.gross_pp.estimate, result.baseline_pp,
                      result.incremental_pp.estimate, visible_event_ids=ids)
