"""Offline weight-only correction using the runner's causal calibration helper."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from models import paper_tvwqrf as engine
from models.path_inputs import compound_path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def path_score_rows(data, run, bridge):
    """Report both own paired coverage and the existing bridge-common sample."""
    both = data.merge(bridge[['origin','h','yy_exante']].rename(columns={'yy_exante':'bridge_yy'}),
                      on=['origin','h'], how='left', validate='one_to_one')
    rows = []
    for sample, mask in [('full', np.ones(len(both), bool)),
                         ('recent_origins', both.origin.ge('2024-01')),
                         ('recent_targets', both.target.ge('2024-01'))]:
        for support in ('own_paired', 'paired_with_bridge'):
            required = ['original_yy','yy_exante','yy_actual']
            if support == 'paired_with_bridge':
                required.append('bridge_yy')
            for h, g in both.loc[mask].dropna(subset=required).groupby('h'):
                rows.append(dict(run=run, sample=sample, support=support, h=h, n=len(g),
                    original_rmse=float(np.sqrt(np.mean((g.original_yy-g.yy_actual)**2))),
                    corrected_rmse=float(np.sqrt(np.mean((g.yy_exante-g.yy_actual)**2))),
                    bridge_rmse=(float(np.sqrt(np.mean((g.bridge_yy-g.yy_actual)**2)))
                                 if support == 'paired_with_bridge' else np.nan)))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    source_root = ROOT/'output/paper_tvwqrf_20260912'
    target_file = ROOT/'data/paper_replication/paper_model_panel_20260912_luci/target_cpi_mm.csv'
    target_frame = pd.read_csv(target_file, float_precision='round_trip')
    target = pd.Series(target_frame.cpi_mm.to_numpy(), index=pd.PeriodIndex(target_frame.period, freq='M'))
    headline_file = ROOT/'output/independent_path_frozen_inputs.csv'
    head = pd.read_csv(headline_file, float_precision='round_trip')
    history = pd.Series(head.headline_mm.to_numpy(), index=pd.PeriodIndex(head.period, freq='M')).dropna()
    hard_file = ROOT/'output/independent_nowcast_forecasts.csv'
    hard = pd.read_csv(hard_file, float_precision='round_trip').set_index('period').HARD_BASE
    bridge_file = ROOT/'output/research_r14b/integration/forecasts.csv'
    bridge = pd.read_csv(bridge_file, float_precision='round_trip')
    bridge = bridge[bridge.model.eq('INDEPENDENT_BRIDGE')]
    monthly_rows, path_rows, sources = [], [], {str(p.relative_to(ROOT)):sha(p) for p in (target_file, headline_file, hard_file, bridge_file)}
    for name, board_name, suffix in [('realtime_full_luci', 'path_scores_luci', 'FULL'),
                                    ('realtime_full_luci_month', 'path_scores_luci_month', 'FULLM')]:
        folder = output/name
        folder.mkdir()
        source = source_root/name
        forecasts_file, quantiles_file = source/'forecasts.csv', source/'quantiles.csv'
        board_file = source_root/board_name/'board_a_forecasts.csv'
        for p in (forecasts_file, quantiles_file, source/'manifest.json', board_file):
            sources[str(p.relative_to(ROOT))] = sha(p)
        old = pd.read_csv(forecasts_file, float_precision='round_trip')
        quantiles = pd.read_csv(quantiles_file, float_precision='round_trip')
        fixed = engine.recalibrate_saved(quantiles, target)
        replacement = fixed['points'].set_index(['edge','horizon','model']).forecast
        new = old.copy()
        selected = new.model.isin(engine.SCHEMES)
        keys = pd.MultiIndex.from_frame(new.loc[selected, ['edge','horizon','model']])
        new.loc[selected,'forecast'] = replacement.reindex(keys).to_numpy()
        if not np.isfinite(new.loc[selected,'forecast']).all():
            raise ValueError('Missing corrected forecast')
        pd.testing.assert_frame_equal(old.loc[~selected], new.loc[~selected], check_exact=True)
        new.to_csv(folder/'forecasts.csv', index=False)
        for label in ('weights','diagnostics'):
            fixed[label].to_csv(folder/('tvw_weights.csv' if label == 'weights' else 'calibration.csv'), index=False)
        paired = old[['edge','horizon','model','actual','forecast','target_period']].rename(columns={'forecast':'original'})
        paired['corrected'] = new.forecast.to_numpy()
        paired = paired.merge(fixed['diagnostics'][['edge','horizon','calibration_status']], on=['edge','horizon'], validate='many_to_one')
        paired.to_csv(folder/'paired_monthly.csv', index=False)
        for sample, mask in [('all', np.ones(len(paired), bool)),
                             ('complete_calibration', paired.calibration_status.eq('past_origin_forecasts'))]:
            for (h, model), g in paired.loc[mask].groupby(['horizon','model']):
                if model not in engine.SCHEMES and model not in ('QRF_MEAN','QRF_MEDIAN'):
                    continue
                g = g.dropna(subset=['actual','original','corrected'])
                row = dict(run=name, sample=sample, horizon=h, model=model, n=len(g))
                for version in ('original','corrected'):
                    row[version+'_rmse'] = float(np.sqrt(np.mean((g[version]-g.actual)**2)))
                monthly_rows.append(row)
        old_board = pd.read_csv(board_file, float_precision='round_trip')
        path_data = old_board[old_board.model.eq('TVWQRF_TVW3_'+suffix)].copy()
        tvw = new[new.model.eq('TVW3')].copy()
        tvw['origin'] = (pd.PeriodIndex(tvw.edge, freq='M')+1).astype(str)
        paths = {}
        for origin, g in tvw.groupby('origin'):
            paths[origin] = dict(zip(g.horizon-1, g.forecast))
        new_yoy=[]
        for r in path_data.itertuples():
            origin = pd.Period(r.origin, freq='M')
            new_yoy.append(compound_path(history[history.index<origin],paths[r.origin],origin,int(r.h),hard.loc[r.origin]))
        path_data['original_yy'] = path_data.yy_exante
        path_data['yy_exante'] = new_yoy
        path_data.to_csv(folder/'paired_paths.csv', index=False)
        path_rows.extend(path_score_rows(path_data, name, bridge))
        print(name, 'complete; QRF means and medians unchanged', flush=True)
    pd.DataFrame(monthly_rows).to_csv(output/'monthly_scores.csv', index=False)
    path_scores = pd.DataFrame(path_rows)
    path_scores.to_csv(output/'path_scores.csv', index=False)
    for relative, expected in sources.items():
        if sha(ROOT/relative) != expected:
            raise ValueError('Source changed during recalibration: '+relative)
    manifest = dict(sources=sources, engine_sha256=sha(engine.__file__), script_sha256=sha(__file__),
        method='Saved own-origin quantiles, 12 consecutive matured targets, fixed feasible weights during incomplete warmup',
        unchanged_forecasts='Every non-TVW row remains exactly unchanged',
        limitations='Frozen current-vintage input conventions retained; no full forest refit in this weight-only replay',
        outputs={str(p.relative_to(output)):sha(p) for p in output.rglob('*.csv')})
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(path_scores[path_scores['sample'].eq('full') & path_scores.support.eq('paired_with_bridge')
                      & path_scores.h.isin([1,3,6,9,12])].to_string(index=False))


if __name__ == '__main__':
    main()
