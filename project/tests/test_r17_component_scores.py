import pandas as pd
import numpy as np
from tools.review import evaluate_r17 as e


def test_component_missing_intermediate_month_propagates_and_uses_own_value():
    native=pd.DataFrame(dict(origin='2024-01',model='x',h=range(13),target=pd.period_range('2024-01',periods=13,freq='M').astype(str),value_food=1.))
    actual=pd.DataFrame({'food':2.},index=pd.period_range('2024-01',periods=13,freq='M'));actual.loc['2024-03','food']=np.nan
    rows=e.component_outcomes(native,actual,blocks=['food']).set_index('h')
    assert rows.loc[1,'mm_forecast']==1 and rows.loc[1,'mm_actual']==2
    assert np.isnan(rows.loc[3,'cumulative_log_actual'])
    assert np.isclose(rows.loc[3,'cumulative_log_forecast'],300*np.log1p(.01))
