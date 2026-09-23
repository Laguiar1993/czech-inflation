import numpy as np
import pandas as pd


def test_driver_contributions_respect_imputation_and_standardized_units():
    from tools.review.r15_drivers import linear_contributions
    info=dict(columns=['services','fx'],means={'services':2.,'fx':.5},scales={'services':2.,'fx':.25},
              coefficients={'services':.1,'fx':-.3},intercept=.05)
    row=linear_contributions(pd.Series({'services':4.,'fx':np.nan}),info)
    assert row=={'intercept':.05,'services':.1,'fx':0.}
