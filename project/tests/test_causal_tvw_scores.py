import numpy as np
import pandas as pd
from tools.review import recalibrate_tvw_20260914 as replay


def test_path_comparison_distinguishes_own_from_bridge_support():
    data = pd.DataFrame(dict(origin=['2024-01','2024-02'], target=['2024-02','2024-03'],
                             h=[1,1], original_yy=[1.,3.], yy_exante=[1.,2.], yy_actual=[0.,0.]))
    bridge = pd.DataFrame(dict(origin=['2024-01','2024-02'], h=[1,1], yy_exante=[.5,np.nan]))
    assert hasattr(replay, 'path_score_rows')
    rows = pd.DataFrame(replay.path_score_rows(data, 'test', bridge))
    rows = rows[rows['sample'].eq('full')].set_index('support')
    assert rows.loc['own_paired','n'] == 2
    common = rows.loc['paired_with_bridge']
    assert common['n'] == 1 and common.original_rmse == common.corrected_rmse == 1.
    assert common.bridge_rmse == .5
