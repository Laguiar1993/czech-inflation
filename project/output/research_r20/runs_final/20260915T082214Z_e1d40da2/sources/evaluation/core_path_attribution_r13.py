"""Ex-post core replacement for error accounting only; never a forecast input."""
import numpy as np
import pandas as pd


def replacement_path(frame, actual_core):
    if frame.h.duplicated().any() or sorted(frame.h.tolist()) != list(range(13)):
        raise ValueError('complete unique horizon grid h0..12 required')
    legs = ['contribution_'+v for v in ('food','administered','alcohol_tobacco','fuel','wedge')]
    result = {}
    for row in frame.to_dict('records'):
        h = int(row['h'])
        if h == 0:
            result[h] = float(row['mm_forecast'])
            continue
        pieces = np.asarray([row[v] for v in legs]+[
            row['weight_core']*actual_core.get(pd.Period(row['target'],'M'),np.nan)],dtype=float)
        result[h] = float(pieces.sum()) if np.isfinite(pieces).all() else np.nan
    return result


def error_attribution(reference, candidate, actual, replaced):
    reference_core, candidate_core = reference-replaced,candidate-replaced
    other = replaced-actual
    gain = (reference-actual)**2-(candidate-actual)**2
    core_gain = reference_core**2-candidate_core**2
    cross_gain = 2*other*(reference_core-candidate_core)
    if np.isfinite([gain,core_gain,cross_gain]).all() and abs(gain-core_gain-cross_gain)>1e-8:
        raise AssertionError('annual headline error attribution identity failed')
    return dict(reference_core_error=reference_core,candidate_core_error=candidate_core,
                other_error=other,headline_squared_gain=gain,core_squared_gain=core_gain,
                cross_term_gain=cross_gain)
