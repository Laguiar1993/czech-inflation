import math
import numpy as np
import pytest
from models.nowcast_reliability_r18_final import weighted_quantile


@pytest.mark.parametrize('n',range(24,61))
@pytest.mark.parametrize('p',[.05,.1,.5,.9,.95])
def test_equal_weight_inverse_cdf_has_exact_nearest_rank(n,p):
    expected=max(0,math.ceil(n*p-1e-12)-1)
    assert weighted_quantile(np.arange(n),np.ones(n),p)==expected


def test_unequal_weight_boundary_and_off_boundary():
    assert weighted_quantile([0,1,2],[.1,.2,.7],.3)==1
    assert weighted_quantile([0,1,2],[.1,.2,.7],.30000001)==2


def test_zero_mass_atoms_do_not_extend_support():
    assert weighted_quantile([-100,1,2,100],[0,.5,.5,0],0)==1
    assert weighted_quantile([-100,1,2,100],[0,.5,.5,0],1)==2


def test_unit_quantile_keeps_tiny_positive_tail():
    assert weighted_quantile([0,1],[1,1e-16],1)==1
