import hashlib
import json

import pytest
import numpy as np

import core_split_experiment as experiment


@pytest.mark.parametrize('changed', ['core_split_forecasts.csv', 'core_split_gates.json'])
def test_offline_verification_rejects_tampered_saved_outputs(tmp_path, monkeypatch, changed):
    original_csv = b'period,R9_BASE\n2024-01,0.1\n'
    original_gates = b'{}'
    (tmp_path/'core_split_forecasts.csv').write_bytes(original_csv)
    (tmp_path/'core_split_gates.json').write_bytes(original_gates)
    manifest = {'inputs': {}, 'outputs': {'core_split_forecasts.csv': hashlib.sha256(original_csv).hexdigest()},
                'gates_sha256': hashlib.sha256(original_gates).hexdigest()}
    (tmp_path/'core_split_manifest.json').write_text(json.dumps(manifest))
    (tmp_path/changed).write_text('corrupted saved evidence')
    monkeypatch.setattr(experiment, 'OUTPUT', tmp_path)
    monkeypatch.setattr(experiment, 'run', lambda destination: manifest)
    with pytest.raises(ValueError, match='saved output changed'):
        experiment.verify()


def test_component_evidence_separates_core_improvement_from_error_cancellation():
    # The candidate improves core, yet worsens headline because the old core
    # error offset an opposite non-core error. The cross term must explain it.
    d = experiment.component_evidence(np.array([1.]), np.array([0.]), np.array([0.]),
                                      np.array([.5]), np.array([-.5]), np.array([0.]))
    assert d['weighted_core_squared_gain'][0] == pytest.approx(.25)
    assert d['headline_squared_gain'][0] == pytest.approx(-.25)
    assert d['cross_term_gain'][0] == pytest.approx(-.5)
    assert d['headline_squared_gain'][0] == pytest.approx(
        d['weighted_core_squared_gain'][0] + d['cross_term_gain'][0])
