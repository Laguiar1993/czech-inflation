import pandas as pd
import pytest


def frame():
    from models.current_path import MODELS,BLOCKS
    rows=[]
    for m in MODELS:
        for h in range(13):
            rows.append(dict(origin='2026-07',model=m,h=h,target=str(pd.Period('2026-07','M')+h),
                as_of_utc='2026-08-04T12:00:00Z',mm_forecast=.3,yy_exante=2.,
                **{'contribution_'+b:.05 for b in BLOCKS}))
    return pd.DataFrame(rows)


def test_recording_checks_h0_and_all_horizons():
    from tools.current_path.record import validate_paths
    df=frame();validate_paths(df,'2026-07',.3)
    df.loc[1,'h']=15
    with pytest.raises(ValueError,match='horizon'):validate_paths(df,'2026-07',.3)


@pytest.mark.parametrize('column,value',[('mm_forecast',float('nan')),('contribution_food',.8)])
def test_recording_rejects_nonfinite_and_wrong_contributions(column,value):
    from tools.current_path.record import validate_paths
    df=frame();df.loc[2,column]=value
    with pytest.raises(ValueError):validate_paths(df,'2026-07',.3)


def test_recording_rejects_h0_substitution():
    from tools.current_path.record import validate_paths
    df=frame()
    with pytest.raises(ValueError,match='h0'):validate_paths(df,'2026-07',.4)
