import json
import pandas as pd
import pytest


def test_sealed_path_inputs_preserve_values_and_refuse_overwrite(tmp_path):
    from tools.current_path.seal_inputs import seal
    from tools.current_path.run import load_path_inputs
    source=tmp_path/'prepared';source.mkdir();out=tmp_path/'bundle'
    (source/'pipeline_log_levels.csv').write_text('period,agri4,food_ppi,food\n2026-01,1,2,3\n')
    (source/'pipeline_available_from.csv').write_text('period,agri4,food_ppi,food\n2026-01,2026-02-26,2026-02-16,2026-02-10\n')
    (source/'pump_weekly.csv').write_text('date,gross_petrol95,gross_diesel\n2026-01-05,30,31\n')
    seal(source,out,'Test prepared inputs; not a live source refresh')
    levels,available,pump,meta=load_path_inputs(out)
    assert levels.loc[pd.Period('2026-01','M'),'food']==3
    assert meta['source_notes'].startswith('Test prepared')
    with pytest.raises(FileExistsError):seal(source,out,'second attempt')


def test_packager_requires_source_notes(tmp_path):
    from tools.current_path.seal_inputs import seal
    with pytest.raises(ValueError,match='notes'):seal(tmp_path,tmp_path/'out','')
