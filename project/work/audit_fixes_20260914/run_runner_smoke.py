import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import paper_tvwqrf_experiment as runner

folder=ROOT/'output/audit_fixes_20260914/runner_smoke'
runner.main(['--convention','realtime','--policy','full',
             '--panel-dir',str(ROOT/'data/paper_replication/paper_model_panel_20260912_luci'),
             '--horizons','1','3','13','--first-edge','2024-01','--last-target','2025-02',
             '--limit-edges','2','--include-month','--jobs','2',
             '--forest','{"n_estimators":30}','--output',str(folder)])
cal=pd.read_csv(folder/'calibration.csv')
first=cal[cal.edge.eq('2024-01')]
assert set(first.horizon)=={1,3,13}
assert first.validation_n.eq(12).all()
assert first.calibration_status.eq('past_origin_forecasts').all()
points=pd.read_csv(folder/'forecasts.csv')
assert points.edge.ge('2024-01').all()
assert not points.duplicated(['edge','horizon','model']).any()
for _, g in points.groupby('horizon'):
    support=g.groupby('model').edge.apply(set)
    assert all(v==support.iloc[0] for v in support)
print('PASS: actual 30-tree runner, h1/h3/h13, full causal calibration at first scored origin, matching model support.')
