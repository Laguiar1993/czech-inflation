"""Offline regression tests for real production functions, with synthetic inputs.

Set CZ_STRUCT_UNDER_TEST to the source file. No live loaders are executed.
"""
from pathlib import Path
import ast,os,inspect
import numpy as np
import pandas as pd
import pytest

@pytest.fixture
def s():
    file=Path(os.environ.get('CZ_STRUCT_UNDER_TEST',str(Path(__file__).with_name('cz_struct.py'))))
    tree=ast.parse(file.read_text(encoding='utf-8'))
    names={'_regime','_basket_available_from','solve_weights','_gate_value','admin_forecast','_fuel_inputs_as_of',
           # v2.5: the calendar helpers the above now depend on
           '_release_calendar','_first_release_dt','_detail_release_dt','_cpi_family_released_by',
           '_released_index','_eligible_edge',
           # v2.7.1: the gate is split into event / headline-units / fires helpers
           '_gate_event','_gate_headline_pp','_gate_fires','_energy_item_weights_at'}
    constants={'_OFFICIAL_FOOD','_OFFICIAL_FUEL','_OFFICIAL_ALC'}
    # include plain Assign constants AND annotated module globals (AnnAssign):
    # the original filter missed `_BASKET_PUB_CACHE: dict = {}`, giving a
    # NameError inside _basket_available_from (found by /code-review).
    # v2.5: also keep private UPPER_CASE module constants (_RELEASE_HOUR,
    # _CAL_PATH, _CAL, _FALLBACK_DETAIL_DAY) that the calendar loader uses.
    def _keep(n):
        if isinstance(n,ast.FunctionDef) and n.name in names: return True
        if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id in constants for x in n.targets): return True
        if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) \
           and n.targets[0].id.startswith('_') and n.targets[0].id.upper()==n.targets[0].id: return True
        if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id.startswith('_'): return True
        return False
    nodes=[n for n in tree.body if _keep(n)]
    ann=pd.DataFrame({'announced_regulated_mm_est_pct':[16.5],'available_from':[pd.Timestamp('2021-12-15')],'provenance':['reconstructed']},index=pd.PeriodIndex(['2022-01'],freq='M'))
    # v2.4 (Fable D4 / Codex R4): the namespace MUST carry os and HERE, else
    # _basket_available_from raises NameError inside its try/except and the
    # tests silently exercise the Feb-15 fallback instead of the production
    # survey-table lookup (2026 basket published 2026-02-05).
    ns=dict(pd=pd,np=np,os=os,HERE=str(file.parent),W={'food':.188,'fuel':.035,'administered':.202},_announcements=lambda:ann)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(file),'exec'),ns)
    return ns,ann

def test_fixture_runs_production_basket_clock(s):
    ns,_=s
    # v2.5: the basket is published with the January DETAILED release (13 Feb 2026 per CZSO), not the flash
    assert ns['_basket_available_from'](2026)==pd.Timestamp('2026-02-13'),'fixture fell back to Feb-15: production lookup not exercised'
    assert ns['_basket_available_from'](2024)==pd.Timestamp('2024-02-15')

def test_missing_decision_clock_fails_closed(s):
    ns,_=s
    assert np.isnan(ns['_gate_value'](pd.Period('2022-01','M'),pd.NaT,'reconstructed_scenario'))

def test_admin_does_not_infer_month_end(s):
    ns,_=s;target=pd.Period('2022-01','M');hist=pd.Series([1.],index=pd.PeriodIndex(['2021-01'],freq='M'))
    with pytest.raises(ValueError):ns['admin_forecast'](hist,target)

def test_infinite_announcement_fails_closed(s):
    ns,a=s;a.iloc[0,a.columns.get_loc('announced_regulated_mm_est_pct')]=np.inf
    assert np.isnan(ns['_gate_value'](a.index[0],pd.Timestamp('2022-01-31'),'reconstructed_scenario'))

def test_weights_use_actual_clock_and_supplied_inputs(s):
    ns,_=s;fn=ns['solve_weights']
    assert 'as_of' in inspect.signature(fn).parameters,'solve_weights must accept the actual decision timestamp'
    assert 'alc' in inspect.signature(fn).parameters,'use the already-frozen alcohol input'
    idx=pd.period_range('2014-01','2026-01',freq='M');y=pd.Series(.2,index=idx);core=y*.9;reg=y*1.2
    comp=pd.DataFrame({'food':y*1.1,'fuel':y*.7});alc=y.copy();known=idx[-1]
    # straddle the PRODUCTION publication date of the 2026 basket (the January
    # DETAILED release, 2026-02-13 per the release calendar), not the Feb-15 fallback
    early=fn(y,comp,core,reg,known,as_of=pd.Timestamp('2026-02-12'),alc=alc)[2026]
    late=fn(y,comp,core,reg,known,as_of=pd.Timestamp('2026-02-14'),alc=alc)[2026]
    assert early['food']==ns['_OFFICIAL_FOOD'][2024]
    assert late['food']==ns['_OFFICIAL_FOOD'][2026]
    assert sum(early.values())==pytest.approx(1.)
    with pytest.raises(ValueError):fn(y,comp,core,reg,known,as_of=pd.NaT,alc=alc)

def test_alcohol_anchors_match_archived_baskets(s):
    ns,_=s
    expected={2014:.094979744,2016:.093386880,2018:.092144617,2020:.086973141,2022:.086948337,2024:.084622084,2026:.082870815}
    assert ns['_OFFICIAL_ALC']==expected

def test_future_calendar_classification_does_not_change_past(s):
    ns,a=s
    hist=pd.Series([1.,2.,10.,20.],index=pd.PeriodIndex(['2017-01','2018-01','2019-01','2020-01'],freq='M'))
    target=pd.Period('2021-01','M');f=ns['admin_forecast'];before=f(hist,target,as_of=target.end_time)
    a.loc[pd.Period('2019-01','M')]=[10.,pd.Timestamp('2025-01-01'),'reconstructed']
    assert f(hist,target,as_of=target.end_time)==before

def test_unknown_admin_mode_cannot_select_realized_target(s):
    ns,_=s;target=pd.Period('2021-01','M')
    hist=pd.Series([1.,2.,10.,20.,100.],index=pd.PeriodIndex(['2017-01','2018-01','2019-01','2020-01','2021-01'],freq='M'))
    with pytest.raises(ValueError):ns['admin_forecast'](hist,target,mode='typo',as_of=target.end_time)

def test_proxy_mode_requires_explicit_oracle_permission(s):
    ns,_=s;target=pd.Period('2021-01','M')
    hist=pd.Series([1.,2.,10.,20.,100.],index=pd.PeriodIndex(['2017-01','2018-01','2019-01','2020-01','2021-01'],freq='M'))
    with pytest.raises(ValueError):ns['admin_forecast'](hist,target,mode='proxy',as_of=target.end_time)

def test_live_and_replay_share_pump_publication_filter(s):
    ns,_=s
    assert '_fuel_inputs_as_of' in ns,'live and pre-release replay need one shared cutoff function'
    weekly=pd.DataFrame({'petrol':[30.,40.],'diesel':[29.,39.]},index=pd.to_datetime(['2026-08-17','2026-08-24']))
    brent=pd.Series([100.,999.],index=pd.to_datetime(['2026-08-23','2026-08-25']))
    wk,br=ns['_fuel_inputs_as_of'](weekly,brent,pd.Timestamp('2026-08-24'))
    assert list(wk.index)==[pd.Timestamp('2026-08-17')]
    assert list(br.index)==[pd.Timestamp('2026-08-23')]
    with pytest.raises(ValueError):ns['_fuel_inputs_as_of'](weekly,brent,pd.NaT)
