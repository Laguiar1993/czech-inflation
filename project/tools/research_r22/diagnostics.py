"""Post-score mechanism diagnostic and source metadata addendum; no refitting.

Equalizes forecast seasonality to R15, retaining the original R15-adjusted
actual event labels. This isolates R22's predicted dynamics from disagreement
between seasonal estimators. It is not a new competitive forecasting column.
"""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from tools.review import evaluate_r15 as prior, evaluate_r17 as evaluation
from tools.paper_replication.build_paper_panel import load_raw


def main():
    root=ROOT/'output/research_r22/full';out=ROOT/'output/research_r22/diagnostics';out.mkdir(exist_ok=True)
    frame=pd.read_csv(root/'evaluation/forecast_core_outcomes.csv')
    states=json.loads((ROOT/'output/research_r15/states.json').read_text())
    fits={d['origin']:d for d in map(json.loads,(root/'fits.jsonl').read_text().splitlines())}
    # HALF mixes simple percent changes. To avoid pretending its seasonality
    # is exactly the same mixture in log space, omit it from this diagnostic.
    models=[m for m in frame.model.unique() if m!='JOINT_HALF_R22']
    modified=frame[frame.model.isin(models)].copy()
    for origin,g in modified.groupby('origin'):
        subset=g[g.model.str.endswith('_R22') & g.h.gt(0)]
        own=fits[origin]['preprocessing']['seasonal']['core'];reference=states[origin]['seasonal']
        months=[str((pd.Period(origin,'M')+h).month) for h in subset.h]
        shift=np.array([reference[m]-own[m] for m in months])
        modified.loc[subset.index,'core_mm_forecast']=100*np.expm1(np.log1p(subset.core_mm_forecast/100)+shift/100)
    bands,changes,turns=prior.core_turn_diagnostics(modified,states)
    original=pd.read_csv(root/'evaluation/underlying_core_turns.csv')
    matched=turns.merge(original,on=['origin','model','band'],suffixes=('_diagnostic','_original'),validate='one_to_one')
    assert matched.actual_turn_diagnostic.fillna('missing').equals(matched.actual_turn_original.fillna('missing'))
    assert matched.eligible_diagnostic.equals(matched.eligible_original)
    turns.to_csv(out/'seasonality_equalized_turn_pairs.csv',index=False)
    summary=prior.turn_summaries(turns,models=models)
    summary=summary[summary.scope.eq('all_models_common')]
    summary.to_csv(out/'seasonality_equalized_turn_summary.csv',index=False)
    evaluation.sustained_summary(evaluation.sustained_rows(bands),models).to_csv(out/'seasonality_equalized_movement_summary.csv',index=False)
    raw=load_raw(luci=ROOT/'data/research_r22_no_luci.csv')
    rows={'unemployment':11,'ulc':17,'ip':12,'imports':26,'ppi':47,'brent':60,'metals':62}
    panel=pd.read_csv(root/'measurements.csv',index_col='period')
    core=c.monthly('tests/fixtures/cleanup/cnb_core_mm.csv','core')
    categories=c.monthly('data/research_r18/categories/primary_monthly_levels.csv')
    fx=c.monthly('output/independent_path_frozen_inputs.csv','eurczk')
    metadata=json.loads((root/'measurement_metadata.json').read_text())
    for item in metadata:
        name=item['variable']
        if name in rows:source=raw[rows[name]].values.dropna()
        elif name=='core':source=core.dropna()
        elif name=='fx':source=fx.dropna()
        else:source=categories[item['members']].dropna()
        item.update(source_frequency=source.index.freqstr,source_first=str(source.index.min()),source_last=str(source.index.max()),
                    source_observations=len(source),measurement_frequency='M',measurement_first=panel[name].first_valid_index(),
                    measurement_last=panel[name].last_valid_index(),measurement_finite=int(panel[name].notna().sum()))
    c.dump(out/'measurement_metadata_addendum.json',metadata)
    c.dump(out/'method.json',dict(status='post-score explanatory diagnostic; no new candidate or refit',
       transform='forecast log rate minus R22 season plus R15 season; actual and event definition unchanged',
       excluded='JOINT_HALF_R22: simple-percent mixture has no exact additive log season',
       purpose='Check whether apparent interior turns reflect seasonal disagreement rather than forecast pressure dynamics.',
       original_event_labels_unchanged=True))
    print(summary[summary['sample'].eq('full')][['model','predicted_turns','exact_band_hits','false_turns']].to_string(index=False))


if __name__=='__main__':main()
