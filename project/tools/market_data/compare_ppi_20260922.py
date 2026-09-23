"""Which Bloomberg producer-price series reproduces the manufacturing (NACE C) domestic PPI the R29B phase reads?

    python tools/market_data/compare_ppi_20260922.py

Every series in the two 22 September PPI probes is compared with A6 row 47 (Eurostat sts_inppd_m PRC_PRR_DOM C, index
2021=100) on three transforms: rebased level, m/m, and the six-month log momentum the phase uses; then the R29B phase
(building above 1.0 log point) is recomputed with each candidate at the 90 origins and compared with the recorded phase.
Rows 45 (total industry) and the CZSO import-price total are included as anchors. Output: output/bloomberg_ppi_comparison_20260922/.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from data.cost_gaps_r23 import load_inputs as load_r23
from models.core_phase_r29 import published_levels
from models.core_phase_r29b import phase_from_levels

SNAPSHOTS = ['data/market_snapshots/20260922_bloomberg_ppi_probe', 'data/market_snapshots/20260922_bloomberg_ppi_probe2']
OUT = ROOT / 'output/bloomberg_ppi_comparison_20260922'
R29B = 'output/research_r29b/final'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load():
    frames = []; meta = {}
    for s in SNAPSHOTS:
        d = pd.read_csv(ROOT / s / 'history_long.csv', low_memory=False, usecols=['ticker', 'observation_date', 'value']); frames.append(d)
        meta.update({k: v for k, v in json.loads((ROOT / s / 'metadata.json').read_text(encoding='utf-8')).items() if isinstance(v, dict) and 'name' in v})
    h = pd.concat(frames); h['p'] = pd.PeriodIndex(pd.to_datetime(h.observation_date), freq='M'); h = h.drop_duplicates(['ticker', 'p'], keep='last')
    return {t: g.set_index('p').value.astype(float).sort_index() for t, g in h.groupby('ticker')}, meta


def stats(a, b, tol):
    both = pd.concat([a.rename('a'), b.rename('b')], axis=1).dropna(); gap = (both.a - both.b).abs()
    if both.empty:
        return dict(n=0)
    return dict(n=int(len(both)), first=str(both.index.min()), last=str(both.index.max()), exact_share=float((gap <= 1e-9).mean()), within_tol_share=float((gap <= tol).mean()),
                max_abs_gap=float(gap.max()), mean_abs_gap=float(gap.mean()), corr=float(both.a.corr(both.b)) if len(both) > 2 else np.nan)


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    bbg, meta = load(); _, _, raw, _, _ = load_r23(); r47 = raw[47].values.dropna(); r45 = raw[45].values.dropna(); stamps = raw[47].available
    native = pd.read_csv(ROOT / R29B / 'native_forecasts.csv', low_memory=False); clocks = native[native.h.eq(0) & native.model.eq('STATE_FAST_R15')].drop_duplicates('origin').set_index('origin').as_of_utc.map(pd.Timestamp)
    recorded_phase = pd.read_csv(ROOT / R29B / 'phase_audit.csv').set_index('origin').czech_phase
    log47 = 100 * np.log(r47); mom47 = log47 - log47.shift(6); mm47 = 100 * (r47 / r47.shift(1) - 1)
    rows = []
    for ticker, s in sorted(bbg.items()):
        kind = meta.get(ticker, {}).get('seasonality_and_transformation', ''); name = meta.get(ticker, {}).get('name', '')
        is_change = 'MoM' in kind or 'YoY' in kind or ticker.startswith(('EPA', 'EPM', 'EPC', 'EPD', 'EPB', 'CZPPCM', 'CZPPCY'))
        row = dict(ticker=ticker, name=name, transformation=kind, n=int(s.notna().sum()), first=str(s.index.min()), last=str(s.index.max()))
        if not is_change and (s > 0).all():
            # level: rebase both to a common month, then compare m/m and momentum
            common = s.index.intersection(r47.index)
            if len(common) >= 24:
                base = common[-1]; lvl = 100 * s / s[base]; ref = 100 * r47 / r47[base]
                row.update({'level_' + k: v for k, v in stats(lvl, ref, .051).items()})
                row.update({'mm_' + k: v for k, v in stats(100 * (s / s.shift(1) - 1), mm47, .051).items()})
                logs = 100 * np.log(s); row.update({'mom6_' + k: v for k, v in stats(logs - logs.shift(6), mom47, .11).items()})
                agree = []; momenta = []
                for origin in clocks.index:
                    p_ref, d_ref = phase_from_levels(published_levels(r47, stamps, origin, clocks[origin])); p_new, d_new = phase_from_levels(published_levels(s, stamps.reindex(s.index), origin, clocks[origin]))
                    if p_ref is None or p_new is None:
                        continue
                    agree.append(p_ref == p_new); momenta.append(abs(d_ref['momentum'] - d_new['momentum']))
                if agree:
                    row.update(phase_n=len(agree), phase_agree_share=float(np.mean(agree)), phase_max_momentum_gap=float(max(momenta)), phase_vs_recorded=float(np.mean([(phase_from_levels(published_levels(s, stamps.reindex(s.index), o, clocks[o]))[0] == recorded_phase.get(o)) for o in clocks.index if phase_from_levels(published_levels(s, stamps.reindex(s.index), o, clocks[o]))[0] is not None])))
        elif is_change and 'YoY' not in kind and not ticker.endswith(('CY Index', 'CYOY Index')):
            row.update({'mm_' + k: v for k, v in stats(s, mm47, .051).items()})
        elif 'YoY' in kind or ticker.endswith(('CY Index', 'CYOY Index')):
            yy47 = 100 * (r47 / r47.shift(12) - 1); row.update({'yy_' + k: v for k, v in stats(s, yy47, .051).items()})
        rows.append(row)
    table = pd.DataFrame(rows); table.to_csv(OUT / 'comparison_vs_row47_manufacturing.csv', index=False)
    anchor = dict(row45_total_vs_PPTXCZ=stats(r45, bbg['PPTXCZ Index'], 1e-9), row47_vs_row45_mom6=stats(mom47, 100 * np.log(r45) - (100 * np.log(r45)).shift(6), .11))
    (OUT / 'anchors.json').write_text(json.dumps(anchor, indent=1), encoding='utf-8')
    (OUT / 'manifest.json').write_text(json.dumps(dict(created_at_utc=datetime.now(timezone.utc).isoformat(), snapshots={s: sha(ROOT / s / 'history_long.csv') for s in SNAPSHOTS},
                                                       r29b_native=sha(ROOT / R29B / 'native_forecasts.csv'), code=sha(__file__), outputs={p.name: sha(p) for p in sorted(OUT.iterdir()) if p.name != 'manifest.json'}), indent=1), encoding='utf-8')
    pd.set_option('display.width', 260); pd.set_option('display.max_colwidth', 34); pd.set_option('display.max_rows', 80)
    cols = [c for c in ['ticker', 'name', 'n', 'first', 'last', 'level_exact_share', 'level_max_abs_gap', 'mm_within_tol_share', 'mm_max_abs_gap', 'mm_corr', 'mom6_within_tol_share', 'mom6_max_abs_gap', 'mom6_corr', 'phase_agree_share', 'phase_max_momentum_gap', 'yy_within_tol_share', 'yy_max_abs_gap'] if c in table]
    print(table[cols].round(3).to_string(index=False)); print(json.dumps(anchor, indent=1))


if __name__ == '__main__':
    main()
