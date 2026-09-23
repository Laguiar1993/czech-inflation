"""Independent arithmetic/event audit of the post-score seasonal diagnostic."""
from pathlib import Path
import json
import sys
import hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import r17_common as c
from tools.paper_replication.build_paper_panel import load_raw


def label(values):
    if not np.isfinite(values).all(): return None
    first,second=np.diff(values)
    if first >= .5-1e-12 and second <= -.5+1e-12: return 'peak'
    if first <= -.5+1e-12 and second >= .5-1e-12: return 'trough'
    return 'none'


def sustained_label(values):
    if not np.isfinite(values).all(): return np.nan
    adjacent=np.diff(values); net=values[-1]-values[0]
    if net >= .5 and np.min(adjacent)>-.5: return 1
    if net <= -.5 and np.max(adjacent)<.5: return -1
    return 0


def main():
    full=ROOT/'output/research_r22/full'; diagnostic=ROOT/'output/research_r22/diagnostics'
    for base,file in ((full,'manifest.json'),(full/'evaluation','input_manifest.json')):
        manifest=json.loads((base/file).read_text())
        for name,digest in manifest['outputs'].items():
            assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest,name
    frame=pd.read_csv(full/'evaluation/forecast_core_outcomes.csv',float_precision='round_trip')
    fits={r['origin']:r for r in map(json.loads,(full/'fits.jsonl').read_text().splitlines())}
    states=json.loads((ROOT/'output/research_r15/states.json').read_text())
    saved=pd.read_csv(diagnostic/'seasonality_equalized_turn_pairs.csv',keep_default_na=False)
    original=pd.read_csv(full/'evaluation/underlying_core_turns.csv',keep_default_na=False)
    saved=saved.set_index(['origin','model','band']).sort_index()
    original=original.set_index(['origin','model','band']).sort_index()
    maximum_arithmetic_error=0.; checked=0; movements=[]
    for (origin,model),g in frame[frame.model.ne('JOINT_HALF_R22')].groupby(['origin','model']):
        g=g[g.h.gt(0)].sort_values('h'); month=[str((pd.Period(origin,'M')+h).month) for h in g.h]
        reference=np.array([states[origin]['seasonal'][m] for m in month])
        logforecast=100*np.log1p(g.core_mm_forecast.to_numpy()/100)
        actual=100*np.log1p(g.core_mm_actual.to_numpy()/100)-reference
        if model.endswith('_R22'):
            own=np.array([fits[origin]['preprocessing']['seasonal']['core'][m] for m in month])
            direct=logforecast-own
            transformed_mm=100*np.expm1((logforecast-own+reference)/100)
            back=100*np.log1p(transformed_mm/100)-reference
            maximum_arithmetic_error=max(maximum_arithmetic_error,float(abs(back-direct).max()))
            np.testing.assert_allclose(back,direct,atol=1e-12,rtol=1e-12)
        else: direct=logforecast-reference
        predicted_bands=12*direct.reshape(4,3).mean(axis=1)
        actual_bands=12*actual.reshape(4,3).mean(axis=1)
        movements.append(dict(origin=origin,model=model,target=str(pd.Period(origin,'M')+9),
                              predicted=sustained_label(predicted_bands[:3]),actual=sustained_label(actual_bands[:3])))
        for band in (2,3):
            prediction=label(predicted_bands[band-2:band+1]); truth=label(actual_bands[band-2:band+1])
            row=saved.loc[(origin,model,band)];old=original.loc[(origin,model,band)]
            assert row.predicted_turn==('' if prediction is None else prediction)
            assert row.actual_turn==('' if truth is None else truth)
            assert row.actual_turn==old.actual_turn
            assert row.eligible==old.eligible
            if not model.endswith('_R22'):
                assert row.predicted_turn==old.predicted_turn
            checked+=1
    assert checked==len(saved)==1800
    summary=pd.read_csv(diagnostic/'seasonality_equalized_turn_summary.csv')
    full_summary=summary[summary['sample'].eq('full')].set_index('model')
    for model,g in saved.reset_index().query('eligible').groupby('model'):
        r=full_summary.loc[model]
        assert len(g)==r.n==159
        assert g.exact_hit.sum()==r.exact_band_hits
        assert g.false_turn.sum()==r.false_turns
        assert g.actual_turn.ne('none').sum()==r.actual_turns==77
    movements=pd.DataFrame(movements).dropna(subset=['predicted','actual'])
    movement_summary=pd.read_csv(diagnostic/'seasonality_equalized_movement_summary.csv')
    for row in movement_summary.itertuples():
        g=movements[movements.model.eq(row.model)]
        if row.sample=='origins_2019_2021': g=g[g.origin.between('2019-01','2021-12')]
        elif row.sample=='origins_2022_2023': g=g[g.origin.between('2022-01','2023-12')]
        elif row.sample=='origins_2024plus': g=g[g.origin.ge('2024-01')]
        elif row.sample=='recent_targets': g=g[g.target.ge('2024-01')]
        else: assert row.sample=='full'
        events=g.actual.ne(0); calls=g.predicted.ne(0); hits=events&calls&g.actual.eq(g.predicted)
        assert row.n==len(g)
        assert row.actual_events==events.sum() and row.calls==calls.sum()
        assert row.hits==hits.sum() and row.false_calls==(calls&~hits).sum()
    raw=load_raw(luci=ROOT/'data/research_r22_no_luci.csv')
    maprows={'unemployment':11,'ulc':17,'ip':12,'imports':26,'ppi':47,'brent':60,'metals':62}
    base_sources={'core':c.monthly('tests/fixtures/cleanup/cnb_core_mm.csv','core'),
                  'fx':c.monthly('output/independent_path_frozen_inputs.csv','eurczk')}
    categories=c.monthly('data/research_r18/categories/primary_monthly_levels.csv')
    panel=pd.read_csv(full/'measurements.csv',index_col='period')
    metadata=json.loads((diagnostic/'measurement_metadata_addendum.json').read_text())
    assert len(metadata)==12
    for item in metadata:
        name=item['variable']
        source=(raw[maprows[name]].values if name in maprows else base_sources[name] if name in base_sources else categories[item['members']]).dropna()
        assert item['source_frequency']==source.index.freqstr
        assert item['source_first']==str(source.index.min())
        assert item['source_last']==str(source.index.max())
        assert item['source_observations']==len(source)
        assert item['measurement_first']==panel[name].first_valid_index()
        assert item['measurement_last']==panel[name].last_valid_index()
        assert item['measurement_finite']==np.isfinite(panel[name]).sum()
    report=dict(checks=['Full and evaluation output hashes unchanged',
        'Direct forecast log minus R22 season matches transform then subtract R15 season',
        'Independently reproduced all 1800 diagnostic event rows',
        'Actual turn labels/eligibility and all control predictions unchanged',
        'Same 159 eligible origin/bands and 77 actual turns per model',
        'Every sustained-movement summary independently reproduced',
        'Metadata frequency, source sample and transformed sample independently checked for all 12 variables'],
        max_log_arithmetic_error=maximum_arithmetic_error,
        headline_counts=full_summary.loc[['JOINT_LINEAR_R22','JOINT_RF_R22','JOINT_ENET_R22'],['predicted_turns','exact_band_hits','false_turns']].to_dict('index'))
    Path(__file__).with_name('seasonality_audit_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
