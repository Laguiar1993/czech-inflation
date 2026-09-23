"""Independent R23 review probes; writes no production or research artifacts."""
import json
import runpy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from data.cost_gaps_r23 import features_at, load_inputs, relative_gap
from models.cost_gaps_r23 import monthly_correction, eligible, choose
from tools.research_r23.lead import lead_pairs, first_episodes, summaries
from tools.research_r23.run import targets

fixtures = runpy.run_path(str(ROOT / 'tests/test_cost_gaps_r23.py'))
report = {}

# An independent quarter/month calendar check, with a missing interior quarter.
q = pd.period_range('2000Q1', periods=13, freq='Q')
relative = pd.Series(np.arange(13, dtype=float), index=q)
assert relative_gap(relative, q[-1], 12) == 6.5
assert np.isnan(relative_gap(relative.drop(q[4]), q[-1], 12))
report['strict_consecutive_quarters'] = 'pass'

rng = np.random.default_rng(230916)
for target in rng.normal(size=(100, 4)):
    monthly = monthly_correction(target)
    np.testing.assert_allclose(monthly.reshape(4, 3).mean(axis=1), target, atol=1e-14)
    np.testing.assert_allclose(monthly.cumsum()[[2,5,8,11]], 3 * target.cumsum(), atol=1e-14)
report['interpolation_100_random_vectors'] = 'pass'

x,y,a,clocks = fixtures['label_fixture']()
t = pd.Period('2016-01', 'M'); clock = pd.Timestamp('2016-02-01')
keys = eligible(x,y,a,t,clock,24)
assert len(keys) <= 40 and all(keys.month % 3 == 0)
assert all(keys + 12 < t) and all(a.loc[keys] <= clock)
selection = choose(x,y,a,clocks,t,clock,['gap'],'ridge')
assert len(selection['validation']) == 24  # Eight folds times three alphas.
for row in selection['validation']:
    assert pd.Period(row['last_training_target'],'M') < pd.Period(row['validation_origin'],'M')
    assert pd.Timestamp(row['max_training_release']) <= pd.Timestamp(row['validation_clock'])
report['outer_and_nested_maturity'] = 'pass'

core,pub,raw,fx = fixtures['input_fixture']()
raw[26].available.loc['2008-03'] = pd.Timestamp('2010-03-01')
try:
    values,_ = features_at(core,pub,raw,fx,'2010-01','2010-02-05',{i:0. for i in range(1,13)})
    report['unpublished_interior_falls_back'] = bool(np.isnan(values.import_gap))
except Exception as exc:
    report['unpublished_interior_falls_back'] = f'{type(exc).__name__}: {exc}'

cnb = pd.DataFrame({'report_date':['2022-02-10','2022-05-12'],
                    'quarter':['2023Q1']*2,'value':[2.,2.1],'is_forecast':[True]*2})
pairs = pd.DataFrame({'report_date':['2022-02-10'],'quarter':['2023Q1'],
                      'clock':['report'],'model':['TEST'],'forecast':[2.6],'actual':[np.nan]})
small = lead_pairs(pairs,cnb)
report['small_same_sign_direction_agrees'] = bool(small.iloc[0].revision_direction_agrees)
assert small.iloc[0].call and small.iloc[0].revision_eligible and not small.iloc[0].revision_confirmed
episode = first_episodes(small,cnb)
score = summaries(episode)
assert score.iloc[0]['calls'] == 1 and score.iloc[0]['mature_calls'] == 0
report['unmatured_actual_still_counts_as_call'] = 'pass'
cnb.loc[1,'value'] = 3.4
overshoot = lead_pairs(pairs,cnb)
assert overshoot.iloc[0].revision_direction_agrees and not overshoot.iloc[0].revision_confirmed
report['overshoot_direction_vs_confirmation'] = 'pass'

cnb = pd.DataFrame({'report_date':['2022-02-10','2022-05-12','2022-08-11','2022-11-03','2023-02-02'],
                    'quarter':['2024Q1']*5,'value':[2.]*5,'is_forecast':[True]*5})
rows = pd.DataFrame({'report_date':cnb.report_date,'quarter':['2024Q1']*5,'clock':['report']*5,
                     'model':['TEST']*5,'forecast':[2.6,2.1,2.6,1.4,1.4],'actual':[2.55]*5})
events = first_episodes(lead_pairs(rows,cnb),cnb)
assert events.episode_start.tolist() == [True,False,True,True,False]
missing = rows.drop(3)
events = first_episodes(lead_pairs(missing,cnb),cnb)
assert events.episode_start.tolist() == [True,False,True,True]
report['episode_noncall_missing_report_and_sign_reset'] = 'pass'

core,pub,raw,fx,_ = load_inputs()
states = json.loads((ROOT/'output/research_r15/states.json').read_text())
features = []
for origin,state in states.items():
    values,audit = features_at(core,pub,raw,fx,origin,state['as_of'],state['seasonal'])
    features.append({'origin':origin,'complete':bool(np.isfinite(values).all())})
coverage = pd.DataFrame(features)
report['real_features'] = coverage.groupby('complete').origin.agg(['size','min','max']).reset_index().to_dict('records')
yy,available,_ = targets(core,pub,states)
origin = pd.Period('2015-03','M'); damaged = pub.copy(); damaged.loc[origin+4] = pd.NaT
bad,late,_ = targets(core,damaged,states)
assert bad.loc[origin].isna().all() and pd.isna(late.loc[origin])
actual = 100*np.log1p(core.reindex(pd.period_range(origin+1,origin+12,freq='M')).to_numpy()/100)
baseline = np.array([states[str(origin)]['forecasts_log']['fast'][str(h)] for h in range(1,13)])
np.testing.assert_allclose(yy.loc[origin],(actual-baseline).reshape(4,3).mean(axis=1))
report['target_exact_log_error_and_all_publication_gate'] = 'pass'
print(json.dumps(report, indent=2))
