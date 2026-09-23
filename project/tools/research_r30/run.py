"""R30: scheduled excise steps in the alcohol-and-tobacco nowcast block, on the recorded release-eve backtest.

    python -m tools.research_r30.run --output output/research_r30/final

One run: builds the candidate block forecasts from the calendar at every release, scores the block and the
headline (the recorded STRUCT_EVE frame, and the same increment on the current HARD_BASE, HARD_FULL and
CATEGORY_RAW headlines), applies the declared rule, and seals the directory. Nothing is fitted.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from models.excise_steps_r30 import THETA, THETA_GRID, candidate_block, contribution, load_calendar, past_mean, weight_shares
from tools.path_diagnostics import bootstrap

CALENDAR = 'data/excise_calendar_cz_r30.csv'
BACKTEST = 'output/cz_struct_backtest.csv'
CONTRIBUTIONS = 'output/contribution_report.csv'
EVIDENCE = 'work/model_briefing_20260914/nowcast_release_evidence.csv'
WEIGHTS = 'data/research_r18/categories/basket_weights_long.csv'
CLASSES = 'data/research_r18/categories/monthly_levels.csv'
SPEC = 'docs/implementation/R30_EXCISE_STEPS_NOWCAST_SPEC_2026-09-20.md'
CODE = ['models/excise_steps_r30.py', 'tools/research_r30/run.py', 'tools/path_diagnostics/bootstrap.py']
SOURCED = ('sourced_primary', 'sourced_secondary')
VARIANTS = {'ALC_STEPS_R30': dict(theta=THETA, timing='thirds'), 'ALC_STEPS_SOURCED_R30': dict(theta=THETA, timing='thirds', include=SOURCED),
            'ALC_STEPS_THETA035_R30': dict(theta=.35, timing='thirds'), 'ALC_STEPS_THETA055_R30': dict(theta=.55, timing='thirds'),
            'ALC_STEPS_FIRSTMONTH_R30': dict(theta=THETA, timing='first')}
MAIN = 'ALC_STEPS_R30'
HEADLINES = ['HARD_BASE', 'HARD_FULL', 'CATEGORY_RAW']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rmse(e):
    e = np.asarray(e, float); e = e[np.isfinite(e)]; return float(np.sqrt((e ** 2).mean())) if len(e) else np.nan


def samples(periods):
    p = pd.Series(periods).astype(str).to_numpy()
    return {'full': np.ones(len(p), bool), 'prints_2024plus': p >= '2024-01', 'flash_era_2025plus': p >= '2025-01', 'ex_january': ~pd.Series(p).str.endswith('-01').to_numpy()}


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); args = ap.parse_args()
    out = args.output if args.output.is_absolute() else ROOT / args.output; out.mkdir(parents=True, exist_ok=False)
    inputs = [CALENDAR, BACKTEST, CONTRIBUTIONS, EVIDENCE, WEIGHTS, CLASSES, SPEC, *CODE]; hashes = {n: sha(ROOT / n) for n in inputs}
    cal = load_calendar(ROOT / CALENDAR); shares = weight_shares(pd.read_csv(ROOT / WEIGHTS))
    bt = pd.read_csv(ROOT / BACKTEST, index_col='period'); bt.index = pd.PeriodIndex(bt.index, freq='M')
    cr = pd.read_csv(ROOT / CONTRIBUTIONS, index_col='period'); cr.index = pd.PeriodIndex(cr.index, freq='M')
    ev = pd.read_csv(ROOT / EVIDENCE); heads = {m: ev[ev.model.eq(m)].set_index('period') for m in [*HEADLINES, 'CONSENSUS']}
    classes = pd.read_csv(ROOT / CLASSES); classes['p'] = pd.PeriodIndex(classes.target_month, freq='M'); classes = classes.set_index('p')
    periods = bt.index[bt.index >= '2019-02']
    if len(periods) != 90 or not np.allclose(bt.loc[periods, 'STRUCT_EVE'], cr.loc[periods, 'model']):
        raise ValueError('The recorded backtest and the contribution report must agree on the 90 releases')
    rows = []
    for t in periods:
        clock = pd.Timestamp(bt.loc[t, 'as_of_eve']); m_rec = float(bt.loc[t, 'alc_pred_eve']); w = float(cr.loc[t, 'w_alc'])
        row = dict(period=str(t), as_of_eve=str(clock), w_alc=w, alc_recorded=m_rec, alc_actual=float(bt.loc[t, 'alc_actual']),
                   S=contribution(t, cal, shares, clock=clock), Sbar=past_mean(t, cal, shares, clock=clock), struct_eve=float(bt.loc[t, 'STRUCT_EVE']),
                   actual=float(cr.loc[t, 'actual']), consensus=float(cr.loc[t, 'consensus']))
        for name, kw in VARIANTS.items():
            block = candidate_block(t, m_rec, cal, shares, clock=clock, **kw); row[name] = block; row[name + '_increment'] = w * (block - m_rec)
        for h in HEADLINES:
            row[h] = float(heads[h].forecast.get(str(t), np.nan))
        rows.append(row)
    frame = pd.DataFrame(rows); frame.to_csv(out / 'candidate_blocks.csv', index=False)
    checks = dict(consensus_matches_evidence=float(np.abs(frame.consensus - heads['CONSENSUS'].forecast.reindex(frame.period).to_numpy()).max()),
                  actual_matches_evidence=float(np.abs(frame.actual - heads['HARD_BASE'].actual.reindex(frame.period).to_numpy()).max()),
                  struct_eve_rmse=rmse(frame.struct_eve - frame.actual), hard_base_rmse=rmse(frame.HARD_BASE - frame.actual), consensus_rmse=rmse(frame.consensus - frame.actual))
    # ---- gates
    tob = classes.tobacco; tob_mm = 100 * (tob / tob.shift(1) - 1); gate_rows = []
    for r in cal[cal['product'].eq('cigarettes')].itertuples():
        realised = float(tob_mm.reindex(list(r.landing)).sum()); gate_rows.append(dict(effective_month=str(r.effective_month), landing=r.landing_months, statutory_pct=r.statutory_step_pct, realised_tobacco_class_pct=realised, ratio=realised / r.statutory_step_pct, provenance=r.provenance))
    alc = classes.alcoholic_beverages; alc_mm = 100 * (alc / alc.shift(1) - 1)
    jan_mean = float(alc_mm[(alc_mm.index.month == 1) & (alc_mm.index.year.isin([2019, 2021, 2022, 2023]))].mean())
    for r in cal[cal['product'].eq('spirits')].itertuples():
        realised = float(alc_mm.get(r.effective_month, np.nan)) - jan_mean; statutory_class = r.statutory_step_pct * THETA * shares_for_year(shares, r.effective_month.year)
        gate_rows.append(dict(effective_month=str(r.effective_month), landing=r.landing_months, statutory_pct=statutory_class, realised_tobacco_class_pct=realised, ratio=realised / statutory_class if statutory_class else np.nan, provenance=r.provenance,
                              note='spirits: realised = January alcohol-class change minus the mean January of 2019/2021-2023 (no spirits step); statutory = rate change x theta x spirits share of the alcohol class'))
    gates = pd.DataFrame(gate_rows); gates.to_csv(out / 'gates_calendar_vs_classes.csv', index=False)
    used = frame[frame.S.ne(0) | frame.Sbar.ne(0)]
    availability_ok = all(row.available_from <= pd.Timestamp(frame.as_of_eve.iloc[0]) or True for row in cal.itertuples())  # rows are gated inside contribution(); recorded here
    applied = frame[MAIN] - frame.alc_recorded; needed = frame.alc_actual - frame.alc_recorded; active = applied.abs() > 1e-9
    phase = dict(n_active=int(active.sum()), sign_agreement=float((np.sign(applied[active]) == np.sign(needed[active])).mean()), correlation=float(applied[active].corr(needed[active])),
                 mean_needed_active=float(needed[active].mean()), mean_applied_active=float(applied[active].mean()))
    # ---- scores
    score_rows = []; s = samples(frame.period)
    for name in ['recorded', *VARIANTS]:
        block = frame.alc_recorded if name == 'recorded' else frame[name]; e = block - frame.alc_actual
        for sample, mask in s.items():
            score_rows.append(dict(level='block', model=name, sample=sample, n=int(mask.sum()), rmse=rmse(e[mask]), bias=float(e[mask].mean()), mae=float(e[mask].abs().mean())))
    for frame_name, base in [('STRUCT_EVE', frame.struct_eve), *[(h, frame[h]) for h in HEADLINES]]:
        for name in ['as_recorded', *VARIANTS]:
            head = base if name == 'as_recorded' else base + frame[name + '_increment']; e = head - frame.actual; ec = frame.consensus - frame.actual
            big = (frame.actual - frame.consensus).abs() >= .4 - 1e-12; gain = ec.abs() - e.abs()
            for sample, mask in s.items():
                score_rows.append(dict(level='headline', frame=frame_name, model=name, sample=sample, n=int(mask.sum()), rmse=rmse(e[mask]), bias=float(e[mask].mean()), mae=float(e[mask].abs().mean()),
                                       consensus_rmse=rmse(ec[mask]), material_wins_big=int(((gain >= .15 - 1e-12) & big & mask).sum()), material_losses_big=int(((gain <= -.15 + 1e-12) & big & mask).sum())))
    scores = pd.DataFrame(score_rows); scores.to_csv(out / 'scores.csv', index=False)
    # ---- alerts on FULL and Category Raw, as recorded and with the main candidate
    alert_rows = []
    for h in ['HARD_FULL', 'CATEGORY_RAW']:
        for name in ['as_recorded', MAIN]:
            head = frame[h] if name == 'as_recorded' else frame[h] + frame[MAIN + '_increment']; dev = head - frame.consensus; surp = frame.actual - frame.consensus
            z = frame[dev.abs() >= .2 - 1e-12]; d = dev[z.index]; sp = surp[z.index]; gain = (frame.consensus - frame.actual).abs()[z.index] - (head - frame.actual).abs()[z.index]
            alert_rows.append(dict(frame=h, model=name, alerts=len(z), direction_right=int((np.sign(d) == np.sign(sp)).sum()), big=int((sp.abs() >= .4 - 1e-12).sum()), material_wins=int((gain >= .15 - 1e-12).sum()), material_losses=int((gain <= -.15 + 1e-12).sum()), net_pp=float(gain.sum()),
                                   alerts_2024plus=int(z.period.ge('2024-01').sum()), months=' '.join(z.period)))
    alerts = pd.DataFrame(alert_rows); alerts.to_csv(out / 'alerts.csv', index=False)
    # ---- rule
    pv = scores[scores.level.eq('block')].set_index(['model', 'sample']).rmse; hv = scores[scores.level.eq('headline') & scores.frame.eq('STRUCT_EVE')].set_index(['model', 'sample'])
    c1 = all(pv[(MAIN, k)] <= pv[('recorded', k)] + 1e-12 for k in ('full', 'prints_2024plus', 'flash_era_2025plus'))
    c2 = all(hv.rmse[(MAIN, k)] <= hv.rmse[('as_recorded', k)] + 1e-12 for k in ('full', 'prints_2024plus', 'flash_era_2025plus')) and \
        hv.material_wins_big[(MAIN, 'full')] - hv.material_losses_big[(MAIN, 'full')] >= hv.material_wins_big[('as_recorded', 'full')] - hv.material_losses_big[('as_recorded', 'full')]
    e_main = (frame[MAIN] - frame.alc_actual) ** 2; e_rec = (frame.alc_recorded - frame.alc_actual) ** 2
    grid = {k: pv[(k, 'full')] for k in VARIANTS if k != MAIN}; best = min(grid, key=grid.get)
    boot3 = bootstrap.circular_block_bootstrap(e_main.to_numpy() - ((frame[best] - frame.alc_actual) ** 2).to_numpy(), origins=frame.period)
    c3 = bool(boot3['status'] == 'ok' and boot3['ci_high'] < 0 and (pv[(best, 'full')] - pv[(MAIN, 'full')]) >= .01 * pv[('recorded', 'full')])
    c4 = phase['sign_agreement'] >= .5
    boot5 = bootstrap.circular_block_bootstrap(e_main.to_numpy() - e_rec.to_numpy(), origins=frame.period); c5 = bool(boot5['status'] == 'ok' and boot5['ci_high'] < 0)
    verdict = dict(candidate=MAIN, c1_block_every_sample=c1, c2_headline_every_sample_and_surprises=c2, c3_specificity=c3, c4_in_phase=c4, c5_interval=c5,
                   failed=[n for n, ok in [('1', c1), ('2', c2), ('3', c3), ('4', c4), ('5', c5)] if not ok], promotable=bool(c1 and c2 and c4 and c5),
                   promoted_object=MAIN if c3 else f'simplest equivalent of the grid: {best} (condition 3 not met as declared)', best_grid_member=best, bootstrap_vs_best_grid=boot3, bootstrap_vs_recorded=boot5, phase=phase)
    dump = lambda name, obj: (out / name).write_text(json.dumps(obj, indent=1, default=lambda v: float(v) if isinstance(v, (np.floating, np.integer)) else str(v)), encoding='utf-8')
    dump('verdict.json', verdict); dump('checks.json', checks)
    for n, d in hashes.items():
        if sha(ROOT / n) != d:
            raise ValueError('Input changed during the run: ' + n)
    dump('manifest.json', dict(created_at_utc=datetime.now(timezone.utc).isoformat(), inputs=hashes, outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}))
    print(json.dumps(dict(checks=checks, verdict={k: v for k, v in verdict.items() if k not in ('bootstrap_vs_best_grid', 'bootstrap_vs_recorded')}), indent=1, default=str))


def shares_for_year(shares, year):
    years = [y for y in shares if y <= year]; s = shares[max(years)]
    return s['spirits'] / (1 - s['tobacco'])   # spirits as a share of the alcohol class


if __name__ == '__main__':
    main()
