import pytest


def test_two_stage_driver_chain_includes_generated_predictor_centering():
    from tools.review.r16_drivers import transmission_parts
    first={'columns':['x'],'means':{'x':2.},'scales':{'x':2.},'coefficients':{'x':4.},'intercept':2.}
    second={'columns':['services_projection'],'means':{'services_projection':.5},'scales':{'services_projection':.25},'coefficients':{'services_projection':.1},'intercept':.1}
    parts=transmission_parts({},second,{'services':{'x':6.}},{'services':first})
    assert parts['services_centering']==pytest.approx(-.2)
    assert sum(parts.values())==pytest.approx(.1+.1*((10/12)-.5)/.25)
