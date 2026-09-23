import numpy as np
import pandas as pd
import pytest
from tools.research_r18.evaluate import monthly_revisions, r18_branding


def rows():
    out=[]
    for i,origin in enumerate(['2020-01','2020-02']):
        r=dict(model='x',target='2020-04',origin=origin,h=3-i,mm_forecast=.2+i*.1,yy_exante=2.+i)
        for c in ['core','food','administered','alcohol_tobacco','fuel','wedge']:r['contribution_'+c]=0.
        r['contribution_core']=r['mm_forecast'];out.append(r)
    return pd.DataFrame(out)


def test_missing_old_component_stays_unavailable():
    f=rows();f.loc[0,['mm_forecast','contribution_food']]=np.nan
    result=monthly_revisions(f).iloc[0]
    assert result['revision_status']=='unavailable_component_or_total'
    assert np.isnan(result.monthly_revision)


def test_finite_revision_identity_and_bad_data_rejected():
    f=rows();r=monthly_revisions(f).iloc[0]
    assert r.monthly_revision==pytest.approx(.1)
    assert r.annual_revision==1.
    f.loc[1,'contribution_food']=1
    with pytest.raises(ValueError):monthly_revisions(f)


def test_branding_preserves_frozen_model_identifiers():
    text='<title>CNB Rounds Replayed · R17 · historical</title> Czech CPI · R17 · cnb-rounds-r17-visible-v1 {"model":"FUEL_ANNUAL_R17"}'
    result=r18_branding(text)
    assert 'FUEL_ANNUAL_R17' in result and 'FUEL_ANNUAL_R18' not in result
    assert 'cnb-rounds-r18-visible-v1' in result
    assert '<title>CNB Rounds Replayed · R18 · historical</title>' in result
