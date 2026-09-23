"""R29: core persistence conditioned on the phase of upstream (producer-price) momentum.

The phase at an origin is read from the last published producer-price month L: momentum m = 100*(log P_L - log P_{L-6});
building if m is above its value six months earlier, fading otherwise. Persistence weights per band and phase are
pooled no-intercept slopes on the R25 panel rows (realised deviation on forecast deviation from each country's norm),
estimated from rows whose labels are published by the Czech origin. The Czech core path is mu + lambda(phase) * (f - mu)
band by band, with a fixed 2%-a-year norm or the own-history norm. See docs/implementation/R29_CORE_PHASE_SPEC_2026-09-18.md.
"""
import numpy as np
import pandas as pd

from models.panel_persistence_r25 import BANDS, estimate_lambda, usable

MODELS = ('CORE_PHASE_TARGET_R29', 'CORE_PHASE_OWN_R29', 'CORE_SINGLE_TARGET_R29')
FIXED_FADING = (.4, .6, .8)
TARGET_LOG_PER_MONTH = 100 * np.log1p(.02) / 12
MOMENTUM_MONTHS = 6


def fixed_name(fading):
    return f'CORE_PHASE_FIXED{int(round(100 * fading)):03d}_R29'


def _local(value):
    t = pd.Timestamp(value)
    return t.tz_convert('Europe/Prague').tz_localize(None) if t.tzinfo else t


def published_levels(levels, published, origin, clock):
    """Index levels strictly before the origin whose publication stamp is at or before the clock."""
    origin = pd.Period(origin, 'M'); clock = _local(clock)
    stamps = pd.Series([_local(v) if pd.notna(v) else pd.NaT for v in published.reindex(levels.index)], index=levels.index)
    mask = (levels.index < origin) & stamps.notna().to_numpy() & (stamps <= clock).to_numpy()
    return levels[mask].dropna()


def phase_from_levels(known, months=MOMENTUM_MONTHS):
    """(phase, diagnostics) from published index levels; None when fewer than 2*months+1 consecutive months end the series."""
    if len(known) < 2 * months + 1:
        return None, dict(status='insufficient_history', n=len(known))
    tail = known.iloc[-(2 * months + 1):]
    if (tail.index[-1] - tail.index[0]).n != 2 * months or (tail <= 0).any():
        return None, dict(status='gap_or_nonpositive_level', n=len(known))
    logs = 100 * np.log(tail.to_numpy(float))
    m_now = float(logs[-1] - logs[-1 - months]); m_before = float(logs[-1 - months] - logs[0])
    phase = 'building' if m_now - m_before > 0 else 'fading'
    return phase, dict(status='estimated', last_month=str(tail.index[-1]), momentum=m_now, momentum_before=m_before, change=m_now - m_before, phase=phase)


def phase_at(levels, published, origin, clock):
    return phase_from_levels(published_levels(levels, published, origin, clock))


def lambda_phase_at(rows, band, t, phase, minimum):
    """Pooled slope on panel rows of the given phase whose labels are published by t; 1.0 fallback when too few rows."""
    z = usable(rows, band, t); z = z[z.phase.eq(phase)]
    if len(z) < minimum:
        return dict(lam=1., n=len(z), status='fallback_too_few_rows')
    lam = estimate_lambda(z.f - z.mu, z.r - z.mu)
    return dict(lam=lam, n=len(z), status='estimated') if np.isfinite(lam) else dict(lam=1., n=len(z), status='fallback_no_variation')


def band_corrections(f_cz, mu, lam):
    """Move each band mean from f to mu + lam * (f - mu): the correction added to the FAST log rates, per band."""
    return (np.asarray(lam, float) - 1.) * (np.asarray(f_cz, float) - float(mu))
